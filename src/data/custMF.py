import pandas as pd
import datetime
import src.const as const
import src.data.amdata as amdata
import src.data.irm as irm
import src.data.wind as wind
import src.utils.fof_calendar as calendar

# ------------------------------------------------------
# 读取本地的公募基金分类的信息，之后移入数据库中
# ------------------------------------------------------
def custMF_getCustomizedProductClassifications(
    category = None
):
    path = 'C:/Users/041947/Desktop/Data Framework/行业分类.xlsx'
    data = pd.read_excel(path)
    if category is not None:
        data = data.loc[data['product_classification'] == category]
    return data

# -----------------------------------------------------------------------------------------
# 从数据库中获取公募基金行业分类情况 - 目前是公募组本地代码逻辑实现，每半年手动存入一次
# -----------------------------------------------------------------------------------------
def custMF_getMFIndustryClassification(
    date=None,      # 默认取出当前最新结果，如果指定日期则取出该日期前最新一期的数据
    category=None   # list，可取出具体某些类别，默认全部取出
):
    conn = irm.irm_connectIRMDB()
    sql = "SELECT * FROM irm.AMFOF_MF_CLASSIIFCATION WHERE CLASSIFY_PERSPECTIVE = 'INDUSTRY'"
    if date is not None:
        sql += " AND data_date <= DATE'{}'".format(date)
    ret = pd.read_sql_query(sql, conn).rename(columns=str.lower)
    ret = ret[ret['data_date'] == ret['data_date'].max()]
    if category is not None:
        ret = ret[ret['product_classification'].isin(category)]
    conn.close()
    return ret

# ------------------------------------------------------
# 读取本地的公募基金分类的信息，之后移入数据库中
# ------------------------------------------------------
def custMF_getCoreMFProductlist():
    amdata_conn = amdata.amdata_connectAmdataDb()
    sql = "SELECT * FROM AMFOF.SRC_PUBLIC_FUND_LABEL"
    ret = pd.read_sql_query(sql, amdata_conn).rename(columns=str.lower)
    amdata_conn.close()
    return ret

# ------------------------------------------------------
# 获取公募基金评级信息
# ------------------------------------------------------
def custMF_getMFRatingInfo(
    start_date,
    end_date,
):
    conn = irm.irm_connectIRMDB()
    sql = "SELECT * FROM irm.AMFOF_SRC_FUND_RATING WHERE fund_type = '偏股型' AND (rating_date >= DATE'{0}' and rating_date <= DATE'{1}')"
    ret = pd.read_sql_query(sql.format(start_date, end_date), conn).rename(columns=str.lower)
    ret.rename(columns={'fund_code': 'product_id', 'fund_name': 'product_name'}, inplace=True)
    ret['rating_date'] = pd.to_datetime(ret['rating_date']).dt.date
    conn.close()
    return ret

# ------------------------------------------------------
# 获取公募基金评级信息日期列表
# ------------------------------------------------------
def custMF_getMFRatingInfoDateList():
    conn = irm.irm_connectIRMDB()
    sql = "SELECT DISTINCT rating_date FROM irm.AMFOF_SRC_FUND_RATING WHERE fund_type = '偏股型'"
    ret = pd.read_sql_query(sql, conn).rename(columns=str.lower)
    ret['rating_date'] = pd.to_datetime(ret['rating_date']).dt.date
    ret.sort_values(by='rating_date', ascending=False, inplace=True)
    conn.close()
    return ret

# ------------------------------------------------------------------------
# 从AMDATA中读取公募基金公司信息
# ------------------------------------------------------------------------
def custMF_getMFCompanyInfo(
    company_category = None,    # 私募、公募, list
    company_status = None       # 公司状态, list
):
    sql = "SELECT * FROM irm.MF_COMPANY_LIST"
    conn = irm.irm_connectIRMDB()
    df = pd.read_sql_query(sql, conn).rename(columns=str.lower)
    if company_category:
        df = df[df['company_category'].isin(company_category)]
    if company_status:
        df = df[df['company_status'].isin(company_status)]
    conn.close()
    return df

# ------------------------------------------------------------------------
# 从AMDATA中读取公募基金经理信息
# ------------------------------------------------------------------------
def custMF_getMFStrategyInfo(
    strategy_status = None,   # 是一个array，可选策略状态：已投、跟踪、其他
    strategy_level_1 = None,  # 策略一级标签, 是一array， ['主观权益']
    strategy_level_2 = None,  # 策略二级标签, 是一个array， ['质量策略']
):
    conn = irm.irm_connectIRMDB()
    sql = "SELECT * FROM irm.MF_STRATEGY_LIST"
    df = pd.read_sql_query(sql, conn).rename(columns=str.lower)
    strategy_level_1_list = df['label_level_1'].unique()
    strategy_level_2_list = df['label_level_2'].unique()

    if strategy_level_1:
        assert set(strategy_level_1) < set(strategy_level_1_list), "一级标签输入有误"
        filter_1 = (df['label_level_1'].isin(strategy_level_1))
    else:
        filter_1 = ~(df['label_level_1'] == strategy_level_1)

    if strategy_level_2:
        assert set(strategy_level_2) < set(strategy_level_2_list), "不存在该二级标签"
        filter_2 = (df['label_level_2'].isin(strategy_level_2))
    else:
        filter_2 = ~(df['label_level_2'] == strategy_level_2)

    if strategy_status:
        filter_3 = (df['strategy_status'].isin(strategy_status))
        df = df[filter_1 & filter_2 & filter_3]
    else:
        df = df[filter_1 & filter_2]
    company_info = custMF_getMFCompanyInfo()
    df = df.merge(company_info[['company_id', 'company_legal_name']], how='left', on='company_id')
    df.reset_index(inplace=True, drop=True)
    df['strategy_aum_date'] = pd.to_datetime(df['strategy_aum_date']).dt.date
    conn.close()
    return df

# ------------------------------------------------------------------------
# 从AMDATA中读取公募基金产品信息
# ------------------------------------------------------------------------
def custMF_getMFProductInfo(
    product_status=None,    # 产品类型，是一个array
    strategy_level_1=None,  # 一级策略对应的产品标签，是一个array
    strategy_level_2=None   # 二级策略对应的产品标签，是一个array
):
    if product_status == None:
        sql = "SELECT * FROM irm.MF_PRODUCT_LIST"
    else:
        sql = "SELECT * FROM irm.MF_PRODUCT_LIST WHERE product_status in ({})"
        product_status = ','.join(["'%s'" % x for x in product_status])
        sql = sql.format(product_status)
    conn = irm.irm_connectIRMDB()
    df = pd.read_sql_query(sql, conn).rename(columns=str.lower)
    strategy_info = custMF_getMFStrategyInfo(strategy_level_1=strategy_level_1, strategy_level_2=strategy_level_2)
    df = pd.merge(df, strategy_info[['company_id', 'company_legal_name', 'strategy_id', 'strategy_name', 'label_level_1', 'label_level_2']],
                  left_on='strategy_id', right_on='strategy_id', how='inner')
    conn.close()
    return df

# ------------------------------------------------------------------------
# 从AMDATA中读取公募策略收益序列信息
# ------------------------------------------------------------------------
def custMF_getMFStrategyReturn(
    strategy_ids,   # list, 策略id, e.g. ['MS000001', 'MS000771']
    start_date,     # DateTime.date instance
    end_date,       # DateTime.date instance
    freq            # 数据频率，D或者W
):
    assert isinstance(start_date, datetime.date), "date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "date must be an instance of datetime.date"
    assert isinstance(strategy_ids, list), '策略序列需为list'
    assert freq in ("D", "W"), "数据频率只支持D或者W"

    if freq == "D":
        sql = "SELECT * FROM irm.MF_STRATEGY_DAILY_INFO WHERE DT >= DATE'{}' AND DT <= DATE'{}' AND STRATEGY_ID IN ({})"
    else:
        sql = "SELECT * FROM irm.MF_STRATEGY_WEEKLY_INFO WHERE DT >= DATE'{}' AND DT <= DATE'{}' AND STRATEGY_ID IN ({})"
    strategy_ids = ','.join(["'%s'" % x for x in strategy_ids])
    conn = irm.irm_connectIRMDB()
    df = pd.read_sql_query(sql.format(start_date, end_date, strategy_ids), conn).rename(columns=str.lower)
    df.rename(columns={'dt': 'date'}, inplace=True)
    df['date'] = pd.to_datetime(df['date']).dt.date
    df = df[['date', 'strategy_name', 'strategy_id', 'adj_return_rate']].copy()
    df.sort_values(by=['strategy_name', 'date'], ascending=[True, True], inplace=True)
    df.reset_index(inplace=True, drop=True)
    df['data_freq'] = freq
    conn.close()
    return df

# ------------------------------------------------------------------------
# 从WIND读取公募产品收益序列信息
# LOF、ETF等产品需要使用场内ID (WIND数据库原因)
# ------------------------------------------------------------------------
def custMF_getMFProductReturn(
    product_ids,  # list, 公募产品id, e.g. ['000001.OF', '000002.OF']
    start_date,  # DateTime.date instance
    end_date,  # DateTime.date instance
    freq  # 数据频率，D或者W
):
    assert isinstance(start_date, datetime.date), "date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "date must be an instance of datetime.date"
    assert isinstance(product_ids, list), '产品id序列需为list'
    assert freq in ("D", "W"), "数据频率只支持D或者W"

    mf_product_info = wind.wind_getCurrentProductList(product_ids=product_ids)
    id_to_name = mf_product_info.set_index('product_id')['product_name'].to_dict()
    ret = wind.wind_getMFStats(product_ids, start_date, end_date, stats=['f_avgreturn_day']).dropna(subset=['f_avgreturn_day'])  # 非交易日也有nan数据，drop处理
    ret.rename(columns={'f_avgreturn_day': 'adj_return_rate'}, inplace=True)
    ret['product_name'] = ret['product_id'].apply(lambda x: id_to_name[x] if x in id_to_name.keys() else x)
    if freq == 'W':
        ret = calendar.calender_convertDailyReturnToWeekly(ret, 'date', 'adj_return_rate', 'product_id')
    ret['data_freq'] = freq
    ret = ret[['date', 'product_id', 'product_name', 'adj_return_rate', 'data_freq']]
    return ret

# ------------------------------------------------------------------------
# 从AMDATA或WIND中读取公募策略或产品收益信息的wrapper
# ------------------------------------------------------------------------
def custMF_getMFReturn(
    ids,
    start_date,
    end_date,
    freq,
    data_level,        # Strategy or Product
):
    assert data_level in ('Strategy', 'Product'), ""
    if data_level == 'Strategy':
        level_data = custMF_getMFStrategyReturn(ids, start_date, end_date, freq)
        level_data.rename(columns={'strategy_id': 'level_id', 'strategy_name': 'level_name'}, inplace=True)
    else:
        level_data = custMF_getMFProductReturn(ids, start_date, end_date, freq)
        level_data.rename(columns={'product_id': 'level_id', 'product_name': 'level_name'}, inplace=True)
    return level_data

# -----------------------------
# 获取研究平台模拟组合基础信息
# -----------------------------
def custMF_getMockPortReferenceData(
    pm_name=None,  # list, 分管人，默认为None取全部
    mock_port_label=None  # list, 模拟组合类型，例如'核心中核心'
):
    conn = irm.irm_connectIRMDB()
    sql = "select ID, GROUP_NAME, GROUP_TYPE, USER, START_DATE, LAST_ADJUST_DATE from irm.FUND_GROUP_VIEW where 1=1 "
    if pm_name:
        assert isinstance(pm_name, list), "pm_name需为list类型"
        sql += "and USER IN ({}) ".format(','.join(["'%s'" % pm for pm in pm_name]))
    if mock_port_label:
        assert isinstance(mock_port_label, list), "mock_port_label需为list类型"
        sql += "and GROUP_TYPE IN ({}) ".format(','.join(["'%s'" % label for label in mock_port_label]))
    df = pd.read_sql_query(sql, conn).rename(columns=str.lower)
    df.rename(columns={
        'id': 'portfolio_id', 'group_name': 'portfolio_name', 'group_type': 'mock_port_label', 'user': 'pm_name',
        'start_date': 'inception_date', 'last_adjust_date': 'holding_adjust_date'
    }, inplace=True)
    conn.close()
    return df

# -----------------------------
# 获取研究平台模拟组合持仓信息
# -----------------------------
def custMF_getMockPortHoldingData(
    start_date,  # 起始日期
    end_date,  # 截止日期
    mock_port_ids=None  # list，模拟组合id
):
    assert isinstance(start_date, datetime.date), 'start_date需为datetime.date'
    assert isinstance(end_date, datetime.date), 'start_date需为datetime.date'
    conn = irm.irm_connectIRMDB()
    sql = "select a.ID, a.NAME, a.BATCH_DATE, b.TOTAL_CAP, a.FUND_SYMBOL, a.FUND_NAME, a.HOLD_CAP, a.WEIGHT, a.TODAY_EARN, " \
          "a.TODAY_EARN_RATE, a.TOTAL_EARN, a.TOTAL_EARN_RATE " \
          "from irm.FUND_GROUP_ITEM_HISTORY_VIEW a left join irm.FUND_GROUP_DAY_HISTORY_VIEW b on a.ID=b.ID and a.BATCH_DATE=b.BATCH_DATE where 1=1 "
    if mock_port_ids:
        assert isinstance(mock_port_ids, list), "mock_port_ids需为list类型"
        sql += "and a.ID IN ({}) ".format(','.join(["'%s'" % mock_port_id for mock_port_id in mock_port_ids]))
    sql += "and a.BATCH_DATE >= DATE'{0}' and a.BATCH_DATE <= DATE'{1}' ".format(start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
    sql += "order by a.BATCH_DATE, a.ID, a.FUND_SYMBOL "
    df = pd.read_sql_query(sql, conn).rename(columns=str.lower)
    # 因持仓数据中未纳入现金项，存在资产求和不等于组合NAV的情况
    df.rename(columns={
        'id': 'portfolio_id', 'name': 'portfolio_name', 'batch_date': 'date', 'total_cap': 'NAV', 'fund_symbol': 'product_id',
        'fund_name': 'product_name', 'hold_cap': 'product_NAV', 'weight': 'product_weight', 'today_earn': 'product_daily_ret',
        'today_earn_rate': 'product_daily_ret_rate', 'total_earn': 'product_acm_ret', 'total_earn_rate': 'product_acm_ret_rate'
    }, inplace=True)
    conn.close()
    # FIXME 持仓数据目前会将全部赎回的产品在调仓当日还留在持仓数据中，持仓金额为0，目的是保留更多交易相关的浮盈浮亏数据
    # 这类为0的数据从推荐产品的角度来说无实际意义，故直接进行筛选
    df = df[df['product_NAV'] != 0]
    return df

# --------------------------------
# 获取研究平台模拟组合历史收益净值数据
# --------------------------------
def custMF_getMockPortNetValueAndReturn(
    start_date,  # 起始日期
    end_date,  # 截止日期
    mock_port_ids=None,   # list，模拟组合id
    freq='D'
):
    assert freq in ("D", "W"), "freq需为D或者W"
    assert isinstance(start_date, datetime.date), 'start_date需为datetime.date'
    assert isinstance(end_date, datetime.date), 'start_date需为datetime.date'
    conn = irm.irm_connectIRMDB()
    sql = "select a.ID, a.NAME, a.BATCH_DATE, a.VALUE, a.TOTAL_CAP, a.TODAY_EARN_RATE from irm.FUND_GROUP_DAY_HISTORY_VIEW a where 1=1 "
    if mock_port_ids:
        assert isinstance(mock_port_ids, list), "mock_port_ids需为list类型"
        sql += "and a.ID IN ({}) ".format(','.join(["'%s'" % mock_port_id for mock_port_id in mock_port_ids]))
    sql += "and a.BATCH_DATE >= DATE'{0}' and a.BATCH_DATE <= DATE'{1}' order by a.BATCH_DATE ".format(start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
    df = pd.read_sql_query(sql, conn).rename(columns=str.lower)
    df.rename(columns={
        'id': 'portfolio_id', 'name': 'portfolio_name', 'batch_date': 'date', 'value': 'NAV', 'total_cap': 'AUM', 'today_earn_rate': 'return',
    }, inplace=True)
    if freq == 'W':
        # 对日频数据降频处理
        df = calendar.calender_convertDailyReturnToWeekly(df, date_column_name='date', return_column_name='return', id_column_name='portfolio_id')
    conn.close()
    return df
