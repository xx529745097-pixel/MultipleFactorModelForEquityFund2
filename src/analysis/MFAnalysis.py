# ------------------------------------------------
# 本文档用于公募基金数据分析
# ------------------------------------------------
import src.data.wind as wind
import src.utils.Calculation as Cal
import statsmodels.api as sm
import pandas as pd
import datetime
import copy
import src.data.custMF as custMF
from src.const import *
from src.data.amdata import *
from src.data.wind import *
from src.analysis.StockAnalysis import *
from WindPy import w
import numpy as np
from sklearn.linear_model import LinearRegression
from src.utils.Calculation import *
import src.utils.fof_calendar as fof_calendar

# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# 0. 内部函数
# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------

# ----------------------------------------------------
# 内部函数，匹配每个股票的行业，并可选是否给港股打上港股标签，美股默认直接打上美股标签
# ----------------------------------------------------
def _getIndustry(
        portfolio,          # dataframe，需要填充行业的组合
        company,            # 分类标准，输入格式:str，'SW' or 'CITICS'
        level,              # 分类级别，输入格式:int
        mask_h_shares=True, # 是否将港股的行业全部置为“港股”，默认为是
):
    assert (company == 'SW' or company == 'CITICS'), 'company必须为SW或CITICS'
    assert (type(level) == int), 'level输入格式需为int'
    # 行业填充 仅包含A股和港股不包含美股
    industry = wind.wind_getAllHistIndustriesMap(company, level)
    portfolio = pd.merge(portfolio, industry, on='stock_id', how='left')
    portfolio = portfolio.loc[
        ((portfolio['date'] >= portfolio['entry_dt']) & (portfolio['date'] <= portfolio['remove_dt'])) | (portfolio['stock_market'] == 'US')].reset_index(
        drop=True)  # 因美股不在行业映射表中 需要额外判断防止日期筛选时被遗漏
    del portfolio['entry_dt'], portfolio['remove_dt']  # 新股会在上市前出现在季报里面，当时没有行业分类，上一步会把当时没有分类的股票删掉
    if mask_h_shares:
        # 港股全都贴上港股标签
        portfolio.industry = portfolio.apply(lambda x: '港股' if x.stock_market == 'H' else x.industry, axis=1)
    # 因行业分类标准并非覆盖全部美股, 美股全都贴上美股标签
    portfolio.industry = portfolio.apply(lambda x: '美股' if x.stock_market == 'US' else x.industry, axis=1)
    portfolio.drop(columns='stock_market', inplace=True)
    portfolio = portfolio.sort_values(by=['date', 'stk_value_to_nav'], ascending=False).reset_index(drop=True)
    return portfolio

# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# 1. 基金经理概述
# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------

# ------------------------------------------------
# 基金经理个人情况
# ------------------------------------------------
def anlsMF_pmInfo(
    fundManager,      # 基金经理
    fundCompany,      # 基金公司
):
    funddf = wind_getCurrentProductList(include_pm_info= True)
    funddf = funddf[(funddf['pm_name'] ==fundManager) & (funddf['company_short_name'] ==fundCompany)]
    df_pminfo = wind.wind_getPMInfo(funddf['pm_id'].unique()[0])
    return df_pminfo

# ------------------------------------------------
# 基金经理所管产品的时序数据，包括：规模、份额、机构持有份额、股票比例、债券比例
# 返回一个表格Df。
# ------------------------------------------------
def anlsMF_allProductTSInfoOfPM(
        fundManager,      # 基金经理
        fundCompany,      # 基金公司
        date              # 日期
):
    w.start()
    LastReportDate = wind_getLastReportDate(date)
    funddf = wind_getCurrentProductList(include_pm_info= True)
    funddf = funddf[(funddf['pm_name'] ==fundManager) & (funddf['company_short_name'] ==fundCompany)]
    fundList = funddf['product_id'].tolist()
    fundCodes = ','.join(fundList)
    df_output = pd.DataFrame(columns = ['product_id', 'date', 'NETASSET_TOTAL', 'UNIT_TOTAL', 'HOLDER_INSTITUTION_TOTALHOLDING',
                                        'PRT_STOCKTONAV', 'PRT_BONDTONAV','FUND_MANAGER_STARTDATE'])
    def startDateComparision(row):
        if row['FUND_MANAGER_STARTDATE'] > row['date']:
            row['NETASSET_TOTAL'] = np.nan
            row['PRT_STOCKTONAV'] = np.nan
            row['PRT_BONDTONAV'] = np.nan
            row['HOLDER_INSTITUTION_TOTALHOLDING'] = np.nan
            row['UNIT_TOTAL'] = np.nan
        return row
    for reportPeriodForward in range(28):
        fundInfo = w.wss(fundCodes,
                            "sec_name, netasset_total,holder_institution_totalholding,unit_total,prt_stocktonav,prt_bondtonav,fund_manager_startdate",
                            "unit=1;tradeDate={0};rptDate={1};order=1".format(LastReportDate, LastReportDate))
        fundInfoDf = pd.DataFrame(pd.DataFrame(fundInfo.Data).values.T, columns= fundInfo.Fields)
        fundInfoDf['product_id'] = fundList
        fundInfoDf['FUND_MANAGER_STARTDATE'] = pd.DatetimeIndex(fundInfoDf['FUND_MANAGER_STARTDATE']).date
        fundInfoDf['date'] = LastReportDate
        fundInfoDf['PRT_STOCKTONAV'] = fundInfoDf['PRT_STOCKTONAV']/1e2
        fundInfoDf['PRT_BONDTONAV'] = fundInfoDf['PRT_BONDTONAV']/1e2
        fundInfoDf = fundInfoDf.apply(startDateComparision, axis = 1)
        df_output = df_output.append(fundInfoDf)
        LastReportDate = wind_getLastReportDate(LastReportDate - datetime.timedelta(days = 1))
    df_output.rename(columns={'SEC_NAME':'product_name', 'date':'report_date', 'NETASSET_TOTAL':'net_asset', 'UNIT_TOTAL':'total_shares',
                                  'HOLDER_INSTITUTION_TOTALHOLDING':'institution_shares_holding', 'PRT_STOCKTONAV':'stock_pct', 'PRT_BONDTONAV':'bond_pct',
                                  'FUND_MANAGER_STARTDATE':'pm_startdate'}, inplace= True)
    return df_output

# ------------------------------------------------
# 基金经理管理所有基金的静态信息，包括：股票比例范围，港股比例范围，管理费，托管费，基准，当前规模
# 返回一个表格Df，基金的基本信息。
# ------------------------------------------------
def anlsMF_allProductStaticInfoOfPM(
    fundManager,      # 基金经理
    fundCompany,      # 基金公司
    date              # 日期
):
    w.start()
    funddf = wind_getCurrentProductList(include_pm_info= True)
    funddf = funddf[(funddf['pm_name'] ==fundManager) & (funddf['company_short_name'] ==fundCompany)]
    fundList = funddf['product_id'].tolist()
    fundCodes = ','.join(fundList)
    fundDetails = w.wss(
        fundCodes,
        "name_official,fund_investtype,fund_manager_startdate,fund_fundmanager,fund_investmentproportion,fund_hkscinvestmentproportion,fund_managementfeeratio,"\
        "fund_custodianfeeratio,fund_benchmark,netasset_total",
        "order=1;investmentvariety=1;unit=1;tradeDate={0}".format(date.strftime('%Y%m%d')))
    fundDetailsDf = pd.DataFrame(pd.DataFrame(fundDetails.Data).values.T, columns= fundDetails.Fields)
    fundDetailsDf['product_id'] = fundList
    fundDetailsDf.rename(columns={'NAME_OFFICIAL':'product_name', 'FUND_INVESTTYPE':'product_type', 'FUND_MANAGER_STARTDATE':'manager_startdate',
                                  'FUND_FUNDMANAGER':'product_manager', 'FUND_INVESTMENTPROPORTION':'stock_proportion', 'FUND_HKSCINVESTMENTPROPORTION':'HKshare_limit',
                                  'FUND_MANAGEMENTFEERATIO':'management_feeratio', 'FUND_CUSTODIANFEERATIO':'custodian_feeratio',
                                  'FUND_BENCHMARK':'benchmark', 'NETASSET_TOTAL':'net_asset'}, inplace= True)
    columnsOrder = ['product_id','product_name', 'product_type', 'product_manager','manager_startdate',
                                  'stock_proportion', 'HKshare_limit',
                                  'management_feeratio', 'custodian_feeratio',
                                  'benchmark', 'net_asset']
    fundDetailsDf = fundDetailsDf[columnsOrder]
    fundDetailsDf['net_asset'] = fundDetailsDf['net_asset']/1e8
    fundDetailsDf['manager_startdate'] = pd.to_datetime(fundDetailsDf['manager_startdate']).dt.date
    return fundDetailsDf

# ------------------------------------------------
# 公募基金上半年和全年的日均规模
# ------------------------------------------------
def anlsMF_getMFAUMHistory_profit(
        product_ids                     # product_ids基金代码，应为list格式（因数据库存储问题，优先使用场内代码）
):
    assert (type(product_ids) == list), '基金代码输入格式需为list'
    df = wind.wind_getMFFinancialInfo(product_ids)
    df = df[['product_id','date','income', 'avg_income_return']]
    df['avg_nav'] = df['income']/df['avg_income_return']
    del df['income'], df['avg_income_return']
    return df

# ------------------------------------------------
# 公募基金上半年和全年的日均规模（托管费倒算法）
# ------------------------------------------------
def anlsMF_getMFAUMHistory(
        product_ids                     # product_ids基金代码，应为list格式（因数据库存储问题，优先使用场内代码）
):
    assert (type(product_ids) == list), '基金代码输入格式需为list'
    df = wind.wind_getMFFinancialInfo(product_ids)
    df = df[['product_id','date','trustee_exp', 'trustee_fee']]
    df['avg_nav'] = df['trustee_exp']/(df['trustee_fee']/100)
    del df['trustee_exp'], df['trustee_fee']
    return df

# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# 2. 业绩分析
# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------

# ------------------------------------------------
# 单只公募基金收益分析
# 返回该基金以及基准的，管理期间以及分年度的收益、回撤、夏普、胜率
# 管理期间收益为年化收益，其他指标是区间值，胜率为周胜率
# ------------------------------------------------
def anlsMF_retAnalysis(
        start_date,             # 起始日期，输入格式:datetime.date
        end_date,               # 结束日期，输入格式:datetime.date
        product_id,             # product_id基金代码，应为str格式（因数据库存储问题，优先使用场内代码）
        idx_code                # 基准指数，输入格式:String, eg: "000905.SH", "885001.WI"
):
    assert (type(start_date) == datetime.date), '日期输入格式需为datetime.date'
    assert (type(end_date) == datetime.date), '日期输入格式需为datetime.date'
    assert (type(product_id) == str), '基金代码输入格式需为str'
    assert (type(idx_code) == str), '基准指数代码输入格式需为str'
    assert start_date < end_date, '起始日需早于结束日'
    ret_product = wind.wind_getMFSingleStats([product_id], start_date, end_date)[product_id]
    ret_index = wind.wind_getIndexReturn(idx_code, start_date, end_date, freq='D')

    ret_product_year = Cal.basicCal_getCalendarPeriodReturn(ret_product)
    ret_index_year = Cal.basicCal_getCalendarPeriodReturn(ret_index)
    mdd_product_year = Cal.basicCal_getCalendarMaxDrawdown(ret_product)
    mdd_index_year = Cal.basicCal_getCalendarMaxDrawdown(ret_index)
    sharpe_product_year = Cal.basicCal_getCalendarSharpeRatio(ret_product)
    sharpe_index_year = Cal.basicCal_getCalendarSharpeRatio(ret_index)
    winningRate_product_year = Cal.basicCal_getCalendarwinningRate(ret_product)
    winningRate_index_year = Cal.basicCal_getCalendarwinningRate(ret_index)

    result_year = pd.concat([ret_product_year, ret_index_year, mdd_product_year, mdd_index_year,
                        sharpe_product_year, sharpe_index_year, winningRate_product_year, winningRate_index_year],axis=1)

    # 修改函数时注意column name的匹配
    result_year.columns = ['return_product', 'return_index', 'MaxDrawdown_product', 'MaxDrawdown_index',
                                  'Sharpe_product', 'Sharpe_index', 'WeeklywinningRate_product', 'WeeklywinningRate_index']

    result_period = pd.DataFrame(data=[[Cal.basicCal_getPeriodReturn(ret_product,'D'),
                                       Cal.basicCal_getPeriodReturn(ret_index,'D'),
                                       Cal.basicCal_getMaxDrawdown(ret_product),
                                       Cal.basicCal_getMaxDrawdown(ret_index),
                                       Cal.basicCal_getSharpeRatio(ret_product, 'D'),
                                       Cal.basicCal_getSharpeRatio(ret_index, 'D'),
                                       Cal.basicCal_winningRate(ret_product),
                                       Cal.basicCal_winningRate(ret_index)]],
                                 index=['period_performance'],
                                 columns=['return_product', 'return_index', 'MaxDrawdown_product', 'MaxDrawdown_index',
                                  'Sharpe_product', 'Sharpe_index', 'WeeklywinningRate_product', 'WeeklywinningRate_index'])
    result = result_period.append(result_year)
    return result

# ------------------------------------------------
# 计算公募基金之间的相关性
# ------------------------------------------------
def anlsMF_productCorrelation(
        start_date,             # 起始日期，输入格式:datetime.date
        end_date,               # 结束日期，输入格式:datetime.date
        product_ids              # product_ids基金代码，应为list格式（因数据库存储问题，优先使用场内代码）
):
    assert (type(start_date) == datetime.date), '日期输入格式需为datetime.date'
    assert (type(end_date) == datetime.date), '日期输入格式需为datetime.date'
    assert start_date < end_date, '起始日需早于结束日'
    ret = wind.wind_getMFSingleStats(product_ids, start_date, end_date)
    corr = Cal.basicCal_Correlation(ret)
    return corr

# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# 3. 持仓分析
# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------

# -------------------------------------------------------------------------------------
# 获取单只FOF公募的基金持仓类别汇总
# 返回的持仓权重比为实际值，未扩为100%，求和结果是基金标的的总持仓权重
# -------------------------------------------------------------------------------------
def anlsMF_getWindMFOFFundHoldingsSector(
        date,           # best effort, 寻找该日期前最新的持仓数据
        product_id,     # 公募基金ID
        freq='Q',       # freq为频率，'Q'为季报，'H'为半年和年报
        level='type_name_lv1'       # 汇总统计level，与wind标签体系一致
):
    assert level in ('allocation_type', 'type_name_lv1', 'type_name_lv2'), "公募FOF持仓汇总统计的维度仅限于type_name_lv1/2和allocation_type"
    level_col_map = {
        'groupby': {
            'allocation_type': ['allocation_type'],
            'type_name_lv1': ['type_name_lv1'],
            'type_name_lv2': ['type_name_lv1', 'type_name_lv2'],
        },
        'sort': {
            'allocation_type': ['asset_value_to_nav'],
            'type_name_lv1': ['holding_fund_value_to_nav'],
            'type_name_lv2': ['type_name_lv1', 'holding_fund_value_to_nav'],
        },
        'sum': {
            'allocation_type': ['asset_value', 'asset_value_to_nav'],
            'type_name_lv1': ['holding_fund_value', 'holding_fund_value_to_nav'],
            'type_name_lv2': ['holding_fund_value', 'holding_fund_value_to_nav'],
        },
    }
    portfolio = wind_getMFOFCurrentFundHoldings(date, product_id, freq)
    # 若考察持仓基金继续向下穿透的大类资产分布（wind标准）
    if level == 'allocation_type':
        portfolio_allocation = wind_getMFAssetAllocation(portfolio['holding_fund_id'].tolist(), only_a_share=False)
        # 对于持有的每个基金，都取其最新数据进行计算，best effort
        portfolio_allocation = portfolio_allocation.groupby(['product_id'], as_index=False).apply(lambda x: x[x['date'] == x['date'].max()])
        # 整理allocation数据，只取需要的列（股票、债券、基金、现金、其他（含商品）的比重），并且把权重为nan的fill0
        allo_cols_map = {
            'product_id': 'holding_fund_id',
            'product_stk_value_to_nav': '股票',
            'product_bond_value_to_nav': '债券',
            'product_fund_value_to_nav': '基金',
            'cash_to_nav': '现金',
            'product_other_value_to_nav': '其他（商品等）'
        }
        portfolio_allocation = portfolio_allocation[list(allo_cols_map.keys())].rename(columns=allo_cols_map)
        # 大类资产配置权重变为长表
        portfolio_allocation = portfolio_allocation.melt(id_vars='holding_fund_id', var_name='allocation_type', value_name='asset_value_to_nav')
        portfolio = pd.merge(portfolio, portfolio_allocation, on=['holding_fund_id'], how='left')
        # 持仓规模先计算（规模数据时产品一级，直接相乘），再计算相对FOF持仓的权重
        portfolio['asset_value'] = portfolio['holding_fund_value'] * portfolio['asset_value_to_nav']
        portfolio['asset_value_to_nav'] = portfolio['holding_fund_value_to_nav'] * portfolio['asset_value_to_nav']

    agg_data = portfolio.groupby(['product_name'] + level_col_map['groupby'][level], as_index=False)[level_col_map['sum'][level]].sum()
    agg_data = agg_data.sort_values(by=level_col_map['sort'][level], ascending=False)
    return agg_data

# -------------------------------------------------------------------------------------
# 单只公募基金历史股票持仓
# 统计历史一段时间内，报告中股票的出现次数和权重合计，以及这些股票最早和最后出现的季报时间，数据粒度为股票
# -------------------------------------------------------------------------------------
def anlsMF_getMFHistoryStock(
        start_date,             # 起始日期，输入格式:datetime.date
        end_date,               # 结束日期，输入格式:datetime.date
        product_id,             # product_id基金代码，应为list格式（因数据库存储问题，优先使用场内代码）
        hidden_holdings = False,# 是否包括上市公司公告里面的隐藏持仓
        freq = 'Q',              # freq为频率，'Q'为季报，'H'为半年和年报
        Top10 = False            # Top10为是否仅取季报前十大持仓
):
    assert (type(start_date) == datetime.date), '日期输入格式需为datetime.date'
    assert (type(end_date) == datetime.date), '日期输入格式需为datetime.date'
    assert (type(product_id) == list), '基金代码输入格式需为list'
    assert start_date < end_date, '起始日需早于结束日'
    portfolio = anlsMF_getMFStockHoldings(product_id, freq, Top10, hidden_holdings)
    portfolio = portfolio.loc[(portfolio['date'] > start_date) & (portfolio['date'] < end_date)].reset_index(drop=True)
    portfolio.sort_values(['date'], ascending=True, inplace=True)
    stock = portfolio.groupby(['stock_id', 'stock_name'])['stk_value_to_nav'].agg(['sum','count']).reset_index()
    stock.sort_values('sum', ascending=False, inplace=True)
    stock_time = portfolio.groupby(['stock_id', 'stock_name'])['date'].agg(['first', 'last']).reset_index()
    stock = pd.merge(stock, stock_time, on=['stock_id', 'stock_name'], how='left')
    stock.rename(columns={'sum':'stock_sum_weight', 'count':'stock_count'}, inplace=True)
    return stock

# -----------------------------------------------------------------------------------------
# 单只公募基金历史股票持仓行业分析 (现在输出各行业占股票资产比）
# 统计历史一段时间内，报告中各行业的出现次数和权重合计，以及这些行业最早和最后出现的季报时间，数据粒度为行业
# -----------------------------------------------------------------------------------------
def anlsMF_getMFHistoryIndustry(
        start_date,                     # 起始日期，输入格式:datetime.date
        end_date,                       # 结束日期，输入格式:datetime.date
        product_id,                     # product_id基金代码，应为list格式（因数据库存储问题，优先使用场内代码）
        company,                        # 分类标准，输入格式:str，'SW' or 'CITICS'
        level,                          # 分类级别，输入格式:int
        hidden_holdings = False,        # 是否包括上市公司公告里面的隐藏持仓
        freq = 'Q',                     # freq为频率，'Q'为季报，'H'为半年和年报
        Top10 = False,                  # Top10为是否仅取季报前十大持仓
        IndustrytoStkValue = False,     # False:行业占基金净值比；True:行业占股票市值比
        OnlyEquity = False              # 非权益基金（start_date到end_date期间基金平均权益仓位小于60%）是否返回AssertionError
):
    assert (type(start_date) == datetime.date), '日期输入格式需为datetime.date'
    assert (type(end_date) == datetime.date), '日期输入格式需为datetime.date'
    assert (type(product_id) == list), '基金代码输入格式需为list'
    assert (len(product_id) == 1), '目前仅支持单只基金分析'
    assert start_date <= end_date, '起始日需早于结束日'
    portfolio = anlsMF_getMFStockHoldings(product_id, freq, Top10, hidden_holdings)
    assert portfolio.empty == False, '成立时间不足'

    portfolio = portfolio.loc[(portfolio['date'] >= start_date) & (portfolio['date'] <= end_date)].reset_index(drop=True)
    # 行业填充
    portfolio = _getIndustry(portfolio, company, level)
    if OnlyEquity:
        monthdelta = (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month)
        period_num = 1 + monthdelta / 6
        result_industry = portfolio.groupby(['industry'])['stk_value_to_nav'].agg(['sum', 'count']).reset_index()
        assert result_industry['sum'].sum() / period_num > 0.6, "非权益基金"
    if IndustrytoStkValue:
        result_industry = portfolio.groupby(['industry'])['stk_value_to_allstk'].agg(['sum', 'count']).reset_index()
    else:
        result_industry = portfolio.groupby(['industry'])['stk_value_to_nav'].agg(['sum', 'count']).reset_index()
    portfolio.sort_values(['industry', 'date'], ascending=True, inplace=True)
    result_industry.sort_values('sum', ascending=False, inplace=True)
    industry_time = portfolio.groupby(['industry'])['date'].agg(['first', 'last']).reset_index()
    result_industry = pd.merge(result_industry, industry_time, on=['industry'], how='left')
    result_industry.rename(columns={'sum': 'industry_sum_weight', 'count': 'industry_count'}, inplace=True)
    return result_industry

# -------------------------------------------------------------------------------
# 多只公募基金的行业占比, 可穿透至主观多头以及二级债基的权益部分
# 默认取基金最新一期报告的行业占比，默认使用原始权益权重，即将比例之和张成100%后乘以权益配置比例
# 目前默认不给港股统一置为”港股“行业
# C份额、ETF、场内交易的LOF均被纳入计算
# start&end_date不需要卡着报告日期进行设置，函数自动选取期间内最新一期报告结果作计算
# 返回 dataframe: product_id industry industry_weight industry_level
# -------------------------------------------------------------------------------
def anlsMF_getListedMFIndustryWeightDetails(
        report_date,                    # 参考报告的截至日期，输入格式:datetime.date
        product_id,                     # product_id基金代码，应为list格式（因数据库存储问题，优先使用场内代码）
        company,                        # 分类标准，输入格式:str，'SW' or 'CITICS'
        level,                          # 分类级别，输入格式:int
        mask_h_shares=True,             # 是否将港股的行业全部置为“港股”，默认为是
        expand_weight=False,            # 是否将单只基金的行业比例之和张成100%，默认为否，即行业求和结果为权益配置比例；对基金单独分析时可张成100%，对FOF组合分析时此步骤为否
):
    assert (type(report_date) == datetime.date), '日期输入格式需为datetime.date'
    assert (type(product_id) == list), '基金代码输入格式需为list'

    start_date = report_date - datetime.timedelta(180)  # 先选取近半年的报告内容，再取最近一期
    portfolio = anlsMF_getMFStockHoldings(product_id, only_a_share=False, passive_index_fund=True)
    port_asset_alloc = wind.wind_getMFAssetAllocation(product_id, only_a_share=False).fillna(0)[['product_id', 'product_full_name', 'date', 'net_asset', 'product_stk_value', 'product_stk_value_to_nav']]

    # 对于每一个持仓基金，取最新一期报告的持仓结果以及大类配置信息，尽量取最新信息，然后进行inner_join
    # 持仓、大类配置都取最新是为了避免二级债基可能最新一期无股票持仓，不能直接判定为缺数
    portfolio = portfolio.loc[(portfolio['date'] >= start_date) & (portfolio['date'] <= report_date)].reset_index(drop=True)
    portfolio['product_latest_report_date'] = portfolio.groupby('product_id')['date'].transform('max')
    portfolio = portfolio[portfolio['date'] == portfolio['product_latest_report_date']]
    if portfolio.empty:  # 由于目前使用场景是将组合持仓的全部product_id输入，可能不会包括多头公募，故目前portfolio为空时不报错，返回空df
        return pd.DataFrame()
    port_asset_alloc = port_asset_alloc.loc[(port_asset_alloc['date'] >= start_date) & (port_asset_alloc['date'] <= report_date)].reset_index(drop=True)
    port_asset_alloc['product_latest_report_date'] = port_asset_alloc.groupby('product_id')['date'].transform('max')
    port_asset_alloc = port_asset_alloc[port_asset_alloc['date'] == port_asset_alloc['product_latest_report_date']]
    # 持仓与资产配置表整合
    portfolio = pd.merge(portfolio, port_asset_alloc, on=['product_id', 'date'])  # product_stk_value_to_nav 这一项已包含A股和港股通

    # 填充行业标签
    portfolio = _getIndustry(portfolio, company, level, mask_h_shares)
    industry_result = portfolio.groupby(by=['product_id', 'industry']).agg({'stk_value_to_nav': 'sum'}).rename(columns={'stk_value_to_nav': 'industry_weight'})
    # 先将一支基金内的行业权重和张为100%
    industry_result = industry_result.groupby(level=0).apply(lambda x: x/x.sum()).reset_index()
    if not expand_weight:  # 如果选择不张为100%，则用上面结果再乘以权益部分的比例，这样操作是为了将季报前十大数据填充100%后再按照权益比例重置，尽量准确地刻画行业分布
        industry_result = pd.merge(industry_result, portfolio[['product_id', 'product_stk_value_to_nav']].drop_duplicates(), on='product_id', how='left')
        industry_result['industry_weight'] = industry_result['industry_weight'] * industry_result['product_stk_value_to_nav']
        del industry_result['product_stk_value_to_nav']
    industry_result.sort_values(['product_id', 'industry'], ascending=True, inplace=True)
    industry_result['industry_level'] = company + '_' + str(level)
    industry_result['report_date'] = portfolio['date'].max()
    industry_result['earliest_report_date'] = portfolio['date'].min()  # 若处于公募报告正在披露的阶段，会有report_date不统一的情况，该列用于存储所选基金中报告期最早时间，用于判断
    return industry_result

# ------------------------------------------------
# 单只公募基金历史股票持仓板块分析
# 历史各板块净值占比平均值
# ------------------------------------------------
def anlsMF_getMFHistorySector(
        product_id,                     # product_id基金代码，应为list格式（因数据库存储问题，优先使用场内代码）
        start_date,                     # 起始日期，输入格式:datetime.date
        end_date,                       # 结束日期，输入格式:datetime.date
        company,                        # 分类标准，输入格式:str，'SW' or 'CITICS'
        level,                          # 分类级别，输入格式:int
        hidden_holdings = False,        # 是否包括上市公司公告里面的隐藏持仓
        freq = 'Q',                     # freq为频率，'Q'为季报，'H'为半年和年报
        Top10 = False,                  # Top10为是否仅取季报前十大持仓
        IndustrytoStkValue = False,     # False:行业占基金净值比；True:行业占股票市值比
        OnlyEquity = False              # 非权益基金（start_date到end_date期间基金平均权益仓位小于60%）是否返回AssertionError
):
    assert (type(start_date) == datetime.date), '日期输入格式需为datetime.date'
    assert (type(end_date) == datetime.date), '日期输入格式需为datetime.date'
    assert (type(product_id) == list), '基金代码输入格式需为list'
    assert start_date <= end_date, '起始日需早于结束日'

    start_date = wind.wind_getNextReportDate(start_date, Freq='H') # Next
    end_date = wind.wind_getLastReportDate(end_date, Freq='H') # Last
    monthdelta = (end_date.year - start_date.year)*12 + (end_date.month - start_date.month)
    period_num = 1 + monthdelta/6
    df = anlsMF_getMFHistoryIndustry(start_date, end_date, product_id, company, level, hidden_holdings, freq, Top10, IndustrytoStkValue, OnlyEquity)
    df['ind_avg_weight'] = df['industry_sum_weight']/ period_num
    df['sector'] = df['industry'].apply(lambda x: const.const.INDUSTRYTOSECTOR_CITICSFOF[x])
    returndf = df.groupby('sector').sum().sort_values('ind_avg_weight', ascending=False)[['ind_avg_weight']]
    returndf.rename(columns = {"ind_avg_weight": "sector_avg_weight"}, inplace = True)
    return returndf

# ------------------------------------------------
# 单只公募基金各报告期各行业第一大重仓股
# ------------------------------------------------
def anlsMF_getMFFirstStockofEachIndustry(
        start_date,                     # 起始日期，输入格式:datetime.date
        end_date,                       # 结束日期，输入格式:datetime.date
        product_id,                     # product_id基金代码，应为list格式（因数据库存储问题，优先使用场内代码）
        company,                        # 分类标准，输入格式:str，'SW' or 'CITICS'
        level,                          # 分类级别，输入格式:int
        hidden_holdings = False,            # 是否包括上市公司公告里面的隐藏持仓
        freq = 'Q',                     # freq为频率，'Q'为季报，'H'为半年和年报
        Top10 = False                   # Top10为是否仅取季报前十大持仓
):
    assert (type(start_date) == datetime.date), '日期输入格式需为datetime.date'
    assert (type(end_date) == datetime.date), '日期输入格式需为datetime.date'
    assert (type(product_id) == list), '基金代码输入格式需为list'
    assert (len(product_id) == 1), '目前仅支持单只基金分析'
    assert start_date <= end_date, '起始日需早于结束日'
    portfolio = anlsMF_getMFStockHoldings(product_id, freq, Top10, hidden_holdings)
    assert portfolio.empty == False, '成立时间不足'

    portfolio = portfolio.loc[(portfolio['date'] >= start_date) & (portfolio['date'] <= end_date)].reset_index(drop=True)
    # 行业填充
    portfolio = _getIndustry(portfolio, company, level)
    first_stock = portfolio.groupby(['date', 'industry'])['stock_name'].first().reset_index()
    first_stock = pd.pivot_table(first_stock, columns='industry', index='date', values='stock_name', aggfunc='first')

    return first_stock

# ------------------------------------------------
# 单只公募基金各报告期前三大行业
# ------------------------------------------------
def anlsMF_getMFTop3Industry(
        start_date,                     # 起始日期，输入格式:datetime.date
        end_date,                       # 结束日期，输入格式:datetime.date
        product_id,                     # product_id基金代码，应为list格式（因数据库存储问题，优先使用场内代码）
        company,                        # 分类标准，输入格式:str，'SW' or 'CITICS'
        level,                          # 分类级别，输入格式:int
        hidden_holdings = False,            # 是否包括上市公司公告里面的隐藏持仓
        freq = 'Q',                     # freq为频率，'Q'为季报，'H'为半年和年报
        Top10 = False,                  # Top10为是否仅取季报前十大持仓
        IndustrytoStkValue = False      # False:行业占基金净值比；True:行业占股票市值比
):
    assert (type(start_date) == datetime.date), '日期输入格式需为datetime.date'
    assert (type(end_date) == datetime.date), '日期输入格式需为datetime.date'
    assert (type(product_id) == list), '基金代码输入格式需为list'
    assert (len(product_id) == 1), '目前仅支持单只基金分析'
    assert start_date <= end_date, '起始日需早于结束日'
    portfolio = anlsMF_getMFStockHoldings(product_id, freq, Top10, hidden_holdings)
    assert portfolio.empty == False, '成立时间不足'

    portfolio = portfolio.loc[(portfolio['date'] >= start_date) & (portfolio['date'] <= end_date)].reset_index(drop=True)
    # 行业填充
    portfolio = _getIndustry(portfolio, company, level)
    if IndustrytoStkValue:
        result_industry = portfolio.groupby(['date', 'industry'])['stk_value_to_allstk'].agg(['sum', 'count']).reset_index()
    else:
        result_industry = portfolio.groupby(['date', 'industry'])['stk_value_to_nav'].agg(['sum', 'count']).reset_index()
    result_industry = result_industry.sort_values(by=['date','sum'], ascending=False).reset_index(drop=True)
    Top3_industry = result_industry.groupby('date').apply(lambda x: x.iloc[:3]).reset_index(drop=True)
    Top3_industry['rank'] = Top3_industry.groupby('date')['sum'].rank(ascending=False)
    result_top3_industry = pd.pivot_table(Top3_industry, columns='rank', index='date', values='industry', aggfunc='first')
    result_top3_industry.columns = ['第一大行业', '第二大行业', '第三大行业']
    result_top3_sum = pd.pivot_table(Top3_industry, columns='rank', index='date', values='sum',aggfunc='first')
    result_top3_sum.columns = ['第一大行业比例', '第二大行业比例', '第三大行业比例']
    result_top3 = pd.merge(result_top3_industry, result_top3_sum, on='date')

    return result_top3

# ------------------------------------------------
# 单只公募基金各报告期各行业比例
# ------------------------------------------------
def anlsMF_getMFIndustryDistribution(
        start_date,                     # 起始日期，输入格式:datetime.date
        end_date,                       # 结束日期，输入格式:datetime.date
        product_id,                     # product_id基金代码，应为list格式（因数据库存储问题，优先使用场内代码）
        company,                        # 分类标准，输入格式:str，'SW' or 'CITICS'
        level,                          # 分类级别，输入格式:int
        hidden_holdings = False,            # 是否包括上市公司公告里面的隐藏持仓
        freq = 'Q',                     # freq为频率，'Q'为季报，'H'为半年和年报
        Top10 = False,                  # Top10为是否仅取季报前十大持仓
        IndustrytoStkValue = False      # False:行业占基金净值比；True:行业占股票市值比
):
    assert (type(start_date) == datetime.date), '日期输入格式需为datetime.date'
    assert (type(end_date) == datetime.date), '日期输入格式需为datetime.date'
    assert (type(product_id) == list), '基金代码输入格式需为list'
    assert (len(product_id) == 1), '目前仅支持单只基金分析'
    assert start_date <= end_date, '起始日需早于结束日'
    portfolio = anlsMF_getMFStockHoldings(product_id, freq, Top10, hidden_holdings)
    assert portfolio.empty == False, '成立时间不足'

    portfolio = portfolio.loc[(portfolio['date'] >= start_date) & (portfolio['date'] <= end_date)].reset_index(drop=True)
    # 行业填充
    portfolio = _getIndustry(portfolio, company, level)
    if IndustrytoStkValue:
        result_industry = portfolio.groupby(['date', 'industry'])['stk_value_to_allstk'].agg(['sum', 'count']).reset_index()
    else:
        result_industry = portfolio.groupby(['date', 'industry'])['stk_value_to_nav'].agg(['sum', 'count']).reset_index()
    result_industry = result_industry.sort_values(by=['date','sum'], ascending=False).reset_index(drop=True)
    result_industry_sum = pd.pivot_table(result_industry, columns='industry', index='date', values='sum', aggfunc='first')
    result_industry_sum = result_industry_sum.append(pd.DataFrame(result_industry_sum.fillna(0).mean(), columns=['平均']).T)

    return result_industry_sum

# ------------------------------------------------
# 单只公募基金各报告期各行业的股票个数
# ------------------------------------------------
def anlsMF_getMFStockNumofEachIndustry(
        start_date,                     # 起始日期，输入格式:datetime.date
        end_date,                       # 结束日期，输入格式:datetime.date
        product_id,                     # product_id基金代码，应为list格式（因数据库存储问题，优先使用场内代码）
        company,                        # 分类标准，输入格式:str，'SW' or 'CITICS'
        level,                          # 分类级别，输入格式:int
        hidden_holdings = False,            # 是否包括上市公司公告里面的隐藏持仓
        freq = 'Q',                     # freq为频率，'Q'为季报，'H'为半年和年报
        Top10 = False,                  # Top10为是否仅取季报前十大持仓
        IndustrytoStkValue = False      # False:行业占基金净值比；True:行业占股票市值比
):
    assert (type(start_date) == datetime.date), '日期输入格式需为datetime.date'
    assert (type(end_date) == datetime.date), '日期输入格式需为datetime.date'
    assert (type(product_id) == list), '基金代码输入格式需为list'
    assert (len(product_id) == 1), '目前仅支持单只基金分析'
    assert start_date <= end_date, '起始日需早于结束日'
    portfolio = anlsMF_getMFStockHoldings(product_id, freq, Top10, hidden_holdings)
    assert portfolio.empty == False, '成立时间不足'

    portfolio = portfolio.loc[(portfolio['date'] >= start_date) & (portfolio['date'] <= end_date)].reset_index(drop=True)
    # 行业填充
    portfolio = _getIndustry(portfolio, company, level)
    if IndustrytoStkValue:
        result_industry = portfolio.groupby(['date', 'industry'])['stk_value_to_allstk'].agg(['sum', 'count']).reset_index()
    else:
        result_industry = portfolio.groupby(['date', 'industry'])['stk_value_to_nav'].agg(['sum', 'count']).reset_index()
    result_industry = result_industry.sort_values(by=['date','sum'], ascending=False).reset_index(drop=True)
    result_industry_count = pd.pivot_table(result_industry, columns='industry', index='date', values='count',aggfunc='first')
    result_industry_count = result_industry_count.append(pd.DataFrame(result_industry_count.fillna(0).mean(), columns=['平均']).T)

    return result_industry_count

# ------------------------------------------------
# 单只公募基金各报告期持股特点（PE/PB/ROE/MV/GROWTH等）
# ------------------------------------------------
def anlsMF_getMFHoldingsFinData(
        start_date,                     # 起始日期，输入格式:datetime.date
        end_date,                       # 结束日期，输入格式:datetime.date
        product_id,                     # product_id基金代码，应为str格式（因数据库存储问题，优先使用场内代码）
        freq = 'Q',                     # freq为频率，'Q'为季报，'H'为半年和年报
        Top10 = False,                  # Top10为是否仅取季报前十大持仓
):
    assert (type(start_date) == datetime.date), '日期输入格式需为datetime.date'
    assert (type(end_date) == datetime.date), '日期输入格式需为datetime.date'
    assert (type(product_id) == str), '基金代码输入格式需为str'
    assert (len(product_id) == 9), '目前仅支持单只基金分析'
    assert start_date <= end_date, '起始日需早于结束日'
    portfolio = wind.wind_getMFStockHoldings([product_id], freq, Top10)

    assert portfolio.empty == False, '成立时间不足'
    portfolio = portfolio.loc[(portfolio['date'] >= start_date) & (portfolio['date'] <= end_date)].reset_index(drop=True)

    df_stock = wind.wind_getAShareFinancialInfo(stock_ids=portfolio['stock_id'].unique().tolist())
    del df_stock['stock_name']
    portfolio = pd.merge(portfolio, df_stock, how='left', on=['date', 'stock_id'])
    portfolio['pe_ttm'].fillna(0, inplace=True) # 负EPS的PE为nan
    portfolio = portfolio.dropna().reset_index(drop=True)

    eps_quarter = portfolio.groupby(['date']).apply(lambda x: np.average(x['eps_quarter'], weights=x['stk_value'])).to_frame()
    net_profit_yoy = portfolio.groupby(['date']).apply(lambda x: np.average(x['net_profit_yoy'], weights=x['stk_value'])).to_frame()
    total_mv = portfolio.groupby(['date']).apply(lambda x: np.average(x['total_mv'], weights=x['stk_value'])).to_frame()
    floating_mv = portfolio.groupby(['date']).apply(lambda x: np.average(x['floating_mv'], weights=x['stk_value'])).to_frame()
    pe_ttm = portfolio.groupby(['date']).apply(lambda x: np.average(x['pe_ttm'], weights=x['stk_value'])).to_frame()
    pb = portfolio.groupby(['date']).apply(lambda x: np.average(x['pb'], weights=x['stk_value'])).to_frame()
    result = pd.concat([eps_quarter, net_profit_yoy, total_mv, floating_mv, pe_ttm, pb],axis=1)
    # 新加指标时注意对应添加列名
    result.columns = ['eps_quarter', 'net_profit_yoy', 'total_mv', 'floating_mv', 'pe_ttm', 'pb']
    result.reset_index(inplace=True)
    result['date'] = pd.to_datetime(result['date']).dt.date
    result = result.sort_values('date').reset_index(drop=True)
    return result

# ------------------------------------------------
# 公募基金隐藏在上市公司股东的持仓
# 主要用于补充季报的持仓，也有可能与基金季报公布的重复
# ------------------------------------------------
def anlsMF_getMFHiddenHoldings(
        product_id                     # product_id基金代码，应为str格式（因数据库存储问题，优先使用场内代码）
):
    assert (type(product_id) == str), '基金代码输入格式需为str'
    AShare_holder = anlsStk_getAShareHolders()
    df = wind.wind_getCurrentProductList() # 获得基金全称，！目前只考虑最新名称，未考虑曾用名，比如易方达中小盘，CFundPreviousName仅有简称，不能在上市公司股东里面做检索
    full_name = df.loc[df['product_id'] == product_id]['product_full_name'].values[0]
    result = AShare_holder.loc[AShare_holder['holder_name'].str.contains(full_name)].reset_index(drop=True)
    result['product_id'] = product_id
    return result

# ------------------------------------------------
# 公募基金股票持仓，可以选择是否纳入A股上市公司公告中的隐藏持仓
# 隐藏持仓仅适用于单只基金分析
# ------------------------------------------------
def anlsMF_getMFStockHoldings(
        product_id=None,         # product_id基金代码，应为list格式（因数据库存储问题，优先使用场内代码），为None时，相当于获取全部持仓
        freq = 'Q',              # freq为频率，'Q'为季报，'H'为半年和年报
        Top10 = False,           # Top10为是否仅取季报前十大持
        hiddenHoldings=False,    # 是否加入上市公司前十大流通股东和股东里面隐藏的基金持仓
        start_date=None,         # 起始日期
        end_date=None,           # 结束日期
        only_a_share=True,       # 是否只取A份额，默认为是
        passive_index_fund=False,  # 是否包含被动指数基金，默认为否
):
    portfolio = wind.wind_getMFStockHoldings(product_id, freq, Top10, start_date, end_date, only_a_share, passive_index_fund)
    if hiddenHoldings == True: # 如果不考虑隐藏持仓，无需其他操作
        if freq == 'H': # 只看中报和年报就不需要隐藏持仓了
            hiddenHoldings = pd.DataFrame()
        else:
            hiddenHoldings = anlsMF_getMFHiddenHoldings(product_id[0])
            del hiddenHoldings['holder_name'], hiddenHoldings['trade_date']
            hiddenHoldings['stock_market'] = 'A'

        result = portfolio.append(hiddenHoldings).reset_index(drop=True)
        result['company_short_name'].fillna(method='ffill', inplace=True)
        result = result.sort_values(by=['date', 'stk_value'], ascending=False).reset_index(drop=True)
        result = result.drop_duplicates(['date','stock_id']).reset_index(drop=True) # 去重
        nav = portfolio.groupby('date').apply(lambda x: x['stk_value'].max() / x['stk_value_to_nav'].max()).to_frame().reset_index().rename(columns={0:'nav'})
        allstk = portfolio.groupby('date').apply(lambda x: x['stk_value'].max() / x['stk_value_to_allstk'].max()).to_frame().reset_index().rename(columns={0: 'allstk'})
        result = pd.merge(result, nav, how='left', on='date')
        result = pd.merge(result, allstk, how='left', on='date')
        result['stk_value_to_nav'] = result['stk_value'] / result['nav']
        result['stk_value_to_allstk'] = result['stk_value'] / result['allstk']
        del result['nav'], result['allstk']
    else:
        result = portfolio.copy()
    return result

# ---------------------------------------------------------
# 获取公募FOF多头行业穿透
# ---------------------------------------------------------
def anlsMF_getWindMFOFIndustryLookThrough(
    date,                   # 持仓数据日期(筛选最近一期报告的数据)，输入格式:datetime.date
    product_id,
    company='SW',           # 行业分类标准，输入格式:str，'SW' or 'CITICS'
    level=1,                # 行业分类级别，输入格式:int
    top_num=10,             # 前N大行业
    mask_h_shares=True,     # 是否将港股的行业全部置为“港股”，默认为是
):
    assert company in ['SW', 'CITICS'], "行业分类目前支持申万和中信"
    assert level in [1, 2, 3], "行业分类级别支持1、2、3级"

    # 持仓信息
    holding_result = wind_getMFOFCurrentFundHoldings(date, product_id)

    # 按持仓类型获取行业比重数据
    # 公募 主观多头 公募不筛类型直接输入 有数字即返回 包含了主观权益 指数增强 二级债基
    # 对于未录入的产品 holding_result['hf_mf_type'] == '公募' 也无法筛出 故直接将所有id输入 返回时只会包含有权益持仓的公募
    mf_list = holding_result['holding_fund_id'].to_list()
    mf_industry = anlsMF_getListedMFIndustryWeightDetails(date, mf_list, company, level, mask_h_shares=mask_h_shares) if mf_list else pd.DataFrame()
    if mf_industry.empty:
        return mf_industry
    combine_result = pd.merge(mf_industry, holding_result[['holding_fund_id', 'holding_fund_name', 'holding_fund_value_to_nav',
                                'type_name_lv1', 'type_name_lv2']], left_on='product_id', right_on='holding_fund_id')
    combine_result['industry_weight_in_port'] = combine_result['industry_weight'] * combine_result['holding_fund_value_to_nav']

    # 计算行业
    result = combine_result.groupby(by='industry', as_index=False)['industry_weight_in_port'].sum()
    result['equity_total_weight'] = result['industry_weight_in_port'].sum()
    result['industry_weight'] = result['industry_weight_in_port'] / result['equity_total_weight']
    # 报告期信息
    # 如果公募正处于报告披露的过程中，存在数据日期不同的情况，则同时展示所用的两个日期以提示用户
    earliest_report_date_list = combine_result['earliest_report_date']
    earliest_report_date = earliest_report_date_list[~earliest_report_date_list.isnull()].max()
    report_date = combine_result['report_date'].min() if combine_result['report_date'].min() == earliest_report_date else str([str(earliest_report_date), str(combine_result['report_date'].min())])
    result[['product_id', 'product_name', 'date', 'holding_fund_value', 'industry_level', 'report_date']] = \
        [product_id, holding_result['product_name'].iloc[0], holding_result['date'].iloc[0], holding_result['holding_fund_value'].sum(), company + '_' + str(level), report_date]
    result['industry_NAV'] = result['holding_fund_value'] * result['industry_weight_in_port']
    result = result.sort_values(by='industry_weight', ascending=False).reset_index(drop=True)

    # 拆分top_num并将bottom部分求和作为其他项
    top_result = result.iloc[:top_num, :]
    bottom_result = result.iloc[top_num:, :]
    if not bottom_result.empty:
        top_result = top_result.append({'industry': '其他', 'industry_weight_in_port': bottom_result['industry_weight_in_port'].sum(),
                                        'industry_weight': bottom_result['industry_weight'].sum(), 'industry_NAV': bottom_result['industry_NAV'].sum()},ignore_index=True)
    top_result = top_result.append({'industry': '合计', 'industry_weight_in_port': top_result['industry_weight_in_port'].sum(),
                                    'industry_weight': top_result['industry_weight'].sum(), 'industry_NAV': top_result['industry_NAV'].sum()}, ignore_index=True)
    col_to_fillna = ['equity_total_weight', 'product_id', 'product_name', 'date', 'holding_fund_value', 'industry_level', 'report_date']  # 组合级别的信息通过fillna补全（该级别信息对于全表来说都是一致的）
    top_result[col_to_fillna] = top_result[col_to_fillna].fillna(method='ffill')  # 新加行的其他基础信息依照已有数据fill
    return top_result

# ------------------------------------------------
# 公募基金择时选股收益拆分 Treynor-Mazuy模型
# ------------------------------------------------
def anlsMF_TMModel(
        start_date,             # 起始日期，输入格式:datetime.date
        end_date,               # 结束日期，输入格式:datetime.date
        product_id,             # product_id基金代码，应为str格式（因数据库存储问题，优先使用场内代码）
        position = 0.85,        # 股票仓位
        window = 126            # 回看周期，天数
):
    assert (type(start_date) == datetime.date), '日期输入格式需为datetime.date'
    assert (type(end_date) == datetime.date), '日期输入格式需为datetime.date'
    assert (type(product_id) == str), '基金代码输入格式需为str'
    assert start_date < end_date, '起始日需早于结束日'
    rf = wind.wind_getBondCurve(start_date, end_date) # 十年国债收益率，视作无风险收益率
    rf.set_index('date', inplace=True)

    ret_fund = wind.wind_getMFStats([product_id], start_date, end_date, ['f_avgreturn_day']) # 基金收益率
    ret_fund = ret_fund[['date', 'f_avgreturn_day']].set_index('date')

    ret_bond = wind.wind_getIndexReturn('CBA00101.CS', start_date, end_date, 'D') # 中债-新综合财富(总值)指数
    ret_stock = wind.wind_getIndexReturn('881001.WI', start_date, end_date, 'D') # 万得全A
    ret_growth = wind.wind_getIndexReturn('399370.SZ', start_date, end_date, 'D') # 国证成长
    ret_value = wind.wind_getIndexReturn('399371.SZ', start_date, end_date, 'D') # 国证价值
    ret_bigcap = wind.wind_getIndexReturn('399314.SZ', start_date, end_date, 'D') # 巨潮大盘
    ret_smallcap = wind.wind_getIndexReturn('399316.SZ', start_date, end_date, 'D') # 巨潮小盘

    ret = pd.concat([ret_fund, ret_bond, ret_stock, ret_growth, ret_value, ret_bigcap, ret_smallcap, rf], axis=1)
    ret.dropna(inplace=True)
    # 因子构建
    ret['SMB'] = ret['399316.SZ'] - ret['399314.SZ']
    ret['HML'] = ret['399371.SZ'] - ret['399370.SZ']
    ret['rm'] = ret['881001.WI'] * position + ret['CBA00101.CS'] * (1 - position)
    ret['rf'] = (1 + ret['yield']) ** (1 / const.const.ANNUAL_SCALE) - 1
    ret['rm-rf'] = ret['rm'] - ret['rf']
    ret['rm_2'] = (ret['rm'] - ret['rf']) ** 2
    ret['rm_D'] = (ret['rm'] - ret['rf']) * ((ret['rm'] - ret['rf']) > 0)
    ret['rm_D1'] = (ret['rm'] - ret['rf']) * ((ret['rm'] - ret['rf']) < 0)
    ret.reset_index(inplace=True)
    # T-M 模型
    res_TM = pd.DataFrame(index=ret.index, columns=['alpha', 'beta1', 'beta2', 'R2'])
    res_TM['date'] = ret['date']
    for i in range(window,ret.shape[0]):
        X = ret[['rm-rf', 'rm_2']]
        X = sm.add_constant(X)
        X = X.iloc[(i-window):i]
        Y = ret['f_avgreturn_day'] - ret['rf']
        Y = Y.iloc[(i-window):i]
        OLS = sm.OLS(Y, X).fit()
        OLS.summary()
        res_TM.loc[i, 'alpha'] = round(OLS.params[0], 4)
        res_TM.loc[i, 'beta1'] = round(OLS.params[1], 4)
        res_TM.loc[i, 'beta2'] = round(OLS.params[2], 4)
        res_TM.loc[i, 'R2'] = round(OLS.rsquared, 4)
    res_TM = res_TM.dropna().reset_index(drop=True)
    return res_TM

# ------------------------------------------------
# 公募基金择时选股收益拆分 Henriksson-Merton模型
# ------------------------------------------------
def anlsMF_HMModel(
        start_date,             # 起始日期，输入格式:datetime.date
        end_date,               # 结束日期，输入格式:datetime.date
        product_id,             # product_id基金代码，应为str格式（因数据库存储问题，优先使用场内代码）
        position = 0.85,        # 股票仓位
        window = 126            # 回看周期，天数
):
    assert (type(start_date) == datetime.date), '日期输入格式需为datetime.date'
    assert (type(end_date) == datetime.date), '日期输入格式需为datetime.date'
    assert (type(product_id) == str), '基金代码输入格式需为str'
    assert start_date < end_date, '起始日需早于结束日'
    rf = wind.wind_getBondCurve(start_date, end_date) # 十年国债收益率，视作无风险收益率
    rf.set_index('date', inplace=True)

    ret_fund = wind.wind_getMFStats([product_id], start_date, end_date, ['f_avgreturn_day']) # 基金收益率
    ret_fund = ret_fund[['date', 'f_avgreturn_day']].set_index('date')

    ret_bond = wind.wind_getIndexReturn('CBA00101.CS', start_date, end_date, 'D') # 中债-新综合财富(总值)指数
    ret_stock = wind.wind_getIndexReturn('881001.WI', start_date, end_date, 'D') # 万得全A
    ret_growth = wind.wind_getIndexReturn('399370.SZ', start_date, end_date, 'D') # 国证成长
    ret_value = wind.wind_getIndexReturn('399371.SZ', start_date, end_date, 'D') # 国证价值
    ret_bigcap = wind.wind_getIndexReturn('399314.SZ', start_date, end_date, 'D') # 巨潮大盘
    ret_smallcap = wind.wind_getIndexReturn('399316.SZ', start_date, end_date, 'D') # 巨潮小盘

    ret = pd.concat([ret_fund, ret_bond, ret_stock, ret_growth, ret_value, ret_bigcap, ret_smallcap, rf], axis=1)
    ret.dropna(inplace=True)
    # 因子构建
    ret['SMB'] = ret['399316.SZ'] - ret['399314.SZ']
    ret['HML'] = ret['399371.SZ'] - ret['399370.SZ']
    ret['rm'] = ret['881001.WI'] * position + ret['CBA00101.CS'] * (1 - position)
    ret['rf'] = (1 + ret['yield']) ** (1 / const.const.ANNUAL_SCALE) - 1
    ret['rm-rf'] = ret['rm'] - ret['rf']
    ret['rm_2'] = (ret['rm'] - ret['rf']) ** 2
    ret['rm_D'] = (ret['rm'] - ret['rf']) * ((ret['rm'] - ret['rf']) > 0)
    ret['rm_D1'] = (ret['rm'] - ret['rf']) * ((ret['rm'] - ret['rf']) < 0)
    ret.reset_index(inplace=True)
    # H-M 模型
    res_HM = pd.DataFrame(index=ret.index, columns=['alpha', 'beta1', 'beta2', 'R2'])
    res_HM['date'] = ret['date']
    for i in range(window, ret.shape[0]):
        X = ret[['rm-rf', 'rm_D']]
        X = sm.add_constant(X)
        X = X.iloc[(i - window):i]
        Y = ret['f_avgreturn_day'] - ret['rf']
        Y = Y.iloc[(i - window):i]
        OLS = sm.OLS(Y, X).fit()
        OLS.summary()
        res_HM.loc[i, 'alpha'] = round(OLS.params[0], 4)
        res_HM.loc[i, 'beta1'] = round(OLS.params[1], 4)
        res_HM.loc[i, 'beta2'] = round(OLS.params[2], 4)
        res_HM.loc[i, 'R2'] = round(OLS.rsquared, 4)
    res_HM = res_HM.dropna().reset_index(drop=True)
    return res_HM

# ------------------------------------------------
# 单只公募基金各行业选股能力
# 数值越大排名越靠前
# ------------------------------------------------
def anlsMF_StockSelectingAbility(
        start_date,                     # 起始日期，输入格式:datetime.date
        end_date,                       # 结束日期，输入格式:datetime.date
        product_id,                     # product_id基金代码，应为str格式（因数据库存储问题，优先使用场内代码）
        company,                        # 分类标准，输入格式:str，'SW' or 'CITICS'
        level,                          # 分类级别，输入格式:int
        freq = 'Q',                     # freq为频率，'Q'为季报，'H'为半年和年报
        Top10 = False                   # Top10为是否仅取季报前十大持仓
):
    assert (type(start_date) == datetime.date), '日期输入格式需为datetime.date'
    assert (type(end_date) == datetime.date), '日期输入格式需为datetime.date'
    assert (type(product_id) == str), '基金代码输入格式需为str'
    assert (len(product_id) == 9), '目前仅支持单只基金分析'
    assert start_date <= end_date, '起始日需早于结束日'
    assert (type(level) == int), 'level输入格式需为int'
    assert (company == 'SW' or company == 'CITICS'), 'company必须为SW或CITICS'
    portfolio = wind_getMFStockHoldings(None, freq, Top10) # 全部基金持仓

    assert portfolio.empty == False, '成立时间不足'

    portfolio = portfolio.loc[(portfolio['date'] >= start_date) & (portfolio['date'] <= end_date)].reset_index(drop=True)
    # 行业填充
    industry = wind.wind_getAllHistIndustriesMap(company, level)
    portfolio = pd.merge(portfolio, industry, on='stock_id', how='left')
    portfolio = portfolio.loc[(portfolio['date'] >= portfolio['entry_dt']) &(portfolio['date'] <= portfolio['remove_dt'])].reset_index(drop=True)
    del portfolio['entry_dt'], portfolio['remove_dt'] # 新股会在上市前出现在季报里面，当时没有行业分类，上一步会把当时没有分类的股票删掉
    # 股票季度表现
    AShare_return = wind.wind_getASharePeriodicReturn(start_date - datetime.timedelta(weeks=12), end_date, 'Q') # start_date早一段时间，防止季度收益计算时漏掉几个月
    AShare_return = AShare_return.sort_values(by=['stock_id', 'date']).reset_index(drop=True)
    AShare_return['next_quarterly_return'] = AShare_return.groupby(['stock_id'])['return'].shift(-1)
    AShare_return = AShare_return.dropna().reset_index(drop=True)

    AShare_return['year'] = pd.to_datetime(AShare_return['date']).dt.year
    AShare_return['quarter'] = pd.to_datetime(AShare_return['date']).dt.quarter
    portfolio['year'] = pd.to_datetime(portfolio['date']).dt.year
    portfolio['quarter'] = pd.to_datetime(portfolio['date']).dt.quarter
    portfolio = pd.merge(portfolio, AShare_return[['stock_id', 'year', 'quarter', 'next_quarterly_return']],how='left', on=['stock_id', 'year', 'quarter'])
    portfolio = portfolio.dropna(subset=['next_quarterly_return']).reset_index(drop=True)
    df_stk_ret_of_industries = portfolio.groupby(['date', 'product_id', 'industry'], as_index=False).apply(
        lambda x: np.average(x['next_quarterly_return'], weights=x['stk_value'])).rename(
        columns={None: 'stk_selecting_ret'})
    df_stk_ret_of_industries = df_stk_ret_of_industries.dropna().sort_values(by=['date', 'industry', 'stk_selecting_ret']).reset_index(drop=True)
    df_stk_ret_of_industries_rank = df_stk_ret_of_industries.groupby(['date','industry']).apply(lambda x: x['stk_selecting_ret'].rank()/len(x['stk_selecting_ret'])).reset_index()
    df_stk_ret_of_industries_rank['product_id'] = df_stk_ret_of_industries['product_id'] # 因为前一步排序了，所以可以直接赋值
    result = df_stk_ret_of_industries_rank.loc[df_stk_ret_of_industries_rank['product_id'] == product_id].reset_index(drop=True)
    result = result[['date', 'industry', 'stk_selecting_ret']]
    result = pd.pivot_table(result, columns='industry', index='date', values='stk_selecting_ret',aggfunc='first')
    result = result.append(pd.DataFrame(result.mean(), columns = ['平均']).T)
    return result

# ------------------------------------------------
# 基金产品的风格时序数据，包括：集中度、换手率、平均规模
# 返回一个表格Df。
# ------------------------------------------------
def anlsMF_fundTSStyleInfo(
        product_id,                                             # 基金代码，输入list
        date = datetime.date.today()   # 日期
):
    w.start()
    date = wind_getLastReportDate(date)
    fundCodes = ','.join(product_id)
    df_output = pd.DataFrame()
    for reportPeriodForward in range(16):
        fundStyle =w.wss(fundCodes,
                                   "trade_code,sec_name,prt_sellstockincome,prt_buystockcost,prt_topnstocktostock,prt_stockholding,fund_managementfeeratio,stm_is_11",
                                   "unit=1;rptDate={0};order=10;tradeDate={1}".format(date,date))
        fundStyledf = pd.DataFrame(pd.DataFrame(fundStyle.Data).values.T, columns=fundStyle.Fields)
        fundStyledf['top_10_stocks'] = fundStyledf['PRT_TOPNSTOCKTOSTOCK']/1e2
        fundStyledf['stock_num'] = fundStyledf['PRT_STOCKHOLDING'] if ((date.month in [6, 12]) & ((fundStyledf['PRT_STOCKHOLDING'] != 10).any())) else np.nan
        fundStyledf['date'] = date
        fundStyledf['product_id'] = product_id
        fundStyledf['product_name'] = fundStyledf['SEC_NAME']
        df_output = df_output.append(fundStyledf[['product_id', 'date', 'product_name', 'top_10_stocks', 'stock_num',
                                            'PRT_SELLSTOCKINCOME','PRT_BUYSTOCKCOST']])
        date = wind_getLastReportDate(date - datetime.timedelta(days = 1))
    avg_nav = anlsMF_getMFAUMHistory(product_id)
    df_output = pd.merge(df_output, avg_nav, on=['product_id', 'date'], how='left')
    df_output['turnover'] = (df_output['PRT_SELLSTOCKINCOME'] + df_output['PRT_BUYSTOCKCOST']) / df_output['avg_nav'] / 1e8
    del df_output['PRT_SELLSTOCKINCOME'], df_output['PRT_BUYSTOCKCOST']
    return df_output

# ------------------------------------------------
# 基金产品的持仓可变现程度时序数据，包含：占流通股本比，完全卖出需要天数
# 可计算单只产品流动性，或多只产品的持仓合计流动性（将所有产品的持仓股票加总后再计算)。如需计算多只产品，请令combineAllProducts=True
# 返回一个表格Df。
# ------------------------------------------------
def anlsMF_fundTSLiquidityInfo(
        product_id,                 # 基金代码，输入list
        combineAllProducts = False  # 是否合并计算所有产品的流动性
):
    stockHolding = wind_getMFStockHoldings(product_id, freq = 'Q', Top10= True)
    if combineAllProducts:
        stockHolding = stockHolding.groupby(['date', 'stock_id']).sum()
        stockHolding = stockHolding.reset_index()
    stockHolding['trade_date'] = wind_getLastTradeDates(stockHolding['date'].tolist())
    tradeAmount = wind_getAShareStockTradeData(stock_ids=stockHolding['stock_id'].tolist())
    tradeAmount = tradeAmount[['s_tech_tvma60', 'stock_id', 'trade_date']]
    stockHolding = pd.merge(stockHolding, tradeAmount, on = ['trade_date', 'stock_id'], how = 'left')
    stockHolding['liquidate_day'] = stockHolding['stk_value']/(stockHolding['s_tech_tvma60']*0.1)  # assume sell 10% per day.
    if combineAllProducts:
        stockHolding = stockHolding.groupby(['date']).max()
        stockHolding = stockHolding.reset_index()
        return stockHolding[['date', 'stk_quantity_to_compfloat', 'liquidate_day']]
    stockHolding = stockHolding.groupby(['date', 'product_id']).max()
    stockHolding = stockHolding.reset_index()
    return stockHolding[['date', 'product_id','stk_quantity_to_compfloat', 'liquidate_day']]

# ----------------------------------------------------
# 基金持仓模拟，持仓结合最新年报和季报披露股票持仓数据进行模拟
# -----------------------------------------------------
def anlsMF_getMFStockHoldingSimulation(
    date,  # datetime.date, 考察日期
    product_ids  # list, 产品列表
):
    assert isinstance(date, datetime.date), "date需为datetime.date类型"
    assert isinstance(product_ids, list), "product_ids需为list类型"
    holding_data = wind.wind_getMFStockHoldings(product_id=product_ids, freq='Q', start_date=date - datetime.timedelta(days=366), end_date=date).sort_values(['product_id', 'date'])
    holding_data['annual_flag'] = holding_data['date'].apply(lambda x: (x.month == 6 and x.day == 30) or (x.month == 12 and x.day == 31))  # 标记年报期
    # 因二季报和半年报/四季报和年报公布时间存在间隔，在12.31-3.30和6.30-8.31区间0630和1231持仓当作季报处理(但不限制只取Top10)
    # holding_data回溯时间为366天，至少会包含一期有效的年报数据
    if (date > datetime.date(date.year-1, 12, 31)) and (date <= datetime.date(date.year, 3, 31)):
        holding_data.loc[holding_data['date'].apply(lambda x: (x.month == 12 and x.day == 31)), 'annual_flag'] = False
    elif (date > datetime.date(date.year, 6, 30)) and (date <= datetime.date(date.year, 8, 31)):
        holding_data.loc[holding_data['date'].apply(lambda x: (x.month == 6 and x.day == 30)), 'annual_flag'] = False
    product_position_info = wind.wind_getMFAssetAllocation(product_ids=holding_data['product_id'].unique().tolist()).rename(columns={'product_stk_value_to_nav': 'stk_total_position'})
    holding_data = pd.merge(holding_data, product_position_info[['date', 'product_id', 'stk_total_position']], on=['date', 'product_id'], how='left')
    # 最新持仓数据
    latest_holding_data = holding_data.groupby(['product_id'], as_index=False).apply(lambda x: x[x['date'] == x['date'].max()])
    # 最新持仓披露为半年度的产品
    annual_holding_data = latest_holding_data[latest_holding_data['annual_flag']]
    # 最新持仓披露为季度的产品，再加入最新一期半年度持仓数据，结合两期持仓数据调整得到模拟持仓
    quarterly_holding_data = latest_holding_data[~latest_holding_data['annual_flag']]
    quarterly_holding_data = quarterly_holding_data.append(holding_data[(holding_data['product_id'].isin(quarterly_holding_data['product_id'].unique().tolist()))
                     & (holding_data['annual_flag'])].groupby(['product_id'], as_index=False).apply(lambda x: x[x['date'] == x['date'].max()]))
    def adjustQuarterlyHoldingData(x):
        # 季报持仓数据
        quarterly_holding = x[~x['annual_flag']].sort_values('stk_value_to_nav', ascending=False)
        quarterly_total_position = quarterly_holding['stk_total_position'].iloc[0]
        # 年报持仓仅保留不在季报持仓中的股票，调整权重对齐最新季度股票总仓位
        remain_position = quarterly_total_position - quarterly_holding['stk_value_to_nav'].sum()
        quarterly_excluded_annual_holding = x[(x['annual_flag']) & (~x['stock_id'].isin(quarterly_holding['stock_id'].to_list()))].copy()
        quarterly_excluded_annual_holding['stk_value_to_nav'] = quarterly_excluded_annual_holding['stk_value_to_nav'] * (remain_position / quarterly_excluded_annual_holding['stk_value_to_nav'].sum())
        return pd.concat([quarterly_holding, quarterly_excluded_annual_holding], axis=0)
    quarterly_holding_data = quarterly_holding_data.groupby('product_id', as_index=False).apply(adjustQuarterlyHoldingData)
    holding_simulation_res = pd.concat([annual_holding_data, quarterly_holding_data], axis=0)[['product_id', 'stock_id', 'stock_name', 'stk_value_to_nav']]
    holding_simulation_res['date'] = date
    return holding_simulation_res

# -------------------------------------------
# 公募基金股票持仓部分的收益模拟，根据模拟持仓数据推算
# 用于比较拟合股票持仓收益和实际收益的差异
# -------------------------------------------
def anlsMF_getMFStockHoldingSimulatedDailyReturn(
    date,           # datetime.date, 考察日期
    product_ids     # list, 产品列表
):
    holding_simulation_res = anlsMF_getMFStockHoldingSimulation(date, product_ids)
    # 收益模拟
    AShare_stock_px_data = wind.wind_getAShareStockTradeData(stock_ids=holding_simulation_res['stock_id'].unique().tolist(), start_date=date - datetime.timedelta(days=14), end_date=date)
    HKShare_stock_px_data = wind.wind_getHKShareStockTradeData(stock_ids=holding_simulation_res['stock_id'].unique().tolist(), start_date=date - datetime.timedelta(days=14), end_date=date)
    stock_px_data = pd.concat([AShare_stock_px_data[['trade_date', 'stock_id', 'adj_close']], HKShare_stock_px_data[['trade_date', 'stock_id', 'adj_close']]]).sort_values(['stock_id', 'trade_date']).rename(columns={'trade_date': 'date'})
    stock_px_data['stock_daily_ret'] = stock_px_data.groupby(['stock_id'], as_index=False)['adj_close'].transform(lambda x: x.pct_change())
    holding_simulation_res = pd.merge(holding_simulation_res, stock_px_data[['date', 'stock_id', 'stock_daily_ret']], on=['date', 'stock_id'], how='left')
    holding_simulation_res['stock_daily_contrib'] = holding_simulation_res['stk_value_to_nav'] * holding_simulation_res['stock_daily_ret']
    product_sim_ret = holding_simulation_res.groupby(['date', 'product_id'], as_index=False).agg({'stock_daily_contrib': 'sum'}).rename(columns={'stock_daily_contrib': 'product_sim_daily_ret'})
    product_nav_data = wind.wind_getMFNav(start_date=date - datetime.timedelta(days=14), end_date=date, product_id=product_ids)  # 向前多取一段时间保证有数
    product_nav_data['product_daily_ret'] = product_nav_data.groupby(['product_id'], as_index=False)['nav_adjusted'].transform(lambda x: x.pct_change())
    product_sim_ret = pd.merge(product_nav_data[['date', 'product_id', 'product_daily_ret']], product_sim_ret[['date', 'product_id', 'product_sim_daily_ret']], on=['date', 'product_id'], how='right')
    product_sim_ret['ret_diff'] = product_sim_ret['product_daily_ret'] - product_sim_ret['product_sim_daily_ret']
    product_sim_ret.sort_values('ret_diff', ascending=False, inplace=True)
    # 加入产品名称和pm信息
    product_info = wind.wind_getCurrentProductList(include_pm_info=True, product_ids=product_sim_ret['product_id'].unique().tolist(), only_a_share=False)
    product_info = product_info.groupby(['product_id'], as_index=False).agg({'product_name': 'first', 'pm_name': lambda x: ','.join([pm for pm in x])})
    product_sim_ret = pd.merge(product_info[['product_id', 'product_name', 'pm_name']], product_sim_ret, on='product_id', how='right')
    return product_sim_ret

# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# 4. 基金分类
# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------

# ------------------------------------------------------------------------
# 基金分类
# 按照以下规则：单行业占比超40%为行业主题，否则，单板块占比超45%为板块基金，否则：
# 若1）过去n个全持仓报告持有超2%的行业大于等于8个，2）每期前八大行业至少保留5个，则为均衡；否则Alpha
# startdate<=计算期<=enddate
# 目前算法是观察过往四期全持仓报表，startdate需在enddate四期前。可视需要修改代码更改期数。
# ------------------------------------------------------------------------
def anlsMF_singleFundClassification(
        product_id,         #基金代码str
        startdate,          #起始年报/半年报日期。仅限12.31或6.30
        enddate             #结束年报/半年报日期。仅限12.31或6.30
):
    assert (type(startdate) == datetime.date), '日期输入格式需为datetime.date'
    assert (type(enddate) == datetime.date), '日期输入格式需为datetime.date'
    assert (type(product_id) == str), '基金代码输入格式需为str'
    assert startdate <= enddate, '起始日需早于结束日'
    assert (startdate.month, startdate.day) in [(6,30), (12,31)], '月份需为6月或12月'
    assert (enddate.month , enddate.day) in [(6,30), (12,31)], '月份需为6月或12月'

    monthdelta = (enddate.year - startdate.year)*12 + (enddate.month - startdate.month)
    periodnum = 1 + monthdelta/6
    try:
        df = anlsMF_getMFHistoryIndustry(startdate, enddate, product_id, 'CITICS', 1, False, 'H', IndustrytoStkValue = True, OnlyEquity= True)
    except AssertionError as error:
        return str(error)
    if df.empty:
        return '成立时间不足'
    df['industry_avg_weight'] = df.industry_sum_weight/periodnum
    if df['industry_avg_weight'].sum() < 0.6:
        return '非权益基金'
    if max(df.industry_avg_weight) >= 0.40:
        row = df.industry_avg_weight.idxmax()
        fundType = df.industry[row] + '行业基金'
    else:
        df_sector = anlsMF_getMFHistorySector(product_id, startdate, enddate, IndustrytoStkValue=True, OnlyEquity= True)
        if max(df_sector['sector_avg_weight']) >= 0.45:
            row = df_sector.sector_avg_weight.idxmax()
            fundType = row

        else:
            indThreshold = 0.02
            if (enddate.month, enddate.day) == (12, 31):
                date1 = datetime.date(enddate.year, 6, 30)
            else:
                date1 = datetime.date(enddate.year - 1, 12, 31)
            date2 = datetime.date(enddate.year - 1, enddate.month, enddate.day)
            date3 = datetime.date(date1.year - 1, date1.month, date1.day)
            dates = [enddate, date1, date2, date3]
            qualifiedIndustryNumbers = []
            historyHoldingSummary = []
            for date in dates:
                historyHolding = anlsMF_getMFHistoryIndustry(date, date, product_id, 'CITICS', 1, False, 'H', IndustrytoStkValue=True)
                historyHolding.sort_values('industry_sum_weight', ascending= False, inplace= True)
                qualifiedIndustryNumbers.append(historyHolding[historyHolding['industry_sum_weight'] >= indThreshold].industry_sum_weight.count())
                historyHoldingSummary.append(historyHolding)
            IndustryNumberThreshold = 8
            if min(qualifiedIndustryNumbers) < IndustryNumberThreshold:
                fundType = 'Alpha基金'
            else:
                indIntersection1 = len(list(set(historyHoldingSummary[0].industry[:IndustryNumberThreshold].tolist()) & set(historyHoldingSummary[1].industry[:IndustryNumberThreshold].tolist())))
                indIntersection2 = len(list(set(historyHoldingSummary[1].industry[:IndustryNumberThreshold].tolist()) & set(historyHoldingSummary[2].industry[:IndustryNumberThreshold].tolist())))
                indIntersection3 = len(list(set(historyHoldingSummary[2].industry[:IndustryNumberThreshold].tolist()) & set(historyHoldingSummary[3].industry[:IndustryNumberThreshold].tolist())))
                if min(indIntersection1, indIntersection2, indIntersection3) < 5:
                    fundType = 'Alpha基金'
                else:
                    fundType = '均衡基金'
    return fundType

# ------------------------------------------------------------------------
# 基金分类-批量对基金库进行分类
# 按照以下规则：单行业占比超40%为行业主题，否则，单板块占比超45%为板块基金，否则：
# 若1）过去4个全持仓报告持有超2%的行业大于等于8个，2）每期前八大行业至少保留5个，则为均衡；否则Alpha
# startdate<=计算期<=enddate
# 请输入权益基金。根据行业占股票比例来计算。
# ------------------------------------------------------------------------
def anlsMF_fundClassification(
        fundDf,      #基金dataframe
        startdate,   #起始年报/半年报日期。仅限12.31或6.30
        enddate,     #结束年报/半年报日期。仅限12.31或6.30
        path         #结果输出路径
):
    assert (type(startdate) == datetime.date), '日期输入格式需为datetime.date'
    assert (type(enddate) == datetime.date), '日期输入格式需为datetime.date'
    assert startdate <= enddate, '起始日需早于结束日'
    assert (startdate.month, startdate.day) in [(6,30), (12,31)], '月份需为6月或12月'
    assert (enddate.month , enddate.day) in [(6,30), (12,31)], '月份需为6月或12月'
    fundDf['product_classification'] = fundDf.product_id.apply(lambda x: anlsMF_singleFundClassification(x, startdate, enddate))
    fundDf.to_excel('{0}/行业分类.xlsx'.format(path))
    return fundDf

# ------------------------------------------------
# 计算基金的jensen，选股能力(alpha)，选时能力(gamma)，Sharpe
# jensen-alpha = (ri-rf) - beta_i(rm-rf)
# 选股能力(alpha)，选时能力(gamma)： r-rf = alpha + beta(rm-rf) + gamma(rm-rf)**2 + epsilon
# ------------------------------------------------
def anlsMF_SelectedRatingIndicator(
        product_ids,                                    # list
        startdate,                                      # datetime.date
        enddate,                                        # datetime.date
        benchmark = '000300.SH',                        # benchmark, str.
        rf = 0.03                                       # risk-free rate (annual)
):
    retDf = wind_getMFSingleStats(product_ids, startdate, enddate)
    idxret = wind_getIndexReturn(benchmark, startdate, enddate, 'D')
    retDf = retDf.fillna(0)   # 部分封闭期基金只披露周度净值，处理nan项。
    regression_result = pd.DataFrame(columns = [*product_ids], index = ['jensen', 'alpha', 'gamma', 'sharpe'])
    for product in product_ids:
        regression_result.loc['jensen', product] = basicCal_jensen(retDf[product], idxret, rf)[0]
        [alpha, beta, gamma] = basicCal_AlphaGamma(retDf[product], idxret, rf)
        regression_result.loc['alpha', product] = alpha
        regression_result.loc['gamma', product] = gamma
        regression_result.loc['sharpe', product] = basicCal_getSharpeRatio(retDf[product], 'D', rf)
    regression_result = regression_result.T.reset_index()
    regression_result = regression_result.rename({'index':'product_id'}, axis = 1)
    regression_result.rename(columns = {'index':'factor'}, inplace=True)
    return regression_result

# ------------------------------------------------
# 计算基金的稳定度。数值越大，稳定性越好。
# 稳定度=Rank(Mean(Rank(r_{i,t}))/Std(Rank(r_i,t)))
# ------------------------------------------------
def anlsMF_RankStability(
        product_ids,    # list
        startdate,      # datetime.date
        enddate,        # datetime.date
):
    Fridays = fof_calendar.calendar_getFridays(startdate, enddate)
    def toPercentage(series):
        returntxt = []
        for str in series:
            if str is None:
                returntxt.append('无数据')
            else:
                returntxt.append('{:.2%}'.format(int(str.split('/')[0]) / int(str.split('/')[1])))
        return returntxt
    MFRanking = wind_getMFStats(product_ids, startdate, enddate, ['F_SFRANK_RECENTWEEKT'])
    MFRanking = MFRanking.merge(Fridays, on = 'date', how = 'inner')
    MFRanking['rank_1w'] = MFRanking[['f_sfrank_recentweekt']].apply(toPercentage)
    MFRanking.drop('f_sfrank_recentweekt', axis = 1, inplace = True)
    MFRanking.replace('无数据', '50.00%', inplace=True)  # 某些沪港深基金或其他原因在某时刻没有排名数据，替换为50%
    MFRanking['stability'] = MFRanking['rank_1w'].apply(lambda x: float(x[:-1]))
    Stability = MFRanking.groupby('product_id').mean() / MFRanking.groupby('product_id').std()
    Stability = Stability.rank(pct = True, ascending = False)
    Stability = Stability.reset_index()
    return Stability

# ------------------------------------------------
# 基金评级底层计算函数
# 40% sharpe + 20% jensen + 10% gamma + 10% alpha + 20% stability
# 评级: 一星：0-10%；二星：10%-32.5%；三星：32.5%-67.5%；四星：67.5%-90%；五星：90%-100%
# 在输入的基金之间进行排名
# ------------------------------------------------
def anlsMF_fundCustRank(
        product_ids,                                    # list
        startdate,                                      # datetime.date
        enddate,                                        # datetime.date
        benchmark = '000300.SH',                        # benchmark, str.
        rf = 0.03                                       # risk-free rate (annual)
):
    regression_result = anlsMF_SelectedRatingIndicator(product_ids, startdate, enddate, benchmark, rf)
    regression_result = regression_result.set_index('product_id').rank(pct=True).reset_index()  # 将因子值转化为排名，越大表现越好。
    Stability = anlsMF_RankStability(product_ids, startdate, enddate)
    RankingDf = regression_result.merge(Stability, on = 'product_id', how = 'left')
    RankingDf['score'] = RankingDf.apply(lambda x: 0.2*x['jensen']+0.4*x['sharpe']+0.1*x['gamma']+0.1*x['alpha']+0.2*x['stability'], axis = 1)
    RankingDf['score_rank'] = RankingDf['score'].rank(pct=True, ascending = True)
    def score_to_star(score):
        if score >0.9:
            star = 5
        elif score >0.675:
            star = 4
        elif score > 0.325:
            star = 3
        elif score >0.1:
            star = 2
        else:
            star = 1
        return star
    RankingDf['star'] = RankingDf['score_rank'].apply(score_to_star)
    return RankingDf

# ------------------------------------------------
# 基金评级（计算给定自定义区间基金评级）
# 40% sharpe + 20% jensen + 10% gamma + 10% alpha + 20% stability
# 评级: 一星：0-10%；二星：10%-32.5%；三星：32.5%-67.5%；四星：67.5%-90%；五星：90%-100%
# ------------------------------------------------
def anlsMF_fundRankingCustPeriod(
        startdate,                                                          # datetime.date
        enddate,                                                            # datetime.date
        type=['2001010101000000', '2001010201000000', '2001010204000000'],  # 要评级的基金类型，参见const
        benchmark = '000300.SH',                                            # benchmark, str.，影响jensen、alpha、beta的计算
        rf = 0.03                                                           # risk-free rate (annual)，影响jensen、alpha、beta、sharpe的计算
):
    FundPool = wind_getHistoricalProductList(fund_types=type, as_of_date=startdate, exclude_new_product=True)
    FundPool = FundPool[FundPool['sector_end_date'].isna()]
    RankingDf = anlsMF_fundCustRank(FundPool['product_id'].to_list(), startdate, enddate, benchmark, rf)
    RankingDf = RankingDf.merge(FundPool, on = 'product_id', how = 'left')
    return RankingDf

# ------------------------------------------------
# 基金评级-6m,1y,3y,5y（计算给定日期前6个月、一年、三年、五年的基金评级，用作每季度定期评级任务）
# 40% sharpe + 20% jensen + 10% gamma + 10% alpha + 20% stability
# 评级: 一星：0-10%；二星：10%-32.5%；三星：32.5%-67.5%；四星：67.5%-90%；五星：90%-100%
# ------------------------------------------------
def anlsMF_fundRankingQuarterly(
        date,                                                               # datetime.date
        type=['2001010101000000', '2001010201000000', '2001010204000000'],  # 要评级的基金类型，参见const
        benchmark = '000300.SH',                                            # benchmark, str.，影响jensen、alpha、beta的计算
        rf = 0.03                                                           # risk-free rate (annual)，影响jensen、alpha、beta、sharpe的计算
):
    #6m
    startdate_6m = date - datetime.timedelta(days = 182)
    FundPool_6m = wind_getHistoricalProductList(fund_types=type, as_of_date=startdate_6m, exclude_new_product=True)
    FundPool_6m = FundPool_6m[FundPool_6m['sector_end_date'].isna()]
    RankingDf_6m = anlsMF_fundCustRank(FundPool_6m['product_id'].to_list(), startdate_6m, date, benchmark, rf)
    RankingDf_6m.rename(columns = {'jensen':'Jensen_A_6M', 'sharpe':'Sharpe_6M', 'alpha':'选股能力_A_6M', 'gamma':'择时能力_A_6M',
                                 'stability':'稳定性_6M', 'star':'评级_6M','score':'score_6M'}, inplace = True)
    #1y
    startdate_1y = datetime.date(date.year - 1, date.month, date.day)
    FundPool_1y = wind_getHistoricalProductList(fund_types=type, as_of_date=startdate_6m, exclude_new_product=True)
    FundPool_1y = FundPool_1y[FundPool_1y['sector_end_date'].isna()]
    RankingDf_1y = anlsMF_fundCustRank(FundPool_1y['product_id'].to_list(), startdate_1y, date, benchmark, rf)
    RankingDf_1y.rename(columns = {'jensen':'Jensen_A_1Y', 'sharpe':'Sharpe_1Y', 'alpha':'选股能力_A_1Y', 'gamma':'择时能力_A_1Y',
                                 'stability':'稳定性_1Y', 'star':'评级_1Y','score':'score_1Y'}, inplace = True)
    #3y
    startdate_3y = datetime.date(date.year - 3, date.month, date.day)
    FundPool_3y = wind_getHistoricalProductList(fund_types=type, as_of_date=startdate_6m, exclude_new_product=True)
    FundPool_3y = FundPool_3y[FundPool_3y['sector_end_date'].isna()]
    RankingDf_3y = anlsMF_fundCustRank(FundPool_3y['product_id'].to_list(), startdate_3y, date, benchmark, rf)
    RankingDf_3y.rename(columns = {'jensen':'Jensen_A_3Y', 'sharpe':'Sharpe_3Y', 'alpha':'选股能力_A_3Y', 'gamma':'择时能力_A_3Y',
                                 'stability':'稳定性_3Y', 'star':'评级_3Y','score':'score_3Y'}, inplace = True)
    #5y
    startdate_5y = datetime.date(date.year - 5, date.month, date.day)
    FundPool_5y = wind_getHistoricalProductList(fund_types=type, as_of_date=startdate_6m, exclude_new_product=True)
    FundPool_5y = FundPool_5y[FundPool_5y['sector_end_date'].isna()]
    RankingDf_5y = anlsMF_fundCustRank(FundPool_5y['product_id'].to_list(), startdate_5y, date, benchmark, rf)
    RankingDf_5y.rename(columns = {'jensen':'Jensen_A_5Y', 'sharpe':'Sharpe_5Y', 'alpha':'选股能力_A_5Y', 'gamma':'择时能力_A_5Y',
                                 'stability':'稳定性_5Y', 'star':'评级_5Y','score':'score_5Y'}, inplace = True)
    RankingDf = RankingDf_6m.merge(RankingDf_1y, on = 'product_id', how = 'left')
    RankingDf = RankingDf.merge(RankingDf_3y, on = 'product_id', how = 'left')
    RankingDf = RankingDf.merge(RankingDf_5y, on = 'product_id', how = 'left')
    FundPool_6m = FundPool_6m.drop(['product_end_date', 'sector_end_date'], axis = 1)
    RankingDf = RankingDf.merge(FundPool_6m, on = 'product_id', how = 'left')
    return RankingDf


# ------------------------------------------------------
# 公募基金评级筛选
# ------------------------------------------------------
def anlsMF_univRatingDataFilter(
    as_of_date,
    date_list,
    lookback_num,
    coverage,
    filters # 是list of list的形式，例如：[['rating_6m', 3], ['rating_1y', 3]] 表示6月评分在3星及以上且1年评分3星及以上
):
    start_date = date_list[date_list['rating_date'] <= as_of_date]['rating_date'].iloc[lookback_num]
    rating_data = custMF.custMF_getMFRatingInfo(start_date, as_of_date)
    qualifed_rating_data = copy.deepcopy(rating_data)
    for this_filter in filters:
        qualifed_rating_data = qualifed_rating_data[qualifed_rating_data[this_filter[0]] >= this_filter[1]]
    qualified = qualifed_rating_data.groupby(by='product_id', as_index=False).count()[['product_id', 'product_name']].rename(columns={'product_name': 'coverage'})
    qualified['coverage'] = qualified['coverage']/(lookback_num+1)
    qualified = qualified[qualified['coverage'] >= coverage]
    rating_data = rating_data.merge(qualified, how='inner', on='product_id')
    return rating_data
