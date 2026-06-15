import pandas as pd
import datetime
import src.data.wind as wd
import src.data.quantFundData as qfd
import src.data.custHF as custHF
import src.data.barra as barraData
import src.const as const

# ------------------------------------------------------
# 根据估值表计算300、500、1000内比例
# ------------------------------------------------------
def qfa_calStockIndexComponentRatio(
    start_date,  # datetime.date instance
    end_date,  # datetime.date instance
    product_ids  # e.g. ['SLR151.OF']
):
    assert isinstance(start_date, datetime.date), "date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "date must be an instance of datetime.date"
    assert isinstance(product_ids, list), 'product_ids需为list'
    assert not [product_id for product_id in product_ids if not product_id.endswith('.OF')], 'product_ids中的代码需以.OF结尾'

    result = []
    for product_id in product_ids:
        product_data = custHF.custHF_getDataFromValuationSheet(product_id, start_date, end_date)
        hs300_data = wd.wind_getStockIndexComponentsWeight('HS300', start_date, end_date)
        zz500_data = wd.wind_getStockIndexComponentsWeight('ZZ500', start_date, end_date)
        stock_data = pd.concat([hs300_data, zz500_data], axis=0)
        data = pd.merge(product_data, stock_data[['date', 'stock_id', 'index_code']], left_on=['date', 'stock_id'], right_on=['date', 'stock_id'], how='left')
        data = data.groupby(['date', 'index_code'])['weight'].sum().unstack()
        data['Other'] = 1 - data['HS300'] - data['ZZ500']
        data.reset_index(inplace=True)
        data['product_id'] = product_id
        result.append(data)
    result = pd.concat(result, axis=0)
    return result

# ------------------------------------------------------
# 计算最大单票比例
# ------------------------------------------------------
def qfa_calSingleStockMaxWeight(
    start_date,  # datetime.date instance
    end_date,  # datetime.date instance
    product_ids  # e.g. ['SLR151.OF']
):
    assert isinstance(start_date, datetime.date), "date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "date must be an instance of datetime.date"
    assert isinstance(product_ids, list), 'product_ids需为list'
    assert not [product_id for product_id in product_ids if not product_id.endswith('.OF')], 'product_ids中的代码需以.OF结尾'

    result = []
    for product_id in product_ids:
        product_data = custHF.custHF_getDataFromValuationSheet(product_id, start_date, end_date)
        data = product_data.groupby('date')['weight'].max().reset_index()
        data['product_id'] = product_id
        result.append(data)
    result = pd.concat(result, axis=0)
    return result

# ------------------------------------------------------
# 计算前十大股票占比
# ------------------------------------------------------
def qfa_calTop10StockWeight(
    start_date,  # datetime.date instance
    end_date,  # datetime.date instance
    product_ids  # e.g. ['SLR151.OF']
):
    assert isinstance(start_date, datetime.date), "date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "date must be an instance of datetime.date"
    assert isinstance(product_ids, list), 'product_ids需为list'
    assert not [product_id for product_id in product_ids if not product_id.endswith('.OF')], 'product_ids中的代码需以.OF结尾'
    result = []
    for product_id in product_ids:
        product_data = custHF.custHF_getDataFromValuationSheet(product_id, start_date, end_date)
        data = product_data.groupby('date').apply(lambda _df: _df.sort_values(by='weight', ascending=False).head(10)['weight'].sum())
        data = data.to_frame('Top10Weight').reset_index()
        data['product_id'] = product_id
        result.append(data)
    result = pd.concat(result, axis=0)
    return result



# --------------------------------------------------------------
# 获取多个量化私募行业占比数据，行业转为中文
# 默认取日期区间内最新的行业占比，数据只有A股，默认使用原始权益权重，不张成100%
# --------------------------------------------------------------
def qfa_getListedQuantFundIndustryWeightDetails(
    report_date,            # 参考报告的截至日期，输入格式:datetime.date
    product_id,             # product_id基金代码，应为list格式（因数据库存储问题，优先使用场内代码）
    expand_weight=False,    # 是否将单只基金的行业比例之和张成100%，默认为否；对基金单独分析时可张成100%，对FOF组合分析时此步骤为否
):
    start_date = report_date - datetime.timedelta(30)  # 先选取近一个月的exposure内容，再取最近一期
    df = qfd.qfd_getQuantFundsExposure(start_date, report_date, product_id)
    # FIXME 标准组合中，使用500股指期货主连，穿透时相当于满仓运行的指增，进行行业穿透时，使用500的行业分布进行代替
    if 'IC.CFE' in product_id:
        ZZ500_index_industry = wd.wind_getIndexIndustryWeight('000905.SH', datetime.date.today(), 'SW', 1)
        ZZ500_index_industry['product_id'] = 'IC.CFE'
    elif df.empty:
        return pd.DataFrame()
    # 取最新一期报告结果
    df = df[df['date'] == df['date'].max()]
    sw_industry = pd.DataFrame({'chinese': const.const.SW_INDUSTRY_NAME_CN_TO_EN.keys(),
                                'english': const.const.SW_INDUSTRY_NAME_CN_TO_EN.values()})
    col_list = ['date','product_id', 'net_stock'] + list(sw_industry['english'])
    df = df[col_list]
    melted = pd.melt(df, id_vars='product_id',value_vars=list(sw_industry['english'])).rename(columns={'variable': 'industry', 'value': 'industry_weight'})
    result = melted.sort_values(['product_id', 'industry_weight'], ascending=[True, False]).reset_index(drop=True)
    dict_industry = dict(zip(sw_industry['english'],sw_industry['chinese']))
    result.replace({'industry': dict_industry}, inplace=True)
    # FIXME 标准组合中，使用500股指期货主连，穿透时相当于满仓运行的指增，进行行业穿透时，使用500的行业分布进行代替
    if 'IC.CFE' in product_id:
        result = result.append(ZZ500_index_industry[['product_id', 'industry', 'industry_weight']])
        df = df.append({'product_id': 'IC.CFE', 'net_stock': 1}, ignore_index=True)
    # 先将一支基金内的行业权重和张为100%
    result = result.set_index(['product_id', 'industry']).groupby(level=0).apply(lambda x: x/x.sum()).reset_index()
    if not expand_weight:  # 如果选择不张为100%，则用上面结果再乘以权益部分的比例，精确到产品权益比例去刻画行业分布
        result = pd.merge(result, df[['product_id', 'net_stock']].drop_duplicates(), on='product_id', how='left')
        result['industry_weight'] = result['industry_weight'] * result['net_stock']
        del result['net_stock']
    result['industry_level'] = 'SW_1'
    result['report_date'] = df['date'].iloc[0]
    return result


# ------------------------------------------------------
# 获取所有产品的行业或Barra原始数据
# ------------------------------------------------------
def qfa_getFundDataFromCustodian(
    start_date,
    end_date,
    data_type='INDUSTRY',  # 输出的数据类型，目前支持行业权重或者Barra
    excess_bm='ZERO_BM',  # Barra暴露是否计算超额及其使用哪个基准
):
    assert data_type in ('INDUSTRY', 'BARRA'), "取数类型仅支持行业数据和Barra"
    if data_type == 'INDUSTRY':
        assert excess_bm == 'ZERO_BM', "行业数据暂不支持输出超额"
    else:
        assert excess_bm in ("ZERO_BM", "HS300", "ZZ100", "ZZ500", "ZZ800", "ZZ1000"), "目前只支持ZERO_BM，沪深300，中证100， 中证500， 中证800， 中证1000"
    exp = qfd.qfd_getQuantFundsExposure(start_date, end_date)
    level_info = custHF.custHF_getProductInfo()
    barra_factor_list = [s.lower() for s in const.const.BARRA_STYLE_FACTOR]
    exp = exp.merge(level_info[['product_id', 'product_short_name', 'label_level_1', 'label_level_2']], how='left', on='product_id')
    if excess_bm != 'ZERO_BM':  # 如果不是用零基准做bm
        index_data = barraData.barra_readIndexBarraFactorExposure(start_date=start_date, end_date=end_date, index_codes=[excess_bm])
        index_data = index_data[index_data['date'].isin(exp['date'].to_list())]
        exp = pd.merge(exp, index_data, left_on='date', right_on='date', how='left')
        for factor in barra_factor_list:
            exp[factor + '_excess'] = exp[factor + '_x'] - exp[factor + '_y']
            del exp[factor + '_x'], exp[factor + '_y']
        barra_factor_list = ['index_code'] + [s+'_excess' for s in barra_factor_list]
    to_project = ['date', 'product_id', 'product_short_name', 'label_level_1', 'label_level_2'] + (barra_factor_list if data_type == 'BARRA'
                else ['net_stock', 'stock', 'future'] + list(const.const.SW_INDUSTRY_NAME_CN_TO_EN.values()))
    exp = exp[to_project]
    sw_map = dict(zip(const.const.SW_INDUSTRY_NAME_CN_TO_EN.values(), const.const.SW_INDUSTRY_NAME_CN_TO_EN.keys()))
    exp.rename(columns=sw_map, inplace=True)
    exp.rename(columns={'date': '日期', 'product_id': '产品ID', 'product_short_name': '产品名称', 'index_code': '基准指数', 'label_level_1': '一级标签',
                        'label_level_2': '二级标签', 'net_stock': '净仓位', 'stock': '股票', 'future': '期货'}, inplace=True)
    return exp
