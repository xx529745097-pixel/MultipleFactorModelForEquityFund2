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
    fund_universe = mf_info[['date', 'product_id', 'product_name', 'aum', 'pm_name']].sort_values('product_id')
    return fund_universe

# -----------------------------------------
# 因子计算模块 获取模型因子得分并缓存
# -----------------------------------------
def fstrat_getCC30ProductScore(
    date,                   # 考察日期
    model_freq='Q',             # 模型调仓频率 决定了模型的运行日期
    benchmark='000906.SH',  # 指标计算基准
    rf=0.03,                # 无风险利率
):
    # 计算最近两次模型运行日期
    adj_calendar = fstrat_getAdjustmentCalendar(freq=model_freq)
    assert date in adj_calendar['model_date'].to_list(), "入参date需为模型运行日期"
    anls_start_date = date - datetime.timedelta(days=365)
    # 获取基金池和当期模型打分并缓存
    fund_universe = fstrat_getCC30EquityMFPool(date, include_pm_info=True)
    # 缓存基金池 数据带PM不去重
    fund_universe.to_excel(fstrat_config.cc30_fund_universe_path.format(date), index=None)
    # 因子计算
    product_ids = fund_universe['product_id'].unique().tolist()
    product_indicator_info = MFanls.anlsMF_SelectedRatingIndicator(product_ids, anls_start_date, date, 'D', benchmark, rf)  # 因子底层使用日频收益计算
    indicator_score = product_indicator_info.set_index('product_id').rank(pct=True, ascending=True).reset_index()   # 将因子值转化为排名，越大表现越好。
    weekly_perf_rank_stability = MFanls.anlsMF_RankStability(product_ids, anls_start_date, date)   # 周度收益率的排名稳定性
    product_score = pd.merge(indicator_score, weekly_perf_rank_stability, on='product_id', how='left')
    # 缓存因子打分
    product_score.to_excel(fstrat_config.cc30_fund_score_path.format(date), index=None)
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
    adj_calendar = fstrat_getAdjustmentCalendar(freq=model_freq)
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

# ----------------------------------
# 回测模块 基于缓存结果回测策略收益序列
# ----------------------------------
def fstrat_getCC30ModelBackTestReturnSeries(
    start_date,     # 起始日期
    end_date,       # 截止日期
    model_freq='Q'  # 模型频率
):
    trading_calendar = wind.wind_getSSECalendar()
    adj_calendar = fstrat_getAdjustmentCalendar(freq=model_freq)
    adj_calendar['next_effective_date'] = adj_calendar['effective_date'].shift(-1)
    adj_calendar = adj_calendar[(adj_calendar['model_date'] >= start_date) & (adj_calendar['model_date'] <= end_date)]
    # back-test model
    port_ret_series_list = []
    for index, row in adj_calendar.iterrows():
        print(row['model_date'])
        single_period_shortlist_res = pd.read_excel(fstrat_config.cc30_shortlist_res_path.format(row['model_date']), index_col=0)
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
        single_period_port_ret_series = bt.backtest_calPortfolioReturnSeries(single_period_ret_pivot, single_period_shortlist_res_pivot)
        port_ret_series_list.append(single_period_port_ret_series)
    port_ret_series = pd.concat(port_ret_series_list, axis=0)
    port_ret_series.to_frame().to_excel(f'./收益回测序列{port_ret_series.index.min()}_{port_ret_series.index.max()}.xlsx')


if __name__ == '__main__':
    # 模型回溯区间
    model_start_date = datetime.date(2014, 1, 1)
    model_end_date = datetime.date(2025, 2, 28)
    model_freq = 'Q'  # 调仓频率 暂仅支持季度调仓Q
    trading_calendar = wind.wind_getSSECalendar()  # 交易日历，用于回测时过滤非交易日净值数据
    # 初始化前一个模型日期的结果为空，保证首次运行时不参考上一期模型结果(即不考虑缓冲池产品的保留，第一期结果仅根据打分得到)
    adj_calendar = fstrat_getAdjustmentCalendar(freq=model_freq)
    adj_calendar['next_effective_date'] = adj_calendar['effective_date'].shift(-1)
    model_init_date = adj_calendar[adj_calendar['model_date'] < model_start_date]['model_date'].iloc[-1]
    if not os.path.exists(fstrat_config.cc30_shortlist_res_path.format(model_init_date)):
        pd.DataFrame(columns=['product_id']).to_excel(fstrat_config.cc30_shortlist_res_path.format(model_init_date))
    adj_calendar = adj_calendar[(adj_calendar['model_date'] >= model_start_date) & (adj_calendar['model_date'] <= model_end_date)]

    # # cal & cache factors
    # for model_date in adj_calendar['model_date'].to_list():
    #     print(model_date)
    #     fstrat_getCC30ProductScore(date=model_date, model_freq=model_freq, benchmark='000906.SH', rf=0.03)

    # shortlist & cache final 30-products res from cached files
    for model_date in adj_calendar['model_date'].to_list():
        print(model_date)
        fstrat_getCC30ModelFinalProductList(model_date, model_freq=model_freq, shortlist_num=30, buffer_size=90)

    # back-test model from cached files
    fstrat_getCC30ModelBackTestReturnSeries(start_date=model_start_date, end_date=model_end_date, model_freq=model_freq)