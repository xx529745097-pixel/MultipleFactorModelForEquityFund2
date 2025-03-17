# ------------------------------------------------------
# 本文档用于从Wind WDS数据库读取并预处理数据
# ------------------------------------------------------
import re

from sqlalchemy import create_engine
import pandas as pd
import datetime
from dateutil.relativedelta import relativedelta
import src.const as const
import src.utils.Calculation as cal
import math as math
import streamlit as st
from src.data.custMF import custMF_getMFIndustryClassification

# ------------------------------------------------------
# wind数据库链接
# Author: Zhongheng Shen, 041439
# ------------------------------------------------------
def wind_connectWindDB():
    __oracle_url = 'oracle://wangnanhao:40!VEz6QX@10.23.153.15:21010/wind'
    dbengine = create_engine(__oracle_url)
    dbconn = dbengine.connect()
    return dbconn

# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# 0. 内部函数
# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------

# 选取主动权益基金的sql
# length(a.f_info_windcode)!=10，带！的转型基金(11位)不能去，只把带F的（10位）香港互认基金去掉
# a.F_INFO_ISINITIAL =1，只考虑初始份额，A份额
__sql_EquityFund = " from (select * from ChinaMutualFundDescription )a, (select * from ChinaMutualFundManager)b,(select * from ChinaMutualFundSector)c, (select * from CFundPchRedm)d" \
                   " where a.f_info_windcode=b.f_info_windcode and a.f_info_windcode=c.f_info_windcode and a.f_info_windcode=d.f_info_windcode and length(a.f_info_windcode)!=10" \
                   " and a.F_INFO_ISINITIAL =1 and length(c.S_INFO_SECTOR)=16 "
__sql_EquityFundAllShare = " from (select * from ChinaMutualFundDescription )a, (select * from ChinaMutualFundManager)b,(select * from ChinaMutualFundSector)c, (select * from CFundPchRedm)d" \
                   " where a.f_info_windcode=b.f_info_windcode and a.f_info_windcode=c.f_info_windcode and a.f_info_windcode=d.f_info_windcode and length(a.f_info_windcode)!=10" \
                   " and length(c.S_INFO_SECTOR)=16 "
__sql_EquityFund2 = " and c.S_INFO_SECTOR in {} "
__sql_orderby = " order by a.f_info_windcode,b.F_INFO_MANAGER_STARTDATE"

# ------------------------------------------------------
# 把wind的波动率，夏普等指标做年化scale
# ------------------------------------------------------
def _getAnnualizedStats(data):
    scale_map = {'f_stdarddev_year': math.sqrt(const.const.ANNUAL_SCALE),
                 'f_stdarddev_twoyear': math.sqrt(const.const.ANNUAL_SCALE),
                 'f_stdarddev_threeyear': math.sqrt(const.const.ANNUAL_SCALE),
                 'f_sharpratio_year': math.sqrt(const.const.ANNUAL_SCALE),
                 'f_sharpratio_twoyear': math.sqrt(const.const.ANNUAL_SCALE),
                 'f_sharpratio_threeyear': math.sqrt(const.const.ANNUAL_SCALE),
                 'f_maxdownside_quarter': -1,
                 'f_maxdownside_halfyear': -1,
                 'f_maxdownside_year': -1,
                 'f_maxdownside_twoyear': -1,
                 'f_maxdownside_threeyear': -1,
                 'f_maxdownside_thisyeart': -1,
                 'f_maxdownside_sincefound': -1,
                 'f_maxdownside_thisweek': -1,
                 'f_maxdownside_thismonth': -1
                }
    scale_columns = list(scale_map.keys())
    scale_columns = list(set(scale_columns).intersection(set(data.columns)))
    for column in scale_columns:
        data[column] = data[column]*scale_map[column]
    return data

# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# 1. 股票Ref函数
# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------

# ------------------------------------------------------
# 获取指数成分股信息（名称、权重等）
# ------------------------------------------------------
def wind_getStockIndexComponentsWeight(
    index_code,  # must be in "HS300", "ZZ100", "ZZ500", "ZZ800", "ZZ1000"
    start_date,  # datetime.date instance
    end_date  # datetime.date instance
):
    wd_conn = wind_connectWindDB()
    assert index_code in ("HS300", "ZZ100", "ZZ500", "ZZ800", "ZZ1000"), "目前只支持沪深300，中证100， 中证500， 中证800， 中证1000"
    assert isinstance(start_date, datetime.date), "date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "date must be an instance of datetime.date"

    start_date = datetime.datetime.strftime(start_date, format='%Y%m%d')
    end_date = datetime.datetime.strftime(end_date, format='%Y%m%d')

    index_table_mapping = {
        "ZZ500": ["weight", "AIndexCSI500Weight"],
        "ZZ100": ["weight", "AIndexCSI100Weight"],
        "ZZ800": ["weight", "AIndexCSI800Weight"],
        "ZZ1000": ["weight", "AIndexCSI1000Weight"],
        "HS300": ["i_weight", "AIndexHS300CloseWeight"]
    }

    sql = "select trade_dt, s_con_windcode, " + index_table_mapping[index_code][0] + " from " + index_table_mapping[index_code][1] \
          + " where trade_dt >=  '{}' and trade_dt <= '{}' order by trade_dt"
    df = pd.read_sql_query(sql.format(start_date, end_date), wd_conn)
    df['trade_dt'] = pd.to_datetime(df['trade_dt']).dt.date
    df.rename(columns={"trade_dt": "date", 's_con_windcode': 'stock_id'}, inplace=True)
    if "i_weight" in df.columns:  # In the table of HS300, 'weight' was named as 'i_weight'
        df.rename(columns={"i_weight": "weight"}, inplace=True)
    df['weight'] = df['weight'] / 100  # scale to 1
    df['index_code'] = index_code
    wd_conn.close()
    return df

# ------------------------------------------------------
# 获取A股的股东及持股数量
# 股东和自由流通股东并集
# ------------------------------------------------------
def wind_getAShareHolders(
        stock_ids = None     # stock_ids股票代码，应为list格式，为None时，相当于获取全部股票
):
    dbconn = wind_connectWindDB()
    sql_total = "select S_INFO_WINDCODE as stock_id, REPORT_PERIOD as dt, " \
                "S_HOLDER_ANAME as holder_name, S_HOLDER_QUANTITY as quantity " \
                "from AShareInsideHolder " # 前十大股东
    sql_float = "select S_INFO_WINDCODE as stock_id, REPORT_PERIOD as dt, " \
                "S_HOLDER_NAME as holder_name, S_HOLDER_QUANTITY as quantity " \
                "from AShareFloatHolder " # 流通股东
    sql_codes = "where S_INFO_WINDCODE in {} "
    sql_2 = "order by S_INFO_WINDCODE, REPORT_PERIOD, S_HOLDER_QUANTITY desc"

    if stock_ids == None:  # 空的时候读取全部股票
        df_total = pd.read_sql_query(sql_total + sql_2, dbconn)
        df_float = pd.read_sql_query(sql_float + sql_2, dbconn)
    elif len(stock_ids) == 1:  # list长度为1时候无法使用tuple
        df_total = pd.read_sql_query(sql_total + sql_codes.format('\'' + stock_ids[0] + '\'') + sql_2, dbconn)
        df_float = pd.read_sql_query(sql_float + sql_codes.format('\'' + stock_ids[0] + '\'') + sql_2, dbconn)
    elif len(stock_ids) < 1000:
        df_total = pd.read_sql_query(sql_total + sql_codes.format(tuple(stock_ids)) + sql_2, dbconn)
        df_float = pd.read_sql_query(sql_float + sql_codes.format(tuple(stock_ids)) + sql_2, dbconn)
    else:  # 长度超过1000，读全部股票，再loc
        df_total = pd.read_sql_query(sql_total + sql_2, dbconn)
        df_total = df_total.loc[df_total['stock_id'].isin(stock_ids)].reset_index(drop=True)
        df_float = pd.read_sql_query(sql_float + sql_2, dbconn)
        df_float = df_float.loc[df_float['stock_id'].isin(stock_ids)].reset_index(drop=True)
    df_total = df_total.dropna().reset_index(drop=True)
    df_float = df_float.dropna().reset_index(drop=True)
    df = pd.merge(df_total, df_float, on=df_total.columns.to_list(), how='outer') # 取并集
    df = df.sort_values(by=['stock_id', 'dt', 'quantity'], ascending=False).reset_index(drop=True)
    df.rename(columns={'dt': 'date'}, inplace=True)
    df['date'] = pd.to_datetime(df['date']).dt.date
    dbconn.close()
    return df

# ------------------------------------------------------
# 获取A股的财务报表信息
# ------------------------------------------------------
def wind_getAShareFinancialInfo(
    stock_ids=None,     # stock_ids股票代码，应为list格式，为None时，相当于获取全部股票
    report_period_start_date=None,  # datetime.date, 起始日期
    report_period_end_date=None,  # datetime.date, 截止日期
):
    dbconn = wind_connectWindDB()
    sql_1 = "select a.S_INFO_WINDCODE as stock_id, c.S_INFO_NAME as stock_name, " \
            "a.REPORT_PERIOD as dt, a.S_FA_EPS_BASIC as eps_basic, a.S_QFA_EPS as eps_quarter, a.S_FA_YOYNETPROFIT as net_profit_yoy, " \
            "b.S_VAL_MV as total_mv, b.S_DQ_MV as floating_mv, b.S_VAL_PE_TTM as pe_ttm, b.S_VAL_PB_NEW as pb " \
            "from AShareFinancialIndicator a, AShareEODDerivativeIndicator b, AShareDescription c " \
            "where a.S_INFO_WINDCODE = c.S_INFO_WINDCODE and a.S_INFO_WINDCODE = b.S_INFO_WINDCODE and a.REPORT_PERIOD = b.TRADE_DT "
    sql_codes = "and a.S_INFO_WINDCODE in ({}) "
    sql_date_between = "and a.REPORT_PERIOD >= '{}' and a.REPORT_PERIOD <= '{}' "
    # 如果start_date和end_date均不为None，进行日期区间筛选
    if (report_period_start_date is not None) and (report_period_end_date is not None):
        assert isinstance(report_period_start_date, datetime.date) and isinstance(report_period_end_date, datetime.date), "start_date和end_date类型需为datetime.date"
        sql_1 += sql_date_between.format(report_period_start_date.strftime("%Y%m%d"), report_period_end_date.strftime("%Y%m%d"))
    # 股票筛选，stock_ids为None的时候读取全部股票
    if stock_ids is None:
        df = pd.read_sql_query(sql_1, dbconn).rename(columns=str.lower)
    elif len(stock_ids) < 500:
        assert isinstance(stock_ids, list), "stock_ids参数类型需为list"
        df = pd.read_sql_query(sql_1 + sql_codes.format(",".join(["'%s'" % s_id for s_id in stock_ids])), dbconn).rename(columns=str.lower)
    else:  # 长度超过500, 分批读入
        assert isinstance(stock_ids, list), "stock_ids参数类型需为list"
        stock_id_list = cal.basicCal_cut(stock_ids, 500)
        temp_list = []
        for sl in stock_id_list:
            df = pd.read_sql_query(sql_1 + sql_codes.format(",".join(["'%s'" % s_id for s_id in sl])), dbconn).rename(columns=str.lower)
            temp_list.append(df)
        df = pd.concat(temp_list, axis=0)
    df.rename(columns={'dt':'date'}, inplace=True)
    df['date'] = pd.to_datetime(df['date']).dt.date
    df['net_profit_yoy'] /= 100  # 量纲为1
    df[['total_mv', 'floating_mv']] /= 1e4 # 单位为亿
    dbconn.close()
    return df

# -----------------------------------------------------
# wind一致预测个股指标
# 同一报告期的预测会不断更新，使用预测日期EST_DT字段进行日期筛选
# -----------------------------------------------------
def wind_getAshareConsensusEstimation(
    est_start_date,  # datetime.date, 起始日期, 根据预测日期EST_DT字段筛选
    est_end_date,  # datetime.date, 截止日期, 根据预测日期EST_DT字段筛选
    stock_ids=None,     # stock_ids股票代码，应为list格式，为None时，相当于获取全部股票
    consensus_model=None  # list, 一致预期模型 '263001000'-领先预测(30d) '263002000'-前瞻预测(90d) '263003000'-万得一致预测(180d) '263004000'-大事后(180d)
):
    assert isinstance(est_start_date, datetime.date), "est_start_date类型需为datetime.date"
    assert isinstance(est_end_date, datetime.date), "est_end_date类型需为datetime.date"
    dbconn = wind_connectWindDB()
    sql_1 = "select a.S_INFO_WINDCODE as stock_id, a.EST_DT as est_date, a.EST_REPORT_DT as report_period, a.NUM_EST_INST as institution_num, " \
            "a.EPS_AVG as consen_avg_eps, a.MAIN_BUS_INC_AVG as consen_avg_main_bus_inc, a.NET_PROFIT_AVG as consen_avg_net_profit, " \
            "a.S_EST_AVGCPS as consen_avg_cps, a.S_EST_AVGDPS as consen_avg_dps, a.S_EST_AVGBPS as consen_avg_bps, " \
            "a.S_EST_AVGEBT as consen_avg_ebt, a.S_EST_AVGROA as consen_avg_roa, a.S_EST_AVGROE as consen_avg_roe, " \
            "a.CONSEN_DATA_CYCLE_TYP as consensus_model from AShareConsensusData a " \
            "where 1=1 "
    sql_codes = "and a.S_INFO_WINDCODE in ({}) "
    sql_date_between = "and a.EST_DT >= '{}' and a.EST_DT <= '{}' "
    sql_consensus_model = "and a.CONSEN_DATA_CYCLE_TYP in ({}) "
    sql_1 += sql_date_between.format(est_start_date.strftime("%Y%m%d"), est_end_date.strftime("%Y%m%d"))  # 预测日期筛选
    # 对一致预期模型进行筛选
    if consensus_model:
        assert isinstance(consensus_model, list), "consensus_model类型需为list"
        sql_1 += sql_consensus_model.format(",".join(["'%s'" % model for model in consensus_model]))
    # 筛选股票
    if stock_ids is None:
        df = pd.read_sql_query(sql_1, dbconn).rename(columns=str.lower)
    elif len(stock_ids) < 500:
        assert isinstance(stock_ids, list), "stock_ids参数类型需为list"
        df = pd.read_sql_query(sql_1 + sql_codes.format(",".join(["'%s'" % s_id for s_id in stock_ids])), dbconn).rename(columns=str.lower)
    else:  # 长度超过500, 分批读入
        assert isinstance(stock_ids, list), "stock_ids参数类型需为list"
        stock_id_list = cal.basicCal_cut(stock_ids, 500)
        temp_list = []
        for sl in stock_id_list:
            df = pd.read_sql_query(sql_1 + sql_codes.format(",".join(["'%s'" % s_id for s_id in sl])), dbconn).rename(columns=str.lower)
            temp_list.append(df)
        df = pd.concat(temp_list, axis=0)
    df['est_date'] = pd.to_datetime(df['est_date']).dt.date
    df['report_period'] = pd.to_datetime(df['report_period']).dt.date
    # 单位为万元的列
    for col in ['consen_avg_main_bus_inc', 'consen_avg_net_profit', 'consen_avg_ebt']:
        df[col] *= 1e4
    # 单位为%的列
    for col in ['consen_avg_roa', 'consen_avg_roe']:
        df[col] /= 1e2
    dbconn.close()
    return df

# ------------------------------------------------------
# 新股上市机构询价信息，包括询价价格、询价数量等
# ------------------------------------------------------
def wind_getIPOInquiryDetails(
    start_date,                       # 招股公告日开始时间
    end_date = datetime.date.today()  # 招股公告日截止时间，默认最新
):
    dbconn = wind_connectWindDB()
    start_date = start_date.strftime("%Y%m%d")
    end_date = end_date.strftime("%Y%m%d")
    sql = "select a.S_INFO_WINDCODE as stock_id, b.S_IPO_PUBOFFRDATE as sdate, " \
          "a.INQUIRER as company_full_name, a.ISSUETARGET as product_full_name, a.DEDAREDPRICE as bid_price, a.DEDAREDSHARES as bid_quantity " \
          "from IPOInquiryDetails a, AShareIPO b " \
          "where a.S_INFO_WINDCODE = b.S_INFO_WINDCODE " \
          "and INQUIRER_TYPECODE != 202000090 " \
          "and b.S_IPO_PUBOFFRDATE >= '{}' " \
          "and b.S_IPO_PUBOFFRDATE <= '{}'"
    df = pd.read_sql_query(sql.format(start_date, end_date), dbconn) # != 202000090 剔除个人投资者
    df.rename(columns = {'sdate':'date'}, inplace=True)
    df['date'] = pd.to_datetime(df['date']).dt.date
    df['bid_quantity'] *= 10000 # 单位转为股
    dbconn.close()
    return df

# --------------------------------------------
# 获取A股分红信息，包含分红方案，进度，公告时间等信息
# 使用REPORT_PERIOD字段进行日期筛选
# --------------------------------------------
def wind_getAShareDividendInfo(
    report_period_start_date,  # datetime.date, 开始报告期
    report_period_end_date,  # datetime.date, 截止报告期
    stock_ids=None,  # list or None, 筛选股票列表
    include_additional_info=False  # 是否带入其他表的信息，例如分红日前120日收盘价均值
):
    assert isinstance(report_period_start_date, datetime.date), "date must be an instance of datetime.date"
    assert isinstance(report_period_end_date, datetime.date), "date must be an instance of datetime.date"
    dbconn = wind_connectWindDB()
    sql = "SELECT a.S_INFO_WINDCODE AS stock_id, a.S_DIV_PROGRESS AS div_progress_id, a.STK_DVD_PER_SH AS stk_div_per_share, a.CASH_DVD_PER_SH_PRE_TAX AS cash_div_per_share_pre_tax, " \
          "a.CASH_DVD_PER_SH_AFTER_TAX AS cash_div_per_share_after_tax, a.EQY_RECORD_DT AS registry_date, a.EX_DT AS ex_date, a.DVD_PAYOUT_DT AS cash_div_payout_date, a.LISTING_DT_OF_DVD_SHR AS stk_div_listing_date, " \
          "a.S_DIV_PRELANDATE AS preland_date, a.S_DIV_SMTGDATE AS smtg_date, a.DVD_ANN_DT dvd_ann_date, a.S_DIV_BASEDATE AS div_base_share_date, a.S_DIV_BASESHARE AS div_base_share, " \
          "a.CRNCY_CODE AS currency_code, a.ANN_DT AS latest_ann_date, a.IS_CHANGED AS is_changed, a.REPORT_PERIOD AS report_period, a.IS_TRANSFER AS no_div_flag, " \
          "a.DISTRI_PROFIT_CONSOLIDATE AS distri_consolidate_profit, a.DISTRI_PROFIT_PARENT_COMP AS distri_parent_profit "
    # 是否带入额外信息
    if include_additional_info:
        sql += ", b.MA_120D FROM AShareDividend a LEFT JOIN Ashareintensitytrend b ON a.S_INFO_WINDCODE=b.S_INFO_WINDCODE AND a.EX_DT=b.TRADE_DT "
    else:
        sql += "FROM AShareDividend a "
    # 只保留处于正常状态的分红记录(1-董事会预案，2-股东大会通过，3-实施)，过滤未通过或已终止的分红记录，正常预案决定不分红的股票分红状态会停留在1-董事会预案
    div_progress_map = {'1': '董事会预案', '2': '股东大会通过', '3': '实施'}
    sql += "WHERE a.S_DIV_PROGRESS IN ({}) ".format(','.join(["'%s'" % div_progress_id for div_progress_id in div_progress_map.keys()]))
    # 日期条件
    sql += "AND a.REPORT_PERIOD >= '{}' AND a.REPORT_PERIOD <= '{}' ".format(report_period_start_date.strftime("%Y%m%d"), report_period_end_date.strftime("%Y%m%d"))
    if stock_ids:
        assert isinstance(stock_ids, list), "stock_ids must be a list"
        sql += "AND a.S_INFO_WINDCODE IN ({}) "
        if len(stock_ids) <= 500:
            df = pd.read_sql_query(sql.format(','.join(["'%s'" % x for x in stock_ids])), dbconn)
        else:
            stock_list = cal.basicCal_cut(stock_ids, 500)
            temp_list = list()
            for sl in stock_list:
                sql_temp = sql.format(','.join(["'%s'" % x for x in sl]))
                df = pd.read_sql_query(sql_temp, dbconn)
                temp_list.append(df)
            df = pd.concat(temp_list, axis=0)
    else:
        df = pd.read_sql_query(sql.format(report_period_start_date, report_period_end_date), dbconn)
    for col in ['registry_date', 'ex_date', 'cash_div_payout_date', 'stk_div_listing_date', 'preland_date', 'smtg_date',
                'dvd_ann_date', 'div_base_share_date', 'latest_ann_date']:
        df[col] = pd.to_datetime(df[col], format="%Y%m%d").dt.date
    df['div_base_share'] = df['div_base_share'] * 1e4
    df.insert(2, 'div_progress', df['div_progress_id'].map(div_progress_map))
    dbconn.close()
    return df

# -----------------------------------
# 获取机构调研上市公司信息
# -----------------------------------
def wind_getMFInstitutionSurvey(
    start_date,   # 起始日期
    end_date      # 截止日期
):
    assert isinstance(start_date, datetime.date), "start_date需为datetime.date类型"
    assert isinstance(end_date, datetime.date), "end_date需为datetime.date类型"
    dbconn = wind_connectWindDB()
    sql = "select a.EVENT_ID as event_id, b.S_INFO_WINDCODE as stock_id, b.S_SURVEYDATE as dt, b.S_ACTIVITIESTYPE as survey_type, " \
          "a.S_INSTITUTIONCODE as company_id, c.S_SNAME as company_name, a.S_ANALYST_ID as analyst_id, a.S_ANALYSTNAME as analyst_name " \
          "from AShareISParticipant a, AshareISActivity b, CompOrganizationcode c where a.EVENT_ID = b.EVENT_ID and a.S_INSTITUTIONCODE = c.COMP_ID " \
          "and b.S_SURVEYDATE >= '{}' and b.S_SURVEYDATE <= '{}' "
    df = pd.read_sql_query(sql.format(start_date.strftime('%Y%m%d'), end_date.strftime('%Y%m%d')), dbconn).rename(columns=str.lower)
    dbconn.close()
    df.rename(columns={'dt': 'date'}, inplace=True)
    # FIXME 底层数据不规范，存在只有月份的六位日期，无法自动转换成datetime类型，暂保留原始字符串
    # df['date'] = pd.to_datetime(df['date']).dt.date
    return df

# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# 2. 基金Ref函数
# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------



# ------------------------------------------------------
# 根据输入的fund_types，来获取历史上的产品列表，default给出的是
# 所有基金。可以通过输入不同的ID，来获取不同种类
# 的基金列表，具体参见const.WIND_SECTOR_CODE_MAP
# ------------------------------------------------------
def wind_getHistoricalProductList(
    as_of_date=None,  # 如不为None，仅保留在此日期前成立的基金
    fund_types = None,          # Default are all types of funds, Check const.py for all types to use
    include_pm_info = False,    # 如果该参数为True，则同一个基金可能出现在多行！！因为曾经或者正在管理的所有基金经理都会各占一行。
    exclude_new_product=False,  # 去掉距离as_of_date最近三个月成立的基金产品
):
    if exclude_new_product == True:
        assert as_of_date is not None, '参数exclude_new_product为True需要参数as_of_date不为None'
    dbconn = wind_connectWindDB()
    sql_fund = "select a.F_INFO_WINDCODE as product_id, a.F_INFO_NAME as product_name, a.F_INFO_CORP_FUNDMANAGEMENTCOMP as company_short_name," \
       " a.F_INFO_SETUPDATE as product_start_date,a.F_INFO_MATURITYDATE as product_end_date, a.F_INFO_TYPE as fund_open_type, d.F_MINM_HOLDING_PRD as min_holding_month, " \
       " b.F_INFO_MANAGER_GENDER as pm_gender, b.F_INFO_FUNDMANAGER_ID as pm_id, b.F_INFO_FUNDMANAGER as pm_name," \
       " b.F_INFO_MANAGER_STARTDATE as pm_start_date,b.F_INFO_MANAGER_LEAVEDATE as pm_end_date, " \
       " c.S_INFO_SECTOR as type, c.S_INFO_SECTORENTRYDT as sector_start_date, c.S_INFO_SECTOREXITDT as sector_end_date "

    if fund_types is not None and len(fund_types) == 1 and '指数增强' in fund_types[0]:
        sub_type = fund_types[0]
        fund_types = ['2001010103000000']
    else:
        sub_type = 'Other'

    if fund_types is None:
        full_sql = sql_fund + __sql_EquityFund + __sql_orderby
    elif len(fund_types) == 1:
        full_sql = sql_fund + __sql_EquityFund + __sql_EquityFund2.format('\''+fund_types[0]+'\'') + __sql_orderby
    else:
        full_sql = sql_fund + __sql_EquityFund + __sql_EquityFund2.format(tuple(fund_types)) + __sql_orderby
    df_fund = pd.read_sql_query(full_sql, dbconn)

    if fund_types is not None and len(fund_types) == 1 and '指数增强' in sub_type:
        if sub_type == '300指数增强':
            df_fund = df_fund[df_fund['product_name'].str.contains('300')]
        elif sub_type == '500指数增强':
            df_fund = df_fund[df_fund['product_name'].str.contains('500')]
        else:
            return

    df_fund = df_fund.loc[df_fund['product_start_date'].notnull()].reset_index(drop=True)  # 删掉未成立的基金
    df_fund.replace({"type": const.const.WIND_SECTOR_CODE_MAP}, inplace=True)
    if include_pm_info == False:
        df_fund.drop(columns=['pm_gender', 'pm_id', 'pm_name', 'pm_start_date', 'pm_end_date'], inplace=True)
        df_fund.drop_duplicates(inplace=True)
    df_fund['product_start_date'] = pd.to_datetime(df_fund['product_start_date']).dt.date
    df_fund['product_end_date'] = pd.to_datetime(df_fund['product_end_date']).dt.date
    df_fund['pm_start_date'] = pd.to_datetime(df_fund['pm_start_date'], format='%Y%m%d').dt.date
    df_fund['pm_end_date'] = pd.to_datetime(df_fund['pm_end_date'], format='%Y%m%d').dt.date
    df_fund['sector_start_date'] = pd.to_datetime(df_fund['sector_start_date'], format='%Y%m%d').dt.date
    df_fund['sector_end_date'] = pd.to_datetime(df_fund['sector_end_date'], format='%Y%m%d').dt.date
    if as_of_date is not None:
        if exclude_new_product:
            df_fund = df_fund[df_fund['product_start_date'].apply(lambda x: (as_of_date-x).days > 90)]
        else:
            df_fund = df_fund[df_fund['product_start_date'].apply(lambda x: (as_of_date-x).days > 0)]
    dbconn.close()
    return df_fund


# ------------------------------------------------------
# 根据输入的fund_types，来当前时点的产品列表，default给出的是
# 所有基金。可以通过输入不同的ID，来获取不同种类
# 的基金列表，具体参见const.WIND_SECTOR_CODE_MAP
# ------------------------------------------------------
def wind_getCurrentProductList(
    fund_types=None,              # Default are all types of funds, Check const.py for all types to use
    include_pm_info=False,        # 如果该参数为True，则同一个基金可能出现在多行！！因为曾经或者正在管理的所有基金经理都会各占一行。
    exclude_new_product=False,    # 去掉最近三个月成立的基金产品
    exclude_small_product=False,  # 去掉小市值基金，目前规定3000w
    product_ids=None,             # 指定product_list获取对应信息, 提升时效, 否则数据太多处理速度慢
    only_a_share=True,              # 是否只取A份额，默认为是
):
    # select后面增加column
    dbconn = wind_connectWindDB()
    sql_fund = "select a.F_INFO_WINDCODE as product_id, a.F_INFO_NAME as product_name, a.F_INFO_FULLNAME as product_full_name, a.F_INFO_CORP_FUNDMANAGEMENTCOMP as company_short_name, " \
               "a.F_INFO_SETUPDATE as product_start_date, a.F_INFO_MATURITYDATE as product_end_date, a.F_INFO_MANAGEMENTFEERATIO as management_fee, " \
               "a.F_INFO_CUSTODIANFEERATIO as trustee_fee, a.CRNY_CODE as product_ccy, a.F_INFO_BENCHMARK as product_benchmark_name, a.F_INFO_TYPE as fund_open_type, d.F_MINM_HOLDING_PRD as min_holding_month, " \
               "b.F_INFO_MANAGER_GENDER as pm_gender, b.F_INFO_FUNDMANAGER_ID as pm_id, b.F_INFO_FUNDMANAGER as pm_name, " \
               "b.F_INFO_MANAGER_STARTDATE as pm_start_date,b.F_INFO_MANAGER_LEAVEDATE as pm_end_date, c.S_INFO_SECTOR as type "
    sql_cursign = " and c.CUR_SIGN = 1 " # c.CUR_SIGN = 1 分类最新标志

    if product_ids and len(product_ids) < 1000:
        sql_codes = "and a.F_INFO_WINDCODE in ({}) ".format(','.join(["'%s'" % x for x in product_ids]))
    else:
        sql_codes = ""

    if fund_types is not None and len(fund_types) == 1 and '指数增强' in fund_types[0]:
        sub_type = fund_types[0]
        fund_types = ['2001010103000000']
    else:
        sub_type = 'Other'

    if fund_types is None:
        full_sql = sql_fund + (__sql_EquityFund if only_a_share else __sql_EquityFundAllShare) + sql_codes + sql_cursign + __sql_orderby
    elif len(fund_types) == 1:
        full_sql = sql_fund + (__sql_EquityFund if only_a_share else __sql_EquityFundAllShare) + sql_codes + __sql_EquityFund2.format('\''+fund_types[0]+'\'') + sql_cursign + __sql_orderby
    else:
        full_sql = sql_fund + (__sql_EquityFund if only_a_share else __sql_EquityFundAllShare) + sql_codes + __sql_EquityFund2.format(tuple(fund_types)) + sql_cursign + __sql_orderby
    df_fund = pd.read_sql_query(full_sql, dbconn)

    if fund_types is not None and len(fund_types) == 1 and '指数增强' in sub_type:
        if sub_type == '300指数增强':
            df_fund = df_fund[df_fund['product_name'].str.contains('300')]
        elif sub_type == '500指数增强':
            df_fund = df_fund[df_fund['product_name'].str.contains('500')]
        else:
            return

    df_fund = df_fund.loc[df_fund['product_end_date'].isnull()].reset_index(drop=True) # 选择仍存续的基金
    df_fund = df_fund.loc[df_fund['product_start_date'].notnull()].reset_index(drop=True) # 删掉未成立的基金
    df_fund = df_fund.loc[df_fund['pm_end_date'].isnull()].reset_index(drop=True) # 选择仍在任的基金经理
    df_fund[['management_fee', 'trustee_fee']] /= 100 # 量纲调整为%
    df_fund.replace({"type": const.const.WIND_SECTOR_CODE_MAP}, inplace=True)
    if include_pm_info == False:
        df_fund.drop(columns=['pm_gender', 'pm_id', 'pm_name', 'pm_start_date', 'pm_end_date'], inplace=True)
        df_fund.drop_duplicates(inplace=True)
    df_fund['product_start_date'] = pd.to_datetime(df_fund['product_start_date']).dt.date
    df_fund['product_end_date'] = pd.to_datetime(df_fund['product_end_date']).dt.date
    if exclude_new_product:
        df_fund = df_fund[df_fund['product_start_date'].apply(lambda x: (datetime.date.today()-x).days > 90)]
    if exclude_small_product:
        all_product_NAV = wind_getMFAssetAllocation()
        all_product_NAV_recent = all_product_NAV.groupby(by=['product_id'], as_index=False)['date'].last()
        all_product_NAV = pd.merge(all_product_NAV[['product_id', 'date', 'net_asset']], all_product_NAV_recent,
                                   how='inner',
                                   on=['product_id', 'date'])
        df_fund = pd.merge(df_fund, all_product_NAV[['product_id', 'net_asset']], how='left', on='product_id')
        df_fund = df_fund[df_fund['net_asset'] > 3e7]
    dbconn.close()
    return df_fund

# ------------------------------------------------------
# 获取当前存续基金暂停申购赎回信息
# ------------------------------------------------------
def wind_getCurrentProductSuspendInfo(
    start_date,   # datetime.date, 起始日期
    end_date      # datetime.date, 截止日期
):
    assert isinstance(start_date, datetime.date), "start_date需为datetime.date类型"
    assert isinstance(end_date, datetime.date), "end_date需为datetime.date类型"
    dbconn = wind_connectWindDB()
    sql = "select a.S_INFO_WINDCODE as product_id, a.F_INFO_SUSPCHSTARTDT as suspend_start_date, a.F_INFO_SUSPCHANNDT as suspend_start_ann_date, " \
          "a.F_INFO_REPCHDT as suspend_end_date,a.F_INFO_REPCHANNDT as suspend_end_ann_date, a.F_INFO_PURCHASEUPLIMIT as trade_limit, " \
          "a.F_INFO_SUSPCHREASON as suspend_reason, a.F_INFO_SUSPCHTYPE as suspend_type_code " \
          "from ChinaMutualFundSuspendPchRedm a, ChinaMutualFundDescription b " \
          "where a.S_INFO_WINDCODE=b.F_INFO_WINDCODE and b.F_INFO_STATUS='101001000' " \
          "and a.F_INFO_SUSPCHSTARTDT <= {} and (a.F_INFO_REPCHDT is null or a.F_INFO_REPCHDT >= {}) "
    ret = pd.read_sql_query(sql.format(end_date.strftime('%Y%m%d'), start_date.strftime('%Y%m%d')), dbconn).rename(columns=str.lower)
    dbconn.close()
    return ret

# ------------------------------------------------------
# 获取券商理财产品列表
# ------------------------------------------------------
def wind_getFinancialProductList():
    dbconn = wind_connectWindDB()
    sql = 'select * from ChinaInhouseFundDescription'
    df_fund = pd.read_sql_query(sql, dbconn)
    df_fund.rename(columns={'f_info_windcode': 'product_id', 'f_info_name': 'product_name'}, inplace=True)
    dbconn.close()
    return df_fund

# ------------------------------------------------------
# 获取基金经理个人信息
# ------------------------------------------------------
def wind_getPMInfo(
        pm_id = None    # 基金经理ID，输入格式:str, 为None时，相当于获取全部基金经理信息
):
    dbconn = wind_connectWindDB()
    sql = "select F_INFO_FUNDMANAGER_ID as pm_id, F_INFO_FUNDMANAGER as pm_name, " \
          "F_INFO_MANAGER_GENDER as gender, F_INFO_MANAGER_BIRTHYEAR as birthyear, F_INFO_MANAGER_EDUCATION as education, " \
          "F_INFO_MANAGER_RESUME as resume " \
          "from ChinaMutualFundManager "
    sql_2 = "where F_INFO_FUNDMANAGER_ID = '{}'"
    if pm_id == None:
        df = pd.read_sql_query(sql, dbconn)
    else:
        df = pd.read_sql_query(sql+sql_2.format(pm_id), dbconn)
    df = df.drop_duplicates(['pm_id']).reset_index(drop=True) # resume字段类型是CLOB，无法使用Unique
    dbconn.close()
    return df

# ------------------------------------------------------
# 获取基金的财务报表信息
# Columns含义请参考CMFfairvalueChangeProfit，CMFIncome
# ------------------------------------------------------
def wind_getMFFinancialInfo(
        product_ids=None,     # product_ids基金代码，应为list格式（因数据库存储问题，优先使用场内代码），为None时，相当于获取全部基金
        companies = None       # 基金公司简称，list格式，如果company有赋值，则返回该公司旗下所有基金的数据，忽略product_ids变量的任何赋值
):
    dbconn = wind_connectWindDB()
    sql_1 = "select a.S_INFO_WINDCODE as product_id, d.F_INFO_NAME as product_name, e.S_INFO_COMPCODE as company_id, d.F_INFO_CORP_FUNDMANAGEMENTCOMP as company_short_name, e.COMP_SNAME as company_name, " \
            "d.F_INFO_MANAGEMENTFEERATIO as management_fee, d.F_INFO_CUSTODIANFEERATIO as trustee_fee, a.REPORT_PERIOD as dt, a.PRT_NETASSET as net_asset, " \
          "b.MGMT_EXP as management_exp, b.CUSTODIAN_EXP as trustee_exp, b.NET_PROFIT as net_profit, " \
          "b.STOCK_INV_INC, b.BOND_INV_INC, b.FUND_INV_INC, b.BOND_INT_INC, b.DVD_INC, " \
          "c.STOCK_CHANGE_FAIR_VALUE as stock_fv_chg, c.BOND_CHANGE_FAIR_VALUE as bond_fv_chg_exchange, c.BOND1_CHANGE_FAIR_VALUE as bond_fv_chg_bank, c.FUND_CHANGE_FAIR_VALUE as fund_fv_chg, " \
          "f.ANAL_INCOME as income, f.ANAL_AVGNAVRETURN as avg_income_return " \
          "from CMFBalanceSheet a, CMFIncome b, CMFfairvalueChangeProfit c, ChinaMutualFundDescription d, FundCompanyInsideHolder e, CMFFinancialIndicator f " \
          "where a.S_INFO_WINDCODE = d.F_INFO_WINDCODE and a.S_INFO_WINDCODE = b.S_INFO_WINDCODE and a.S_INFO_WINDCODE = c.F_INFO_WINDCODE and a.S_INFO_WINDCODE = f.S_INFO_WINDCODE " \
          "and a.REPORT_PERIOD = b.REPORT_PERIOD and a.REPORT_PERIOD = c.REPORT_PERIOD and a.REPORT_PERIOD = f.REPORT_PERIOD and d.F_INFO_CORP_FUNDMANAGEMENTID = e.S_INFO_COMPCODE " \
          "and d.F_INFO_ISINITIAL = 1" # 仅考虑初始份额
    sql_codes = "and a.S_INFO_WINDCODE in {} "
    sql_company = "and d.F_INFO_CORP_FUNDMANAGEMENTCOMP in {} "
    sql_2 = "order by a.S_INFO_WINDCODE, a.REPORT_PERIOD"

    if companies != None:
        if len(companies) == 1:  # list长度为1时候无法使用tuple
            fund = pd.read_sql_query(sql_1 + sql_company.format('\'' + companies[0] + '\'') + sql_2, dbconn)
        else:
            fund = pd.read_sql_query(sql_1 + sql_company.format(tuple(companies)) + sql_2, dbconn)
    else:
        if product_ids == None:  # 空的时候读取全部基金
            fund = pd.read_sql_query(sql_1 + sql_2, dbconn)
        elif len(product_ids) == 1:  # list长度为1时候无法使用tuple
            fund = pd.read_sql_query(sql_1 + sql_codes.format('\'' + product_ids[0] + '\'') + sql_2, dbconn)
        elif len(product_ids) < 1000:
            fund = pd.read_sql_query(sql_1 + sql_codes.format(tuple(product_ids)) + sql_2, dbconn)
        else:  # 长度超过1000，读全部基金，再loc
            fund = pd.read_sql_query(sql_1 + sql_2, dbconn)
            fund = fund.loc[fund['product_id'].isin(product_ids)].reset_index(drop=True)

    fund.drop_duplicates(subset=['product_id', 'dt'], inplace=True) # 涉及FundCompanyInsideHolder无法避免重复值
    fund.rename(columns={'dt':'date'}, inplace=True)
    fund['date'] = pd.to_datetime(fund['date']).dt.date
    fund['bond_fv_chg'] = fund['bond_fv_chg_exchange'].fillna(0) + fund['bond_fv_chg_bank'].fillna(0)
    del fund['bond_fv_chg_exchange'], fund['bond_fv_chg_bank']
    col = ['net_asset','management_exp','trustee_exp','net_profit','stock_inv_inc','bond_inv_inc','fund_inv_inc','bond_int_inc','dvd_inc','stock_fv_chg','fund_fv_chg','bond_fv_chg','income']
    fund[col] /= 1e8 # 单位调整为亿元
    fund['avg_income_return'] /= 100
    fund = fund.reset_index(drop=True)
    # 添加基金类型
    fund_type = wind_getMFtype()
    fund = pd.merge(fund, fund_type, how='left', on='product_id')
    dbconn.close()
    return fund

# ------------------------------------------------------
# 获取基金公司的信息，以财务报表信息为主
# 只有部分公司会披露部分时点的报表信息
# ------------------------------------------------------
def wind_getMFCompanyInfo(
        companies = None     # 基金公司简称（如中信证券），输入格式:list, 为None时，相当于获取全部基金公司信息
):
    dbconn = wind_connectWindDB()
    sql_1 = "select a.S_INFO_COMPCODE as company_id, a.COMP_SNAME as company_name, b.REPORT_PERIOD as dt, " \
          "b.TOT_OPER_REV as revenue, b.NET_PROFIT_INCL_MIN_INT_INC as net_profit, b.EBIT as ebit, b.S_FA_EPS_BASIC as eps_basic," \
          "c.tot_assets as total_asset, c.tot_liab as total_liability " \
          "from FundCompanyInsideHolder a, FundIncome b, FundBalanceSheet c " \
          "where a.S_INFO_COMPCODE = b.S_INFO_COMPCODE and a.S_INFO_COMPCODE = c.S_INFO_COMPCODE " \
          "and b.REPORT_PERIOD = c.REPORT_PERIOD " \
          "and b.statement_type = '408001000' and c.statement_type = '408001000' " #statement_type=408001000,合并报表
    sql_2 = "order by a.S_INFO_COMPCODE, b.REPORT_PERIOD"

    company_info = pd.read_sql_query(sql_1 + sql_2, dbconn) # 读取全部基金公司
    company_info.drop_duplicates(subset=['company_id', 'dt'], inplace=True) # FundCompanyInsideHolder会重复多行，显示有多个股东
    company_info.reset_index(drop=True, inplace=True)
    company_info['net_asset'] = company_info['total_asset'] - company_info['total_liability']
    company_info['ROE'] = company_info['net_profit'] / company_info['net_asset']
    company_info.rename(columns={'dt':'date'}, inplace=True)
    company_info['date'] = pd.to_datetime(company_info['date']).dt.date
    company_name = wind_getMFCompanyName()
    company_info = pd.merge(company_info, company_name[['company_id', 'company_short_name']], how='left', on=['company_id'])
    if companies != None:
        company_info = company_info.loc[company_info['company_short_name'].isin(companies)].reset_index(drop=True)
    dbconn.close()
    return company_info

# ------------------------------------------------------
# 获取基金公司股东列表及对应的持股比例
# ------------------------------------------------------
def wind_getMFCurrentStakeHolder(
    companies = None     # 基金公司简称（如中信证券），输入格式:str, 为None时，相当于获取全部基金公司信息
):
    dbconn = wind_connectWindDB()
    sql = "select a.S_INFO_COMPCODE as company_id, a.COMP_SNAME as company_name, " \
          "a.S_HOLDER_ENDDATE as sdate, a.S_HOLDER_ANAME as holder_name, a.S_HOLDER_PCT as holder_pct " \
          "from FundCompanyInsideHolder a " \
          "order by a.S_INFO_COMPCODE, a.S_HOLDER_ENDDATE"
    df = pd.read_sql_query(sql, dbconn)
    df_shortname = wind_getMFCompanyName()
    df = pd.merge(df, df_shortname[['company_id', 'company_short_name']], how='left', on='company_id')
    df.rename(columns={'sdate': 'date'}, inplace=True)
    df['date'] = pd.to_datetime(df['date']).dt.date
    dbconn.close()
    if companies == None:
        return df
    else:
        return df.loc[df['company_short_name'].isin(companies)].reset_index(drop=True)

# -------------------------------
# 获取基金公司管理层变动信息
# -------------------------------
def wind_getMFCompanyExecutivesAdjustInfo(
    start_date,  # 变动起始日期
    end_date     # 变动截止日期
):
    dbconn = wind_connectWindDB()
    sql = "select a.ANN_DATE as ann_date, b.COMP_NAME as company_name, a.S_INFO_MANAGER_NAME as exec_name, " \
          "a.S_INFO_MANAGER_POST as exec_position, a.S_INFO_MANAGER_STARTDATE as exec_start_date, " \
          "a.S_INFO_MANAGER_LEAVEDATE as exec_end_date, b.COMP_TYPE as company_type from CFundManagement a, CFundIntroduction b " \
          "where a.S_INFO_COMPCODE=b.COMP_ID "
    sql += "and ((a.S_INFO_MANAGER_STARTDATE between {} and {}) or (a.S_INFO_MANAGER_LEAVEDATE between {} and {})) "
    df = pd.read_sql_query(sql.format(start_date.strftime('%Y%m%d'), end_date.strftime('%Y%m%d'), start_date.strftime('%Y%m%d'),
                                      end_date.strftime('%Y%m%d')), dbconn).rename(columns=str.lower)
    # FIXME 因部分日期列存在位数不齐的情况，暂保留原始字符串，不转换为datetime.date类型
    dbconn.close()
    return df

# ------------------------------------------------------
# 获取公募基金类型，Wind一级分类和二级分类
# ------------------------------------------------------
def wind_getMFtype():
    dbconn = wind_connectWindDB()
    sql_type_1 = ("select a.F_INFO_WINDCODE as product_id, b.industriesname as type_name "
                  "from ChinaMutualFundSector a, AShareIndustriesCode b "
                  "where substr(a.s_info_sector, 1, 8) = substr(b.industriescode, 1, 8) and b.levelnum = 4 "
                  "and substr(a.s_info_sector, 1, 6) = '200101' "  # 200101：基金投资范围板块
                  "order by a.S_INFO_SECTOREXITDT ")
    df_type_1 = pd.read_sql_query(sql_type_1, dbconn).rename(columns={'type_name': 'type_name_lv1'})  # 一级分类
    df_type_1 = df_type_1.drop_duplicates(subset=['product_id'], keep='last').reset_index(drop=True)  # 不能用CUR_SIGN=1，而是要对截止日期排序并去重，这样可以保留已清算基金的类型

    sql_type_2 = ("select a.F_INFO_WINDCODE as product_id, b.industriesname as type_name "
                  "from ChinaMutualFundSector a, AShareIndustriesCode b "
                  "where substr(a.s_info_sector, 1, 10) = substr(b.industriescode, 1, 10) and b.levelnum = 5 "
                  "and substr(a.s_info_sector, 1, 6) = '200101' "  # 200101：基金投资范围板块
                  "order by a.S_INFO_SECTOREXITDT ")
    df_type_2 = pd.read_sql_query(sql_type_2, dbconn).rename(columns={'type_name': 'type_name_lv2'})  # 一级分类
    df_type_2 = df_type_2.drop_duplicates(subset=['product_id'], keep='last').reset_index(drop=True)  # 不能用CUR_SIGN=1，而是要对截止日期排序并去重，这样可以保留已清算基金的类型
    result = pd.merge(df_type_1, df_type_2, how='outer', on='product_id')
    dbconn.close()
    return result

# ------------------------------------------------------
# 获取基金发行信息
# ------------------------------------------------------
def wind_getMFIssueinfo(
        date,                # 开始日期，发行/成立日期
        issue=True           # True表示发行日期，False表示成立日期
):
    assert (type(date) == datetime.date), '日期输入格式需为datetime.date'
    sql1 = ("select a.f_info_windcode as product_id, a.f_info_name as product_name, "
           "b.F_INFO_FUNDMANAGER as pm_name, b.F_INFO_FUNDMANAGER_ID as pm_id, "
           "a.f_info_corp_fundmanagementcomp as company_short_name, "
           "a.f_info_issuedate as product_issuedate, a.f_info_setupdate as product_start_date, "
           "a.max_num_coltarget as target_nav, a.f_issue_totalunit as issue_nav, "
           "c.s_info_sector as type_id, d.industriesname as type_name "
           "from (select * from ChinaMutualFundDescription)a, (select * from ChinaMutualFundManager)b, "
           "(select * from ChinaMutualFundSector)c, (select * from AShareIndustriesCode)d "
           "where a.f_info_windcode = c.f_info_windcode and a.f_info_windcode=b.f_info_windcode "
           "and substr(c.s_info_sector, 1, 10) = substr(d.industriescode, 1, 10) and d.levelnum = 5 "# 二者搭配使用，四级分类
           "and substr(c.s_info_sector, 1, 6) = '200101' " #200101：基金投资范围板块
           "and c.cur_sign = '1' and a.F_INFO_ISINITIAL = 1 " # 最新分类，只要A份额
           "and b.F_INFO_MANAGER_LEAVEDATE is NULL ") # 选取现任基金经理
    sql_issue = "and a.f_info_issuedate > {} "
    sql_setup = "and a.f_info_setupdate > {} "
    dbconn = wind_connectWindDB()

    date = datetime.datetime.strftime(date, format='%Y%m%d')

    if issue:
        df = pd.read_sql(sql1+sql_issue.format(date), dbconn)
    else:
        df = pd.read_sql(sql1+sql_setup.format(date), dbconn)

    df_new = df.groupby(['product_id'])['pm_name'].apply(lambda x: x.str.cat(sep=',')).to_frame().reset_index()  # 多个pm，多行转一行
    df.drop(['pm_name', 'pm_id'], axis=1, inplace=True) # 如果不做pm的匹配，不需要pm_id
    df.drop_duplicates(inplace=True)
    df_new = pd.merge(df_new, df, on=['product_id'], how='left')
    df_new['product_issuedate'] = pd.to_datetime(df_new['product_issuedate']).dt.date
    df_new['product_start_date'] = pd.to_datetime(df_new['product_start_date']).dt.date
    df_new = df_new.sort_values(by=['product_issuedate']).reset_index(drop=True)
    dbconn.close()
    return df_new

# ------------------------------------------------------
# 获取ETF基金的投资范围分类以及挂钩指数信息
# 股票型ETF存在子类型，同一产品可能出现多条分类记录，使用level_2层级筛选时，股票型ETF会拆分成子类型进行展示
# ------------------------------------------------------
def wind_getETFInvestType(
    invest_type_level=None  # 对ETF投资分类标签层级进行筛选，默认为None不进行筛选
):
    assert invest_type_level in ['level_1', 'level_2', None], "invest_type_level不可用，需为'level_1', 'level_2'或None"
    dbconn = wind_connectWindDB()
    sql = "SELECT a.S_INFO_WINDCODE AS product_id, a.S_INFO_SECTOR AS etf_invest_type_id, a.S_INFO_NAME AS etf_invest_type, " \
          "d.S_INFO_INDEXWINDCODE AS benchmark_id, d.S_INFO_NAME AS benchmark_name FROM ChinaETFInvestClass a " \
          "LEFT JOIN (SELECT b.S_INFO_WINDCODE, b.S_INFO_INDEXWINDCODE, b.CUR_SIGN, c.S_INFO_NAME FROM ChinaMutualFundBenchMark b " \
          "LEFT JOIN WindCustomCode c on b.S_INFO_INDEXWINDCODE=c.S_INFO_WINDCODE WHERE b.CUR_SIGN=1) d ON a.S_INFO_WINDCODE=d.S_INFO_WINDCODE "
    df = pd.read_sql_query(sql, dbconn).rename(columns=str.lower)
    dbconn.close()
    # 存在少量股票型ETF缺失level_2标签
    if invest_type_level == 'level_1':
        df = df[df['etf_invest_type_id'].isin(const.const.WIND_ETF_INVEST_TYPE_LEVEL_1_SECTOR_CODE_MAP.keys())]
        df.rename(columns={'etf_invest_type_id': 'etf_invest_type_id_level_1', 'etf_invest_type': 'etf_invest_type_level_1'}, inplace=True)
    elif invest_type_level == 'level_2':
        df = df[df['etf_invest_type_id'].isin(const.const.WIND_ETF_INVEST_TYPE_LEVEL_2_SECTOR_CODE_MAP.keys())]
        df.rename(columns={'etf_invest_type_id': 'etf_invest_type_id_level_2', 'etf_invest_type': 'etf_invest_type_level_2'}, inplace=True)
    return df

# ------------------------------------------------------
# 获取基金份额信息，包括上市流通份额和总份额
# ------------------------------------------------------
def wind_getMFShareInfo(
    latest_only=True, # 默认选取各产品最新份额信息(cur_sign=1), 不使用日期进行筛选
    start_date=None,  # 起始日期
    end_date=None,    # 截止日期
    product_ids=None  # list, 对公募基金产品进行筛选，默认为None表示全选
):
    dbconn = wind_connectWindDB()
    sql = "SELECT a.CHANGE_DATE, a.F_INFO_WINDCODE, b.F_INFO_NAME, a.F_INFO_SHARE, a.FUNDSHARE, a.CHANGEREASON " \
          "FROM CHINAMUTUALFUNDSHARE a, ChinaMutualFundDescription b " \
          "WHERE a.F_INFO_WINDCODE=b.F_INFO_WINDCODE "
    if product_ids:
        assert isinstance(product_ids, list), "product_ids must be an instance of list"
        sql += "AND a.F_INFO_WINDCODE='{}' ".format(product_ids[0]) if len(product_ids) == 1 else "AND a.F_INFO_WINDCODE IN ({}) ".format(','.join("'%s'" % x for x in product_ids))
    if latest_only:
        assert (start_date is None) and (end_date is None), "获取最新份额数据时，请勿传入start_date和end_date"
        sql += "AND a.CUR_SIGN=1 ORDER BY a.CHANGE_DATE, a.F_INFO_WINDCODE"
        df = pd.read_sql_query(sql, dbconn).rename(columns=str.lower)
    else:
        assert isinstance(start_date, datetime.date), "start_date must be an instance of datetime.date"
        assert isinstance(end_date, datetime.date), "end_date must be an instance of datetime.date"
        assert latest_only == False, "使用日期筛选时latest_only需设置为False"
        sql += "AND a.CHANGE_DATE BETWEEN {} AND {} ORDER BY a.CHANGE_DATE, a.F_INFO_WINDCODE"
        df = pd.read_sql_query(sql.format(start_date.strftime('%Y%m%d'), end_date.strftime('%Y%m%d')), dbconn).rename(columns=str.lower)
    df.rename(columns={
        'change_date': 'date',
        'f_info_windcode': 'product_id',
        'f_info_name': 'product_name',
        'f_info_share': 'product_liquid_share',
        'fundshare': 'product_total_share',
        'changereason': 'share_chg_reason'
    }, inplace=True)
    df['date'] = pd.to_datetime(df['date']).dt.date
    dbconn.close()
    return df

# ------------------------------
# 获取公募基金份额拆分与折算信息
# ------------------------------
def wind_getMFShareSplitInfo(
    start_date,  # 起始日期
    end_date     # 截止日期
):
    assert isinstance(start_date, datetime.date), "start_date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "end_date must be an instance of datetime.date"
    dbconn = wind_connectWindDB()
    sql = "SELECT a.S_INFO_WINDCODE AS product_id, b.F_INFO_NAME AS product_name, a.F_INFO_SPLITTYPE AS share_split_type, " \
          "a.F_INFO_SHARETRANSDATE AS dt, a.F_INFO_SPLITINC AS share_split_conversion_ratio, a.F_INFO_SPLITTYPECODE AS share_split_type_id " \
          "FROM CMFundSplit a, ChinaMutualFundDescription b " \
          "WHERE a.S_INFO_WINDCODE=b.F_INFO_WINDCODE AND a.F_INFO_SHARETRANSDATE >= '{}' AND a.F_INFO_SHARETRANSDATE <= '{}' "
    df = pd.read_sql_query(sql.format(start_date.strftime('%Y%m%d'), end_date.strftime('%Y%m%d')), dbconn).rename(columns=str.lower)
    df.rename(columns={'dt': 'date'}, inplace=True)
    df['date'] = pd.to_datetime(df['date']).dt.date
    dbconn.close()
    return df

# ------------------------------
# 获取公募基金产品各类份额的代码
# ------------------------------
def wind_getMFRelatedProductMap():
    # s_info_windcode列对应初始基金份额(通常为A份额)，s_info_ralatedcode列对应非初始基金份额，该表仅记录存在多个份额映射关系的产品
    dbconn = wind_connectWindDB()
    sql = "select a.S_INFO_WINDCODE as initial_product_id, a.S_INFO_RALATEDCODE as mapped_product_id from RalatedSecuritiesCode a " \
          "where a.S_RELATION_TYPCODE='115002101' and a.S_INFO_INVALID_DT is null "
    df = pd.read_sql_query(sql, dbconn).rename(columns=str.lower)
    dbconn.close()
    return df

# ----------------------------
# 获取公募基金持有人结构
# ----------------------------
def wind_getMFLatestHoldingStructure(
    date   # 考察日期
):
    assert isinstance(date, datetime.date), "date需为datetime.date类型"
    dbconn = wind_connectWindDB()
    sql = "select S_INFO_WINDCODE as product_id, END_DT as dt, SCOPE as scope, HOLDER_NUMBER as holder_num, HOLDER_AVGHOLDING as avg_holding_share, " \
           "HOLDER_INSTITUTION_HOLDING as institution_holding_share, HOLDER_INSTITUTION_HOLDINGPCT as institution_holding_ratio, HOLDER_PERSONAL_HOLDING as retail_holding_share, " \
           "HOLDER_PERSONAL_HOLDINGPCT as retail_holding_ratio, HOLDER_MNGEMP_HOLDING as employee_holding_share, HOLDER_MNGEMP_HOLDINGPCT as employee_holding_ratio " \
           "from CMFHolderStructure where END_DT >= '{}' and END_DT <= '{}' "
    df = pd.read_sql_query(sql.format((date - datetime.timedelta(days=270)).strftime('%Y%m%d'), date.strftime('%Y%m%d')), dbconn).rename(columns=str.lower)
    dbconn.close()
    df.rename(columns={'dt': 'date'}, inplace=True)
    df['date'] = pd.to_datetime(df['date']).dt.date
    df = df.groupby(['product_id'], as_index=False).apply(lambda x: x[x['date'] == x['date'].max()])
    return df

# -----------------------------------------------------------------------------
# 3. 收益函数（股票/基金/指数)
# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------

# ------------------------------------------------------
# 获取A股股票的交易数据，包括收盘价，成交量，换手率等
# ------------------------------------------------------
def wind_getAShareStockTradeData(
    stock_ids=None,        # 股票代码，应为list格式，为None时，相当于获取全部股票
    start_date=None,       # datetime.date, 起始日期, 仅当on_dates参数为None时生效
    end_date=None,         # datetime.date, 截止日期, 仅当on_dates参数为None时生效
    on_dates=None          # list, 日期序列, 启用时取全量股票数据再筛选，忽略start_date, end_dates筛选
):
    dbconn = wind_connectWindDB()
    sql_1 = "select a.S_INFO_WINDCODE as stock_id, c.S_INFO_NAME as stock_name, a.TRADE_DT as trade_date, " \
            "a.s_tech_tvma6, a.s_tech_tvma20, a.s_tech_tvma60, a.s_tech_mktfaciind, " \
            "b.S_DQ_CLOSE as close, S_DQ_ADJCLOSE as adj_close " \
            "from TurnoverTechnicalFactor a, AShareEODPrices b, AShareDescription c " \
            "where b.S_INFO_WINDCODE = c.S_INFO_WINDCODE and a.S_INFO_WINDCODE = b.S_INFO_WINDCODE and a.TRADE_DT = b.TRADE_DT "
    sql_codes = "and a.S_INFO_WINDCODE in ({}) "
    sql_on_dates = "and a.TRADE_DT in ({}) "
    sql_date_between = "and a.TRADE_DT >= '{}' and a.TRADE_DT <= '{}' "

    # on_dates不为None，取全量股票数据，忽略stock_ids, start_date, end_dates筛选
    if on_dates:
        assert (start_date is None) and (end_date is None), "当启用on_dates参数时，取全量股票数据再筛选，同时start_date,end_date参数均需设为None"
        assert isinstance(on_dates, list), "on_dates参数类型需为list"
        if len(on_dates) < 500:
            df = pd.read_sql_query(sql_1 + sql_on_dates.format(",".join(["'%s'" % date.strftime("%Y%m%d") for date in on_dates])), dbconn).rename(columns=str.lower)
        else:  # 长度超过500, 分批读入
            date_list = cal.basicCal_cut(on_dates, 500)
            temp_list = []
            for dl in date_list:
                df = pd.read_sql_query(sql_1 + sql_on_dates.format(",".join(["'%s'" % date.strftime("%Y%m%d") for date in dl])), dbconn).rename(columns=str.lower)
                temp_list.append(df)
            df = pd.concat(temp_list, axis=0)
        if stock_ids:
            assert isinstance(stock_ids, list), "stock_ids参数类型需为list"
            df = df[df['stock_id'].isin(stock_ids)]

    # 若on_dates为None，再进行stock_ids, start_date, end_dates筛选
    else:
        # 如果start_date和end_date均不为None，进行日期区间筛选
        if (start_date is not None) and (end_date is not None):
            assert isinstance(start_date, datetime.date) and isinstance(end_date, datetime.date), "start_date和end_date类型需为datetime.date"
            sql_1 += sql_date_between.format(start_date.strftime("%Y%m%d"), end_date.strftime("%Y%m%d"))
        # 股票筛选，stock_ids为None的时候读取全部股票
        if stock_ids is None:
            df = pd.read_sql_query(sql_1, dbconn).rename(columns=str.lower)
        elif len(stock_ids) < 500:
            assert isinstance(stock_ids, list), "stock_ids参数类型需为list"
            df = pd.read_sql_query(sql_1 + sql_codes.format(",".join(["'%s'" % s_id for s_id in stock_ids])), dbconn).rename(columns=str.lower)
        else:  # 长度超过500, 分批读入
            assert isinstance(stock_ids, list), "stock_ids参数类型需为list"
            stock_id_list = cal.basicCal_cut(stock_ids, 500)
            temp_list = []
            for sl in stock_id_list:
                df = pd.read_sql_query(sql_1 + sql_codes.format(",".join(["'%s'" % s_id for s_id in sl])), dbconn).rename(columns=str.lower)
                temp_list.append(df)
            df = pd.concat(temp_list, axis=0)
    df['trade_date'] = pd.to_datetime(df['trade_date']).dt.date
    df = df.sort_values(['stock_id', 'trade_date']).reset_index(drop=True)
    scale_columns = ['s_tech_tvma6','s_tech_tvma20','s_tech_tvma60','s_tech_mktfaciind']
    df[scale_columns] = df[scale_columns]*1e4
    dbconn.close()
    return df

# ------------------------------------------------------
# 获取H股股票的交易数据，包括收盘价，成交量等
# ------------------------------------------------------
def wind_getHKShareStockTradeData(
    stock_ids=None,        # 股票代码，应为list格式，为None时，相当于获取全部股票
    start_date=None,       # datetime.date, 起始日期, 仅当on_dates参数为None时生效
    end_date=None          # datetime.date, 截止日期, 仅当on_dates参数为None时生效
):
    dbconn = wind_connectWindDB()
    sql_1 = "select a.S_INFO_WINDCODE as stock_id, b.S_INFO_NAME as stock_name, a.TRADE_DT as trade_date, a.S_DQ_CLOSE as close, " \
            "S_DQ_ADJCLOSE as adj_close from HKshareEODPrices a, HKShareDescription b " \
            "where a.S_INFO_WINDCODE = b.S_INFO_WINDCODE "
    sql_codes = "and a.S_INFO_WINDCODE in ({}) "
    sql_date_between = "and a.TRADE_DT >= '{}' and a.TRADE_DT <= '{}' "
    # 如果start_date和end_date均不为None，进行日期区间筛选
    if (start_date is not None) and (end_date is not None):
        assert isinstance(start_date, datetime.date) and isinstance(end_date, datetime.date), "start_date和end_date类型需为datetime.date"
        sql_1 += sql_date_between.format(start_date.strftime("%Y%m%d"), end_date.strftime("%Y%m%d"))
    # 股票筛选，stock_ids为None的时候读取全部股票
    if stock_ids is None:
        df = pd.read_sql_query(sql_1, dbconn).rename(columns=str.lower)
    elif len(stock_ids) < 500:
        assert isinstance(stock_ids, list), "stock_ids参数类型需为list"
        df = pd.read_sql_query(sql_1 + sql_codes.format(",".join(["'%s'" % s_id for s_id in stock_ids])), dbconn).rename(columns=str.lower)
    else:  # 长度超过500, 分批读入
        assert isinstance(stock_ids, list), "stock_ids参数类型需为list"
        stock_id_list = cal.basicCal_cut(stock_ids, 500)
        temp_list = []
        for sl in stock_id_list:
            df = pd.read_sql_query(sql_1 + sql_codes.format(",".join(["'%s'" % s_id for s_id in sl])), dbconn).rename(
                columns=str.lower)
            temp_list.append(df)
        df = pd.concat(temp_list, axis=0)

    df['trade_date'] = pd.to_datetime(df['trade_date']).dt.date
    df = df.sort_values(['stock_id', 'trade_date']).reset_index(drop=True)
    dbconn.close()
    return df

# --------------------------
# A股强弱与趋向技术指标(不复权)
# --------------------------
def wind_getStockIntensityTrendTechIndicator(
    stock_ids=None,        # 股票代码，应为list格式，为None时，相当于获取全部股票
    start_date=None,       # datetime.date, 起始日期, 仅当on_dates参数为None时生效
    end_date=None,         # datetime.date, 截止日期, 仅当on_dates参数为None时生效
    on_dates=None          # list, 日期序列, 启用时取全量股票数据再筛选，忽略start_date, end_dates筛选
):
    dbconn = wind_connectWindDB()
    sql_1 = "select a.S_INFO_WINDCODE as stock_id, b.S_INFO_NAME as stock_name, a.TRADE_DT as trade_date, " \
            "a.MARKET, a.STRENGTH, a.WEAKKNESS, a.BOTTOMING_B, a.BOTTOMING_D, a.DMI_PDI, a.DMI_MDI, a.DMI_ADX, " \
            "a.DMI_ADXR, a.EXPMA, a.MA_5D, a.MA_10D, a.MA_20D, a.MA_30D, a.MA_60D, a.MA_120D, a.MA_250D, " \
            "a.MACD_DIFF, a.MACD_DEA, a.MACD_MACD, a.BBI, a.DMA_DDD, a.DMA_AMA, a.MTM, a.MTM_MTMMA, a.PRICEOSC, " \
            "a.TRIX, a.TRMA, a.SAR from Ashareintensitytrend a, AShareDescription b " \
            "where a.S_INFO_WINDCODE = b.S_INFO_WINDCODE "
    sql_codes = "and a.S_INFO_WINDCODE in ({}) "
    sql_on_dates = "and a.TRADE_DT in ({}) "
    sql_date_between = "and a.TRADE_DT >= '{}' and a.TRADE_DT <= '{}' "

    # on_dates不为None，取全量股票数据，忽略stock_ids, start_date, end_dates筛选
    if on_dates:
        assert (start_date is None) and (end_date is None), "当启用on_dates参数时，取全量股票数据再筛选，同时start_date,end_date参数均需设为None"
        assert isinstance(on_dates, list), "on_dates参数类型需为list"
        if len(on_dates) < 500:
            df = pd.read_sql_query(sql_1 + sql_on_dates.format(",".join(["'%s'" % date.strftime("%Y%m%d") for date in on_dates])), dbconn).rename(columns=str.lower)
        else:  # 长度超过500, 分批读入
            date_list = cal.basicCal_cut(on_dates, 500)
            temp_list = []
            for dl in date_list:
                df = pd.read_sql_query(sql_1 + sql_on_dates.format(",".join(["'%s'" % date.strftime("%Y%m%d") for date in dl])), dbconn).rename(columns=str.lower)
                temp_list.append(df)
            df = pd.concat(temp_list, axis=0)
        if stock_ids:
            assert isinstance(stock_ids, list), "stock_ids参数类型需为list"
            df = df[df['stock_id'].isin(stock_ids)]
    # 若on_dates为None，再进行stock_ids, start_date, end_dates筛选
    else:
        # 如果start_date和end_date均不为None，进行日期区间筛选
        if (start_date is not None) and (end_date is not None):
            assert isinstance(start_date, datetime.date) and isinstance(end_date, datetime.date), "start_date和end_date类型需为datetime.date"
            sql_1 += sql_date_between.format(start_date.strftime("%Y%m%d"), end_date.strftime("%Y%m%d"))
        # 股票筛选，stock_ids为None的时候读取全部股票
        if stock_ids is None:
            df = pd.read_sql_query(sql_1, dbconn).rename(columns=str.lower)
        elif len(stock_ids) < 500:
            assert isinstance(stock_ids, list), "stock_ids参数类型需为list"
            df = pd.read_sql_query(sql_1 + sql_codes.format(",".join(["'%s'" % s_id for s_id in stock_ids])), dbconn).rename(columns=str.lower)
        else:  # 长度超过500, 分批读入
            assert isinstance(stock_ids, list), "stock_ids参数类型需为list"
            stock_id_list = cal.basicCal_cut(stock_ids, 500)
            temp_list = []
            for sl in stock_id_list:
                df = pd.read_sql_query(sql_1 + sql_codes.format(",".join(["'%s'" % s_id for s_id in sl])), dbconn).rename(columns=str.lower)
                temp_list.append(df)
            df = pd.concat(temp_list, axis=0)
    df['trade_date'] = pd.to_datetime(df['trade_date']).dt.date
    df = df.sort_values(['stock_id', 'trade_date']).reset_index(drop=True)
    dbconn.close()
    return df

# ------------------------------------------------------
# 计算所有申万一级行业或恒生一级行业某两天之间的收益率
# ------------------------------------------------------
def wind_getIndustryReturn(
        date1,
        date2,
        vendor    # 数据提供商，输入格式:str，'SW' or 'HS''
):
    assert (type(date1) == datetime.date), '日期输入格式需为datetime.date'
    assert (type(date2) == datetime.date), '日期输入格式需为datetime.date'
    assert vendor in ("SW", "HS"), '数据提供商目前支持SW(申万)/HS(恒生港股)'

    vendor_index_code_mapping = {
        'SW': const.const.SW_INDUSTRY_CODE_LEVEL_1,
        'HS': const.const.HSHK_INDUSTRY_CODE_LEVEL_1
    }
    industry_name_cn_to_en_mapping = {
        'SW': const.const.SW_INDUSTRY_NAME_CN_TO_EN,
        'HS': const.const.HK_INDUSTRY_NAME_CN_TO_EN
    }
    index = wind_getThirdPartyStockIndexIndustryData(vendor, 1, date1, date2, 'D')[['date', 'close_price', 'index_code']]
    index = index.loc[(index['date'] == date1) | (index['date'] == date2)].sort_values(['index_code','date']).reset_index(drop=True)
    ret = index.groupby(['index_code'], as_index=True).apply(lambda x: x['close_price']/x['close_price'].shift(1) - 1).reset_index().rename(columns={'close_price':'return'})
    ret['date'] = index['date']
    ret = ret[['date','index_code','return']]
    ret = ret.loc[ret['date'] == date2]
    ret = ret.rename(columns={'index_code': 'industry'})
    ret = ret.replace({'industry': vendor_index_code_mapping[vendor]})
    ret = ret.replace({'industry': industry_name_cn_to_en_mapping[vendor]})
    ret = ret[['industry', 'return']]
    ret['start_date'] = date1
    ret['end_date'] = date2
    return ret

# ------------------------------------------------------
# 获取A股票在某一时段的日度/周度/月度/季度收益率
# 日度收益率的日期为每天，周度收益率的日期为每周最后一个交易日，以此类推
# ------------------------------------------------------
def wind_getASharePeriodicReturn(
        start_date,     # 起始日期，输入格式:datetime.date
        end_date,       # 结束日期，输入格式:datetime.date
        period = 'Q',     # 频率，D 日度，W 周度，M 月度
        stock_ids=None  # 股票代码，输入格式：list，None代表取所有股票
):
    assert isinstance(start_date, datetime.date), "start_date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "end_date must be an instance of datetime.date"

    dbconn = wind_connectWindDB()
    start_date = start_date.strftime("%Y%m%d")
    end_date = end_date.strftime("%Y%m%d")

    sql_D = "select S_INFO_WINDCODE as stock_id, TRADE_DT as dt, PCT_CHANGE_D as return " \
            "from AShareYield where TRADE_DT >= '{}' and TRADE_DT <= '{}' "
    sql_W = "select S_INFO_WINDCODE as stock_id, TRADE_DT as dt, S_WQ_PCTCHANGE as return " \
            "from AShareWeeklyYield where TRADE_DT >= '{}' and TRADE_DT <= '{}' "
    sql_M = "select S_INFO_WINDCODE as stock_id, TRADE_DT as dt, S_MQ_PCTCHANGE as return " \
            "from AShareMonthlyYield where TRADE_DT >= '{}' and TRADE_DT <= '{}' "
    sql_codes = "and S_INFO_WINDCODE in {}"

    sqlDict = {
        'D' : sql_D,
        'W' : sql_W,
        'M' : sql_M,
        'Q' : sql_M
    }

    if stock_ids == None:  # 空的时候读取全部基金
        df = pd.read_sql_query(sqlDict[period].format(start_date, end_date), dbconn)
    elif len(stock_ids) == 1:  # list长度为1时候无法使用tuple
        df = pd.read_sql_query(sqlDict[period].format(start_date, end_date) + sql_codes.format('\'' + stock_ids[0] + '\''), dbconn)
    elif len(stock_ids) < 1000:
        df = pd.read_sql_query(sqlDict[period].format(start_date, end_date) + sql_codes.format(tuple(stock_ids)), dbconn)
    else:  # 长度超过1000，读全部基金，再loc
        df = pd.read_sql_query(sqlDict[period].format(start_date, end_date), dbconn)
        df = df.loc[df['stock_id'].isin(stock_ids)].reset_index(drop=True)
    df.rename(columns={'dt':'date'}, inplace=True)
    df['date'] = pd.to_datetime(df['date']).dt.date
    df = df.sort_values(['stock_id', 'date']).reset_index(drop=True)
    df['return'] /= 100

    if period == 'Q':
        df['date'] = pd.to_datetime(df['date'])
        df['year'] = df['date'].dt.year
        df['quarter'] = df['date'].dt.quarter
        result = df.groupby(['stock_id', 'year', 'quarter']).apply(lambda x: (1+x['return']).prod() - 1).to_frame().reset_index().rename(columns={0: 'return'})
        df_date = df.drop_duplicates(subset=['year', 'quarter'], keep='last').reset_index(drop=True)
        result = pd.merge(result, df_date[['date', 'year', 'quarter']], how='left', on=['year','quarter'])
        del result['year'], result['quarter']
        result['date'] = pd.to_datetime(result['date']).dt.date
    else:
        result = df
    dbconn.close()
    return result

# ------------------------------------------------------
#  获取A股日行情估值指标及成交额指标
#  目前只取了部分指标：total_mv, floating_mv, pe_ttm, pb, trade_amount_60days
#  所有指标单位为：元
# ------------------------------------------------------
def wind_getAShareDailyValuationIndicators(
    start_date,   # DateTime.date instance
    end_date,   # DateTime.date instance
    stock_ids=None
):
    assert isinstance(start_date, datetime.date), "date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "date must be an instance of datetime.date"
    start_date = start_date.strftime("%Y%m%d")
    end_date = end_date.strftime("%Y%m%d")
    dbconn = wind_connectWindDB()
    if stock_ids:
        assert isinstance(stock_ids, list), "stock_ids must be a list"
        sql = "select a.S_INFO_WINDCODE as stock_id, a.TRADE_DT as dt, " \
                "a.S_VAL_MV as total_mv, a.S_DQ_MV as floating_mv, a.S_VAL_PE_TTM as PE_TTM, a.S_VAL_PB_NEW as PB, " \
                "a.S_PRICE_DIV_DPS, b.S_TECH_TVMA60 as trade_amount_60days " \
                "from AShareEODDerivativeIndicator a, TurnoverTechnicalFactor b " \
                "where a.S_INFO_WINDCODE = b.S_INFO_WINDCODE and a.TRADE_DT = b.TRADE_DT and a.TRADE_DT >= '{}' and a.TRADE_DT <= '{}' and a.S_INFO_WINDCODE in ({}) "
        if len(stock_ids) <= 500:
            sql_temp = sql.format(start_date, end_date,  ','.join(["'%s'" % x for x in stock_ids]))
            df = pd.read_sql_query(sql_temp, dbconn)
        else:
            stock_list = cal.basicCal_cut(stock_ids, 500)
            temp_list = list()
            for sl in stock_list:
                sql_temp = sql.format(start_date, end_date, ','.join(["'%s'" % x for x in sl]))
                df = pd.read_sql_query(sql_temp, dbconn)
                temp_list.append(df)
            df = pd.concat(temp_list, axis=0)
    else:
        sql = "select a.S_INFO_WINDCODE as stock_id, a.TRADE_DT as dt, " \
                "a.S_VAL_MV as total_mv, a.S_DQ_MV as floating_mv, a.S_VAL_PE_TTM as PE_TTM, a.S_VAL_PB_NEW as PB, " \
                "b.S_TECH_TVMA60 as trade_amount_60days " \
                "from AShareEODDerivativeIndicator a, TurnoverTechnicalFactor b " \
                "where a.S_INFO_WINDCODE = b.S_INFO_WINDCODE and a.TRADE_DT = b.TRADE_DT and a.TRADE_DT >= '{}' and a.TRADE_DT <= '{}' "

        sql_temp = sql.format(start_date, end_date)
        df = pd.read_sql_query(sql_temp, dbconn)
    df.rename(columns={'dt': 'date'}, inplace=True)
    df['total_mv'] = df['total_mv'] * 10000
    df['floating_mv'] = df['floating_mv'] * 10000
    df['trade_amount_60days'] = df['trade_amount_60days'] * 10000
    df['date'] = pd.to_datetime(df['date']).dt.date  # convert timestamp to datetime.date
    dbconn.close()
    return df

# ------------------------------------------------------
# 获取公募基金的单位净值和复权净值序列
# ------------------------------------------------------
def wind_getMFNav(
        start_date,             # 起始日期，输入格式:datetime.date
        end_date,               # 结束日期，输入格式:datetime.date
        product_id              # product_id基金代码，应为list格式（因数据库存储问题，优先使用场内代码），为None时，相当于获取全部基金
):
    assert (type(start_date) == datetime.date), '日期输入格式需为datetime.date'
    assert (type(end_date) == datetime.date), '日期输入格式需为datetime.date'
    assert start_date <= end_date, '起始日需不晚于结束日'
    dbconn = wind_connectWindDB()
    start_date = datetime.datetime.strftime(start_date, format='%Y%m%d')
    end_date = datetime.datetime.strftime(end_date, format='%Y%m%d')

    sql_1="select a.F_INFO_WINDCODE as product_id, b.F_INFO_NAME as product_name, a.PRICE_DATE as dt, a.F_NAV_UNIT as nav_unit, a.F_NAV_ADJUSTED as nav_adjusted " \
         "from (ChinaMutualFundNAV)a, (ChinaMutualFundDescription)b " \
         "where a.F_INFO_WINDCODE=b.F_INFO_WINDCODE " \
         "and a.PRICE_DATE >= '{}' and a.PRICE_DATE <= '{}' "
    sql_codes = "and a.F_INFO_WINDCODE IN {} "
    sql_2 = "order by a.F_INFO_WINDCODE, a.PRICE_DATE"

    if product_id == None: # 空的时候读取全部基金
        df = pd.read_sql_query(sql_1.format(start_date, end_date) + sql_2, dbconn)
    elif len(product_id) == 1: # list长度为1时候无法使用tuple
        df = pd.read_sql_query(sql_1.format(start_date, end_date)+sql_codes.format('\''+product_id[0]+'\'')+sql_2, dbconn)
    elif len(product_id) < 1000:
        df = pd.read_sql_query(sql_1.format(start_date, end_date)+sql_codes.format(tuple(product_id))+sql_2, dbconn)
    else: # 长度超过1000，读全部基金，再loc
        df = pd.read_sql_query(sql_1.format(start_date, end_date) + sql_2, dbconn)
        df = df.loc[df['product_id'].isin(product_id)].reset_index(drop=True)
    df['dt'] = pd.to_datetime(df['dt']).dt.date
    df.rename(columns={'dt':'date'}, inplace=True)
    dbconn.close()
    return df

# ------------------------------------------------------
#  获取公募基金在某段时间的风险收益指标，具体的指标参见Wind中的
#  ChinaMFPerformance表格。返回为dataframe
# ------------------------------------------------------
def wind_getMFStats(
        fcode,                       # wind基金代码，输入格式：List 如 ['000001.OF', '000002.OF']
        startdate,                   # 起始日期，输入格式:datetime.date
        enddate,                     # 结束日期，输入格式:datetime.date
        stats = ['f_avgreturn_day'], # 通过ChinaMFPerformance表格来查可以输入的stats,所有字母用小写。
        MF = True                    # 如果MF为False，则对应的是的券商理财产品的stats
):
    assert (type(startdate) == datetime.date), '日期输入格式需为datetime.date'
    assert (type(enddate) == datetime.date), '日期输入格式需为datetime.date'
    assert startdate <= enddate, '起始日需早于结束日'
    stats_str = ','.join(stats)
    dbconn = wind_connectWindDB()
    if MF == True:
        stats_sql = "select trade_dt, s_info_windcode, {0} " \
                    " from ChinaMFPerformance where TRADE_DT <= '{1}' and TRADE_DT >= '{2}' and S_INFO_WINDCODE in {3}"
    else:
        stats_sql = "select trade_dt, s_info_windcode, {0} " \
                    " from FundSAMPerformance where TRADE_DT <= '{1}' and TRADE_DT >= '{2}' and S_INFO_WINDCODE in {3}"
    if len(fcode) == 1:     # list长度为1时候无法使用tuple
        fcode = ('\''+fcode[0]+'\'')
    else:
        fcode = tuple(fcode)

    fcode_array = [fcode[i:i+500] for i in range(0, len(fcode), 500)]
    all_stats_array = []
    for i in range(len(fcode_array)):
        thisStats = pd.read_sql_query(stats_sql.format(stats_str, enddate.strftime('%Y%m%d'), startdate.strftime('%Y%m%d'), fcode_array[i]),
                                      dbconn)
        all_stats_array.append(thisStats)
    FundStats = pd.concat(all_stats_array)
    scale_stats = [ x for x in stats if 'return' in x or 'maxdownside' in x]
    FundStats[scale_stats] = FundStats[scale_stats]/100
    FundStats.rename(columns={'s_info_windcode': 'product_id'}, inplace=True)
    FundStats['date'] = FundStats['trade_dt'].apply(lambda x: datetime.datetime.strptime(x,'%Y%m%d').date())
    del FundStats['trade_dt']
    FundStats = _getAnnualizedStats(FundStats)
    dbconn.close()
    return FundStats

# ------------------------------------------------------
#  获取公募基金每日收益，返回为dataframe，每列代表一个产品。
# ------------------------------------------------------
def wind_getMFSingleStats(
    fcode,  # wind基金代码，输入格式：List 如 ['000001.OF', '000002.OF']
    startdate,  # 起始日期，输入格式:datetime.date
    enddate,  # 结束日期，输入格式:datetime.date
    stat = 'f_avgreturn_day'
):
    single_stat = wind_getMFStats(fcode, startdate, enddate, [stat])
    single_stat.dropna(inplace=True)
    result = pd.pivot_table(single_stat, values=[stat], index=['date'], columns=['product_id'])[stat]
    return result

# ------------------------------------------------------
# 获取指数在某一时段的return, return格式为series
# 指数包括A股指数、港股指数、公募基金指数等各类指数
# Author: Zhongheng Shen, 041439
# ------------------------------------------------------
def wind_getIndexReturn(
        idx_code,  # wind指数代码，输入格式：String, eg: "000905.SH", "885001.WI"
        start_date,  # 起始日期，输入格式:datetime.date
        end_date,  # 结束日期，输入格式:datetime.date
        freq  # 频率："W", "D", "M"
):
    assert freq in ["D", "W", "M"], "frequency must be one of ('D', 'W', 'M')"
    assert isinstance(start_date, datetime.date), "start_date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "end_date must be an instance of datetime.date"
    price_col = 's_dq_close'
    if idx_code.split('.')[1] == 'CFE':
        # 期货数据收益率计算采用结算价
        price_col = 's_dq_settle'
    dbconn = wind_connectWindDB()

    # 向前多取一段时间，保证收益率数据均有值
    if freq in ('D', 'W'):
        temp_start_date = start_date - relativedelta(weeks=4)
    elif freq == 'M':
        temp_start_date = start_date - relativedelta(months=2)

    temp_start_date = temp_start_date.strftime("%Y%m%d")
    end_date = end_date.strftime("%Y%m%d")
    sql_AIndex = "SELECT S_INFO_WINDCODE, TRADE_DT, S_DQ_CLOSE, S_DQ_PCTCHANGE FROM AIndexEODPrices WHERE S_INFO_WINDCODE = '{}' AND TRADE_DT >= '{}' AND TRADE_DT <= '{}'"
    df_AIndex = pd.read_sql_query(sql_AIndex.format(idx_code, temp_start_date, end_date), dbconn)  # A股指数

    sql_AWindIndex = "SELECT S_INFO_WINDCODE, TRADE_DT, S_DQ_CLOSE, S_DQ_PCTCHANGE FROM AIndexWindIndustriesEOD WHERE S_INFO_WINDCODE = '{}' AND TRADE_DT >= '{}' AND TRADE_DT <= '{}'"
    df_AWindIndex = pd.read_sql_query(sql_AWindIndex.format(idx_code, temp_start_date, end_date), dbconn)  # A股Wind行业指数

    sql_HKIndex = "SELECT S_INFO_WINDCODE, TRADE_DT, S_DQ_CLOSE, S_DQ_PCTCHANGE FROM HKIndexEODPrices WHERE S_INFO_WINDCODE = '{}' AND TRADE_DT >= '{}' AND TRADE_DT <= '{}'"
    df_HKIndex = pd.read_sql_query(sql_HKIndex.format(idx_code, temp_start_date, end_date), dbconn)  # H股指数

    sql_CMFIndex = "SELECT S_INFO_WINDCODE, TRADE_DT, S_DQ_CLOSE, S_DQ_PCTCHANGE FROM CMFIndexEOD WHERE S_INFO_WINDCODE = '{}' AND TRADE_DT >= '{}' AND TRADE_DT <= '{}'"
    df_CMFIndex = pd.read_sql_query(sql_CMFIndex.format(idx_code, temp_start_date, end_date), dbconn)  # 公募基金指数

    sql_BondIndex = "SELECT S_INFO_WINDCODE, TRADE_DT, S_DQ_CLOSE, S_DQ_PCTCHANGE FROM CBIndexEODPrices WHERE S_INFO_WINDCODE = '{}' AND TRADE_DT >= '{}' AND TRADE_DT <= '{}'"
    df_BondIndex = pd.read_sql_query(sql_BondIndex.format(idx_code, temp_start_date, end_date), dbconn)  # 债券指数

    sql_WindThirdPartyIndex = "SELECT S_INFO_WINDCODE, TRADE_DT, S_DQ_CLOSE FROM ThirdPartyStockIndexEOD WHERE S_INFO_WINDCODE = '{}' AND TRADE_DT >= '{}' AND TRADE_DT <= '{}'"
    df_WindThirdPartyIndex = pd.read_sql_query(sql_WindThirdPartyIndex.format(idx_code, temp_start_date, end_date), dbconn).sort_values('trade_dt')  # Wind数据库第三方指数行情，e.g. CC30.WI CAMO2.WI
    df_WindThirdPartyIndex['s_dq_pctchange'] = df_WindThirdPartyIndex['s_dq_close'].pct_change().dropna() * 100

    # 获取股指期货结算价作为收益率计算基础
    sql_IndexFutures = "SELECT S_INFO_WINDCODE, TRADE_DT,S_DQ_SETTLE FROM CIndexFuturesEODPrices WHERE S_INFO_WINDCODE = '{}' AND TRADE_DT >= '{}' AND TRADE_DT <= '{}'"
    IndexFutures = pd.read_sql_query(sql_IndexFutures.format(idx_code, temp_start_date, end_date), dbconn).sort_values('trade_dt')  # Wind股指期货数据行情，e.g IF01.CFE
    IndexFutures['s_dq_pctchange'] = IndexFutures['s_dq_settle'].pct_change().dropna() * 100     # 与上方数据保持格式一致


    df_idx = df_AIndex.append(df_HKIndex).reset_index(drop=True)
    df_idx = df_idx.append(df_AWindIndex).reset_index(drop=True)
    df_idx = df_idx.append(df_CMFIndex).reset_index(drop=True)
    df_idx = df_idx.append(df_BondIndex).reset_index(drop=True)
    df_idx = df_idx.append(df_WindThirdPartyIndex).reset_index(drop=True)
    df_idx = df_idx.append(IndexFutures).reset_index(drop=True)
    df_idx.sort_values(by='trade_dt', ascending=True, axis=0, inplace=True)
    df_idx.index = pd.to_datetime(df_idx['trade_dt'])

    if freq == "D":
        final_return = df_idx['s_dq_pctchange'] / 100
    elif freq == "W":
        final_return = df_idx[price_col].resample('W-Fri').last().pct_change().dropna()
    elif freq == "M":
        final_return = df_idx[price_col].resample('M').last().pct_change().dropna()

    final_return = final_return.loc[start_date: end_date]
    final_return.name = idx_code
    final_return.index = final_return.index.date
    final_return.index.name = "date"
    dbconn.close()
    return final_return

# ------------------------------------------------------
# 获取股票指数在某一时段的price, volume等信息，包括港股指数、基金指数以及三方数据
# ------------------------------------------------------
def wind_getIndexData(
        idx_code,  # wind指数代码，输入格式：String, eg: "000905.SH", "HSTECH.HI", "885001.WI", "801220.SI", "CI005001.WI"
        start_date,  # 起始日期，输入格式:datetime.date
        end_date,  # 结束日期，输入格式:datetime.date
        freq,  # 频率："W", "D", "M"
        method="average"  # 如果频率为W或者M，提供均值或者last两种采样方式，default为average
):
    assert freq in ["D", "W", "M"], "frequency must be one of ('D', 'W', 'M')"
    assert isinstance(start_date, datetime.date), "start_date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "end_date must be an instance of datetime.date"

    dbconn = wind_connectWindDB()
    start_date = start_date.strftime("%Y%m%d")
    end_date = end_date.strftime("%Y%m%d")

    sql_AIndex = "SELECT S_INFO_WINDCODE as wcode, TRADE_DT as dt, S_DQ_CLOSE as close_price, S_DQ_OPEN as open_price, " \
                 "S_DQ_HIGH as high_price, S_DQ_LOW as low_price, S_DQ_VOLUME as volume, S_DQ_AMOUNT as amount " \
                 "FROM AIndexEODPrices WHERE S_INFO_WINDCODE = '{}' AND TRADE_DT >= '{}' AND TRADE_DT <= '{}' " \
                 "order by dt"
    df_AIndex = pd.read_sql_query(sql_AIndex.format(idx_code, start_date, end_date), dbconn)  # A股指数

    sql_WDIndex = "SELECT S_INFO_WINDCODE as wcode, TRADE_DT as dt, S_DQ_CLOSE as close_price, S_DQ_OPEN as open_price, " \
                 "S_DQ_HIGH as high_price, S_DQ_LOW as low_price, S_DQ_VOLUME as volume, S_DQ_AMOUNT as amount " \
                 "FROM AIndexWindIndustriesEOD WHERE S_INFO_WINDCODE = '{}' AND TRADE_DT >= '{}' AND TRADE_DT <= '{}' " \
                 "order by dt"
    df_WDIndex = pd.read_sql_query(sql_WDIndex.format(idx_code, start_date, end_date), dbconn)  # 万得的指数


    sql_HKIndex = "SELECT S_INFO_WINDCODE as wcode, TRADE_DT as dt, S_DQ_CLOSE as close_price, S_DQ_OPEN as open_price, " \
                  "S_DQ_HIGH as high_price, S_DQ_LOW as low_price, S_DQ_VOLUME as volume, S_DQ_AMOUNT as amount " \
                  "FROM HKIndexEODPrices WHERE S_INFO_WINDCODE = '{}' AND TRADE_DT >= '{}' AND TRADE_DT <= '{}' " \
                  "order by dt"
    df_HKIndex = pd.read_sql_query(sql_HKIndex.format(idx_code, start_date, end_date), dbconn)  # H股指数

    sql_CMFIndex = "SELECT S_INFO_WINDCODE as wcode, TRADE_DT as dt, S_DQ_CLOSE as close_price, S_DQ_OPEN as open_price, " \
                   "S_DQ_HIGH as high_price, S_DQ_LOW as low_price, S_DQ_VOLUME as volume, S_DQ_AMOUNT as amount " \
                   "FROM CMFIndexEOD WHERE S_INFO_WINDCODE = '{}' AND TRADE_DT >= '{}' AND TRADE_DT <= '{}' " \
                   "order by dt"
    df_CMFIndex = pd.read_sql_query(sql_CMFIndex.format(idx_code, start_date, end_date), dbconn)  # 公募基金指数

    sql_CFutureIndex = "SELECT S_INFO_WINDCODE as wcode, TRADE_DT as dt, S_DQ_CLOSE as close_price, S_DQ_OPEN as open_price, " \
                   "S_DQ_HIGH as high_price, S_DQ_LOW as low_price, S_DQ_VOLUME as volume, S_DQ_AMOUNT as amount " \
                   "FROM ThirdPartyIndexEOD WHERE S_INFO_WINDCODE = '{}' AND TRADE_DT >= '{}' AND TRADE_DT <= '{}' " \
                   "order by dt"
    df_CFutureIndex = pd.read_sql_query(sql_CFutureIndex.format(idx_code, start_date, end_date), dbconn)  # 三方期货指数

    sql_CITICSIndex = "SELECT S_INFO_WINDCODE as wcode, TRADE_DT as dt, S_DQ_CLOSE as close_price, S_DQ_OPEN as open_price, S_DQ_HIGH as high_price, S_DQ_LOW as low_price, S_DQ_VOLUME as volume, S_DQ_AMOUNT as amount FROM AIndexIndustriesEODCITICS WHERE S_INFO_WINDCODE = '{}' AND TRADE_DT >= '{}' AND TRADE_DT <= '{}'"
    df_CITICSIndex = pd.read_sql_query(sql_CITICSIndex.format(idx_code, start_date, end_date), dbconn)  # 中信行业指数

    sql_SWIndex = "SELECT S_INFO_WINDCODE as wcode, TRADE_DT as dt, S_DQ_CLOSE as close_price, S_DQ_OPEN as open_price, S_DQ_HIGH as high_price, S_DQ_LOW as low_price, S_DQ_VOLUME as volume, S_DQ_AMOUNT as amount FROM ASWSIndexEOD WHERE S_INFO_WINDCODE = '{}' AND TRADE_DT >= '{}' AND TRADE_DT <= '{}'"
    df_SWIndex = pd.read_sql_query(sql_SWIndex.format(idx_code, start_date, end_date), dbconn)  # 申万行业指数

    sql_BondIndex = "SELECT S_INFO_WINDCODE as wcode, TRADE_DT as dt, S_DQ_CLOSE as close_price, S_DQ_OPEN as open_price, S_DQ_HIGH as high_price, S_DQ_LOW as low_price, S_DQ_VOLUME as volume, S_DQ_AMOUNT as amount FROM CBIndexEODPrices WHERE S_INFO_WINDCODE = '{}' AND TRADE_DT >= '{}' AND TRADE_DT <= '{}'"
    df_BondIndex = pd.read_sql_query(sql_BondIndex.format(idx_code, start_date, end_date), dbconn)  # 债券指数

    df_idx = df_AIndex.append(df_HKIndex).reset_index(drop=True)
    df_idx = df_idx.append(df_WDIndex).reset_index(drop=True)
    df_idx = df_idx.append(df_CMFIndex).reset_index(drop=True)
    df_idx = df_idx.append(df_CFutureIndex).reset_index(drop=True)
    df_idx = df_idx.append(df_CITICSIndex).reset_index(drop=True)
    df_idx = df_idx.append(df_SWIndex).reset_index(drop=True)
    df_idx = df_idx.append(df_BondIndex).reset_index(drop=True)
    df_idx.index = pd.to_datetime(df_idx['dt'])
    del df_idx['wcode'], df_idx['dt']

    if freq == "D" or len(df_idx) == 0:
        final_return = df_idx
    elif freq == "W":
        if method == "average":
            final_return = df_idx.resample('W-Fri').mean()
        elif method == "last":
            final_return = df_idx.resample('W-Fri').last()
    elif freq == "M":
        if method == "average":
            final_return = df_idx.resample('M').mean()
        elif method == "last":
            final_return = df_idx.resample('M').last()

    for col in ['volume','amount']:
        if col not in final_return.columns.values:
            final_return[col] = None

    final_return.name = idx_code
    final_return.reset_index(inplace=True)
    final_return.rename(columns={'dt': 'date'}, inplace=True)
    final_return['date'] = pd.to_datetime(final_return['date']).dt.date
    final_return['index_code'] = idx_code
    dbconn.close()
    return final_return

# ------------------------------------------------------
#  获取第三方股票行业指数（中信、申万、恒生港股等）行情量价信息
# ------------------------------------------------------
def wind_getThirdPartyStockIndexIndustryData(
    vendor,     # 数据提供商，输入格式:str，'SW' or 'CITICS or 'HS''
    level,  # 几级行业
    start_date,   # DateTime.date instance
    end_date,   # DateTime.date instance
    freq,  # D, W, M
    method='average'  # 如果频率为W或者M，提供均值或者last两种采样方式，default为average
):
    assert isinstance(start_date, datetime.date), "date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "date must be an instance of datetime.date"
    assert vendor in ("SW", "CITICS","HS"), '数据提供商目前支持SW(申万)/CITICS(中信)/HS(恒生港股)'

    vendor_index_code_mapping = {
        'SW': {
            1: const.const.SW_INDUSTRY_CODE_LEVEL_1,
            2: const.const.SW_INDUSTRY_CODE_LEVEL_2
        },
        'CITICS': {
            1: const.const.CITICS_INDUSTRY_CODE_LEVEL_1
        },
        'HS': {
            1: const.const.HSHK_INDUSTRY_CODE_LEVEL_1
        }
    }
    assert level in vendor_index_code_mapping[vendor].keys(), "该数据商暂不支持这一level"

    index_list = list(vendor_index_code_mapping[vendor][level].keys())
    result = []
    for idx in index_list:
        df = wind_getIndexData(idx, start_date, end_date, freq, method)
        result.append(df)
    result = pd.concat(result, axis=0)
    return result

# ------------------------------------------------------
# 获取股指期货数据
# Author: Zhongheng Shen, 041439
# ------------------------------------------------------
def wind_getStockIndexFutureData(
        futures_id,  # string, must be "IF", "IC", "IM" OR "IH"
        start_date,  # 起始日期，输入格式:datetime.date
        end_date  # 结束日期，输入格式:datetime.date
):
    assert futures_id in ["IF", "IC", "IM", "IH"], "future code must be one of ('IH', 'IF', 'IM', 'IC')"
    assert isinstance(start_date, datetime.date), "start_date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "end_date must be an instance of datetime.date"

    dbconn = wind_connectWindDB()
    start_date = start_date.strftime("%Y%m%d")
    end_date = end_date.strftime("%Y%m%d")
    sql = "select a.s_info_windcode, a.trade_dt, a.S_DQ_OPEN," \
          " a.S_DQ_HIGH, a.S_DQ_LOW, a.S_DQ_CLOSE, a.S_DQ_settle," \
          " a.S_DQ_VOLUME, a.S_DQ_AMOUNT, a.S_DQ_OI, b.s_info_delistdate" \
          " from (select * from CIndexFuturesEODPrices where trade_dt between '{}' and '{}' and" \
          " instr(s_info_windcode,'{}') > 0 and instr(s_info_windcode,'S') < 1 and length(s_info_windcode) = 10)a,(select s_info_windcode" \
          " ,s_info_delistdate from CFuturesDescription)b where b.s_info_windcode=a.s_info_windcode" \
          " order by a.trade_dt, a.s_dq_oi desc"

    df = pd.read_sql_query(sql.format(start_date, end_date, futures_id), dbconn)
    rename_dict = {'s_info_windcode': 'contract_id',
                   'trade_dt': 'date',
                   's_dq_open': 'open_price',
                   's_dq_high': 'high_price',
                   's_dq_low': 'low_price',
                   's_dq_close': 'close_price',
                   's_dq_settle': 'settle_price',
                   's_dq_volume': 'volume',
                   's_dq_amount': 'amount',
                   's_dq_oi': 'open_interest',
                   's_info_delistdate': 'delist_date'
                   }
    df.rename(columns=rename_dict, inplace=True)
    df['date'] = pd.to_datetime(df['date']).dt.date
    df['delist_date'] = pd.to_datetime(df['delist_date']).dt.date
    df['ttm'] = (df['delist_date'] - df['date']).dt.days  # 距离到期剩余自然日
    dbconn.close()
    return df

# ------------------------------------------------------
# 获取股指期货连续合约(主力/次主力/00-03合约)与底层实际月份合约代码的映射关系
# ------------------------------------------------------
def wind_getStockIndexFuturesContinuousContractMapping(
        futures_id,  # "IF", "IC", "IM" OR "IH"
        start_date,  # 起始日期，输入格式:datetime.date
        end_date,  # 截止日期，输入格式:datetime.date
):
    assert futures_id in ["IF", "IC", "IM", "IH"], "futures_id must be one of ('IH', 'IF', 'IM', 'IC')"
    assert isinstance(start_date, datetime.date), "date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "date must be an instance of datetime.date"

    dbconn = wind_connectWindDB()
    start_date = start_date.strftime("%Y%m%d")
    end_date = end_date.strftime("%Y%m%d")
    sql = "SELECT a.trade_dt, a.s_info_windcode, b.fs_mapping_windcode" \
          " FROM (SELECT * FROM CIndexFuturesEODPrices WHERE trade_dt BETWEEN '{}' AND '{}' AND s_info_windcode IN ({}))a" \
          " LEFT JOIN (select * from CfuturesContractMapping)b ON a.s_info_windcode=b.s_info_windcode" \
          " WHERE a.trade_dt BETWEEN b.startdate AND b.enddate" \
          " ORDER BY a.trade_dt, a.s_info_windcode"
    main_contracts = [futures_id + postfix for postfix in ['.CFE', '_S.CFE', '00.CFE', '01.CFE', '02.CFE', '03.CFE']]
    df = pd.read_sql_query(sql.format(start_date, end_date, ','.join(["'%s'" % x for x in main_contracts])), dbconn)
    df.columns = df.columns.str.lower()
    rename_dict = {'trade_dt': 'date',
                   's_info_windcode': 'contract_id',
                   'fs_mapping_windcode': 'mapping_contract_id'
                   }
    df.rename(columns=rename_dict, inplace=True)
    df['date'] = pd.to_datetime(df['date']).dt.date
    dbconn.close()
    return df

# ------------------------------------------------------
# 获取商品期货指数数据
# ------------------------------------------------------
def wind_getCommodityIndexFutureData(
    futures_codelist,  # a string list, 需要读取期货指数的列表, e.g. [RBFI.WI, TAFI.WI] or [JJRI.WI]
    start_date,  # 起始日期，输入格式:datetime.date
    end_date  # 结束日期，输入格式:datetime.date
):
    assert isinstance(futures_codelist, list), "futures_codelist must be a list of futures index code"
    assert isinstance(start_date, datetime.date), "start_date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "end_date must be an instance of datetime.date"
    dbconn = wind_connectWindDB()
    start_date = start_date.strftime("%Y%m%d")
    end_date = end_date.strftime("%Y%m%d")
    sql = "SELECT s_info_windcode as windcode, TRADE_DT as dt, S_DQ_OPEN as open, S_DQ_HIGH as high, S_DQ_LOW as low, " \
          "S_DQ_CLOSE as close, S_DQ_VOLUME as volume, S_DQ_AMOUNT as amount " \
          "FROM CFutureIndexEODPrices " \
          "WHERE ((trade_dt between '{0}' and '{1}') and " \
          "s_info_windcode in {2}) " \
          "ORDER BY dt desc"
    df = pd.read_sql_query(sql.format(start_date, end_date, tuple(futures_codelist)), dbconn)
    dbconn.close()
    if not df['windcode'].unique().__len__() == futures_codelist.__len__():
        AssertionError('There is input error in futures_codelist')
    else:
        df.rename(columns={'dt': 'date'}, inplace=True)
        df['date'] = pd.to_datetime(df['date']).dt.date
        return df

# ------------------------------------------------------
# 获取商品期货合约行情
# ------------------------------------------------------
def wind_getCommodityFutureContractData(
    futures_codelist,  # a string list, 需要读取品种代码的列表, e.g. [RB.SHF, TA.CZC]
    start_date,  # 起始日期，输入格式:datetime.date
    end_date  # 结束日期，输入格式:datetime.date
):
    assert isinstance(futures_codelist, list), "futures_codelist must be a list of futures contract code"
    assert isinstance(start_date, datetime.date), "start_date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "end_date must be an instance of datetime.date"
    dbconn = wind_connectWindDB()
    start_date = start_date.strftime("%Y%m%d")
    end_date = end_date.strftime("%Y%m%d")
    sql = "SELECT s_info_windcode as windcode, TRADE_DT as dt, S_DQ_OPEN as open, S_DQ_HIGH as high, S_DQ_LOW as low, " \
          "S_DQ_CLOSE as close, S_DQ_VOLUME as volume, S_DQ_AMOUNT as amount, S_DQ_OI as oi, " \
          "S_DQ_SETTLE as settle, S_DQ_PRESETTLE as presettle " \
          "FROM CCommodityFuturesEODPrices " \
          "WHERE ((trade_dt between '{0}' and '{1}') and " \
          "s_info_windcode in {2})"
    df = pd.read_sql_query(sql.format(start_date, end_date, tuple(futures_codelist)), dbconn)
    dbconn.close()
    if not df['windcode'].unique().__len__() == futures_codelist.__len__():
        AssertionError('There is input error in futures_codelist')
    else:
        df.rename(columns={'dt': 'date'}, inplace=True)
        df['date'] = pd.to_datetime(df['date']).dt.date
        return df

# ------------------------------------------------------
#  获取中债登债券收益率曲线
# ------------------------------------------------------
def wind_getBondCurve(
        startdate,                  # 起始日期，输入格式:datetime.date
        enddate,                    # 结束日期，输入格式:datetime.date
        term = 10,                  # 期限，输入格式：int 如 10 代表十年, 可以填0-50的整数
        curvetype = 1,              # 曲线类型，输入格式：int，1:即期 2:到期
        curvecode = 1231            # 曲线编号，输入格式：int 如 1231 代表中债国债收益率曲线，对照表参考wind_getBondCurveNumberName函数
):
    assert (type(startdate) == datetime.date), '日期输入格式需为datetime.date'
    assert (type(enddate) == datetime.date), '日期输入格式需为datetime.date'
    assert startdate <= enddate, '起始日需早于结束日'
    dbconn = wind_connectWindDB()
    startdate = startdate.strftime("%Y%m%d")
    enddate = enddate.strftime("%Y%m%d")
    sql = "select TRADE_DT, B_ANAL_YIELD as yield " \
          "from CBondCurveCNBD " \
          "where B_ANAL_CURVENUMBER = '{}' and B_ANAL_CURVETYPE = '{}' and B_ANAL_CURVETERM = '{}' " \
          "and TRADE_DT >= '{}' and TRADE_DT <= '{}' "
    result = pd.read_sql_query(sql.format(curvecode, curvetype, term, startdate, enddate), dbconn)
    result.rename(columns={'trade_dt': 'date'}, inplace=True)
    result['date'] = pd.to_datetime(result['date']).dt.date
    result['yield'] /= 100
    dbconn.close()
    return result

# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# 4. 持仓函数
# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------

# ------------------------------------------------------
# 获取基金的资产配置信息
# ------------------------------------------------------
def wind_getMFAssetAllocation(
        start_date=None,         # 起始日期, datetime.date
        end_date=None,           # 截止日期, datetime.date
        product_ids=None,   # product_ids基金代码，应为list格式（因数据库存储问题，优先使用场内代码），为None时，相当于获取全部基金
        companies=None,     # 基金公司简称，list格式，如果company有赋值，则返回该公司旗下所有基金的数据，忽略product_ids变量的任何赋值
        only_a_share=True,  # 是否只取A份额，默认为是
):
    dbconn = wind_connectWindDB()
    sql_1 = "select a.S_INFO_WINDCODE as product_id, b.F_INFO_FULLNAME as product_full_name, a.F_PRT_ENDDATE as dt, b.F_INFO_CORP_FUNDMANAGEMENTCOMP as company_short_name, a.F_PRT_NETASSET as net_asset, " \
          "a.F_PRT_STOCKVALUE as product_stk_value, a.F_PRT_STOCKTONAV as product_stk_value_to_nav, " \
          "a.F_PRT_CASH as cash_value, a.F_PRT_CASHTONAV as cash_to_nav,  " \
          "a.F_PRT_COVERTBOND as product_cbond_value, a.F_PRT_COVERTBONDTONAV as product_cbond_value_to_nav, " \
          "a.F_PRT_BONDVALUE as product_bond_value, a.F_PRT_BONDTONAV as product_bond_value_to_nav, " \
          "a.F_PRT_FUNDVALUE as product_fund_value, a.F_PRT_FUNDTONAV as product_fund_value_to_nav, " \
          "a.F_PRT_OTHER as product_other_value, a.F_PRT_OTHERTONAV as product_other_value_to_nav, " \
          "a.F_PRT_HKSTOCKVALUE as product_hkstk_value, a.F_PRT_HKSTOCKTONAV as product_hkstk_value_to_nav " \
          "from ChinaMutualFundAssetPortfolio a, ChinaMutualFundDescription b " \
            "where a.S_INFO_WINDCODE = b.F_INFO_WINDCODE "
    if start_date is not None and end_date is not None:
        sql_1 += "and a.F_PRT_ENDDATE >= '{}' and a.F_PRT_ENDDATE <= '{}' ".format(start_date.strftime('%Y%m%d'), end_date.strftime('%Y%m%d'))
    if only_a_share:
        sql_1 += "and b.F_INFO_ISINITIAL = 1 "
    sql_codes = "and a.S_INFO_WINDCODE in {} "
    sql_company = "and b.F_INFO_CORP_FUNDMANAGEMENTCOMP in {} "
    sql_2 = "order by a.S_INFO_WINDCODE, a.F_PRT_ENDDATE"

    if companies != None:
        if len(companies) == 1:  # list长度为1时候无法使用tuple
            fund = pd.read_sql_query(sql_1 + sql_company.format('\'' + companies[0] + '\'') + sql_2, dbconn)
        else:
            fund = pd.read_sql_query(sql_1 + sql_company.format(tuple(companies)) + sql_2, dbconn)
    else:
        if product_ids == None:  # 空的时候读取全部基金
            fund = pd.read_sql_query(sql_1 + sql_2, dbconn)
        elif len(product_ids) == 1:  # list长度为1时候无法使用tuple
            fund = pd.read_sql_query(sql_1 + sql_codes.format('\'' + product_ids[0] + '\'') + sql_2, dbconn)
        elif len(product_ids) < 500:
            fund = pd.read_sql_query(sql_1 + sql_codes.format(tuple(product_ids)) + sql_2, dbconn)
        else:  # 长度超过500，读全部基金，再loc
            fund = pd.read_sql_query(sql_1 + sql_2, dbconn)
            fund = fund.loc[fund['product_id'].isin(product_ids)].reset_index(drop=True)
    fund.rename(columns={'dt': 'date'}, inplace=True)
    fund['date'] = pd.to_datetime(fund['date']).dt.date
    col = ['product_stk_value_to_nav', 'cash_to_nav', 'product_cbond_value_to_nav', 'product_bond_value_to_nav','product_fund_value_to_nav','product_hkstk_value_to_nav', 'product_other_value_to_nav']
    fund[col] /= 100  # 单位调整为1
    # 添加基金类型
    fund_type = wind_getMFtype()
    fund = pd.merge(fund, fund_type, how='left', on='product_id')
    dbconn.close()
    return fund

# ------------------------------------------------------
# 获取全部公募基金的股票持仓
# 可以取到A股和H股 QDII基金可取到美股
# 如果设置起始日期和结束日期，则仅返回区间内的持仓
# 是否取A份额、是否取被动指数基金可选
# ------------------------------------------------------
def wind_getMFStockHoldings(
        product_id=None,            # product_id基金代码，应为list格式（因数据库存储问题，优先使用场内代码），为None时，相当于获取全部持仓
        freq='H',                   # freq为频率，'Q'为季报，'H'为半年和年报
        Top10=False,                # Top10为是否仅取季报前十大持仓
        start_date=None,            # 起始日期
        end_date=None,              # 结束日期
        only_a_share=True,          # 是否只取A份额，默认为是
        passive_index_fund=False,   # 是否包含被动指数基金，默认为否
):
    # F_PRT_ENDDATE 截止日期 会有非季末日期，例如ETF基金，最近成分股披露日非季末;
    # 场内基金在上市交易公告书里会公布最新成分，也可能是非季末
    # F_INFO_ISINITIAL = 1，默认只取A份额，否则按公司汇总时，市值会重复计算
    # b.CUR_SIGN = 1, 基金分类是最新的，避免重复计算
    # b.S_INFO_SECTOR not in ('2001010102000000', '200101080102000000') 默认剔除被动指数型基金和QDII被动指数型基金
    dbconn = wind_connectWindDB()
    sql_A = "select a.F_PRT_ENDDATE as rpt_date, a.S_INFO_WINDCODE as product_id, c.F_INFO_CORP_FUNDMANAGEMENTCOMP as company_short_name, " \
            "a.S_INFO_STOCKWINDCODE as stock_id, d.S_INFO_NAME as stock_name, " \
                 "a.F_PRT_STKVALUE as stk_value, a.F_PRT_STKVALUETONAV as stk_value_to_nav, a.STOCK_PER as stk_value_to_allstk, " \
                 "a.FLOAT_SHR_PER as stk_quantity_to_compfloat " \
                 "from (ChinaMutualFundStockPortfolio)a, (ChinaMutualFundSector)b, " \
                 "(ChinaMutualFundDescription)c, (AShareDescription)d " \
                 "where a.S_INFO_WINDCODE=b.F_INFO_WINDCODE and a.S_INFO_WINDCODE=c.F_INFO_WINDCODE and a.S_INFO_STOCKWINDCODE = d.S_INFO_WINDCODE " \
                 "and substr(b.S_INFO_SECTOR, 1, 6) = '200101' and b.CUR_SIGN = 1 "

    sql_H = "select a.F_PRT_ENDDATE as rpt_date, a.S_INFO_WINDCODE as product_id, c.F_INFO_CORP_FUNDMANAGEMENTCOMP as company_short_name, " \
            "a.S_INFO_STOCKWINDCODE as stock_id, d.S_INFO_NAME as stock_name, " \
            "a.F_PRT_STKVALUE as stk_value, a.F_PRT_STKVALUETONAV as stk_value_to_nav, a.STOCK_PER as stk_value_to_allstk, " \
            "a.FLOAT_SHR_PER as stk_quantity_to_compfloat " \
            "from (ChinaMutualFundStockPortfolio)a, (ChinaMutualFundSector)b, " \
            "(ChinaMutualFundDescription)c, (HKShareDescription)d " \
            "where a.S_INFO_WINDCODE=b.F_INFO_WINDCODE and a.S_INFO_WINDCODE=c.F_INFO_WINDCODE and a.S_INFO_STOCKWINDCODE = d.S_INFO_WINDCODE " \
            "and substr(b.S_INFO_SECTOR, 1, 6) = '200101' and b.CUR_SIGN = 1 "

    sql_QD = "select a.ENDDATE as rpt_date, a.S_INFO_WINDCODE as product_id, c.F_INFO_CORP_FUNDMANAGEMENTCOMP as company_short_name, " \
             "a.S_INFO_INVESTWINDCODE as stock_id, a.NAME as stock_name, " \
             "a.VALUE as stk_value, a.POSSTKTONAV as stk_value_to_nav, a.LISTSCOPE as country_code_3 " \
             "from (QDIISecuritiesPortfolio)a, (ChinaMutualFundSector)b, (ChinaMutualFundDescription)c " \
             "where a.S_INFO_WINDCODE=b.F_INFO_WINDCODE and a.S_INFO_WINDCODE=c.F_INFO_WINDCODE " \
             "and substr(b.S_INFO_SECTOR, 1, 6) = '200101' and a.TYPE = '股票' and b.CUR_SIGN = 1 "
    if not passive_index_fund:
        sql_A += "and b.S_INFO_SECTOR not in ('2001010102000000', '200101080102000000') "
        sql_H += "and b.S_INFO_SECTOR not in ('2001010102000000', '200101080102000000') "
        sql_QD += "and b.S_INFO_SECTOR not in ('2001010102000000', '200101080102000000') "
    if only_a_share:
        sql_A += "and c.F_INFO_ISINITIAL = 1 "
        sql_H += "and c.F_INFO_ISINITIAL = 1 "
        sql_QD += "and c.F_INFO_ISINITIAL = 1 "
    if (start_date != None) and (end_date != None):
        sql_A += "and a.F_PRT_ENDDATE >= '{}' and a.F_PRT_ENDDATE <= '{}' ".format(start_date.strftime("%Y%m%d"), end_date.strftime("%Y%m%d"))
        sql_H += "and a.F_PRT_ENDDATE >= '{}' and a.F_PRT_ENDDATE <= '{}' ".format(start_date.strftime("%Y%m%d"), end_date.strftime("%Y%m%d"))
        sql_QD += "and a.ENDDATE >= '{}' and a.ENDDATE <= '{}' ".format(start_date.strftime("%Y%m%d"), end_date.strftime("%Y%m%d"))

    sql_codes = "and a.S_INFO_WINDCODE in {} "
    sql_2 = "order by product_id, rpt_date, stk_value desc"
    if product_id == None: # 空的时候读取全部基金
        portfolioA = pd.read_sql_query(sql_A + sql_2, dbconn)
        portfolioA['stock_market'] = 'A'
        portfolioH = pd.read_sql_query(sql_H + sql_2, dbconn)
        portfolioH['stock_market'] = 'H'
        portfolioQD = pd.read_sql_query(sql_QD + sql_2, dbconn)
        portfolioQD = portfolioQD.loc[portfolioQD['country_code_3'].isin(['CHN', 'HKG', 'USA'])].replace(
            {'country_code_3': {'CHN': 'A', 'HKG': 'H', 'USA': 'US'}})  # 暂时仅穿透A股/港股/美股持仓
        portfolioQD.rename(columns={'country_code_3': 'stock_market'}, inplace=True)
        portfolio = pd.concat([portfolioA, portfolioH, portfolioQD])
    elif len(product_id) == 1: # list长度为1时候无法使用tuple
        portfolioA = pd.read_sql_query(sql_A+sql_codes.format('\''+product_id[0]+'\'')+sql_2, dbconn)
        portfolioA['stock_market'] = 'A'
        portfolioH = pd.read_sql_query(sql_H + sql_codes.format('\''+product_id[0]+'\'')+sql_2, dbconn)
        portfolioH['stock_market'] = 'H'
        portfolioQD= pd.read_sql_query(sql_QD + sql_codes.format('\'' + product_id[0] + '\'') + sql_2, dbconn)
        portfolioQD = portfolioQD.loc[portfolioQD['country_code_3'].isin(['CHN', 'HKG', 'USA'])].replace(
            {'country_code_3': {'CHN': 'A', 'HKG': 'H', 'USA': 'US'}})  # 暂时仅穿透A股/港股/美股持仓
        portfolioQD.rename(columns={'country_code_3': 'stock_market'}, inplace=True)
        portfolio = pd.concat([portfolioA, portfolioH, portfolioQD])
    elif len(product_id) <= 500:
        portfolioA = pd.read_sql_query(sql_A+sql_codes.format(tuple(product_id))+sql_2, dbconn)
        portfolioA['stock_market'] = 'A'
        portfolioH = pd.read_sql_query(sql_H +sql_codes.format(tuple(product_id))+sql_2, dbconn)
        portfolioH['stock_market'] = 'H'
        portfolioQD = pd.read_sql_query(sql_QD + sql_codes.format(tuple(product_id)) + sql_2, dbconn)
        portfolioQD = portfolioQD.loc[portfolioQD['country_code_3'].isin(['CHN', 'HKG', 'USA'])].replace(
            {'country_code_3': {'CHN': 'A', 'HKG': 'H', 'USA': 'US'}})  # 暂时仅穿透A股/港股/美股持仓
        portfolioQD.rename(columns={'country_code_3': 'stock_market'}, inplace=True)
        portfolio = pd.concat([portfolioA, portfolioH, portfolioQD])
    else: # 长度超过500，读全部基金，再loc
        product_list = [product_id[i: i+500] for i in range(0, len(product_id), 500)]
        temp_list = list()
        for pl in product_list:
            dfA = pd.read_sql_query(sql_A + sql_codes.format(tuple(pl)) + sql_2, dbconn)
            dfA['stock_market'] = 'A'
            dfH = pd.read_sql_query(sql_H + sql_codes.format(tuple(pl)) + sql_2, dbconn)
            dfH['stock_market'] = 'H'
            dfQD = pd.read_sql_query(sql_QD + sql_codes.format(tuple(pl)) + sql_2, dbconn)
            dfQD = dfQD.loc[dfQD['country_code_3'].isin(['CHN', 'HKG', 'USA'])].replace(
                {'country_code_3': {'CHN': 'A', 'HKG': 'H', 'USA': 'US'}})  # 暂时仅穿透A股/港股/美股持仓
            dfQD.rename(columns={'country_code_3': 'stock_market'}, inplace=True)
            temp = pd.concat([dfA, dfH, dfQD])
            temp_list.append(temp)
        portfolio = pd.concat(temp_list, axis=0)

    if freq == 'Q': # 季度末数据
        result = portfolio.loc[portfolio['rpt_date'].str[-4:].isin(['0331', '0630', '0930', '1231'])].reset_index(drop=True)
        if Top10: # 仅取前十大
            result = result.groupby(['rpt_date', 'product_id']).apply(lambda x: x.iloc[:10, 2:]).reset_index()
            result.drop('level_2', axis=1, inplace=True)
    elif freq == 'H': # 半年末数据
        assert Top10 == False, '半年末不能仅返回前十大持仓'
        result = portfolio.loc[portfolio['rpt_date'].str[-4:].isin(['0630', '1231'])].reset_index(drop=True)
    result.rename(columns={'rpt_date':'date'}, inplace=True)
    result['date'] = pd.to_datetime(result['date']).dt.date
    result['stk_value_to_nav'] = result['stk_value_to_nav']/100
    result['stk_value_to_allstk'] = result['stk_value_to_allstk']/100
    result['stk_quantity_to_compfloat'] = result['stk_quantity_to_compfloat']/1e2
    dbconn.close()
    return result

# ------------------------------------------------------
# 获取公募基金的基金持仓 - WIND中国共同基金投资组合—其他证券数据表
# 如果设置起始日期和结束日期，则仅返回区间内的持仓
# 返回的持仓权重比为实际值，未扩为100%，求和结果是基金标的的总持仓权重
# 是否只取A份额可选（对全量筛选）
# ------------------------------------------------------
def wind_getMFOFFundHoldings(
        product_id=None,            # product_id基金代码，应为list格式（因数据库存储问题，优先使用场内代码），为None时，相当于获取全部持仓
        freq='H',                   # freq为频率，'Q'为季报，'H'为半年和年报
        Top10=False,                # Top10为是否仅取季报前十大持仓
        start_date=None,            # 起始日期
        end_date=None,              # 结束日期
        only_a_share=True,          # 是否只取A份额，默认为是
):
    # F_PRT_ENDDATE 截止日期 会有非季末日期，例如ETF基金，最近成分股披露日非季末;
    # 场内基金在上市交易公告书里会公布最新成分，也可能是非季末
    # F_INFO_ISINITIAL = 1，默认只取A份额，否则按公司汇总时，市值会重复计算
    # b.CUR_SIGN = 1, 基金分类是最新的，避免重复计算
    # b.S_INFO_SECTOR not in ('2001010102000000', '200101080102000000') 默认剔除被动指数型基金和QDII被动指数型基金
    dbconn = wind_connectWindDB()
    sql_1 = "select a.END_DT as rpt_date, a.S_INFO_WINDCODE as product_id, c.F_INFO_NAME as product_name, c.F_INFO_CORP_FUNDMANAGEMENTCOMP as company_short_name, " \
            "a.S_INFO_HOLDWINDCODE as holding_fund_id, d.F_INFO_NAME as holding_fund_name, a.VALUE as holding_fund_value, a.QUANTITY as holding_fund_quantity, a.VALUETONAV as holding_fund_value_to_nav " \
             "from (CMFOtherPortfolio)a, (ChinaMutualFundSector)b, (ChinaMutualFundDescription)c, (ChinaMutualFundDescription)d " \
             "where a.S_INFO_WINDCODE=b.F_INFO_WINDCODE and a.S_INFO_WINDCODE=c.F_INFO_WINDCODE and a.S_INFO_HOLDWINDCODE = d.F_INFO_WINDCODE " \
             "and substr(b.S_INFO_SECTOR, 1, 6) = '200101' and b.CUR_SIGN = 1 "
    if only_a_share:
        sql_1 += "and c.F_INFO_ISINITIAL = 1 "
    sql_codes = "and a.S_INFO_WINDCODE in {} "
    sql_2 = "order by a.S_INFO_WINDCODE, a.END_DT, a.VALUE desc"

    if product_id == None: # 空的时候读取全部基金
        portfolio = pd.read_sql_query(sql_1 + sql_2, dbconn)
    elif len(product_id) == 1: # list长度为1时候无法使用tuple
        portfolio = pd.read_sql_query(sql_1+sql_codes.format('\''+product_id[0]+'\'')+sql_2, dbconn)
    elif len(product_id) <= 500:
        portfolio = pd.read_sql_query(sql_1+sql_codes.format(tuple(product_id))+sql_2, dbconn)
    else: # 长度超过500，读全部基金，再loc
        product_list = cal.basicCal_cut(product_id, 500)
        temp_list = list()
        for pl in product_list:
            temp_df = pd.read_sql_query(sql_1 + sql_codes.format(tuple(pl)) + sql_2, dbconn)
            temp_list.append(temp_df)
        portfolio = pd.concat(temp_list, axis=0)

    if freq == 'Q': # 季度末数据
        result = portfolio.loc[portfolio['rpt_date'].str[-4:].isin(['0331', '0630', '0930', '1231'])].reset_index(drop=True)
        if Top10: # 仅取前十大
            result = result.groupby(['rpt_date', 'product_id']).apply(lambda x: x.iloc[:10, 2:]).reset_index()
            result.drop('level_2', axis=1, inplace=True)
    elif freq == 'H': # 半年末数据
        assert Top10 == False, '半年末不能仅返回前十大持仓'
        result = portfolio.loc[portfolio['rpt_date'].str[-4:].isin(['0630', '1231'])].reset_index(drop=True)
    result.rename(columns={'rpt_date':'date'}, inplace=True)
    result['date'] = pd.to_datetime(result['date']).dt.date
    result['holding_fund_value_to_nav'] = result['holding_fund_value_to_nav']/100
    if (start_date != None) and (end_date != None):
        result = result.loc[(result['date'] >= start_date) & (result['date'] <= end_date)].reset_index(drop=True)

    # 添加持仓基金类型
    fund_type = wind_getMFtype().rename(columns={'product_id': 'holding_fund_id'})
    result = pd.merge(result, fund_type, how='left', on='holding_fund_id')
    result['type_name_lv2'] = result.apply(lambda x: x['type_name_lv1'] if pd.isnull(x['type_name_lv2']) else x['type_name_lv2'], axis=1)
    dbconn.close()
    return result

# -------------------------------------------------------------------------------------
# 获取单只FOF公募的基金持仓 取输入日期前最近一期报告的持仓数据
# 返回的持仓权重比为实际值，未扩为100%，求和结果是基金标的的总持仓权重
# -------------------------------------------------------------------------------------
def wind_getMFOFCurrentFundHoldings(
        date,  # best effort, 寻找该日期前最新的持仓数据
        product_id,  # 公募基金ID
        freq='Q',  # freq为频率，'Q'为季报，'H'为半年和年报
):
    portfolio = wind_getMFOFFundHoldings([product_id], freq=freq, Top10=False, start_date=date - datetime.timedelta(365),
                                            end_date=date, only_a_share=False)
    portfolio = portfolio[portfolio['date'] == portfolio['date'].max()].reset_index(drop=True)
    return portfolio

# ------------------------------------------------------
# 获取指数的成分股
# 目前支持A股指数
# ------------------------------------------------------
def wind_getIndexComponent(
    index_id,           # 指数ID，目前支持A股指数
    data_date=None,     # 为None代表取最新值，不为None时去当时时点的指数成分
):
    dbconn = wind_connectWindDB()
    sql_AIndex = "SELECT S_INFO_WINDCODE as index_id, S_CON_WINDCODE as stock_id, S_CON_INDATE as in_date, S_CON_OUTDATE as out_date, CUR_SIGN as current_sign " \
                 "FROM AIndexMembers WHERE S_INFO_WINDCODE = '{}'" #+ "order by in_dt" # AND TRADE_DT >= '{}' AND TRADE_DT <= '{}' "
    df_AIndex = pd.read_sql_query(sql_AIndex.format(index_id), dbconn)  # A股指数成分
    df_AIndex['in_date'] = pd.to_datetime(df_AIndex['in_date']).dt.date
    df_AIndex['out_date'] = pd.to_datetime(df_AIndex['out_date']).dt.date
    if not data_date:
        result = df_AIndex[df_AIndex['current_sign']==1]
    else:
        result = df_AIndex[(df_AIndex['in_date'] <= data_date) & (df_AIndex['out_date'].isnull() | (df_AIndex['out_date'] > data_date))]
    result['data_date'] = data_date if data_date else datetime.date.today()
    dbconn.close()
    return result

# ----------------------------------------------------------------------------------------------------
# 获取指数的成分股的权重, 分为日频模式和月频模式，wind客户端做行业分析使用的是月频数据
# 日频数据来源是WIND数据库的日频权重表,会与wind客户端所展示的结果有小差别(客户端使用月频权重进行展示),目前支持300 500 800 1000
# 月频数据来源是WIND数据库的月频权重表,数据日期均落在当月最后一个交易日
# 返回的dataframe：数据日期 指数id 权重股id 权重
# ----------------------------------------------------------------------------------------------------
def wind_getStockIndexComponentWeight(
    index_id,  # 指数ID，月频模式freq=M时支持A股指数，日频模式freq=D时支持300 500 800 1000
    start_date,
    end_date,
    freq='D'
):
    assert freq in ('D', 'M'), "获取指数成分股权重的数据频率目前支持D和W"
    aux_start_date = start_date.strftime("%Y%m%d")
    aux_end_date = end_date.strftime("%Y%m%d")
    dbconn = wind_connectWindDB()
    if freq == 'D':
        assert index_id in ('000016.SH', '000300.SH', '000905.SH', '000906.SH', '000852.SH'), "目前日频地获取指数成分股权重只支持 50 300 500 800 1000"
        table_map = {
            '000016.SH': 'weight as stock_weight from AIndexSSE50Weight',
            '000300.SH': 'i_weight as stock_weight from AIndexHS300CloseWeight',
            '000905.SH': 'weight as stock_weight from AIndexCSI500Weight',
            '000906.SH': 'weight as stock_weight from AIndexCSI800Weight',
            '000852.SH': 'weight as stock_weight from AIndexCSI1000Weight',
        }
        sql_weight = "select trade_dt as data_date,s_con_windcode as stock_id," + table_map[index_id] + " where trade_dt >= '{}' and trade_dt <= '{}' order by trade_dt"
        index_weight = pd.read_sql_query(sql_weight.format(aux_start_date, aux_end_date), dbconn)
    else:
        sql_weight="select trade_dt as data_date,s_con_windcode as stock_id, i_weight as stock_weight from AIndexHS300FreeWeight where s_info_windcode='{}' and trade_dt >= '{}' and trade_dt <= '{}' order by trade_dt"
        index_weight = pd.read_sql_query(sql_weight.format(index_id, aux_start_date, aux_end_date), dbconn)
    index_weight["stock_weight"] = index_weight["stock_weight"].astype("float")
    index_weight['index_data_date'] = pd.to_datetime(index_weight['data_date']).dt.date
    index_weight['index_id'] = index_id
    index_weight['stock_weight'] = index_weight['stock_weight'] / 100  # 权重的量纲归一
    index_weight = index_weight[['index_data_date', 'index_id', 'stock_id', 'stock_weight']].reset_index(drop=True)
    dbconn.close()
    return index_weight

# --------------------------------------------------------------------------------------------------------------------
# 获取公募基金的最新规模，与wind界面上展示的数字一致
# --------------------------------------------------------------------------------------------------------------------
def wind_getMFLatestAUM(
    start_date,         # datetime.date格式，起始日期
    end_date,           # datetime.date格式，截止日期
    product_id=None,    # 默认取全量的，不会很慢，优先输入基金场内代码（如有）
):
    dbconn = wind_connectWindDB()
    sql_2 = "select PRICE_DATE as data_date, F_INFO_WINDCODE as product_id, NETASSET_TOTAL as aum from ChinaMutualFundNAV " \
            "where NETASSET_TOTAL is not null and PRICE_DATE >= '{}' and PRICE_DATE <= '{}' "
    aum = pd.read_sql_query(sql_2.format(start_date.strftime("%Y%m%d"), end_date.strftime("%Y%m%d")), dbconn)
    dbconn.close()
    aum = aum.sort_values('data_date').groupby(['product_id'], as_index=False)[['data_date', 'aum']].last()
    if product_id:
        aum = aum[aum['product_id'].isin(product_id)]
    return aum

# --------------------------------------------------------------------------------------------------------------------
# 获取wind基金指数穿透后的成分股的权重, 支持对成分基金进行等权计算和规模加权计算，通过index_id后缀区分
# wind基金指数只提供最新的基金成份，依照该成份取出date之前最新的一期报告得到前十大或者全部持仓股票，合并计算得到该基金指数的stock component
# 返回的dataframe：数据日期（所使用报告的日期） 指数id 权重股id 权重
# --------------------------------------------------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def wind_getMFIndexStockComponentWeight(
    index_id,   # 指数id
    date,       # 数据日期，会选择最新的指数基金成份，并取出date之前最新的一期报告得到前十大或者全部持仓，合并为该基金指数的stock component
):
    assert index_id in ('885001.EQUAL_WEIGHTED', '885001.AUM_WEIGHTED', '885007.EQUAL_WEIGHTED', '885007.AUM_WEIGHTED', 'BALANCED_MF_CUSTOMIZED.EQUAL_WEIGHTED', 'BALANCED_MF_CUSTOMIZED.AUM_WEIGHTED'),\
        "基金指数穿透股票成份仅支持'885001.EQUAL_WEIGHTED', '885001.AUM_WEIGHTED', '885007.EQUAL_WEIGHTED', '885007.AUM_WEIGHTED', 'BALANCED_MF_CUSTOMIZED.EQUAL_WEIGHTED', 'BALANCED_MF_CUSTOMIZED.AUM_WEIGHTED'"
    # 基金类型mapping，与基金指数定义相一致，比如偏股混合基金
    fund_type_map = {
        '885001.EQUAL_WEIGHTED': 'a201060302000000',
        '885001.AUM_WEIGHTED': 'a201060302000000',
        '885007.EQUAL_WEIGHTED': 'a201060308000000',
        '885007.AUM_WEIGHTED': 'a201060308000000',
    }
    if index_id in ('885001.EQUAL_WEIGHTED', '885001.AUM_WEIGHTED', '885007.EQUAL_WEIGHTED', '885007.AUM_WEIGHTED'):
        # 获取偏股混或二级债基类型下基金成份
        dbconn = wind_connectWindDB()
        sql_1 = "select S_INFO_WINDCODE as product_id, S_CON_CODE as fund_type_code, S_CON_NAME as fund_type_name from CFundWindIndexMembers where S_CON_CODE = '{}'"
        index_fund_component = pd.read_sql_query(sql_1.format(fund_type_map[index_id]), dbconn)
        dbconn.close()

    elif index_id in ('BALANCED_MF_CUSTOMIZED.EQUAL_WEIGHTED', 'BALANCED_MF_CUSTOMIZED.AUM_WEIGHTED'):
        # 获取公募组定义的均衡基金的成分信息
        index_fund_component = custMF_getMFIndustryClassification(category=['均衡'])

    # 获取成份基金的股票持仓
    index_stock_component = wind_getMFStockHoldings(index_fund_component['product_id'].tolist(), freq='Q', only_a_share=False, passive_index_fund=True)
    index_stock_component = index_stock_component.loc[index_stock_component['date'] <= date].reset_index(drop=True)
    index_stock_component = index_stock_component[index_stock_component['date'] == index_stock_component['date'].max()]
    # 如果选择规模加权的方式，则依照股票持有规模进行加权，否则按照基金中每个股票的持有权重进行加权汇总
    weight_col = 'stk_value' if index_id.split('.')[1] == 'AUM_WEIGHTED' else 'stk_value_to_nav'
    index_stock_component_summary = index_stock_component.groupby(['date', 'stock_id', 'stock_name'], as_index=False)[weight_col].sum()
    # 无论是否市值加权，最终需要将权重的和置为1
    index_stock_component_summary['stock_weight'] = index_stock_component_summary[weight_col] / index_stock_component_summary[weight_col].sum()
    index_stock_component_summary['index_id'] = index_id
    index_stock_component_summary = index_stock_component_summary[['date', 'index_id', 'stock_id', 'stock_name', 'stock_weight']]

    return index_stock_component_summary


# --------------------------------------------------------------------------------------------------------
# 获取指定日期的指数行业分布，目前使用日度的成分权重计算；WIND客户端使用是月度成分权重，故可能会与客户端展示的指数行业分布有出入
# 目前股票指数支持300 500 800 1000，基金指数支持885001等权/市值加权（885001.EQUAL_WEIGHTED, 885001.AUM_WEIGHTED）
# 返回的dataframe：数据日期 指数id 行业 行业权重
# --------------------------------------------------------------------------------------------------------
def wind_getIndexIndustryWeight(
    index_id,                       # 指数ID，目前支持A股指数和885001等权/市值加权
    date,
    company,                        # 分类标准，输入格式:str，'SW' or 'CITICS'
    level,                          # 分类级别，输入格式:int
):
    assert index_id in ('000300.SH', '000905.SH', '000906.SH', '000852.SH', '881001.WI', '885001.EQUAL_WEIGHTED', '885001.AUM_WEIGHTED', '885007.EQUAL_WEIGHTED', '885007.AUM_WEIGHTED', 'BALANCED_MF_CUSTOMIZED.EQUAL_WEIGHTED', 'BALANCED_MF_CUSTOMIZED.AUM_WEIGHTED'),\
        "行业超低配基准仅支持'000300.SH', '000905.SH', '000906.SH', '000852.SH', '881001.WI', '885001.EQUAL_WEIGHTED', '885001.AUM_WEIGHTED', '885007.EQUAL_WEIGHTED', '885007.AUM_WEIGHTED', 'BALANCED_MF_CUSTOMIZED.EQUAL_WEIGHTED', 'BALANCED_MF_CUSTOMIZED.AUM_WEIGHTED'"
    assert (company == 'SW' or company == 'CITICS'), 'company必须为SW或CITICS'
    assert (type(level) == int), 'level输入格式需为int'
    industry = wind_getAllHistIndustriesMap(company, level)
    # 中证指数和基金指数分别使用俩个取数口
    if index_id in ('000300.SH', '000905.SH', '000906.SH', '000852.SH'):
        # 使用日频的成分权重计算；WIND客户端使用是月度成分权重，故可能会与客户端数据展示有出入
        portfolio = wind_getStockIndexComponentWeight(index_id, date-datetime.timedelta(14), date, freq='D')
    elif index_id in ('885001.EQUAL_WEIGHTED', '885001.AUM_WEIGHTED', '885007.EQUAL_WEIGHTED', '885007.AUM_WEIGHTED', 'BALANCED_MF_CUSTOMIZED.EQUAL_WEIGHTED', 'BALANCED_MF_CUSTOMIZED.AUM_WEIGHTED'):
        # 自定义的公募基金指数作为行业超低配基准
        portfolio = wind_getMFIndexStockComponentWeight(index_id, date).rename(columns={'date': 'index_data_date'})
    elif index_id in ('881001.WI'):
        # 万得全A指数
        # FIXME 万得数据库无法获取精确成分权重，故使用windPy，跟着自定义公募基金指数一起，每季度缓存
        from WindPy import w
        w.start()
        portfolio_data = w.wset("indexconstituent", "date={0};windcode={1}".format(str(date), index_id))
        portfolio = pd.DataFrame(pd.DataFrame(portfolio_data.Data).values.T, columns=portfolio_data.Fields).\
                    rename(columns={'date': 'index_data_date', 'wind_code': 'stock_id', 'sec_name': 'stock_name', 'i_weight': 'stock_weight'})
        del portfolio['industry']
        portfolio['index_data_date'] = portfolio['index_data_date'].dt.date
        portfolio['stock_weight'] = portfolio['stock_weight'] / 100  # 权重的量纲归一
        portfolio['index_id'] = index_id
        w.close()
    portfolio = portfolio[portfolio['index_data_date'] == portfolio['index_data_date'].max()]
    industry = industry[(industry['entry_dt'] <= portfolio['index_data_date'].max()) & (industry['remove_dt'] >= portfolio['index_data_date'].max())]
    portfolio = pd.merge(portfolio, industry, on='stock_id', how='left').reset_index(drop=True)
    del portfolio['entry_dt'], portfolio['remove_dt']  # 按照时间筛选当时股票所在行业,使用之后可删除
    industry_result = portfolio.groupby(by=['index_data_date', 'index_id', 'industry'], as_index=False).agg({'stock_weight': 'sum'}).rename(columns={'stock_weight': 'industry_weight'})
    return industry_result

# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# 5. Map函数
# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------

# ------------------------------------------------------
# 获取股票的历史行业分类（A股+港股通），中信或申万分类
# 港股通股票里面中信行业只有一级分类（如果level>1，仅返回A股），申万有多级分类
# 申万全部用的2021版分类，对A股有历史分类，对港股通股票只有2021年以来的分类
# ------------------------------------------------------
def wind_getAllHistIndustriesMap(
        company,     # 分类标准，输入格式:str，'SW' or 'CITICS'
        level        # 分类级别，输入格式:int
):
    assert (type(level) == int), 'level输入格式需为int'
    assert (company == 'SW' or company == 'CITICS'), 'company必须为SW或CITICS'
    dbconn = wind_connectWindDB()
    if company == 'CITICS':
        sql_A = "select a.S_INFO_WINDCODE as stock_id, b.Industriesname as industry, a.ENTRY_DT, a.REMOVE_DT " \
              "from AShareIndustriesClassCITICS a, AShareIndustriesCode b " \
              "where substr(a.CITICS_IND_CODE, 1, {}) = substr(b.INDUSTRIESCODE, 1, {}) " \
              "and b.LEVELNUM = '{}' " \
              "order by a.S_INFO_WINDCODE, a.ENTRY_DT"
        industry_AShare = pd.read_sql_query(sql_A.format(2+level*2, 2+level*2, str(level+1)), dbconn)
    else:  # 申万全部用的2021版分类，这个分类里面，对A股有历史分类，对港股通股票只有今年以来的分类
        sql = "select a.S_INFO_WINDCODE as stock_id, b.Industriesname as industry, a.ENTRY_DT, a.REMOVE_DT " \
              "from AShareSWNIndustriesClass a, AShareIndustriesCode b " \
              "where substr(a.SW_IND_CODE, 1, {}) = substr(b.INDUSTRIESCODE, 1, {}) " \
              "And b.LEVELNUM = '{}' " \
              "order by a.S_INFO_WINDCODE, a.ENTRY_DT"
        industry_AShare = pd.read_sql_query(sql.format(2 + level * 2, 2 + level * 2, str(level + 1)), dbconn)

    # 公募港股按恒生一级分类，与私募产品港股行业暴露标准统一
    sql_H = "select a.S_INFO_WINDCODE as stock_id, b.INDUSTRIESNAME as industry, a.ENTRY_DT, a.REMOVE_DT " \
            "from HKStockHSIndustriesMembers a, HKStockIndustriesCode b " \
            "where substr(a.HS_IND_CODE, 1, {}) = substr(b.INDUSTRIESCODE, 1, {}) " \
            "and b.LEVELNUM = '{}' " \
            "order by a.S_INFO_WINDCODE, a.ENTRY_DT"
    industry_HKShare = pd.read_sql_query(sql_H.format(6, 6, '1'), dbconn)
    industry_HKShare['industry'] = industry_HKShare['industry'].apply(lambda x: x.split('(')[0] + '_港股')  # 去掉(HS) 加上'_港股' 与私募恒生行业分类保持一致

    industry = industry_AShare.append(industry_HKShare).reset_index(drop=True)
    industry['entry_dt'] = pd.to_datetime(industry['entry_dt']).dt.date
    industry['remove_dt'] = pd.to_datetime(industry['remove_dt']).dt.date
    industry['remove_dt'].fillna(datetime.date.today(), inplace=True)
    dbconn.close()
    return industry

# ------------------------------------------------------
# 获取股票的任意时点分类
# 港股通股票里面中信行业只有一级分类（如果level>1，仅返回A股）
# 申万全部用的2021版分类，对A股有历史分类，对港股通股票只有2021年以来的分类
# ------------------------------------------------------
def wind_getIndustriesMap(
        company,     # 分类标准，输入格式:str，'SW' or 'CITICS'
        level,       # 分类级别，输入格式:int
        date = datetime.date.today() # 观察时点，输入格式:datetime.date，默认是最新分类
):
    assert (type(date) == datetime.date), '日期输入格式需为datetime.date'
    industry = wind_getAllHistIndustriesMap(company, level)
    industry = industry.loc[(industry['entry_dt'] <= date) & (industry['remove_dt'] >= date)].reset_index(drop=True)
    industry['date'] = date
    del industry['entry_dt'], industry['remove_dt']
    return industry


# ------------------------------------------------------
# 获取基金公司简称全称对应表
# ------------------------------------------------------
def wind_getMFCompanyName():
    dbconn = wind_connectWindDB()
    sql = "select Unique S_INFO_COMPCODE as company_id, COMP_SNAME as company_name " \
          "from FundCompanyInsideHolder "
    df1 = pd.read_sql_query(sql, dbconn)
    sql = "select Unique F_INFO_CORP_FUNDMANAGEMENTID as company_id, F_INFO_CORP_FUNDMANAGEMENTCOMP as company_short_name " \
          "from ChinaMutualFundDescription"
    df2 = pd.read_sql_query(sql, dbconn)
    result = pd.merge(df2, df1, how='left', on='company_id')
    dbconn.close()
    return result

# ------------------------------------------------------
#  获取中债登债券收益率曲线 曲线编码和曲线名称的对照表
# ------------------------------------------------------
def wind_getBondCurveNumberName():
    dbconn = wind_connectWindDB()
    sql = "select Unique B_ANAL_CURVENUMBER, B_ANAL_CURVENAME " \
          "from CBondCurveCNBD " \
          "order by B_ANAL_CURVENUMBER"
    data = pd.read_sql_query(sql, dbconn)
    dbconn.close()
    return data

# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# 5. 日期数据
# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------

# ------------------------------------------------------
# 获取上交所交易日历
# ------------------------------------------------------
def wind_getSSECalendar():
    # S_INFO_EXCHMARKET的选项，SSE:上海交易所 SZSE:深圳交易所 SHN:沪股通 SZN:深股通
    sql = "select TRADE_DAYS " \
          "from AShareCalendar " \
          "where S_INFO_EXCHMARKET = 'SSE' " \
          "order by TRADE_DAYS"
    dbconn = wind_connectWindDB()
    SSECalendar = pd.read_sql_query(sql, dbconn)
    SSECalendar['trade_days'] = pd.to_datetime(SSECalendar['trade_days']).dt.date
    SSECalendar.rename(columns={'trade_days': 'date'}, inplace=True)
    dbconn.close()
    return SSECalendar

# ------------------------------------------------------
# 判断日期是否为交易日
# 输入格式datetime.date
# 返回Bool变量
# ------------------------------------------------------
def wind_isTradeDate(inputDate):
    SSECalendar = wind_getSSECalendar()
    return inputDate in SSECalendar['date'].tolist()

# ------------------------------------------------------
# 获取一列日期的最近一个交易日日期，输入和输出都是list
# ------------------------------------------------------
def wind_getLastTradeDates(
        list_of_dates      # 输入list。
):
    calender = wind_getSSECalendar()
    df_of_dates = pd.DataFrame({'date': list_of_dates})
    df_of_dates['trade_date'] = df_of_dates['date'].apply(lambda x: max(calender[calender['date'] < x]['date']))
    return df_of_dates['trade_date'].tolist()

# ------------------------------------------------------
# 获取某日前最近一个季报/半年报期
# ------------------------------------------------------
def wind_getLastReportDate(
        as_of_date,  # 该日前的最后一个交易日。
        Freq = 'Q'  # Q:季报 H:半年报/年报
):
    assert Freq in ['H', 'Q'], "Freq must in ['H', 'Q']"
    if Freq == 'Q':
        if as_of_date.month in range(1,4):
            if as_of_date.month == 3 and as_of_date.day == 31:
                reportdate = as_of_date
            else:
                reportdate = datetime.date(as_of_date.year -1, 12, 31)
        elif as_of_date.month in range(4,7):
            if as_of_date.month == 6 and as_of_date.day == 30:
                reportdate = as_of_date
            else:
                reportdate = datetime.date(as_of_date.year, 3, 31)
        elif as_of_date.month in range(7,10):
            if as_of_date.month == 9 and as_of_date.day == 30:
                reportdate = as_of_date
            else:
                reportdate = datetime.date(as_of_date.year, 6, 30)
        elif as_of_date.month in range(10,13):
            if as_of_date.month == 12 and as_of_date.day == 31:
                reportdate = as_of_date
            else:
                reportdate = datetime.date(as_of_date.year, 9, 30)
    elif Freq == 'H':
        if as_of_date.month in range(1,7):
            if as_of_date.month == 6 and as_of_date.day == 30:
                reportdate = as_of_date
            else:
                reportdate = datetime.date(as_of_date.year -1, 12, 31)
        elif as_of_date.month in range(7,13):
            if as_of_date.month == 12 and as_of_date.day == 31:
                reportdate = as_of_date
            else:
                reportdate = datetime.date(as_of_date.year, 6, 30)
    return reportdate

# ------------------------------------------------------
# 获取某日之后最近一个季报/半年报期
# ------------------------------------------------------
def wind_getNextReportDate(
        as_of_date,  # 该日前的最后一个交易日。
        Freq = 'Q'  # Q:季报 H:半年报/年报
):
    assert Freq in ['H', 'Q'], "Freq must in ['H', 'Q']"
    if Freq == 'Q':
        if as_of_date.month in range(1,4):
            if as_of_date.month == 3 and as_of_date.day == 31:
                reportdate = as_of_date
            else:
                reportdate = datetime.date(as_of_date.year, 3, 31)
        elif as_of_date.month in range(4,7):
            if as_of_date.month == 6 and as_of_date.day == 30:
                reportdate = as_of_date
            else:
                reportdate = datetime.date(as_of_date.year, 6, 30)
        elif as_of_date.month in range(7,10):
            if as_of_date.month == 9 and as_of_date.day == 30:
                reportdate = as_of_date
            else:
                reportdate = datetime.date(as_of_date.year, 9, 30)
        elif as_of_date.month in range(10,13):
            if as_of_date.month == 12 and as_of_date.day == 31:
                reportdate = as_of_date
            else:
                reportdate = datetime.date(as_of_date.year, 12, 31)
    elif Freq == 'H':
        if as_of_date.month in range(1,7):
            if as_of_date.month == 6 and as_of_date.day == 30:
                reportdate = as_of_date
            else:
                reportdate = datetime.date(as_of_date.year , 6, 30)
        elif as_of_date.month in range(7,13):
            if as_of_date.month == 12 and as_of_date.day == 31:
                reportdate = as_of_date
            else:
                reportdate = datetime.date(as_of_date.year, 12, 31)
    return reportdate

# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# 6. wind data helper
# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------

# ------------------------------------------------------
# 当前时点的所有公募基金列表，包括AC份额
# ------------------------------------------------------
def wind_getCurrentAllProductList():
    dbconn = wind_connectWindDB()
    sql = "select F_INFO_WINDCODE as product_id, F_INFO_NAME as product_name " \
          "from ChinaMutualFundDescription " \
          "where F_INFO_MATURITYDATE is null"
    df_fund = pd.read_sql_query(sql, dbconn)
    dbconn.close()
    return df_fund

# ------------------------------------------------------
# 按照WIND一级基金分类筛选出当前时点的所有公募基金列表，包括AC份额
# ------------------------------------------------------
@st.cache_data(ttl=86400)
def wind_getCurrentMFProductListbyType(
        fund_type  # wind基金分类（一级）
):
    product_info = wind_getCurrentAllProductList()
    product_type = wind_getMFtype()
    product_info = pd.merge(product_info, product_type[product_type['type_name_lv1'] == fund_type], on='product_id', how='inner')
    return product_info

# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# 7. wind数据库获取期货数据
# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------

# ------------------------------------------------
# 加载期货合约日K线信息
# ------------------------------------------------
def wind_getDailyFuturesContractInfo(
        start_date,  # 开始日期，数字格式 20210101
        end_date     #结束日期，数字格式 20210101

):
    assert isinstance(start_date, datetime.date), "date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "date must be an instance of datetime.date"
    start_date = start_date.strftime("%Y%m%d")
    end_date = end_date.strftime("%Y%m%d")
    dbconn = wind_connectWindDB()
    sql_getContractInfo = "SELECT a.trade_date, a.s_info_windcode, c.s_info_listdate," \
                          " c.s_info_delistdate, c.s_info_name, c.fs_info_sccode," \
                          " d.s_info_tunit, d.s_info_punit, d.s_info_mfprice, d.s_info_ftmargins," \
                          " e.s_info_windcode as s_info_type, c.fs_info_type, a.transaction_fee_rate," \
                          " (a.discount_rate_cp * a.transaction_fee_rate) as comson_charge," \
                          " b.trade_dt, b.marginratio FROM CFuturesDeliveryFee a" \
                          " LEFT JOIN CFuturesmarginratio b" \
                          " ON (a.s_info_windcode = b.s_info_windcode AND a.trade_date = b.trade_dt)" \
                          " LEFT JOIN Cfuturesdescription c ON a.s_info_windcode = c.s_info_windcode" \
                          " LEFT JOIN CfuturesContPro d ON a.s_info_windcode = d.s_info_windcode" \
                          " LEFT JOIN Cfuturescontractmapping e ON a.s_info_windcode = e.fs_mapping_windcode" \
                          " WHERE (a.trade_date >= '{0}'  AND a.trade_date <= '{1}' AND c.fs_info_type = 1" \
                          " AND c.s_info_exchmarket NOT IN ('NIB', 'CFFEX'))" \
                          " AND e.startdate <= a.trade_date and e.enddate >=a.trade_date" \
                          " ORDER BY s_info_windcode,a.trade_date".format(start_date, end_date)
    currentContractInfo = pd.read_sql_query(sql_getContractInfo, dbconn)
    dbconn.close()
    currentContractInfo.rename(columns={'trade_date': 'date',
                                         's_info_windcode': 'windcode',
                                         's_info_listdate': 'list',
                                         's_info_delistdate': 'delist',
                                         's_info_name': 'contract',
                                         'fs_info_sccode': 'code',
                                         'fs_info_type': 'type_code',
                                         's_info_tunit': 'unit',
                                         's_info_punit': 'multiplier',
                                         's_info_mfprice': 'mfprice',
                                         's_info_ftmargins': 'margin',
                                         's_info_type': 'contract_type',
                                         'transaction_fee_rate': 'transact_fee',
                                         'comson_charge': 'intra_day_charge',
                                         'trade_dt': 'adjust_date',
                                         'marginratio': 'new_margin'}, inplace=True)
    currentContractInfo['margin'] = [int(re.findall("\d+\.?\d*", string)[0]) / 100
                                     for string in currentContractInfo.margin]

    currentContractInfo['date'] = pd.to_datetime(currentContractInfo['date']).dt.date
    currentContractInfo['list'] = pd.to_datetime(currentContractInfo['list']).dt.date
    currentContractInfo['delist'] = pd.to_datetime(currentContractInfo['delist']).dt.date
    currentContractInfo['windcode'] = currentContractInfo['windcode'].astype(str)
    return currentContractInfo

# ------------------------------------------------
# 加载期货合约日K线信息
# ------------------------------------------------
def wind_getDailyFuturesBar(
        start_date,  # 开始日期
        end_date     #结束日期
):
    assert isinstance(start_date, datetime.date), "date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "date must be an instance of datetime.date"
    start_date = start_date.strftime("%Y%m%d")
    end_date = end_date.strftime("%Y%m%d")
    dbconn = wind_connectWindDB()
    sql_getBar = "SELECT a.s_info_windcode, a.trade_dt, a.s_dq_open, a.s_dq_high, a.s_dq_low, a.s_dq_close, " \
                 "a.s_dq_settle, a.s_dq_presettle, a.s_dq_oi, a.s_dq_volume, a.s_dq_amount " \
                 "FROM Ccommodityfutureseodprices a " \
                 "LEFT JOIN Cfuturesdescription b ON a.s_info_windcode = b.s_info_windcode " \
                 "WHERE (a.trade_dt >= '{0}' AND a.trade_dt <='{1}' AND a.fs_info_type = 2 " \
                 "AND b.s_info_exchmarket  NOT IN ('NIB', 'CFFEX')) " \
                 "ORDER BY a.s_info_windcode,a.trade_dt".format(start_date, end_date)
    daliy_bar = pd.read_sql_query(sql_getBar, dbconn)
    dbconn.close()
    daliy_bar.rename(columns={'trade_dt': 'date', 's_info_windcode': 'windcode',
                               's_dq_open': 'open', 's_dq_high': 'high',
                               's_dq_low': 'low', 's_dq_close': 'close',
                               's_dq_settle': 'settle', 's_dq_presettle': 'presettle',
                               's_dq_oi': 'openinterest', 's_dq_volume': 'volume',
                               's_dq_amount': 'amount'
                               }, inplace=True)
    daliy_bar['date'] = pd.to_datetime(daliy_bar['date']).dt.date
    daliy_bar['windcode'] = daliy_bar['windcode'].astype(str)
    return daliy_bar

# ------------------------------------------------
# 加载期货仓单信息
# ------------------------------------------------
def wind_getWarehouseTotal(
        start_date,  # 开始日期
        end_date     #结束日期
):
    assert isinstance(start_date, datetime.date), "date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "date must be an instance of datetime.date"
    start_date = start_date.strftime("%Y%m%d")
    end_date = end_date.strftime("%Y%m%d")
    dbconn = wind_connectWindDB()
    sql_description = "SELECT fs_info_sccode, s_info_name, s_info_fullname" \
                      " FROM CFuturesDescription WHERE (fs_info_type = 1" \
                      " AND s_info_exchmarket NOT IN ('NIB', 'CFFEX')" \
                      " AND fs_info_sccode NOT IN ('IM', 'SCTAS')) ORDER BY fs_info_sccode"
    code2name = pd.read_sql_query(sql_description, dbconn)

    code2name['s_info_name'] = [x[:-4] for x in code2name['s_info_name']]
    code2name['s_info_fullname'] = [x[:-6] for x in code2name['s_info_fullname']]
    code2name.drop_duplicates(keep='first', inplace=True)
    code2name.columns = ['code', 'name', 'fullname']

    sql_getWarehouseTotal = "SELECT a.fs_info_scname, a.ann_date, a.in_stock_total, a.in_stock, a.unit " \
                            "FROM Cfuturesinstock a WHERE a.ann_date >= '{0}' AND a.ann_date <= '{1}'  " \
                            "ORDER BY a.fs_info_scname,a.ann_date".format(start_date, end_date)
    currentWarehouseTotal = pd.read_sql_query(sql_getWarehouseTotal, dbconn)
    dbconn.close()
    if currentWarehouseTotal.empty:
        pass
    else:
        currentWarehouseTotal.rename(columns={'fs_info_scname': 'fullname', 'ann_date': 'reportdate',
                                              'in_stock_total': 'instock_total', 'in_stock': 'registered',
                                              }, inplace=True)
        currentWarehouseTotal = code2name.join(currentWarehouseTotal.set_index('fullname'), on='fullname',
                                               how='inner')

        return currentWarehouseTotal