# ------------------------------------------------------
# 本文档用于从Wind WDS数据库读取并缓存产品、指数等数据
# ------------------------------------------------------
import pandas as pd
import datetime
from dateutil.relativedelta import relativedelta
import src.utils.fof_calendar as fof_calendar
import src.data.wind as wind
import src.data.irm as irm
import src.const as const

# --------------------------------------------------------------------
# 获取wind的自建基金指数的成份
# 由于目前wind只提供当前最新成份，故需周期性缓存以供追溯
# 等权处理的指数，成份的product_weight为None
# --------------------------------------------------------------------
def wind_getWindMFIndexComponent(
    index_id,   # wind指数id, 目前支持885000普通股票型 885001偏股混 885005债券型 885007混合债券二级 885008中长期纯债型
):
    assert index_id in ('885000.WI', '885001.WI', '885005.WI', '885007.WI', '885008.WI'), "目前只支持部分wind基金指数：'885000.WI', '885001.WI', '885005.WI', '885007.WI', '885008.WI'"
    # 所选index_id与CFundWindIndexMembers（指数最新成分）表中板块代码的对应关系
    sector_code_map = {
        '885000.WI': {'index_name': '万得普通股票型基金指数', 'sector_code': 'a201060301000000'},
        '885001.WI': {'index_name': '万得偏股混合型基金指数', 'sector_code': 'a201060302000000'},
        '885005.WI': {'index_name': '万得债券型基金指数', 'sector_code': 'a201060306000000'},
        '885007.WI': {'index_name': '万得混合债券型二级基金指数', 'sector_code': 'a201060308000000'},
        '885008.WI': {'index_name': '万得中长期纯债型基金指数', 'sector_code': 'a201060309000000'},
    }
    dbconn = wind.wind_connectWindDB()
    sql = "select s_con_code, s_con_name, s_info_windcode from CFundWindIndexMembers where S_CON_CODE = '{}'"
    component = pd.read_sql_query(sql.format(sector_code_map[index_id]['sector_code']), dbconn)
    del component['s_con_code'], component['s_con_name']
    component.rename(columns={'s_info_windcode': 'product_id'}, inplace=True)
    # date即数据日期，为当前日期
    component['date'] = datetime.date.today()
    component['data_source'] = 'wind'
    component['index_id'] = index_id
    component['index_name'] = sector_code_map[index_id]['index_name']
    component['product_weight'] = None
    component = component[['date', 'data_source', 'index_id', 'index_name', 'product_id', 'product_weight']]
    dbconn.close()
    return component

# --------------------------------------------------------------------
# 获取wind中长期纯债指数基于下列条件筛选后所得到的成份
# 筛选条件：估值-市值法，规模-2亿以上，份额-A份额即初始基金，没有最短持有期，非定开
# 因为885008本身的成份即进行了成立3个月以上的筛选，故对成份的基金成立时间不再做筛选
# --------------------------------------------------------------------
def wind_getCustomizedBondBMComponent():
    '''
    1. 首先筛出中长期纯债指数的成分 CFundWindIndexMembers（wind只提供最新数据）
    2. 估值方法代码：CFundPchRedm F_INFO_VALMETCODE 663006001: 摊余成本法 663006002: 市值法
    3. 最短持有期(月)：F_MINM_HOLDING_PRD
    4. 定期开放基金（反向选择）：中国Wind基金分类[ChinaMutualFundSector].S_INFO_SECTOR =‘2001020e00’, ChinaMutualFundSector 基金所属概念板块，是一对多的结构，不能进行直接的反选，故取出数据后再去除有定开的基金
    5. A份额（初始基金）：F_INFO_ISINITIAL = 1
    6. 规模数据：ChinaMutualFundNAV(中国共同基金净值)
    CUR_SIGN = 1, 基金分类是最新的，避免重复计算
    '''
    dbconn = wind.wind_connectWindDB()
    sql_1 = "select a.S_INFO_WINDCODE as product_id, c.F_INFO_NAME as product_name ,c.F_INFO_CORP_FUNDMANAGEMENTCOMP as company_short_name, " \
            "b.S_INFO_SECTOR as sector_id, d.F_MINM_HOLDING_PRD as min_holding_period, d.F_INFO_VALMETCODE as valuation_method_id " \
            "from (CFundWindIndexMembers)a, (ChinaMutualFundSector)b, (ChinaMutualFundDescription)c, (CFundPchRedm)d " \
            "where a.S_CON_CODE = 'a201060309000000' and a.S_INFO_WINDCODE=c.F_INFO_WINDCODE and a.S_INFO_WINDCODE=b.F_INFO_WINDCODE " \
            "and a.S_INFO_WINDCODE=d.F_INFO_WINDCODE and b.CUR_SIGN = 1 and c.F_INFO_ISINITIAL = 1 "
    component = pd.read_sql_query(sql_1, dbconn)
    component = component[(component['valuation_method_id'] == 663006002) & (component['min_holding_period'].isnull())]
    regular_open_component = component[component['sector_id'] == '2001020e00']
    component = component[~component['product_id'].isin(regular_open_component['product_id'].tolist())]
    del component['sector_id'], component['valuation_method_id'], component['min_holding_period']
    # 目前得到的是所需component数据的sector（所属风格）信息，是一对多的结构所以product_id等基础信息有重复，去重后进行后面的操作
    component = component.drop_duplicates()
    # 除了规模的筛选条件，其他都已筛选完成，下面取最新规模
    year = str(datetime.date.today().year - 1)  # 优化取数速度
    sql_2 = "select PRICE_DATE as trade_date, F_INFO_WINDCODE as product_id, NETASSET_TOTAL as aum from ChinaMutualFundNAV " \
            "where NETASSET_TOTAL is not null and PRICE_DATE >= '" + year + "0101'"
    aum = pd.read_sql_query(sql_2, dbconn)
    aum = aum.sort_values('trade_date').groupby(['product_id'], as_index=False)['aum'].last()
    component = pd.merge(component, aum, on='product_id', how='left')
    component = component[component['aum'] >= 2e8].reset_index(drop=True)
    dbconn.close()
    component['data_date'] = datetime.date.today()
    return component

# ----------------------------------------------------------------------------
# 基于当前可获取的wind中长期纯债指数成份基于下列条件筛选，再合并重新等权合并为定制指数的收益率
# 筛选条件：估值-市值法，规模-2亿以上，份额-A份额即初始基金，没有最短持有期，非定开
# ----------------------------------------------------------------------------
def wind_calCustomizedBondBMReturn(
    start_date, # 起始日期
    end_date,   # 截止日期，返回起止之间的交易日
):
    index_component = wind_getCustomizedBondBMComponent()
    aux_start_date = start_date - datetime.timedelta(15)
    nav = wind.wind_getMFNav(aux_start_date, end_date, index_component.product_id.tolist())
    nav_pivot = nav.pivot(columns='product_id', index='date', values='nav_adjusted')
    # wind 公募数据的特性：有分红事件、有季度报告时，无论是不是交易日，都会补上当天的收益和净值数据，这会对合并计算、超额的计算造成影响
    # 故使用交易日历filter复权净值之后再计算收益率
    wind_calendar = wind.wind_getSSECalendar()
    nav_pivot = nav_pivot[nav_pivot.index.isin(wind_calendar['date'].tolist())]
    ret_pivot = nav_pivot.pct_change()
    ret_pivot['index_return'] = ret_pivot.mean(axis=1)
    index_ret = pd.DataFrame(ret_pivot[ret_pivot.index >= start_date]['index_return']).reset_index()
    index_ret['index_id'] = '885008.CUSTOMIZED'
    index_ret['index_name'] = '定制-中长期纯债型基金指数'
    index_ret['freq'] = 'D'
    return index_ret

# ------------------------------------------------------------------------------
# 取数接口 - 获取缓存的定制基金指数每日收益表现，目前只支持定制的中长期纯债基金指数，支持日频周频
# ------------------------------------------------------------------------------
def windCached_getCustomizedIndexReturn(
    index_id,       # 定制指数的id，目前只支持885008.CUSTOMIZED
    start_date,     # 起始日期
    end_date,       # 截止日期，返回起止之间的交易日的数据
    freq='D',       # 数据频率，默认为D
):
    assert index_id in ('885008.CUSTOMIZED', 'CTA_MANAGER_INDEX_01.CUSTOMIZED'), "提示: 目前仅支持定制化万得纯债基金指数，定制CTA管理人指数。"
    assert freq in ('D', 'W')
    if index_id == 'CTA_MANAGER_INDEX_01.CUSTOMIZED':
        assert freq == 'W', 'CTA_MANAGER_INDEX_01.CUSTOMIZED定制CTA管理人指数仅支持W'
    conn = irm.irm_connectIRMDB()
    sql = "SELECT * FROM irm.AMFOF_CUSTOMIZED_INDEX_RETURN WHERE dt >= DATE'{0}' and dt <= DATE'{1}' and index_id = '{2}' "
    index_ret = pd.read_sql_query(sql.format(start_date, end_date, index_id), conn)
    rename_mapping = {'DT': 'date', 'DATA_SOURCE': 'data_source', 'INDEX_ID': 'index_id', 'INDEX_NAME': 'index_name', 'INDEX_RETURN': 'index_return',
                      'DATA_FREQ': 'freq'}
    index_ret.rename(columns=rename_mapping, inplace=True)
    index_ret = index_ret[list(rename_mapping.values())]
    conn.close()
    if freq == 'W':
        index_ret = fof_calendar.calender_convertDailyReturnToWeekly(index_ret, 'date', 'index_return', 'index_id')
        index_ret['freq'] = 'W'
    return index_ret

# -----------------------------------------------------------------------------
# 取数接口 - 获取缓存的定制基金指数的净值曲线，目前只支持定制的中长期纯债基金指数，支持日频周频
# -----------------------------------------------------------------------------
def windCached_getCustomizedIndexNav(
    index_id,       # 定制指数的id，目前只支持885008.CUSTOMIZED
    start_date,     # 起始日期
    end_date,       # 截止日期，返回起止之间的交易日的数据
    freq='D',       # 数据频率，默认为D
):
    assert index_id in ('885008.CUSTOMIZED', 'CTA_MANAGER_INDEX_01.CUSTOMIZED'), "提示: 目前仅支持定制化万得纯债基金指数，定制CTA管理人指数。"
    assert freq in ('D', 'W')
    if index_id == 'CTA_MANAGER_INDEX_01.CUSTOMIZED':
        assert freq == 'W',  'CTA_MANAGER_INDEX_01.CUSTOMIZED定制CTA管理人指数仅支持W'

    ret_result = windCached_getCustomizedIndexReturn(index_id, start_date, end_date, freq)
    nav_result = ret_result.pivot_table(index='date', values='index_return', columns='index_id')
    nav_result = (nav_result.fillna(0) + 1).cumprod(axis=0)
    nav_result.loc[nav_result.index[0]-datetime.timedelta(days=const.const.FREQ_INTERVAL[freq])] = 1
    nav_result.reset_index(inplace=True)
    nav_result = nav_result.sort_values(by='date').reset_index(drop=True).rename(columns={index_id: 'nav'})
    nav_result['index_id'] = index_id
    return nav_result

# ----------------------------------------------------------------------------
# 取数接口 - 获取月度缓存的wind自建基金指数的成份
# 由于目前wind只提供当前最新成份，故需周期性缓存以供追溯
# ----------------------------------------------------------------------------
def windCached_getWindMFIndexComponent(
    index_id,       # wind指数id, 目前支持885000普通股票型 885001偏股混 885005债券型 885007混合债券二级 885008中长期纯债型
    start_date,     # 起始日期
    end_date,       # 截止日期，返回起止之间缓存的数据，一般每月只缓存一次
):
    assert index_id in ('885000.WI', '885001.WI', '885005.WI', '885007.WI', '885008.WI'), "目前只支持部分wind基金指数：'885000.WI', '885001.WI', '885005.WI', '885007.WI', '885008.WI'"

    conn = irm.irm_connectIRMDB()
    sql = "SELECT * FROM irm.AMFOF_THIRD_PARTY_INDEX_COMPONENT WHERE dt >= DATE'{0}' and dt <= DATE'{1}' and index_id = '{2}' "
    index_component = pd.read_sql_query(sql.format(start_date, end_date, index_id), conn)
    rename_mapping = {'DT': 'date', 'DATA_SOURCE': 'data_source', 'INDEX_ID': 'index_id', 'INDEX_NAME': 'index_name', 'PRODUCT_ID': 'product_id',
                      'PRODUCT_WEIGHT': 'product_weight', 'UPDATE_FREQ': 'update_freq'}
    index_component.rename(columns=rename_mapping, inplace=True)
    index_component = index_component[list(rename_mapping.values())]
    conn.close()
    return index_component


####################################################################
# WRITE API
####################################################################

# ----------------------------------------------------------------------------
# 缓存定制化的wind基金指数每日收益表现，目前只支持中长期纯债指数的定制
# 基于当前可获取的wind中长期纯债指数成份基于下列条件筛选，再合并重新等权合并为定制指数的收益率
# 筛选条件：估值-市值法，规模-2亿以上，份额-A份额即初始基金，没有最短持有期，非定开
# ----------------------------------------------------------------------------
def wind_cacheCustomizedIndexReturn(
    index_id,  # 定制指数的id，目前只支持885008.CUSTOMIZED
    start_date, # 起始日期
    end_date,   # 截止日期，返回起止之间的交易日
    insert=False,   # 默认不存入数据库
):
    assert index_id in ('885008.CUSTOMIZED'), "提示: 目前仅支持运行定制化万得纯债基金指数。"
    index_func_map = {
        '885008.CUSTOMIZED': wind_calCustomizedBondBMReturn
    }
    index_ret = index_func_map[index_id](start_date, end_date)
    index_ret['data_source'] = 'wind'
    index_ret['update_time'] = datetime.date.today()
    index_ret = index_ret.rename(columns={'date': 'dt', 'freq': 'data_freq'})
    index_ret = index_ret[['dt', 'data_source', 'index_id', 'index_name', 'index_return', 'data_freq', 'update_time']]

    if insert:
        # 如果重复日期数据
        conn = irm.irm_connectIRMDB()
        sql = "DELETE FROM irm.AMFOF_CUSTOMIZED_INDEX_RETURN WHERE dt >= DATE'{0}' and dt <= DATE'{1}' and index_id = '{2}' "
        sql = sql.format(start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'), index_id)
        cur = conn.cursor()
        cur.execute(sql)
        conn.commit()

        # 写入数据库
        irm.irm_insertIRMData(index_ret, 'irm.AMFOF_CUSTOMIZED_INDEX_RETURN')

    return index_ret

# ----------------------------------------------------------------------------
# 缓存wind的自建基金指数的成份
# 由于目前wind只提供当前最新成份，故需周期性缓存以供追溯
# 等权处理的指数，成份的product_weight为None
# ----------------------------------------------------------------------------
def wind_cacheWindMFIndexComponent(
    index_id,       # wind指数id, 目前支持885000普通股票型 885001偏股混 885005债券型 885007混合债券二级 885008中长期纯债型
    insert=False,   # 默认不存入数据库
):
    assert index_id in ('885000.WI', '885001.WI', '885005.WI', '885007.WI', '885008.WI'), "目前只支持部分wind基金指数：'885000.WI', '885001.WI', '885005.WI', '885007.WI', '885008.WI'"

    component = wind_getWindMFIndexComponent(index_id)
    component['update_freq'] = 'M'
    component['update_time'] = datetime.date.today()
    component = component.rename(columns={'date': 'dt'})
    component = component[['dt', 'data_source', 'index_id', 'index_name', 'product_id', 'product_weight', 'update_freq', 'update_time']]

    if insert:
        # 如果重复日期数据
        conn = irm.irm_connectIRMDB()
        sql = "DELETE FROM irm.AMFOF_THIRD_PARTY_INDEX_COMPONENT WHERE dt = DATE'{0}' and index_id = '{1}' "
        sql = sql.format(datetime.date.today().strftime('%Y-%m-%d'), index_id)
        cur = conn.cursor()
        cur.execute(sql)
        conn.commit()

        # 写入数据库
        irm.irm_insertIRMData(component, 'irm.AMFOF_THIRD_PARTY_INDEX_COMPONENT')

    return component

