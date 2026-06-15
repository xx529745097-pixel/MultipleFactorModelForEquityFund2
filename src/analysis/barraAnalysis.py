import numpy as np
import pandas as pd
from WindPy import w
import src.data.barra as barra
import src.data.wind as wd
import src.data.quantFundData as qfd
import src.data.fundamentalFundData as ffd
import src.data.custHF as custHF
import src.data.amdata as amdata
import src.data.irm as irm
import src.const as const
import src.utils.Calculation as cal
import datetime
import cx_Oracle

# ------------------------------------------------------------------------
# 计算factor correlation, 详细的methodology请见 Nomura Global Quant Equity Conference 2011
# ------------------------------------------------------------------------
def barraAnal_calFactorCorr(
    start_date,  # DateTime.date instance, eg: datetime.date(2021, 1, 1)
    end_date,  # DateTime.date instance, eg: datetime.date(2021, 10, 1)
    rolling_window,  # int, 使用过去多少天的数据来计算correlation
    factor_list=None  # python list
):
    w.start()
    start_date = w.tdaysoffset(-rolling_window, start_date.strftime("%Y-%m-%d"), "").Times[0]
    df_factor_return = barra.barra_getBarraFactorDailyReturn(start_date, end_date, factor_list)
    df_factor_return.set_index('date', inplace=True)
    corr_df = df_factor_return.rolling(rolling_window).corr(pairwise=True)
    num_fac = corr_df.shape[1]
    fac_ret_corr_dict = dict()
    corr_df.dropna(inplace=True)
    for idx in corr_df.index:
        idx_ = idx[0]
        fac_ret_corr_dict[idx_] = ((abs(corr_df.loc[idx_].values).sum() - num_fac) / 2) / ((num_fac ** 2 - num_fac) / 2)
    fac_ret_corr_dict = {'date': list(fac_ret_corr_dict.keys()), 'factor_corr': list(fac_ret_corr_dict.values())}
    corr_avg_df = pd.DataFrame.from_dict(fac_ret_corr_dict)

    return corr_avg_df

# ------------------------------------------------------------------------
# 计算barra因子区间净值
# ------------------------------------------------------------------------
def barraAnal_calFactorNav(
    start_date,  # DateTime.date instance, eg: datetime.date(2021, 1, 1)
    end_date,  # DateTime.date instance, eg: datetime.date(2021, 10, 1)
    factor_list=None  # python list
):
    assert isinstance(start_date, datetime.date), "date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "date must be an instance of datetime.date"
    if factor_list:
        assert isinstance(factor_list, list), 'factor_list much be a list instance'

    barra_daily_return = barra.barra_getBarraFactorDailyReturn(start_date, end_date, factor_list)
    barra_daily_return['date'] = pd.to_datetime(barra_daily_return['date']).dt.date
    barra_daily_return.set_index('date', inplace=True)
    barra_daily_nav = (barra_daily_return + 1).cumprod(axis=0)
    barra_daily_nav.loc[barra_daily_return.index[0] - datetime.timedelta(days=const.const.FREQ_INTERVAL['D'])] = 1
    barra_daily_nav = barra_daily_nav.sort_index()
    result = barra_daily_nav.reset_index()
    return result

# ------------------------------------------------------------------------
# 计算barra因子区间收益指标
# ------------------------------------------------------------------------
def barraAnal_calFactorPerf(
    start_date,  # DateTime.date instance, eg: datetime.date(2021, 1, 1)
    end_date,  # DateTime.date instance, eg: datetime.date(2021, 10, 1)
    factor_list=None  # python list
):
    assert isinstance(start_date, datetime.date), "date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "date must be an instance of datetime.date"
    if factor_list:
        assert isinstance(factor_list, list), 'factor_list much be a list instance'

    barra_daily_return = barra.barra_getBarraFactorDailyReturn(start_date, end_date, factor_list).set_index('date')
    barra_daily_return.index = pd.to_datetime(barra_daily_return.index)
    factor_perf = dict()
    for factor_col in barra_daily_return.columns:
        factor_perf[factor_col] = cal.basicCal_calPerformanceStats(barra_daily_return[factor_col], freq='D', stats=const.const.COMMON_PERF_STATS)
    result = pd.DataFrame.from_dict(factor_perf).T
    result.reset_index(inplace=True)
    result.rename(columns={'index': 'style_factor'}, inplace=True)
    return result

# ------------------------------------------------------------------------
# 计算barra factor weekly/monthly return
# ------------------------------------------------------------------------
def barraAnal_calFactorReturn(
    start_date,  # DateTime.date instance, eg: datetime.date(2021, 1, 1)
    end_date,  # DateTime.date instance, eg: datetime.date(2021, 10, 1)
    freq,  # 'W' or 'M'
    factor_list=None  # python list
):
    assert isinstance(start_date, datetime.date), "date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "date must be an instance of datetime.date"
    assert freq in ('W', 'M'), 'freq must be either M or W'
    if factor_list:
        assert isinstance(factor_list, list), 'factor_list much be a list instance'

    daily_return = barra.barra_getBarraFactorDailyReturn(start_date, end_date, factor_list)
    daily_return.set_index('date', inplace=True)
    result = list()
    for factor in daily_return.columns:
        factor_monthly_return = cal.basicCal_getCalendarPeriodReturn(daily_return[factor], 'M')
        factor_monthly_return = factor_monthly_return.to_frame(factor)
        result.append(factor_monthly_return)
    result = pd.concat(result, axis=1, join='outer').sort_index(ascending=False)
    return result

# ------------------------------------------------------------------------
# 根据估值表计算fund的barra因子暴露
# ------------------------------------------------------------------------
def barraAnal_calFundExposureFromValuationSheet(
    start_date,   # DateTime.date instance
    end_date,  # DateTime.date instance
    product_code
):
    assert isinstance(start_date, datetime.date), "date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "date must be an instance of datetime.date"
    assert product_code.endswith('.OF'), '产品代码须在原6位后加上.OF'

    fund_data = custHF.custHF_getDataFromValuationSheet(product_code, start_date, end_date)
    fund_data = fund_data[['date', 'stock_id', 'weight']]
    stock_list = list(fund_data['stock_id'].unique())
    date_list = fund_data['date'].unique().tolist()
    stock_exposure = barra.barra_getStockExposure(method="discrete", start_date=start_date, end_date=end_date, factor_type="STYLE", stock_list=stock_list, date_list=date_list)
    df = pd.merge(fund_data, stock_exposure, left_on=['date', 'stock_id'], right_on=['date', 'stock_id'], how='left')
    df['exposure_temp'] = df['weight'] * df['exposure']
    df = df.groupby(['date', 'factor'])['exposure_temp'].sum()
    df = df.to_frame().pivot_table(index='date', columns='factor', values='exposure_temp')
    df['product_id'] = product_code
    df.reset_index(inplace=True)
    return df

# ------------------------------------------------------------------------
# 计算fund相对某一指数的barra因子暴露
# ------------------------------------------------------------------------
def barraAnal_calRelativeBarraFactorExposure(
    index_code,  # must be in "HS300", "ZZ100", "ZZ500", "ZZ800", "ZZ1000", "ZERO_BM", "Customized"
    start_date,  # DateTime.date instance
    end_date,  # DateTime.date instance
    fund_data_source,  # "ValuationSheet" or "CustodianQuant" or "CustodianFunda"
    fund_id=None,  # fund's id, e.g. SLR151.OF
    customized_bm_weight_dict=None  # dict, 仅当benchmark为Customized时生效
):
    assert isinstance(start_date, datetime.date), "date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "date must be an instance of datetime.date"
    assert fund_data_source in ("ValuationSheet", "CustodianQuant", "CustodianFunda"), "基金数据来源只能是ValuationSheet、CustodianQuant、CustodianFunda"
    assert index_code in ("HS300", "ZZ100", "ZZ500", "ZZ800", "ZZ1000", "ZERO_BM", 'Customized'), "目前只支持沪深300，中证100， 中证500， 中证800， 中证1000， ZERO_BM， Customized"

    if fund_data_source == "CustodianQuant":
        fund_data = qfd.qfd_getQuantFundsExposure(start_date, end_date, product_ids=[fund_id] if fund_id else None)
    elif fund_data_source == "CustodianFunda":
        fund_data = ffd.ffd_getFundamentalFundsExposure(start_date, end_date, product_ids=[fund_id] if fund_id else None)
    else:
        assert fund_id is not None, "如果数据源为估值表则产品代码不能为空"
        fund_data = barraAnal_calFundExposureFromValuationSheet(start_date, end_date, product_code=fund_id)
    barra_factor_list = [s.lower() for s in const.const.BARRA_STYLE_FACTOR]
    if index_code == 'Customized':
        assert isinstance(customized_bm_weight_dict, dict), "customized_bm_weight类型需为dict"
        assert set(customized_bm_weight_dict.keys()) <= {'ZZ500', 'HS300', 'ZZ1000', 'ZZ800', 'ZERO_BM'}, "customized_bm_weight的keys需在('ZZ500','HS300','ZZ1000','ZZ800','ZERO_BM')中"
        assert abs(sum(customized_bm_weight_dict.values()) - 1) < const.const.EPSILON, "customized_bm_weight权重求和需等于1"
        index_codes = [index_code for index_code in customized_bm_weight_dict.keys() if index_code != 'ZERO_BM']  # 底层数据不支持ZERO_BM，提前过滤对结果无影响
        if index_codes:
            index_data = barra.barra_readIndexBarraFactorExposure(start_date=start_date, end_date=end_date, index_codes=index_codes)
            melted_index_data = pd.melt(index_data, id_vars=['date', 'index_code'], value_vars=barra_factor_list, var_name='style_factor', value_name='exposure')
            code_to_index_name_map = dict(zip(const.const.INDEX_NAME_TO_CODE_MAP.values(), const.const.INDEX_NAME_TO_CODE_MAP.keys()))
            melted_index_data['exposure'] = melted_index_data.apply(lambda x: x['exposure'] * customized_bm_weight_dict[code_to_index_name_map[x['index_code']]], axis=1)
            # 对index exposure按自定义基准比例加权求和
            melted_index_data = melted_index_data.groupby(['date', 'style_factor'], as_index=False).agg({'exposure': 'sum'})
            index_data = pd.pivot_table(melted_index_data, index=['date'], columns='style_factor', values='exposure').reset_index()
            data = pd.merge(fund_data, index_data[['date'] + barra_factor_list], on='date', how='left')
            for factor in barra_factor_list:
                data[factor + '_excess'] = data[factor + '_x'] - data[factor + '_y']
        else:  # 如果自定义权重仅包括'ZERO_BM'(即等同基准选择'ZERO_BM')，则单独处理
            data = fund_data
            for factor in barra_factor_list:
                data[factor + '_excess'] = data[factor]
    elif index_code != 'ZERO_BM':  # 如果不是用零基准做bm
        index_data = barra.barra_readIndexBarraFactorExposure(start_date=start_date, end_date=end_date, index_codes=[index_code])
        data = pd.merge(fund_data, index_data[['date'] + barra_factor_list], on='date', how='left')
        for factor in barra_factor_list:
            data[factor + '_excess'] = data[factor + '_x'] - data[factor + '_y']
    else:
        data = fund_data
        for factor in barra_factor_list:
            data[factor + '_excess'] = data[factor]
    data = data[['date', 'product_id'] + [x for x in data.columns if x.endswith('_excess')]]
    data['benchmark'] = index_code
    return data

####################################################################
# WRITE API
####################################################################

# ------------------------------------------------------------------------
# 计算某一指数的barra因子暴露并写入数据库
# ------------------------------------------------------------------------
def barraAnal_calAndWriteIndexBarraFactorExposure(
    index_code,  # must be in "HS300", "ZZ100", "ZZ500", "ZZ800", "ZZ1000"
    start_date,  # DateTime.date instance
    end_date,  # DateTime.date instance
    insert=False
):
    assert index_code in ("HS300", "ZZ100", "ZZ500", "ZZ800", "ZZ1000"), "目前只支持沪深300，中证100， 中证500， 中证800， 中证1000"
    assert isinstance(start_date, datetime.date), "date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "date must be an instance of datetime.date"
    index_data = wd.wind_getStockIndexComponentsWeight(index_code, start_date, end_date)
    index_components = list(index_data['stock_id'].unique())
    stock_exposure = barra.barra_getStockExposure(method='continuous', start_date=start_date, end_date=end_date, factor_type="STYLE", stock_list=index_components)
    df = pd.merge(index_data, stock_exposure, left_on=['date', 'stock_id'], right_on=['date', 'stock_id'], how='left')
    df['exposure_temp'] = df['weight'] * df['exposure']
    df = df.groupby(['date', 'factor'])['exposure_temp'].sum()
    df = df.to_frame().pivot_table(index='date', columns='factor', values='exposure_temp')
    df.reset_index(inplace=True)
    df['index_code'] = index_code
    if insert:
        bm_name_id_mapping = {
            'ZZ500': '000905.SH',
            'HS300': '000300.SH',
            'ZZ1000': '000852.SH',
            'ZZ800': '000906.SH'
        }
        df.rename(columns={'index_code': 'id_code', 'date': 'dt', 'size': 'sz'}, inplace=True)
        df['id_code'] = bm_name_id_mapping[index_code]
        df['id_type'] = 'index'
        df = df[['dt', 'id_code', 'id_type', 'beta', 'btop', 'earnyild', 'growth', 'leverage', 'liquidty', 'momentum', 'resvol', 'sz', 'sizenl']]
        df['id_code'] = df['id_code'].astype('string')
        df['id_type'] = df['id_type'].astype('string')

        # amdata数据库
        # Delete existing key if exists
        conn = amdata.amdata_connectAmdataDb()
        sql = "DELETE FROM AMFOF.PRODUCT_BARRA_EXPOSURE WHERE dt>= DATE'{0}' and dt <= DATE'{1}' and id_code = '{2}'"
        sql = sql.format(start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'), const.const.INDEX_NAME_TO_CODE_MAP[index_code])
        cur = conn.cursor()
        cur.execute(sql)
        conn.commit()

        # Write into database
        amdata.amdata_insertAMData(df, 'AMFOF.PRODUCT_BARRA_EXPOSURE')

        # IRM数据库
        conn = irm.irm_connectIRMDB()
        sql = "DELETE FROM irm.AMFOF_PRODUCT_BARRA_EXPOSURE WHERE dt>= DATE'{0}' and dt <= DATE'{1}' and id_code = '{2}'"
        sql = sql.format(str(start_date.strftime('%Y-%m-%d')), str(end_date.strftime('%Y-%m-%d')), const.const.INDEX_NAME_TO_CODE_MAP[index_code])
        cur = conn.cursor()
        cur.execute(sql)
        conn.commit()

        # Write into database
        irm.irm_insertIRMData(df, 'irm.AMFOF_PRODUCT_BARRA_EXPOSURE')
    return df

# ------------------------------------------------------
# 根据托管数据拆解某一量化、多头产品的超额收益
# 返回：剥离了风格因子后的超额收益，风格因子带来的超额收益，产品相对于基准的超额收益
# ------------------------------------------------------

def barraAnal_decomposeExcessReturn(
    product_id,  # 产品代码 'SGR167.OF'
    start_date,  # datetime.date instance
    end_date,  # datetime.date instance
    return_benchmark,  # must be in "HS300", "ZZ100", "ZZ500", "ZZ800", "ZZ1000", "ZERO_BM", "ZERO_BM" for market neutral
    holding_benchmark,  # must be in "HS300", "ZZ100", "ZZ500", "ZZ800", "ZZ1000", "ZERO_BM", "ZERO_BM" for market neutral
    fund_data_source='CustodianQuant'  # "CustodianQuant" or "CustodianFunda"
):
    assert isinstance(start_date, datetime.date), "date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "date must be an instance of datetime.date"
    assert return_benchmark in ('ZZ500', 'HS300', 'ZZ1000', 'ZZ800', 'ZERO_BM'), 'benchmark只能为ZZ500, HS300, ZZ1000, ZZ800, ZERO_BM中的一个'
    assert holding_benchmark in ('ZZ500', 'HS300', 'ZZ1000', 'ZZ800', 'ZERO_BM'), 'benchmark只能为ZZ500, HS300, ZZ1000, ZZ800, ZERO_BM中的一个'
    assert fund_data_source in ("CustodianQuant", "CustodianFunda"), "CustodianQuant、CustodianFunda"
    bm_name_id_mapping = {
        'ZZ500': '000905.SH',
        'HS300': '000300.SH',
        'ZZ1000': '000852.SH',
        'ZZ800': '000906.SH',
        'ZERO_BM': 'ZERO_BM'
    }

    barra_factor_rela_expo = barraAnal_calRelativeBarraFactorExposure(holding_benchmark, start_date - datetime.timedelta(15), end_date, fund_data_source=fund_data_source, fund_id=product_id)
    assert product_id in barra_factor_rela_expo['product_id'].to_list(), '托管数据中不存在该产品'
    barra_factor_rela_expo = barra_factor_rela_expo[['date'] + [x for x in barra_factor_rela_expo.columns if x.endswith('_excess')]]
    barra_factor_rela_expo.set_index('date', inplace=True)
    barra_factor_rela_expo.sort_index(inplace=True)
    # 目前认为取T-1exposure的均值更符实际，而不是两日均值
    barra_factor_rela_expo = barra_factor_rela_expo.shift(1)
    barra_factor_daily_return = barra.barra_getBarraFactorDailyReturn(start_date - datetime.timedelta(15), end_date, const.const.BARRA_STYLE_FACTOR)
    barra_factor_rela_expo.columns = [x.replace('_excess', '') for x in barra_factor_rela_expo.columns.to_list()]
    barra_factor_daily_return = barra_factor_daily_return.set_index('date').loc[barra_factor_rela_expo.index]
    barra_factor_daily_return = barra_factor_daily_return[barra_factor_rela_expo.columns.to_list()]
    barra_factor_excess_return=pd.DataFrame(np.multiply(barra_factor_rela_expo.values, barra_factor_daily_return.values), index=barra_factor_daily_return.index, columns=barra_factor_daily_return.columns)
    barra_factor_excess_return['barra_excess_return'] = barra_factor_excess_return.sum(axis=1)
    # 产品return数据以custHF的数据源为准
    product_ret_d = custHF.custHF_getHFReturn([product_id], start_date, end_date, 'D', 'Product')
    # 需判断return_bm是否是"0", 是否要走wind取数
    if bm_name_id_mapping[return_benchmark] != 'ZERO_BM':
        # bm后续涉及price转return_rate的过程，故取数需要多往前取
        bm_close_price = wd.wind_getIndexData(bm_name_id_mapping[return_benchmark], start_date - datetime.timedelta(15), end_date, 'D')[['date', 'close_price']]
        bm_close_price.set_index('date', inplace=True)
        bm_ret_d = bm_close_price.pct_change().reset_index().rename(columns={'close_price': 'bm_return_rate'})
    else:
        bm_ret_d = cal.basicCal_getConstBMCurve(start_date - datetime.timedelta(15), end_date, const_return=0, return_col_name='bm_return_rate')
    bm_ret_d['id'] = return_benchmark
    # 将bm_ret_d与product_ret_d日期对齐
    bm_ret_d = pd.merge(product_ret_d, bm_ret_d, on='date', how='left')[['date', 'bm_return_rate']].set_index('date')
    barra_factor_excess_return = pd.merge(product_ret_d, barra_factor_excess_return.reset_index(), on='date', how='left')[['date']+list(barra_factor_excess_return.columns)].set_index('date')
    product_ret_d.set_index('date', inplace=True)
    product_excess_return = product_ret_d['adj_return_rate'] - bm_ret_d['bm_return_rate']
    pure_alpha = product_excess_return - barra_factor_excess_return['barra_excess_return']
    return pure_alpha, barra_factor_excess_return['barra_excess_return'], product_excess_return, barra_factor_excess_return[list(barra_factor_daily_return.columns)]

# ------------------------------------------------------
# 获取私募量化产品超额收益拆分汇总表
# 支持多产品的list输入
# ------------------------------------------------------
def barraAnal_decomposeExcessReturnTable(
    start_date,         # datetime.date instance
    end_date,           # datetime.date instance
    return_benchmark,  # must be in "HS300", "ZZ100", "ZZ500", "ZZ800", "ZZ1000", "ZERO_BM", "ZERO_BM" for market neutral
    holding_benchmark,  # must be in "HS300", "ZZ100", "ZZ500", "ZZ800", "ZZ1000", "ZERO_BM", "ZERO_BM" for market neutral
    product_ids=None,   # 量化私募产品ID list
):
    product_info = custHF.custHF_getProductInfo()
    exposure_product_ids = qfd.qfd_getQuantFundsExposure(start_date, end_date)['product_id'].unique().tolist()
    if product_ids:
        # 筛选出有托管暴露数据的id
        product_ids = list(set(product_ids) & set(exposure_product_ids))
    else:
        product_ids = exposure_product_ids
    result = pd.DataFrame(columns=['product_id', 'pure_alpha', 'barra_factor_excess_return','product_excess_return', 'start_date', 'end_date'])
    barra_single_factor_list=[]
    for product_id in product_ids:
        # FIXME 存在刚由套利切换为指增的产品，暂无barra数据导致报错
        try:
            pure_alpha, barra_factor_excess_return, product_excess_return, single_factor_return = barraAnal_decomposeExcessReturn(product_id, start_date, end_date, return_benchmark, holding_benchmark)
            # 对于只有暴露数据但无收益数据的产品，跳过
            if pure_alpha.fillna(0).sum() == 0:
                continue
            result = result.append({'product_id': product_id,
                                    'pure_alpha': (pure_alpha.fillna(0) + 1).cumprod()[-1] - 1,
                                    'barra_factor_excess_return': (barra_factor_excess_return.fillna(0) + 1).cumprod()[-1] - 1,
                                    'product_excess_return': (product_excess_return.fillna(0) + 1).cumprod()[-1] - 1,
                                    'start_date': pure_alpha.dropna().index.min(),
                                    'end_date': pure_alpha.dropna().index.max()}, ignore_index=True)
            barra_factor_cumret=((single_factor_return.dropna() + 1).cumprod().iloc[-1] - 1).to_frame().T
            barra_factor_cumret['product_id'] = product_id
            barra_single_factor_list.append(barra_factor_cumret)
        except:
            print('托管数据暂时缺数：'+product_id)
    barra_single_factor = pd.concat(barra_single_factor_list, axis=0)
    result = pd.merge(result, product_info[['product_id', 'product_short_name']], how='left', on='product_id')
    result['benchmark'] = return_benchmark
    result = result[['product_id', 'product_short_name', 'benchmark', 'start_date', 'end_date', 'pure_alpha', 'barra_factor_excess_return', 'product_excess_return']]
    result = result.merge(barra_single_factor, how='left', on='product_id')
    result = result.sort_values('product_excess_return', ascending=False).reset_index(drop=True)
    return result