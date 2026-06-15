# ------------------------------------------------
# 本文档用于公募基金数据的画图
# ------------------------------------------------
import src.data.wind as wind
import seaborn as sn
import pandas as pd
import datetime
import matplotlib.pyplot as plt
import dataframe_image as dfi
import dateutil.relativedelta as relativedelta
from src.data.wind import *
from src.analysis.MFAnalysis import *
import src.utils.Calculation as Cal
import src.analysis.MFAnalysis as Anls
from src.visualization.basicVis import *
plt.style.use('ggplot') # 使用ggplot样式
plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False

# ------------------------------------------------------
# 公募基金净值画图，加上基准，支持多个基金
# ------------------------------------------------------
def visMF_navHist(
        start_date,                  # 起始日期，输入格式:datetime.date
        end_date,                    # 结束日期，输入格式:datetime.date
        product_ids,                  # product_id基金代码，应为list格式（因数据库存储问题，优先使用场内代码）
        idx_code=None                # 基准指数，输入格式:String, eg: "000905.SH", "885001.WI"，默认为空，不加基准
):
    assert (type(start_date) == datetime.date), '日期输入格式需为datetime.date'
    assert (type(end_date) == datetime.date), '日期输入格式需为datetime.date'
    assert start_date < end_date, '起始日需早于结束日'
    df_fund = wind.wind_getMFNav(start_date, end_date, product_ids)
    df_index = wind.wind_getIndexData(idx_code, start_date, end_date, freq='D')[['date','close_price']]
    df_index.rename(columns={'close_price':idx_code}, inplace=True)
    df_index.set_index('date', inplace=True)
    df_fund = pd.pivot(data=df_fund, columns='product_name', index='date', values='nav_adjusted')
    df = pd.merge(df_fund, df_index, left_index=True, right_index=True, how='left')
    df.fillna(method='bfill', inplace=True)
    df = df / df.iloc[0, :]  # 归一化
    if idx_code == None:
        df.drop([None], axis=1, inplace=True)
    df.plot()
    plt.title('净值曲线')
    plt.show()
    plt.close()

# ------------------------------------------------------
# 公募基金收益相关性画图
# ------------------------------------------------------
def visMF_Correlation(
        start_date,                  # 起始日期，输入格式:datetime.date
        end_date,                    # 结束日期，输入格式:datetime.date
        product_ids,                  # product_id基金代码，应为list格式（因数据库存储问题，优先使用场内代码）
):
    ret = wind.wind_getMFSingleStats(product_ids, start_date, end_date)
    corr = Cal.basicCal_Corraltion(ret)
    sn.heatmap(corr, cmap='coolwarm', annot=True)
    plt.show()

# ------------------------------------------------------
# 公募基金择时选股收益拆分 T-M模型画图
# ------------------------------------------------------
def visMF_TMModel(
        start_date,        # 起始日期，输入格式:datetime.date
        end_date,          # 结束日期，输入格式:datetime.date
        product_id,        # product_id基金代码，应为str格式（因数据库存储问题，优先使用场内代码）
        position=0.85,     # 股票仓位
        window=126         # 回看周期，天数
):
    df = Anls.anlsMF_TMModel(start_date, end_date, product_id, position, window)
    fig, ax1 = plt.subplots()
    ax1.plot(df['date'], df['beta2'], 'b', label='beta(左轴)')
    ax1.legend(loc='upper left')
    ax1.grid(axis='y', linestyle='--')
    ax2 = ax1.twinx()
    ax2.plot(df['date'], df['alpha'], label='alpha(右轴)')
    ax2.legend(loc='upper right')
    plt.title('T-M模型')
    plt.show()

# ------------------------------------------------------
# 公募基金择时选股收益拆分 H-M模型画图
# ------------------------------------------------------
def visMF_HMModel(
        start_date,        # 起始日期，输入格式:datetime.date
        end_date,          # 结束日期，输入格式:datetime.date
        product_id,        # product_id基金代码，应为str格式（因数据库存储问题，优先使用场内代码）
        position=0.85,     # 股票仓位
        window=126         # 回看周期，天数
):
    df = Anls.anlsMF_HMModel(start_date, end_date, product_id, position, window)
    fig, ax1 = plt.subplots()
    ax1.plot(df['date'], df['beta2'], 'b', label='beta(左轴)')
    ax1.legend(loc='upper left')
    ax1.grid(axis='y', linestyle='--')
    ax2 = ax1.twinx()
    ax2.plot(df['date'], df['alpha'], label='alpha(右轴)')
    ax2.legend(loc='upper right')
    plt.title('H-M模型')
    plt.show()

# ------------------------------------------------------
# 公募基金经理管理规模图
# ------------------------------------------------------
def visMF_AUMofPM(
        fundManager,                    # 基金经理
        fundCompany,                    # 基金公司
        date=datetime.date.today()      # 日期
):
    AumInfo = anlsMF_allProductTSInfoOfPM(fundManager, fundCompany, date)
    AumInfo = AumInfo.fillna(0)
    institution_holding = AumInfo.groupby('report_date').sum()
    institution_holding['institution_ratio'] = institution_holding['institution_shares_holding']/institution_holding['total_shares']
    institution_ratio = institution_holding.sort_values(by = 'report_date', ascending= True)['institution_ratio'].tolist()
    for i in range(len(institution_ratio)):
        if institution_ratio[i] == 0:
            if i != 0:
                institution_ratio[i] = institution_ratio[i-1]
    productsAUM = []
    productsNames = []
    reportdates = AumInfo.sort_values(by = 'report_date', ascending= True)['report_date'].unique().tolist()
    product_ids = AumInfo.sort_values(by = 'pm_startdate', ascending= True)['product_id'].unique().tolist()
    for product in product_ids:
        productAUM = AumInfo[AumInfo['product_id']==product].sort_values(by = 'report_date', ascending= True)
        productsAUM.append(productAUM['net_asset'].tolist())
        productsNames.append(productAUM['product_name'].iloc[0])
    fig, ax1 = plt.subplots()
    ax2 = ax1.twinx()
    ax1.stackplot(reportdates, *productsAUM, baseline='zero', labels=productsNames)
    ax1.legend(loc='upper left')
    ax1.set_ylabel('规模')
    ax1.grid(axis='y', color='gray', linestyle=':', linewidth=2)
    ax2.plot(reportdates, institution_ratio)
    ax2.set_ylabel('机构持仓占比')
    plt.title('基金经理管理规模')
    plt.show()
    return

# ------------------------------------------------------
# 公募基金经理各产品权益仓位变化图
# ------------------------------------------------------
def visMF_stockPctofPM(
        fundManager,                    # 基金经理
        fundCompany,                    # 基金公司
        date=datetime.date.today()      # 日期
):
    AumInfo = anlsMF_allProductTSInfoOfPM(fundManager, fundCompany, date)
    productsNames = []
    stockpct = []
    reportdates = AumInfo.sort_values(by = 'report_date', ascending= True)['report_date'].unique().tolist()
    product_ids = AumInfo.sort_values(by = 'pm_startdate', ascending= True)['product_id'].unique().tolist()
    for product in product_ids:
        productAUM = AumInfo[AumInfo['product_id']==product].sort_values(by = 'report_date', ascending= True)
        productsNames.append(productAUM['product_name'].iloc[0])
        stockpct.append(productAUM['stock_pct'].tolist())
    for i in range(len(stockpct)):
        plt.plot(reportdates, stockpct[i])
    plt.legend(productsNames)
    plt.ylabel('权益仓位')
    plt.grid(axis='y', color='gray', linestyle=':', linewidth=2)
    plt.title('权益仓位变化')
    plt.show()
    return

# ------------------------------------------------------
# 公募基金经理整体仓位变化图
# ------------------------------------------------------
def visMF_AssetAllocationofPM(
        fundManager,                    # 基金经理
        fundCompany,                    # 基金公司
        date=datetime.date.today()      # 日期
):
    AumInfo = anlsMF_allProductTSInfoOfPM(fundManager, fundCompany, date)
    AumInfo = AumInfo[AumInfo['pm_startdate'] < AumInfo['report_date']]
    AumInfo = AumInfo.dropna(subset = ['stock_pct'])
    reportdates = AumInfo.sort_values(by = 'report_date', ascending= True)['report_date'].unique().tolist()
    AumInfo['stockNAV'] = AumInfo['stock_pct']*AumInfo['net_asset']
    AumInfo['bondNAV'] = AumInfo['bond_pct']*AumInfo['net_asset']
    stockNAV = AumInfo.groupby('report_date')['stockNAV'].sum()
    bondNAV = AumInfo.groupby('report_date')['bondNAV'].sum()
    NAV = AumInfo.groupby('report_date')['net_asset'].sum()
    stockpct = (stockNAV/NAV).sort_index(ascending= True).tolist()
    bondpct = (bondNAV/NAV).sort_index(ascending= True).tolist()
    plt.stackplot(reportdates, stockpct, bondpct, baseline='zero', labels=['权益仓位', '债券仓位'])
    plt.legend(loc='upper left')
    plt.grid(axis='y', color='gray', linestyle=':', linewidth=2)
    plt.title('基金经理整体仓位变化')
    plt.show()
    return

# ------------------------------------------------------
# 公募基金持股集中度变化图
# ------------------------------------------------------
def visMF_concentrationRate(
        product_id,                     # 基金代码，输入str，请输入单只基金。
        date=datetime.date.today()      # 日期
):
    TSinfo = anlsMF_fundTSStyleInfo([product_id], date).sort_values(by='date', ascending=True)
    TSinfo = TSinfo.fillna(0)
    top_10_stocks = TSinfo['top_10_stocks'].tolist()
    stock_num = TSinfo['stock_num'].tolist()
    report_date = TSinfo['date'].tolist()
    # 排除掉输入日期在某报告期后但报告未出的情况
    if top_10_stocks[-1] == 0 and stock_num[-1] == 0:
        top_10_stocks = top_10_stocks[:-1]
        stock_num = stock_num[:-1]
        report_date = report_date [:-1]
    for i in range(len(stock_num)):
        if stock_num[i] == 0:
            if i != 0:
                stock_num[i] = stock_num[i-1]
    fig, ax1 = plt.subplots()
    ax1.grid(False)
    line1, = ax1.plot(report_date, top_10_stocks)
    ax2 = ax1.twinx()
    ax2.grid(False)
    line2, = ax2.stackplot(report_date, stock_num, color = 'darkgray')
    ax1.set_facecolor("none")
    ax1.set_zorder(2)
    ax2.set_zorder(1)
    plt.legend(handles = [line1, line2], labels = ['前十大权重（%）', '持股数量（右）'], loc = 'upper left')
    plt.title('基金持股集中度')
    plt.show()
    return

# ------------------------------------------------------
# 公募基金持股流动性变化图
# 可计算单只产品流动性，或多只产品的持仓合计流动性（将所有产品的持仓股票加总后再计算)。如需计算多只产品，请令combineAllProducts=True
# ------------------------------------------------------
def visMF_liquidity(
        product_id,                     # 基金代码，输入list。若分析多只基金，请令combineAllProducts=True
        combineAllProducts=False        # 是否合并计算所有产品的流动性
):
    liquidity = anlsMF_fundTSLiquidityInfo(product_id, combineAllProducts)
    stk_quantity_to_compfloat = liquidity['stk_quantity_to_compfloat'].tolist()
    liquidate_day = liquidity['liquidate_day'].tolist()
    report_date = liquidity['date'].tolist()
    fig, ax1 = plt.subplots()
    line1, = ax1.plot(report_date, liquidate_day)
    ax2 = ax1.twinx()
    line2, = ax2.plot(report_date, stk_quantity_to_compfloat, color = 'blue')
    plt.legend(handles = [line1, line2], labels = ['前十大重仓股完全卖出需要天数', '前十大重仓股占上市公司自由流通市值比例（右）'], loc = 'upper left')
    ax1.grid(axis='y', linestyle='--')
    plt.title('持股流动性')
    plt.show()
    return

# ------------------------------------------------------
# 公募基金换手率变化图
# ------------------------------------------------------
def visMF_turnover(
        product_id,                     # 基金代码，输入str，请输入单只基金。
        date=datetime.date.today()      # 日期
):
    TSinfo = anlsMF_fundTSStyleInfo([product_id], date).sort_values(by='date', ascending=True)
    TSinfo = TSinfo.dropna()
    avg_netasset = TSinfo['avg_nav'].tolist()
    turnover = TSinfo['turnover'].tolist()
    report_date = TSinfo['date'].tolist()
    fig, ax1 = plt.subplots()
    line1, = ax1.plot(report_date, turnover)
    ax2 = ax1.twinx()
    line2, = ax2.plot(report_date, avg_netasset, color = 'blue')
    ax1.grid(axis='y', linestyle='--')
    plt.legend(handles = [line1, line2], labels = ['双边换手率', '平均规模（右）'], loc = 'upper left')
    plt.title('换手率')
    plt.show()
    return

# ------------------------------------------------------
# 公募基金历史股票持仓
# ------------------------------------------------------
def visMF_HistoryStock(
        start_date,  # 起始日期，输入格式:datetime.date
        end_date,  # 结束日期，输入格式:datetime.date
        product_id,  # product_id基金代码，应为list格式（因数据库存储问题，优先使用场内代码）
        allHoldings = False,    # 是否包括上市公司公告里面的隐藏持仓
        chrome_path=None,           # the chrome.exe path
        local_path=None,            # the path you would like to save the image
        picture_name=None          # the name of the picture you want to save
):
    df = Anls.anlsMF_getMFHistoryStock(start_date, end_date, product_id, allHoldings)
    df = df.iloc[:40]
    df = df.style.format({'stock_sum_weight': '{:.2%}'}).background_gradient(subset=['stock_sum_weight', 'stock_count'], cmap='Reds', low=0, high=config.cmap_range_adjust_coef)
    if chrome_path is not None and local_path is not None and picture_name is not None:
        local_path = local_path + '/' + picture_name + '.png'
        dfi.export(df, local_path, chrome_path=chrome_path)
        return
    else:
        return df

# ------------------------------------------------------
# 公募基金历史持仓行业
# ------------------------------------------------------
def visMF_HistoryIndustry(
        start_date,  # 起始日期，输入格式:datetime.date
        end_date,  # 结束日期，输入格式:datetime.date
        product_id,  # product_id基金代码，应为str格式（因数据库存储问题，优先使用场内代码）
        company,                        # 分类标准，输入格式:str，'SW' or 'CITICS'
        level,                          # 分类级别，输入格式:int
        allHoldings = False,         # 是否包括上市公司公告里面的隐藏持仓
        chrome_path=None,           # the chrome.exe path
        local_path=None,            # the path you would like to save the image
        picture_name=None          # the name of the picture you want to save
):
    df = Anls.anlsMF_getMFHistoryIndustry(start_date, end_date, product_id, company, level, allHoldings, 'Q')
    df = df.iloc[:20]
    df = df.style.format({'industry_sum_weight': '{:.2%}'}).background_gradient(subset=['industry_sum_weight','industry_count'], cmap='Reds', low=0, high=config.cmap_range_adjust_coef)
    if chrome_path is not None and local_path is not None and picture_name is not None:
        local_path = local_path + '/' + picture_name + '.png'
        dfi.export(df, local_path, chrome_path=chrome_path)
        return
    else:
        return df

# ------------------------------------------------------
# 公募基金历史持仓板块
# ------------------------------------------------------
def visMF_HistorySector(
        start_date,  # 起始日期，输入格式:datetime.date
        end_date,  # 结束日期，输入格式:datetime.date
        product_id,  # product_id基金代码，应为str格式（因数据库存储问题，优先使用场内代码）
        company,                        # 分类标准，输入格式:str，'SW' or 'CITICS'
        level,                          # 分类级别，输入格式:int
        hidden_holdings = False,        # 是否包括上市公司公告里面的隐藏持仓
        freq = 'Q',                     # freq为频率，'Q'为季报，'H'为半年和年报
        Top10 = False,                  # Top10为是否仅取季报前十大持仓
        IndustrytoStkValue = False,     # False:行业占基金净值比；True:行业占股票市值比
        OnlyEquity = False,              # 非权益基金（start_date到end_date期间基金平均权益仓位小于60%）是否返回AssertionError
        chrome_path=None,           # the chrome.exe path
        local_path=None,            # the path you would like to save the image
        picture_name=None          # the name of the picture you want to save
):
    df = Anls.anlsMF_getMFHistorySector(product_id, start_date, end_date,company, level, hidden_holdings = False, freq = 'Q', Top10 = False, IndustrytoStkValue = False, OnlyEquity = False
)
    df = df.style.format({'sector_avg_weight': '{:.2%}'}).background_gradient(subset=['sector_avg_weight'], cmap='Reds', low=0, high=config.cmap_range_adjust_coef)
    if chrome_path is not None and local_path is not None and picture_name is not None:
        local_path = local_path + '/' + picture_name + '.png'
        dfi.export(df, local_path, chrome_path=chrome_path)
        return
    else:
        return df

# ------------------------------------------------------
# 单只公募基金收益分析
# ------------------------------------------------------
def visMF_retAnalysis(
        start_date,  # 起始日期，输入格式:datetime.date
        end_date,  # 结束日期，输入格式:datetime.date
        product_id,  # product_id基金代码，应为str格式（因数据库存储问题，优先使用场内代码）
        idx_code,  # 基准指数，输入格式:String, eg: "000905.SH", "885001.WI"
        chrome_path=None,           # the chrome.exe path
        local_path=None,            # the path you would like to save the image
        picture_name=None          # the name of the picture you want to save
):
    df = Anls.anlsMF_retAnalysis(start_date, end_date, product_id, idx_code)
    df = df.style.format('{:.2%}').background_gradient(subset=['return_product', 'MaxDrawdown_product'], cmap='Reds', low=0, high=config.cmap_range_adjust_coef)
    if chrome_path is not None and local_path is not None and picture_name is not None:
        local_path = local_path + '/' + picture_name + '.png'
        dfi.export(df, local_path, chrome_path=chrome_path)
        return
    else:
        return df

# ------------------------------------------------------
# 基金经理管理所有基金的静态信息
# ------------------------------------------------------
def visMF_allProductStaticInfoOfPM(
        fundManager,  # 基金经理
        fundCompany,  # 基金公司
        date = datetime.date.today(),  # 日期
        chrome_path=None,           # the chrome.exe path
        local_path=None,            # the path you would like to save the image
        picture_name=None          # the name of the picture you want to save
):
    df = Anls.anlsMF_allProductStaticInfoOfPM(fundManager, fundCompany, date)
    if chrome_path is not None and local_path is not None and picture_name is not None:
        local_path = local_path + '/' + picture_name + '.png'
        dfi.export(df, local_path, chrome_path=chrome_path)
        return
    else:
        return df

# ------------------------------------------------------
# 基金经理个人简介
# ------------------------------------------------------
def visMF_pmInfo(
        fundManager,  # 基金经理
        fundCompany,  # 基金公司
        chrome_path=None,           # the chrome.exe path
        local_path=None,            # the path you would like to save the image
        picture_name=None          # the name of the picture you want to save
):
    df = Anls.anlsMF_pmInfo(fundManager, fundCompany)
    df = df.style.format(None)
    if chrome_path is not None and local_path is not None and picture_name is not None:
        local_path = local_path + '/' + picture_name + '.png'
        dfi.export(df, local_path, chrome_path=chrome_path)
        return
    else:
        return df

# ------------------------------------------------------
# 单只公募基金各报告期各行业第一大重仓股
# ------------------------------------------------------
def visMF_firstStockofEachIndustry(
        start_date,         # 起始日期，输入格式:datetime.date
        end_date,           # 结束日期，输入格式:datetime.date
        product_id,         # product_id基金代码，应为str格式（因数据库存储问题，优先使用场内代码）
        company,            # 分类标准，输入格式:str，'SW' or 'CITICS'
        level,              # 分类级别，输入格式:int
        allHoldings = False,    # 是否包括上市公司公告里面的隐藏持仓
        freq='Q',           # freq为频率，'Q'为季报，'H'为半年和年报
        Top10=False,        # Top10为是否仅取季报前十大持仓
        chrome_path=None,   # the chrome.exe path
        local_path=None,    # the path you would like to save the image
        picture_name=None   # the name of the picture you want to save
):
    df = Anls.anlsMF_getMFFirstStockofEachIndustry(start_date, end_date, product_id, company, level, allHoldings, freq, Top10)
    df.fillna('', inplace=True)
    df = df.style.format(None)
    if chrome_path is not None and local_path is not None and picture_name is not None:
        local_path = local_path + '/' + picture_name + '.png'
        dfi.export(df, local_path, chrome_path=chrome_path)
        return
    else:
        return df

# ------------------------------------------------------
# 单只公募基金各报告期前三大行业
# ------------------------------------------------------
def visMF_Top3Industry(
        start_date,                 # 起始日期，输入格式:datetime.date
        end_date,                   # 结束日期，输入格式:datetime.date
        product_id,                 # product_id基金代码，应为str格式（因数据库存储问题，优先使用场内代码）
        company,                    # 分类标准，输入格式:str，'SW' or 'CITICS'
        level,                      # 分类级别，输入格式:int
        allHoldings = False,        # 是否包括上市公司公告里面的隐藏持仓
        freq='Q',                   # freq为频率，'Q'为季报，'H'为半年和年报
        Top10=False,                # Top10为是否仅取季报前十大持仓
        IndustrytoAllStock = False, # False:行业占基金净值比；True:行业占股票市值比
        chrome_path=None,           # the chrome.exe path
        local_path=None,            # the path you would like to save the image
        picture_name=None           # the name of the picture you want to save
):
    df = Anls.anlsMF_getMFTop3Industry(start_date, end_date, product_id, company, level, allHoldings, freq, Top10, IndustrytoAllStock)
    df = df.style.format({'第一大行业比例': '{:.2%}', '第二大行业比例': '{:.2%}', '第三大行业比例': '{:.2%}'}, na_rep='').background_gradient(subset=['第一大行业比例', '第二大行业比例', '第三大行业比例'], axis=None, cmap='Reds', low=0, high=config.cmap_range_adjust_coef)
    if chrome_path is not None and local_path is not None and picture_name is not None:
        local_path = local_path + '/' + picture_name + '.png'
        dfi.export(df, local_path, chrome_path=chrome_path)
        return
    else:
        return df

# ------------------------------------------------------
# 单只公募基金各报告期各行业比例
# ------------------------------------------------------
def visMF_IndustryDistribution(
        start_date,                 # 起始日期，输入格式:datetime.date
        end_date,                   # 结束日期，输入格式:datetime.date
        product_id,                 # product_id基金代码，应为str格式（因数据库存储问题，优先使用场内代码）
        company,                    # 分类标准，输入格式:str，'SW' or 'CITICS'
        level,                      # 分类级别，输入格式:int
        allHoldings = False,        # 是否包括上市公司公告里面的隐藏持仓
        freq='Q',                   # freq为频率，'Q'为季报，'H'为半年和年报
        Top10=False,                # Top10为是否仅取季报前十大持仓
        IndustrytoAllStock = False, # False:行业占基金净值比；True:行业占股票市值比
        chrome_path=None,           # the chrome.exe path
        local_path=None,            # the path you would like to save the image
        picture_name=None           # the name of the picture you want to save
):
    df = Anls.anlsMF_getMFIndustryDistribution(start_date, end_date, product_id, company, level, allHoldings, freq, Top10, IndustrytoAllStock)
    df = df.style.format('{:.2%}').applymap(lambda x: 'color: transparent' if pd.isnull(x) else '')
    if chrome_path is not None and local_path is not None and picture_name is not None:
        local_path = local_path + '/' + picture_name + '.png'
        dfi.export(df, local_path, chrome_path=chrome_path)
        return
    else:
        return df

# ------------------------------------------------------
# 单只公募基金各报告期各行业的股票个数
# ------------------------------------------------------
def visMF_StockNumofEachIndustry(
        start_date,                 # 起始日期，输入格式:datetime.date
        end_date,                   # 结束日期，输入格式:datetime.date
        product_id,                 # product_id基金代码，应为str格式（因数据库存储问题，优先使用场内代码）
        company,                    # 分类标准，输入格式:str，'SW' or 'CITICS'
        level,                      # 分类级别，输入格式:int
        allHoldings = False,        # 是否包括上市公司公告里面的隐藏持仓
        freq='Q',                   # freq为频率，'Q'为季报，'H'为半年和年报
        Top10=False,                # Top10为是否仅取季报前十大持仓
        IndustrytoAllStock = False, # False:行业占基金净值比；True:行业占股票市值比
        chrome_path=None,           # the chrome.exe path
        local_path=None,            # the path you would like to save the image
        picture_name=None           # the name of the picture you want to save
):
    df = Anls.anlsMF_getMFStockNumofEachIndustry(start_date, end_date, product_id, company, level, allHoldings, freq, Top10, IndustrytoAllStock)
    df = df.style.format('{:.0f}').applymap(lambda x: 'color: transparent' if pd.isnull(x) else '')
    if chrome_path is not None and local_path is not None and picture_name is not None:
        local_path = local_path + '/' + picture_name + '.png'
        dfi.export(df, local_path, chrome_path=chrome_path)
        return
    else:
        return df

# ------------------------------------------------------
# 单只公募基金各行业选股能力
# ------------------------------------------------------
def visMF_StockSelectingAbility(
        start_date,                 # 起始日期，输入格式:datetime.date
        end_date,                   # 结束日期，输入格式:datetime.date
        product_id,                 # product_id基金代码，应为str格式（因数据库存储问题，优先使用场内代码）
        company,                    # 分类标准，输入格式:str，'SW' or 'CITICS'
        level,                      # 分类级别，输入格式:int
        freq='Q',                   # freq为频率，'Q'为季报，'H'为半年和年报
        Top10=False,                # Top10为是否仅取季报前十大持仓
        chrome_path=None,           # the chrome.exe path
        local_path=None,            # the path you would like to save the image
        picture_name=None           # the name of the picture you want to save
):
    df = Anls.anlsMF_StockSelectingAbility(start_date, end_date, product_id, company, level, freq, Top10)
    # 最新一期雷达图
    df_avg = df.iloc[-1,:]
    plt.style.use('ggplot')
    feature = list(df_avg.index)
    values = df_avg.tolist()
    N = len(values)
    angles = np.linspace(0, 2 * np.pi, N, endpoint=False)  # 设置雷达图的角度，用于平分切开一个平面
    values = np.concatenate((values, [values[0]]))  # 使雷达图封闭起来
    angles = np.concatenate((angles, [angles[0]]))
    fig = plt.figure()  # 绘图
    ax = fig.add_subplot(111, polar=True)  # 设置为极坐标格式
    ax.plot(angles, values, 'o-', linewidth=2, label='活动前')  # 绘制折线图
    ax.fill(angles, values, 'r', alpha=0.5)
    ax.set_thetagrids(angles[:len(angles)-1] * 180 / np.pi, feature)  # 添加每个特质的标签
    ax.set_ylim(0, 1)  # 设置极轴范围
    ax.grid(True)  # 增加网格纸
    plt.title('管理以来各行业平均选股能力')
    plt.show()
    df = df.style.format('{:.2%}').applymap(lambda x: 'color: transparent' if pd.isnull(x) else '')
    if chrome_path is not None and local_path is not None and picture_name is not None:
        local_path = local_path + '/' + picture_name + '.png'
        dfi.export(df, local_path, chrome_path=chrome_path)
        return
    else:
        return df

# ------------------------------------------------------
# 单只公募基金各报告期持股特点（PE/PB/ROE/MV/GROWTH等）
# ------------------------------------------------------
def visMF_holdingsFinData(
        start_date,                 # 起始日期，输入格式:datetime.date
        end_date,                   # 结束日期，输入格式:datetime.date
        product_id,                 # product_id基金代码，应为str格式（因数据库存储问题，优先使用场内代码）
        freq='Q',                   # freq为频率，'Q'为季报，'H'为半年和年报
        Top10=False,                # Top10为是否仅取季报前十大持仓
        chrome_path=None,           # the chrome.exe path
        local_path=None,            # the path you would like to save the image
        picture_name=None           # the name of the picture you want to save
):
    df = Anls.anlsMF_getMFHoldingsFinData(start_date, end_date, product_id, freq, Top10)
    df = df.style.format({'eps_quarter': '{:.2f}', 'net_profit_yoy': '{:.2%}', 'total_mv': '{:.0f}', 'floating_mv': '{:.0f}', 'pe_ttm': '{:.2f}', 'pb': '{:.2f}'}).background_gradient(subset=['eps_quarter', 'net_profit_yoy', 'total_mv', 'floating_mv', 'pe_ttm', 'pb'], cmap='Reds', low=0, high=config.cmap_range_adjust_coef)
    if chrome_path is not None and local_path is not None and picture_name is not None:
        local_path = local_path + '/' + picture_name + '.png'
        dfi.export(df, local_path, chrome_path=chrome_path)
        return
    else:
        return df

# ------------------------------------------------
# 基金经理所有产品历史业绩
# sync = True 则同步输出，，只包含距离date成立一年以上的产品。
# 区间：起始日期为展示产品中最晚任职产品的任职日期，结束日期为date
# sync = False 则从最早任职产品开始计算
# ------------------------------------------------
def visMF_allProductNAVofPM(
    fundManager,                    # 基金经理
    fundCompany,                    # 基金公司
    date = datetime.date.today(),   # 日期
    sync = True                     # 是否同步输出，若否，则从第一只产品任职以来画图，若是，从一年以上产品中最后一只任职以来画图
):
    date = wind_getLastTradeDates([date])[0]
    AllProducts = anlsMF_allProductStaticInfoOfPM(fundManager,fundCompany,date)
    if sync:
        startdate = max(AllProducts[AllProducts['manager_startdate']<datetime.date(date.year-1, date.month, date.day)]['manager_startdate'].tolist())
    else:
        startdate = min(AllProducts['manager_startdate'].tolist())
    NavDf = wind_getMFNav(startdate, date, AllProducts['product_id'].tolist())
    NavDfpivot = NavDf.pivot_table(index='date', columns = 'product_name')
    for productName in NavDf['product_name'].unique().tolist():
        NavDfpivot['nav_adjusted'][productName] = NavDfpivot['nav_adjusted'][productName] / \
                                                     NavDfpivot['nav_adjusted'][productName].dropna()[0]
    NavDfpivot['nav_adjusted'].plot()
    plt.title("'{0}'至'{1}'".format(startdate, date))
    plt.show()
    return

# ------------------------------------------------
# 基金经理所有产品历史业绩相关性，只包含距离date成立一年以上的产品。
# 区间：起始日期为展示产品中最晚任职产品的任职日期，结束日期为date
# ------------------------------------------------
def visMF_allProductCorr(
    fundManager,                    # 基金经理
    fundCompany,                    # 基金公司
    date = datetime.date.today()    # 日期
):
    date = wind_getLastTradeDates([date])[0]
    AllProducts = anlsMF_allProductStaticInfoOfPM(fundManager,fundCompany,date)
    startdate = max(AllProducts[AllProducts['manager_startdate']<datetime.date(date.year-1, date.month, date.day)]['manager_startdate'].tolist())
    corr = basicVis_plotCorrelation({'MF': AllProducts['product_id'].tolist()}, 'Custom', 'D', date=date, start_date=startdate)
    return corr

# ------------------------------------------------
# 单只基金前十大持仓
# 包括：市值、流通市值、pe、pb、近60日平均成交额、持仓金额、持仓占净值比、持仓占流通市值比、完全卖出需要天数
# ------------------------------------------------
def visMF_top10stocks(
    product_id,                     # 基金, str
    date                            # 日期，请输入最近一个已出报告的报告日期
):
    date = wind_getLastReportDate(date, Freq= 'Q')
    top10 = wind_getMFStockHoldings([product_id], 'Q', Top10=True)
    portfolio = top10[top10['date'] == date]
    # 行业填充
    industry = wind.wind_getIndustriesMap('CITICS', 1, date)
    portfolio = pd.merge(portfolio, industry, on=['stock_id', 'date'], how='left')
    stockList = portfolio['stock_id'].tolist()
    stockDetails = wind_getAShareDailyValuationIndicators(date, date, stock_ids=stockList)
    portfolio = pd.merge(portfolio, stockDetails, on=['stock_id', 'date'], how='left')
    portfolio = portfolio.rename(columns = {'date': '报告期', 'stock_name':'股票简称', 'total_mv':'市值（亿）', 'floating_mv':'流通市值（亿）', 'trade_amount_60days':'近60交易日平均成交额（亿）',
                                'stk_value':'持仓金额（亿）', 'stk_value_to_nav':'持仓占净值比（%）'})
    portfolio['市值（亿）'] = portfolio['市值（亿）']/1e8
    portfolio['流通市值（亿）'] = portfolio['流通市值（亿）']/1e8
    portfolio['近60交易日平均成交额（亿）'] = portfolio['近60交易日平均成交额（亿）'] / 1e8
    portfolio['持仓金额（亿）'] = portfolio['持仓金额（亿）'] / 1e8
    portfolio['持仓占流通市值比(%)'] = portfolio['持仓金额（亿）'] / portfolio['流通市值（亿）']*100
    portfolio['完全卖出需要天数'] = portfolio['持仓金额（亿）'] / (portfolio['近60交易日平均成交额（亿）']*0.1)
    portfolio['持仓占净值比（%）'] = portfolio['持仓占净值比（%）'] *100
    return portfolio[['报告期', '股票简称','市值（亿）', '流通市值（亿）', 'pe_ttm', 'pb', '近60交易日平均成交额（亿）', '持仓金额（亿）', '持仓占净值比（%）', '持仓占流通市值比(%)', '完全卖出需要天数']]

# ------------------------------------------------
# 公募基金筛选
# ------------------------------------------------
def visMF_univRatingDataFilter(
    as_of_date,
    date_list,
    lookback_num,
    coverage,
    filters # 是list of list的形式，例如：[['rating_6m', 3], ['rating_1y', 3]] 表示6月评分在3星及以上且1年评分3星及以上
):
    rating_data = anlsMF_univRatingDataFilter(as_of_date, date_list, lookback_num, coverage, filters)
    rating_data.sort_values(by=['coverage', 'product_name', 'rating_date'], ascending=False, inplace=True)
    return rating_data

# -------------------------------------------------------------------------------------
# 获取单只FOF公募的基金持仓
# 返回的持仓权重比为实际值，未扩为100%，求和结果是基金标的的总持仓权重
# -------------------------------------------------------------------------------------
def visMF_getWindMFOFFundHoldings(
        date,           # best effort, 寻找该日期前最新的持仓数据
        product_id,     # 公募基金ID
        freq='Q',       # freq为频率，'Q'为季报，'H'为半年和年报
):
    result = wind_getMFOFCurrentFundHoldings(date, product_id, freq)
    result['holding_fund_value_sum'] = result['holding_fund_value'].sum()
    rename_dict = {
        'date': '持仓数据日期',
        'product_name': '名称',
        'holding_fund_value_sum': '持仓基金总规模',
        'holding_fund_id': '产品ID',
        'holding_fund_name': '产品名称',
        'holding_fund_value': '产品规模',
        'holding_fund_value_to_nav': '产品权重',
        'type_name_lv1': 'WIND一级标签',
        'type_name_lv2': 'WIND二级标签',
    }
    result.rename(columns=rename_dict, inplace=True)
    result = result[list(rename_dict.values())]
    formatter = {'持仓基金总规模': '{:,.2f}', '产品规模': '{:,.2f}', '产品权重': '{:.2%}'}
    result = result.style.format(formatter).background_gradient(subset=['产品规模', '产品权重'], cmap='Reds', low=0, high=config.cmap_range_adjust_coef).hide_index()
    return result

# -------------------------------------------------------------------------------------
# 获取单只FOF公募的基金持仓类别汇总
# 返回的持仓权重比为实际值，未扩为100%，求和结果是基金标的的总持仓权重
# -------------------------------------------------------------------------------------
def visMF_getWindMFOFFundHoldingsSector(
        date,           # best effort, 寻找该日期前最新的持仓数据
        product_id,     # 公募基金ID
        freq='Q',       # freq为频率，'Q'为季报，'H'为半年和年报
        level='type_name_lv1'       # 汇总统计level，与wind标签体系一致
):
    assert level in ('allocation_type', 'type_name_lv1', 'type_name_lv2'), "公募FOF持仓汇总统计的维度仅限于type_name_lv1/2和allocation_type"

    value_to_nav_col = 'asset_value_to_nav' if level == 'allocation_type' else 'holding_fund_value_to_nav'
    result = anlsMF_getWindMFOFFundHoldingsSector(date, product_id, freq, level)
    base = alt.Chart(result).mark_arc().encode(
        theta=alt.Theta(value_to_nav_col+':Q', stack=True),
        color=alt.Color(level+':N'),
    )
    pie = base.mark_arc(outerRadius=120)
    text = base.mark_text(radius=140, size=10).encode(text=alt.Text(value_to_nav_col+':Q', format='.2%'))
    table_result = result.copy(deep=True)
    rename_dict = {
        'product_name': '名称',
        'allocation_type': 'WIND大类资产分类',
        'type_name_lv1': 'WIND基金一级标签',
        'type_name_lv2': 'WIND基金二级标签',
        'holding_fund_value': '规模',
        'holding_fund_value_to_nav': '权重',
        'asset_value': '规模',
        'asset_value_to_nav': '权重'
    }
    table_result.rename(columns=rename_dict, inplace=True)
    table_result['规模'] = table_result['规模'].round(2)
    formatter = {'规模': '{:,}', '权重': '{:.2%}'}
    table_result = table_result.style.format(formatter).background_gradient(subset=['规模', '权重'], cmap='Reds', low=0, high=config.cmap_range_adjust_coef).hide_index()
    return {'chart': pie+text, 'table': table_result}

# ---------------------------------------------------------
# 获取公募FOF多头行业穿透
# 可选行业分类 申万中信123级
# 返回：table: 行业比重表; chart: 行业饼状图
# ---------------------------------------------------------
def visMF_getWindMFOFIndustryLookThrough(
    date,                   # 持仓数据日期(筛选最近一期报告的数据)，输入格式:datetime.date
    product_id,
    company='SW',           # 行业分类标准，输入格式:str，'SW' or 'CITICS'
    level=1,                # 行业分类级别，输入格式:int
    top_num=10,             # 前N大行业
    mask_h_shares=True,     # 是否将港股的行业全部置为“港股”，默认为是
):
    result = Anls.anlsMF_getWindMFOFIndustryLookThrough(date, product_id, company, level, top_num, mask_h_shares)
    if result.empty:
        return {'table': result, 'chart': None}
    del result['product_id'], result['equity_total_weight']
    rename_dict = {
        'industry': '行业',
        'industry_weight_in_port': '行业占整体组合比重',
        'industry_weight': '行业占多头比重',
        'product_name': '产品名称',
        'date': '持仓数据日期',
        'holding_fund_value': '持仓基金规模',
        'industry_NAV': '行业规模',
        'industry_level': '行业分类等级',
        'report_date': '行业分类参考报告期'
    }
    industry_level_map = {
        'company': {'SW': '申万', 'CITICS': '中信'},
        'level': {1: '一级', 2: '二级', 3: '三级'}
    }

    top_num_str = "全部行业，" if top_num == 999 else ("前" + str(top_num) + "大行业，")
    title = "行业穿透：展示" + top_num_str + "\n行业分类：" + industry_level_map['company'][company] + industry_level_map['level'][level]
    result.rename(columns=rename_dict, inplace=True)
    result['行业分类等级'] = industry_level_map['company'][company] + industry_level_map['level'][level]

    # table
    table_result = result.copy(deep=True)
    col_list = ['产品名称', '持仓基金规模', '持仓数据日期', '行业分类参考报告期', '行业分类等级', '行业', '行业规模', '行业占整体组合比重', '行业占多头比重']
    table_result = table_result[col_list]
    formatter = {
        '持仓基金规模': '{:,.2f}',
        '行业规模': '{:,.2f}',
        '行业占整体组合比重': '{:.2%}',
        '组合多头比重': '{:.2%}',
        '行业占多头比重': '{:.2%}',
    }
    table_result = table_result.style.format(formatter).background_gradient(subset=['持仓基金规模', '行业规模', '行业占整体组合比重', '行业占多头比重'], cmap='Reds', low=0, high=config.cmap_range_adjust_coef).hide_index()
    table_result = table_result.highlight_null('white')

    # chart
    from src.visualization.portfolioVis import _complex_pie_chart
    chart_result = _complex_pie_chart(result.iloc[:-1][['行业', '行业占多头比重']], title)  # 画饼图时需删去最后一行合计数据

    return {'table': table_result, 'chart': chart_result}