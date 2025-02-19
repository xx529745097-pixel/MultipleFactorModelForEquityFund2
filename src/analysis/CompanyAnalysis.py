# ------------------------------------------------
# 本文档用于基金公司数据分析
# ------------------------------------------------
import src.data.wind as wind
import src.utils.fof_calendar as calendar
import pandas as pd
import numpy as np
import datetime

# ------------------------------------------------
# 基金公司的财务数据汇总
# ------------------------------------------------
def anlsCompany_compFinData(
        companies = None      # 基金公司简称（如易方达基金，东证资管，中信证券），输入格式:list, 为None时，相当于获取全部基金公司信息
):
    df = wind.wind_getMFFinancialInfo(companies=companies)
    df.fillna(0, inplace=True)
    finData = df.groupby(['date', 'company_short_name']).sum().reset_index()
    del finData['management_fee'], finData['trustee_fee']
    finData.sort_values(by=['company_short_name', 'date'], inplace=True)
    if companies == None:
        result= finData
    else:
        result= finData.loc[finData['company_short_name'].isin(companies)]
    result = result.loc[pd.to_datetime(result['date']).dt.year >= 2008] # 08年之前半年度数据不全
    result.reset_index(drop=True, inplace=True)
    result = result.copy()
    result['stock_pnl'] = result['stock_inv_inc'] + result['dvd_inc']+ result['stock_fv_chg'] # 股票端realized和unrealized收益
    result['bond_pnl'] = result['bond_inv_inc'] + result['bond_int_inc'] + result['bond_fv_chg']
    result['fund_pnl'] = result['fund_inv_inc'] + result['fund_fv_chg']
    # 拆分出下半年的数据
    result = result.sort_values(by=['company_short_name', 'date']).reset_index(drop=True)
    result['date'] = pd.to_datetime(result['date'])  # 为了使用df['date'].dt.month
    result.index = result['date']
    col = ['company_short_name', 'management_exp', 'trustee_exp', 'net_profit', 'stock_inv_inc', 'bond_inv_inc', 'fund_inv_inc',
           'bond_int_inc', 'dvd_inc', 'stock_fv_chg', 'fund_fv_chg', 'bond_fv_chg', 'stock_pnl', 'bond_pnl', 'fund_pnl']
    df_diff = result[col].groupby('company_short_name').diff()
    df_diff['date'] = df_diff.index
    col.pop(0) # 删除 company_short_name
    result.loc[result['date'].dt.month == 12, col] = df_diff.loc[df_diff['date'].dt.month == 12, col]
    result['date'] = pd.to_datetime(result['date']).dt.date
    result.reset_index(drop=True, inplace=True)
    return result

# ------------------------------------------------
# 基金公司的财务数据分位数
# ------------------------------------------------
def anlsCompany_compFinDataRanking(
        companies = None      # 基金公司简称（如易方达基金，东证资管，中信证券），输入格式:list, 为None时，相当于获取全部基金公司信息
):
    df = anlsCompany_compFinData()
    df_rank = df.groupby('date').apply(lambda x: x.rank(ascending=True)/len(x))
    df_rank[['date','company_short_name']] = df[['date','company_short_name']]
    if companies == None:
        result = df_rank
    else:
        result = df_rank.loc[df_rank['company_short_name'].isin(companies)].reset_index(drop=True)

    return result

# ------------------------------------------------
# 基金公司持有股票的财务数据，包括盈利能力，估值水平，集中度等
# ------------------------------------------------
def anlsCompany_stockHoldingsFinData(
        companies = None      # 基金公司简称（如易方达基金，东证资管，中信证券），输入格式:list, 为None时，相当于获取全部基金公司信息
):
    df = wind.wind_getMFStockHoldings(freq='H')
    df_findata = wind.wind_getMFAssetAllocation()
    df = pd.merge(df, df_findata[['date', 'product_id', 'net_asset','product_stk_value']], how='left', on=['date', 'product_id'])
    df_holdings = df.groupby(['date', 'company_short_name', 'stock_id', 'stock_name'])[['stk_value', 'stk_quantity_to_compfloat']].sum().reset_index() # 基金公司股票投资汇总
    df_fund = df.drop_duplicates(['date','product_id']).groupby(['date','company_short_name'])[['net_asset', 'product_stk_value']].sum().reset_index() # 基金公司管理规模及股票投资规模
    df_holdings = pd.merge(df_holdings, df_fund, how='left', on=['date','company_short_name'])
    df_holdings['stk_value_to_nav'] = df_holdings['stk_value'] / df_holdings['net_asset']
    df_holdings['stk_value_to_allstk'] = df_holdings['stk_value'] / df_holdings['product_stk_value']
    df_holdings = df_holdings.sort_values(by=['date', 'company_short_name', 'stk_value'],ascending=[True, True, False]).reset_index(drop=True)
    Top10_stock = df_holdings.groupby(['date', 'company_short_name'])['stk_value_to_allstk'].apply(lambda x: x.iloc[:10].sum()) # 前十大股票集中度

    # 行业填充
    industry = wind.wind_getAllHistIndustriesMap('CITICS', 1)
    df_industry = pd.merge(df_holdings, industry, on='stock_id', how='left')
    df_industry = df_industry.loc[(df_industry['date'] >= df_industry['entry_dt']) & (df_industry['date'] <= df_industry['remove_dt'])].reset_index(drop=True)
    del df_industry['entry_dt'], df_industry['remove_dt']  # 新股会在上市前出现在季报里面，当时没有行业分类，上一步会把当时没有分类的股票删掉
    df_industry = df_industry.groupby(['date', 'company_short_name', 'industry'])[['stk_value_to_allstk']].sum().reset_index()
    df_industry = df_industry.sort_values(by=['date', 'company_short_name', 'stk_value_to_allstk'],ascending=[True, True, False]).reset_index(drop=True)
    Top3_industry = df_industry.groupby(['date', 'company_short_name'])['stk_value_to_allstk'].apply(lambda x: x.iloc[:3].sum())  # 前三大行业集中度

    df_stock = wind.wind_getAShareFinancialInfo()
    del df_stock['stock_name']
    df_holdings = pd.merge(df_holdings, df_stock, how='left', on=['date', 'stock_id'])
    df_holdings = df_holdings.sort_values(by=['date', 'company_short_name', 'stk_value'],ascending=[True, True, False]).reset_index(drop=True)
    df_holdings = df_holdings.dropna().reset_index(drop=True) # 删掉没有财务数据的行

    eps_quarter = df_holdings.groupby(['date', 'company_short_name']).apply(lambda x: np.average(x['eps_quarter'], weights=x['stk_value'])).to_frame()
    net_profit_yoy = df_holdings.groupby(['date', 'company_short_name']).apply(lambda x: np.average(x['net_profit_yoy'], weights=x['stk_value'])).to_frame()
    total_mv = df_holdings.groupby(['date', 'company_short_name']).apply(lambda x: np.average(x['total_mv'], weights=x['stk_value'])).to_frame()
    floating_mv = df_holdings.groupby(['date', 'company_short_name']).apply(lambda x: np.average(x['floating_mv'], weights=x['stk_value'])).to_frame()
    pe_ttm = df_holdings.groupby(['date', 'company_short_name']).apply(lambda x: np.average(x['pe_ttm'], weights=x['stk_value'])).to_frame()
    pb = df_holdings.groupby(['date', 'company_short_name']).apply(lambda x: np.average(x['pb'], weights=x['stk_value'])).to_frame()
    result = pd.concat([eps_quarter, net_profit_yoy, total_mv, floating_mv, pe_ttm, pb, Top10_stock, Top3_industry], axis=1)
    # 新加指标时注意对应添加列名
    result.columns = ['eps_quarter', 'net_profit_yoy', 'total_mv', 'floating_mv', 'pe_ttm', 'pb', 'Top10_stock', 'Top3_industry']
    result.reset_index(inplace=True)
    result['date'] = pd.to_datetime(result['date']).dt.date
    if companies == None:
        return result
    else:
        result = result.loc[result['company_short_name'].isin(companies)].reset_index(drop=True)
        return result

# ------------------------------------------------
# 基金公司的持股特点，包括盈利能力，估值水平，集中度等
# ------------------------------------------------
def anlsCompany_stockHoldingsFinDataRanking(
        companies = None      # 基金公司简称（如易方达基金，东证资管，中信证券），输入格式:list, 为None时，相当于获取全部基金公司信息
):
    df = anlsCompany_stockHoldingsFinData()
    df_rank = df.groupby('date').apply(lambda x: x.rank(ascending=True) / len(x))
    df_rank[['date', 'company_short_name']] = df[['date', 'company_short_name']]
    if companies == None:
        result = df_rank
    else:
        result = df_rank.loc[df_rank['company_short_name'].isin(companies)].reset_index(drop=True)
    return result

# ------------------------------------------------
# 基金公司分类型管理规模
# ------------------------------------------------
def anlsCompany_compAUM(
        companies = None,      # 基金公司简称（如易方达基金，东证资管，中信证券），输入格式:list, 为None时，相当于获取全部基金公司信息
        type_level = 1         # 基金类型分类，只有1和2两个选项
):
    df = wind.wind_getMFAssetAllocation(companies=companies)[['date', 'company_short_name', 'net_asset','type_name_lv1','type_name_lv2']]
    df['net_asset'] /= 1e8
    if type_level == 1:
        result = df.groupby(['date', 'company_short_name', 'type_name_lv1'])[['net_asset']].sum().reset_index()
    else:
        result = df.groupby(['date', 'company_short_name', 'type_name_lv2'])[['net_asset']].sum().reset_index()
    df_calendar = calendar.calendar_getLastDay('Q')
    result = result.loc[result['date'].isin(df_calendar['date'])].reset_index(drop=True) # 只选择季末数据
    return result

# ------------------------------------------------
# 基金公司分类型管理规模排名
# ------------------------------------------------
def anlsCompany_compAUMRanking(
        companies=None,  # 基金公司简称（如易方达基金，东证资管，中信证券），输入格式:list, 为None时，相当于获取全部基金公司信息
        type_level=1  # 基金类型分类，只有1和2两个选项
):
    df = anlsCompany_compAUM(None, type_level)
    typeDict = {
        1 : 'type_name_lv1',
        2 : 'type_name_lv2'
    }
    df = df.sort_values(by=['date', typeDict[type_level], 'net_asset']).reset_index(drop=True)
    df_rank = df.groupby(['date', typeDict[type_level]]).apply(lambda x: x.rank(ascending=False)).rename(columns={'net_asset':'rank'})
    df_rank[['date', typeDict[type_level], 'company_short_name']] = df[['date', typeDict[type_level], 'company_short_name']]
    df_num = df.groupby(['date', typeDict[type_level]]).apply(lambda x: len(x)).reset_index().rename(columns={0: 'num'})
    df_rank = pd.merge(df_rank, df_num, on=['date', typeDict[type_level]], how='left')

    if companies == None:
        result = df_rank
    else:
        result = df_rank.loc[df_rank['company_short_name'].isin(companies)].reset_index(drop=True)
    return result

# ------------------------------------------------
# 获取基金公司最新股东列表及对应的持股比例
# ------------------------------------------------
def anlsCompany_getMFCurrentStakeHolder(
        companies=None,  # 基金公司简称（如易方达基金，东证资管，中信证券），输入格式:list, 为None时，相当于获取全部基金公司信息
):
    df = wind.wind_getMFCurrentStakeHolder(companies)
    df_latest = df.loc[df['date'] == df['date'].max()].reset_index(drop=True)  # 最新报告期
    del df_latest['company_id'], df_latest['company_name']
    df_latest = df_latest.sort_values(by=['company_short_name', 'holder_pct'], ascending=False).reset_index(drop=True)
    return df_latest

# ------------------------------------------------------
# 基于新股询价数据计算基金公司的管理规模下限，量化私募效果最好
# ------------------------------------------------------
def anlsCompany_getCompanyAUMLBfromIPOStats(
    company_short_name,  # e.g. ['衍复']，输入的公司名字最好有唯一性，不然可能影响结果
    start_date,
    end_date = datetime.date.today()
):
    ipostats = wind.wind_getIPOInquiryDetails(start_date, end_date)
    ipostats['aum'] = ipostats['bid_price'] * ipostats['bid_quantity']
    ipostats['aum'] /= 1e8 # 单位亿元
    uplimit_quantity = ipostats.groupby(['stock_id'], as_index=False)['bid_quantity'].max().rename(columns={'bid_quantity': 'uplimit_quantity'})
    ipostats = pd.merge(ipostats, uplimit_quantity, how='left', on=['stock_id'])
    ipostats['is_uplimit'] = ipostats['bid_quantity'] == ipostats['uplimit_quantity']
    ipostats['year'] = pd.to_datetime(ipostats['date']).dt.year
    ipostats['month'] = pd.to_datetime(ipostats['date']).dt.month
    result = pd.DataFrame()
    for fund_name in company_short_name:
        df_fund = ipostats.loc[ipostats['company_full_name'].str.contains(fund_name)].reset_index(drop=True)
        if len(df_fund) > 0:
            df_fund_max = df_fund.groupby(['year', 'month', 'product_full_name', 'is_uplimit'], as_index=False)['aum'].max()
            df_fund_max = df_fund_max.sort_values(['year', 'month', 'product_full_name', 'aum'], ascending=False).reset_index(drop=True)
            df_fund_max = df_fund_max.drop_duplicates(['year', 'month', 'product_full_name'], keep='first').reset_index(drop=True)

            nav_fund = df_fund_max.groupby(['year', 'month'], as_index=False)['aum'].sum()
            uplimit_count = df_fund_max.groupby(['year', 'month'], as_index=False)['is_uplimit'].sum()
            all_count = df_fund_max.groupby(['year', 'month'], as_index=False)['is_uplimit'].count().rename(columns={'is_uplimit': 'product_num'})

            nav_fund = pd.merge(nav_fund, uplimit_count, how='left', on=['year', 'month'])
            nav_fund = pd.merge(nav_fund, all_count, how='left', on=['year', 'month'])
            nav_fund['company_name'] = fund_name
            nav_fund['date'] = nav_fund.apply(lambda x: datetime.date(x['year'],x['month'],28), axis=1)
            del nav_fund['year'], nav_fund['month']
            nav_fund['confidence'] = 1 - nav_fund['is_uplimit']/nav_fund['product_num']
            result = result.append(nav_fund)
    return result