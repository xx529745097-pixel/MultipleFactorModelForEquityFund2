import os.path
import time

import pandas as pd
import datetime
from dateutil.relativedelta import relativedelta
import numpy as np
import sqlalchemy
from dateutil.parser import parse
from matplotlib import pyplot as plt
import src.utils.Calculation as Cal
import src.data.wind as wind
import src.analysis.MFAnalysis as MFanls
import src.utils.backtest as bt
import fstrat_config
import warnings
warnings.filterwarnings('ignore')
import pulp


def towindcode(x):
    if x[0] == '1':
        x = x[:-2] + 'SZ'
    if x[0] == '5':
        x = x[:-2] + 'SH'
    return x

def otc_to_inside(list1):
    import sqlalchemy
    import os

    os.environ['NLS_LANG'] = 'SIMPLIFIED CHINESE_CHINA.UTF8'
    ora_connect_str  = 'oracle://xujunwei:40!VEz6QX@10.23.153.15:21010/wind'
    dbengine = sqlalchemy.create_engine(ora_connect_str, poolclass=sqlalchemy.pool.NullPool)
    dbconn = dbengine.connect()
    sql = "select F_INFO_WINDCODE " \
          "from ChinaMutualFundDescription "
    df = pd.read_sql_query(sql, dbconn)
    list2 = df['f_info_windcode'].tolist()
    for i in range(len(list1)):
        if list1[i] not in list2:
            list1[i] = towindcode(list1[i])
    return list1


# -----------------------------------------------
# 获取模型运行日期t和调仓日期t+2交易日
# 符合公募场外申购赎回规则：t日收盘后模型给出结果，t+1日完成申赎，t+2日确认份额开始计算收益
# -----------------------------------------------
def fstrat_getAdjustmentCalendar(
    freq='Q'     # 调仓频率
):
    assert freq in ('Q', 'W'), "暂仅支持季频/周频调仓"
    adjustment_calendar = wind.wind_getSSECalendar().rename(columns={'date': 'model_date'})
    adjustment_calendar['effective_date'] = adjustment_calendar['model_date'].shift(-2)  # 模型日期为t日，调仓生效日期为t+2日
    if freq == 'Q':
        adjustment_calendar['year'] = adjustment_calendar['model_date'].apply(lambda x: x.year)
        adjustment_calendar['month'] = adjustment_calendar['model_date'].apply(lambda x: x.month)
        adjustment_calendar = adjustment_calendar[adjustment_calendar['month'].isin([1, 4, 7, 10])]  # 1, 4, 7, 10月末调仓
        adjustment_calendar = adjustment_calendar.groupby(['year', 'month']).last().sort_values('model_date').reset_index(drop=True)
    elif freq == 'W':  # only Fridays
        adjustment_calendar['weekday'] = adjustment_calendar['model_date'].apply(lambda x: x.weekday())
        adjustment_calendar = adjustment_calendar[adjustment_calendar['weekday'] == 4]
    else:
        raise Exception(f'{freq}频率未定义')
    return adjustment_calendar[['model_date', 'effective_date']]

# --------------------------------------------
# 筛选CC30公募基金池
# 1. 股票型，偏股混合型，高仓位灵活配置型(>=50%)开放式基金，无最短持有期限
# 2. 至少一位现任基金经理任职时间大于1年
# 3. 基金最新规模大于2亿
# 4. 近四个季度权益平均仓位大于50%
# 5. 开放申购赎回
# --------------------------------------------
def fstrat_getCC30EquityMFPool(
    date,    # 考察日期
    company_id = False  #是否保留公司id
):
    mf_info = wind.wind_getHistoricalProductList(as_of_date=date, include_pm_info=True)  # 获取历史初始基金，即AC份额仅考虑A份额
    # 筛选正在生效的sector type标签
    mf_info = mf_info[(mf_info['sector_start_date'] <= date) & ((mf_info['sector_end_date'] >= date) | mf_info['sector_end_date'].isna())]
    mf_info = mf_info[mf_info['type'].isin(['普通股票型基金', '偏股混合型基金', '灵活配置型基金'])]
    mf_info = mf_info[(mf_info['fund_open_type'] == '契约型开放式') & (mf_info['min_holding_month'].isna())]
    mf_info = mf_info[~(mf_info['product_full_name'].str.contains('定开') | mf_info['product_full_name'].str.contains('持有') | mf_info['product_full_name'].str.contains('定期'))]
    # 筛选正在任职的PM，保留任职时间大于1Y
    mf_info = mf_info[(mf_info['pm_start_date'] <= date) & ((mf_info['pm_end_date'] >= date) | mf_info['pm_end_date'].isna())]
    mf_info['pm_duration_days'] = (mf_info['pm_end_date'].apply(lambda x: min(date, x) if not pd.isna(x) else date) - mf_info['pm_start_date']).apply(lambda x: x.days)
    mf_info = mf_info[mf_info['pm_duration_days'] >= 365]
    # 基金最新规模大于2亿
    mf_latest_aum = wind.wind_getMFLatestAUM(date - datetime.timedelta(days=365), date)
    mf_info = pd.merge(mf_info, mf_latest_aum[['product_id', 'aum']], on=['product_id'], how='left')
    mf_info = mf_info[mf_info['aum'] >= 2e8]
    # 近一年权益平均仓位大于50%
    mf_position = wind.wind_getMFAssetAllocation(date - datetime.timedelta(days=450), date).sort_values(['product_id', 'date'])  # 默认only_a_share=True
    mf_avg_position = mf_position.groupby(['product_id'])['product_stk_value_to_nav'].rolling(4).mean().reset_index()
    mf_latest_avg_position = mf_avg_position.groupby(['product_id'], as_index=False).last()
    mf_info = pd.merge(mf_info, mf_latest_avg_position[['product_id', 'product_stk_value_to_nav']], on='product_id', how='left')
    mf_info = mf_info[mf_info['product_stk_value_to_nav'] >= 0.5]
    # 无申购赎回限制
    suspend_info = wind.wind_getCurrentProductSuspendInfo(date, date)
    mf_info = mf_info[~mf_info['product_id'].isin(suspend_info['product_id'])]
    # 加入日期
    mf_info['date'] = date
    # 加入pm信息，不对产品去重
    if company_id:
        fund_universe = mf_info[['date', 'product_id', 'product_name', 'aum', 'pm_name', 'company_id']].sort_values('product_id')
    else:
        fund_universe = mf_info[['date', 'product_id', 'product_name', 'aum', 'pm_name']].sort_values('product_id')
    return fund_universe

# ------------------------------------------------
# 计算基金的jensen，选股能力(alpha)，选时能力(gamma)，Sharpe
# jensen-alpha = (ri-rf) - beta_i(rm-rf)
# 选股能力(alpha)，选时能力(gamma)： r-rf = alpha + beta(rm-rf) + gamma(rm-rf)**2 + epsilon
# ------------------------------------------------
def anlsMF_SelectedRatingIndicator(
        product_ids,                                    # list
        startdate,                                      # datetime.date
        enddate,                                        # datetime.datezxzq
        freq='D',                                       # freq, 'D' or 'W'
        benchmark = '000300.SH',                        # benchmark, str.
        rf = 0.03                                       # risk-free rate (annual)
):
    retDf = wind.wind_getMFStats(product_ids, startdate-relativedelta(weeks=4), enddate, ['f_avgreturn_day'])
    wind_calendar = wind.wind_getSSECalendar()
    retDf = retDf[retDf['date'].isin(wind_calendar['date'].to_list())].fillna(0)  # 仅保留交易日，缺失值填充为0
    if freq == 'W':  # convert to weekly freq
        retDf = fof_calendar.calender_convertDailyReturnToWeekly(retDf, date_column_name='date', return_column_name='f_avgreturn_day', id_column_name='product_id')
    retDf = pd.pivot_table(retDf, values='f_avgreturn_day', index='date', columns='product_id').loc[startdate:enddate]
    retDf = retDf.fillna(0)  # 部分封闭期基金只披露周度净值，处理nan项。
    idxret = wind.wind_getIndexReturn(benchmark, startdate, enddate, freq)
    # 以end_date作为考察时点
    latest_aum_info = wind.wind_getMFLatestAUM(startdate, enddate)
    # # 以end_date作为考察时点的6个月调研数量变动因子
    # delta_survey_6m_data = anlsMF_getMFDeltaSurveyIndicator(enddate, tracked_months=6)
    # delta_survey_6m = pd.DataFrame(product_ids, columns=['product_id'])
    # delta_survey_6m = pd.merge(delta_survey_6m, delta_survey_6m_data[['product_id', 'delta_survey']], on='product_id', how='left').fillna(0)  # 缺失值填充为0
    # 以end_date作为考察时点的最新员工自购比例
    employee_holding_ratio_data = wind.wind_getMFLatestHoldingStructure(enddate)
    employee_holding_ratio = pd.DataFrame(product_ids, columns=['product_id'])
    employee_holding_ratio = pd.merge(employee_holding_ratio, employee_holding_ratio_data[['product_id', 'employee_holding_ratio']], on='product_id', how='left').fillna(0)  # 缺失值填充为0
    # # 相对885001跟踪误差(超额波动率因子)
    # tracking_error_885001 = anlsMF_getMFVolatilityIndicator(product_ids, startdate, enddate, freq, vol_type='std', benchmark='885001.WI')
    # # 相对000906跟踪误差(超额波动率因子)
    # tracking_error_000906 = anlsMF_getMFVolatilityIndicator(product_ids, startdate, enddate, freq, vol_type='std', benchmark='000906.SH')
    # # 收益非线性波动率，log(1 + 100*vol)^3对log(1 + 100*vol)线性回归的残差项
    # vol_nl = anlsMF_getMFVolatilityIndicator(product_ids, startdate, enddate, freq, vol_type='nl', benchmark=None)
    indicator_result = pd.DataFrame(columns=[*product_ids], index=['jensen_beta', 'jensen_alpha', 'sharpe', 'mdd', 'employee_holding_ratio'])
    for product in product_ids:
        jensen_alpha, jensen_beta = MFanls.basicCal_jensen(retDf[product], idxret, freq, rf)  # CAPM Model
        indicator_result.loc['jensen_beta', product] = jensen_beta
        indicator_result.loc['jensen_alpha', product] = jensen_alpha
        # tm_alpha, tm_beta, tm_gamma = basicCal_AlphaGamma(retDf[product], idxret, freq, rf)  # TM Model
        # indicator_result.loc['TM_gamma', product] = tm_gamma
        # indicator_result.loc['TM_alpha', product] = tm_alpha
        indicator_result.loc['sharpe', product] = MFanls.basicCal_getSharpeRatio(retDf[product], freq, rf)
        indicator_result.loc['mdd', product] = abs(MFanls.basicCal_getMaxDrawdown(retDf[product]))  # 使用mdd绝对值，反向指标
        # indicator_result.loc['size', product] = latest_aum_info[latest_aum_info['product_id'] == product]['aum'].iloc[0]
        # indicator_result.loc['delta_survey_6m', product] = delta_survey_6m[delta_survey_6m['product_id'] == product]['delta_survey'].iloc[0]
        indicator_result.loc['employee_holding_ratio', product] = employee_holding_ratio[employee_holding_ratio['product_id'] == product]['employee_holding_ratio'].iloc[0]
        # indicator_result.loc['tracking_error_885001', product] = tracking_error_885001[tracking_error_885001['product_id'] == product]['vol_std'].iloc[0]
        # indicator_result.loc['tracking_error_000906', product] = tracking_error_000906[tracking_error_000906['product_id'] == product]['vol_std'].iloc[0]
        # indicator_result.loc['vol_nl', product] = vol_nl[vol_nl['product_id'] == product]['vol_nl'].iloc[0]
    indicator_result = indicator_result.T.reset_index()
    indicator_result = indicator_result.rename({'index': 'product_id'}, axis=1)
    indicator_result.rename(columns={'index': 'factor'}, inplace=True)
    return indicator_result



# -----------------------------------------
# 因子计算模块 获取模型因子得分并缓存
# -----------------------------------------
def fstrat_getCC30ProductScore(
    date,                   # 考察日期
    path,
    model_freq='Q',             # 模型调仓频率 决定了模型的运行日期
    benchmark='000906.SH',  # 指标计算基准
    rf=0.03                # 无风险利率
):
    # 计算最近两次模型运行日期
    if model_freq == 'Q':
        adj_calendar = fstrat_getAdjustmentCalendar(freq=model_freq)
    if model_freq == 'W':
        adj_calendar1 = fstrat_getAdjustmentCalendar(freq='Q')
        adj_calendar2 = fstrat_getAdjustmentCalendar(freq='W')
        adj_calendar = pd.concat([adj_calendar1, adj_calendar2], axis=0).drop_duplicates(subset=["model_date"])
        adj_calendar.dropna(inplace=True)
        adj_calendar.sort_values(by='model_date', inplace=True)
    # assert date in adj_calendar['model_date'].to_list(), "入参date需为模型运行日期"
    anls_start_date = date - datetime.timedelta(days=365)
    # 获取基金池和当期模型打分并缓存
    fund_universe = pd.read_excel(path)
    fund_universe['product_id'] = otc_to_inside(fund_universe['product_id'])
    sql1 = "select F_INFO_WINDCODE as product_id, F_INFO_ISINITIAL as is_initial " \
           "from ChinaMutualFundDescription "
    df1 = pd.read_sql_query(sql1, wind.wind_connectWindDB())
    fund_universe = pd.merge(fund_universe, df1, on = 'product_id')
    fund_universe = fund_universe[fund_universe['is_initial']==1].reset_index(drop = True)
    # # 剔除掉不在备选库的基金公司的产品
    # fundCompanyPool = pd.read_excel(fstrat_config.cc30_run_path+"基金公司库.xlsx")
    # fundCompanyPool = fundCompanyPool[fundCompanyPool['所属库'] == '基金公司备选库']
    # fundCompanyPool2 = fundCompanyPool['基金公司代码'].to_list()
    # sql_1 = "select COMP_NAME, COMP_SNAME, COMP_ID " \
    #         "from CFundIntroduction "
    # dbconn = wind.wind_connectWindDB()
    # fundcompanylist = pd.read_sql_query(sql_1, dbconn)
    # fund_universe = fund_universe[fund_universe['company_id'].isin(fundCompanyPool2)]

    # 缓存基金池 数据带PM不去重
    # fund_universe.to_excel(fstrat_config.cc30_run_path+"基金池_{}.xlsx".format(date), index=None)
    # 因子计算
    product_ids = fund_universe['product_id'].unique().tolist()
    product_indicator_info = anlsMF_SelectedRatingIndicator(product_ids, anls_start_date, date, 'D', benchmark, rf)  # 因子底层使用日频收益计算
    indicator_score = product_indicator_info.set_index('product_id').rank(pct=True, ascending=True).reset_index()   # 将因子值转化为排名，越大表现越好。
    weekly_perf_rank_stability = MFanls.anlsMF_RankStability(product_ids, anls_start_date, date)   # 周度收益率的排名稳定性
    product_score = pd.merge(indicator_score, weekly_perf_rank_stability, on='product_id', how='left')
    # 缓存因子打分
    start_index = path.rfind('_') + 1  # 最后一个_的下一个位置
    end_index = path.rfind('.')  # 扩展名前的点位置
    cate = path[start_index:end_index]
    product_score.to_excel("债基-输出结果/固收+因子打分_{0}_{1}.xlsx".format(date,cate), index=None)
    return product_score

# -----------------------------------------
# 回测缓存CC30模型的最终产品清单
# 设置缓冲池，每位PM仅保留一个产品
# -----------------------------------------
def fstrat_getCC30ModelFinalProductList(
    date,              # 考察日期 需为模型运行日期
    model_freq='Q',    # 模型调仓频率 决定了模型的运行日期
    shortlist_num=30,  # 模型最终输出的产品个数
    buffer_size=90     # 缓冲池大小
):
    # 计算最近两次模型运行日期
    if model_freq == 'Q':
        adj_calendar = fstrat_getAdjustmentCalendar(freq=model_freq)
    if model_freq == 'W':
        adj_calendar1 = fstrat_getAdjustmentCalendar(freq='Q')
        adj_calendar2 = fstrat_getAdjustmentCalendar(freq='W')
        adj_calendar = pd.concat([adj_calendar1, adj_calendar2], axis=0).drop_duplicates(subset=["model_date"])
        adj_calendar.dropna(inplace = True)
        adj_calendar.sort_values(by = 'model_date', inplace = True)
    assert date in adj_calendar['model_date'].to_list(), "入参date需为模型运行日期"
    previous_model_date = adj_calendar[adj_calendar['model_date'] < date]['model_date'].iloc[-1]

    # -------------------
    # 读取上一期最终名单
    # -------------------
    previous_shortlist_res_path = fstrat_config.cc30_shortlist_res_path.format(previous_model_date)
    assert os.path.exists(previous_shortlist_res_path), f"未找到{previous_shortlist_res_path}，请先缓存上一期最终名单"  # 需要取到上一期结果得到缓冲池产品
    previous_shortlist_res = pd.read_excel(previous_shortlist_res_path, index_col=0)[['product_id']].reset_index().rename(columns={'index': 'previous_index'})

    # -------------------------
    # 读取当期基金池 包含多行pm信息
    # -------------------------
    fund_universe_path = fstrat_config.cc30_fund_universe_path.format(date)
    assert os.path.exists(fund_universe_path), f"未找到{fund_universe_path}，请先缓存当期基金池结果"  # 需要取到当期的打分结果
    fund_universe = pd.read_excel(fund_universe_path)
    fund_universe['date'] = pd.to_datetime(fund_universe['date']).dt.date

    # -------------------
    # 读取当期的打分结果
    # -------------------
    current_fund_score_path = fstrat_config.cc30_fund_score_path.format(date)
    assert os.path.exists(current_fund_score_path), f"未找到{current_fund_score_path}，请先缓存当期打分结果"  # 需要取到当期的打分结果
    product_score = pd.read_excel(current_fund_score_path)

    # -------------------
    # 模型策略部分 因子权重
    # -------------------
    # JW30
    product_score['score'] = (0.143 * product_score['sharpe'] - 0.071 * product_score['mdd'] - 0.071 * product_score['jensen_beta'] + 0.143 * product_score['jensen_alpha']
     + 0.143 * product_score['TM_gamma'] - 0.143 * product_score['size'] + 0.143 * product_score['delta_survey_6m'] + 0.143 * product_score['employee_holding_ratio']) + 0.2850
    # # CC30
    # product_score['score'] = 0.2*product_score['jensen_beta'] + 0.4*product_score['sharpe'] + 0.1*product_score['TM_gamma'] + 0.1*product_score['TM_alpha'] + 0.2*product_score['stability']
    product_score.sort_values('score', ascending=False, inplace=True)

    # -------------------
    # 生成最终名单
    # -------------------
    # 多pm的产品会保留多行, 此处是为了引入pm信息
    product_score_with_info = pd.merge(fund_universe, product_score, on='product_id', how='left').sort_values('score', ascending=False)
    # 缓冲池中属于上一期模型结果的产品进行保留处理
    buffered_product_ids = product_score_with_info['product_id'].unique().tolist()[:buffer_size]
    retained_product_ids = previous_shortlist_res[previous_shortlist_res['product_id'].isin(buffered_product_ids)]['product_id'].to_list()
    # 从上一期名单中保留下产品的信息，目的是获取pm信息进行下一步pm去重
    retained_product_score_with_info = product_score_with_info[product_score_with_info['product_id'].isin(retained_product_ids)]
    # 首先排除上一期保留下的基金以及这些基金经理管理的其他产品，对剩余基金仅保留每个pm得分最高的一只产品
    product_score_with_info_exclude_retained = product_score_with_info[~(product_score_with_info['product_id'].isin(retained_product_score_with_info['product_id'].unique().tolist()))
                                                             & ~(product_score_with_info['pm_name'].isin(retained_product_score_with_info['pm_name'].unique().tolist()))]
    product_score_with_info_exclude_retained = product_score_with_info_exclude_retained.groupby(['pm_name'], as_index=False).first().sort_values('score', ascending=False)
    # 对结果去重, 取前30名作为模型输出, 加入上一期结果的序号(如有，若为空则为新增产品)
    shortlist_res = pd.concat([retained_product_score_with_info, product_score_with_info_exclude_retained], axis=0)[['date', 'product_id', 'product_name', 'score']].drop_duplicates().iloc[:shortlist_num]

    # -------------
    # 加权方式
    # -------------
    shortlist_res['weight'] = 1 / len(shortlist_res)  # 等权进行组合

    # --------------
    # 缓存最终名单
    # --------------
    shortlist_res = pd.merge(shortlist_res, previous_shortlist_res[['product_id', 'previous_index']], on='product_id', how='left')  # 加入上一期名单序号
    shortlist_res.to_excel(fstrat_config.cc30_shortlist_res_path.format(date))  # 缓存最终名单
    return shortlist_res

#############################################################################################
#以下为xjw改动部分
#############################################################################################

def get_previous_trading_dates(target_date, num_days=5):
    """
    获取某个日期的前 num_days 个交易日日期
    :param target_date: 目标日期，格式为 'YYYY-MM-DD' 或 datetime.date
    :param num_days: 需要获取的交易日数量，默认为 5
    :return: 前 num_days 个交易日日期的列表
    """
    # 转换为 datetime.date 格式
    if isinstance(target_date, str):
        target_date = pd.to_datetime(target_date).date()

    # 获取上交所的交易日历（可以根据需要替换为其他交易所）
    trading_days = wind.wind_getSSECalendar()

    # 筛选出目标日期之前的交易日
    trading_days = trading_days[trading_days['date'] < target_date]

    # 获取前 num_days 个交易日日期
    previous_trading_dates = trading_days[-num_days:].date.tolist()

    return previous_trading_dates


def getQuarterDates(startdate, enddate):
    quaterdates = []
    if startdate.year == enddate.year:
        if startdate.month <= 9:
            if enddate.month >= 10 or (enddate.month == 9 and enddate.day == 30):
                quaterdates.append(datetime.date(startdate.year, 9, 30))
        if startdate.month <= 6:
            if enddate.month >= 7 or (enddate.month == 6 and enddate.day == 30):
                quaterdates.append(datetime.date(startdate.year, 6, 30))
        if startdate.month <= 3:
            if enddate.month >= 4 or (enddate.month == 3 and enddate.day == 31):
                quaterdates.append(datetime.date(startdate.year, 3, 31))
        if (enddate.month == 12 and enddate.day == 31):
            quaterdates.append(datetime.date(startdate.year, 12, 31))
    else:
        for year in range(startdate.year, enddate.year + 1):
            if year == startdate.year:
                quaterdates.append(datetime.date(year, 12, 31))
                if startdate.month <= 9:
                    quaterdates.append(datetime.date(year, 9, 30))
                    if startdate.month <= 6:
                        quaterdates.append(datetime.date(year, 6, 30))
                        if startdate.month <= 3:
                            quaterdates.append(datetime.date(year, 3, 31))
            elif year == enddate.year:
                if enddate.month >= 4 or (enddate.month == 3 and enddate.day == 31):
                    quaterdates.append(datetime.date(year, 3, 31))
                    if enddate.month >= 7 or (enddate.month == 6 and enddate.day == 30):
                        quaterdates.append(datetime.date(year, 6, 30))
                        if enddate.month >= 10 or (enddate.month == 9 and enddate.day == 30):
                            quaterdates.append(datetime.date(year, 9, 30))
                            if (enddate.month == 12 and enddate.day == 31):
                                quaterdates.append(datetime.date(year, 12, 31))
            else:
                quaterdates.append(datetime.date(year, 3, 31))
                quaterdates.append(datetime.date(year, 6, 30))
                quaterdates.append(datetime.date(year, 9, 30))
                quaterdates.append(datetime.date(year, 12, 31))
    quaterdates = sorted(quaterdates)
    return quaterdates


def getBackTestDates(startdate, enddate):
    quaterdates = []
    if startdate.year == enddate.year:
        if startdate.month <= 10:
            if enddate.month >= 11 or (enddate.month == 10 and enddate.day == 31):
                quaterdates.append(datetime.date(startdate.year, 10, 31))
        if startdate.month <= 7:
            if enddate.month >= 8 or (enddate.month == 7 and enddate.day == 31):
                quaterdates.append(datetime.date(startdate.year, 7, 31))
        if startdate.month <= 4:
            if enddate.month >= 5 or (enddate.month == 4 and enddate.day == 30):
                quaterdates.append(datetime.date(startdate.year, 4, 30))
        if startdate.month <= 1:
            if enddate.month >= 2 or (enddate.month == 1 and enddate.day == 31):
                quaterdates.append(datetime.date(startdate.year, 1, 31))
    else:
        for year in range(startdate.year, enddate.year + 1):
            if year == startdate.year:
                if startdate.month <= 10:
                    quaterdates.append(datetime.date(year, 10, 31))
                    if startdate.month <= 7:
                        quaterdates.append(datetime.date(year, 7, 31))
                        if startdate.month <= 4:
                            quaterdates.append(datetime.date(year, 4, 30))
                            if startdate.month <= 1:
                                quaterdates.append(datetime.date(year, 1, 31))
            elif year == enddate.year:
                if enddate.month >= 2 or (enddate.month == 1 and enddate.day == 31):
                    quaterdates.append(datetime.date(year, 1, 31))
                    if enddate.month >= 5 or (enddate.month == 4 and enddate.day == 30):
                        quaterdates.append(datetime.date(year, 4, 30))
                        if enddate.month >= 8 or (enddate.month == 7 and enddate.day == 31):
                            quaterdates.append(datetime.date(year, 7, 31))
                            if enddate.month >= 11 or (enddate.month == 10 and enddate.day == 31):
                                quaterdates.append(datetime.date(year, 10, 31))
            else:
                quaterdates.append(datetime.date(year, 1, 31))
                quaterdates.append(datetime.date(year, 4, 30))
                quaterdates.append(datetime.date(year, 7, 31))
                quaterdates.append(datetime.date(year, 10, 31))
    quaterdates = sorted(quaterdates)
    return quaterdates

# -----------------------------------------
# 触发调仓时收紧偏离度控制
# 回测缓存CC30模型的最终产品清单
# 设置缓冲池，每位PM仅保留一个产品
# -----------------------------------------
def fstrat_getCC30ModelFinalProductList_changeable_diviation(
    date,              # 考察日期 需为模型运行日期
    ann_date_temp,     #最近一期年报
    fund_universe_path,
    model_freq='Q',    # 模型调仓频率 决定了模型的运行日期
    shortlist_num=30,  # 模型最终输出的产品个数
    buffer_size=90,    # 缓冲池大小
    excess_drawdown_threshold=0.03,     # 周度观测时，超额收益回撤多少会触发临时调仓
    original_ind_deviation = 1,
    original_deviation=10,               # 原始偏离度限制
    temp_ind_deviation=0.01,  # 临时调仓偏离度限制
    temp_deviation=0.1,                 # 临时调仓偏离度限制
    index = '885001.WI',                # 观测指数
    index_delay = 0,                    # 指数公布延迟，股票指数为0，基金指数为1，延迟1天
    stock_barra=0,  # 股票barra偏离
    index_barra=0,   # 基准barra偏离
    equal_weight = True  #每期是否等权
):
    # ---------------------------------
    # 使用全维度收紧的优化算法
    # ---------------------------------
    # 构建优化问题
    def optimize_portfolio(df_crossSection, benchmark_industry_weights, deviation_limit, stock_holdings_size,
                           zz800_barra_temp, size_deviation_limit=None,
                           stock_holdings_sizenl=None, sizenl_deviation_limit=None):
        # 检查并清理数据
        df_crossSection = df_crossSection.fillna(0)  # 将 NaN 替换为 0
        benchmark_industry_weights = benchmark_industry_weights.fillna(0)  # 将 NaN 替换为 0

        # 获取行业列表
        industries = benchmark_industry_weights['industry'].tolist()
        n_funds = len(df_crossSection)
        n_industries = len(industries)

        # 补齐缺数据的列
        existing_columns = set(df_crossSection.columns)
        # 找出industries中存在但数据框中不包含的列
        missing_industries = [ind for ind in industries if ind not in existing_columns]
        # 为每个缺失的行业列添加全0列
        for industry in missing_industries:
            df_crossSection[industry] = 0.0

        # 定义问题
        prob = pulp.LpProblem("Portfolio_Optimization", pulp.LpMaximize)

        if equal_weight:
            # 定义二进制变量 z_i
            z = [pulp.LpVariable(f"z_{i}", cat='Binary') for i in range(n_funds)]
        else:
            z = [pulp.LpVariable(f"z_{i}", lowBound=0, upBound=0.05*30) for i in range(n_funds)]
            ## 限制权重在0.005以上的基金数量正好为30
            # 定义辅助二进制变量b_i
            b = [pulp.LpVariable(f"b_{i}", cat='Binary') for i in range(n_funds)]
            # 建立权重与二进制的逻辑关系
            M = 10000  # 足够大的常数（取权重上限值）
            for i in range(n_funds):
                # 当w_i >0.005时必须b_i=1
                prob += z[i] <= 0.005*30 + M * b[i]
                # 当w_i >=0.005时必须b_i=1（放大判断阈值避免浮点误差）
                prob += z[i] >= 0.005*30 * b[i] - 1e-8
            # 限制符合条件的基金数量
            prob += pulp.lpSum(b) == 30

        # 目标函数：最大化因子得分
        c = df_crossSection['score'].values
        prob += pulp.lpSum([(c[i] / 30) * z[i] for i in range(n_funds)])

        # 约束条件：权重之和为 1
        prob += pulp.lpSum([z[i] for i in range(n_funds)]) == 30

        # 约束条件：行业偏离不超过 deviation_limit
        for industry in industries:
            industry_weights = df_crossSection[industry].values
            benchmark_weight = \
                benchmark_industry_weights[benchmark_industry_weights['industry'] == industry]['weight'].values[0]

            # 上限约束
            prob += pulp.lpSum(
                [(industry_weights[i] / 30) * z[i] for i in range(n_funds)]) <= benchmark_weight + deviation_limit

            # 下限约束
            prob += pulp.lpSum(
                [(industry_weights[i] / 30) * z[i] for i in range(n_funds)]) >= benchmark_weight - deviation_limit

        # 添加市值偏离约束
        if size_deviation_limit is not None:
            # 计算每只基金的市值暴露
            fund_size_exposures = []
            for product_id in df_crossSection['product_id']:
                # 获取基金的股票持仓
                fund_stocks = stock_holdings_size[stock_holdings_size['product_id'] == product_id]
                # 计算基金的市值暴露
                size_exposure = fund_stocks['stk_value_to_allstk'] * fund_stocks['exposure']
                fund_size_exposures.append(size_exposure.sum())

            # 基准指数的市值暴露
            benchmark_size_exposure = zz800_barra_temp['size'].sum()

            # 市值偏离约束
            prob += pulp.lpSum([(fund_size_exposures[i] / 30) * z[i] for i in
                                range(n_funds)]) <= benchmark_size_exposure + size_deviation_limit
            prob += pulp.lpSum([(fund_size_exposures[i] / 30) * z[i] for i in
                                range(n_funds)]) >= benchmark_size_exposure - size_deviation_limit

        # 添加 sizenl 偏离约束
        if sizenl_deviation_limit is not None:
            # 计算每只基金的 sizenl 暴露
            fund_sizenl_exposures = []
            for product_id in df_crossSection['product_id']:
                # 获取基金的股票持仓
                fund_stocks = stock_holdings_sizenl[stock_holdings_sizenl['product_id'] == product_id]
                # 计算基金的 sizenl 暴露
                sizenl_exposure = fund_stocks['stk_value_to_allstk'] * fund_stocks['exposure']
                fund_sizenl_exposures.append(sizenl_exposure.sum())

            # 基准指数的 sizenl 暴露
            benchmark_sizenl_exposure = zz800_barra_temp['sizenl'].sum()

            # sizenl 偏离约束
            prob += pulp.lpSum([(fund_sizenl_exposures[i] / 30) * z[i] for i in
                                range(n_funds)]) <= benchmark_sizenl_exposure + sizenl_deviation_limit
            prob += pulp.lpSum([(fund_sizenl_exposures[i] / 30) * z[i] for i in
                                range(n_funds)]) >= benchmark_sizenl_exposure - sizenl_deviation_limit

        # 求解问题
        cbc_path = r"D:/anaconda21/envs/fof_qr/lib/site-packages/pulp/solverdir/cbc/win/i64/cbc.exe"
        solver = pulp.apis.COIN_CMD(path=cbc_path)  # 使用CBC求解器
        prob.solve(solver)

        # 提取结果
        solution = np.array([z[i].varValue for i in range(n_funds)])
        weights = solution / 30  # 转换为权重

        # 计算行业权重偏离值
        industry_deviations = {}
        for industry in industries:
            industry_weights = df_crossSection[industry].values
            portfolio_weight = np.sum(industry_weights * weights)  # 投资组合中该行业的权重
            benchmark_weight = \
                benchmark_industry_weights[benchmark_industry_weights['industry'] == industry]['weight'].values[0]
            deviation = portfolio_weight - benchmark_weight  # 行业权重偏离值
            industry_deviations[industry] = deviation

        # 计算市值偏离值
        if size_deviation_limit is not None:
            portfolio_size_exposure = np.sum(np.array(fund_size_exposures) * weights)  # 投资组合的市值暴露
            size_deviation = portfolio_size_exposure - benchmark_size_exposure  # 市值偏离值
        else:
            size_deviation = None

        # 计算因子打分平均值
        total_factor_score = np.sum(c * weights)

        return weights, industry_deviations, total_factor_score, size_deviation

    # 计算最近两次模型运行日期
    if model_freq == 'Q':
        adj_calendar = fstrat_getAdjustmentCalendar(freq=model_freq)
        adj_calendar1 = adj_calendar
    if model_freq == 'W':
        adj_calendar1 = fstrat_getAdjustmentCalendar(freq='Q')
        adj_calendar2 = fstrat_getAdjustmentCalendar(freq='W')
        adj_calendar = pd.concat([adj_calendar1, adj_calendar2], axis=0).drop_duplicates(subset=["model_date"])
        adj_calendar.dropna(inplace = True)
        adj_calendar.sort_values(by = 'model_date', inplace = True)
    # assert date in adj_calendar['model_date'].to_list(), "入参date需为模型运行日期"
    previous_model_date = adj_calendar[adj_calendar['model_date'] < date]['model_date'].iloc[-1]

    # -------------------
    # 读取上一期最终名单
    # -------------------
    previous_shortlist_res_path = fstrat_config.cc30_run_path+"上一期持仓.xlsx"
    assert os.path.exists(previous_shortlist_res_path), f"未找到{previous_shortlist_res_path}，请先缓存上一期最终名单"  # 需要取到上一期结果得到缓冲池产品
    previous_shortlist_res = pd.read_excel(previous_shortlist_res_path, index_col=0)[['product_id']].reset_index().rename(columns={'index': 'previous_index'})

    # -------------------------
    # 读取当期基金池 包含多行pm信息
    # -------------------------
    fund_universe = pd.read_excel(fund_universe_path)
    fund_universe['date'] = pd.to_datetime(fund_universe['date']).dt.date

    # -------------------
    # 读取当期的打分结果
    # -------------------
    start_index = fund_universe_path.rfind('_') + 1  # 最后一个_的下一个位置
    end_index = fund_universe_path.rfind('.')  # 扩展名前的点位置
    cate = fund_universe_path[start_index:end_index]

    current_fund_score_path = '债基-输出结果/'+"固收+因子打分_{0}_{1}.xlsx".format(date,cate)
    assert os.path.exists(current_fund_score_path), f"未找到{current_fund_score_path}，请先缓存当期打分结果"  # 需要取到当期的打分结果
    product_score = pd.read_excel(current_fund_score_path)

    # -------------------
    # 模型策略部分 因子权重
    # -------------------
    # # # 原版JW30
    # product_score['score'] = (0.143 * product_score['sharpe'] - 0.071 * product_score['mdd'] - 0.071 * product_score['jensen_beta'] + 0.143 * product_score['jensen_alpha']
    #  + 0.143 * product_score['TM_gamma'] - 0.143 * product_score['size'] + 0.143 * product_score['delta_survey_6m'] + 0.143 * product_score['employee_holding_ratio']) + 0.2850
    ## 新JW30——885001
    # product_score['score'] = (product_score['sharpe'] + 0.5 * (1 - product_score['mdd']) + 0.5 * (
    #             1 - product_score['jensen_beta']) + product_score['jensen_alpha']
    #                           + product_score['TM_gamma'] + (1 - product_score['size']) + product_score[
    #                               'delta_survey_6m'] + product_score['employee_holding_ratio']
    #                           + (1 - product_score['tracking_error_885001']) + (1 - product_score['vol_nl'])) / 9

    ##  新JW30——000906：
    product_score['score'] = (product_score['sharpe'] + 0.5 * (1 - product_score['mdd']) + 0.5 * (
                1 - product_score['jensen_beta']) + product_score['jensen_alpha']
                               + product_score['employee_holding_ratio']) / 4
    # -------------------
    # 生成最终名单
    # -------------------
    # 多pm的产品会保留多行, 此处是为了引入pm信息
    product_score_with_info = pd.merge(fund_universe, product_score, on='product_id', how='left').sort_values('score', ascending=False)
    # 缓冲池中属于上一期模型结果的产品进行保留处理
    buffered_product_ids = product_score_with_info['product_id'].unique().tolist()[:buffer_size]
    retained_product_ids = previous_shortlist_res[previous_shortlist_res['product_id'].isin(buffered_product_ids)]['product_id'].to_list()
    # 从上一期名单中保留下产品的信息，目的是获取pm信息进行下一步pm去重
    retained_product_score_with_info = product_score_with_info[product_score_with_info['product_id'].isin(retained_product_ids)]
    # 首先排除上一期保留下的基金以及这些基金经理管理的其他产品，对剩余基金仅保留每个pm得分最高的一只产品
    product_score_with_info_exclude_retained = product_score_with_info[~(product_score_with_info['product_id'].isin(retained_product_score_with_info['product_id'].unique().tolist()))
                                                             & ~(product_score_with_info['pm_name'].isin(retained_product_score_with_info['pm_name'].unique().tolist()))]
    product_score_with_info_exclude_retained = product_score_with_info_exclude_retained.groupby(['pm_name'], as_index=False).first().sort_values('score', ascending=False)
    product_score_with_info = pd.concat([retained_product_score_with_info, product_score_with_info_exclude_retained], axis=0)[['date', 'product_id', 'product_name', 'score']].drop_duplicates()

    #计算与上个交易日之间的交易日天数
    SSE_calendar = wind.wind_getSSECalendar()
    delta_days = (date - previous_model_date).days
    trading_days = 0
    # 遍历每个自然日
    for i in range(delta_days + 1):
        current_date = previous_model_date + datetime.timedelta(days=i)
        if current_date in SSE_calendar['date'].tolist():
            trading_days += 1

    ## 计算quarter_to_backtest映射
    startdate_temp = datetime.date(2009, 3, 1)
    enddate_temp = datetime.date(2028, 3, 1)
    BackTestDates2 = getBackTestDates(startdate_temp, enddate_temp)
    BackTestDates2 = wind.wind_getLastTradeDates(BackTestDates2)
    QuarterDates2 = getQuarterDates(startdate_temp, enddate_temp)
    quarter_to_backtest = pd.DataFrame({'quarter_date': QuarterDates2, 'backtest_date': BackTestDates2})
    def quarter_to_annual(quarter_date):
        if quarter_date.month == 3:
            return datetime.date(quarter_date.year-1, 12,31)
        if quarter_date.month == 9:
            return datetime.date(quarter_date.year, 6,30)
        return quarter_date
    quarter_to_backtest['ann_date'] = 0
    quarter_to_backtest['ann_date'] = quarter_to_backtest['quarter_date'].apply(quarter_to_annual)

    # # 计算date的前一年报日
    # temp_df = quarter_to_backtest.copy()
    # temp_df["backtest_date"] = pd.to_datetime(temp_df["backtest_date"], errors="coerce")
    # target_date = pd.to_datetime(date)
    # filtered = temp_df[temp_df["backtest_date"] <= target_date]
    # if not pd.api.types.is_datetime64_any_dtype(filtered["backtest_date"]):
    #     raise TypeError("backtest_date column is not datetime type after filtering")
    # closest_row = filtered.loc[filtered["backtest_date"].idxmax()]
    # ann_date_temp = closest_row['ann_date']

    ### 季度调仓
    # PM去重与权重分配
    product_score_with_info = product_score_with_info.sort_values('score', ascending=False)
    # 数据预处理，仅从前999里优化
    product_score_with_info = product_score_with_info.reset_index(drop = True)
    if len(product_score_with_info)> 999:
        product_score_with_info = product_score_with_info[:999]

    fundlist = product_score_with_info['product_id'].tolist()

    if index == '000906.SH':
        # 中证800行业权重获取
        index_df = wind.wind_getStockIndexComponentsWeight(
            'ZZ800',
            wind.wind_getLastTradeDates([ann_date_temp])[0],  # datetime.date instance
            wind.wind_getLastTradeDates([ann_date_temp])[0]
        )
        mapping = wind.wind_getIndustriesMap('SW', 1, date=ann_date_temp).drop(['date'], axis = 1)
        index_df = pd.merge(index_df, mapping, on = ['stock_id'])
        benchmark_industry_weights = index_df.groupby(['industry']).sum().reset_index()

        stock_holdings = wind.wind_getMFStockHoldings(fundlist, freq='H', Top10=False,
                                                      start_date=ann_date_temp,
                                                      end_date=ann_date_temp)
        stock_barra_temp = stock_barra[stock_barra['date'] <= date]
        max_date = stock_barra_temp["date"].max()
        stock_barra_temp = stock_barra[stock_barra['date'] == max_date]
        stock_barra_temp = stock_barra_temp[stock_barra_temp['factor'] == 'size']
        index_barra_temp = index_barra[index_barra['date'] <= date]
        max_date = index_barra_temp["date"].max()
        index_barra_temp = index_barra_temp[index_barra_temp['date'] == max_date]
        stock_holdings_size = pd.merge(stock_holdings, stock_barra_temp[['stock_id', 'exposure']], on='stock_id',
                                       how='left')
        stock_holdings_size['exposure'] = np.where(
            (stock_holdings_size['exposure'].isna()) & (stock_holdings_size['stock_market'] == 'A'), -3,
            np.where(stock_holdings_size['exposure'].isna(), 0, stock_holdings_size['exposure']))
        stock_barra_temp = stock_barra[stock_barra['date'] <= date]
        max_date = stock_barra_temp["date"].max()
        stock_barra_temp = stock_barra[stock_barra['date'] == max_date]
        stock_barra_temp = stock_barra_temp[stock_barra_temp['factor'] == 'sizenl']
        stock_holdings_sizenl = pd.merge(stock_holdings, stock_barra_temp[['stock_id', 'exposure']], on='stock_id',
                                         how='left')
        stock_holdings_sizenl['exposure'] = np.where(
            (stock_holdings_sizenl['exposure'].isna()) & (stock_holdings_sizenl['stock_market'] == 'A'), -3,
            np.where(stock_holdings_sizenl['exposure'].isna(), 0, stock_holdings_sizenl['exposure']))

    # 根据基准类型生成行业权重
    elif index == '885001.WI':
        # 通过 WDS 获取基准指数的行业权重
        dbconn = wind.wind_connectWindDB()
        sql_equity_fund = "select F_INFO_WINDCODE, S_INFO_SECTOR " \
                          "from ChinaMutualFundSector " \
                          "where S_INFO_SECTORENTRYDT <= {0} AND (S_INFO_SECTOREXITDT >= {1} OR S_INFO_SECTOREXITDT IS NULL) "
        date_temp = ann_date_temp.strftime("%Y%m%d")
        equity_fund_df = pd.read_sql_query(sql_equity_fund.format(date_temp, date_temp), dbconn)
        equity_fund_df = equity_fund_df[
            equity_fund_df['s_info_sector'].str[:10].isin(['2001010101', '2001010201'])]
        equity_fund_list = equity_fund_df['f_info_windcode'].unique().tolist()
        date_temp = ann_date_temp

        # 通过 WDS 获取基准指数的行业权重
        if len(equity_fund_list) > 502:
            def process_chunks(equity_fund_list, chunk_size=500):
                All_MF_stockholding = []
                for i in range(0, len(equity_fund_list), chunk_size):
                    chunk = equity_fund_list[i:i + chunk_size]
                    result = wind.wind_getMFStockHoldings(product_id=chunk, freq='H', Top10=False,
                                                          start_date=date_temp,
                                                          end_date=date_temp)
                    All_MF_stockholding.append(result)
                    # 释放内存
                    del result
                return pd.concat(All_MF_stockholding, ignore_index=True)

            # 调用函数
            All_MF_stockholding = process_chunks(equity_fund_list)
        else:
            All_MF_stockholding = wind.wind_getMFStockHoldings(product_id=equity_fund_list, freq='H', Top10=False,
                                                               start_date=date_temp, end_date=date_temp)
        index_holding = All_MF_stockholding[['stock_id', 'stk_value_to_nav']]
        index_holding = index_holding.groupby('stock_id', as_index=False)['stk_value_to_nav'].sum()
        index_holding.rename(columns={'stk_value_to_nav': 'weight'}, inplace=True)
        index_holding['weight'] = index_holding['weight'] / index_holding['weight'].sum()
        mapping = wind.wind_getIndustriesMap('SW', 1, date=ann_date_temp).drop(['date'], axis=1)
        index_holding = pd.merge(index_holding, mapping, on=['stock_id'])
        benchmark_industry_weights = index_holding.groupby(['industry']).sum().reset_index()

        stock_holdings = wind.wind_getMFStockHoldings(fundlist, freq='H', Top10=False,
                                                      start_date=ann_date_temp,
                                                      end_date=ann_date_temp)
        stock_barra_temp = stock_barra[stock_barra['date'] <= date]
        max_date = stock_barra_temp["date"].max()
        stock_barra_temp = stock_barra[stock_barra['date'] == max_date]
        stock_barra_temp = stock_barra_temp[stock_barra_temp['factor'] == 'size']
        size_exposure = stock_barra_temp[['stock_id', 'exposure']]
        merged_data = pd.merge(index_holding, size_exposure, on='stock_id', how='inner')
        merged_data['weighted_exposure'] = merged_data['weight'] * merged_data['exposure']
        index_size_exposure = merged_data['weighted_exposure'].sum()
        stock_holdings_size = pd.merge(stock_holdings, stock_barra_temp[['stock_id', 'exposure']], on='stock_id',
                                       how='left')
        stock_holdings_size['exposure'] = np.where(
            (stock_holdings_size['exposure'].isna()) & (stock_holdings_size['stock_market'] == 'A'), -3,
            np.where(stock_holdings_size['exposure'].isna(), 0, stock_holdings_size['exposure']))
        stock_barra_temp = stock_barra[stock_barra['date'] <= date]
        max_date = stock_barra_temp["date"].max()
        stock_barra_temp = stock_barra[stock_barra['date'] == max_date]
        stock_barra_temp = stock_barra_temp[stock_barra_temp['factor'] == 'sizenl']
        sizenl_exposure = stock_barra_temp[['stock_id', 'exposure']]
        merged_data = pd.merge(index_holding, sizenl_exposure, on='stock_id', how='inner')
        merged_data['weighted_exposure'] = merged_data['weight'] * merged_data['exposure']
        index_sizenl_exposure = merged_data['weighted_exposure'].sum()
        stock_holdings_sizenl = pd.merge(stock_holdings, stock_barra_temp[['stock_id', 'exposure']], on='stock_id',
                                         how='left')
        stock_holdings_sizenl['exposure'] = np.where(
            (stock_holdings_sizenl['exposure'].isna()) & (stock_holdings_sizenl['stock_market'] == 'A'), -3,
            np.where(stock_holdings_sizenl['exposure'].isna(), 0, stock_holdings_sizenl['exposure']))
        index_barra_temp = pd.DataFrame({
            'size': [index_size_exposure],  # 计算得到的 Barra Size 暴露
            'sizenl': [index_sizenl_exposure],  #
        })

    # 通过 WDS 获取基金行业信息
    df_industry = MFanls.anlsMF_getMFIndustryDistribution(ann_date_temp,ann_date_temp,
        fundlist,  # product_id基金代码，应为list格式（因数据库存储问题，优先使用场内代码）
        'SW',  # 分类标准，输入格式:str，'SW' or 'CITICS'
        1,  # 分类级别，输入格式:int
        hidden_holdings=False,  # 是否包括上市公司公告里面的隐藏持仓
        freq='Q',  # freq为频率，'Q'为季报，'H'为半年和年报
        Top10=False,  # Top10为是否仅取季报前十大持仓
        IndustrytoStkValue=True  # False:行业占基金净值比；True:行业占股票市值比
    )
    product_score_with_info = pd.merge(product_score_with_info, df_industry.drop('date', axis=1), on='product_id', how='left')
    # 输出因子打分结果
    product_score_with_info_output = pd.merge(product_score_with_info, product_score, on = 'product_id', how = 'left')
    product_score_with_info_output.to_excel('债基-输出结果/'+"固收+基金打分结果_{0}_{1}.xlsx".format(date,cate))
    #
    # # 优化组合
    # optimized_results = optimize_portfolio(
    #     product_score_with_info,
    #     benchmark_industry_weights,
    #     original_ind_deviation,
    #     stock_holdings_size,
    #     index_barra_temp,
    #     original_deviation,
    #     stock_holdings_sizenl,
    #     original_deviation
    # )
    #
    # optimized_weights = optimized_results[0]
    # optimized_weights = np.where(optimized_weights<0.005-1e-8, 0, optimized_weights) # 剔除小于0.5%的仓位
    # optimized_weights = optimized_weights / optimized_weights.sum()  # 如果限制了单策略规模，在数据比较少的情况下，可能仓位不到100%，扩到100%
    # product_score_with_info['weight'] = optimized_weights
    #
    # # 提取行业偏离和市值偏离
    # industry_deviations = optimized_results[1]
    # size_deviation = optimized_results[3]
    #
    # # 将市值偏离添加到结果中
    # df_size_deviation = pd.DataFrame({'date': [date], 'size_deviation': [size_deviation]})
    #
    # # 将行业偏离和市值偏离合并
    # df_deviations = pd.DataFrame.from_dict(industry_deviations, orient='index', columns=['权重偏离值']).reset_index()
    # df_deviations['date'] = date
    # df_deviations = pd.merge(df_deviations, df_size_deviation, on='date', how='left')
    #
    # # 选择前30只基金
    # fund_result = product_score_with_info.nlargest(30, 'weight')
    #
    # # 更新缓存
    # product_score = product_score.sort_values('score', ascending= False).reset_index(drop = True).reset_index().rename(columns = {'index':'rank'})
    # product_score = product_score.drop(columns = 'score')
    # shortlist_res = pd.merge(fund_result, product_score,
    #                          on='product_id', how='left')
    # shortlist_res.rename(columns = {'mdd':'mdd_反向', 'size':'size_反向', 'tracking_error_885001':'tracking_error_885001_反向',
    #                                 'tracking_error_000906':'tracking_error_000906_反向', 'vol_nl':'vol_nl_反向'})
    # shortlist_res.to_excel('投顾-输出结果/'+"基金选择_{}.xlsx".format(date))
    return product_score_with_info_output


#############################################################################################
#以上为xjw改动部分
#############################################################################################

# ----------------------------------
# 回测模块 基于缓存结果回测策略收益序列
# ----------------------------------
def fstrat_getCC30ModelBackTestReturnSeries(
    start_date,     # 起始日期
    end_date,       # 截止日期
    model_freq='Q', # 模型频率
    path = fstrat_config.cc30_shortlist_res_path,
    fund_list = None #如果输入df，则只回测此组合。输入product_id、weight
):
    if fund_list is not None:
        # 数据校验
        if set(['product_id', 'weight']).issubset(fund_list.columns) == False:
            raise ValueError("持仓数据必须包含product_id和weight两列")

        # 权重预处理
        fund_list = fund_list.copy()
        fund_list['weight'] = fund_list['weight'] / fund_list['weight'].sum()  # 归一化处理

        # 获取全量净值数据
        product_ids = fund_list['product_id'].unique().tolist()
        nav_data = wind.wind_getMFNav(
            start_date - datetime.timedelta(days=7),  # 前向多取7天用于填充
            end_date,
            product_id=product_ids
        )

        # 净值数据预处理
        trading_calendar = wind.wind_getSSECalendar()
        nav_data = nav_data[nav_data['date'].isin(trading_calendar['date'])]
        nav_pivot = nav_data.pivot(index='date', columns='product_id', values='nav_adjusted')
        nav_pivot = nav_pivot.ffill().bfill()  # 双向填充

        # 计算组合净值
        valid_dates = nav_pivot.index[(nav_pivot.index >= start_date) & (nav_pivot.index <= end_date)]
        normalized_nav = nav_pivot.loc[valid_dates] / nav_pivot.loc[valid_dates[0]]  # 归一化
        try:
            portfolio_nav = normalized_nav.dot(fund_list.set_index('product_id')['weight'])
        except:
            len(normalized_nav)
            fund_list = fund_list[fund_list['product_id'].isin(normalized_nav.columns.to_list())]
            portfolio_nav = normalized_nav.dot(fund_list.set_index('product_id')['weight'])
        return portfolio_nav.sort_index().ffill().dropna()

    if model_freq == 'Q':  # 调仓频率
        trading_calendar = wind.wind_getSSECalendar()  # 交易日历，用于回测时过滤非交易日净值数据
        # 初始化前一个模型日期的结果为空，保证首次运行时不参考上一期模型结果(即不考虑缓冲池产品的保留，第一期结果仅根据打分得到)
        adj_calendar = fstrat_getAdjustmentCalendar(freq=model_freq)
        adj_calendar['next_effective_date'] = adj_calendar['effective_date'].shift(-1)
    elif model_freq == 'W':
        trading_calendar = wind.wind_getSSECalendar()  # 交易日历，用于回测时过滤非交易日净值数据
        # 初始化前一个模型日期的结果为空，保证首次运行时不参考上一期模型结果(即不考虑缓冲池产品的保留，第一期结果仅根据打分得到)
        adj_calendar1 = fstrat_getAdjustmentCalendar(freq='Q')
        adj_calendar2 = fstrat_getAdjustmentCalendar(freq='W')
        adj_calendar = pd.concat([adj_calendar1, adj_calendar2], axis=0).drop_duplicates(subset=["model_date"])
        adj_calendar.dropna(inplace = True)
        adj_calendar.sort_values(by = 'model_date', inplace = True)
        adj_calendar['next_effective_date'] = adj_calendar['effective_date'].shift(-1)
    adj_calendar = adj_calendar[(adj_calendar['model_date'] >= start_date) & (adj_calendar['model_date'] <= end_date)]
    # back-test model
    port_ret_series_list = []
    pd.DataFrame(columns=['product_id']).to_excel(path.format("回测用_上一期持仓"))
    for index, row in adj_calendar.iterrows():
        print(row['model_date'])
        try:
            single_period_shortlist_res = pd.read_excel(path.format(row['model_date']), index_col=0)
            single_period_shortlist_res.to_excel(path.format("回测用_上一期持仓"))
        except:
            single_period_shortlist_res = pd.read_excel(path.format('回测用_上一期持仓'), index_col=0)
        single_period_shortlist_res['effective_date'] = row['effective_date']
        single_period_shortlist_res_pivot = pd.pivot_table(single_period_shortlist_res, values='weight', index='effective_date', columns='product_id')
        # 向前多取一些，保证取到上一交易日的净值
        single_period_nav = wind.wind_getMFNav(row['effective_date'] - datetime.timedelta(days=14), min(end_date, row['next_effective_date'] - datetime.timedelta(days=1)),
                                               product_id=single_period_shortlist_res['product_id'].to_list()).sort_values(['product_id', 'date'])
        single_period_nav = single_period_nav[single_period_nav['date'].isin(trading_calendar['date'].to_list())]  # 过滤非交易日期的净值 通常为季度末
        single_period_nav['nav_adjusted'] = single_period_nav.groupby(['product_id'])['nav_adjusted'].apply(lambda x: x.fillna(method='ffill'))
        single_period_nav['ret'] = single_period_nav.groupby(['product_id'])['nav_adjusted'].apply(lambda x: x.diff() / x.shift(1))
        single_period_nav = single_period_nav[(single_period_nav['date'] >= row['effective_date']) & (single_period_nav['date'] < row['next_effective_date'])]  # 限制死区间
        single_period_ret_pivot = pd.pivot_table(single_period_nav, values='ret', index='date', columns='product_id')
        # if row['model_date'] ==datetime.date(2022,11,25):
        #     print(1)
        if row['model_date'] ==datetime.date(2025,2,28):
            break
        single_period_port_ret_series = bt.backtest_calPortfolioReturnSeries(single_period_ret_pivot, single_period_shortlist_res_pivot)
        port_ret_series_list.append(single_period_port_ret_series)
    port_ret_series = pd.concat(port_ret_series_list, axis=0)
    port_ret_series.to_frame().to_excel(f'./收益回测序列{port_ret_series.index.min()}_{port_ret_series.index.max()}.xlsx')


if __name__ == '__main__':
    # 模型回溯区间
    model_start_date = datetime.date(2024, 12, 31)
    # model_start_date = datetime.date(2024,7,31)
    model_end_date = datetime.date(2025, 4, 30)
    model_freq = 'Q'  # 调仓频率 暂仅支持Q\W

    ### 如果希望在指定日期运算，请运行以下代码
    model_date = datetime.date(2025,1,1)
    ann_date = datetime.date(2024,6,30)
    ###
    path = '债基-输出结果/固收+基金池_2025-01-01.xlsx'
    path1 = path[:-5]+"_L.xlsx"
    path2 = path[:-5]+"_M.xlsx"
    path3 = path[:-5]+"_HandF.xlsx"
    # 拆分固收+类别
    bond_plus_df = pd.read_excel(path)
    bond_plus_df[bond_plus_df['cate'] == 'L'].to_excel(path1)
    bond_plus_df[bond_plus_df['cate'] == 'M'].to_excel(path2)
    bond_plus_df[bond_plus_df['cate'].isin(['H', 'F'])].to_excel(path3)

    paths = [path1,path2,path3]
    for path in paths:
        # # cal & cache factors
        print(model_date)
        fstrat_getCC30ProductScore(date=model_date, path = path, model_freq=model_freq, benchmark='885007.WI', rf=0.03)

        # shortlist & cache final 30-products res from cached files

        stock_barra = pd.read_csv('C:/Users/041685/Desktop/多因子code2/CC30优化_baseline/CC30优化/model_res/stock_barra.csv')
        index_barra = pd.read_excel('C:/Users/041685/Desktop/多因子code2/CC30优化_baseline/CC30优化/model_res/zz800_barra.xlsx')

        # 步骤1：将字符串转换为pandas的datetime类型
        stock_barra['date'] = pd.to_datetime(stock_barra['date'])
        # 步骤2：提取datetime.date对象（保留日期部分）
        stock_barra['date'] = stock_barra['date'].dt.date
        # 步骤1：将字符串转换为pandas的datetime类型
        index_barra['date'] = pd.to_datetime(index_barra['date'])
        # 步骤2：提取datetime.date对象（保留日期部分）
        index_barra['date'] = index_barra['date'].dt.date

        # 基金选择
        print(model_date)
        fstrat_getCC30ModelFinalProductList_changeable_diviation(model_date, ann_date, path,model_freq=model_freq, shortlist_num=30, buffer_size=0,excess_drawdown_threshold=100,
                                                                     original_ind_deviation=100, original_deviation=100, temp_ind_deviation=100,temp_deviation=100, index='885008.WI', index_delay=1,
                                                                     stock_barra=stock_barra, index_barra=index_barra,  equal_weight = True )
        # model_start_date = datetime.date(2022,10,31)

        # back-test model from cached files
        # fstrat_getCC30ModelBackTestReturnSeries(start_date=model_start_date, end_date=model_end_date,
        #                                         path = fstrat_config.cc30_shortlist_res_path_backtest1, model_freq=model_freq)