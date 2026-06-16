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

from 计算885001行业比例 import dbconn

warnings.filterwarnings('ignore')
import pulp

cc30_run_path = '原版智选30/'


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
    fund_universe = fstrat_getCC30EquityMFPool(date,company_id=True)
    # 剔除掉不在备选库的基金公司的产品
    # fundCompanyPool = pd.read_excel(cc30_run_path+"基金公司库.xlsx")
    # fundCompanyPool = fundCompanyPool[fundCompanyPool['所属库'] == '基金公司备选库']
    # fundCompanyPool2 = fundCompanyPool['基金公司代码'].to_list()
    # # sql_1 = "select COMP_NAME, COMP_SNAME, COMP_ID " \
    # #         "from CFundIntroduction "
    # # dbconn = wind.wind_connectWindDB()
    # # fundcompanylist = pd.read_sql_query(sql_1, dbconn)
    # fund_universe = fund_universe[fund_universe['company_id'].isin(fundCompanyPool2)]

    # 缓存基金池 数据带PM不去重
    fund_universe.to_excel(cc30_run_path+"基金池_{}.xlsx".format(date), index=None)
    # 因子计算
    product_ids = fund_universe['product_id'].unique().tolist()
    product_indicator_info = MFanls.anlsMF_SelectedRatingIndicator(product_ids, anls_start_date, date, 'D', benchmark, rf)  # 因子底层使用日频收益计算
    indicator_score = product_indicator_info.set_index('product_id').rank(pct=True, ascending=True).reset_index()   # 将因子值转化为排名，越大表现越好。
    weekly_perf_rank_stability = MFanls.anlsMF_RankStability(product_ids, anls_start_date, date)   # 周度收益率的排名稳定性
    product_score = pd.merge(indicator_score, weekly_perf_rank_stability, on='product_id', how='left')
    # 缓存因子打分
    product_score.to_excel(cc30_run_path+"因子打分_{}.xlsx".format(date), index=None)
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
    previous_shortlist_res_path = "原版智选30/上一期持仓.xlsx"
    previous_shortlist_res = pd.read_excel(previous_shortlist_res_path, index_col=0)[['product_id']].reset_index().rename(columns={'index': 'previous_index'})

    # -------------------------
    # 读取当期基金池 包含多行pm信息
    # -------------------------
    fund_universe_path = "原版智选30/基金池_{}.xlsx".format(date)
    assert os.path.exists(fund_universe_path), f"未找到{fund_universe_path}，请先缓存当期基金池结果"  # 需要取到当期的打分结果
    fund_universe = pd.read_excel(fund_universe_path)
    fund_universe['date'] = pd.to_datetime(fund_universe['date']).dt.date

    # -------------------
    # 读取当期的打分结果
    # -------------------
    current_fund_score_path = "原版智选30/因子打分_{}.xlsx".format(date)
    assert os.path.exists(current_fund_score_path), f"未找到{current_fund_score_path}，请先缓存当期打分结果"  # 需要取到当期的打分结果
    product_score = pd.read_excel(current_fund_score_path)

    # -------------------
    # 模型策略部分 因子权重
    # -------------------
    # JW30
    # product_score['score'] = (0.143 * product_score['sharpe'] - 0.071 * product_score['mdd'] - 0.071 * product_score['jensen_beta'] + 0.143 * product_score['jensen_alpha']
    #  + 0.143 * product_score['TM_gamma'] - 0.143 * product_score['size'] + 0.143 * product_score['delta_survey_6m'] + 0.143 * product_score['employee_holding_ratio']) + 0.2850
    # # CC30
    product_score['score'] = 0.2*product_score['jensen_beta'] + 0.4*product_score['sharpe'] + 0.1*product_score['TM_gamma'] + 0.1*product_score['TM_alpha'] + 0.2*product_score['stability']
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


# --------------------------------------------
# 债基-筛选CC30公募基金池
# 1. 股票型，偏股混合型，高仓位灵活配置型(>=50%)开放式基金，无最短持有期限
# 2. 至少一位现任基金经理任职时间大于1年
# 3. 基金最新规模大于2亿
# 4. 近四个季度权益平均仓位大于50%
# 5. 开放申购赎回
# --------------------------------------------
def fstrat_getCC30BondMFPool(
    date,    # 考察日期
    company_id = False  #是否保留公司id
):
    mf_info = wind.wind_getHistoricalProductList(as_of_date=date, include_pm_info=True)  # 获取历史初始基金，即AC份额仅考虑A份额
    # 筛选正在生效的sector type标签
    mf_info = mf_info[(mf_info['sector_start_date'] <= date) & ((mf_info['sector_end_date'] >= date) | mf_info['sector_end_date'].isna())]
    mf_info = mf_info[mf_info['type'].isin(['中长期纯债型基金', '短期纯债型基金', '被动指数型债券基金'])]
    mf_info = mf_info[(mf_info['fund_open_type'] == '契约型开放式') & (mf_info['min_holding_month'].isna())]
    mf_info = mf_info[~(mf_info['product_full_name'].str.contains('定开') | mf_info['product_full_name'].str.contains('持有') | mf_info['product_full_name'].str.contains('定期'))]
    # 筛选正在任职的PM，保留任职时间大于1Y
    mf_info = mf_info[(mf_info['pm_start_date'] <= date) & ((mf_info['pm_end_date'] >= date) | mf_info['pm_end_date'].isna())]
    mf_info['pm_duration_days'] = (mf_info['pm_end_date'].apply(lambda x: min(date, x) if not pd.isna(x) else date) - mf_info['pm_start_date']).apply(lambda x: x.days)
    mf_info = mf_info[mf_info['pm_duration_days'] >= 365]
    # 基金最新规模大于10亿
    mf_latest_aum = wind.wind_getMFLatestAUM(date - datetime.timedelta(days=365), date)
    mf_info = pd.merge(mf_info, mf_latest_aum[['product_id', 'aum']], on=['product_id'], how='left')
    mf_info = mf_info[mf_info['aum'] >= 10e8]
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
# -----------------------------------------
# 债基因子计算模块 获取模型因子得分并缓存
# -----------------------------------------
def fstrat_getCC30ProductScore_bond(
    date,                   # 考察日期
    model_freq='Q',             # 模型调仓频率 决定了模型的运行日期
    benchmark='000906.SH',  # 指标计算基准
    rf=0.03,                # 无风险利率
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
    fund_universe = fstrat_getCC30BondMFPool(date,company_id=True)
    # 剔除掉不在备选库的基金公司的产品
    # fundCompanyPool = pd.read_excel(cc30_run_path+"基金公司库.xlsx")
    # fundCompanyPool = fundCompanyPool[fundCompanyPool['所属库'] == '基金公司备选库']
    # fundCompanyPool2 = fundCompanyPool['基金公司代码'].to_list()
    # # sql_1 = "select COMP_NAME, COMP_SNAME, COMP_ID " \
    # #         "from CFundIntroduction "
    # # dbconn = wind.wind_connectWindDB()
    # # fundcompanylist = pd.read_sql_query(sql_1, dbconn)
    # fund_universe = fund_universe[fund_universe['company_id'].isin(fundCompanyPool2)]

    # 缓存基金池 数据带PM不去重
    fund_universe.to_excel(cc30_run_path+"债基基金池_{}.xlsx".format(date), index=None)
    # 因子计算
    product_ids = fund_universe['product_id'].unique().tolist()
    product_indicator_info = MFanls.anlsMF_SelectedRatingIndicator(product_ids, anls_start_date, date, 'D', benchmark, rf)  # 因子底层使用日频收益计算
    indicator_score = product_indicator_info.set_index('product_id').rank(pct=True, ascending=True).reset_index()   # 将因子值转化为排名，越大表现越好。
    weekly_perf_rank_stability = MFanls.anlsMF_RankStability(product_ids, anls_start_date, date)   # 周度收益率的排名稳定性
    product_score = pd.merge(indicator_score, weekly_perf_rank_stability, on='product_id', how='left')
    # 缓存因子打分
    product_score.to_excel(cc30_run_path+"债基因子打分_{}.xlsx".format(date), index=None)
    return product_score

# -----------------------------------------
# 回测缓存CC30模型的最终产品清单
# 设置缓冲池，每位PM仅保留一个产品   债基
# -----------------------------------------
def fstrat_getCC30ModelFinalProductList_bond(
        date,  # 考察日期 需为模型运行日期
        ann_date_temp,  # 最近一期年报
        model_freq='Q',  # 模型调仓频率 决定了模型的运行日期
        shortlist_num=30,  # 模型最终输出的产品个数
        buffer_size=90,  # 缓冲池大小
        excess_drawdown_threshold=0.03,
        original_ind_deviation=1,
        original_deviation=10,
        temp_ind_deviation=0.01,
        temp_deviation=0.1,
        index='885001.WI',
        index_delay=0,
        stock_barra=0,
        index_barra=0,
        equal_weight=True
):
    # 1. 计算最近两次模型运行日期
    if model_freq == 'Q':
        adj_calendar = fstrat_getAdjustmentCalendar(freq=model_freq)
        adj_calendar1 = adj_calendar
    if model_freq == 'W':
        adj_calendar1 = fstrat_getAdjustmentCalendar(freq='Q')
        adj_calendar2 = fstrat_getAdjustmentCalendar(freq='W')
        adj_calendar = pd.concat([adj_calendar1, adj_calendar2], axis=0).drop_duplicates(subset=["model_date"])
        adj_calendar.dropna(inplace=True)
        adj_calendar.sort_values(by='model_date', inplace=True)

    previous_model_date = adj_calendar[adj_calendar['model_date'] < date]['model_date'].iloc[-1]

    # 2. 读取上一期最终名单
    previous_shortlist_res_path = cc30_run_path + "债基上一期持仓.xlsx"
    assert os.path.exists(previous_shortlist_res_path), f"未找到{previous_shortlist_res_path}，请先缓存上一期最终名单"
    previous_shortlist_res = pd.read_excel(previous_shortlist_res_path, index_col=0)[
        ['product_id']].reset_index().rename(columns={'index': 'previous_index'})

    # 3. 读取当期基金池 包含多行pm信息
    fund_universe_path = cc30_run_path + "债基基金池_{}.xlsx".format(date)
    assert os.path.exists(fund_universe_path), f"未找到{fund_universe_path}，请先缓存当期基金池结果"
    fund_universe = pd.read_excel(fund_universe_path)
    fund_universe['date'] = pd.to_datetime(fund_universe['date']).dt.date

    # 4. 读取当期的打分结果
    current_fund_score_path = cc30_run_path + "债基因子打分_{}.xlsx".format(date)
    assert os.path.exists(current_fund_score_path), f"未找到{current_fund_score_path}，请先缓存当期打分结果"
    product_score = pd.read_excel(current_fund_score_path)

    # 5. 模型策略部分 因子权重
    product_score['score'] = (0.3 * product_score['calmar'] + 0.3 * product_score['sharpe'] +
                              0.4 * product_score['stability'])

    # 将基本信息与打分合并，保留原始未去重文件以便排查
    product_score_with_info = pd.merge(fund_universe, product_score, on='product_id', how='left').sort_values('score',
                                                                                                              ascending=False)
    # product_score_with_info.to_excel("模型输出结果/智选30-基金打分结果(不去重版)_{}.xlsx".format(date))

    # ==========================================
    # 【功能 2】：对基金去重，基金经理显示为所有基金经理
    # ==========================================
    # 通过 groupby 将相同产品的多位基金经理用逗号连接起来，保证每只产品只有唯一一行
    df_agg = product_score_with_info.groupby('product_id', sort=False).agg({
        'date': 'first',
        'product_name': 'first',
        'score': 'first',
        'pm_name': lambda x: ', '.join(x.dropna().unique())
    }).reset_index()
    # 再次严格按照打分倒序排列
    df_agg = df_agg.sort_values('score', ascending=False).reset_index(drop=True)

    # -------------------
    # 生成最终名单 (缓冲池 + 同基金经理去重 + 等权)
    # -------------------
    # 提取排名前 buffer_size 的 product_id 列表
    buffered_product_ids = df_agg['product_id'].tolist()[:buffer_size]

    # 检查上期持仓中有哪些基金成功留在了当期前 buffer_size 内
    retained_product_ids = previous_shortlist_res[previous_shortlist_res['product_id'].isin(buffered_product_ids)][
        'product_id'].to_list()

    # 获取这批保留基金的完整信息
    retained_df = df_agg[df_agg['product_id'].isin(retained_product_ids)]

    # 记录已经被选中的基金经理名单（为了后续的基金经理去重做准备）
    seen_pms = set()
    for pms_str in retained_df['pm_name']:
        if pd.notna(pms_str):
            # 将多基金经理字符串拆解后放入集合
            seen_pms.update([pm.strip() for pm in str(pms_str).split(',')])

    # 计算距离目标 shortlist_num 还需要再选几只
    needed_num = shortlist_num - len(retained_df)

    # ==========================================
    # 【功能 1】：出名单前对同基金经理的基金去重
    # ==========================================
    new_selected_list = []
    pool_exclude_retained = df_agg[~df_agg['product_id'].isin(retained_product_ids)]

    # 遍历剩下的基金池，顺延选拔
    for _, row in pool_exclude_retained.iterrows():
        if needed_num <= 0:
            break

        # 提取当前这只基金所有的基金经理
        current_pms_str = row['pm_name']
        current_pms = set([pm.strip() for pm in str(current_pms_str).split(',')]) if pd.notna(
            current_pms_str) else set()

        # 核心去重逻辑：如果这只基金的【任何一位】基金经理已经存在于 seen_pms 集合中，则跳过该基金
        if not current_pms.isdisjoint(seen_pms):
            continue

        # 满足条件，入选！
        new_selected_list.append(row)
        # 将该基金的所有基金经理加入已选集合中，阻断他们入选下一只产品的机会
        seen_pms.update(current_pms)
        needed_num -= 1

    # 将新入选的字典列表转回 DataFrame
    new_selected_df = pd.DataFrame(new_selected_list) if new_selected_list else pd.DataFrame(
        columns=retained_df.columns)

    # 拼接保留名单与新入选名单，形成最终的 shortlist_num 只基金
    final_fund_result = pd.concat([retained_df, new_selected_df], axis=0).reset_index(drop=True)

    # 强制等权分配 (1/30)
    final_fund_result['weight'] = 1.0 / shortlist_num

    # 提取需要的标准字段
    final_fund_result = final_fund_result[['date', 'product_id', 'product_name', 'pm_name', 'score', 'weight']]

    # -------------------
    # 输出和收尾工作
    # -------------------
    # 计算每只基金当前期的真实打分排名
    product_score = product_score.sort_values('score', ascending=False).reset_index(drop=True).reset_index().rename(
        columns={'index': 'rank'})
    product_score = product_score.drop(columns=['score'])

    # 左连接合并全部因子打分详情
    shortlist_res = pd.merge(final_fund_result, product_score, on='product_id', how='left')

    # 反向因子重命名操作
    rename_cols = {
        'mdd': 'mdd_反向',
        'size': 'size_反向',
        'tracking_error_885001': 'tracking_error_885001_反向',
        'tracking_error_000906': 'tracking_error_000906_反向',
        'vol_nl': 'vol_nl_反向'
    }
    shortlist_res = shortlist_res.rename(columns=rename_cols)

    # 输出缓存文件
    shortlist_res.to_excel(cc30_run_path + "智选30-债券基金选择_{}.xlsx".format(date))

    return shortlist_res


# --------------------------------------------
# 货基-筛选CC30公募基金池
# 1. 股票型，偏股混合型，高仓位灵活配置型(>=50%)开放式基金，无最短持有期限
# 2. 至少一位现任基金经理任职时间大于1年
# 3. 基金最新规模大于2亿
# 4. 近四个季度权益平均仓位大于50%
# 5. 开放申购赎回
# --------------------------------------------
def fstrat_getCC30MoneyMFPool(
    date,    # 考察日期
    company_id = False  #是否保留公司id
):
    mf_info = wind.wind_getHistoricalProductList(as_of_date=date, include_pm_info=True)  # 获取历史初始基金，即AC份额仅考虑A份额
    # 筛选正在生效的sector type标签
    mf_info = mf_info[(mf_info['sector_start_date'] <= date) & ((mf_info['sector_end_date'] >= date) | mf_info['sector_end_date'].isna())]
    mf_info = mf_info[mf_info['type'].isin(['货币市场型基金'])]
    mf_info = mf_info[(mf_info['fund_open_type'] == '契约型开放式') & (mf_info['min_holding_month'].isna())]
    mf_info = mf_info[~(mf_info['product_full_name'].str.contains('定开') | mf_info['product_full_name'].str.contains('持有') | mf_info['product_full_name'].str.contains('定期'))]
    # 筛选正在任职的PM，保留任职时间大于1Y
    mf_info = mf_info[(mf_info['pm_start_date'] <= date) & ((mf_info['pm_end_date'] >= date) | mf_info['pm_end_date'].isna())]
    mf_info['pm_duration_days'] = (mf_info['pm_end_date'].apply(lambda x: min(date, x) if not pd.isna(x) else date) - mf_info['pm_start_date']).apply(lambda x: x.days)
    mf_info = mf_info[mf_info['pm_duration_days'] >= 365]
    # 基金最新规模大于10亿
    mf_latest_aum = wind.wind_getMFLatestAUM(date - datetime.timedelta(days=365), date)
    mf_info = pd.merge(mf_info, mf_latest_aum[['product_id', 'aum']], on=['product_id'], how='left')
    mf_info = mf_info[mf_info['aum'] >= 10e8]
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
# -----------------------------------------
# 债基因子计算模块 获取模型因子得分并缓存
# -----------------------------------------
def fstrat_getCC30ProductScore_money(
    date,                   # 考察日期
    model_freq='Q',             # 模型调仓频率 决定了模型的运行日期
    benchmark='000906.SH',  # 指标计算基准
    rf=0.03,                # 无风险利率
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
    fund_universe = fstrat_getCC30MoneyMFPool(date,company_id=True)
    # 剔除掉不在备选库的基金公司的产品
    # fundCompanyPool = pd.read_excel(cc30_run_path+"基金公司库.xlsx")
    # fundCompanyPool = fundCompanyPool[fundCompanyPool['所属库'] == '基金公司备选库']
    # fundCompanyPool2 = fundCompanyPool['基金公司代码'].to_list()
    # # sql_1 = "select COMP_NAME, COMP_SNAME, COMP_ID " \
    # #         "from CFundIntroduction "
    # # dbconn = wind.wind_connectWindDB()
    # # fundcompanylist = pd.read_sql_query(sql_1, dbconn)
    # fund_universe = fund_universe[fund_universe['company_id'].isin(fundCompanyPool2)]

    # 缓存基金池 数据带PM不去重
    fund_universe.to_excel(cc30_run_path+"货基基金池_{}.xlsx".format(date), index=None)
    # 因子计算
    product_ids = fund_universe['product_id'].unique().tolist()
    product_indicator_info = MFanls.anlsMF_SelectedRatingIndicator(product_ids, anls_start_date, date, 'D', benchmark, rf)  # 因子底层使用日频收益计算

    #计算7日收益sharpe
    sql1 = ("select S_INFO_WINDCODE as product_id, F_INFO_YEARLYROE as seven_day_return, F_INFO_ENDDATE as trade_date "
            "from CMoneyMarketFIncome where S_INFO_WINDCODE in {}")
    dbconn = wind.wind_connectWindDB()
    moneyfundreturn = pd.read_sql_query(sql1.format(tuple(product_ids)), dbconn)
    moneyfundreturn = moneyfundreturn[moneyfundreturn['trade_date']>=anls_start_date.strftime("%Y%m%d")]
    moneyfundreturn = moneyfundreturn[moneyfundreturn['trade_date']<=date.strftime("%Y%m%d")]
    # 1. 核心计算函数：按基金分组计算夏普比率
    def calc_seven_day_sharpe(group):
        """
        计算单只基金的七日收益夏普比率
        参数：group - 单只基金的分组数据
        返回：夏普比率（均值/标准差），无有效数据时返回NaN
        """
        # 提取该基金的所有七日收益数据
        returns = group['seven_day_return']
        # 计算均值和标准差（使用样本标准差，ddof=1，符合金融分析惯例）
        mean_ret = returns.mean()
        std_ret = returns.std(ddof=1)

        # 处理边界情况：标准差为0/NaN，或数据量不足（至少2条才计算标准差）
        if pd.isna(std_ret) or std_ret == 0 or len(returns) < 2:
            return np.nan
        # 计算夏普比率
        return mean_ret / std_ret
    # 2. 按基金分组计算夏普比率（移除include_groups参数，兼容所有版本）
    # 方式1：仅输出夏普比率（适配低版本pandas）
    sharpe_result = moneyfundreturn.groupby('product_id').apply(calc_seven_day_sharpe)
    # 重置索引并命名列（低版本pandas需要手动处理）
    sharpe_result = sharpe_result.reset_index(name='seven_day_sharpe')
    product_indicator_info = pd.merge(product_indicator_info, sharpe_result, on='product_id', how='left')
    indicator_score = product_indicator_info.set_index('product_id').rank(pct=True, ascending=True).reset_index()   # 将因子值转化为排名，越大表现越好。
    weekly_perf_rank_stability = MFanls.anlsMF_RankStability(product_ids, anls_start_date, date)   # 周度收益率的排名稳定性
    product_score = pd.merge(indicator_score, weekly_perf_rank_stability, on='product_id', how='left')
    # 缓存因子打分
    product_score.to_excel(cc30_run_path+"货基因子打分_{}.xlsx".format(date), index=None)
    return product_score


# -----------------------------------------
# 回测缓存CC30模型的最终产品清单
# 设置缓冲池，每位PM组合仅保留一个产品   货基
# -----------------------------------------
def fstrat_getCC30ModelFinalProductList_money(
        date,  # 考察日期 需为模型运行日期
        ann_date_temp,  # 最近一期年报
        model_freq='Q',  # 模型调仓频率 决定了模型的运行日期
        shortlist_num=20,  # 模型最终输出的产品个数
        buffer_size=60,  # 缓冲池大小
        excess_drawdown_threshold=0.03,
        original_ind_deviation=1,
        original_deviation=10,
        temp_ind_deviation=0.01,
        temp_deviation=0.1,
        index='885001.WI',
        index_delay=0,
        stock_barra=0,
        index_barra=0,
        equal_weight=True
):
    # 1. 计算最近两次模型运行日期
    if model_freq == 'Q':
        adj_calendar = fstrat_getAdjustmentCalendar(freq=model_freq)
        adj_calendar1 = adj_calendar
    if model_freq == 'W':
        adj_calendar1 = fstrat_getAdjustmentCalendar(freq='Q')
        adj_calendar2 = fstrat_getAdjustmentCalendar(freq='W')
        adj_calendar = pd.concat([adj_calendar1, adj_calendar2], axis=0).drop_duplicates(subset=["model_date"])
        adj_calendar.dropna(inplace=True)
        adj_calendar.sort_values(by='model_date', inplace=True)

    previous_model_date = adj_calendar[adj_calendar['model_date'] < date]['model_date'].iloc[-1]

    # 2. 读取上一期最终名单
    previous_shortlist_res_path = cc30_run_path + "货基上一期持仓.xlsx"
    assert os.path.exists(previous_shortlist_res_path), f"未找到{previous_shortlist_res_path}，请先缓存上一期最终名单"
    previous_shortlist_res = pd.read_excel(previous_shortlist_res_path, index_col=0)[
        ['product_id']].reset_index().rename(columns={'index': 'previous_index'})

    # 3. 读取当期基金池 包含多行pm信息
    fund_universe_path = cc30_run_path + "货基基金池_{}.xlsx".format(date)
    assert os.path.exists(fund_universe_path), f"未找到{fund_universe_path}，请先缓存当期基金池结果"
    fund_universe = pd.read_excel(fund_universe_path)
    fund_universe['date'] = pd.to_datetime(fund_universe['date']).dt.date

    # ==========================================
    # 【去重步骤 1】：对基金ID去重，合并所有基金经理
    # 逻辑：使用sorted排序，确保“A,B”和“B,A”经理组合被识别为完全相同
    # ==========================================
    fund_universe_agg = fund_universe.groupby('product_id', sort=False).agg({
        'date': 'first',
        'product_name': 'first',
        'pm_name': lambda x: ', '.join(sorted(x.dropna().astype(str).unique()))
    }).reset_index()

    # 4. 读取当期的打分结果
    current_fund_score_path = cc30_run_path + "货基因子打分_{}.xlsx".format(date)
    assert os.path.exists(current_fund_score_path), f"未找到{current_fund_score_path}，请先缓存当期打分结果"
    product_score = pd.read_excel(current_fund_score_path)

    # 5. 模型策略部分 计算得分
    product_score['score'] = (0.5 * product_score['seven_day_sharpe'] +
                              0.5 * product_score['stability'])

    # 将基本信息与打分合并
    df_merged = pd.merge(fund_universe_agg, product_score, on='product_id', how='left')
    # 先按得分降序排列
    df_merged = df_merged.sort_values('score', ascending=False).reset_index(drop=True)

    # ==========================================
    # 【去重步骤 2】：对“经理团队完全相同”的产品去重
    # 逻辑：在打分后保留该团队组合中分数最高的那只基金
    # ==========================================
    df_agg = df_merged.drop_duplicates(subset=['pm_name'], keep='first').reset_index(drop=True)

    # 导出完全去重后的打分表以便排查
    df_agg.to_excel("模型输出结果/货基-基金打分结果(完全去重版)_{}.xlsx".format(date))

    # -------------------
    # 生成最终名单 (缓冲池优先保留 + 顺延递补 + 等权)
    # -------------------
    # 提取去重后池子中排名前 buffer_size 的 product_id
    buffered_product_ids = df_agg['product_id'].tolist()[:buffer_size]

    # 检查上期持仓中有哪些基金留在了当期前 buffer_size 内
    retained_product_ids = previous_shortlist_res[previous_shortlist_res['product_id'].isin(buffered_product_ids)][
        'product_id'].to_list()

    # 获取保留基金的完整信息
    retained_df = df_agg[df_agg['product_id'].isin(retained_product_ids)]

    # 计算还需要再补选几只
    needed_num = shortlist_num - len(retained_df)

    # 从去重池子中剔除已保留的基金
    pool_exclude_retained = df_agg[~df_agg['product_id'].isin(retained_product_ids)]

    # 按照打分顺延截取
    if needed_num > 0:
        new_selected_df = pool_exclude_retained.head(needed_num)
    else:
        new_selected_df = pd.DataFrame(columns=retained_df.columns)

    # 拼接保留名单与新入选名单
    final_fund_result = pd.concat([retained_df, new_selected_df], axis=0).reset_index(drop=True)

    # 强制等权分配 (1/shortlist_num)
    final_fund_result['weight'] = 1.0 / shortlist_num

    # 提取标准字段
    final_fund_result = final_fund_result[['date', 'product_id', 'product_name', 'pm_name', 'score', 'weight']]

    # -------------------
    # 输出和收尾工作
    # -------------------
    # 计算全池真实的打分排名（基于去重后的池子）
    rank_df = df_agg[['product_id', 'score']].sort_values('score', ascending=False).reset_index(
        drop=True).reset_index().rename(
        columns={'index': 'rank'})
    rank_df = rank_df.drop(columns=['score'])

    # 合并打分排名详情
    shortlist_res = pd.merge(final_fund_result, rank_df, on='product_id', how='left')

    # 反向因子重命名操作
    rename_cols = {
        'mdd': 'mdd_反向',
        'size': 'size_反向',
        'tracking_error_885001': 'tracking_error_885001_反向',
        'tracking_error_000906': 'tracking_error_000906_反向',
        'vol_nl': 'vol_nl_反向'
    }
    shortlist_res = shortlist_res.rename(columns=rename_cols)

    # 输出缓存文件
    shortlist_res.to_excel(cc30_run_path + "智选30-货币基金选择_{}.xlsx".format(date))

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


import pandas as pd
import numpy as np
import os
import datetime

# -----------------------------------------
# 回测缓存CC30模型的最终产品清单
# 设置缓冲池，读取上期名单并在buffer内保留，30只等权
# 功能1：对基金去重（相同产品合并展示所有基金经理，按字母/拼音排序保证标识唯一）
# 功能2：对完全相同的基金经理团队去重（保留该团队下打分最高的一只产品）
# 注：所有去重动作均在生成最终选拔名单前完成
# -----------------------------------------
def fstrat_getCC30ModelFinalProductList_changeable_diviation(
        date,  # 考察日期 需为模型运行日期
        ann_date_temp,  # 最近一期年报
        model_freq='Q',  # 模型调仓频率 决定了模型的运行日期
        shortlist_num=30,  # 模型最终输出的产品个数
        buffer_size=90,  # 缓冲池大小
        excess_drawdown_threshold=0.03,
        original_ind_deviation=1,
        original_deviation=10,
        temp_ind_deviation=0.01,
        temp_deviation=0.1,
        index='885001.WI',
        index_delay=0,
        stock_barra=0,
        index_barra=0,
        equal_weight=True
):
    # 1. 计算最近两次模型运行日期
    if model_freq == 'Q':
        adj_calendar = fstrat_getAdjustmentCalendar(freq=model_freq)
        adj_calendar1 = adj_calendar
    if model_freq == 'W':
        adj_calendar1 = fstrat_getAdjustmentCalendar(freq='Q')
        adj_calendar2 = fstrat_getAdjustmentCalendar(freq='W')
        adj_calendar = pd.concat([adj_calendar1, adj_calendar2], axis=0).drop_duplicates(subset=["model_date"])
        adj_calendar.dropna(inplace=True)
        adj_calendar.sort_values(by='model_date', inplace=True)

    previous_model_date = adj_calendar[adj_calendar['model_date'] < date]['model_date'].iloc[-1]

    # 2. 读取上一期最终名单
    previous_shortlist_res_path = cc30_run_path + "上一期持仓.xlsx"
    assert os.path.exists(previous_shortlist_res_path), f"未找到{previous_shortlist_res_path}，请先缓存上一期最终名单"
    previous_shortlist_res = pd.read_excel(previous_shortlist_res_path, index_col=0)[
        ['product_id']].reset_index().rename(columns={'index': 'previous_index'})

    # 3. 读取当期基金池 包含多行pm信息
    fund_universe_path = cc30_run_path + "基金池_{}.xlsx".format(date)
    assert os.path.exists(fund_universe_path), f"未找到{fund_universe_path}，请先缓存当期基金池结果"
    fund_universe = pd.read_excel(fund_universe_path)
    fund_universe['date'] = pd.to_datetime(fund_universe['date']).dt.date

    # ==========================================
    # 【去重步骤 1】：对同一只基金去重，合并显示所有基金经理
    # ==========================================
    # 加入 sorted() 确保基金经理顺序一致 (如"张三, 李四"与"李四, 张三"统一为同一种表述)
    fund_universe_agg = fund_universe.groupby('product_id', sort=False).agg({
        'date': 'first',
        'product_name': 'first',
        'pm_name': lambda x: ', '.join(sorted(x.dropna().astype(str).unique()))
    }).reset_index()

    # 4. 读取当期的打分结果
    current_fund_score_path = cc30_run_path + "因子打分_{}.xlsx".format(date)
    assert os.path.exists(current_fund_score_path), f"未找到{current_fund_score_path}，请先缓存当期打分结果"
    product_score = pd.read_excel(current_fund_score_path)

    # 5. 模型策略部分 因子权重计算
    product_score['score'] = (0.2 * product_score['jensen_beta'] + 0.4 * product_score['sharpe'] +
                              0.1 * product_score['TM_gamma'] + 0.1 * product_score['TM_alpha'] +
                              0.2 * product_score['stability'])

    # 将去重后的基金基本信息与打分合并
    df_agg = pd.merge(fund_universe_agg, product_score, on='product_id', how='left')

    # 按照综合打分倒序排列
    df_agg = df_agg.sort_values('score', ascending=False).reset_index(drop=True)

    # ==========================================
    # 【去重步骤 2】：对“基金经理团队完全相同”的产品去重
    # ==========================================
    # 此时 df_agg 已按打分倒序排列，drop_duplicates 默认 keep='first'
    # 即可完美剔除完全相同基金经理团队的多余产品，仅保留该团队打分最高的那一只
    df_agg = df_agg.drop_duplicates(subset=['pm_name'], keep='first').reset_index(drop=True)

    # 导出文件供排查（此时的池子已经是完全去重且排好序的纯净池）
    df_agg.to_excel("模型输出结果/智选30-基金打分结果(完全去重版)_{}.xlsx".format(date))

    # -------------------
    # 生成最终名单 (缓冲池优先保留 + 顺延递补 + 等权)
    # -------------------
    # 提取排名前 buffer_size 的 product_id 列表
    buffered_product_ids = df_agg['product_id'].tolist()[:buffer_size]

    # 检查上期持仓中有哪些基金成功留在了当期前 buffer_size 内
    retained_product_ids = previous_shortlist_res[previous_shortlist_res['product_id'].isin(buffered_product_ids)][
        'product_id'].to_list()

    # 获取这批保留基金的完整信息
    retained_df = df_agg[df_agg['product_id'].isin(retained_product_ids)]

    # 计算距离目标 shortlist_num 还需要再选几只
    needed_num = shortlist_num - len(retained_df)

    # ==========================================
    # 递补剩余名额
    # ==========================================
    # 从已经去重且排好序的打分表中剔除掉已经保留的基金
    pool_exclude_retained = df_agg[~df_agg['product_id'].isin(retained_product_ids)]

    # 顺延截取头部 needed_num 只
    if needed_num > 0:
        new_selected_df = pool_exclude_retained.head(needed_num)
    else:
        new_selected_df = pd.DataFrame(columns=retained_df.columns)

    # 拼接保留名单与新入选名单，形成最终的 shortlist_num 只基金
    final_fund_result = pd.concat([retained_df, new_selected_df], axis=0).reset_index(drop=True)

    # 强制等权分配 (1/30)
    final_fund_result['weight'] = 1.0 / shortlist_num

    # 提取需要的标准字段
    final_fund_result = final_fund_result[['date', 'product_id', 'product_name', 'pm_name', 'score', 'weight']]

    # -------------------
    # 输出和收尾工作
    # -------------------
    # 计算每只基金当前期的真实打分排名
    product_score = product_score.sort_values('score', ascending=False).reset_index(drop=True).reset_index().rename(
        columns={'index': 'rank'})
    product_score = product_score.drop(columns=['score'])

    # 左连接合并全部因子打分详情
    shortlist_res = pd.merge(final_fund_result, product_score, on='product_id', how='left')

    # 反向因子重命名操作
    rename_cols = {
        'mdd': 'mdd_反向',
        'size': 'size_反向',
        'tracking_error_885001': 'tracking_error_885001_反向',
        'tracking_error_000906': 'tracking_error_000906_反向',
        'vol_nl': 'vol_nl_反向'
    }
    shortlist_res = shortlist_res.rename(columns=rename_cols)

    # 输出缓存文件
    shortlist_res.to_excel(cc30_run_path + "智选30-基金选择_{}.xlsx".format(date))

    return shortlist_res


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
    model_start_date = datetime.date(2025, 6, 30)
    # model_start_date = datetime.date(2024,7,31)
    model_end_date = datetime.date(2026, 1, 30)
    model_freq = 'Q'  # 调仓频率 暂仅支持Q\W

    ### 如果希望在指定日期运算，请运行以下代码
    model_date = datetime.date(2026,4,30)
    ann_date = datetime.date(2025,12,31)
    ###

    # # cal & cache factors
    # print(model_date)
    # fstrat_getCC30ProductScore(date=model_date, model_freq=model_freq, benchmark='885001.WI', rf=0.03)

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
    fstrat_getCC30ModelFinalProductList_changeable_diviation(model_date, ann_date, model_freq=model_freq, shortlist_num=30, buffer_size=90,excess_drawdown_threshold=100,
                                                                 original_ind_deviation=100, original_deviation=100, temp_ind_deviation=100,temp_deviation=100, index='885001.WI', index_delay=1,
                                                                 stock_barra=stock_barra, index_barra=index_barra,  equal_weight = True )

    ####债基 每半年跑一次
    # fstrat_getCC30ProductScore_bond(date=model_date, model_freq=model_freq, benchmark='885008.WI', rf=0.03)
    # fstrat_getCC30ModelFinalProductList_bond(model_date, ann_date, model_freq=model_freq, shortlist_num=20, buffer_size=100,excess_drawdown_threshold=100,
    #                                                              original_ind_deviation=100, original_deviation=100, temp_ind_deviation=100,temp_deviation=100, index='885001.WI', index_delay=1,
    #                                                              stock_barra=stock_barra, index_barra=index_barra,  equal_weight = True )

    ####货基 每季度跑一次
    # fstrat_getCC30ProductScore_money(date=model_date, model_freq=model_freq, benchmark='885008.WI', rf=0.03)
    fstrat_getCC30ModelFinalProductList_money(model_date, ann_date, model_freq=model_freq, shortlist_num=20, buffer_size=60,excess_drawdown_threshold=100,
                                                                 original_ind_deviation=100, original_deviation=100, temp_ind_deviation=100,temp_deviation=100, index='885001.WI', index_delay=1,
                                                                 stock_barra=stock_barra, index_barra=index_barra,  equal_weight = True )