# ------------------------------------------------
# 本文档用于资产配置模型研究
# ------------------------------------------------
import math

import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import seaborn as sn
import datetime
import copy
import src.data.zyyx as zyyx
import src.data.wind as wind
import src.const as const
from src.data.custHF import *
from src.utils.riskBudgetTools import *
from src.utils.Calculation import *
from src.analysis.universeAnalysis import *

# ------------------------------------------------------
# 从Amdata读取实盘私募拟合收益序列
# ------------------------------------------------------
def _getFundfromAmdata(
    start_date,  # 起始日期，输入格式:datetime.date
    end_date,  # 结束日期，输入格式:datetime.date
    read_fund_code,  # list, 读取实盘产品代码
    freq='W'  # 数据频率，可以取'W'或'D'
):
    read_fund = custHF_getStrategyReturn(read_fund_code, start_date, end_date, freq=freq)
    fund_ret = pd.pivot_table(read_fund, index='date', columns='strategy_name', values='adj_return_rate')
    ret_series = fund_ret.mean(axis=1)
    strategy = pd.DataFrame(ret_series.values, index=ret_series.index, columns=['strategy_name'])
    return strategy

# ------------------------------------------------------
# 读取资产收益风险特征
# output: asset_return 大类资产收益序列
# ------------------------------------------------------
def pc_loadAssetReturn(
    start_date,  # 起始日期，输入格式:datetime.date
    end_date,  # 结束日期，输入格式:datetime.date
    freq='W',  # 数据频率，'W'或者'D'，freq='D'时无法读取朝阳永续数据
    wind_mapping=None,  # dict, 'Strategy name': wind code,
    # e.g. {'Equity':'885001.WI','Bond':'885008.WI'}
    zyyx_mapping=None,  # dict, 'Strategy name': zyyx code,
    # e.g. {'Arbitrage':'ZYYXARBB'}
    amdata_mapping=None  # dict, 'Strategy name': list of 拟合产品代码,
    # e.g.{'Commodity':['S0000064', 'S0000066', 'S0000093', 'S0000095'],
    #      'Hedge':['S0000036', 'S0000035', 'S0000029', 'S0000032']}
):
    assert freq in ['W', 'D'], "Freq must in ['W', 'D']"
    _asset_pool = []
    if freq == 'D':
        assert zyyx_mapping is None, "ZYYX data is not daily frequency"
    if not wind_mapping is None:
        asset_from_wind = pd.concat([wind.wind_getIndexData(wind_mapping[wind_code], start_date, end_date, freq=freq).set_index('date')['close_price']
                          for wind_code in wind_mapping.keys()], axis=1)
        asset_from_wind.columns = wind_mapping.keys()
        _asset_pool.append(asset_from_wind / asset_from_wind.shift(1) - 1)
    if not amdata_mapping is None:
        asset_from_amdata = pd.concat([_getFundfromAmdata(start_date, end_date, amdata_mapping[fund_code],freq=freq)
                            for fund_code in amdata_mapping.keys()], axis=1)
        asset_from_amdata.columns = amdata_mapping.keys()
        _asset_pool.append(asset_from_amdata)
    if not zyyx_mapping is None:
        asset_from_zyyx = zyyx.zyyx_getStrategyIndex(start_date, end_date, index_ids=zyyx_mapping.values())
        asset_from_zyyx = asset_from_zyyx.pivot_table(index='date', columns='index_name', values='index_value')
        asset_from_zyyx.columns = zyyx_mapping.keys()
        _asset_pool.append(asset_from_zyyx / asset_from_zyyx.shift(1) - 1)
    asset_return = pd.concat(_asset_pool, axis=1).sort_index(ascending=True)
    asset_return = asset_return.fillna(0)
    return asset_return

# ------------------------------------------------------
# 单个资产收益风险特征
# ------------------------------------------------------
def pc_calAssetPerfStats(
    asset_return,  # DataFrame，各类资产收益率序列
    freq='W'  # 数据频率，可以取'W'或'D'
):
    assert freq in ['W', 'D'], "freq must be 'W' or 'D'"
    output_df = pd.DataFrame(index=['ann_ret', 'ann_vol', 'mdd'], columns=asset_return.columns)
    for col in output_df:
        output_df.loc['ann_ret', col] = basicCal_getPeriodReturn(asset_return[col], freq=freq)
        output_df.loc['ann_vol', col] = basicCal_getAnnualVol(asset_return[col], freq=freq)
        output_df.loc['mdd', col] = basicCal_getMaxDrawdown(asset_return[col])
    return output_df
# ------------------------------------------------------
# 风险预算模型
# output[0]: asset weight
# output[1]: covariance matrix
# ------------------------------------------------------
def pc_riskBudgetModel(
    asset_return,  # DataFrame，各类资产收益率序列
    risk_budget,  # a list of risk budget
    freq='W',  # 数据频率，可以取'W'或'D'
):
    assert asset_return.shape[1] == len(risk_budget), "length of risk_budget must be %s" % asset_return.shape[1]
    assert np.array(risk_budget).sum() == 1, "the sum of risk budget input must equals 1"
    assert freq in ['W', 'D'], "freq must be 'W' or 'D'"
    FreqDiction = {'W': const.const.WEEK_SCALE,
                   'D': const.const.ANNUAL_SCALE}
    sig = asset_return.cov() * FreqDiction[freq]
    num = sig.shape[0]
    V = np.mat(sig)
    w0 = [1 / num] * num
    w = riskBgt_calWeight(risk_budget, w0, V)
    output_w = pd.DataFrame(w, columns=sig.columns, index=['weight'])
    return output_w, sig

# ------------------------------------------------------
# 给定目标风险预算下的组合优化
# ------------------------------------------------------
def pc_riskBudgetAdjust(
    asset_return,  # asset history return series
    asset_weight,  # dictionary of original weight
    TB,  # tolerated bias
    discount_asset=['Commodity', 'Arbitrage', 'Hedge'],  # List, 需要提取业绩报酬的资产列表
    fee=0.15,
    freq='W',  # 数据频率，可以取'W'或'D'
):
    assert freq in ['W', 'D'], "freq must be 'W' or 'D'"
    FreqDiction = {'W': const.const.WEEK_SCALE,
                   'D': const.const.ANNUAL_SCALE}
    sig = asset_return.cov() * FreqDiction[freq]
    w0 = np.array([asset_weight[asset] for asset in asset_return.columns])
    V = np.mat(sig)
    asset_return_copy = copy.deepcopy(asset_return)  # 避免修改asset_return变量本身
    for col in discount_asset:
        asset_return_copy[col].loc[asset_return_copy[col] > 0] = asset_return_copy[col].loc[asset_return_copy[col] > 0] * (1 - fee)
    ann_ret = np.array([basicCal_getPeriodReturn(asset_return.loc[:, col], freq=freq) for col in asset_return.columns])
    adj_w = riskBgt_calAdjustedWeight(ann_ret, V, w0, TB)
    output_w = pd.DataFrame(adj_w, columns=sig.columns, index=['weight'])
    return output_w

# ------------------------------------------------------
# 组合风险收益特征测算
# ------------------------------------------------------
def pc_backTest(
    asset_return,  # DataFrame，各类资产收益率序列
    asset_weight,  # dictionary of asset weight
    freq='W',  # 数据频率，可以取'W'或'D'
    rebalance=26,  # 多长时间做一次rebalance, 单位：周
    discount_asset=['Commodity', 'Arbitrage', 'Hedge'],  # List, 需要提取业绩报酬的资产列表
    fee=0.15,  # 提取业绩报酬
):
    assert freq in ['W', 'D'], "freq must be 'W' or 'D'"
    asset_return_copy = copy.deepcopy(asset_return)  # 避免修改asset_return变量本身
    for col in discount_asset:
        asset_return_copy[col].loc[asset_return_copy[col] > 0] = asset_return_copy[col].loc[asset_return_copy[col] > 0] * (1 - fee)
    startpoint = 0
    endpoint = asset_return_copy.shape[0]
    lastperiod_nav = 1
    backtest_nav = []
    asset_weight = np.array([asset_weight[asset] for asset in asset_return.columns])
    while startpoint <= endpoint:
        if freq == 'W':
            period_nav = (asset_return_copy.iloc[startpoint:(startpoint+rebalance)] + 1).\
                             cumprod(axis=0).dot(asset_weight) * lastperiod_nav
        else:
            period_nav = (asset_return_copy.iloc[startpoint:(startpoint+rebalance * 5)] + 1).\
                             cumprod(axis=0).dot(asset_weight) * lastperiod_nav
        lastperiod_nav = period_nav.tail(1)[0]
        backtest_nav.append(period_nav)
        startpoint = startpoint + rebalance if freq == 'W' else startpoint + rebalance * 5
    backtest_nav = pd.concat(backtest_nav, axis=0)
    backtest_ret = (backtest_nav / backtest_nav.shift(1) - 1).dropna()
    MDD = basicCal_getMaxDrawdown(backtest_ret)
    ann_vol = basicCal_getAnnualVol(backtest_ret, freq=freq)
    ann_ret = basicCal_getPeriodReturn(backtest_ret, freq=freq)
    index_df = pd.DataFrame([ann_ret, ann_vol, MDD],
                            index=['ret', 'vol', 'mdd'], columns=['回测结果']).T
    return index_df, backtest_nav

# ------------------------------------------------------
# 计算当前组合风险预算权重
# ------------------------------------------------------
def pc_calRiskBudgetWeight(
    asset_return,  # DataFrame，各类资产收益率序列
    asset_weight,  # dictionary of asset weight
    freq='W'
):
    FreqDiction = {'W': const.const.WEEK_SCALE,
                   'D': const.const.ANNUAL_SCALE}
    sig = asset_return.cov() * FreqDiction[freq]
    w = np.array([asset_weight[asset] for asset in sig.columns])
    V = np.mat(sig)
    rc = riskBgt_calRiskContribution(w, V)
    return pd.Series((rc / rc.sum()).tolist()[0], index=sig.columns)
