# ------------------------------------------------
# 本文档用于CTA私募分析
# ------------------------------------------------
import pandas as pd
import numpy as np
import src.data.wind as wind
import src.data.cta as ctaData
import src.data.custHF as custHF
from src.const import *
from WindPy import *
import src.utils.Calculation as cal
import datetime
import statsmodels.api as sm
import src.utils.fof_calendar as calendar
import src.config as config
import src.data.irm as irm


# ------------------------------------------------------
# 计算期货品种区间时序波动（年化）
# return: vol_ew 各品种历史波动率平均, vol_aw 各品种历史波动率平均（按成交额加权）
# ------------------------------------------------------
def ctaAnls_getTimeSeriesVolatility(
        start_date,  # 起始日期，输入格式:datetime.date
        end_date,  # 结束日期，输入格式:datetime.date
        window=20  # 回看时间窗口，默认20个交易日
):
    dailydata_dict = ctaData.cta_getFuturesIndexDailyData(list(const.FUTURES_DICT.values()), start_date, end_date)
    close_df = dailydata_dict['close']
    amount_df = dailydata_dict['amount']
    ret_df = (close_df / close_df.shift(1) - 1).dropna(axis=0, how='all')
    vol = ret_df.rolling(window).std().dropna(axis=0, how='all')
    vol_ew = vol.apply(np.nanmean, axis=1)*np.sqrt(const.ANNUAL_SCALE)
    amount_weight = amount_df.shift(1).rolling(window).mean().dropna(axis=0, how='all').fillna(0)
    amount_weight = amount_weight.div(amount_weight.sum(axis=1), axis=0)
    amount_weight = amount_weight.loc[:, vol.columns]
    vol_aw = (vol * amount_weight).sum(axis=1)*np.sqrt(const.ANNUAL_SCALE)
    vol_df = pd.concat([vol_ew, vol_aw], axis=1)
    vol_df.columns = ['equal weighted', 'amount weighted']
    return vol_df

# ------------------------------------------------------
# 计算期货品种区间时序波动历史分位数
# e.g. start_date为2023.1.1，如果window=20，表示计算20个交易日滚动波动率，2023.1.1的数据需要用到2022.12.1-2023.1.1的收益率数据计算
# 如果history=365，表示计算当日的时序波动率在过去365个自然日的区间内所处的分位数，最早的收益率数据需要从2021.12.1开始读取
# ------------------------------------------------------
def ctaAnls_getTimeSeriesVolPercentile(
    start_date,  # 起始日期，输入格式:datetime.date
    end_date,  # 结束日期，输入格式:datetime.date
    window=20,  # 回看时间窗口，默认20个交易日
    history=365 # 历史分位数窗口，默认365个自然日
):
    vol_series = ctaAnls_getTimeSeriesVolatility(start_date-datetime.timedelta(days=history),
                                                 end_date, window)['equal weighted']
    pct_series = vol_series.rolling(history).apply(lambda x: len(x[x <= x.iloc[-1]]) / len(x))
    pct_series = pct_series.dropna()
    return pct_series

# ------------------------------------------------------
# 计算期货品种区间截面波动率
# ------------------------------------------------------
def ctaAnls_getCrossSectionVolatility(
        start_date,  # 起始日期，输入格式:datetime.date
        end_date,  # 结束日期，输入格式:datetime.date
        window=20  # 回看时间窗口，默认20个交易日
):
    # 可改为直接读 ctaAnls_getFuturesContractDailyData
    dailydata_dict = ctaData.cta_getFuturesIndexDailyData(list(const.FUTURES_DICT.values()), start_date, end_date)
    close_df = dailydata_dict['close']
    ret_df = (close_df / close_df.shift(window) - 1).dropna(axis=0, how='all')
    vol_all = ret_df.apply(np.nanstd, axis=1)
    vol_black = ret_df.loc[:, [x.split('.')[0] + 'FI.WI' for x in const.BLACK_IND_DICT.values()]].apply(np.nanstd, axis=1)
    vol_chemistry = ret_df.loc[:, [x.split('.')[0] + 'FI.WI' for x in const.CHEMISTRY_IND_DICT.values()]].apply(np.nanstd, axis=1)
    vol_agri = ret_df.loc[:, [x.split('.')[0] + 'LFI.WI' if x=='AP.CZC' else x.split('.')[0] + 'FI.WI'
                              for x in const.AGRICULTURE_IND_DICT.values()]].apply(np.nanstd, axis=1)
    vol_oil = ret_df.loc[:, [x.split('.')[0] + 'FI.WI' for x in const.AGRIOIL_IND_DICT.values()]].apply(np.nanstd, axis=1)
    vol_color = ret_df.loc[:, [x.split('.')[0] + 'FI.WI' for x in const.COLOR_IND_DICT.values()]].apply(np.nanstd, axis=1)
    vol_gold = ret_df.loc[:, [x.split('.')[0] + 'FI.WI' for x in const.GOLD_IND_DICT.values()]].apply(np.nanstd, axis=1)
    vol_df = pd.concat([vol_all, vol_black, vol_chemistry, vol_agri, vol_oil, vol_color, vol_gold], axis=1)
    vol_df.columns = ['all', 'black', 'chemistry', 'agriculture', 'oil', 'color', 'gold']
    return vol_df

# ------------------------------------------------------
# 期货板块量能分析-交易额变化
# ------------------------------------------------------
def ctaAnls_getTransAmtChange(
        start_date,  # 起始日期，输入格式:datetime.date
        end_date,  # 结束日期，输入格式:datetime.date
        ind_name_list=['黑色建材'],  # 重分类商品板块名, 输入格式:list
        window=20  # 移动均线窗口
):
    _output_df = []
    for ind_name in ind_name_list:
        dailydata_dict = ctaData.cta_getFuturesContractDailyData(list(const.REGROUP_IND_DICT[ind_name].values()), start_date, end_date)
        amount_df = dailydata_dict['amount']
        amount_change_MA = amount_df.rolling(window, axis=0).mean()
        amount_change_MA = amount_change_MA.dropna(axis=0, how='all')
        ind_amount_change_MA = amount_change_MA.mean(axis=1)
        _output_df.append(ind_amount_change_MA)
    output_df = pd.concat(_output_df, axis=1)
    output_df.columns = ind_name_list
    return output_df

# ------------------------------------------------------
# 期货板块量能分析-持仓量变化
# ------------------------------------------------------
def ctaAnls_getOpenInterestChange(
        start_date,  # 起始日期，输入格式:datetime.date
        end_date,  # 结束日期，输入格式:datetime.date
        ind_name_list=['黑色建材'],  # 重分类商品板块名, 输入格式:list
        window=20,  # 移动均线窗口
        amount_weighted=True  # 是否按成交量加权
):
    _output_df = []
    for ind_name in ind_name_list:
        dailydata_dict = ctaData.cta_getFuturesContractDailyData(list(const.REGROUP_IND_DICT[ind_name].values()),
                                                             start_date, end_date)
        oi_df = dailydata_dict['oi']
        oi_change_MA = oi_df.rolling(window, axis=0).mean()
        oi_change_MA = oi_change_MA.dropna(axis=0, how='all')
        if amount_weighted:
            amount_df = dailydata_dict['amount']
            amount_weight = amount_df.rolling(window).mean().dropna(axis=0, how='all').fillna(0)
            amount_weight = amount_weight.div(amount_weight.sum(axis=1), axis=0)
            ind_oi_change_MA = (oi_change_MA * amount_weight).sum(axis=1)
        else:
            ind_oi_change_MA = oi_change_MA.mean(axis=1)
        _output_df.append(ind_oi_change_MA)
    output_df = pd.concat(_output_df, axis=1)
    output_df.columns = ind_name_list
    return output_df

# ------------------------------------------------------
# 市场情景分析
# ------------------------------------------------------
def ctaAnls_SenarioClassification(
        start_date,  # 起始日期，输入格式:datetime.date
        end_date,  # 结束日期，输入格式:datetime.date
        threshold={'时序动量':0.6, '复合波动率':0.5},  # dict类型，市场环境划分界限，高于此为强动量/高波动
        threshold_type='QUANTILE'  # str类型，QUANTILE:分位数，VALUE:绝对值
):
    ts_vol_short = ctaAnls_getTimeSeriesVolatility(start_date-timedelta(30), end_date, window=5)
    ts_vol_long = ctaAnls_getTimeSeriesVolatility(start_date-timedelta(30), end_date, window=20)
    #  动量效应用华泰长周期商品动量指数做观察，之后可替
    w.start()
    read_benchmark = wind.wind_getIndexData('HTCI0101.WI', start_date-timedelta(30), end_date, "D")
    momentum_index = pd.Series(read_benchmark['close_price'].tolist(), index=read_benchmark['date'])
    ts_vol = (ts_vol_short + ts_vol_long) / 2
    market_condition = pd.concat([momentum_index, ts_vol], axis=1).drop('equal weighted', axis=1)
    market_condition = market_condition.dropna(axis=0, how='any')
    market_condition.columns = ['时序动量', '复合波动率']
    market_condition.index = pd.to_datetime(market_condition.index)
    trading_week = w.tdays(start_date, end_date, "Period=W").Data[0]
    senario_df = pd.DataFrame(index=trading_week, columns=market_condition.columns)
    weekly_vol = market_condition.groupby(market_condition.index.to_period('W-Fri')).mean().loc[:, '复合波动率']
    _momentum_ret = (market_condition.loc[:, '时序动量'] / market_condition.loc[:, '时序动量'].shift(1)).fillna(1)
    weekly_mom = _momentum_ret.groupby(_momentum_ret.index.to_period('W-Fri')).prod() - 1
    senario_df.loc[:, '时序动量'] = weekly_mom.tolist()[1:]  # 避免第一个数据集非完整周
    senario_df.loc[:, '复合波动率'] = weekly_vol.tolist()[1:]
    if threshold_type == 'QUANTILE':
        momentum_bar = senario_df['时序动量'].quantile(threshold['时序动量'])
        volatility_bar = senario_df['复合波动率'].quantile(threshold['复合波动率'])
    elif threshold_type == 'VALUE':
        momentum_bar = threshold['时序动量']
        volatility_bar = threshold['复合波动率']
    else:
        ValueError("threshold_type should be either 'QUANTILE' or 'VALUE'")
    senario_df.loc[senario_df['时序动量'] > momentum_bar, 'momentum'] = 1
    senario_df.loc[senario_df['时序动量'] <= momentum_bar, 'momentum'] = 0
    senario_df.loc[senario_df['复合波动率'] > volatility_bar, 'volatile'] = 1
    senario_df.loc[senario_df['复合波动率'] <= volatility_bar, 'volatile'] = 0
    senario_df = senario_df.reset_index().rename(columns={'index':'date'})
    senario_df['date'] = pd.to_datetime(senario_df['date']).dt.date
    return senario_df

# ------------------------------------------------------
# 托管截面前n大板块保证金
# ------------------------------------------------------
def ctaAnls_HFSectionMarginCS(
    date,  # 输入格式:datetime.date
    product_id=None,  # 单产品代码 e.g. 'SGW851.OF', 默认None为全量读取
    section_num=5  # 显示前N大板块
):
    read_margin = ctaData.cta_getFundPositionsInfo(start_date=date, end_date=date, sheet_tag='MARGIN', product_id=product_id)
    col_keep = list(const.FUTURES_IND_NAME_CN_TO_EN.keys())
    col_keep.remove('n_commodity_future') # 删去商品板块总保证金数据，仅展示板块
    melted = pd.melt(read_margin, id_vars=['product_id', 'product_name'],
                     value_vars=col_keep).rename(columns={'variable': 'section', 'value': 'margin'})
    melted = melted.sort_values(['product_id', 'margin'], ascending=[True, False]).reset_index(drop=True)
    result = melted.groupby('product_id', as_index=False).apply(lambda x: x[:section_num]).reset_index(drop=True)
    return result

# ------------------------------------------------------
# 托管时序板块保证金
# ------------------------------------------------------
def ctaAnls_HFSectionMarginTS(
    start_date, # 输入格式:datetime.date
    end_date,  # 输入格式:datetime.date
    product_id=None,  # 单产品代码 e.g. ['SGW851.OF'], 默认None为全量读取
):
    read_margin = ctaData.cta_getFundPositionsInfo(start_date=start_date, end_date=end_date, sheet_tag='MARGIN', product_id=product_id)
    col_keep=list(set(read_margin.columns)-set(['date','product_id','product_name','n_bzj']))
    melted = pd.melt(read_margin, id_vars=['date','product_id', 'product_name'],
                     value_vars=col_keep).rename(
                     columns={'variable': 'section', 'value': 'margin'})
    result = melted.sort_values(['product_id', 'margin'], ascending=[True, False]).reset_index(drop=True)
    # FIXME 待托管数据修复，去掉fillna(0)
    result['margin'] = result['margin'].fillna(0)
    result['date']=pd.to_datetime(result['date']).dt.date
    return result

# ------------------------------------------------------
# 托管时序保证金
# ------------------------------------------------------
def ctaAnls_HFMarginTS(
    start_date,  # 输入格式:datetime.date
    end_date,  # 输入格式:datetime.date
    product_id=None,  # 单产品代码 e.g. 'SGW851.OF', 默认None为全量读取
):
    read_margin = ctaData.cta_getFundPositionsInfo(start_date=start_date, end_date=end_date, sheet_tag='MARGIN', product_id=product_id)
    result = read_margin.loc[:, ['date', 'product_id', 'product_name', 'n_bzj']].\
        sort_values(['product_id', 'date'], ascending=[True, True]).reset_index(drop=True)
    result.rename(columns={'n_bzj':'margin'}, inplace=True)
    result['date'] = pd.to_datetime(result['date']).dt.date
    # FIXME 节假日存在空值,待托管数据修复以后处理
    result.dropna(inplace=True)
    return result

# ------------------------------------------------------
# 托管时序持有期货品种数量
# ------------------------------------------------------
def ctaAnls_HFHoldingNumTS(
    start_date,  # 输入格式:datetime.date
    end_date,  # 输入格式:datetime.date
    product_id=None,  # 单产品代码 e.g. 'SGW851.OF', 默认None为全量读取
):
    read_margin = ctaData.cta_getFundPositionsInfo(start_date=start_date, end_date=end_date, sheet_tag='MARGIN', product_id=product_id)
    result = read_margin.loc[:, ['date', 'product_id', 'product_name', 'holding_num']].\
        sort_values(['product_id', 'date'], ascending=[True, True]).reset_index(drop=True)
    result['date'] = pd.to_datetime(result['date']).dt.date
    return result

# ------------------------------------------------------
# 托管时序净市值敞口
# ------------------------------------------------------
def ctaAnls_HFValExposureTS(
    start_date,  # 输入格式:datetime.date
    end_date,  # 输入格式:datetime.date
    product_id=None,  # 单产品代码 e.g. 'SGW851.OF', 默认None为全量读取
):
    read_exposure = ctaData.cta_getFundPositionsInfo(start_date=start_date, end_date=end_date, sheet_tag='VAL', product_id=product_id)
    result = read_exposure.loc[:, ['date', 'product_id', 'product_name', 'n_stock_future', 'n_bond_future', 'n_commodity_future']].\
        sort_values(['product_id', 'date'], ascending=[True, True]).reset_index(drop=True)
    result.rename(columns={'n_stock_future':'stock_net_val', 'n_bond_future':'bond_net_val',
                           'n_commodity_future':'commodity_net_val'}, inplace=True)
    return result

# ------------------------------------------------------
# 托管区间板块交易损益
# ------------------------------------------------------
def ctaAnls_HFSectionPNL(
    start_date,  # 开始日期，输入格式:datetime.date
    end_date,  # 结束日期，输入格式:datetime.date，日期代表当周
    product_id=None  # 单产品代码 e.g. 'SGW851.OF', 默认None为全量读取
):
    read_pnl = ctaData.cta_getFundPositionsInfo(start_date=start_date, end_date=end_date, sheet_tag='RETURN', product_id=product_id)
    pnl_df = read_pnl.groupby(['product_id', 'product_name']).sum().reset_index()
    return pnl_df
# ------------------------------------------------------
# 托管区间板块交易时序累积损益
# ------------------------------------------------------
def ctaAnls_HFSectionPNLTS(
    start_date,  # 开始日期，输入格式:datetime.date
    end_date,  # 结束日期，输入格式:datetime.date，日期代表当周
    product_id=None  # 单产品代码 e.g. 'SGW851.OF', 默认None为全量读取
):
    read_pnl = ctaData.cta_getFundPositionsInfo(start_date=start_date, end_date=end_date, sheet_tag='RETURN', product_id=product_id)
    read_pnl.set_index(['date','product_id', 'product_name'],inplace=True)
    # FIXME 待托管数据修复，去掉fillna(0)
    read_pnl=read_pnl.fillna(0)
    pnl_df = read_pnl.groupby(['product_id', 'product_name']).cumsum().reset_index()
    return pnl_df

# ------------------------------------------------------
# 托管截面前N大板块市值敞口
# ------------------------------------------------------
def ctaAnls_HFSectionExposureCS(
    date,  # 输入格式:datetime.date
    direction=True,  # 仓位方向，True为多，False为空
    product_id=None,  # 单产品代码 e.g. 'SGW851.OF', 默认None为全量读取
    section_num=3  # 显示前N大板块
):
    read_expo = ctaData.cta_getFundPositionsInfo(start_date=date, end_date=date, sheet_tag='VAL', product_id=product_id)
    col_keep = list(const.FUTURES_IND_NAME_CN_TO_EN.keys())
    col_keep.remove('n_commodity_future')
    expo_df = pd.concat([read_expo[['date', 'product_id', 'product_name']],
                         read_expo[const.FUTURES_IND_NAME_CN_TO_EN][(read_expo[const.FUTURES_IND_NAME_CN_TO_EN] > 0) if direction
                         else (read_expo[const.FUTURES_IND_NAME_CN_TO_EN] <= 0)]], axis=1)
    melted = pd.melt(expo_df, id_vars=['product_id', 'product_name'],
                     value_vars=col_keep).rename(
                     columns={'variable': 'section', 'value': 'value_exposure'})
    melted = melted.sort_values(['product_id', 'value_exposure'], ascending=[True, False if direction else True]).reset_index(drop=True)
    result = melted.groupby('product_id', as_index=False).apply(lambda x: x[:section_num]).reset_index(drop=True)
    return result

# ------------------------------------------------------
# 托管时序前N大板块市值敞口
# ------------------------------------------------------
def ctaAnls_HFSectionExposureTS(
    start_date,  # 输入格式:datetime.date
    end_date,   # 输入格式:datetime.date
    product_id=None,  # 单产品代码 e.g. ['SGW851.OF'], 默认None为全量读取
):
    read_expo = ctaData.cta_getFundPositionsInfo(start_date=start_date, end_date=end_date, sheet_tag='VAL', product_id=product_id)
    col_keep=list(set(read_expo.columns)-set(['date','product_id','product_name']))
    melted = pd.melt(read_expo, id_vars=['date','product_id', 'product_name'],
                     value_vars=col_keep).rename(
                     columns={'variable': 'section', 'value': 'value_exposure'})
    result = melted.sort_values(['date','product_id','section'], ascending=True).reset_index(drop=True)
    # FIXME 待托管数据修复，去掉fillna(0)
    result['value_exposure']=result['value_exposure'].fillna(0)
    result['date'] = pd.to_datetime(result['date']).dt.date
    return result
# ------------------------------------------------------
# 托管前N大板块较上期市值敞口变动
# ------------------------------------------------------
def ctaAnls_HFSectionExposureChg(
    end_date,  # 结束日期，输入格式:datetime.date
    start_date,  # 起始日期，输入格式:datetime.date
    direction=True,  # 仓位变动方向，True为加仓，False为减仓
    product_id=None,  # 单产品代码 e.g. 'SGW851.OF', 默认None为全量读取
    section_num=3  # 显示前N大板块
):
    read_expo = ctaData.cta_getFundPositionsInfo(start_date=start_date, end_date=end_date, sheet_tag='VAL', product_id=product_id)
    start_expo = read_expo.loc[read_expo['date'] == start_date]
    end_expo = read_expo.loc[read_expo['date'] == end_date]
    col_keep = list(set(read_expo.columns) - set(['date', 'product_id', 'product_name', 'n_commodity_future', 'n_bzj']))
    start_melted = pd.melt(start_expo, id_vars=['product_id', 'product_name'],
                           value_vars=col_keep).rename(
                           columns={'variable': 'section', 'value': 'exposure_start'})
    end_melted = pd.melt(end_expo, id_vars=['product_id', 'product_name'],
                         value_vars=col_keep).rename(
                         columns={'variable': 'section', 'value': 'exposure_end'})
    # FIXME 待托管数据修复，去掉fillna(0)
    df = pd.merge(start_melted, end_melted, how='left', on=['product_id', 'section']).fillna(0)
    df['exposure_change'] = df['exposure_end'] - df['exposure_start']
    df.rename(columns={'product_name_x':'product_name'}, inplace=True)
    df = df.sort_values(by=['product_id', 'exposure_change'], ascending=[True, False if direction else True]).reset_index(drop=True)
    result = df.groupby('product_id', as_index=False).apply(lambda x: x[:section_num]).reset_index(drop=True)
    result['exposure_change'] = result['exposure_change'][(result['exposure_change'] > 0) if direction else (result['exposure_change'] <= 0)]
    return result

# ------------------------------------------------------
# 单产品-托管板块较上期市值敞口变动
# ------------------------------------------------------
def ctaAnls_SingleFundSectionExposureChg(
    end_date,  # 结束日期，输入格式:datetime.date
    start_date,  # 起始日期，输入格式:datetime.date
    product_id=None,  # 单产品代码 e.g. 'SGW851.OF', 默认None为全量读取
):
    read_expo = ctaData.cta_getFundPositionsInfo(start_date=start_date, end_date=end_date, sheet_tag='VAL',
                                                 product_id=product_id)
    col_keep=list(set(read_expo.columns)-set(['date','product_id', 'product_name','n_commodity_future','n_bzj']))
    start_expo = read_expo.loc[read_expo['date'] == read_expo['date'].min()]
    end_expo = read_expo.loc[read_expo['date'] == read_expo['date'].max()]
    start_melted = pd.melt(start_expo, id_vars=['product_id', 'product_name'],
                           value_vars=col_keep).rename(
        columns={'variable': 'section', 'value': 'exposure_start'})
    end_melted = pd.melt(end_expo, id_vars=['product_id', 'product_name'],
                         value_vars=col_keep).rename(
        columns={'variable': 'section', 'value': 'exposure_end'})
    # FIXME 待托管数据修复，去掉fillna(0)
    df = pd.merge(start_melted, end_melted, how='left', on=['product_id', 'product_name', 'section']).fillna(0)
    df['exposure_change'] = df['exposure_end'] - df['exposure_start']
    result = df.sort_values(by=['product_id', 'exposure_change'], ascending=False).reset_index(drop=True)
    result['开始日期'] = read_expo['date'].min()
    result['结束日期'] = read_expo['date'].max()
    return result

# ------------------------------------------------------
# 托管换手率及平均持仓周期、持有品种数量
# ------------------------------------------------------
def ctaAnls_HFTurnover(
    end_date,  # 结束日期，输入格式:datetime.date
    start_date,  # 起始日期，输入格式:datetime.date
    type='Turnover',  # 输入为'Turnover':换手率、 'HoldingPeriod':平均持仓周期、'HoldingVolume':持仓品种数量
    product_id=None,  # 单产品代码 e.g. 'SGW851.OF', 默认None为全量读取
):
    assert type in ('Turnover', 'HoldingPeriod', 'HoldingVolume'), "type只能输入'Turnover'、'HoldingPeriod'、'HoldingVolume'"
    type_map = {'Turnover': 'turnover', 'HoldingPeriod': 'holding_period', 'HoldingVolume': 'holding_num'}
    read_turnover = ctaData.cta_getFundTurnover(end_date=end_date, start_date=start_date, product_id=product_id)
    read_turnover.rename(columns={'n_rolling_60_hsl': 'turnover', 'n_avg_cczq': 'holding_period'}, inplace=True)
    df = read_turnover.loc[:, ['date', 'product_id', 'product_name', type_map[type]]]. \
        sort_values(['product_id', 'date'], ascending=[True, True]).reset_index(drop=True)
    df.dropna(inplace=True)
    df['date'] = pd.to_datetime(df['date']).dt.date
    return df

# ------------------------------------------------------------------------
# 计算CTA因子区间净值
# ------------------------------------------------------------------------
def ctaAnls_calCtaFactorNav(
    start_date,  # DateTime.date instance, eg: datetime.date(2021, 1, 1)
    end_date,  # DateTime.date instance, eg: datetime.date(2021, 10, 1)
    factor_list=None  # python list
):
    assert isinstance(start_date, datetime.date), "date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "date must be an instance of datetime.date"
    if factor_list:
        assert isinstance(factor_list, list), 'factor_list much be a list instance'

    cta_factor_daily_return = ctaData.cta_getCtaFactorReturn(start_date, end_date, factor_list)
    cta_factor_daily_return.set_index('date', inplace=True)
    cta_factor_daily_nav = (cta_factor_daily_return + 1).cumprod(axis=0)
    cta_factor_daily_nav.loc[cta_factor_daily_return.index[0] - datetime.timedelta(days=const.FREQ_INTERVAL['D'])] = 1
    cta_factor_daily_nav = cta_factor_daily_nav.sort_index()
    result = cta_factor_daily_nav.reset_index()
    return result


# ------------------------------------------------------------------------
# 计算CTA因子区间收益指标
# ------------------------------------------------------------------------
def ctaAnls_calCTAFactorPerfStats(
    start_date,  # DateTime.date instance, eg: datetime.date(2021, 1, 1)
    end_date,  # DateTime.date instance, eg: datetime.date(2021, 10, 1)
    factor_list=None  # python list
):
    assert isinstance(start_date, datetime.date), "date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "date must be an instance of datetime.date"
    if factor_list:
        assert isinstance(factor_list, list), 'factor_list much be a list instance'

    cta_factor_daily_return = ctaData.cta_getCtaFactorReturn(start_date, end_date, factor_list).set_index('date')
    factor_perf = dict()
    for factor_col in cta_factor_daily_return.columns:
        factor_perf[factor_col] = cal.basicCal_calPerformanceStats(cta_factor_daily_return[factor_col], freq='D', stats=const.COMMON_PERF_STATS)
    result = pd.DataFrame.from_dict(factor_perf).T
    result.reset_index(inplace=True)
    result.rename(columns={'index': 'cta_factor'}, inplace=True)
    return result

# ------------------------------------------------------------------------
# 计算CTA因子周度/月度收益
# ------------------------------------------------------------------------
def ctaAnls_calCTAFactorMonthlyReturn(
    start_date,  # DateTime.date instance, eg: datetime.date(2021, 1, 1)
    end_date,  # DateTime.date instance, eg: datetime.date(2021, 10, 1)
    factor_list=None  # python list
):
    assert isinstance(start_date, datetime.date), "date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "date must be an instance of datetime.date"
    if factor_list:
        assert isinstance(factor_list, list), 'factor_list much be a list instance'

    daily_return = ctaData.cta_getCtaFactorReturn(start_date, end_date, factor_list)
    daily_return.set_index('date', inplace=True)
    result = list()
    for factor in daily_return.columns:
        factor_monthly_return = cal.basicCal_getCalendarPeriodReturn(daily_return[factor], 'M')
        factor_monthly_return = factor_monthly_return.to_frame(factor)
        result.append(factor_monthly_return)
    result = pd.concat(result, axis=1, join='outer').sort_index(ascending=False)
    return result

# ------------------------------------------------------------------------
# CTA因子回归分析
# ------------------------------------------------------------------------
def ctaAnls_ctaRegressionAnalysis(
    ids,    # 输入私募产品或策略id list
    start_date,  # DateTime.date instance, eg: datetime.date(2021, 1, 1)
    end_date,  # DateTime.date instance, eg: datetime.date(2021, 10, 1)
    factor_list=None,  # python list
    data_level='Product',  # 数据层级
    freq='W'    # 频率
):
    assert isinstance(start_date, datetime.date), "date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "date must be an instance of datetime.date"
    assert freq in ("D", "W"), "freq需为D或者W"
    assert data_level in ('Strategy', 'Product'), "数据层级为Strategy 或 Product"
    hf_ret = custHF.custHF_getHFReturn(ids, start_date=start_date, end_date=end_date, freq=freq, data_level=data_level, include_nav=True)
    cta_factor_ret = ctaData.cta_getCtaFactorReturn(start_date, end_date, freq=freq, factor_list=factor_list).set_index('date')
    data_dict = {}
    for id in set(hf_ret['level_name']):
        single_hf_ret = hf_ret[hf_ret['level_name'] == id].set_index('date')
        # 对于statsmodels的回归模型需输入清洁后的数据
        filtered_date = single_hf_ret.index.intersection(cta_factor_ret.index)
        y = single_hf_ret.loc[filtered_date].sort_index()['adj_return_rate']
        x = cta_factor_ret.loc[filtered_date].sort_index()
        model = sm.OLS(y, x).fit()
        predict = model.predict(x)
        residuals = y-predict
        result_df = pd.DataFrame({
            id: y,
            '因子拟合净值': predict,
            '残差净值': residuals
        })
        result_df = (result_df+1).cumprod()
        result_df = result_df.div(result_df.iloc[0, ])
        result_params = pd.DataFrame({
            'coefficient': model.params,
            'pvalue': model.pvalues,
            'tvalues': model.tvalues,
            'R2_adj': model.rsquared_adj
        })
        data_dict[id] = {
            'nav_decompose': result_df.copy(deep=True),
            'reg_params': result_params.copy(deep=True),
        }
    return data_dict

# ------------------------------------------------------------------------
# 计算CTA因子收益贡献
# ------------------------------------------------------------------------
def ctaAnls_ctaFactorReturnAnalysis(
    factor,
    start_date,  # DateTime.date instance, eg: datetime.date(2021, 1, 1)
    end_date,  # DateTime.date instance, eg: datetime.date(2021, 10, 1)
    data_level='section',  # 归因层级，section板块，future品种
    long_short=False  # 归因是否区分多头、空头
):
    assert isinstance(start_date, datetime.date), "date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "date must be an instance of datetime.date"
    assert data_level in ('section', 'future'), "仅支持板块层面和品种层面"
    df_factor_return_info = ctaData.cta_getCtaFactorInfo(start_date, end_date)

    df_factor_return_info = df_factor_return_info.loc[df_factor_return_info['factor_return_name'] == factor]
    df_factor_return_info['real_return'] = df_factor_return_info['future_return']*df_factor_return_info['weight'] * \
                                           df_factor_return_info['signal_flag'].astype(int)
    df_factor_return_info['direction'] = df_factor_return_info['signal_flag'].replace({1: '多头', -1: '空头'})
    df_factor_return_info['future_id'] = df_factor_return_info['future_id'].replace(const.FUTURES_NAME_DICT)

    if data_level == 'section':
        group_columns = ['future_section']
    elif data_level == 'future':
        group_columns = ['future_id']
    direction_column = ['direction'] if long_short else []
    df_attribution = df_factor_return_info.groupby(['date'] + group_columns + direction_column, as_index=False)['real_return'].sum()
    df_attribution['NAV'] = df_attribution.groupby(group_columns + direction_column, as_index=False)['real_return'].transform(lambda x: (x + 1).cumprod())
    df_attribution_return = df_attribution.groupby(group_columns + direction_column, as_index=False)['NAV'].apply(lambda x: x.iloc[-1] - 1)
    df_attribution_return.rename(columns={'NAV': 'return'}, inplace=True)
    df_attribution_return['start_date'] = df_attribution['date'].min()
    df_attribution_return['end_date'] = df_attribution['date'].max()
    df_attribution_return = df_attribution_return.sort_values(by='return', ascending=False).reset_index(drop=True)
    df_attribution['accumulate_return'] = df_attribution['NAV'] - 1
    if long_short:
        df_attribution['level_direction'] = df_attribution[group_columns[0]]+df_attribution['direction']
        df_attribution_return['level_direction'] = df_attribution_return[group_columns[0]] + df_attribution_return['direction']
    else:
        df_attribution['level_direction'] = df_attribution[group_columns[0]]
        df_attribution_return['level_direction'] = df_attribution_return[group_columns[0]]
    return df_attribution, df_attribution_return

# ------------------------------------------------
# 计算给定策略或产品与CTA因子的相关性
# ------------------------------------------------
def ctaAnls_calFactorCorrelation(
    ids_dict,  # dict, id with fund type, e.g. {'HF': ['S0000045', 'S0000053']}
    start_date,  # DateTime.date instance
    end_date,  # DateTime.date instance
    freq,  # 数据频率，D或者W
    data_level='Strategy',  # Strategy or Product
    factor_list=None
):
    assert isinstance(ids_dict, dict), "ids_dict需为dict，例：{'HF': ['S0000045', 'S0000053']}"
    assert isinstance(start_date, datetime.date), "date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "date must be an instance of datetime.date"
    assert freq in ("D", "W"), "数据频率只支持D或者W"
    for k in ids_dict.keys():
        assert k in ('HF'), 'ids_dict的key只能为HF'
    hf_ids = ids_dict['HF']
    data = custHF.custHF_getHFReturn(hf_ids, start_date, end_date, freq, data_level=data_level)
    assert len(data) > 0, '无收益数据'
    data = data.pivot_table(index='date', values='adj_return_rate', columns='level_name')
    cta_ret = ctaData.cta_getCtaFactorReturn(start_date, end_date, freq=freq, factor_list=factor_list).set_index('date')
    corr_df = pd.concat([data, cta_ret], axis=1)
    id_order = list(cta_ret.columns) + list(data.columns)
    id_order = [id for id in id_order if id in corr_df.columns]
    corr_df = corr_df[id_order]
    corr_df = cal.basicCal_Correlation(corr_df)
    return corr_df


# ------------------------------------------------------------------------
#   计算近一周、近一月、近三月周期的因子收益率
# ------------------------------------------------------------------------
def ctaAnls_calCTAFactorPeriodReturn(
    start_date,  # DateTime.date instance, eg: datetime.date(2021, 1, 1)
    end_date,  # DateTime.date instance, eg: datetime.date(2021, 10, 1)
):
    daily_return = ctaData.cta_getCtaFactorReturn(start_date, end_date, factor_list=list(const.CTA_FACTOR_NAME_DICT.values()))
    daily_return.rename(columns=dict(zip(const.CTA_FACTOR_NAME_DICT.values(), const.CTA_FACTOR_NAME_DICT.keys())),inplace=True)
    daily_return.set_index('date', inplace=True)
    period_dict = {'近一周收益率': 'Recent_1W',
                   '近一月收益率': 'Recent_1M',
                   '近三月收益率': 'Recent_3M'
                   }
    return_dict = {}
    for period in period_dict.keys():
        start_date, end_date = calendar.calender_getStartEndDate(period_dict[period], end_date)
        return_dict[period] = (daily_return.loc[(daily_return.index >= start_date) & (daily_return.index <= end_date), ]
                               + 1).prod() - 1
    factor_period_return = pd.DataFrame(return_dict).reset_index().rename(columns={'index': '因子'})
    factor_period_return['因子分类'] = factor_period_return['因子'].replace(const.CTA_FACTOR_TYPE_DICT)
    factor_period_return['因子'] = factor_period_return['因子'].replace(const.CTA_FACTOR_NAME_DICT)
    return factor_period_return


# ------------------------------------------------------------------------
# 计算规模以上CTA管理人等权指数
# ------------------------------------------------------------------------
def ctaAnls_calCTACustomizedIndexReturn(
    start_date,  # DateTime.date instance, eg: datetime.date(2021, 1, 1)
    end_date,  # DateTime.date instance, eg: datetime.date(2021, 10, 1)
    insert=False
):
    assert isinstance(start_date, datetime.date), "date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "date must be an instance of datetime.date"
    strategy_ids = custHF.custHF_getStrategyInfo(strategy_level_1=['期货策略'])['strategy_id'].unique().tolist()
    return_data = custHF.custHF_getStrategyReturn(strategy_ids, start_date, end_date, freq='W')
    return_data['year'] = pd.to_datetime(return_data['date']).dt.year
    return_data['month'] = pd.to_datetime(return_data['date']).dt.month
    strategy_component = const.CTA_MANAGER_INDEX_COMPONENT
    strategy_component_ret = strategy_component.merge(return_data, on=['year', 'strategy_id'])
    index_ret = strategy_component_ret.groupby('date', as_index=False)[['adj_return_rate']].mean()
    index_ret = index_ret.loc[index_ret['date']>=start_date, ]
    index_ret.sort_values(by='date', inplace=True)
    index_ret = index_ret.rename(columns={'adj_return_rate': 'index_return', 'date': 'dt'})
    index_id = 'CTA_MANAGER_INDEX_01.CUSTOMIZED'
    index_ret['index_id'] = index_id
    index_ret['index_name'] = '定制-CTA管理人指数'
    index_ret['data_freq'] = 'W'
    index_ret['data_source'] = 'CITICSAM'
    index_ret['update_time'] = datetime.date.today()
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
