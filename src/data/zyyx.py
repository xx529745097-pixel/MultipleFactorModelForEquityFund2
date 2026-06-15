# ------------------------------------------------------
# 本文档用于从朝阳永续数据库读取并预处理数据
# ------------------------------------------------------

from sqlalchemy import create_engine
import pandas as pd
import datetime

# ------------------------------------------------------
# 朝阳永续数据库链接
# ------------------------------------------------------
def _connectzyyyxDB():
    __zyyx = 'oracle://yanruofan:passwd40!@172.22.133.52:1521/ORCL'
    zyyx_engine = create_engine(__zyyx)
    zyyx_conn = zyyx_engine.connect()
    return zyyx_conn

# ------------------------------------------------------
# 一个SQL的Helper私有函数
# ------------------------------------------------------
def _sqlInArrayHelper(array):
    ss = '('
    for i in range(len(array)):
        if i < len(array)-1:
            ss = ss + str(array[i]) + ", "
        else:
            ss = ss + str(array[i])
    ss = ss + ')'
    return ss

# ------------------------------------------------------
# 获取一周/月中哪天汇报的产品数最多的Helper函数
# ------------------------------------------------------
def _getMostReportDateHelper(df_fund, freq):
    freq_dict = {'W': 'week', 'M': 'month'}
    freq = freq_dict[freq]
    max_count = df_fund.groupby(['year'] + [freq] + ['statistic_date'], as_index=False).count()
    max_count = max_count.sort_values(['year'] + [freq] + ['fund_id'])
    max_count = max_count.groupby(['year'] + [freq], as_index=False).last()
    max_count = max_count.loc[:, ['year'] + [freq] + ['statistic_date']]
    df_fund = pd.merge(df_fund, max_count, how='inner',
                       left_on=['year'] + [freq] + ['statistic_date'],
                       right_on=['year'] + [freq] + ['statistic_date'])
    return df_fund

# ------------------------------------------------------
# 从指数增强类策略中拆分300， 500， 1000的Helper函数。
# ------------------------------------------------------
def _enhancedIndexHelper(stats, category):
    if '300' in category:
        ret = stats[stats['fund_name'].str.contains('300')]
    elif '500' in category:
        ret = stats[stats['fund_name'].str.contains('500')]
    elif '1000' in category:
        ret = stats[stats['fund_name'].str.contains('1000')]
    else:
        AssertionError('current category is not supported yet')
    return ret

# ------------------------------------------------------
# 从组合基金拆分处理高、中、低波动率的Helper函数。
# ------------------------------------------------------
def _hfFOFProductHelper(stats, category):

    if '低波动' in category:
        ret = stats[stats['total_stdev_a'] <= 0.05]
    elif '中波动' in category:
        ret = stats[(stats['total_stdev_a'] > 0.05) & (stats['total_stdev_a'] <= 0.1)]
    elif '高波动' in category:
        ret = stats[stats['total_stdev_a'] > 0.1]
    else:
        AssertionError('current category is not supported yet')
    return ret

# ------------------------------------------------------
# 从CTA拆分处理高、中、低波动率的Helper函数。
# 同时根据条件对产品进行过滤
# ------------------------------------------------------
def _hfCTAProductHelper(stats, category):
    # CTA过滤条件：
    # 1.名称中不含其他策略关键字 2.成立以来年化收益不超过100% 3.成立以来年化波动率不超过30% 4.成立以来年化波动率不小于2%
    conditions = ~(
            (stats['fund_name'].str.contains('|'.join(['套利','期权','指增','指数','中性','对冲']))) |
            (stats['total_return_a'] > 1) |
            (stats['total_stdev_a'] > 0.3) |
            (stats['total_stdev_a'] < 0.02)
    )
    stats = stats[conditions]
    if '低波动' in category:
        ret = stats[stats['total_stdev_a'] <= 0.05]
    elif '中波动' in category:
        ret = stats[(stats['total_stdev_a'] > 0.05) & (stats['total_stdev_a'] <= 0.1)]
    elif '高波动' in category:
        ret = stats[stats['total_stdev_a'] > 0.1]
    elif category == '管理期货':
        ret = stats
    else:
        AssertionError('current category is not supported yet')
    return ret

# ------------------------------------------------------
# 从市场中性策略中剔除波动率较高离群点的Helper函数。
# ------------------------------------------------------
def _hfMarketNeutralHelper(stats, category):

    if '市场中性' in category:
        ret = stats[stats['total_stdev_a'] <= 0.1]
    else:
        AssertionError('current category is not supported yet')
    return ret

# ------------------------------------------------------
# 从套利策略中剔除波动率较高离群点的Helper函数。
# ------------------------------------------------------
def _hfArbitrageHelper(stats, category):

    if '套利策略' in category:
        ret = stats[stats['total_stdev_a'] <= 0.06]
    else:
        AssertionError('current category is not supported yet')
    return ret

# ------------------------------------------------------
# 获取朝阳永续所有基金产品信息
# ------------------------------------------------------
def zyyx_getProductBasicInfo():
    zyyx_conn = _connectzyyyxDB()
    zyyx_sql = "SELECT * FROM zysm.t_fund_info"
    df_fund = pd.read_sql_query(zyyx_sql, zyyx_conn)
    zyyx_conn.close()
    return df_fund

# ------------------------------------------------------
# 获取朝阳永续所有管理人基本信息
# ------------------------------------------------------
def zyyx_getManagerBasicInfo():
    zyyx_conn = _connectzyyyxDB()
    zyyx_sql = "SELECT * FROM zysm.t_fund_org"
    df_fund = pd.read_sql_query(zyyx_sql, zyyx_conn)
    zyyx_conn.close()
    return df_fund

# ------------------------------------------------------
# 获取朝阳永续基金类别信息
# ------------------------------------------------------
def zyyx_getAllClassification():
    zyyx_conn = _connectzyyyxDB()
    zyyx_sql = "SELECT * FROM zysm.t_fund_type_code"
    df_fund = pd.read_sql_query(zyyx_sql, zyyx_conn)
    zyyx_conn.close()
    return df_fund

# ------------------------------------------------------
# 获取朝阳永续基金产品的具体分类信息
# ------------------------------------------------------
def zyyx_getProductClassifications(
    type = None    # check the available input from zyyx_getAllClassification()
):
    zyyx_conn = _connectzyyyxDB()
    if type == None:
        zyyx_sql = "SELECT * FROM zysm.t_fund_type_mapping"
    else:
        zyyx_sql = "SELECT * FROM zysm.t_fund_type_mapping WHERE type_name = '{}'"
    df_fund = pd.read_sql_query(zyyx_sql.format(type), zyyx_conn)
    zyyx_conn.close()
    return df_fund

# ------------------------------------------------------
# 获取朝阳永续基金产品与基金管理人对应列表
# ------------------------------------------------------
def zyyx_productManagerMap():
    zyyx_conn = _connectzyyyxDB()
    zyyx_sql = "SELECT * FROM zysm.t_fund_org_mapping"
    df_fund = pd.read_sql_query(zyyx_sql, zyyx_conn)
    zyyx_conn.close()
    return df_fund

# ------------------------------------------------------
# 获取朝阳永续基金产品的收益情况，包括return, std, sharpe, 返回是dataframe.
# ------------------------------------------------------
def zyyx_productPerformance(
    fund_ids,             # An array of fund_id, at most 1000 each time
    start_date,           # 输入格式为Datetime.date
    end_date,             # 输入格式为Datetime.date
    freq,                 # string, must be one of ('W', 'M', 'Y')
    clean_date=False      # Only works when freq = 'W' or 'M'
):
    zyyx_conn = _connectzyyyxDB()
    start_date = start_date.strftime("%Y-%m-%d")
    end_date = end_date.strftime("%Y-%m-%d")
    perf_table = {
        'W' : 't_fund_weekly_performance',
        'M' : 't_fund_month_performance',
        'Y' : 't_fund_annully_performance'
    }
    fund_ids = _sqlInArrayHelper(fund_ids)
    zyyx_perf_sql = "SELECT * FROM zysm." + perf_table[freq] + \
               " WHERE statistic_date >= TO_DATE('{}', 'YYYY-MM-DD') AND statistic_date <= TO_DATE('{}', 'YYYY-MM-DD')" + \
               " AND fund_id IN {}"
    df_fund = pd.read_sql_query(zyyx_perf_sql.format(start_date, end_date, fund_ids), zyyx_conn)
    if freq in ['W', 'M'] and clean_date:
        df_fund = _getMostReportDateHelper(df_fund, freq)
    df_fund['statistic_date'] = pd.to_datetime(df_fund['statistic_date']).dt.date
    zyyx_conn.close()
    return df_fund

# ------------------------------------------------------
# 获取朝阳永续基金产品的风险指标，包括alpha，beta，calmar，sortino
# 等#, 返回是dataframe.
# ------------------------------------------------------
def zyyx_productRisk(
    fund_ids,             # An array of fund_id, at most 1000 each time
    start_date,           # 输入格式为Datetime.date
    end_date,             # 输入格式为Datetime.date
    freq,                 # string, must be one of ('W', 'M', 'Y')
    clean_date=False      # Only works when freq = 'W' or 'M'
):
    zyyx_conn = _connectzyyyxDB()
    start_date = start_date.strftime("%Y-%m-%d")
    end_date = end_date.strftime("%Y-%m-%d")
    risk_table = {
        'W': 't_fund_weekly_risk',
        'M': 't_fund_month_risk',
        'Y': 't_fund_annully_risk'
    }
    fund_ids = _sqlInArrayHelper(fund_ids)
    zyyx_risk_sql = "SELECT * FROM zysm." + risk_table[freq] + \
                    " WHERE statistic_date >= TO_DATE('{}', 'YYYY-MM-DD') AND statistic_date <= TO_DATE('{}', 'YYYY-MM-DD')" + \
                    " AND fund_id IN {}"
    df_fund = pd.read_sql_query(zyyx_risk_sql.format(start_date, end_date, fund_ids), zyyx_conn)
    if freq in ['W', 'M'] and clean_date:
        df_fund = _getMostReportDateHelper(df_fund, freq)
    df_fund['statistic_date'] = pd.to_datetime(df_fund['statistic_date']).dt.date
    zyyx_conn.close()
    return df_fund

# ------------------------------------------------------
# 获取朝阳永续所有某一类别的所有产品的多个风险收益指标情况。
# ------------------------------------------------------
def zyyx_getProductStats(
    start_date,
    end_date,
    category,
    stats,      # check perf or risk table, e.g.,t_fund_weekly_performance for stats column names, e.g., y1_return_a
):
    assert (type(start_date) == datetime.date), '日期输入格式需为datetime.date'
    assert (type(end_date) == datetime.date), '日期输入格式需为datetime.date'
    assert start_date <= end_date, '起始日需不晚于结束日'

    if '指数增强' in category:
        products = zyyx_getProductClassifications('指数增强')
    elif '组合基金' in category:
        products = zyyx_getProductClassifications('组合基金')
    elif '管理期货' in category:
        products = zyyx_getProductClassifications('管理期货')
    else:
        products = zyyx_getProductClassifications(category)
    all_info = zyyx_getProductBasicInfo()
    products = pd.merge(products, all_info, how='left', on=['fund_id'])
    if category == '股票多头':
        products = products[products['fund_type_quant'] == '非量化']
        products = products[products['fund_type_hedging'] == '非对冲']
        products = products.dropna(subset=['fund_member', 'fund_manager'])
        products['fund_manager'] = products['fund_manager']+'__'+products['fund_member']
    all_ids = products['fund_id'].to_list()
    all_ids_array = [all_ids[i:i+1000] for i in range(0,len(all_ids),1000)]
    all_stats_array = []
    for i in range(len(all_ids_array)):
        if 'return' in stats or 'stdev' in stats or 'sharp' in stats or 'max_retracement' in stats: # return, std, sharp and drawdown are from perf table.
            this_stats = zyyx_productPerformance(all_ids_array[i], start_date, end_date, 'W')
        else:
            this_stats = zyyx_productRisk(all_ids_array[i], start_date, end_date, 'W')
        all_stats_array.append(this_stats)

    all_stats = pd.concat(all_stats_array)
    if '指数增强' in category:
        all_stats = _enhancedIndexHelper(all_stats, category)
    if '组合基金' in category:
        all_stats =_hfFOFProductHelper(all_stats, category)
    if '管理期货' in category:
        all_stats = _hfCTAProductHelper(all_stats, category)
    if '股票市场中性' in category:
        all_stats = _hfMarketNeutralHelper(all_stats, category)
    if '套利策略' in category:
        all_stats = _hfArbitrageHelper(all_stats, category)

    all_stats = _getMostReportDateHelper(all_stats, 'W')
    all_stats = all_stats.reset_index(drop=True)
    all_stats = pd.merge(all_stats, products, how='left', on=['fund_id'])
    all_stats = all_stats.dropna(subset=['foundation_date'])
    all_stats['foundation_date'] = pd.to_datetime(all_stats['foundation_date']).dt.date
    all_stats = all_stats[all_stats.apply(lambda x: (x['statistic_date'] - x['foundation_date']).days > 90, axis=1)]
    all_stats = all_stats[['fund_id','fund_name', 'foundation_date', 'statistic_date','fund_manager','type_name']+[stats]]
    all_stats = all_stats.dropna(subset=[stats]+['fund_manager']).reset_index(drop=True)
    all_stats = all_stats.rename(
        columns={'fund_id': 'product_id', 'fund_name': 'product_name', 'statistic_date': 'date','fund_manager': 'manager', 'foundation_date': 'start_date'})
    all_stats = all_stats.reset_index(drop=True)
    return all_stats

# ------------------------------------------------------
# 获取朝阳永续私募指数点位
# ------------------------------------------------------
def zyyx_getStrategyIndex(
    start_date,  # 起始日期，输入格式:datetime.date
    end_date,  # 结束日期，输入格式:datetime.date
    index_ids  # An array of index_id
):
    zyyx_conn = _connectzyyyxDB()
    index_str = ','.join(["'%s'" % x for x in index_ids])
    zyyx_index_sql = "SELECT index_code, index_name, statistic_date," \
                     " index_value, funds_number, update_time" \
                     " FROM ZYSM.T_FUND_INDEX" \
                     " WHERE (index_code in ({}) AND statistic_date >= TO_DATE('{}', 'yyyy-mm-dd')" \
                     " AND statistic_date <= TO_DATE('{}', 'yyyy-mm-dd'))" \
                     " ORDER BY index_name, statistic_date DESC"
    df_zyyx_index = pd.read_sql_query(zyyx_index_sql.format(index_str, start_date, end_date), zyyx_conn)
    df_zyyx_index = df_zyyx_index.rename(columns={'statistic_date':'date'})
    df_zyyx_index['date'] = pd.to_datetime(df_zyyx_index['date']).dt.date
    zyyx_conn.close()
    return df_zyyx_index

# ------------------------------------------------------
# 获取朝阳永续私募指数收益率
# ------------------------------------------------------
def zyyx_getStrategyIndexReturn(
    start_date,  # 起始日期，输入格式:datetime.date
    end_date,   # 结束日期，输入格式:datetime.date
    index_ids,  # An array of index_id
    freq='W',   # 目前只支持周频
):
    assert freq == 'W', "朝阳永续指数目前只支持周频数据"
    assert len(index_ids) == 1, "目前仅支持输入单个指数id"
    zyyx_index = zyyx_getStrategyIndex(start_date-datetime.timedelta(days=30), end_date, index_ids)
    zyyx_index = zyyx_index.sort_values('date')
    zyyx_index['index_return_rate'] = zyyx_index['index_value'].pct_change()
    zyyx_index_return = zyyx_index[['date', 'index_code', 'index_name', 'index_value', 'index_return_rate']].rename(columns={'index_code': 'index_id'})
    zyyx_index_return = zyyx_index_return[(zyyx_index_return['date'] >= start_date) & (zyyx_index_return['date'] <= end_date)]
    return zyyx_index_return
