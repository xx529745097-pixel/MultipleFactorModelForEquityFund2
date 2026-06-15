import pandas as pd
import numpy as np
import datetime
import streamlit as st
import src.const as const
import src.config as config
import src.data.amdata as amdata
import src.data.irm as irm
import src.data.wind as wind
import src.utils.fof_calendar as calendar
import src.utils.Calculation as cal
from dateutil.relativedelta import relativedelta
import src.utils.userIdentify as userIdentify

# ------------------------------------------------------
# 从数据库读取FOF产品列表 - 辅助私有函数,输入日期向前推17个自然日，区间数据取并集
# 该函数使用streamlit内置缓存装饰器，每48小时只需全局计算一次，剩下时段均可以调用缓存数据作为网页前端备选项，提升用户体验
# ------------------------------------------------------
@st.cache_data(ttl=172800)
def _getFOFProductList(
    date=datetime.date.today()
):
    start_date = date-datetime.timedelta(28)
    amdata_conn = amdata.amdata_connectAmdataDb()
    #  to_char(data_dt, 'D')=6 代表取周五数据
    sql = "SELECT DISTINCT A6_FUNDID, prtfl_sim_nm FROM AMFOF.V_FOF_HOLDING_INFO WHERE data_dt >= DATE'{0}' AND data_dt <= DATE'{1}' and to_char(data_dt, 'D')=6"
    holding_ret = pd.read_sql_query(sql.format(start_date.strftime('%Y-%m-%d'), date.strftime('%Y-%m-%d')), amdata_conn)
    holding_ret.rename(columns={'A6_FUNDID': 'portfolio_id', 'PRTFL_SIM_NM': 'portfolio_name'}, inplace=True)
    amdata_conn.close()
    return holding_ret

# ------------------------------------------------------
# 从数据库读取FOF持仓数据
# ------------------------------------------------------
def custFOF_getFOFHoldingData(
    start_date,
    end_date,
    portfolio_id=None,  # 传入list形式
    include_portfolio_oa_id=False   # 返回数据是否包含PRTFL_ID字段，标记为portfolio_oa_id，默认不包含，部分投顾产品A6_FUNDID为None
                                    # 同时也会返回持仓数据中资产总值、产品占资产总值，用于归因模型使用，其他情景默认不包含
):
    assert (type(start_date) == datetime.date), '日期输入格式需为datetime.date'
    assert (type(end_date) == datetime.date), '日期输入格式需为datetime.date'
    amdata_conn = amdata.amdata_connectAmdataDb()

    if portfolio_id is not None:
        # 取标准组合的持仓（展示为一个正常账户的格式）
        if set(portfolio_id) <= set(const.const.STANDARD_PORT_ID_LIST):
            ret = const.const.STANDARD_PORT_COMPONENT_CONFIG[const.const.STANDARD_PORT_COMPONENT_CONFIG['standard_port_id'].isin(portfolio_id)]
            ret = ret[['standard_port_id', 'standard_port_name', 'component_id', 'component_name', 'component_weight']]
            ret.rename(columns={'standard_port_id': 'portfolio_id', 'standard_port_name': 'portfolio_name',
                                'component_id': 'product_id', 'component_name': 'product_name', 'component_weight': 'product_weight'}, inplace=True)
            ret['product_type'] = '私募基金'
            ret['NAV'] = 1e8
            ret['product_NAV'] = ret['NAV'] * ret['product_weight']
            ret['date'] = end_date
            return ret
        else:
            # FIXME portfolio_id替换升级项目 添加PRTFL_ID临时映射 暂未解决投顾账户缺失A6ID的情况
            prtfl_id_mapping_sql = "SELECT * FROM AMFOF.SRC_FOF_ACCT_LABEL"
            ref_data = pd.read_sql_query(prtfl_id_mapping_sql, amdata_conn).rename(columns=str.lower)
            portfolio_oa_ids = ref_data[ref_data['a6_fundid'].isin(portfolio_id)]['prtfl_id'].to_list()

            sql = "SELECT * FROM AMFOF.V_FOF_HOLDING_INFO WHERE data_dt >= DATE'{0}' and data_dt <= DATE'{1}' and PRTFL_ID in ({2})"
            ret = pd.read_sql_query(sql.format(start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'), ','.join(["'%s'" % port_oa_id for port_oa_id in portfolio_oa_ids])), amdata_conn)
    else:
        sql = "SELECT * FROM AMFOF.V_FOF_HOLDING_INFO WHERE data_dt >= DATE'{0}' and data_dt <= DATE'{1}'"
        ret = pd.read_sql_query(sql.format(start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')), amdata_conn)
    amdata_conn.close()
    ret['DATA_DT'] = pd.to_datetime(ret['DATA_DT']).dt.date
    ret['START_DT'] = pd.to_datetime(ret['START_DT']).dt.date
    del ret['TOT_EXPENSE'], ret['INTEREST_EXPENSE'], ret['TOT_INCOME'], ret['BUY_AMT'], ret['BUY_VOL'], ret['SALE_AMT'], ret['SALE_VOL']
    # FIXME!!! ################################################################################
    # 数据库新加入了LATEST_TOT_VAL、HOLDING_WEIGHT_TOT两列用于holding比例的精确计算，目前先一起project掉
    if not include_portfolio_oa_id:
        del ret['PRTFL_ID'], ret['LATEST_TOT_VAL'], ret['HOLDING_WEIGHT_TOT'], ret['PRINCIPAL']
    ret.rename(columns={'A6_FUNDID': 'portfolio_id', 'PRTFL_ID':'portfolio_oa_id', 'PRTFL_SIM_NM': 'portfolio_name', 'START_DT': 'inception_date', 'LATEST_NET_VAL': 'NAV',
                        'LATEST_TOT_VAL': 'total_NAV', 'HOLDING_WEIGHT_TOT': 'total_product_weight', 'DATA_DT': 'date', 'SECU_ID': 'product_id', 'SECU_NM': 'product_name',
                        'SECU_TYPE': 'product_type', 'HOLDING_WEIGHT': 'product_weight', 'VOLUME': 'product_volume', 'PRINCIPAL': 'total_share', 'ACCR_INTEREST': 'product_accu_interest',
                        'TOT_RETURN': 'product_daily_ret', 'FLOAT_RETURN': 'product_daily_float_ret', 'REALIZED_RETURN': 'product_daily_realized_ret',
                        'DVND_RETURN': 'product_daily_dividend', 'INTEREST_RETURN': 'product_daily_interest'}, inplace=True)
    ret['product_NAV'] = ret['NAV'] * ret['product_weight']
    # FIXME AMDATA的持仓数据源目前会将全部赎回的产品在确认日当日还留在持仓数据中，持仓金额为0，目的是保留更多交易相关的浮盈浮亏数据
    # 这类为0的数据从持仓的角度来说无实际意义，还会影响归因模型的计算，故直接进行筛选
    ret = ret[ret['product_NAV'] != 0]
    return ret

# ------------------------------------------------------
# 从AMFOF读取FOF历史持仓产品列表，定期缓存自holding data
# ------------------------------------------------------
def custFOF_getFOFHistoricalHoldingProduct(
    start_date,
    end_date,
    include_holding_dates=True  # 默认包含持仓日期列
):
    assert isinstance(start_date, datetime.date), '日期输入格式需为datetime.date'
    assert isinstance(end_date, datetime.date), '日期输入格式需为datetime.date'
    conn = irm.irm_connectIRMDB()
    if include_holding_dates:
        sql = "SELECT * FROM irm.AMFOF_HOLDING_PRODUCT_LIST a WHERE a.date >= DATE'{0}' AND a.date <= DATE'{1}' "
    else:
        sql = "SELECT DISTINCT a.product_id, a.product_name FROM irm.AMFOF_HOLDING_PRODUCT_LIST a WHERE a.date >= DATE'{0}' AND a.date <= DATE'{1}' "
    result = pd.read_sql_query(sql.format(start_date, end_date), conn)
    conn.close()
    return result

# ------------------------------------------------------
# 从数据库读取FOF投资标的类型列表
# ------------------------------------------------------
def custFOF_getProductTypeList():
    date = datetime.date.today() - datetime.timedelta(days=datetime.date.today().weekday() + 10)  # 获取周五的数据，速度优化
    amdata_conn = amdata.amdata_connectAmdataDb()
    sql = "SELECT DISTINCT secu_type FROM AMFOF.V_FOF_HOLDING_INFO WHERE data_dt = DATE'{0}'"
    ret = pd.read_sql_query(sql.format(date.strftime('%Y-%m-%d')), amdata_conn)
    amdata_conn.close()
    data_list = ret['SECU_TYPE'].to_list()
    return data_list

# ------------------------------------------------------
# 从数据库读取FOF产品列表作为网页前端备选项
# 该函数所调用的_getFOFProductList使用streamlit内置缓存装饰器，
# 每48小时只需全局计算一次，剩下时段均可以调用缓存数据作为网页前端备选项，提升用户体验
# ------------------------------------------------------
def custFOF_getFOFProductList(
    portfolio_type=None,    # FOF产品线类型，传入None或者dict. 传入None时不加筛选取所有有持仓的FOF产品ID+NAME；
                            # 传入dict时必须key包含level_1_type, level_2_type, level_3_type, management_type, 分别对应一级标签、二级标签、三级标签、管理类型,
                            # 传入dict的value可以为list或者None，为None时对应的级别不做筛选
    user_permission_setting=True,   # 是否加入母子公司权限限制。研究类内容不限制置为False。具体账户持仓和交易置为True.此函数的场景默认为True
    date=datetime.date.today()
):
    ret = custFOF_getFOFReferenceData(portfolio_type=portfolio_type, include_advisory_account=True, user_permission_setting=user_permission_setting)
    ret = ret[['portfolio_id', 'portfolio_name']]
    # FIXME 持仓数据全量读取某几天时速度过慢，暂时优化以下代码
    # if portfolio_type == None:
    #     holding_ret = _getFOFProductList(date)
    #     ret = ret[ret['portfolio_id'].isin(holding_ret['portfolio_id'].tolist())]
    return ret

# ------------------------------------------------------
# 从数据库读取FOF类型列表
# ------------------------------------------------------
def custFOF_getFOFTypeList():
    amdata_conn = amdata.amdata_connectAmdataDb()
    sql = "SELECT DISTINCT fof_acct_type FROM AMFOF.SRC_FOF_ACCT_LABEL"
    ret = pd.read_sql_query(sql, amdata_conn)
    amdata_conn.close()
    data_list = ret['FOF_ACCT_TYPE'].to_list()
    return data_list

# ------------------------------------------------------
# 从数据库读取FOF类型列表:一级、二级、三级分类和管理类型
# ------------------------------------------------------
def custFOF_getFOFProductLineFilter():
    amdata_conn = amdata.amdata_connectAmdataDb()
    sql = "SELECT DISTINCT FOF_ACCT_CLASS1, FOF_ACCT_CLASS2, FOF_ACCT_CLASS3,ACCT_MANAGE_TYPE FROM AMFOF.SRC_FOF_ACCT_LABEL"
    ret = pd.read_sql_query(sql, amdata_conn)
    amdata_conn.close()
    level_1_type = (list(set(ret['FOF_ACCT_CLASS1'].to_list()) - {None}) + ['空值']) if None in ret['FOF_ACCT_CLASS1'].to_list() else list(set(ret['FOF_ACCT_CLASS1'].to_list()))
    level_2_type = (list(set(ret['FOF_ACCT_CLASS2'].to_list()) - {None}) + ['空值']) if None in ret['FOF_ACCT_CLASS2'].to_list() else list(set(ret['FOF_ACCT_CLASS2'].to_list()))
    level_3_type = (list(set(ret['FOF_ACCT_CLASS3'].to_list()) - {None}) + ['空值']) if None in ret['FOF_ACCT_CLASS3'].to_list() else list(set(ret['FOF_ACCT_CLASS3'].to_list()))
    management_type = (list(set(ret['ACCT_MANAGE_TYPE'].to_list()) - {None}) + ['空值']) if None in ret['ACCT_MANAGE_TYPE'].to_list() else list(set(ret['ACCT_MANAGE_TYPE'].to_list()))
    return {'level_1_type': level_1_type, 'level_2_type': level_2_type, 'level_3_type': level_3_type, 'management_type': management_type}

# ------------------------------------------------------
# 从数据库读取FOF投资经理列表
# ------------------------------------------------------
def custFOF_getFOFPMList():
    amdata_conn = amdata.amdata_connectAmdataDb()
    sql = "SELECT DISTINCT investor FROM AMFOF.SRC_FOF_ACCT_LABEL"
    ret = pd.read_sql_query(sql, amdata_conn)
    amdata_conn.close()
    data_list = ret['INVESTOR'].to_list()
    pm_list = list(set(sum([pm.split(',') for pm in data_list if pm is not None], [])))  # 得到互斥的、不含None的全量单人列表
    return pm_list

# ------------------------------------------------------
# 从数据库读取FOF客户区域(分公司)列表
# ------------------------------------------------------
def custFOF_getFOFClientRegionList():
    amdata_conn = amdata.amdata_connectAmdataDb()
    sql = "SELECT DISTINCT CUST_REGION FROM AMFOF.SRC_FOF_ACCT_LABEL"
    ret = pd.read_sql_query(sql, amdata_conn)
    amdata_conn.close()
    client_region_list = (list(set(ret['CUST_REGION'].to_list()) - {None}) + ['空值']) if None in ret['CUST_REGION'].to_list() else list(set(ret['CUST_REGION'].to_list()))
    return client_region_list

# ------------------------------------------------------
# 获取底层资产具体标签列表
# ------------------------------------------------------
def custFOF_getUnderlyingLabelInfo(type):
    assert type in const.const.WEB_SECTOR_TYPE_LIST.values(), '目前该类型不支持'
    amdata_conn = amdata.amdata_connectAmdataDb()
    irm_conn = irm.irm_connectIRMDB()
    if type == 'product_type':
        date = datetime.date.today() - datetime.timedelta(days=datetime.date.today().weekday() + 17)
        sql = "SELECT DISTINCT SECU_TYPE FROM AMFOF.V_FOF_HOLDING_INFO WHERE data_dt = DATE'{0}'"
        data = pd.read_sql_query(sql.format(date.strftime('%Y-%m-%d')), amdata_conn)
        ret = data['SECU_TYPE'].to_list()
    elif type == 'label_level_1':
        amdata_conn = amdata.amdata_connectAmdataDb()
        sql_1 = "SELECT DISTINCT LABEL_LEVEL_1 FROM irm.STRATEGY_LIST"
        sql_2 = "SELECT DISTINCT LABEL_LEVEL_1 FROM irm.MF_STRATEGY_LIST"
        data = pd.concat([pd.read_sql_query(sql_1, irm_conn), pd.read_sql_query(sql_2, irm_conn)], axis=0)
        ret = data['LABEL_LEVEL_1'].unique().tolist()

    elif type == 'label_level_2':
        sql_1 = "SELECT DISTINCT LABEL_LEVEL_2 FROM irm.STRATEGY_LIST"
        sql_2 = "SELECT DISTINCT LABEL_LEVEL_2 FROM irm.MF_STRATEGY_LIST"
        data = pd.concat([pd.read_sql_query(sql_1, irm_conn), pd.read_sql_query(sql_2, irm_conn)], axis=0)
        ret = data['LABEL_LEVEL_2'].unique().tolist()
        ret.remove(None)
    else:
        ret = const.const.ALLOCATION_TYPE_LIST
    amdata_conn.close()
    irm_conn.close()
    return ret

# ------------------------------------------------------
# 读取FOF产品的附属信息
# portfolio_type下的各级list以及client_region的list可能会包含'空值'字段，应将其转化为[None]再去筛选
# ------------------------------------------------------
def custFOF_getFOFReferenceData(
    pm_name=None,
    portfolio_type=None,    # FOF产品线类型，传入None或者dict. 传入None时不加筛选取所有FOF产品信息；
                            # 传入dict时必须key包含level_1_type, level_2_type, level_3_type, management_type, 分别对应一级标签、二级标签、三级标签、管理类型,
                            # 传入dict的value可以为list或者None，为None时对应的级别不做筛选
    client_region=None,     # 客户区域(分公司)信息筛选, 传入list或者None, 默认为None不筛选
    include_advisory_account=False,     # 是否加入投顾账户
    read_aum=False,                     # 调节是否加入动态数据, 仅TOT_NET_VAL为动态数据
    include_additional_info=False,      # 是否加入附加信息列，默认为否。目前附加信息列包含benchmark_id列和freq列
                                        # benchmark_id列：如果FOF账户具有benchmark则显示FOF_BM，否则为None
                                        # freq列：是否加入数据频率标识列，添加后freq列展示FOF账户净值数据频率，目前投顾账户为W，其他为D
                                        # advisory_or_not列：是否为投顾账户，True or False
    user_permission_setting=False,      # 是否加入母子公司权限限制。对于研究类内容，不设限制置为False。对于具体账户持仓和交易信息，置为True
    include_portfolio_oa_id=False,      # 返回数据是否包含PRTFL_ID字段，标记为portfolio_oa_id，默认不包含， 部分投顾产品A6_FUNDID为None,可采用PRTFL_ID字段代表产品
    include_all_portfolio_status=False  # 回看历史账户数据时方便纳入当时未清算的账户
):
    if pm_name == '全部':
        pm_name = None
    if portfolio_type is not None:
        assert set(portfolio_type.keys()) == {'level_1_type', 'level_2_type', 'level_3_type', 'management_type'}, \
                "portfolio_type传入字典时, key必须包含level_1_type, level_2_type, level_3_type, management_type四类"
    amdata_conn = amdata.amdata_connectAmdataDb()
    sql = "SELECT * FROM AMFOF.SRC_FOF_ACCT_LABEL"
    ret = pd.read_sql_query(sql, amdata_conn)
    amdata_conn.close()
    ret.rename(columns={'A6_FUNDID': 'portfolio_id', 'PRTFL_ID':'portfolio_oa_id', 'PRTFL_SIM_NM': 'portfolio_name', 'ACCT_STATUS_DESC': 'portfolio_status',
                        'CUST_REGION': 'client_region', 'CO_DEPT': 'client_office', 'CUST_MGR': 'client_manager', 'CUST_TYPE': 'client_type',
                        'CUST_NAME': 'client_name', 'FOF_ACCT_TYPE': 'portfolio_type', 'INVESTOR': 'pm_name',
                        'START_DATE': 'inception_date', 'DATA_DATE': 'date', 'PRINCIPAL': 'initial_funding', 'TOT_NET_VAL': 'AUM', 'BASELINE': 'benchmark',
                        'FOF_ACCT_CLASS1': 'level_1_type', 'FOF_ACCT_CLASS2': 'level_2_type', 'FOF_ACCT_CLASS3': 'level_3_type','ACCT_MANAGE_TYPE': 'management_type',
                        'BELONGED_COMPANY': 'branch_company', 'FOF_KPI_TYPE': 'kpi_type'
                        }, inplace=True)
    if read_aum:
        del ret['date']
    else:
        del ret['AUM'], ret['date'] # 这个信息我们目前从custFOF_getFOFHoldingData()获取
    if include_advisory_account:
        # 使用产品套账号的编码格式来判断是否为投顾（最直接精准的方法）
        ret = ret if include_all_portfolio_status else ret[(ret['portfolio_status'].isin(['正常运作'])) | (ret['portfolio_oa_id'].str.startswith('VIR_C'))]
    else:
        ret = ret[(~ret['portfolio_oa_id'].str.startswith('VIR_C'))] if include_all_portfolio_status else ret[ret['portfolio_status'].isin(['正常运作']) & (~ret['portfolio_oa_id'].str.startswith('VIR_C'))]
    ret['inception_date'] = pd.to_datetime(ret['inception_date']).dt.date
    if pm_name is not None:
        ret = ret[ret['pm_name'].str.contains(pm_name, na=False)]
    if portfolio_type is not None:
        for portfolio_type_key in ['level_1_type', 'level_2_type', 'level_3_type', 'management_type']:
            portfolio_type[portfolio_type_key] = portfolio_type[portfolio_type_key] + [None] if (portfolio_type[portfolio_type_key] is not None and '空值' in portfolio_type[portfolio_type_key]) else portfolio_type[portfolio_type_key]
        level_1_condition = ret['level_1_type'].isin(portfolio_type['level_1_type']) if portfolio_type['level_1_type'] is not None else pd.Series(True, ret.index)
        level_2_condition = ret['level_2_type'].isin(portfolio_type['level_2_type']) if portfolio_type['level_2_type'] is not None else pd.Series(True, ret.index)
        level_3_condition = ret['level_3_type'].isin(portfolio_type['level_3_type']) if portfolio_type['level_3_type'] is not None else pd.Series(True, ret.index)
        management_type_condition = ret['management_type'].isin(portfolio_type['management_type']) if portfolio_type['management_type'] is not None else pd.Series(True, ret.index)
        ret = ret[level_1_condition & level_2_condition & level_3_condition & management_type_condition]
    if client_region is not None:
        client_region = client_region + [None] if '空值' in client_region else client_region
        ret = ret[ret['client_region'].isin(client_region)]
    if include_additional_info:
        ret['benchmark_id'] = ret.apply(lambda x: 'FOF_BM' if x['benchmark'] else None, axis=1)
        ret['freq'] = ret.apply(lambda x: 'W' if x['portfolio_oa_id'][:5] == 'VIR_C' else 'D', axis=1)
        ret['advisory_or_not'] = ret.apply(lambda x: True if x['portfolio_oa_id'][:5] == 'VIR_C' else False, axis=1)
    if include_portfolio_oa_id is False:
        del ret['portfolio_oa_id']
    if user_permission_setting:
        user_permissions = userIdentify.user_identifier()
        if user_permissions:
            ret = ret[ret['PARENT_SUBSIDIARY'].isin(user_permissions)]
    return ret

# -------------------------------------------------------------------------------------------------
# 读取FOF产品的经过对账户转换、投资经理转换、客户特殊需求进行筛选后的信息
# 作为custFOF_getFOFReferenceData的wrapper，在进行账户整体绩效统计时使用，具体到单一账户的各类展示请勿使用该函数
# -------------------------------------------------------------------------------------------------
def custFOF_getFOFReferenceDataThroughConvertFilter(
    pm_name=None,
    portfolio_type=None,    # FOF产品线类型，传入None或者dict. 传入None时不加筛选取所有FOF产品信息；
                            # 传入dict时必须key包含level_1_type, level_2_type, level_3_type, management_type, 分别对应一级标签、二级标签、三级标签、管理类型,
                            # 传入dict的value可以为list或者None，为None时对应的级别不做筛选
    client_region=None,     # 客户区域(分公司)信息筛选, 传入list或者None, 默认为None不筛选
    include_advisory_account=False,     # 是否加入投顾账户
    read_aum=False,                     # 调节是否加入动态数据, 仅TOT_NET_VAL为动态数据
    include_additional_info=False,      # 是否加入附加信息列，默认为否。目前附加信息列包含benchmark_id列和freq列
                                        # benchmark_id列：如果FOF账户具有benchmark则显示FOF_BM，否则为None
                                        # freq列：是否加入数据频率标识列，添加后freq列展示FOF账户净值数据频率，目前投顾账户为W，其他为D
    user_permission_setting=False,      # 是否加入母子公司权限限制。对于研究类内容，不设限制置为False。对于具体账户持仓和交易信息，置为True

    # 以上参数为custFOF_getFOFReferenceData的已有参数，下列参数是对转换等账户进行判断处理的参数

    observe_date=datetime.date.today(), # 不同的日期下，发生转换的账户的属性可能不同，需输入观察日（例如绩效数据截止日期）进行判断。默认站在当前时间点,已录入的投资经理转换都已生效。
    include_account_type_convert=True,       # 是否纳入发生私享臻选转换的账户，默认为纳入
    include_pm_convert=True,    # 是否纳入投资经理转换的账户，默认为纳入
    convert_account_as_whole=True,      # 是否将转换账户前后绩效视为一体(对私享臻选的转换和投资经理的转换同时生效)，默认视为一体（默认设置按照最大化的要求）
    include_client_special_need=True,   # 是否将具有客户特殊需求的账户纳入，默认为纳入
):
    if pm_name == '全部':
        pm_name = None
    if portfolio_type is not None:
        assert set(portfolio_type.keys()) == {'level_1_type', 'level_2_type', 'level_3_type', 'management_type'}, \
                "portfolio_type传入字典时, key必须包含level_1_type, level_2_type, level_3_type, management_type四类"
    # pm_name先直接输入None,在本函数最后再进行筛选,避免pm_name因筛选发生变动导致数据有误
    ret = custFOF_getFOFReferenceData(pm_name=None, portfolio_type=portfolio_type, client_region=client_region,
                                      include_advisory_account=include_advisory_account, read_aum=read_aum,
                                      include_additional_info=include_additional_info, user_permission_setting=user_permission_setting)

    # 转换类信息的处理
    # 1. 账户类型转换(私享<->臻选)的处理
    # FIXME 目前只对臻选转私享的情况做了处理，考察转换前的历史表现时（绩效日期选在转换之前时），会抹去投资经理的信息
    if include_account_type_convert:
        if not convert_account_as_whole:
            # 是转换+有转换日信息+观察日期>=转换日期，则重设inception_date, 否则不变
            ret['inception_date'] = ret.apply(lambda x: x['CONVERT_DATE'] + relativedelta(months=3)
                                    if not pd.isnull(x['CONVERT_DATE']) and x['CONVERT_OR_NOT']=='是'
                                    and x['CONVERT_DATE'] <= observe_date else x['inception_date'], axis=1)
            # 是转换+有转换日信息+观察日期<转换日期（即考察转换前的历史数据），则将pm_name置为空，否则不动pm_name的信息
            ret['pm_name'] = ret.apply(lambda x: None if not pd.isnull(x['CONVERT_DATE']) and x['CONVERT_OR_NOT']=='是'
                                    and x['CONVERT_DATE'] > observe_date else x['pm_name'], axis=1)
    else:
        ret = ret[ret['CONVERT_OR_NOT'] != '是']
    # 2. 投资经理转换的处理
    if include_pm_convert:
        ret['pm_name'] = ret.apply(lambda x: x['pm_name'] if pd.isnull(x['PM_CONVERT_DATE']) else
                                    (x['CURRENT_PM'] if (x['PM_CONVERT_DATE'] + relativedelta(months=3)<=observe_date)
                                     else (x['FORMER_PM'] if (x['PM_CONVERT_DATE']>observe_date) else None)), axis=1)
        if not convert_account_as_whole:
            ret['inception_date'] = ret.apply(lambda x: x['PM_CONVERT_DATE'] + relativedelta(months=3)
                                    if not pd.isnull(x['PM_CONVERT_DATE']) and (x['PM_CONVERT_DATE'] + relativedelta(months=3))<=observe_date
                                    else x['inception_date'], axis=1)
    else:
        ret = ret[pd.isna(ret['PM_CONVERT_DATE'])]
    # 3. 是否纳入有客户特殊需求的账户
    if not include_client_special_need:
        ret = ret[ret['CLIENT_SPECIAL_NEEDS'] != '是']

    if pm_name is not None:
        ret = ret[ret['pm_name'].str.contains(pm_name, na=False)]
    return ret

# ------------------------------------------------------
# 获取账户累计净值和收益率序列
# ------------------------------------------------------
def custFOF_getFOFNetValueAndReturn(
    start_date,
    end_date,
    portfolio_ids=None,  # list, 账户A6_ID， 如果此处为None，freq为W时，会全部产品降频为W，如果freq为D时，会过滤掉投顾产品
    freq='D',
    include_flag=False,  # Flag为True的时候，会包含红黄绿灯
    include_benchmark=False,  # Flag为True的时候，返回数据会包含FOF Benchmark的日收益率
    acc_nav=False  # 是否采用累计净值计算，部分FOF账户存在分红，单位净值计算有误的情况下使用
):
    assert freq in ("D", "W"), "freq需为D或者W"
    assert (type(start_date) == datetime.date), '日期输入格式需为datetime.date'
    assert (type(end_date) == datetime.date), '日期输入格式需为datetime.date'
    if acc_nav:
        assert portfolio_ids is not None and len(portfolio_ids)==1, '部分账户不支持累计净值，仅开放单一FOF获取累计净值'
    amdata_conn = amdata.amdata_connectAmdataDb()

    # 为保证freq为W进行降频时第一周的数据完整准确，需向前多取数据
    aux_start_date = start_date - datetime.timedelta(15)
    benchmark_to_include = ", BM_TODAY_RETURN" if include_benchmark else ""
    benchmark_to_project = ['bm_return'] if include_benchmark else []
    acc_nav_to_include = ", ACM_UNIT_NET_VAL, ACM_RETURN" if acc_nav else ""
    cols_to_include = "A6_FUNDID, PRTFL_SIM_NM, DATA_DT, UNIT_NET_VAL, TOT_NET_VAL, RETURN, DATA_FREQ" + acc_nav_to_include + benchmark_to_include
    if portfolio_ids == None:
        sql = "SELECT " + cols_to_include + " FROM AMFOF.V_FOF_ACCTDAILYINFO WHERE (data_dt >= DATE'{0}' and data_dt <= DATE'{1}')"
        ret = pd.read_sql_query(sql.format(aux_start_date, end_date), amdata_conn)
    else:
        assert isinstance(portfolio_ids, list), '账户名称需为list'
        portfolio_list = cal.basicCal_cut(portfolio_ids, 500)
        temp_list = list()
        # A6ID不是数据库索引、以及加入了BM_TODAY_RETURN字段影响了取数速度，目前sql语句中运用了IT写的oracle内部函数提升速度
        sql = "SELECT " + cols_to_include + " FROM AMFOF.V_FOF_ACCTDAILYINFO AA WHERE data_dt >= DATE'{0}' AND data_dt <= DATE'{1}'" \
              " AND AMFOF.PKG_VIEW_PARAM.FNC_SET_VIEW_A6FUNDID('{2}') IS NOT NULL"
        for sl in portfolio_list:
            read_sql = sql.format(aux_start_date, end_date, ','.join(["%s" % x for x in sl]))
            ret = pd.read_sql_query(read_sql, amdata_conn)
            temp_list.append(ret)
        ret = pd.concat(temp_list, axis=0)

    if freq == 'W':
        weekly_data = ret[ret['DATA_FREQ'] == 'W'].copy()
        if len(weekly_data):
            # 对于周频数据例如投顾数据，不同渠道的数据频率细节上有不同，统一过一遍降频函数，直接进行处理
            if include_benchmark:
                port_weekly_data = calendar.calender_convertDailyReturnToWeekly(weekly_data, date_column_name='DATA_DT', return_column_name='RETURN', id_column_name='A6_FUNDID', columns_to_exclude=['BM_TODAY_RETURN'])
                bm_weekly_data = calendar.calender_convertDailyReturnToWeekly(weekly_data, date_column_name='DATA_DT', return_column_name='BM_TODAY_RETURN', id_column_name='A6_FUNDID', columns_to_exclude=['RETURN'])
                # 对于未成功取到BM收益的数据列，需要保持全nan，不能由0替代
                if weekly_data['BM_TODAY_RETURN'].isnull().all():
                    bm_weekly_data['BM_TODAY_RETURN'] = np.nan
                all_weekly_data = port_weekly_data.merge(bm_weekly_data[['DATA_DT', 'A6_FUNDID', 'BM_TODAY_RETURN']], on=['DATA_DT', 'A6_FUNDID'])
            else:
                all_weekly_data = calendar.calender_convertDailyReturnToWeekly(weekly_data, date_column_name='DATA_DT', return_column_name='RETURN', id_column_name='A6_FUNDID')
        else:
            all_weekly_data = pd.DataFrame()
        # 对日频数据降频处理
        daily_data = ret[ret['DATA_FREQ'] == 'D'].copy()
        if include_benchmark:
            port_daily_data = calendar.calender_convertDailyReturnToWeekly(daily_data, date_column_name='DATA_DT', return_column_name='RETURN', id_column_name='A6_FUNDID', columns_to_exclude=['BM_TODAY_RETURN'])
            bm_daily_data = calendar.calender_convertDailyReturnToWeekly(daily_data, date_column_name='DATA_DT', return_column_name='BM_TODAY_RETURN', id_column_name='A6_FUNDID', columns_to_exclude=['RETURN'])
            all_daily_data = port_daily_data.merge(bm_daily_data[['DATA_DT', 'A6_FUNDID', 'BM_TODAY_RETURN']], on=['DATA_DT', 'A6_FUNDID'])
            ret = pd.concat([all_daily_data, all_weekly_data])
        else:
            port_daily_data = calendar.calender_convertDailyReturnToWeekly(daily_data, date_column_name='DATA_DT', return_column_name='RETURN', id_column_name='A6_FUNDID')
            ret = pd.concat([port_daily_data, all_weekly_data])
        ret['DATA_FREQ'] = 'W'
    else:
        ret = ret[ret['DATA_FREQ'] == 'D']
    if acc_nav:
        ret.rename(columns={'A6_FUNDID': 'portfolio_id', 'PRTFL_SIM_NM': 'portfolio_name', 'DATA_DT': 'date',
                        'ACM_UNIT_NET_VAL': 'NAV', 'TOT_NET_VAL': 'AUM', 'ACM_RETURN': 'return', 'BM_TODAY_RETURN': 'bm_return'}, inplace=True)
    else:
        ret.rename(columns={'A6_FUNDID': 'portfolio_id', 'PRTFL_SIM_NM': 'portfolio_name', 'DATA_DT': 'date',
                        'UNIT_NET_VAL': 'NAV', 'TOT_NET_VAL': 'AUM', 'RETURN': 'return', 'BM_TODAY_RETURN': 'bm_return'}, inplace=True)

    ret['date'] = pd.to_datetime(ret['date']).dt.date
    cols_to_project = ['date', 'portfolio_id', 'portfolio_name', 'NAV', 'AUM', 'return'] + benchmark_to_project
    if include_flag == True:
        flag_info_sql = "SELECT DATA_DT, A6_FUNDID, ACCT_START_ALERT, THIS_YEAR_ALERT FROM AMFOF.FOF_ACCT_ALERT WHERE (data_dt >= DATE'{0}' and data_dt <= DATE'{1}')"
        flag_info = pd.read_sql_query(flag_info_sql.format(start_date, end_date), amdata_conn)
        flag_info.rename(columns={'DATA_DT': 'date', 'A6_FUNDID': 'portfolio_id', 'ACCT_START_ALERT' : 'SI_flag', 'THIS_YEAR_ALERT': 'YTD_flag'}, inplace=True)
        flag_info['date'] = pd.to_datetime(flag_info['date']).dt.date
        ret = ret.merge(flag_info, on=['date', 'portfolio_id'], how='left')
        cols_to_project = cols_to_project + ['SI_flag', 'YTD_flag']
    ret = ret[cols_to_project]
    ret = ret[(ret['date'] >= start_date) & (ret['date'] <= end_date)]  # 截去start_date之前的数据，修正周频模式降频处理时造成的时间戳变化(end_date若在横跨两月的周可能会导致最终数据多出一个月)
    amdata_conn.close()
    return ret

# ------------------------------------------------------
# 获取缓存FOF账户绩效表现
# ------------------------------------------------------
def custFOF_getFOFCachedPerfStats(
    date,
    period='YTD',  # YTD, 2022, 2021, 2020
    portfolio_ids=None,
    stats=const.const.COMMON_PERF_STATS  # perf stats list, 默认stats为'period_return', 'annualized_period_return', 'annualized_volatility', 'max_drawdown', 'sharpe_ratio', 'calmar'
):
    conn = irm.irm_connectIRMDB()
    if period in ['2020', '2021', '2022', '2023', '2024']:
        date = calendar.calender_getStartEndDate(period=period, date=date)[1]
        date = date + datetime.timedelta(1)
    if portfolio_ids == None:
        sql = "SELECT * FROM irm.AMFOF_SRC_FOF_PORTFOLIO_STATS WHERE DT = DATE'{}' AND PERIOD = '{}'"
        ret = pd.read_sql_query(sql.format(date, period), conn).rename(columns=str.lower)
    else:
        assert isinstance(portfolio_ids, list), '账户名称需为list'
        portfolio_list = cal.basicCal_cut(portfolio_ids, 500)
        temp_list = list()
        sql = "SELECT * FROM irm.AMFOF_SRC_FOF_PORTFOLIO_STATS WHERE DT = DATE'{}' AND PERIOD = '{}' AND PORTFOLIO_ID IN ({})"
        for sl in portfolio_list:
            read_sql = sql.format(date, period, ','.join(["'%s'" % x for x in sl]))
            ret = pd.read_sql_query(read_sql, conn).rename(columns=str.lower)
            temp_list.append(ret)
        ret = pd.concat(temp_list, axis=0)
    ret = ret.replace(-9999, np.nan)
    ret['dt'] = pd.to_datetime(ret['dt']).dt.date
    ret.rename(columns={'dt':'date'}, inplace=True)
    ret = ret[['date', 'portfolio_id', 'portfolio_name', 'period']+stats]
    conn.close()
    return ret

# ------------------------------------------------------
# 私享账户分类型筛选
# ------------------------------------------------------
def custFOF_getSXAccountList(
    date,
    pm_name=None,
    aum_level=0,
    inception_before=datetime.date.today() - datetime.timedelta(days=90),
    account_type=None,
    account_area=None,
    include_account_type_convert=True,  # 是否纳入发生私享臻选转换的账户，默认为纳入
    include_pm_convert=True,  # 是否纳入投资经理转换的账户，默认为纳入
    convert_account_as_whole=True,  # 是否将转换账户前后绩效视为一体(对私享臻选的转换和投资经理的转换同时生效)，默认视为一体
    include_client_special_need=True,  # 是否将具有客户特殊需求的账户纳入，默认为纳入
):
    if account_type is None:
        account_type = config.specific_FOF_product_line['sixiang']
    account_list = custFOF_getFOFReferenceDataThroughConvertFilter(pm_name=pm_name, portfolio_type=account_type, read_aum=True, observe_date=date,
                                               include_account_type_convert=include_account_type_convert, include_pm_convert=include_pm_convert,
                                               convert_account_as_whole=convert_account_as_whole, include_client_special_need=include_client_special_need)
    selection = (pd.to_datetime(account_list['inception_date']).dt.date < inception_before) \
                 & (account_list['AUM'] > aum_level * 1e4 * 0.8)
    account_list = account_list[selection]
    if account_area is not None:
        account_list = account_list[account_list['client_region'] == account_area]
    # 异常账户会影响均值计算, 在此处筛选掉
    account_list = account_list[~(account_list['portfolio_id'].isin(list(config.abnormal_accounts_info.keys())))]
    return account_list

# ------------------------------------------------------------------------------
# 获取来自估值表处理后的FOF账户的历史交易数据, 场外交易的数据日期戳为估值表（清算）的确认日日期
# 对于私募基金的交易记录来说，所拿到的日期是实时性不足的，在确认日之前基金已产生收益贡献
# 表中的B份额产品的ID是规整的，无需多作处理
# ------------------------------------------------------------------------------
def custFOF_getTradeHistoricalFlowFromValuation(
    start_date,
    end_date,
    portfolio_ids=None,     # list, 账户A6_ID, 为None时查询全部port的结果
):

    amdata_conn = amdata.amdata_connectAmdataDb()
    cols_to_include = "A6_FUNDID, PRTFL_SIM_NM, D_DT, SECU_ID, SECU_NM, SECU_TYPE, C_BSFLAG, N_MATCH_PRICE, N_MATCH_QTY, N_MATCH_AMT, C_MARKET"
    if portfolio_ids is not None:
        portfolio_list = cal.basicCal_cut(portfolio_ids, 500)
        temp_list = list()
        sql = "SELECT " + cols_to_include + " FROM AMFOF.V_FOF_ACCTDAILYTRADE WHERE D_DT >= DATE'{0}' AND D_DT <= DATE'{1}' AND A6_FUNDID in ({2})"
        for sl in portfolio_list:
            ret = pd.read_sql_query(sql.format(start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'), ','.join(["'%s'" % x for x in sl])), amdata_conn)
            temp_list.append(ret)
        ret = pd.concat(temp_list, axis=0)
    else:
        sql = "SELECT " + cols_to_include + " FROM AMFOF.V_FOF_ACCTDAILYTRADE WHERE D_DT >= DATE'{0}' AND D_DT <= DATE'{1}'"
        ret = pd.read_sql_query(sql.format(start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')), amdata_conn)
    rename_map = {
        'A6_FUNDID': 'portfolio_id',
        'PRTFL_SIM_NM': 'portfolio_name',
        'D_DT': 'trade_date',               # 交易日期
        'SECU_ID': 'product_id',
        'SECU_NM': 'product_name',
        'SECU_TYPE': 'product_type',
        'C_BSFLAG': 'trade_type',           # 交易类型 方向
        'N_MATCH_PRICE': 'trade_price',     # 交易成交价格
        'N_MATCH_QTY': 'trade_volume',      # 交易量
        'N_MATCH_AMT': 'trade_amount',      # 交易金额
        'C_MARKET': 'trade_market',         # 交易市场类型
    }
    trade_type_map = {
        '基金转入': '买入',
        '基金转出': '卖出',
    }
    ret.rename(columns=rename_map, inplace=True)
    ret['trade_type'] = ret['trade_type'].apply(lambda x: trade_type_map.get(x, x))
    ret['trade_date'] = pd.to_datetime(ret['trade_date']).dt.date
    ret.sort_values(['portfolio_id', 'trade_date'], inplace=True)
    amdata_conn.close()
    return ret

# ------------------------------------------------------
# 获取FOF账户的在途交易指令数据
# 目前只从camp获取私募、后端的在途交易指令, 金证相关数据暂不获取
# 原始数据中的B份额产品ID不规整，输出时已处理
# 在途指令的交易类型包括：理财认购、首次申购、理财申购、全部赎回、理财赎回、理财转入、理财转出
# 理财转入转出类型trade_volume列代表的是份额数据
# ------------------------------------------------------
def custFOF_getTradeFutureFlow(
    start_date,             # 用于筛选计划交易的日期
    end_date,               # 用于筛选计划交易的日期
    portfolio_ids=None,     # list, 账户A6_ID, 为None时查询全部port的结果
    realtime_mode=False,    # 是否使用实时的在途交易数据,若为是,则访问每5min刷新的在途交易数据;若为否,访问每半天刷新的在途交易数据(为了与历史交易数据对齐互补)
):
    amdata_conn = amdata.amdata_connectAmdataDb()
    table_name = 'CAMP.PF_INSTRUCTION_VIEW_FOF_TABLE_REALTIME@CAMP' if realtime_mode else 'CAMP.PF_INSTRUCTION_VIEW_FOF_TABLE@CAMP'
    cols_to_include = "FUND_ID, FUND_NAME, DIRECT_USER_NAME, DIRECT_TIME, PAYMENT_DATE, STK_ID, STK_NAME, FLAG, TARGET_VALUE, SEAT, CONFIRM_STATUS"
    if portfolio_ids is not None:
        portfolio_list = cal.basicCal_cut(portfolio_ids, 500)
        temp_list = list()
        sql = "SELECT " + cols_to_include + " FROM " + table_name + " WHERE PAYMENT_DATE >= DATE'{0}' AND PAYMENT_DATE <= DATE'{1}' AND FUND_ID in ({2})"
        for sl in portfolio_list:
            ret = pd.read_sql_query(sql.format(start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'), ','.join(sl)), amdata_conn)
            temp_list.append(ret)
        ret = pd.concat(temp_list, axis=0)
    else:
        sql = "SELECT " + cols_to_include + " FROM " + table_name + " WHERE PAYMENT_DATE >= DATE'{0}' AND PAYMENT_DATE <= DATE'{1}'"
        ret = pd.read_sql_query(sql.format(start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')), amdata_conn)
    rename_map = {
        'FUND_ID': 'portfolio_id',
        'FUND_NAME': 'portfolio_name',
        'DIRECT_USER_NAME': 'pm_name',
        'DIRECT_TIME': 'trade_entry_date',      # 交易指令录入日期
        'PAYMENT_DATE': 'trade_execute_date',   # 交易指令计划执行日期
        'STK_ID': 'product_id',
        'STK_NAME': 'product_name',
        'FLAG': 'trade_type',                   # 交易类型 方向
        'TARGET_VALUE': 'trade_volume',         # 交易金额/数量，赎回类型表示份额，申购、认购类型表示金额
        'SEAT': 'trade_channel',                # 交易渠道
        'CONFIRM_STATUS': 'confirm_status',     # 交易受理状态
    }
    ret.rename(columns=rename_map, inplace=True)
    ret['trade_entry_date'] = pd.to_datetime(ret['trade_entry_date']).dt.date
    ret['trade_execute_date'] = pd.to_datetime(ret['trade_execute_date']).dt.date
    ret['portfolio_id'] = ret['portfolio_id'].astype(str)
    # 处理B份额产品id不统一的问题
    ret['product_id'] = ret['product_id'].apply(lambda x: x.split('.')[0][:6] + '.' + x.split('.')[1] if (len(x) == 10 and x.split('.')[0][6:7] == 'B') else x)  # 正常product_id string长度是9位；B份额是10位，第6位字符后多了个B
    ret.sort_values(['pm_name', 'portfolio_id', 'trade_execute_date'], inplace=True)
    amdata_conn.close()
    return ret

# --------------------------------------------------------------------------------------
# 获取来自CAMP的FOF账户的历史交易数据，所有场外交易记录的时间点都是下单当天日期，
# 能够直接对应到实际的账户持仓情况收益变化、贡献情况，与来自于估值表的数据不同
# --------------------------------------------------------------------------------------
def custFOF_getActualTradeHistoricalFlowFromCAMP(
    start_date,
    end_date,
    portfolio_ids=None,     # list, 账户A6_ID, 为None时查询全部port的结果
):
    amdata_conn = amdata.amdata_connectAmdataDb()
    cols_to_include = "FUNDID, ORDERDATE, MATCHDATE, STKCODE, STKNAME, STKTYPENAME, BSFLAG, MATCHPRICE, MATCHQTY, MATCHAMT, MARKET"
    if portfolio_ids is not None:
        portfolio_list = cal.basicCal_cut(portfolio_ids, 500)
        temp_list = list()
        sql = "SELECT " + cols_to_include + " FROM CAMP.TRADE_HIS_VIEW_CONCAT_FOF_TABLE@CAMP WHERE ORDERDATE >= DATE'{0}' AND ORDERDATE <= DATE'{1}' AND FUNDID in ({2})"
        for sl in portfolio_list:
            ret = pd.read_sql_query(sql.format(start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'), ','.join(["%s" % x for x in sl])), amdata_conn)
            temp_list.append(ret)
        ret = pd.concat(temp_list, axis=0)
    else:
        sql = "SELECT " + cols_to_include + " FROM CAMP.TRADE_HIS_VIEW_CONCAT_FOF_TABLE@CAMP WHERE ORDERDATE >= DATE'{0}' AND ORDERDATE <= DATE'{1}'"
        ret = pd.read_sql_query(sql.format(start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')), amdata_conn)

    rename_map = {
        'FUNDID': 'portfolio_id',
        'MATCHDATE': 'trade_confirm_date',       # 确认日期（在持仓数据体现的日期）
        'ORDERDATE': 'trade_date',       # 交易日期（下指令的日期）
        'STKCODE': 'product_id',
        'STKNAME': 'product_name',
        'STKTYPENAME': 'product_type',
        'BSFLAG': 'trade_type',          # 交易类型 方向
        'MATCHPRICE': 'trade_price',     # 交易成交价格
        'MATCHQTY': 'trade_volume',      # 交易量
        'MATCHAMT': 'trade_amount',      # 交易金额
        'MARKET': 'trade_market',        # 交易市场类型
    }

    trade_type_map = config.camp_trade_flow_config['trade_type_map']
    product_type_map = config.camp_trade_flow_config['product_type_map']

    ret.rename(columns=rename_map, inplace=True)
    ret['portfolio_id'] = ret['portfolio_id'].astype(str)
    ret['trade_date'] = pd.to_datetime(ret['trade_date']).dt.date
    ret['trade_confirm_date'] = pd.to_datetime(ret['trade_confirm_date']).dt.date
    ret['trade_type'] = ret['trade_type'].apply(lambda x: trade_type_map.get(x, x))
    ret['product_type'] = ret['product_type'].apply(lambda x: product_type_map.get(x, x))
    ret['product_type'] = ret['product_type'].apply(lambda x: '公募基金' if 'ETF' in x else x)
    # 处理B份额产品id不统一的问题
    ret['product_id'] = ret['product_id'].apply(lambda x: x.split('.')[0][:6] + '.' + x.split('.')[1] if (len(x) == 10 and x.split('.')[0][6:7] == 'B') else x)  # 正常product_id string长度是9位；B份额是10位，第6位字符后多了个B
    # 不显示基金转换退款的相关记录
    ret = ret[ret['trade_type'] != '基金转换退款']
    ret.sort_values(['portfolio_id', 'trade_date'], inplace=True)
    amdata_conn.close()
    return ret


# --------------------------------------------------------------------------------------
# 获取FOF账户投委会基准的成分及其权重
# 投委会基准会有更新，需输入日期参数以获取所在日期的情况，输出内容是当前有效的投委会基准及其生效区间
# --------------------------------------------------------------------------------------
def custFOF_getFOFBMComponent(
    date=None,              # 数据日期(观察日期)，默认取该账户在所有区间的投委会基准情况，用于判断是否发生过变更以及进行时序分析
    portfolio_id=None,      # 默认取全量数据，指定账户请输入账户ID的list
):
    amdata_conn = amdata.amdata_connectAmdataDb()
    sql = "SELECT * FROM AMFOF.V_FOF_ACCT_BENCHAMRK"
    port_bm_component = pd.read_sql_query(sql, amdata_conn)
    amdata_conn.close()
    port_bm_component.rename(columns={'A6_FUNDID': 'portfolio_id', 'PRTFL_ID':'portfolio_oa_id', 'PRTFL_SIM_NM': 'portfolio_name',
                                      'BANCH_MARK_TYPE': 'bm_data_type', 'BANCH_MARK_ID': 'bm_id', 'BANCH_MARK_DESC': 'bm_name',
                                      'RATIO': 'bm_weight', 'COEFFICIENTS': 'coefficient', 'BM_TYPE': 'bm_type',
                                      'UPDATE_DT': 'update_date', 'EFFECT_FROM': 'effect_from', 'EFFECT_TO': 'effect_to'}, inplace=True)
    del port_bm_component['bm_type']
    port_bm_component['effect_to'] = port_bm_component['effect_to'].apply(lambda x: datetime.datetime(2099, 12, 31) if x > datetime.datetime(2099, 12, 31) else x)
    port_bm_component[['update_date', 'effect_from', 'effect_to']] = port_bm_component[['update_date', 'effect_from', 'effect_to']].apply(lambda col: pd.to_datetime(col).dt.date)
    port_bm_component = port_bm_component[port_bm_component['bm_data_type'] == '投委会基准']
    if portfolio_id:
        port_bm_component = port_bm_component[port_bm_component['portfolio_id'].isin(portfolio_id)]
    if date:
        port_bm_component = port_bm_component[(port_bm_component['effect_from'] <= date) & (port_bm_component['effect_to'] > date)]
    # 底层数据的指数名称不规范不统一，使用config统一进行映射
    port_bm_component['bm_name'] = port_bm_component['bm_id'].apply(lambda x: config.FOF_investment_commitee_bm_info.get(x, {'bm_name': None, 'allocation_type': None})['bm_name'])
    port_bm_component['bm_allocation_type'] = port_bm_component['bm_id'].apply(lambda x: config.FOF_investment_commitee_bm_info.get(x, {'bm_name': None, 'allocation_type': None})['allocation_type'])
    # 固定收益率所用的具体数值进行量纲调整
    port_bm_component['coefficient'] = port_bm_component.apply(lambda x: x['coefficient']/100 if x['bm_id'] == 'FIX_RATE' else None, axis=1)
    # 大类资产按照指定顺序排序
    bm_allocation_type_order = {'权益': 1, 'CTA': 2, '绝对收益': 3, '货币基金': 4, None: 5}
    port_bm_component['bm_allocation_type_order'] = port_bm_component['bm_allocation_type'].apply(lambda x: bm_allocation_type_order[x])
    port_bm_component.sort_values(['portfolio_id', 'effect_from', 'bm_allocation_type_order'], ascending=[True, False, True], inplace=True)
    port_bm_component.reset_index(drop=True, inplace=True)
    return port_bm_component


# --------------------------------------------------------------------------------------
# 获取来自CAMP的FOF账户T0可用金额，数量较少，采用全量获取
# --------------------------------------------------------------------------------------
def custFOF_getT0AvailableCash():
    amdata_conn = amdata.amdata_connectAmdataDb()
    sql = "SELECT * FROM  CAMP.A6_FUND_BAL@CAMP"
    t0_available_cash = pd.read_sql_query(sql, amdata_conn)
    t0_available_cash.rename(columns={'FUNDID': 'portfolio_id', 'BAL': 't0_available_cash'}, inplace=True)
    t0_available_cash['portfolio_id'] = t0_available_cash['portfolio_id'].astype(str)
    return t0_available_cash


# --------------------------------------------------------------------------------------
# 获取来自CAMP的交易款项具体划转时间（T0可用头寸由哪些交易影响）
# 只展示当天数据，刷新频率10分钟一次，与T0可用数据一致
# --------------------------------------------------------------------------------------
def custFOF_getT0AvailableCashTransferTime(
    portfolio_ids=None,     # list, 用于筛选账户, 默认全选
):
    amdata_conn = amdata.amdata_connectAmdataDb()
    sql = "SELECT * FROM CAMP.A6_ASSET@CAMP "
    if portfolio_ids:
        sql += "WHERE FUNDID in ({})".format(','.join(["'%s'" % x for x in portfolio_ids]))
    t0_transfer_time = pd.read_sql_query(sql, amdata_conn)
    t0_transfer_time.rename(columns={
        'FUNDID': 'portfolio_id',
        'STKCODE': 'product_id',
        'FUNDEFFECT': 'trade_amount',
        'CLEARDATE': 'date',
        'OPERTIME': 'transfer_operation_time',
        'MATCHQTY': 'trade_volume',
        'ORDERDATE': 'trade_date',
    }, inplace=True)
    t0_transfer_time['portfolio_id'] = t0_transfer_time['portfolio_id'].astype(str)
    t0_transfer_time['date'] = pd.to_datetime(t0_transfer_time['date']).dt.date
    t0_transfer_time['trade_date'] = pd.to_datetime(t0_transfer_time['trade_date']).dt.date
    t0_transfer_time['transfer_operation_time'] = pd.to_datetime(t0_transfer_time['transfer_operation_time'].astype(str).str.zfill(6), format='%H%M%S').dt.time
    t0_transfer_time = t0_transfer_time[['date', 'portfolio_id', 'product_id', 'trade_date', 'trade_amount', 'trade_volume', 'transfer_operation_time']]
    t0_transfer_time = t0_transfer_time.sort_values(['portfolio_id', 'date', 'transfer_operation_time'])
    return t0_transfer_time


# --------------------------------------------------------------------------------------
# 获取自建的交易试算指令列表
# 可按照时间和账户进行筛选
# --------------------------------------------------------------------------------------
def custFOF_getTrialTradeOrder(
    start_date,
    end_date,               # 起止日期筛选是按照交易执行日期trade_date进行筛选
    portfolio_ids=None,     # list, 用于筛选账户, 默认全选
):
    conn = irm.irm_connectIRMDB()
    sql = "SELECT * FROM irm.amfof_trade_order_precalculation where trade_date >= DATE'{}' and trade_date <= DATE'{}'".format(start_date, end_date)
    if portfolio_ids:
        sql += " and portfolio_id in ({})".format(','.join(["'%s'" % x for x in portfolio_ids]))
    df = pd.read_sql_query(sql, conn).rename(columns=str.lower)
    conn.close()
    return df


# ------------------------------------------------------
# 从AMFOF读取FOF历史持仓产品列表，定期缓存自holding data
# ------------------------------------------------------
def custFOF_getFOFCachedHoldingValuationSheet(
        start_date,
        end_date,
        portfolio_id=None,  # 传入list形式
        product_id=None     # 传入list形式
):
    assert (type(start_date) == datetime.date), '日期输入格式需为datetime.date'
    assert (type(end_date) == datetime.date), '日期输入格式需为datetime.date'
    conn = irm.irm_connectIRMDB()
    if portfolio_id is not None and product_id is None:
        sql = "select * from irm.fof_holding_valuation_sheet_adjusted where date >= DATE'{0}' and date <= DATE'{1}' and portfolio_id in ({2})"
        ret = pd.read_sql_query(sql.format(start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'),
                                           ','.join(["'%s'" % port_oa_id for port_oa_id in portfolio_id])), conn)
    elif portfolio_id is None and product_id is not None:
        sql = "select * from irm.fof_holding_valuation_sheet_adjusted where date >= DATE'{0}' and date <= DATE'{1}' and product_id in ({2})"
        ret = pd.read_sql_query(sql.format(start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'),
                                           ','.join(["'%s'" % prod_id for prod_id in product_id])), conn)
    elif portfolio_id is not None and product_id is not None:
        raise AssertionError("product_id 与 portfolio_id 不能同时传入值")
    else:
        sql = "select * from irm.fof_holding_valuation_sheet_adjusted where date >= DATE'{0}' and date <= DATE'{1}'"
        ret = pd.read_sql_query(sql.format(start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')), conn)
    conn.close()
    ret['date'] = pd.to_datetime(ret['date']).dt.date
    return ret
