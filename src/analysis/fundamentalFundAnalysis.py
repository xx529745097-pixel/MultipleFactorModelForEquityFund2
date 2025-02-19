# -----------------------------------------------------------------------
# 主观多头私募分析
# -----------------------------------------------------------------------

import pandas as pd
import numpy as np
import datetime
from src.data.fundamentalFundData import *
from src.analysis.basicAnalysis import *
from src.data.wind import *
from src.const import *
import src.config as config
import src.data.barra as barra

# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# 1. 单一产品分析函数
# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------

# ------------------------------------------------------
# 某一产品的前N大行业
# 可分别看A股和港股的前N大行业，或将A股港股行业合并来看
# 占资产净值比
# ------------------------------------------------------
def ffa_fundaTopNIndustryTS(
    product_id,          # e.g. 'SQV392.OF'
    start_date,          # datetime.date
    end_date,
    N = 5,               # 前N大行业
    AH = 'AH'            # 'AH'代表A股港股合并在一起看，'A'代表只看A股行业，'H’代表只看港股行业
):
    assert AH in ('AH', 'A', 'H'), "目前只支持'AH, 'A', 'H'"
    df = ffd_getFundamentalFundsExposure(start_date, end_date, [product_id])
    sw_industry = pd.DataFrame({'chinese': const.SW_INDUSTRY_NAME_CN_TO_EN.keys(),
                                'english': const.SW_INDUSTRY_NAME_CN_TO_EN.values()})
    hk_industry = pd.DataFrame({'chinese': const.HK_INDUSTRY_NAME_CN_TO_EN.keys(),
                                'english': const.HK_INDUSTRY_NAME_CN_TO_EN.values()})
    col_list = ['date', 'a_stock', 'hk_stock'] + list(sw_industry['english']) + list(hk_industry['english'])
    df = df[col_list]
    df[hk_industry['english']] = df[hk_industry['english']].multiply(df['hk_stock'], axis='index')
    df[sw_industry['english']] = df[sw_industry['english']].multiply(df['a_stock'], axis='index')
    del df['a_stock'], df['hk_stock']
    AH_dict = {
        'AH': list(sw_industry['english']) + list(hk_industry['english']),
        'A': list(sw_industry['english']),
        'H': list(hk_industry['english'])
    }
    melted = pd.melt(df, id_vars='date',
                     value_vars=AH_dict[AH]).rename(
        columns={'variable': 'industry', 'value': 'weight'})
    melted = melted.sort_values(['date', 'weight'], ascending=[True, False]).reset_index(drop=True)
    result = melted.groupby('date', as_index=False).apply(lambda x: x[:N]).reset_index(drop=True)
    return result

# ------------------------------------------------------
# 某一产品的前N大行业集中度时序
# 把A股行业和港股行业合在一起，计算前N大行业的占资产净值比
# ------------------------------------------------------
def ffa_fundaFundTopNIndustryCRTS(
    product_id,          # e.g. 'SQV392.OF'
    start_date,          # datetime.date
    end_date,
    N = 3,               # 前N大行业
    AH = 'AH'            # 'AH'代表A股港股合并在一起看，'A'代表只看A股行业，'H’代表只看港股行业
):
    melted = ffa_fundaTopNIndustryTS(product_id, start_date, end_date, N, AH)
    result = melted.groupby('date', as_index=False)['weight'].sum()
    return result

# ------------------------------------------------------
# 某一产品的AH仓位/行业变化截面图
# ------------------------------------------------------
def ffa_fundaFundPositionIndustryChg(
    product_id,          # e.g. 'SQV392.OF'
    date1,               # datetime.date 开始时点
    date2,               # 结束时点
    AH = 'AH',           # A股，港股
    industry = True,     # True 看行业，False看仓位
    threshhold = 0.05    # 阈值
):
    if industry:
        df1 = ffa_fundaTopNIndustryTS(product_id, date1, date1, 200, AH).rename(columns={'weight':'weight_start'})
        df2 = ffa_fundaTopNIndustryTS(product_id, date2, date2, 200, AH).rename(columns={'weight':'weight_end'})
        df = pd.merge(df1[['industry', 'weight_start']], df2[['industry', 'weight_end']], how='left', on='industry')
        sw_ret = wind_getIndustryReturn(date1, date2, 'SW')
        hs_ret = wind_getIndustryReturn(date1, date2, 'HS')
        industry_ret = sw_ret.append(hs_ret).reset_index(drop=True)
        df = pd.merge(df, industry_ret, how='left', on='industry')
        df['return'].fillna(0, inplace=True)
        df['weight_change'] = df['weight_end'] - (df['weight_start'] * (1+df['return']))
        df = df.loc[abs(df['weight_change']) >= threshhold].reset_index(drop=True)
        del df['return']
    else:
        assert AH == 'AH', "选择看仓位时默认只看AH净仓位，AH必须等于'AH'"
        df1 = ffd_getFundamentalFundsExposure(date1, date1, [product_id])[['net_stock']].rename(columns={'net_stock' :'net_stock_start'})
        df2 = ffd_getFundamentalFundsExposure(date2, date2, [product_id])[['net_stock']].rename(columns={'net_stock' :'net_stock_end'})
        df = pd.concat([df1['net_stock_start'], df2['net_stock_end']], axis=1)
        mkt_index = wind_getIndexData('885001.WI', date1, date2, 'D').sort_values('date')
        mkt_ret = mkt_index['close_price'].iat[-1] / mkt_index['close_price'].iat[0] - 1
        df['net_stock_chg'] = df2['net_stock_end'] - (df1['net_stock_start'] * (1 + mkt_ret))

    return df

# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# 2. 全部多头产品合并分析
# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------

# ------------------------------------------------------
# 全部多头产品某一时点的仓位stats 平均、中位数、最高、最低
# 仓位分全部仓位、A股仓位和港股仓位
# ------------------------------------------------------
def ffa_fundaFundAllProductsPositionDistribution(
    date,              # datetime.date
    AH = 'AH'          # 'AH'代表全部仓位, 'A'代表A股仓位, 'H'代表港股仓位
):
    df = ffd_getFundamentalFundsExposure(date, date)[['product_id', 'net_stock', 'a_stock', 'hk_stock']]
    # FIXME 加入数据过滤逻辑，筛去net_stock>150%的产品，主要剔除国债期货异动的影响
    df = df[df['net_stock']<1.5]
    AH_dict = {
        'AH': 'net_stock',
        'A' : 'a_stock',
        'H' : 'hk_stock'
    }
    result = df[AH_dict[AH]].apply({'mean':np.mean, 'median': np.median, 'max': np.max, 'min': np.min}).to_frame().T.reset_index(drop=True)
    result['date'] = date
    result['position'] = AH
    return result

# ------------------------------------------------------
# 全部多头产品的加仓减仓持平管理人个数
# 仓位分全部仓位、A股仓位和港股仓位
# ------------------------------------------------------
def ffa_fundaFundAllProductsPositionChgCount(
    date1,                       # datetime.date
    date2,
    AH = 'AH',                   # 'AH'代表全部仓位, 'A'代表A股仓位, 'H'代表港股仓位
    threshhold = 0.05            # 阈值，评判是否加减仓的值
):
    AH_dict = {
        'AH': 'net_stock',
        'A': 'a_stock',
        'H': 'hk_stock'
    }
    benchmark_dict = {
        'AH': '885001.WI',
        'A': '881001.WI',
        'H': 'HSI.HI'
    }
    df1 = ffd_getFundamentalFundsExposure(date1, date1)[['product_id', AH_dict[AH]]].rename(columns={AH_dict[AH]: 'weight_start'})
    df2 = ffd_getFundamentalFundsExposure(date2, date2)[['product_id', AH_dict[AH]]].rename(columns={AH_dict[AH]: 'weight_end'})
    if AH == 'AH':
        # FIXME 加入数据过滤逻辑，筛去net_stock>150%的产品，主要剔除国债期货异动的影响
        df1 = df1[df1['weight_start'] < 1.5]
        df2 = df2[df2['weight_end'] < 1.5]
    df = pd.merge(df1, df2, how='left', on='product_id').fillna(0) # 如果产品是date2新加入的，date1没有该产品，需要fillna
    mkt_index = wind_getIndexData(benchmark_dict[AH], date1, date2, 'D').sort_values('date')
    mkt_ret = mkt_index['close_price'].iat[-1] / mkt_index['close_price'].iat[0] - 1
    df['change'] = df['weight_end'] - (df['weight_start'] * (1 + mkt_ret))
    df['chg'] = np.where(df['change'] >= threshhold, '加仓', np.where(df['change'] <= -threshhold, '减仓', '基本持平'))
    df_count = df.groupby('chg', as_index=False)['product_id'].count().rename(columns={'product_id': 'product_count'})
    df_value = df.groupby('chg', as_index=False)['change'].mean().rename(columns={'change': 'avg_change'})
    result = pd.merge(df_count, df_value, how='left', on='chg')
    result['start_date'] = date1
    result['end_date'] = date2
    result['position'] = AH
    return result

# ------------------------------------------------------
# 全部多头产品仓位Chg Stats
# 仓位分全部仓位、A股仓位和港股仓位
# ------------------------------------------------------
def ffa_fundaFundAllProductsPositionChgStats(
    date1,                      # datetime.date
    date2,
    AH = 'AH',                  # 'AH'代表全部仓位, 'A'代表A股仓位, 'H'代表港股仓位
):
    stats1 = ffa_fundaFundAllProductsPositionDistribution(date1, AH)
    stats2 = ffa_fundaFundAllProductsPositionDistribution(date2, AH)
    stats = stats1.append(stats2)

    return stats

# ------------------------------------------------------
# 全部多头产品仓位detail
# ------------------------------------------------------
def ffa_fundaFundAllProductsPositionWRank(
    date                # datetime.date
):
    level_info = custHF.custHF_getProductInfo()
    id_to_name = level_info.set_index('product_id')['product_short_name'].to_dict()
    df = ffd_getFundamentalFundsExposure(date, date)[['product_id', 'net_stock', 'a_stock', 'hk_stock']].rename(columns={'product_id':'product_name'})
    df['product_name'].replace(id_to_name, inplace=True)
    df['net_stock_rank'] = df['net_stock'].rank(ascending=False)
    df['a_stock_rank'] = df['a_stock'].rank(ascending=False)
    df['hk_stock_rank'] = df['hk_stock'].rank(ascending=False)
    df = df[['product_name', 'net_stock', 'net_stock_rank', 'a_stock', 'a_stock_rank', 'hk_stock', 'hk_stock_rank']]
    df = df.sort_values('net_stock', ascending=False).reset_index(drop=True)
    return df

# ------------------------------------------------------
# 全部多头产品仓位变化
# ------------------------------------------------------
def ffa_fundaFundAllProductsPositionChgDetails(
    date1,          # datetime.date
    date2
):
    level_info = custHF.custHF_getProductInfo()
    id_to_name = level_info.set_index('product_id')['product_short_name'].to_dict()
    df1 = ffd_getFundamentalFundsExposure(date1, date1)[['product_id', 'net_stock', 'a_stock', 'hk_stock']].rename(columns={'net_stock':'net_stock_start','a_stock':'a_stock_start','hk_stock':'hk_stock_start'})
    df2 = ffd_getFundamentalFundsExposure(date2, date2)[['product_id', 'net_stock', 'a_stock', 'hk_stock']].rename(columns={'net_stock':'net_stock_end','a_stock':'a_stock_end','hk_stock':'hk_stock_end'})
    df = pd.merge(df1, df2, how='left', on='product_id').rename(columns={'product_id': 'product_name'}).fillna(0)  # 如果产品是date2新加入的，date1没有该产品，需要fillna
    df['product_name'].replace(id_to_name, inplace=True)
    AH_index = wind_getIndexData('885001.WI', date1, date2, 'D').sort_values('date')
    AH_ret = AH_index['close_price'].iat[-1] / AH_index['close_price'].iat[0] - 1
    A_index = wind_getIndexData('881001.WI', date1, date2, 'D').sort_values('date')
    A_ret = A_index['close_price'].iat[-1] / A_index['close_price'].iat[0] - 1
    H_index = wind_getIndexData('HSI.HI', date1, date2, 'D').sort_values('date')
    H_ret = H_index['close_price'].iat[-1] / H_index['close_price'].iat[0] - 1
    df['net_stock_chg'] = df['net_stock_end'] - (df['net_stock_start'] * (1 + AH_ret))
    df['a_stock_chg'] = df['a_stock_end'] - (df['a_stock_start'] * (1 + A_ret))
    df['hk_stock_chg'] = df['hk_stock_end'] - (df['hk_stock_start'] * (1 + H_ret))
    df['net_stock_chg_rank'] = df['net_stock_chg'].rank(ascending=False)
    df['a_stock_chg_rank'] = df['a_stock_chg'].rank(ascending=False)
    df['hk_stock_chg_rank'] = df['hk_stock_chg'].rank(ascending=False)
    df = df[['product_name', 'net_stock_chg', 'net_stock_chg_rank', 'a_stock_chg', 'a_stock_chg_rank', 'hk_stock_chg', 'hk_stock_chg_rank']]
    df = df.sort_values('net_stock_chg', ascending=False).reset_index(drop=True)
    return df

# ------------------------------------------------------
# 全部多头产品仓位相对于历史中枢仓位的变化情况
# ------------------------------------------------------
def ffa_fundaFundAllProductsPositionChgVSHistoryMedian(
    date,               # datetime.date，最新数据日期
    AH='AH',            # 'AH'代表全部仓位, 'A'代表A股仓位, 'H'代表港股仓位
    look_back_weeks=4   # 回看周数，默认回看4周
):
    assert AH in ('AH', 'A', 'H'), "目前只支持'AH, 'A', 'H'"
    AH_dict = {
        'AH': 'net_stock',
        'A' : 'a_stock',
        'H' : 'hk_stock'
    }
    AH_name = {
        'AH': '净仓位',
        'A' : 'A股仓位',
        'H' : '港股仓位'
    }
    # 基础数据处理
    level_info = custHF.custHF_getProductInfo()
    id_to_name = level_info.set_index('product_id')['product_short_name'].to_dict()
    ff_data = ffd_getFundamentalFundsExposure(datetime.date(2015,1,1), date)[['date', 'product_id', 'net_stock', 'a_stock', 'hk_stock']]
    product_ids = ff_data[ff_data['date'] == ff_data['date'].max()]['product_id'].tolist()
    product_ids = list(set(product_ids) - set(config.ff_product_exclude_label.keys()))
    ff_data = ff_data[ff_data['product_id'].isin(product_ids)]
    ff_data['product_name'] = ff_data['product_id'].apply(lambda x: id_to_name.get(x,''))
    # 将net_stock,a_stock,hk_stock为0的数据设置为nan，汇总统计时不产生影响
    ff_data[['net_stock', 'a_stock', 'hk_stock']] = ff_data[['net_stock', 'a_stock', 'hk_stock']].replace(0, np.nan)
    # 筛选出周度每周五日期
    date_list = ff_data.loc[ff_data['date'].apply(lambda x: x.weekday())==4, 'date'].sort_values(ascending=False).unique()

    # 历史分布计算
    ff_data_median = ff_data.groupby('product_id')[AH_dict[AH]].median().to_dict()
    result = ff_data[ff_data['date']==date_list[0]][['date','product_id', 'product_name', AH_dict[AH]]]
    result['AH'] = AH_name[AH]
    result['history_median'] = result['product_id'].apply(lambda x: ff_data_median.get(x, 0))
    result = result[['date', 'product_id', 'product_name', 'AH', 'history_median', AH_dict[AH]]].rename(columns={AH_dict[AH]: str(date_list[0])+'_position'})
    result[str(date_list[0])+'_position_diff'] = result[str(date_list[0])+'_position'] - result['history_median']
    for date in date_list[1:look_back_weeks+1]:
        single_date_data = ff_data[ff_data['date'] == date]
        result = pd.merge(result, single_date_data[['product_id', AH_dict[AH]]].rename(columns={AH_dict[AH]: str(date)+'_position'}), on='product_id', how='left')
        result[str(date) + '_position_diff'] = result[str(date) + '_position'] - result['history_median']
    return result

# ------------------------------------------------------
# 全部多头产品前N大行业detail
# ------------------------------------------------------
def ffa_fundaFundAllProductsTopIndustryDetails(
    date,         # datetime.date
    AH = 'AH',    # 'AH' A股港股行业合并计算，'A' 只看A股行业，'H'只看港股行业
    N = 3         # 前N大行业
):
    assert AH in ('AH', 'A', 'H'), "目前只支持'AH, 'A', 'H'"
    level_info = custHF.custHF_getProductInfo()
    id_to_name = level_info.set_index('product_id')['product_short_name'].to_dict()
    df = ffd_getFundamentalFundsExposure(date, date).rename(columns={'product_id': 'product_name'})
    df['product_name'].replace(id_to_name, inplace=True)
    sw_industry = pd.DataFrame({'chinese': const.SW_INDUSTRY_NAME_CN_TO_EN.keys(),
                                'english': const.SW_INDUSTRY_NAME_CN_TO_EN.values()})
    hk_industry = pd.DataFrame({'chinese': const.HK_INDUSTRY_NAME_CN_TO_EN.keys(),
                                'english': const.HK_INDUSTRY_NAME_CN_TO_EN.values()})
    col_list = ['date','product_name', 'a_stock', 'hk_stock'] + list(sw_industry['english']) + list(hk_industry['english'])
    df = df[col_list]
    df[hk_industry['english']] = df[hk_industry['english']].multiply(df['hk_stock'], axis='index')
    df[sw_industry['english']] = df[sw_industry['english']].multiply(df['a_stock'], axis='index')
    del df['a_stock'], df['hk_stock'], df['date']
    AH_dict = {
        'AH': list(sw_industry['english']) + list(hk_industry['english']),
        'A': list(sw_industry['english']),
        'H': list(hk_industry['english'])
    }
    melted = pd.melt(df, id_vars='product_name',value_vars=AH_dict[AH]).rename(columns={'variable': 'industry', 'value': 'weight'})
    melted = melted.sort_values(['product_name', 'weight'], ascending=[True, False]).reset_index(drop=True)
    result = melted.groupby('product_name', as_index=False).apply(lambda x: x[:N]).reset_index(drop=True)
    return result

# ------------------------------------------------------
# 获取多个多头私募行业占比数据，行业转为中文
# 默认取日期区间内最新的行业占比，默认使用原始权益权重，不张成100%
# ------------------------------------------------------
def ffa_getListedFundaFundIndustryWeightDetails(
    report_date,            # 参考报告的截至日期，输入格式:datetime.date
    product_id,             # product_id基金代码，应为list格式（因数据库存储问题，优先使用场内代码）
    AH='AH',                # 'AH' A股港股行业合并计算，'A' 只看A股行业，'H'只看港股行业
    mask_h_shares=True,     # 是否将港股的行业全部置为“港股”，默认为是
    expand_weight=False,    # 是否将单只基金的行业比例之和张成100%，默认为否；对基金单独分析时可张成100%，对FOF组合分析时此步骤为
):
    assert AH in ('AH', 'A', 'H'), "目前只支持'AH, 'A', 'H'"
    start_date = report_date - datetime.timedelta(30)  # 先选取近一个月的exposure内容，再取最近一期
    df = ffd_getFundamentalFundsExposure(start_date, report_date, product_id)
    if df.empty:
        return pd.DataFrame()
    # 取最新一期报告结果
    df = df[df['date'] == df['date'].max()]
    sw_industry = pd.DataFrame({'chinese': const.SW_INDUSTRY_NAME_CN_TO_EN.keys(),
                                'english': const.SW_INDUSTRY_NAME_CN_TO_EN.values()})
    hk_industry = pd.DataFrame({'chinese': const.HK_INDUSTRY_NAME_CN_TO_EN.keys(),
                                'english': const.HK_INDUSTRY_NAME_CN_TO_EN.values()})
    col_list = ['date','product_id', 'a_stock', 'hk_stock', 'net_stock'] + list(sw_industry['english']) + list(hk_industry['english'])
    df = df[col_list]
    df[hk_industry['english']] = df[hk_industry['english']].multiply(df['hk_stock'], axis='index')
    df[sw_industry['english']] = df[sw_industry['english']].multiply(df['a_stock'], axis='index')
    del df['a_stock'], df['hk_stock']
    if mask_h_shares:
        df['hk'] = df[list(hk_industry['english'])].sum(axis=1)
        AH = 'AmaskedH'
    AH_dict = {
        'AH': list(sw_industry['english']) + list(hk_industry['english']),
        'A': list(sw_industry['english']),
        'H': list(hk_industry['english']),
        'AmaskedH': list(sw_industry['english']) + ['hk']
    }
    melted = pd.melt(df, id_vars='product_id',value_vars=AH_dict[AH]).rename(columns={'variable': 'industry', 'value': 'industry_weight'})
    result = melted.sort_values(['product_id', 'industry_weight'], ascending=[True, False]).reset_index(drop=True)
    dict_industry = dict(zip(sw_industry['english'].append(hk_industry['english']),sw_industry['chinese'].append(hk_industry['chinese'])))
    dict_industry.update({'hk': '港股'})
    result.replace({'industry': dict_industry}, inplace=True)
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
# 全部多头产品前N大行业变化detail
# ------------------------------------------------------
def ffa_fundaFundAllProductsTopIndustryChgDetails(
    date1,           # datetime.date
    date2,
    AH = 'AH',       # 'AH' A股港股行业合并计算，'A' 只看A股行业，'H'只看港股行业
    N = 3,           # 前N大行业
    add_pos = True   # True是加仓，False是减仓
):
    df1 = ffa_fundaFundAllProductsTopIndustryDetails(date1, AH, 100).rename(columns={'weight': 'weight_start'})
    df2 = ffa_fundaFundAllProductsTopIndustryDetails(date2, AH, 100).rename(columns={'weight': 'weight_end'})
    df = pd.merge(df1, df2, how='left', on=['product_name', 'industry']).fillna(0)# 如果产品是date2新加入的，date1没有该产品，需要fillna
    sw_ret = wind_getIndustryReturn(date1, date2, 'SW')
    hs_ret = wind_getIndustryReturn(date1, date2, 'HS')
    industry_ret = sw_ret.append(hs_ret).reset_index(drop=True)
    df = pd.merge(df, industry_ret, how='left', on='industry')
    df['return'].fillna(0, inplace=True)
    df['weight_change'] = df['weight_end'] - (df['weight_start'] * (1 + df['return']))
    del df['return']
    if add_pos:
        df = df.sort_values(by=['product_name', 'weight_change'], ascending=[True, False]).reset_index(drop=True)
    else:
        df = df.sort_values(by=['product_name', 'weight_change'], ascending=[True, True]).reset_index(drop=True)
    result = df.groupby('product_name', as_index=False).apply(lambda x: x[:N]).reset_index(drop=True)
    del result['weight_end'], result['weight_start']
    return result

# ------------------------------------------------------
# 全部多头产品行业汇总
# 每个行业有多少管理人持有，持有的管理人平均持仓是多少
# ------------------------------------------------------
def ffa_fundaFundAllProductsIndustryNumbyManager(
    date,       # datetime.date
    AH = 'A',    # 'AH' A股港股行业合并计算，'A' 只看A股行业，'H'只看港股行业
    global_mode=False,  # 全局模式，默认关闭，只对比持有该行业产品的仓位均值变化；打开全局模式后，取所有跟踪产品的整体均值进行对比
):
    df = ffa_fundaFundAllProductsTopIndustryDetails(date, AH, 100)
    if not global_mode:
        df = df.loc[df['weight'] > 0].reset_index(drop=True)
    count = df.groupby(['industry'], as_index=False)['weight'].count().rename(columns={'weight':'count'})
    mean = df.groupby(['industry'], as_index=False)['weight'].mean().rename(columns={'weight':'mean'})
    result = pd.merge(mean, count, how='left', on='industry')
    return result

# ------------------------------------------------------
# 全部多头产品行业变化汇总
# ------------------------------------------------------
def ffa_fundaFundAllProductsIndustryChgbyManager(
    date1,      # datetime.date
    date2,
    AH = 'AH',   # 'AH' A股港股行业合并计算，'A' 只看A股行业，'H'只看港股行业
    global_mode=False,  # 全局模式，默认关闭，只对比持有该行业产品的仓位均值变化；打开全局模式后，取所有跟踪产品的整体均值进行对比
):
    df1 = ffa_fundaFundAllProductsIndustryNumbyManager(date1, AH, global_mode).rename(columns={'count':'count_start', 'mean':'mean_start'})
    df2 = ffa_fundaFundAllProductsIndustryNumbyManager(date2, AH, global_mode).rename(columns={'count':'count_end', 'mean':'mean_end'})
    result = pd.merge(df1, df2, how='left', on='industry').fillna(0)# 如果产品是date2新加入的，date1没有该产品，需要fillna
    result['count_change'] = result['count_end'] - result['count_start']
    result['mean_change'] = result['mean_end'] - result['mean_start']
    result = result[['industry','mean_start','mean_end','mean_change','count_start','count_end','count_change']]
    result = result.sort_values('mean_end', ascending=False).reset_index(drop=True)
    return result

# ------------------------------------------------------
# 获取所有产品的行业或Barra原始数据
# ------------------------------------------------------
def ffa_fundaFundDataFromCustodian(
    start_date,
    end_date,
    data_type='INDUSTRY',   # 输出的数据类型，目前支持行业权重或者Barra
    excess_bm='ZERO_BM',    # Barra暴露是否计算超额及其使用哪个基准
):
    assert data_type in ('INDUSTRY', 'BARRA'), "取数类型仅支持行业数据和Barra"
    if data_type == 'INDUSTRY':
        assert excess_bm == 'ZERO_BM', "行业数据暂不支持输出超额"
    else:
        assert excess_bm in ("ZERO_BM", "HS300", "ZZ100", "ZZ500", "ZZ800", "ZZ1000"), "目前只支持ZERO_BM，沪深300，中证100， 中证500， 中证800， 中证1000"
    exp = ffd_getFundamentalFundsExposure(start_date, end_date)
    level_info = custHF.custHF_getProductInfo()
    barra_factor_list = [s.lower() for s in const.BARRA_STYLE_FACTOR]
    exp = exp.merge(level_info[['product_id', 'product_short_name', 'label_level_1', 'label_level_2']], how='left', on='product_id')
    if excess_bm != 'ZERO_BM':  # 如果不是用零基准做bm
        index_data = barra.barra_readIndexBarraFactorExposure(start_date=start_date, end_date=end_date, index_codes=[excess_bm])
        index_data = index_data[index_data['date'].isin(exp['date'].to_list())]
        exp = pd.merge(exp, index_data, left_on='date', right_on='date', how='left')
        for factor in barra_factor_list:
            exp[factor + '_excess'] = exp[factor + '_x'] - exp[factor + '_y']
            del exp[factor + '_x'], exp[factor + '_y']
        barra_factor_list = ['index_code'] + [s+'_excess' for s in barra_factor_list]
    to_project = ['date', 'product_id', 'product_short_name', 'label_level_1', 'label_level_2'] + (barra_factor_list if data_type == 'BARRA'
                else ['net_stock', 'a_stock', 'hk_stock'] + list(const.SW_INDUSTRY_NAME_CN_TO_EN.values()) + list(const.HK_INDUSTRY_NAME_CN_TO_EN.values()))
    exp = exp[to_project]
    sw_map = dict(zip(const.SW_INDUSTRY_NAME_CN_TO_EN.values(), const.SW_INDUSTRY_NAME_CN_TO_EN.keys()))
    hk_map = dict(zip(const.HK_INDUSTRY_NAME_CN_TO_EN.values(), const.HK_INDUSTRY_NAME_CN_TO_EN.keys()))
    exp.rename(columns=sw_map, inplace=True)
    exp.rename(columns=hk_map, inplace=True)
    exp.rename(columns={'date': '日期', 'product_id': '产品ID', 'product_short_name': '产品名称', 'index_code': '基准指数', 'label_level_1': '一级标签',
                        'label_level_2': '二级标签', 'net_stock': '净仓位', 'a_stock': 'A股仓位', 'hk_stock': '港股仓位'}, inplace=True)
    return exp

# ------------------------------------------------------
# 获取所有私募多头的公司/策略/产品等信息
# ------------------------------------------------------
def ffa_AllCompanyDiscription(
        date         # 日期，用于从托管数据中提取产品规模，一般为周五
):
    company_info = custHF.custHF_getCompanyInfo(company_category = '私募', company_status='在库已投')
    company_info = company_info[['company_id', 'company_short_name', 'library_type','company_aum']]
    strategy_info = custHF.custHF_getStrategyInfo(strategy_status=['在库已投'], strategy_level_1=['主观权益'])
    strategy_info = strategy_info[['strategy_id', 'company_id', 'strategy_name', 'strategy_rating', 'label_level_2', 'primary_coverage']]
    product_info = custHF.custHF_getProductInfo(product_status=['在库已投'], strategy_level_1=['主观权益'])
    product_info = product_info[['strategy_id', 'product_id', 'product_short_name','product_open_status', 'product_aum']]
    product_aum = ffd_getFundamentalFundsExposure(date,date)[['product_id','net_asset_val']]
    product_aum['net_asset_val'] /= 1e8
    product_info = pd.merge(product_info, product_aum, how='left', on='product_id')
    product_info['net_asset_val'].fillna(product_info['product_aum'], inplace=True)
    del product_info['product_aum']
    result = pd.merge(company_info, strategy_info, how='right', on='company_id')
    result = pd.merge(result, product_info, how='left', on='strategy_id')
    result = result[['company_short_name', 'library_type', 'strategy_name', 'label_level_2','strategy_rating', 'product_short_name','product_open_status','net_asset_val','primary_coverage']]
    result.rename(columns={'company_short_name':'公司','library_type':'所在库','strategy_name':'策略',
                           'label_level_2':'策略类型','strategy_rating':'策略评级','product_short_name':'产品名称',
                           'product_open_status':'产品开放状态','net_asset_val':'产品规模','primary_coverage':'负责人'},inplace=True)
    result = result[result['所在库'].isin(['核心库', '成长库'])]
    result = result.sort_values(['策略评级', '策略类型', '所在库']).reset_index(drop=True)
    return result

