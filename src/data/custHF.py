import pandas as pd
import numpy as np
import datetime
import streamlit as st
import src.const as const
import src.data.amdata as amdata
import src.data.irm as irm
import src.data.wind as wind
import src.utils.fof_calendar as calendar

# ------------------------------------------------------
# 读取存储在amdata中的zyyx各类资产中位数stats
# ------------------------------------------------------
def custHF_allCategoryStatsDistribution():
    conn = irm.irm_connectIRMDB()
    sql = "SELECT * FROM irm.AMFOF_INDEX_YIELD_INFO"
    ret = pd.read_sql_query(sql, conn).rename(columns=str.lower)
    ret.rename(columns={'dt':'date'}, inplace=True)
    ret['date'] = pd.to_datetime(ret['date']).dt.date
    conn.close()
    return ret

# ------------------------------------------------------------------------
# 从AMDATA中读取估值表持股数据
# ------------------------------------------------------------------------
def custHF_getDataFromValuationSheet(
    product_code,
    start_date,  # DateTime.date instance
    end_date,  # DateTime.date instance
):
    conn = irm.irm_connectIRMDB()
    assert isinstance(start_date, datetime.date), "date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "date must be an instance of datetime.date"
    assert product_code.endswith('.OF'), '产品代码须在原6位后加上.OF'

    sql = "SELECT * FROM irm.amdata_src_fund_valuation_sheet WHERE D_DT >= DATE'{}' AND D_DT <= DATE'{}' AND C_SECU_ID = '{}'"
    df = pd.read_sql_query(sql.format(start_date, end_date, product_code), conn).rename(columns=str.lower)
    df.rename(columns={'d_dt': 'date', 'c_secu_id': 'product_id', 'c_secu_nm': 'product_name', 'c_stk_id': 'stock_id', 'c_stk_nm': 'stock_name', 'n_percent': 'weight'},
              inplace=True)
    df['date'] = pd.to_datetime(df['date']).dt.date
    conn.close()
    return df

# ------------------------------------------------------------------------
# 从估值表中读取产品信息 可根据估值表科目反查持有产品信息
# ------------------------------------------------------------------------
def custHF_getProductInfoFromValuationSheet(
    start_date,  # DateTime.date instance
    end_date,  # DateTime.date instance
    product_ids=None,  # 输入类型为list或None, 用于筛选持仓产品
    subject_id_like=None,  # 输入类型为list或None, 对new_subject_id字段进行局部模糊匹配, 筛选条件取并集
    subject_id_starts_like=None, # 输入类型为list或None, 对new_subject_id字段进行头部模糊匹配, 筛选条件取并集
    valuation_level=None,  # 输入类型为str或None, 对估值表级数筛选, 目前仅支持二级/四级筛选 筛选标准待进一步完善
    include_subject_details=False  # 默认不展示科目信息 保证数据库读取效率
):
    assert valuation_level in ('二级', '四级', None), "valuation_level暂仅支持('二级', '四级', None)"
    assert (subject_id_like is None and subject_id_starts_like is None) or (subject_id_like is None and subject_id_starts_like) \
           or (subject_id_like and subject_id_starts_like is None), "'subject_id_like' 和 'subject_id_starts_like' 不可同时启用"
    conn = irm.irm_connectIRMDB()
    if product_ids:  # 产品筛选
        product_ids = ["'%s'" % product_id.split('.')[0] for product_id in product_ids]  # 删除'.OF'
        sql_product = "AND FUND_ID IN ({}) ".format(','.join(product_ids))
    else:
        sql_product = ""
    if subject_id_like:  # 估值表科目筛选
        sql_subject_id_like = "AND REGEXP_LIKE (NEW_SUBJECT_CODE,'{}') ".format('|'.join(subject_id_like))  # REGEXP 匹配局部字符串
    else:
        sql_subject_id_like = ""
    if subject_id_starts_like:  # 估值表科目筛选
        sql_subject_id_starts_like = "AND REGEXP_LIKE (NEW_SUBJECT_CODE,'^({})') ".format('|'.join(subject_id_starts_like))  # REGEXP '^{}'表示从头匹配多个字符串
    else:
        sql_subject_id_starts_like = ""
    if valuation_level == '二级':  # 估值表级数筛选(对于四级估值表，此项筛选后仅保留二级条目)
        sql_valuation_level = "AND LENGTH(NEW_SUBJECT_CODE) <= 6 AND REGEXP_LIKE(NEW_SUBJECT_CODE,'^[0-9]|[a-zA-Z]$') "
    elif valuation_level == '四级':
        sql_valuation_level = "AND LENGTH(NEW_SUBJECT_CODE) > 6 AND REGEXP_LIKE(NEW_SUBJECT_CODE,'^[0-9]|[a-zA-Z]$') "
    else:
        sql_valuation_level = ""
    if include_subject_details:  # 是否展示科目细节
        sql = "SELECT FUND_DATE, FUND_ID, FUND_NAME, NEW_SUBJECT_CODE, SUBJECT_CODE, SUBJECT_NAME, COST, COST_NET_RATIO, MARKET_VALUE, VALUE_NET_RATIO FROM irm.fund_valuation_view " \
                "WHERE FUND_DATE >= DATE'{0}' AND FUND_DATE <= DATE'{1}' "
    else:  # 效率更高
        sql = "SELECT DISTINCT FUND_DATE, FUND_ID, FUND_NAME FROM irm.fund_valuation_view WHERE FUND_DATE >= DATE'{0}' AND FUND_DATE <= DATE'{1}' "

    sql = sql + sql_product + sql_subject_id_like + sql_subject_id_starts_like + sql_valuation_level
    df = pd.read_sql_query(sql.format(start_date, end_date), conn).rename(columns=str.lower)
    df.rename(columns={'fund_date': 'date',
                       'fund_id': 'product_id',
                       'fund_name': 'product_name',
                       'new_subject_code': 'new_subject_id',
                       'subject_code': 'subject_id',
                       'subject_name': 'subject_name',
                       'cost': 'subject_cost',
                       'cost_net_ratio': 'subject_cost_weight',
                       'market_value': 'subject_NAV',
                       'value_net_ratio': 'subject_weight'}, inplace=True)
    df['date'] = pd.to_datetime(df['date']).dt.date
    df['product_id'] = df['product_id'].apply(lambda x: x+'.OF')
    if include_subject_details:
        # 估值表中权重展示数值为百分比，IT读入时清洗掉了百分号
        df['subject_cost_weight'] /= 1e2
        df['subject_weight'] /= 1e2
    conn.close()
    return df

# ------------------------------------------------------------------------
# 从AMDATA中读取公司信息
# ------------------------------------------------------------------------
def custHF_getCompanyInfo(
    company_category=None,  # 私募、公募
    company_status=None  # 公司状态
):
    sql = "SELECT * FROM irm.COMPANY_LIST"
    if company_category:
        assert company_category in ('私募', '公募'), '公司种类需为私募或公募'
        sql = sql + " WHERE COMPANY_CATEGORY = '{}'"
        if company_status:
            assert company_status in const.const.HF_STATUS, "公司状态只能为" + ','.join(const.const.HF_STATUS)
            sql = sql + " AND COMPANY_STATUS = '{}'"
            sql = sql.format(company_category, company_status)
        else:
            sql = sql.format(company_category)
    else:
        if company_status:
            assert company_status in const.const.HF_STATUS, "公司状态只能为" + ','.join(const.const.HF_STATUS)
            sql = sql + " WHERE COMPANY_STATUS = '{}'"
            sql = sql.format(company_status)

    conn = irm.irm_connectIRMDB()
    df = pd.read_sql_query(sql, conn).rename(columns=str.lower)
    conn.close()
    return df

# ------------------------------------------------------------------------
# 从AMDATA中读取策略信息，判断条件取交集，如果为None则该索引条件无效
# ------------------------------------------------------------------------
def custHF_getStrategyInfo(
    strategy_status=None,  # 是一个array，可选策略状态：在库已投、跟踪、其他
    strategy_level_1=None,  # 策略一级标签, 是一array， ['期货策略']
    strategy_level_2=None,  # 策略二级标签, 是一个array， ['500指增']
):
    conn = irm.irm_connectIRMDB()
    sql = "SELECT * FROM irm.STRATEGY_LIST"
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
    company_info = custHF_getCompanyInfo()
    df = df.merge(company_info[['company_id', 'company_short_name']], how='left', on='company_id')
    df.reset_index(inplace=True, drop=True)
    conn.close()
    return df

# ------------------------------------------------------------------------
# 从AMDATA中读取产品信息
# ------------------------------------------------------------------------
def custHF_getProductInfo(
    product_status=None,            # 产品类型，是一个array
    strategy_level_1=None,          # 一级策略对应的产品标签，是一个array
    strategy_level_2=None,          # 二级策略对应的产品标签，是一个array
    include_filing_product=False,   # 是否纳入未备案的可认购的产品，主要用于交易辅助试算，额外的产品信息来自CAMP
):
    if product_status == None:
        sql = "SELECT * FROM irm.PRODUCT_LIST"
    else:
        sql = "SELECT * FROM irm.PRODUCT_LIST WHERE PRODUCT_TYPE in ({})"
        product_status = ','.join(["'%s'" % x for x in product_status])
        sql = sql.format(product_status)

    conn = irm.irm_connectIRMDB()
    df = pd.read_sql_query(sql, conn).rename(columns=str.lower)
    strategy_info = custHF_getStrategyInfo(strategy_level_1=strategy_level_1, strategy_level_2=strategy_level_2)
    df = pd.merge(df, strategy_info[['company_id', 'company_short_name', 'strategy_id', 'strategy_name', 'label_level_1', 'label_level_2', 'primary_coverage', 'limit']],
                  left_on='strategy_id', right_on='strategy_id', how='inner')
    df['product_inception_date'] = pd.to_datetime(df['product_inception_date']).dt.date
    df['product_aum_date'] = pd.to_datetime(df['product_aum_date']).dt.date
    conn.close()
    # 如果需要纳入未备案的可认购的产品，额外从CAMP产品信息表取数合并
    if include_filing_product:
        assert (product_status is None and strategy_level_1 is None and strategy_level_2 is None), "加入未备案产品信息的模式(include_filing_product)，需要取全量数据的场景才可以打开"
        product_contract_info = custHF_getProductContractInfoFromCAMP()
        product_contract_info = product_contract_info[(~product_contract_info['product_id'].isin(df['product_id'].tolist())) & (product_contract_info['contract_expiration_date']>=datetime.date.today())]
        df = pd.concat([df, product_contract_info[['product_id', 'product_short_name']]])
    return df

# ------------------------------------------------------------------------
# 从AMDATA中读取序列信息
# ------------------------------------------------------------------------
def custHF_getSeriesInfo():
    conn = irm.irm_connectIRMDB()
    sql = "SELECT * FROM irm.SERIES_LIST"
    ret = pd.read_sql_query(sql, conn).rename(columns=str.lower)
    conn.close()
    return ret

# ------------------------------------------------------------------------
# 从AMDATA中读取策略拼接信息
# ------------------------------------------------------------------------
def custHF_getStrategySeriesConcatPriorities():
    conn = irm.irm_connectIRMDB()
    sql = "SELECT * FROM irm.STRATEGY_RETURN_REP_HIST"
    ret = pd.read_sql_query(sql, conn).rename(columns=str.lower)
    conn.close()
    return ret

# ------------------------------------------------------------------------
# 获取策略收益序列拼接信息
# ------------------------------------------------------------------------
def custHF_getStrategySeriesConcatInfo(
    start_date,  # datetime, 开始日期
    end_date,  # datetime, 截止日期
    freq='D',   # 序列频率freq, must be in ('D', 'W')
    strategy_ids=None  # list, 筛选策略
):
    assert freq in ('D', 'W'), "序列频率freq需为'D'或'W'"
    conn = irm.irm_connectIRMDB()
    if freq == 'D':
        sql = "SELECT strategy_id, series_id, dt FROM irm.STRATEGY_DAILY_INFO WHERE dt >= DATE'{}' AND dt <= DATE'{}' "
    else:
        sql = "SELECT strategy_id, series_id, dt FROM irm.STRATEGY_WEEKLY_INFO WHERE dt >= DATE'{}' AND dt <= DATE'{}' "
    if strategy_ids:
        sql += "AND strategy_id IN ({}) ".format(','.join(["'%s'" % strategy_id for strategy_id in strategy_ids]))
    product_interval_info = pd.read_sql_query(sql.format(start_date, end_date), conn)
    conn.close()
    product_interval_info = product_interval_info.groupby(['strategy_id', 'series_id'], as_index=False).agg(start_date=('dt', 'min'), end_date=('dt', 'max'), filled_nav_points=('dt', 'count'))
    # 统计区间净值填充比例
    wind_calendar = wind.wind_getSSECalendar()
    wind_calendar.index = pd.to_datetime(wind_calendar['date'])
    def count_trade_days(x):
        return len(wind_calendar[(wind_calendar['date'] >= x['start_date']) & (wind_calendar['date'] <= x['end_date'])])
    def count_trade_weeks(x):
        # 使用周频筛选区间时，取开始日期所在周的周一作为起点，取截止日期所在周的周日作为终点
        return len(wind_calendar[(wind_calendar['date'] >= calendar.calendar_getLastTargetDay(x['start_date'], 'Monday'))
                                 & (wind_calendar['date'] <= calendar.calendar_getLastTargetDay(x['end_date']+datetime.timedelta(days=7), 'Sunday'))].resample('W').last().dropna())  # dropna 删去没有交易日的周
    product_interval_info['total_nav_points'] = product_interval_info.apply(count_trade_days if freq == 'D' else count_trade_weeks, axis=1)
    product_interval_info['nav_data_integrity'] = product_interval_info['filled_nav_points'] / product_interval_info['total_nav_points']
    strategy_series_concat_info = custHF_getStrategySeriesConcatPriorities()[['strategy_id', 'series_id', 'priority']]
    product_series_info = custHF_getSeriesInfo().rename(columns={'source': 'source_label'})
    result = pd.merge(product_interval_info, strategy_series_concat_info, on=['strategy_id', 'series_id'], how='left')
    result = pd.merge(result, product_series_info[['series_id', 'series_name', 'source_label']], on='series_id', how='left').sort_values(['strategy_id', 'start_date'])
    result['freq'] = freq
    result['priority'] = result['priority'].astype(int)
    return result

# ------------------------------------------------------------------------
# 从AMDATA中读取收益序列信息
# ------------------------------------------------------------------------
def custHF_getStrategyReturn(
    strategy_ids,  # list, 策略id, e.g. ['S0000045', 'S0000053']
    start_date,  # DateTime.date instance
    end_date,  # DateTime.date instance
    freq  # 数据频率，D或者W
):
    assert isinstance(start_date, datetime.date), "date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "date must be an instance of datetime.date"
    assert isinstance(strategy_ids, list), '策略序列需为list'
    assert freq in ("D", "W"), "数据频率只支持D或者W"

    if freq == "D":
        sql = "SELECT * FROM irm.STRATEGY_DAILY_INFO WHERE DT >= DATE'{}' AND DT <= DATE'{}' AND STRATEGY_ID IN ({})"
    else:
        sql = "SELECT * FROM irm.STRATEGY_WEEKLY_INFO WHERE DT >= DATE'{}' AND DT <= DATE'{}' AND STRATEGY_ID IN ({})"
    strategy_ids = ','.join(["'%s'" % x for x in strategy_ids])
    conn = irm.irm_connectIRMDB()
    df = pd.read_sql_query(sql.format(start_date, end_date, strategy_ids), conn).rename(columns=str.lower)
    conn.close()
    df.rename(columns={'dt': 'date'}, inplace=True)
    df['date'] = pd.to_datetime(df['date']).dt.date
    df = df[['date', 'strategy_name', 'strategy_id', 'adj_return_rate']].copy()
    df.sort_values('date', inplace=True)
    # 如果取出了SI区间的收益率，第一个日期的收益率为nan，需去除第一个日期再进行收益计算
    if (not df.empty) and (df['adj_return_rate'].iloc[0] is None or np.isnan(df['adj_return_rate'].iloc[0])):
        df = df[1:]
    # 策略周频数据再过一次降频函数（与获取产品周频数据类似），目的是为了将周频数据点都落在周五
    if freq == 'W':
        df = calendar.calender_convertDailyReturnToWeekly(df, 'date', 'adj_return_rate', 'strategy_id')
    df.sort_values(by=['strategy_name', 'date'], ascending=[True, True], inplace=True)
    df.reset_index(inplace=True, drop=True)
    df['data_freq'] = freq
    return df

# ------------------------------------------------------------------------
# 从AMDATA中读取产品层面的收益信息
# ------------------------------------------------------------------------
def custHF_getProductReturn(
    start_date,
    end_date,
    freq,
    product_ids=None,
    Custodian =True,    # If False, it means manually uploaded data.
    include_nav=False   # 是否包含净值
):
    assert freq in ("D", "W"), "数据频率只支持D或者W"
    # 为保证freq为W进行降频时第一周的数据完整准确，需向前多取数据
    aux_start_date = start_date - datetime.timedelta(15)
    conn = irm.irm_connectIRMDB()
    if Custodian:
        sql = "SELECT * FROM irm.V_FUND_VALUE_ORIGINAL WHERE data_source != '人工上传'"
    else:
        sql = "SELECT * FROM irm.V_FUND_VALUE_ORIGINAL WHERE data_source = '人工上传'"

    sql = sql + " and dt >= DATE'{0}' and dt <= DATE'{1}'"
    if product_ids == None:
        ret = pd.read_sql_query(sql.format(aux_start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')), conn).rename(columns=str.lower)
    elif len(product_ids) == 1:
        sql =sql + " and wind_code = {2} "
        sql_format = sql.format(aux_start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'), str('\''+product_ids[0]+'\''))
        ret = pd.read_sql_query(sql_format, conn).rename(columns=str.lower)
    else:
        sql = sql + " and wind_code in {2} "
        ret = pd.read_sql_query(sql.format(aux_start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'), str(tuple(product_ids))), conn).rename(columns=str.lower)
    ret = ret.rename(columns={'dt': 'date', 'secu_nm': 'product_name', 'wind_code': 'product_id', 'source_freq': 'data_freq'})
    ret.sort_values('date', inplace=True)
    # 如果取出了SI区间的收益率，第一个日期的收益率为nan，需去除第一个日期再进行收益计算
    if not include_nav and not ret.empty and (ret['adj_return_rate'].iloc[0] is None or np.isnan(ret['adj_return_rate'].iloc[0])):
        ret = ret[1:]
    columns = ['date', 'product_name', 'product_id', 'adj_return_rate', 'data_freq'] + (['unit_value', 'acm_unit_value'] if include_nav else [])
    ret = ret[columns]
    if freq == 'W':
        #  1. 为应对周频产品数据存在"非周五数据"或"频次略高于周频"的情况,也使用针对日频数据的方式进行降频,直接全量降频处理
        #  2. 当start_date不是周一或一周的起点时，由于aux_start_date向前多取了数据，所选区间的第一周数据完整，降频后返回的第一周的收益率是完整准确的
        ret = calendar.calender_convertDailyReturnToWeekly(ret, date_column_name='date', return_column_name='adj_return_rate', id_column_name='product_id')
    else:
        ret = ret[ret['data_freq'] == 'D']
    ret['date'] = pd.to_datetime(ret['date']).dt.date
    ret.sort_values(by=['product_id', 'date'], ascending=[True, True], inplace=True)
    ret = ret[(ret['date'] >= start_date) & (ret['date'] <= end_date)]  # 截去start_date之前的数据，修正周频模式降频处理时造成的时间戳变化(end_date若在横跨两月的周可能会导致最终数据多出一个月)
    ret['data_freq'] = freq
    conn.close()
    return ret

# ------------------------------------------------------------------------
# 从AMDATA中读取收益信息的wrapper
# ------------------------------------------------------------------------
def custHF_getHFReturn(
    ids,
    start_date,
    end_date,
    freq,
    data_level,        # Strategy or Product
    Custodian =True,    # If False, it means manually uploaded data, ONLY works for Product level
    include_nav=False,
):
    if data_level == 'Strategy':
        level_data = custHF_getStrategyReturn(ids, start_date, end_date, freq)
        level_data.rename(columns={'strategy_id': 'level_id', 'strategy_name': 'level_name'}, inplace=True)
    else:
        level_data = custHF_getProductReturn(start_date, end_date, freq, ids, Custodian=Custodian, include_nav=include_nav)
        level_data.rename(columns={'product_id': 'level_id', 'product_name': 'level_name'}, inplace=True)
    if include_nav == True and data_level == 'Product':
        level_data.rename(columns={'unit_value': '单位净值', 'acm_unit_value': '累计单位净值'}, inplace=True)
    return level_data

# ------------------------------------------------------------------------
# 从AMDATA中读取label信息
# ------------------------------------------------------------------------
def custHF_getLabelInfo():
    conn = irm.irm_connectIRMDB()
    sql_1 = "SELECT DISTINCT label_level_1 FROM irm.STRATEGY_LIST"
    label_1 = pd.read_sql_query(sql_1, conn).rename(columns=str.lower)['label_level_1'].to_list()
    sql_2 = "SELECT DISTINCT label_level_2 FROM irm.STRATEGY_LIST"
    label_2 = pd.read_sql_query(sql_2, conn).rename(columns=str.lower)['label_level_2'].to_list()
    conn.close()
    return label_1, label_2

# ------------------------------------------------------------------------
# 从AMDATA中读取每月A类基金信息
# ------------------------------------------------------------------------
def custHF_getHFMontlyRecommandedData(
    start_date,
    end_date,
    category,
    researcher=None
):
    conn = irm.irm_connectIRMDB()
    sql = "SELECT * FROM irm.SRC_RECOMMEND_STRATEGY WHERE DT >= DATE'{}' AND DT <= DATE'{}' AND STRATEGY_TYPE = '{}'"
    data = pd.read_sql_query(sql.format(str(start_date), str(end_date), category), conn).rename(columns=str.lower)
    data = data[['dt', 'strategy_type', 'strategy_id', 'researcher']]
    data.rename(columns={'dt': 'date', 'strategy_type': 'label'}, inplace=True)
    data['date'] = pd.to_datetime(data['date']).dt.date
    if researcher is None:
        data = data.loc[data['researcher'].isna(), ]
    else:
        data_researcher = data.loc[data['researcher'] == researcher, ]
        data_group = data.loc[(data['researcher'].isna() & ~data['date'].isin(data_researcher['date'])), ]
        data = pd.concat([data_group, data_researcher], axis=0)
    conn.close()
    data['researcher'] = data['researcher'].fillna('小组推荐')
    return data

# ------------------------------------------------------------------------
# 从IRM数据库中获取私募托管净值清洗映射表的情况
# 通过可该表初步判断私募有没有收到净值邮件，收到邮件且且已被解析读取则会在该表中出现
# ------------------------------------------------------------------------
def custHF_getHFCustodianDataIDMapping(
    update_date=None  # 对清洗映射的记录进行筛选，筛出更新日期小于指定日期的记录，默认把所有记录都纳入
):
    conn = irm.irm_connectIRMDB()
    sql = "SELECT * FROM irm.SRC_FUND_CODE_MAP"
    data = pd.read_sql_query(sql, conn).rename(columns=str.lower)
    data = data[['fund_code', 'fund_name', 'associa_code', 'secu_id', 'memo', 'update_time']]
    data.rename(columns={'fund_code': 'product_id_in_email', 'fund_name': 'product_name_in_email', 'associa_code': 'product_id',
                         'secu_id': 'product_id_with_B'}, inplace=True)
    data['product_id'] = data['product_id'].apply(lambda x: x if pd.isna(x) else x+'.OF')
    data['update_time'] = pd.to_datetime(data['update_time']).dt.date
    if update_date is not None:
        data = data[data['update_time'] <= update_date]
    conn.close()
    return data

# -----------------------------------------------------------------------
# 获取有托管监控数据的产品代码
# -----------------------------------------------------------------------
def custHF_getHFCustodianProductList(
        category
):
    assert category in ('主观多头', '量化', 'CTA')
    category_dict = {
        '主观多头':'amdata_src_fund_daily_iservice_stock_new',
        '量化':'amdata_src_fund_daily_iservice_new',
        'CTA':'amdata_src_cta_fund_daily_new'
    }
    conn = irm.irm_connectIRMDB()
    sql="select distinct c_secu_id from irm."+category_dict[category]
    df = pd.read_sql_query(sql, conn)
    df.rename(columns={'c_secu_id': 'product_id'}, inplace=True)
    conn.close()
    return df

# ------------------------------------------------------------------------
# 从IRM数据库中获取策略评级的历史情况
# ------------------------------------------------------------------------
def custHF_getStrategyRatingSnapshot(
    start_date,
    end_date
):
    conn = irm.irm_connectIRMDB()
    sql = "SELECT * FROM irm.AMFOF_FUND_DAILY_SNAPSHOT where strategy_catetory = '私募' and dt >= DATE'{}' and dt <= DATE'{}'"
    data = pd.read_sql_query(sql.format(str(start_date), str(end_date)), conn).rename(columns=str.lower)
    data['date'] = pd.to_datetime(data['dt']).dt.date
    conn.close()
    return data


# ------------------------------------------------------------------------
# 从CAMP数据库获取私募产品具体可以交易份额的对应ID
# ID命名规则符合CAMP模板导入的要求，可通过生成excel的形式提升交易指令录入效率
# 目前可能会存在协会ID对应具体份额ID一对多的情况
# 例如量派信选CTA五号SAGN44 AC份额都理论上都可投（单笔1000万走C份额），目前在网页端提示投资经理注意
# ------------------------------------------------------------------------
@st.cache_data(ttl=7200, show_spinner=False)
def custHF_getProductCAMPIDWithShareType():
    amdata_conn = amdata.amdata_connectAmdataDb()
    sql = "SELECT ASSOCIATION_RECORD_NUMBER product_id, STKCODE product_camp_id_with_share_type FROM CAMP.FUND_MATERIAL@CAMP"
    product_id_mapping = pd.read_sql_query(sql, amdata_conn).rename(columns=str.lower)
    product_id_mapping['product_id'] = product_id_mapping['product_id'].apply(lambda x: str(x) + '.OF')
    # 匹配后的代码也需加上.OF，避免产品有多个份额时CAMP识别报错
    product_id_mapping['product_camp_id_with_share_type'] = product_id_mapping['product_camp_id_with_share_type'].apply(lambda x: str(x) + '.OF')
    return product_id_mapping


# ------------------------------------------------------------------------
# 从CAMP数据库获取私募产品的合同有效期等信息
# 可通过该数据获取未备案的私募产品，用于加入交易试算备选产品列表
# ------------------------------------------------------------------------
def custHF_getProductContractInfoFromCAMP():
    amdata_conn = amdata.amdata_connectAmdataDb()
    sql = "SELECT ASSOCIATION_RECORD_NUMBER product_id, FUND_NAME product_short_name, EFFECTIVE_DEADLINE contract_expiration_date FROM CAMP.FUND_MATERIAL@CAMP"
    product_contract_info = pd.read_sql_query(sql, amdata_conn).rename(columns=str.lower)
    product_contract_info['product_id'] = product_contract_info['product_id'].apply(lambda x: str(x) + '.OF')
    product_contract_info['contract_expiration_date'] = pd.to_datetime(product_contract_info['contract_expiration_date']).dt.date
    product_contract_info = product_contract_info[~pd.isnull(product_contract_info['contract_expiration_date'])]
    product_contract_info = product_contract_info.sort_values('contract_expiration_date', ascending=False)
    return product_contract_info
