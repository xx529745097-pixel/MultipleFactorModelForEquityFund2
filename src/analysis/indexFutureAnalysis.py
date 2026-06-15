import pandas as pd
import numpy as np
import datetime
import src.data.wind as wind
import src.const as const
import matplotlib.pyplot as plt
from matplotlib import ticker


# ------------------------------------------------------
# 构建连续合约
# 【期货活跃合约（主力合约）判定规则】
# 1、每个品种只对应一个活跃合约。
# 2、月合约在最后交易日当日不能为活跃合约，剔除后，剩下的月合约按照下述规则判定。
# 3、每日收盘后，选出当日成交量和持仓量同为最大的月合约作为新的活跃合约，于下一个交易日生效。若未满足此条件，则维持原来的活跃合约不变。
# 4、若当前活跃合约指向月合约的成交量和持仓量都不是最大，则指向合约必须重新判定，新活跃合约指向成交量最大的合约，若N个合约成交量同为最大，则选择持仓量最大的合约，若持仓量也相同则选择近月合约。
# ------------------------------------------------------
def idxFutureAnls_constructStockIndexFutureContinuousContract(
    futures_id,  # string, must be "IF", "IC" OR "IH"
    start_date,  # 起始日期，输入格式:datetime.date
    end_date  # 结束日期，输入格式:datetime.date
):
    future_data = wind.wind_getStockIndexFutureData(futures_id, start_date, end_date)
    contract_dict = dict()
    date_list = future_data['date'].unique().tolist()

    for i, date in enumerate(date_list):
        if i == 0:
            single_date_future_data = future_data[future_data['date'] == date].copy()
            vol_max_contr = single_date_future_data[single_date_future_data['volume'] == single_date_future_data['volume'].max()]['contract_id'].values[0]
            contract_dict[date] = vol_max_contr
        else:
            date_last = date_list[i - 1]
            single_date_future_data = future_data[future_data['date'] == date_last].copy()
            single_date_future_data.drop(single_date_future_data[single_date_future_data['ttm'] == 1].index, inplace=True)
            vol_max_contr = single_date_future_data[single_date_future_data['volume'] == single_date_future_data['volume'].max()]['contract_id'].values[0]
            oi_max_contr = single_date_future_data[single_date_future_data['open_interest'] == single_date_future_data['open_interest'].max()]['contract_id'].values[0]
            active_contr = vol_max_contr if vol_max_contr == oi_max_contr else contract_dict[date_last]
            if active_contr != vol_max_contr and active_contr != oi_max_contr:
                active_contr = vol_max_contr
            contract_dict[date] = active_contr

    contract_dict = {'date': list(contract_dict.keys()), 'active_contract': list(contract_dict.values())}
    result = pd.DataFrame.from_dict(contract_dict)
    result['adjusted_close'] = None
    result['shift_flag'] = 0

    tmp = result['active_contract'][0]
    result = result.merge(future_data[['contract_id', 'date', 'close_price', 'ttm']], left_on=['date', 'active_contract'], right_on=['date', 'contract_id'], how="left")
    result.drop(columns=['contract_id'], inplace=True)
    result.set_index('date', inplace=True)

    for i, index in enumerate(result.index):
        if result.loc[index, 'active_contract'] != tmp:
            result.loc[index, 'shift_flag'] = 1
            last_contract_close = future_data[(future_data['date'] == index) & (future_data['contract_id'] == tmp)]['close_price'].values
            ratio = result.loc[index, 'close_price'] / last_contract_close
            result.loc[:result.index[i - 1], 'adjusted_close'] = result.loc[:result.index[i - 1], 'close_price'] * ratio
        tmp = result.loc[index, 'active_contract']

    result.reset_index(inplace=True)
    result['adjusted_close'].fillna(result['close_price'], inplace=True)
    result['nav'] = result['adjusted_close'] / result['adjusted_close'][0]
    result['return'] = result['nav'].pct_change()
    return result

# ------------------------------------------------------
# 基于连续合约分析基差
# ------------------------------------------------------
def idxFutureAnls_stockIndexFutureBasisAnalysis(
    futures_id,  # string, must be "IF", "IC" OR "IH"
    start_date,  # 起始日期，输入格式:datetime.date
    end_date  # 结束日期，输入格式:datetime.date
):
    index_id = const.const.STOCK_INDEX_FUTURES_BM_MAP[futures_id]['index_id']
    continuous_contract_data = idxFutureAnls_constructStockIndexFutureContinuousContract(futures_id, start_date, end_date)
    index_data = wind.wind_getIndexData(index_id, start_date, end_date, freq="D")

    continuous_contract_data = continuous_contract_data.merge(index_data[['date', 'close_price']], left_on='date', right_on='date', how="left")
    continuous_contract_data.rename(columns={'close_price_y': 'index_close_price'}, inplace=True)
    continuous_contract_data['basis'] = continuous_contract_data['adjusted_close'] - continuous_contract_data['index_close_price']
    continuous_contract_data['annualized_discount_premium_rate'] = (continuous_contract_data['basis'] / continuous_contract_data['index_close_price']) * (const.const.ANNUAL_SCALE / continuous_contract_data['ttm'])
    return continuous_contract_data

# ------------------------------------------------------
# 获取最近交易日股指期货连续合约与底层合约的映射关系
# ------------------------------------------------------
def idxFutureAnls_getDailyContinuousContractMapping(
    futures_id,  # string, must be "IF", "IC", "IM" OR "IH"
    date,  # 查询日期，输入格式:datetime.date
):
    wind_calendar = wind.wind_getSSECalendar()
    date = wind_calendar[wind_calendar['date'] <= date]['date'].iloc[-1]
    continuous_contract_mapping_data = wind.wind_getStockIndexFuturesContinuousContractMapping(futures_id, date, date)[['date', 'contract_id', 'mapping_contract_id']]
    continuous_contract_mapping = dict(zip(continuous_contract_mapping_data['contract_id'], continuous_contract_mapping_data['mapping_contract_id']))
    return continuous_contract_mapping

# -------------------------------------------------------------------------
# 获取分红预测年份(例如当返回值为2024，表示预测在2024年的分红情况，通常对应2023年的年报)
# 每年10月第3个周五次年六月到期的03合约上市，此时切换预测年份能考虑到03合约剩余期限内的分红事件且影响较小
# 根据当前日期确定是预测当年分红还是次年分红，返回预测年份
# 该预测报告期对全体股票是一致的，即预测周期不受个股当年是否发生了分红影响
# -------------------------------------------------------------------------
def idxFutureAnalysis_getDividendPredYear(
    date  # 考察日期
):
    date_series = pd.Series(pd.date_range(datetime.date(date.year, 10, 1), datetime.date(date.year, 10, 31)))
    third_friday = date_series[date_series.apply(lambda x: True if x.weekday() == 4 else False)].iloc[2].date()
    return date.year if date <= third_friday else date.year + 1

# ----------------------------------------------------------
# 预测个股分红次数 返回传入列表中近三年每年都出现两次以上分红的股票
# 回看近三年的分红情况，若近三年都出现了两次以上的分红
# 则预测今年会分红两次(事实优先级更高，对于已经公布的分红方案，以事实为准)
# ----------------------------------------------------------
def idxFutureAnls_getMultiDivStocks(
    date,  # 考察日期
    stock_ids=None,  # list or None, 需要预测的股票列表
    tracked_years=3  # 回看年份数
):
    assert tracked_years == 3, "预测个股分红次数逻辑暂仅支持tracked_years=3"
    # 根据报告期筛选历史分红信息，因分红日期通常晚于报告期，年份可向前多取一期(div_est_year-tracked_years-1)
    div_est_year = idxFutureAnalysis_getDividendPredYear(date)
    query_start_date = datetime.date(div_est_year-tracked_years-1, 1, 1)  # 获取分红信息的开始日期(对应report_period字段)
    # 实际统计分红时需要观察的年份(预测年份的前三年)
    observation_year_list = range(div_est_year-tracked_years, div_est_year)
    # 由于report_period一般早于分红实施日期(ex_date)，即通常当年分上一年的红，因此向前多取一年保证ex_date覆盖完整
    dividend_info = wind.wind_getAShareDividendInfo(report_period_start_date=query_start_date, report_period_end_date=date, stock_ids=stock_ids)
    # 使用现金分红金额筛选历史分红记录
    dividend_info['ex_date_year'] = dividend_info['ex_date'].apply(lambda x: x.year)
    dividend_info = dividend_info[dividend_info['ex_date_year'].isin(observation_year_list)]
    dividend_info = dividend_info[dividend_info['cash_div_per_share_pre_tax'] > 0]
    div_times_by_year = dividend_info.groupby(['stock_id', 'ex_date_year'], as_index=False).agg({'ex_date': 'count'})
    # 过去tracked_years年中发生过一年两次以上分红的股票，统计近tracked_years年出现两次以上分红的次数，当且仅当历史每年都分两次以上的情况才预测当期也分两次
    div_times_by_year = div_times_by_year[div_times_by_year['ex_date'] >= 2].groupby(['stock_id'], as_index=False).agg({'ex_date': 'count'})
    multi_div_stock_ids = div_times_by_year[div_times_by_year['ex_date'] == tracked_years]['stock_id'].to_list()
    return multi_div_stock_ids

# ------------------------------------
# 获取个股分红量计算模型信息(股利/派息率/股息率)
# 查看近三年分红记录，选择变异系数最小的计算方法(取每年第一次分红)
# 变异系数=(标准差/均值)
# ------------------------------------
def idxFutureAnls_getStockDivEstModelInfo(
    date,  # 考察日期
    stock_ids=None,  # list or None, 需要预测的股票列表
    tracked_years=3  # 回看年份数
):
    # 根据报告期筛选历史分红信息，因分红日期通常晚于报告期，年份可向前多取一期保证完整性([div_est_year-tracked_years-2,div_est_year-1))
    div_est_year = idxFutureAnalysis_getDividendPredYear(date)
    query_start_date = datetime.date(div_est_year-tracked_years-2, 12, 31)  # 获取分红信息的开始日期(对应report_period字段)
    query_end_date = datetime.date(div_est_year-1, 12, 30)
    # 实际统计分红时需要观察的年份(预测年份的前tracked_years年)
    observation_year_list = range(div_est_year - tracked_years, div_est_year)
    # 获取历史分红信息
    dividend_info = wind.wind_getAShareDividendInfo(report_period_start_date=query_start_date, report_period_end_date=query_end_date, stock_ids=stock_ids, include_additional_info=True)
    dividend_info['ex_date_year'] = dividend_info['ex_date'].apply(lambda x: x.year)
    dividend_info = dividend_info[dividend_info['ex_date_year'].isin(observation_year_list)]  # 确保区间只有指定三年
    dividend_info['ex_date_day_of_year'] = dividend_info['ex_date'].apply(lambda x: (x - datetime.date(int(x.year), 1, 1)).days)  # 当年第几日(从0开始)
    # 仅筛现金分红记录(对于从未现金分红过的股票可以认为今年也不分红，可以忽略避免变异系数分母为0，分红量为0对于测算并无影响；对于过去有过现金分红的，认为当期也分红)
    dividend_info = dividend_info[dividend_info['cash_div_per_share_pre_tax'] > 0]

    # 获取两次分红的股票，以下拆分处理
    multi_div_stock_ids = idxFutureAnls_getMultiDivStocks(date, stock_ids, tracked_years)
    single_time_dividend_info = dividend_info[~dividend_info['stock_id'].isin(multi_div_stock_ids)].sort_values(['stock_id', 'ex_date']).groupby(['stock_id', 'ex_date_year'], as_index=False).first()  # 判定为单次分红的情况，取每年第一次分红金额(通常为年报分红)
    single_time_dividend_info['div_times_type'] = 'single_time'
    # 对于预测两次分红的股票，将第一次和第二次分红拆分处理
    multi_times_dividend_info_1 = dividend_info[dividend_info['stock_id'].isin(multi_div_stock_ids)].sort_values(['stock_id', 'ex_date']).groupby(['stock_id', 'ex_date_year'], as_index=False).nth(0)
    multi_times_dividend_info_1['div_times_type'] = 'multi_times_1'
    multi_times_dividend_info_2 = dividend_info[dividend_info['stock_id'].isin(multi_div_stock_ids)].sort_values(['stock_id', 'ex_date']).groupby(['stock_id', 'ex_date_year'], as_index=False).nth(1)
    multi_times_dividend_info_2['div_times_type'] = 'multi_times_2'
    filtered_dividend_info = pd.concat([single_time_dividend_info, multi_times_dividend_info_1, multi_times_dividend_info_2], axis=0)

    # 计算变异系数(CV coefficient variation)
    def _coef_var(x):
        return x.std() / x.mean()

    # -------------------------------
    # Model 1: 股利(近三年均值与变异系数)
    # -------------------------------
    # 对单次分红/两次分红(第一次)/两次分红(第二次) 分别groupby处理
    cash_div_mean_res = filtered_dividend_info.groupby(['stock_id', 'div_times_type'], as_index=False).agg({'cash_div_per_share_pre_tax': 'mean'}).rename(columns={'cash_div_per_share_pre_tax': 'mean'})
    cash_div_cv_res = filtered_dividend_info.groupby(['stock_id', 'div_times_type'], as_index=False).agg({'cash_div_per_share_pre_tax': _coef_var}).rename(columns={'cash_div_per_share_pre_tax': 'cv'})
    cash_div_mean_res['model'] = 'cash_div'
    cash_div_cv_res['model'] = 'cash_div'

    # -------------------------------------------------------
    # Model 2: 派息率 = 股利/年报基本每股收益
    # 取分红期之前的年报eps计算派息率
    # 会存在年报数据缺失的情况，就保留缺失的状态，等后面cv比较时忽略即可
    # -------------------------------------------------------
    ashare_financial_info = wind.wind_getAShareFinancialInfo(stock_ids=stock_ids, report_period_start_date=query_start_date, report_period_end_date=query_end_date)[['date', 'stock_id', 'eps_basic']].rename(columns={'date': 'aux_eps_date'})  # aux_eps_date即eps报告期
    ashare_financial_info = ashare_financial_info[ashare_financial_info['eps_basic'] > 0]  # 仅考虑eps>0的情况(无论是历史还是当期) 否则派息率计算无意义 同时该筛选也能剔除nan
    # 对单次分红/两次分红(第一次)/两次分红(第二次) 分别groupby处理
    eps_yield_info = filtered_dividend_info[['stock_id', 'ex_date', 'cash_div_per_share_pre_tax', 'div_times_type']].copy()
    eps_yield_info['aux_eps_date'] = eps_yield_info['ex_date'].apply(lambda x: datetime.date(x.year - 1, 12, 31))  # 最近一期年报日期
    eps_yield_info = pd.merge(eps_yield_info, ashare_financial_info, on=['aux_eps_date', 'stock_id'], how='left')
    eps_yield_info['eps_yield'] = eps_yield_info['cash_div_per_share_pre_tax'] / eps_yield_info['eps_basic']
    eps_yield_mean_res = eps_yield_info.groupby(['stock_id', 'div_times_type'], as_index=False).agg({'eps_yield': 'mean'}).rename(columns={'eps_yield': 'mean'})
    eps_yield_cv_res = eps_yield_info.groupby(['stock_id', 'div_times_type'], as_index=False).agg({'eps_yield': _coef_var}).rename(columns={'eps_yield': 'cv'})
    eps_yield_mean_res['model'] = 'eps_yield'
    eps_yield_cv_res['model'] = 'eps_yield'

    # -------------------------------------
    # Model 3: 股息率 = 股利/近120交易日收盘价均价
    # (ma120d信息已从dividend_info中带出)
    # -------------------------------------
    # 对单次分红/两次分红(第一次)/两次分红(第二次) 分别groupby处理
    div_yield_info = filtered_dividend_info[['stock_id', 'ex_date', 'cash_div_per_share_pre_tax', 'ma_120d', 'div_times_type']].copy()
    div_yield_info['px_yield'] = div_yield_info['cash_div_per_share_pre_tax'] / div_yield_info['ma_120d']
    px_yield_mean_res = div_yield_info.groupby(['stock_id', 'div_times_type'], as_index=False).agg({'px_yield': 'mean'}).rename(columns={'px_yield': 'mean'})
    px_yield_cv_res = div_yield_info.groupby(['stock_id', 'div_times_type'], as_index=False).agg({'px_yield': _coef_var}).rename(columns={'px_yield': 'cv'})
    px_yield_mean_res['model'] = 'px_yield'
    px_yield_cv_res['model'] = 'px_yield'

    # -------------------------------------
    # 预测分红日期，采用过去3年分红日期的平均值
    # 此处无需限制日期为交易日，将在外层统一处理成距离预测日期最近的未来交易日
    # -------------------------------------
    # 对单次分红/两次分红(第一次)/两次分红(第二次) 分别处理
    ex_date_est_res = filtered_dividend_info.groupby(['stock_id', 'div_times_type'], as_index=False).agg({'ex_date_day_of_year': 'mean'})
    ex_date_est_res['ex_date_est'] = ex_date_est_res['ex_date_day_of_year'].apply(lambda x: datetime.date(div_est_year, 1, 1) + datetime.timedelta(days=x))

    # ------------------------------------------------------------------------
    # 分红预案日到分红实施日的平均间隔，适用于仅有预案金额但尚未确定分红日期的情况
    # 因每年第二次分红间隔普遍小于第一次分红间隔，需要根据分红次数区分处理
    # ------------------------------------------------------------------------
    ex_preland_gap_res = filtered_dividend_info[['stock_id', 'div_times_type', 'ex_date', 'preland_date']].copy()
    ex_preland_gap_res['ex_preland_gap_days'] = (filtered_dividend_info['ex_date'] - filtered_dividend_info['preland_date']).apply(lambda x: x.days)
    ex_preland_gap_type_map = {'single_time': 1, 'multi_times_1': 1, 'multi_times_2': 2}  # 简化分红预案实施日间隔的类型，即合并single_time和multi_times_1作为一类，multi_times_2作为一类
    ex_preland_gap_res['ex_preland_gap_type'] = ex_preland_gap_res['div_times_type'].map(ex_preland_gap_type_map)
    ex_preland_gap_res = ex_preland_gap_res.groupby(['stock_id', 'div_times_type', 'ex_preland_gap_type'], as_index=False).agg({'ex_preland_gap_days': lambda x: round(x.mean())})

    # 汇总数据，对于个股采用变异系数最小的模型(多次分红个股，每次分红独立计算)
    model_mean_res = pd.concat([cash_div_mean_res, eps_yield_mean_res, px_yield_mean_res], axis=0)
    model_cv_res = pd.concat([cash_div_cv_res, eps_yield_cv_res, px_yield_cv_res], axis=0)
    model_cv_res.sort_values(['stock_id', 'div_times_type', 'cv'], na_position='last', ascending=True, inplace=True)
    stock_model_info = pd.merge(model_cv_res.groupby(['stock_id', 'div_times_type'], as_index=False).first(), model_mean_res, on=['stock_id', 'model', 'div_times_type'], how='left')
    stock_model_info = pd.merge(stock_model_info, ex_date_est_res, on=['stock_id', 'div_times_type'], how='left')
    stock_model_info = pd.merge(stock_model_info, ex_preland_gap_res, on=['stock_id', 'div_times_type'], how='left')
    return stock_model_info

# ------------------------------------------------------------
# 预测股票当期分红量，适用于当期分红方案未公布的情况
# 根据个股历史模型变异值(股利/派息率/股息率)，选择变异值最小的模型用于预测
# ------------------------------------------------------------
def idxFutureAnls_getStockDivEst(
    date,  # 考察日期
    stock_ids=None  # list or None, 需要预测的股票列表
):
    # 获取预测模型结果
    stock_model_info = idxFutureAnls_getStockDivEstModelInfo(date, stock_ids)
    # -------------------------
    # 预测分红量 - 1.近三年股利均值
    # -------------------------
    cash_div_stock_model_info = stock_model_info[stock_model_info['model'] == 'cash_div'].copy()
    cash_div_res = cash_div_stock_model_info[['stock_id', 'div_times_type', 'model', 'mean', 'ex_date_est', 'ex_preland_gap_days', 'ex_preland_gap_type']].rename(columns={'mean': 'div_est'})

    # ------------------------------------------------
    # 预测分红量 - 2. 年报eps/一致预期eps * 近三年平均派息率
    # ------------------------------------------------
    # 已公布年报数据
    current_annual_report_period = datetime.date(idxFutureAnalysis_getDividendPredYear(date) - 1, 12, 31)  # 当前预测的年报期
    settled_eps_info = wind.wind_getAShareFinancialInfo(stock_ids=stock_ids, report_period_start_date=current_annual_report_period,
                                                        report_period_end_date=current_annual_report_period)[['stock_id', 'eps_basic']].rename(columns={'eps_basic': 'eps'})
    # 未公布年报数据，取最近一年的最新Wind一致预期数据(一致预期模型: 263003000 万得一致预测(180d))
    consensus_eps_info = wind.wind_getAshareConsensusEstimation(est_start_date=date-datetime.timedelta(days=365), est_end_date=date, stock_ids=stock_ids, consensus_model=['263003000'])
    # 筛选无年报数据的个股，在当前预测报告期,有eps预测数值的记录
    consensus_eps_info = consensus_eps_info[(consensus_eps_info['report_period'] == current_annual_report_period)
                                            & (~(consensus_eps_info['consen_avg_eps'].isna()))
                                            & (~(consensus_eps_info['stock_id'].isin(settled_eps_info['stock_id'].to_list())))]
    # 取最新一致预期数据
    consensus_eps_info = consensus_eps_info.sort_values(['stock_id', 'est_date']).groupby(['stock_id'], as_index=False).last()[['stock_id', 'consen_avg_eps']].rename(columns={'consen_avg_eps': 'eps'})
    eps_info = pd.concat([settled_eps_info, consensus_eps_info], axis=0)
    eps_info = eps_info[eps_info['eps'] >= 0]  # 仅考虑eps>=0的情况(无论是历史还是当期) 否则派息率计算无意义 同时该筛选也能剔除nan
    # 预测分红
    eps_yield_stock_model_info = stock_model_info[stock_model_info['model'] == 'eps_yield'].copy()
    eps_yield_stock_model_info = pd.merge(eps_yield_stock_model_info, eps_info[['stock_id', 'eps']], on='stock_id', how='left')
    eps_yield_stock_model_info['div_est'] = eps_yield_stock_model_info['eps'] * eps_yield_stock_model_info['mean']
    eps_yield_res = eps_yield_stock_model_info[['stock_id', 'div_times_type', 'model', 'div_est', 'ex_date_est', 'ex_preland_gap_days', 'ex_preland_gap_type']]

    # ----------------------------------------
    # 预测分红量 - 3. 最近120个交易日均价*平均股息率
    # ----------------------------------------
    # Ashareintensitytrend表包含ma120d指标，但每日更新时间较晚，此处采用前一日的ma120d近似
    wind_calendar = wind.wind_getSSECalendar()
    last_trade_date = wind_calendar[wind_calendar['date'] < date]['date'].iloc[-1]
    current_ma_120d = wind.wind_getStockIntensityTrendTechIndicator(stock_ids=stock_ids, start_date=last_trade_date, end_date=last_trade_date)[['stock_id', 'ma_120d']]
    px_yield_stock_model_info = stock_model_info[stock_model_info['model'] == 'px_yield'].copy()
    px_yield_stock_model_info = pd.merge(px_yield_stock_model_info, current_ma_120d[['stock_id', 'ma_120d']], on='stock_id', how='left')
    px_yield_stock_model_info['div_est'] = px_yield_stock_model_info['ma_120d'] * px_yield_stock_model_info['mean']
    px_yield_res = px_yield_stock_model_info[['stock_id', 'div_times_type', 'model', 'div_est', 'ex_date_est', 'ex_preland_gap_days', 'ex_preland_gap_type']]

    # 结果汇总 (会存在少量nan的情况，原因是已退市或eps为负，这两种情况均无需特殊处理，因为以eps作为分红量依据的股票当eps为负时可以认为当年不分红)
    # 根据计算逻辑，若个股在过去三年无现金分红，则不会出现在预测结果中
    div_est_res = pd.concat([cash_div_res, eps_yield_res, px_yield_res], axis=0)
    return div_est_res

# ---------------------------------------------------------------------------------
# 股指分红修正点位测算
# [start_date, end_date]为基差监控回看区间，contract_delist_date对应合约到期日期
# ---------------------------------------------------------------------------------
def idxFutureAnls_getIndexDividendAdjustmentSeries(
    index_id,  # string, 指数id 仅支持('000016.SH', '000300.SH', '000905.SH', '000906.SH', '000852.SH')
    start_date,  # datetime.date, 序列开始日期
    end_date,   # datetime.date, 序列截止日期
    contract_delist_dates  # list, 合约到期日期 即分红考察截止日
):
    assert index_id in ('000016.SH', '000300.SH', '000905.SH', '000906.SH', '000852.SH'), "index_id仅支持('000016.SH', '000300.SH', '000905.SH', '000906.SH', '000852.SH')"
    assert isinstance(contract_delist_dates, list), "contract_delist_dates 需为list类型"
    wind_calendar = wind.wind_getSSECalendar()
    index_dates = wind_calendar[(wind_calendar['date'] >= start_date) & (wind_calendar['date'] <= end_date)]['date'].to_list()
    # 成分股权重信息
    index_component_weight = wind.wind_getStockIndexComponentWeight(index_id=index_id, start_date=start_date, end_date=end_date, freq='D')
    # 成分股分红信息(区间起点为去年年报(含)，区间终点为今年年报(不含))
    div_est_year = idxFutureAnalysis_getDividendPredYear(end_date)  # 使用end_date进行预测区间的判断，和下方分红预测保持一致
    dividend_info = wind.wind_getAShareDividendInfo(report_period_start_date=datetime.date(div_est_year-1, 12, 31), report_period_end_date=datetime.date(div_est_year, 12, 30), stock_ids=index_component_weight['stock_id'].unique().tolist())
    # 成分股分红预测信息
    div_est_res = idxFutureAnls_getStockDivEst(date=end_date, stock_ids=index_component_weight['stock_id'].unique().tolist())
    # 判定为多次分红的个股(除非当期已公布两次分红信息，否则仍加入预测)
    est_multi_times_stock_ids = div_est_res[div_est_res['div_times_type'] == 'multi_times_2']['stock_id'].unique().tolist()
    # 1. 已公布分红金额和分红时间 或确定不分红的情况
    settled_dividend_info = dividend_info[((dividend_info['cash_div_per_share_pre_tax'] > 0) & (~dividend_info['ex_date'].isna())) | (dividend_info['no_div_flag'] == 1)][['stock_id', 'ex_date', 'cash_div_per_share_pre_tax']]
    # 2. 已公布分红金额未公布分红时间，为事实将要发生的分红时间，均需预测分红时间(即便历史判定为单次分红，出现了二次分红也需要正常预测)
    # 同时预测日期采用个股历史分红间隔进行测算，在分红日期落地前，预测分红日期需要始终满足大于当前交易日+5的条件，即保持等待分红的状态，避免因实际分红时间比预测时间更晚而被下方循环中的判断条件过滤掉
    div_amount_settled_dividend_info = dividend_info[(dividend_info['cash_div_per_share_pre_tax'] > 0) & (dividend_info['ex_date'].isna())].copy()
    # 因第二次分红间隔通常小于第一次间隔，需要首先判断分红是第几次，再根据历史间隔平均值或间隔的默认值进行填充，进而预测实际分红日期
    settled_stock_ids = settled_dividend_info['stock_id'].unique().tolist()
    div_amount_settled_dividend_info['ex_preland_gap_type'] = div_amount_settled_dividend_info['stock_id'].apply(lambda x: 1 if x not in settled_stock_ids else 2)
    div_amount_settled_dividend_info = pd.merge(div_amount_settled_dividend_info, div_est_res[['stock_id', 'ex_preland_gap_days', 'ex_preland_gap_type']], on=['stock_id', 'ex_preland_gap_type'], how='left')
    # 若无历史间隔数据(有两种情况 1.当前为第一次分红但历史三年无分红记录 2.当前为第二次以上的分红，但根据历史分红记录不被判定为多次分红的股票)，使用默认数据填充: 第一次分红间隔30天，第二次分红间隔15天
    div_amount_settled_dividend_info.loc[(div_amount_settled_dividend_info['ex_preland_gap_type'] == 1), 'ex_preland_gap_days'] = div_amount_settled_dividend_info.loc[(div_amount_settled_dividend_info['ex_preland_gap_type'] == 1), 'ex_preland_gap_days'].fillna(30)
    div_amount_settled_dividend_info.loc[(div_amount_settled_dividend_info['ex_preland_gap_type'] == 2), 'ex_preland_gap_days'] = div_amount_settled_dividend_info.loc[(div_amount_settled_dividend_info['ex_preland_gap_type'] == 2), 'ex_preland_gap_days'].fillna(15)
    div_amount_settled_dividend_info['ex_date'] = pd.to_datetime(div_amount_settled_dividend_info['preland_date']) + pd.to_timedelta(div_amount_settled_dividend_info['ex_preland_gap_days'], unit='D')
    div_amount_settled_dividend_info['ex_date'] = div_amount_settled_dividend_info['ex_date'].apply(lambda x: max(x.date(), end_date + datetime.timedelta(days=5)))
    div_amount_settled_dividend_info = div_amount_settled_dividend_info[['stock_id', 'ex_date', 'cash_div_per_share_pre_tax']]
    # 3. 未公布分红金额分红时间；或判定为分红两次但分红记录不足两次的(仅合并第二次分红预测，因为若未公布第一次分红信息，会被第一个判断条件筛选出)
    # 若股票已公布两次以上分红信息，则不进行二次分红的预测; 若预测时间距当前日期小于30天，则忽略(注意本情况和第二种有分红预案的情况不同，并不能保证后续一定有分红，不能一直保持待分红状态)
    multi_div_info_stock_ids = dividend_info[dividend_info['stock_id'].duplicated()]['stock_id'].unique().tolist()
    non_settled_dividend_info = div_est_res[(~div_est_res['stock_id'].isin(settled_dividend_info['stock_id'].to_list() + div_amount_settled_dividend_info['stock_id'].to_list()))
                                            | ((div_est_res['stock_id'].isin([s_id for s_id in est_multi_times_stock_ids if s_id not in multi_div_info_stock_ids]) & (div_est_res['div_times_type'] == 'multi_times_2')))]
    non_settled_dividend_info = non_settled_dividend_info[non_settled_dividend_info['ex_date_est'] >= end_date + datetime.timedelta(days=30)] \
        .rename(columns={'div_est': 'cash_div_per_share_pre_tax', 'ex_date_est': 'ex_date'})[['stock_id', 'ex_date', 'cash_div_per_share_pre_tax']]
    # 4.事实结果中加入上一预测期的事实分红数据，主要用于补充上一预测期中尚未完成的事实分红信息，不参与以上当期分红状态的判断(即不属于当期是否公布了分红数据的考察范围)
    # 此处无须进行日期筛选，在后续日期判断中会自动过滤；单独对div_amount_settled处理是为了在每年切换预测期时，无缝衔接上一预测期已有预案但尚未公布分红时间的股票分红，逻辑同上述情况2，这里默认的ex_preland_gap_days为15
    last_est_period_div_info = wind.wind_getAShareDividendInfo(report_period_start_date=datetime.date(div_est_year-2, 12, 31), report_period_end_date=datetime.date(div_est_year-1, 12, 30), stock_ids=index_component_weight['stock_id'].unique().tolist())
    last_est_period_settled_div_info = last_est_period_div_info[((last_est_period_div_info['cash_div_per_share_pre_tax'] > 0) & (~last_est_period_div_info['ex_date'].isna())) | (last_est_period_div_info['no_div_flag'] == 1)][['stock_id', 'ex_date', 'cash_div_per_share_pre_tax']]
    last_est_period_div_amount_settled_dividend_info = last_est_period_div_info[(last_est_period_div_info['cash_div_per_share_pre_tax'] > 0) & (last_est_period_div_info['ex_date'].isna())].copy()
    last_est_period_div_amount_settled_dividend_info['ex_preland_gap_days'] = 15
    last_est_period_div_amount_settled_dividend_info['ex_date'] = pd.to_datetime(last_est_period_div_amount_settled_dividend_info['preland_date']) + pd.to_timedelta(last_est_period_div_amount_settled_dividend_info['ex_preland_gap_days'], unit='D')
    last_est_period_div_amount_settled_dividend_info['ex_date'] = last_est_period_div_amount_settled_dividend_info['ex_date'].apply(lambda x: max(x.date(), end_date + datetime.timedelta(days=5)))
    last_est_period_div_amount_settled_dividend_info = last_est_period_div_amount_settled_dividend_info[['stock_id', 'ex_date', 'cash_div_per_share_pre_tax']]
    # 合并事实结果
    settled_dividend_info = pd.concat([settled_dividend_info, last_est_period_settled_div_info], axis=0)  # 加入上一预测期的事实分红数据
    settled_dividend_info['status'] = 'settled'
    # 合并测算结果
    div_amount_settled_dividend_info = pd.concat([div_amount_settled_dividend_info, last_est_period_div_amount_settled_dividend_info], axis=0)  # 加入上一预测期的'有预案'的分红数据
    div_amount_settled_dividend_info['status'] = 'div_amt_settled'
    non_settled_dividend_info['status'] = 'non_settled'
    # 合并分红信息 并将ex_date映射为最近的未来交易日(预测日期采用的是时间间隔测算得到的，不能保证刚好落在交易日，因此需要处理)
    ref_dividend_info = pd.concat([settled_dividend_info, div_amount_settled_dividend_info, non_settled_dividend_info], axis=0)
    ref_dividend_info['ex_date'] = ref_dividend_info['ex_date'].apply(lambda x: wind_calendar[wind_calendar['date'] >= x]['date'].iloc[0] if not pd.isna(x) else x)
    # 指数/个股收盘价数据
    index_close_data = wind.wind_getIndexData(index_id, start_date, end_date, 'D')[['date', 'close_price']].rename(columns={'close_price': 'benchmark_close'})
    component_close_data = wind.wind_getAShareStockTradeData(stock_ids=index_component_weight['stock_id'].unique().tolist(), start_date=start_date, end_date=end_date)[['stock_id', 'trade_date', 'close']]
    # 分红点数计算
    res = []
    for contract_delist_date in contract_delist_dates:
        adjustment_points_res = {'total': [], 'settled': [], 'div_amt_settled': [], 'non_settled': []}
        contract_res = index_close_data.copy()
        # 遍历区间日期
        for date in index_dates:
            assert date <= contract_delist_date, "行情区间应不晚于期货合约到期日期"
            # 使用date过滤未来信息, 并考虑从分红方案确定到执行需要一段时间
            # 对于事实分红信息，全部保留；对于仅有预案金额的分红信息，在之前的处理中已保证日期>=t+5；无金额信息的，在之前的处理中已保证日期>=t+30日。
            filtered_dividend_info = ref_dividend_info[(ref_dividend_info['ex_date'] > date) & (ref_dividend_info['ex_date'] <= contract_delist_date)].copy()
            daily_component_weight = index_component_weight[index_component_weight['index_data_date'] == date][['stock_id', 'stock_weight']]
            # 添加权重信息
            filtered_dividend_info = pd.merge(filtered_dividend_info, daily_component_weight, on='stock_id', how='inner')
            # 添加收盘价信息
            index_close_price = index_close_data[index_close_data['date'] == date]['benchmark_close'].iloc[0]
            component_close_price = component_close_data[(component_close_data['trade_date'] == date) & (component_close_data['stock_id'].isin(daily_component_weight['stock_id'].to_list()))]
            filtered_dividend_info = pd.merge(filtered_dividend_info, component_close_price[['stock_id', 'close']], on='stock_id', how='left')
            filtered_dividend_info['benchmark_close'] = index_close_price
            # 分红点数 = sum((每股股利/当日收盘价)*成分股权重*指数收盘价)
            filtered_dividend_info['adjustment_points'] = filtered_dividend_info['cash_div_per_share_pre_tax'] / filtered_dividend_info['close'] * filtered_dividend_info['stock_weight'] * filtered_dividend_info['benchmark_close']
            # 避免无分红数据时返回nan
            settled_adjustment_points = filtered_dividend_info.loc[filtered_dividend_info['status'] == 'settled', 'adjustment_points'].sum()
            div_amount_settled_adjustment_points = filtered_dividend_info.loc[filtered_dividend_info['status'] == 'div_amt_settled', 'adjustment_points'].sum()
            non_settled_adjustment_points = filtered_dividend_info.loc[filtered_dividend_info['status'] == 'non_settled', 'adjustment_points'].sum()
            # 存入分红结果
            adjustment_points_res['total'].append(settled_adjustment_points + div_amount_settled_adjustment_points + non_settled_adjustment_points)
            adjustment_points_res['settled'].append(settled_adjustment_points)
            adjustment_points_res['div_amt_settled'].append(div_amount_settled_adjustment_points)
            adjustment_points_res['non_settled'].append(non_settled_adjustment_points)
            # 合并返回指数原始点位和修正点位数
        contract_res['adjustment_points'] = adjustment_points_res['total']
        contract_res['settled_adjustment_points'] = adjustment_points_res['settled']
        contract_res['div_amount_settled_adjustment_points'] = adjustment_points_res['div_amt_settled']
        contract_res['non_settled_adjustment_points'] = adjustment_points_res['non_settled']
        contract_res['delist_date'] = contract_delist_date
        res.append(contract_res)
    res = pd.concat(res, axis=0)
    return res
