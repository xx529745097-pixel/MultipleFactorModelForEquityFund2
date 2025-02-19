# ------------------------------------------------
# 本文档用于CTA分析相关数据提取
# ------------------------------------------------
import src.utils.fof_calendar as calendar

import pandas as pd
import numpy as np
import datetime
import src.data.wind as wind
import src.data.amdata as amdata
import src.data.irm as irm
from src.const import *

# ------------------------------------------------------
# 获取期货指数（品种、板块等）日行情
# return: DataFrames-high, low, open, close, volume, amount
# ------------------------------------------------------
def cta_getFuturesIndexDailyData(
    futures_codelist,  # a string list, 需要读取期货指数的列表, e.g. [RBFI.WI, TAFI.WI] or [JJRI.WI]
    start_date,  # 起始日期，输入格式:datetime.date
    end_date  # 结束日期，输入格式:datetime.date
):
    read_data = wind.wind_getCommodityIndexFutureData(futures_codelist, start_date, end_date)
    bar_name = ['open', 'close', 'high', 'low', 'volume', 'amount']
    output_list = [read_data.pivot_table(index='date', columns='windcode', values=x).sort_index(ascending=True)
                   for x in bar_name]
    dailydata_dict = dict(zip(bar_name, output_list))
    return dailydata_dict

# ------------------------------------------------------
# 获取期货（仅单品种）合约日行情
# return: DataFrames-high, low, open, close, volume, amount
# ------------------------------------------------------
def cta_getFuturesContractDailyData(
    futures_codelist,  # a string list, 需要读取品种代码的列表, e.g. [RB.SHF, TA.CZC]
    start_date,  # 起始日期，输入格式:datetime.date
    end_date  # 结束日期，输入格式:datetime.date
):
    read_data = wind.wind_getCommodityFutureContractData(futures_codelist, start_date, end_date)
    bar_name = ['open', 'close', 'high', 'low', 'settle', 'presettle', 'volume', 'amount', 'oi']
    output_list = [read_data.pivot_table(index='date', columns='windcode', values=x).sort_index(ascending=True)
                   for x in bar_name]
    dailydata_dict = dict(zip(bar_name, output_list))
    return dailydata_dict

# ------------------------------------------------------------------------
# 读取CTA产品托管报告
# return: DataFrame of selected tag
# ------------------------------------------------------------------------
def cta_getFundPositionsInfo(
    start_date,  # 起始日期，输入格式:datetime.date
    end_date,  # 结束日期，输入格式:datetime.date
    sheet_tag='RETURN',  # string, 需要读取的表名, RETURN:期货板块损益, MARGIN:保证金占比,
                         # VAL:期末合约名义本金占资产净值比（按持仓成本绝对值）, COST:期末合约名义本金占资产净值比（按持仓成本绝对值）, VALSUM:期末合约名义本金占资产净值比（按合约市值绝对值求和）
    product_id=None  # list, 产品代码列表 e.g. ['SGW851.OF'], 默认None为全量读取
):
    conn = irm.irm_connectIRMDB()
    start_date = datetime.datetime.strftime(start_date, format='%Y%m%d')
    end_date = datetime.datetime.strftime(end_date, format='%Y%m%d')
    if product_id is not None:
        product_id = ','.join(["'%s'" % x for x in product_id])
        sql = "SELECT * FROM irm.amdata_src_cta_fund_daily_new WHERE ('{0}' <= d_dt AND d_dt <= {1} " \
              "AND c_type='{2}' AND c_secu_id IN ({3})) ORDER BY d_dt".format(start_date, end_date, sheet_tag, product_id)
    else:
        sql = "SELECT * FROM irm.amdata_src_cta_fund_daily_new WHERE ('{0}' <= d_dt AND d_dt <= {1} " \
              "AND c_type='{2}') ORDER BY d_dt".format(start_date, end_date, sheet_tag)
    df = pd.read_sql_query(sql, conn).rename(columns=str.lower)
    conn.close()
    assert len(df) > 0, '所选产品或区间无数据'
    df.rename(columns={'d_dt':'date', 'c_secu_id':'product_id', 'c_secu_nm':'product_name',
                       'c_type':'type', 'd_update_dt':'update_date'}, inplace=True)
    table = df.dropna(axis=1, how='all').drop(['type', 'update_date'], axis=1)
    table['date'] = pd.to_datetime(table['date']).dt.date
    if sheet_tag in ['MARGIN', 'VAL', 'COST', 'VALSUM']:
        table.loc[:, const.FUTURES_IND_NAME_CN_TO_EN.keys()]=table.loc[:, const.FUTURES_IND_NAME_CN_TO_EN.keys()]/100

    return table

# ------------------------------------------------------------------------
# 读取CTA产品历史换手率及平均持仓周期
# ------------------------------------------------------------------------
def cta_getFundTurnover(
    start_date,  # 起始日期，输入格式:datetime.date
    end_date,  # 结束日期，输入格式:datetime.date
    product_id=None  # list, 产品代码列表 e.g. ['SGW851.OF'], 默认None为全量读取
):
    start_date = datetime.datetime.strftime(start_date, format='%Y%m%d')
    end_date = datetime.datetime.strftime(end_date, format='%Y%m%d')
    conn = irm.irm_connectIRMDB()
    if product_id is not None:
        product_id = ','.join(["'%s'" % x for x in product_id])
        sql = "SELECT * FROM irm.amdata_src_cta_trans_stats_new WHERE ('{0}' <= d_dt AND d_dt <= '{1}' " \
              "AND c_secu_id IN ({2})) ORDER BY d_dt".format(start_date, end_date, product_id)
    else:
        sql = "SELECT * FROM irm.amdata_src_cta_trans_stats_new WHERE ('{0}' <= d_dt " \
              "AND d_dt <= '{1}') ORDER BY d_dt".format(start_date, end_date)
    df = pd.read_sql_query(sql, conn).rename(columns=str.lower)
    df.rename(columns={'d_dt': 'date', 'c_secu_id': 'product_id', 'c_secu_nm': 'product_name'}, inplace=True)
    turnover_df = df.drop('d_update_dt', axis=1)
    turnover_df['date'] = pd.to_datetime(turnover_df['date']).dt.date
    conn.close()
    return turnover_df

# ------------------------------------------------
# 库存信息获取
# ------------------------------------------------
def _cta_getWarehouseData(
        start_date,     # 开始日期
        end_date,       # 结束日期
        contract_info,  # Dataframe,合约信息
        daily_quote,    # Dataframe,期货日行情数据
        selected_code_list,  # 品种代码，list格式，e.g. ['A','RB']
        param=240  # 因子参数: 滚动周期
):
    warehouseInfo = wind.wind_getWarehouseTotal(start_date, end_date)
    contract_type = ['主力']
    _output_info = []
    for future_code in selected_code_list:
        tradingcontract = contract_info.loc[contract_info['code'] == future_code, ]
        if len(tradingcontract) == 0:
            continue
        tradingcontract.sort_values(by='date', inplace=True)
        exchmarket = tradingcontract['windcode'].iloc[0].split('.')[-1]
        type_code = []
        [(type_code.append(future_code + const.CONTRACT_TYPE[x] + '.%s' % exchmarket) if x in const.CONTRACT_TYPE.keys()
          else type_code.append(future_code + x + '.%s' % exchmarket)) for x in contract_type]
        _output_info.append(tradingcontract.loc[tradingcontract['contract_type'].isin(type_code), ])
    tradingContract = pd.concat(_output_info)

    bar_quote = pd.merge(tradingContract, daily_quote, left_on=['windcode', 'date'],
                         right_on=['windcode', 'date'])
    bar_quote = bar_quote.drop(['contract', 'unit', 'mfprice', 'type_code'], axis=1)
    type_code = bar_quote['contract_type'].unique()
    dailyBarDict = dict(zip(type_code, [bar_quote.loc[bar_quote['contract_type'] == contract_code].set_index('date') for
                           contract_code in type_code]))

    _warehouse_data_list = []
    for future_code in list(dailyBarDict.keys()):
        dailyBarInfo = dailyBarDict[future_code]
        code = dailyBarInfo.code.unique()[0]
        instock = warehouseInfo.loc[warehouseInfo.code == code].set_index('reportdate')
        warehouse_quantile = instock.registered.rolling(param).apply(
            lambda x: (x.sort_values(ascending=True).drop_duplicates().tolist().index(x[-1]) + 1) /
                      len(x.drop_duplicates()) if len(x.drop_duplicates()) >= 5 else np.nan)
        _warehouse_data_list.append(warehouse_quantile)
    warehouse_data = pd.concat(_warehouse_data_list, axis=1)
    warehouse_data.columns = list(dailyBarDict.keys())
    warehouse_data = warehouse_data.reset_index()
    warehouse_data.rename(columns={'reportdate': 'date'}, inplace=True)

    warehouse_data['date'] = pd.to_datetime(warehouse_data['date']).dt.date
    warehouse_data.sort_values(by='date', inplace=True)
    warehouse_data = warehouse_data.set_index('date')
    return warehouse_data

# ------------------------------------------------
# 期货原始数据处理函数，从原始数据中提取出所需合约数据
# ------------------------------------------------
def _contract_data_helper(
        contract_info,  # Dataframe,期货合约信息
        daily_quote,  # Dataframe,期货每日数据
        code_list,  # list,选取的期货品种,e.g.['A','RB']
        contract_type='main' # 需要提取的合约类型
):
    assert contract_type in ['main', 'second', 'next', 'near', 'deferred'], "仅支持main、second、next、near、deferred五种类型"
    # 获取主力合约
    if contract_type == 'main':
        contract_info = contract_info.loc[contract_info['contract_code'].isin(code_list)]
        # 选取需要的列
        contract_main = contract_info[['date', 'windcode', 'list',
                                       'delist', 'contract', 'code', 'contract_type']]
        # 得到主力合约对应的量价数据
        result = pd.merge(contract_main,
                           daily_quote[
                               ['windcode', 'date', 'open', 'high', 'low', 'close', 'preclose', 'settle',
                                'presettle',
                                'volume', 'openinterest', 'amount']],
                           on=['date', 'windcode'],
                           how='left')
        result['return'] = result['close'] / result['preclose'] - 1
        result = result[['date', 'windcode', 'code',
                           'delist', 'close', 'preclose', 'settle',
                           'presettle', 'volume', 'return', 'openinterest', 'amount']]
    elif contract_type == 'second':
        # 挑出交割日晚于该品种对应主力合约交割日的合约
        contract_main = contract_info.loc[contract_info['contract_code'].isin(code_list), ['date', 'code', 'delist']]
        contract_info = pd.merge(contract_info, contract_main[['date', 'code', 'delist']], on=['date', 'code'], how='left', suffixes=('', '_main'))
        contract_info = contract_info.drop_duplicates(['date', 'windcode'])
        contract_info = contract_info.loc[contract_info['delist'] > contract_info['delist_main']]
        contract_info = pd.merge(contract_info,
                             daily_quote[['windcode', 'date', 'open', 'high', 'low', 'close',
                                          'preclose', 'settle', 'presettle', 'volume', 'openinterest', 'amount']],
                             on=['date', 'windcode'],
                             how='left')
        # 在这些合约中选择持仓量最大的合约作为次主力合约
        result = contract_info.groupby(['date', 'code'], as_index=False).apply(lambda x: x.sort_values(by='openinterest', ascending=False).iloc[0])
        # 合并得到次主力合约的量价数据
        result['return'] = result['close'] / result['preclose'] - 1
        result = result[['date', 'windcode', 'code', 'delist', 'settle', 'presettle', 'close', 'preclose', 'volume', 'return']]
    elif contract_type == 'near':
        # 获取近月合约
        contract_info = contract_info.loc[contract_info['contract_code'].isin([x + '00' for x in code_list])]

        result = pd.merge(contract_info, daily_quote[['windcode', 'date', 'open', 'high', 'low', 'close', 'preclose', 'settle', 'presettle', 'volume']],
                           on=['date', 'windcode'],
                           how='left')

        result['return'] = result['close'] / result['preclose'] - 1
        result = result[['date', 'windcode', 'code', 'delist',
                           'settle', 'presettle', 'close', 'preclose', 'volume', 'return']]

    elif contract_type == 'next':
        # 获取到期剩余时间最接近一年的合约
        contract_info = contract_info.loc[
            contract_info.code.isin(code_list)]

        contract_info['gap_year'] = abs(
            (contract_info['delist'] - contract_info['date']) / datetime.timedelta(days=1) - 365)
        contract_next = contract_info.groupby(['date', 'code'], as_index=True).apply(
            lambda x: x.sort_values(by=['gap_year']).iloc[0]).reset_index(drop=True)

        result = pd.merge(contract_next, daily_quote[['windcode', 'date',
                                                       'open', 'high', 'low', 'close', 'preclose', 'settle',
                                                       'presettle', 'volume']], on=['date', 'windcode'], how='left')

        result['return'] = result['close'] / result['preclose'] - 1

        result = result[['date', 'windcode', 'code', 'delist',
                           'settle', 'presettle', 'close', 'preclose', 'volume', 'return']]
    elif contract_type == 'deferred':
        # 获取远月合约
        contract_info = contract_info.loc[contract_info['contract_code'].isin([x + '01' for x in code_list])]

        result = pd.merge(contract_info, daily_quote[['windcode', 'date', 'open', 'high', 'low', 'close', 'preclose', 'settle', 'presettle', 'volume']],
                           on=['date', 'windcode'],
                           how='left')

        result['return'] = result['close'] / result['preclose'] - 1
        result = result[['date', 'windcode', 'code', 'delist',
                           'settle', 'presettle', 'close', 'preclose', 'volume', 'return']]
    return result

# ------------------------------------------------
# CTA因子计算数据获取函数，从底层获取原始数据并进行数据清洗
# ------------------------------------------------
def cta_getFactorsCalculationData(
        date_start, #开始日期
        date_end    #结束日期
):
    # 获取每日行情数据
    print('Step 1.1 获取每日行情数据')
    daily_quote = wind.wind_getDailyFuturesBar(date_start, date_end)

    # 获取合约信息
    print('Step 1.2 获取合约信息')
    contract_info = wind.wind_getDailyFuturesContractInfo(date_start, date_end)

    # 获取库存数据
    print('Step 1.3 获取库存数据')
    warehouse_data = _cta_getWarehouseData(date_start, date_end, contract_info, daily_quote, const.SELECTED_FUTURES_LIST)

    print('Step 1.4 整合数据，需合约行情数据')
    daily_preclose = pd.pivot_table(daily_quote, index='date', columns='windcode', values='close').shift(1).stack().reset_index().rename(columns={0: 'preclose'})
    daily_quote = pd.merge(daily_quote, daily_preclose, on=['date', 'windcode'], how='left')
    contract_info['contract_code']=contract_info['contract_type'].apply(lambda x: x.split('.')[0])
    # 处理得到主力合约，次主力合约，一年后合约
    df_main = _contract_data_helper(contract_info, daily_quote, const.SELECTED_FUTURES_LIST, contract_type='main')
    df_second = _contract_data_helper(contract_info, daily_quote, const.SELECTED_FUTURES_LIST, contract_type='second')
    df_next = _contract_data_helper(contract_info, daily_quote, const.SELECTED_FUTURES_LIST, contract_type='next')
    df_near = _contract_data_helper(contract_info, daily_quote, const.SELECTED_FUTURES_LIST, contract_type='near')
    df_deferred = _contract_data_helper(contract_info, daily_quote, const.SELECTED_FUTURES_LIST, contract_type='deferred')
    df_all = pd.merge(df_main, df_second, on=['date', 'code'], how='inner', suffixes=('', '_second'))
    df_all = pd.merge(df_all, df_next, on=['date', 'code'], how='inner', suffixes=('', '_next'))
    df_all = pd.merge(df_all, df_near, on=['date', 'code'], how='inner', suffixes=('', '_near'))
    df_all = pd.merge(df_all, df_deferred, on=['date', 'code'], how='inner', suffixes=('', '_deferred'))

    return {'all_contract': df_all, 'main_contract': df_main, 'warehouse_data': warehouse_data}

# ------------------------------------------------------------------------
# 读取CTA因子收益
# ------------------------------------------------------------------------
def cta_getCtaFactorReturn(
    start_date,  # DateTime.date instance, eg: datetime.date(2021, 1, 1)
    end_date,  # DateTime.date instance, eg: datetime.date(2021, 10, 1)
    factor_list=None,  # python list
    freq='D'
):
    assert isinstance(start_date, datetime.date), "start_date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "end_date must be an instance of datetime.date"
    assert freq in ("D", "W"), "freq需为D或者W"
    conn = irm.irm_connectIRMDB()
    start_date = start_date.strftime("%Y%m%d")
    end_date = end_date.strftime("%Y%m%d")
    sql = "select * from irm.factor_return_table where date>='{0}' and date<='{1}' and data_source = 'CITICSAM'"
    df_factor_return = pd.read_sql_query(sql.format(start_date, end_date), conn).rename(columns=str.lower)
    conn.close()
    if freq == 'W':
        df_factor_return = calendar.calender_convertDailyReturnToWeekly(df_factor_return, 'date', 'factor_return', 'factor_name')
    df_factor_return = pd.pivot_table(df_factor_return, index=['date'], columns=['factor_name'], values=['factor_return'])['factor_return']
    df_factor_return.columns.name = ''
    df_factor_return.reset_index(inplace=True)
    df_factor_return.rename(columns=const.CTA_FACTOR_NAME_DICT, inplace=True)
    if factor_list:
        assert isinstance(factor_list, list), "factor list must be a list"
        assert set(factor_list).issubset(set(const.CTA_FACTOR_NAME_DICT.values())), "factor list must be a subset of all factors"
        df_factor_return = df_factor_return[['date'] + factor_list]
    df_factor_return.columns = map(str.lower, df_factor_return)
    df_factor_return['date'] = pd.to_datetime(df_factor_return['date']).dt.date
    return df_factor_return

# ------------------------------------------------------------------------
# 读取CTA因子的收益构成信息
# ------------------------------------------------------------------------
def cta_getCtaFactorInfo(
    start_date,  # DateTime.date instance, eg: datetime.date(2021, 1, 1)
    end_date,  # DateTime.date instance, eg: datetime.date(2021, 10, 1)
):
    assert isinstance(start_date, datetime.date), "start_date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "end_date must be an instance of datetime.date"
    conn = irm.irm_connectIRMDB()
    start_date = start_date.strftime("%Y%m%d")
    end_date = end_date.strftime("%Y%m%d")
    sql = "select * from irm.amfof_factor_return_info_cta where date>='{0}' and date<='{1}'"
    df_factor_return_info = pd.read_sql_query(sql.format(start_date, end_date), conn).rename(columns=str.lower)
    conn.close()
    df_factor_return_info = df_factor_return_info[df_factor_return_info['factor_return_name'].isin(list(const.CTA_FACTOR_NAME_DICT.keys()))]
    df_factor_return_info['factor_return_name'].replace(const.CTA_FACTOR_NAME_DICT, inplace=True)
    df_factor_return_info.columns = map(str.lower, df_factor_return_info)
    df_factor_return_info['date'] = pd.to_datetime(df_factor_return_info['date']).dt.date
    return df_factor_return_info