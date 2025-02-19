# ------------------------------------------------
# 本文档用于对收益率序列做指标计算
# ------------------------------------------------
import datetime
import pandas as pd
import numpy as np
import src.data.wind as wind
from src.data.wind import *
from sklearn.linear_model import LinearRegression

# ------------------------------------------------
# 私有函数
# Calendar函数的公共部分，数据预处理，用于简化Calendar函数
# ------------------------------------------------
def _funCalendarHelper(ret_series, calendar):
    assert isinstance(ret_series, pd.Series), 'nav return input must be a Series'
    assert calendar in ['Y', 'M', 'W'], "input for 'calendar' must in ['Y', 'M', 'W']"
    ret_df = ret_series.sort_index(ascending=True).to_frame().reset_index()
    ret_df.columns = ['date', 'return']
    ret_df['year'] = pd.to_datetime(ret_df['date']).dt.year
    ret_df['month'] = pd.to_datetime(ret_df['date']).dt.month
    ret_df['week'] = pd.to_datetime(ret_df['date']).dt.isocalendar().week
    calendarDiction = {
        'Y': ['year'],
        'M': ['year', 'month'],
        'W': ['year', 'week']
    }
    ret_df.set_index('date', inplace=True)
    return calendarDiction, ret_df

# ------------------------------------------------------------------------
# 账户列表切片help函数(sql in 单次最多只支持1000条 同时 整体sql语句string的大小不能超过2kb）
# ------------------------------------------------------------------------
def basicCal_cut(obj, step):
    return [obj[i: i+step] for i in range(0, len(obj), step)]

# ------------------------------------------------
# 计算给定收益序列的期间最大回撤
# ------------------------------------------------
def basicCal_getMaxDrawdown(
        ret_series  # A one column Series, nav return series
):
    assert isinstance(ret_series, pd.Series), 'nav return input must be a Series'
    ret_df = ret_series.sort_index(ascending=True)
    CumulativeNAV = (ret_df + 1).cumprod()
    CumulativeNAV[CumulativeNAV.index[0]-datetime.timedelta(days=1)] = 1
    CumulativeNAV.sort_index(inplace=True, ascending=True)
    MDDSeries = []
    for trade_date in CumulativeNAV.index:
        curMDD = CumulativeNAV[trade_date:].min() / CumulativeNAV.loc[trade_date] - 1
        MDDSeries.append(curMDD)
    MaxDrawdown = np.array(MDDSeries).min()
    return MaxDrawdown

# -----------------------------------------------------
# 计算给定收益序列的当前回撤指标或者时序数据
# 通过选择series_mode可返回回撤序列
# -----------------------------------------------------
def basicCal_getCurrentDrawdown(
        ret_series,         # A one column Series, nav return series
        series_mode=False,  # 如果为True,返回当前回撤的时间序列;如果为False,返回该序列在最后一个时间点的当前回撤
):
    assert isinstance(ret_series,pd.Series),'nav return input must be a Series'
    ret_df = ret_series.sort_index(ascending=True)
    CumulativeNAV = (ret_df + 1).cumprod()
    CumulativeNAV[CumulativeNAV.index[0] - datetime.timedelta(days=1)] = 1
    CumulativeNAV.sort_index(inplace=True, ascending=True)
    # 当前回撤序列: 当前净值/截至当前的最大净值 - 1 的 时间序列
    CurrentDrawdownSeries = CumulativeNAV / CumulativeNAV.cummax() - 1
    if series_mode:
        return CurrentDrawdownSeries
    else:  # 取当前回撤序列的最后一个点，为当前回撤
        CurrentDrawDown=CurrentDrawdownSeries[CurrentDrawdownSeries.index[-1]]
        return CurrentDrawDown

# ------------------------------------------------
# 计算给定收益序列的分年度/月度最大回撤
# 返回Series，index为year或year&month
# ------------------------------------------------
def basicCal_getCalendarMaxDrawdown(
        ret_series,    # A one column Series, nav return series
        calendar='Y'   # 'Y' 分年度，'M' 分月度
):
    calendarDiction, ret_df = _funCalendarHelper(ret_series, calendar)
    MaxDrawdown = ret_df.groupby(calendarDiction[calendar])['return'].apply(
        lambda x: basicCal_getMaxDrawdown(x))
    return MaxDrawdown

# ------------------------------------------------
# 计算给定投资组合的极端风险
# output: tuple类型 (tail volatility, tail maxdrawdown)
# ------------------------------------------------
def basicCal_getPortfolioTailRisk(
    ret_df,  # DataFrame，各底层收益率序列
    weight,  # dictionary of asset weight
    freq='W'  # 数据频率，可以取'W'或'D'
):
    assert freq in ['W', 'D'], "freq must be 'W' or 'D'"
    weight = np.array([weight[asset] for asset in ret_df.columns])
    perfstats = pd.DataFrame(index=['ann_vol', 'mdd'], columns=ret_df.columns)
    for col in ret_df:
        perfstats.loc['ann_vol', col] = basicCal_getAnnualVol(ret_df[col], freq=freq)
        perfstats.loc['mdd', col] = basicCal_getMaxDrawdown(ret_df[col])
    v_vol = weight * perfstats.loc['ann_vol']
    tail_vol = np.sqrt(np.array(v_vol).dot(np.ones((len(weight), len(weight)))).dot(np.array(v_vol).T))
    tail_mdd = (perfstats.loc['mdd', :] * weight).sum()
    return (tail_vol, tail_mdd)

# ------------------------------------------------
# 计算给定收益序列的区间收益率
# ------------------------------------------------
def basicCal_getPeriodReturn(
        ret_series,  # A one column Series, nav return series
        freq='W',    # 'W' stands for weekly return, 'D' stands for daily return, 'M' stands for monthly return, default 'W'
        annualized=True    # if annualized, default True
):
    assert isinstance(ret_series, pd.Series), 'nav return input must be a Series'
    assert freq in ['D', 'W', 'M'], "input for 'freq' must in ['D', 'W', 'M']"
    FreqDiction = {
        'D': const.const.ANNUAL_SCALE,
        'W': const.const.WEEK_SCALE,
        'M': 12
    }
    CumulativeRet = (ret_series + 1).prod() - 1
    AnnualRet = (1 + CumulativeRet) ** (FreqDiction[freq]/len(ret_series)) - 1
    return AnnualRet if annualized else CumulativeRet

# ------------------------------------------------
# 计算给定收益序列的分年度/月度收益
# 返回Series，index为year或year&month
# ------------------------------------------------
def basicCal_getCalendarPeriodReturn(
        ret_series,    # A one column Series, nav return series
        calendar='Y'   # 'Y' 分年度，'M' 分月度， 'W'分周度
):
    calendarDiction, ret_df = _funCalendarHelper(ret_series, calendar)
    CumulativeRet = ret_df.groupby(calendarDiction[calendar])['return'].apply(
        lambda x: basicCal_getPeriodReturn(x, freq='D', annualized=False))  # annualized=False，无所谓D还是W
    return CumulativeRet

# ------------------------------------------------
# 计算给定收益序列的年化波动率
# ------------------------------------------------
def basicCal_getAnnualVol(
        ret_series,  # A one column Series, nav return series
        freq='W'    # 'W' stands for weekly return, 'D' stands for daily return, 'M' stands for monthly return, default 'W'
):
    assert isinstance(ret_series, pd.Series), 'nav return input must be a Series'
    assert freq in ['D', 'W', 'M'], "input for 'freq' must in ['D', 'W', 'M']"
    FreqDiction = {
        'D': const.const.ANNUAL_SCALE,
        'W': const.const.WEEK_SCALE,
        'M': 12
    }
    AnnualVol = ret_series.std() * np.sqrt(FreqDiction[freq])
    return AnnualVol

# ------------------------------------------------
# 计算给定收益序列的期间夏普率
# ------------------------------------------------
def basicCal_getSharpeRatio(
        ret_series,  # A one column Series, nav return series
        freq='W',   # 'W' stands for weekly return, 'D' stands for daily return, default 'W'
        rf=0        # riks free rate, default 0
):
    assert isinstance(ret_series, pd.Series), 'nav return input must be a Series'
    AnnualRet = basicCal_getPeriodReturn(ret_series, freq)
    AnnulVol = basicCal_getAnnualVol(ret_series, freq)
    Sharpe = (AnnualRet - rf) / AnnulVol
    return Sharpe

# ------------------------------------------------
# 计算给定收益序列的分年度/月度夏普率
# 返回Series，index为year或year&month
# ------------------------------------------------
def basicCal_getCalendarSharpeRatio(
        ret_series,    # A one column Series, nav return series
        calendar='Y',  # 'Y' 分年度，'M' 分月度
        freq='D',      # 'W' stands for weekly return, 'D' stands for daily return, default 'D'
        rf=0          # riks free rate, default 0
):
    calendarDiction, ret_df = _funCalendarHelper(ret_series, calendar)
    Sharpe = ret_df.groupby(calendarDiction[calendar])['return'].apply(
        lambda x: basicCal_getSharpeRatio(x, freq, rf))
    return Sharpe

# ------------------------------------------------
# 计算calmar
# ------------------------------------------------
def basicCal_getCalmarRatio(
    ret_series,  # pd.series
    freq  # 数据频率, W or D
):
    assert isinstance(ret_series, pd.Series), "收益率序列需为pd.series格式"
    assert freq in ("W", "D"), "频率只能为D或者W"
    period_return = basicCal_getPeriodReturn(ret_series, freq=freq, annualized=True)
    mdd = basicCal_getMaxDrawdown(ret_series)
    return np.nan if (mdd == 0) else (- period_return / mdd)

# ------------------------------------------------
# 计算基金的jensen
# jensen-alpha = (ri-rf) - beta_i(rm-rf)
# 返回[alpha, beta]
# ------------------------------------------------
def basicCal_jensen(
        ret_series,                 # series，收益序列
        index_return,               # series,指数收益序列
        rf = 0.03                   # risk-free rate (annual)
):
    ret_series.name = 'ret'
    ret_df = ret_series.to_frame()
    index_return.name = 'idx_ret'
    ret_df = ret_df.join(index_return, how = 'inner')
    ri_minus_rf = ret_df['ret'] - rf/const.const.ANNUAL_SCALE
    rm_minus_rf = ret_df['idx_ret'] - rf/const.const.ANNUAL_SCALE
    model = LinearRegression().fit(rm_minus_rf.to_numpy().reshape(-1, 1), ri_minus_rf)
    return [model.intercept_, model.coef_[0]]

# ------------------------------------------------
# 计算基金的选股能力(alpha)，选时能力(gamma)
# 选股能力(alpha)，选时能力(gamma)： r-rf = alpha + beta(rm-rf) + gamma(rm-rf)**2 + epsilon
# 返回 [alpha, beta, gamma]
# ------------------------------------------------
def basicCal_AlphaGamma(
        ret_series,                 # series，每列一只基金
        index_return,               # series,只含单列
        rf = 0.03                   # risk-free rate (annual)
):
    ret_series.name = 'ret'
    ret_df = ret_series.to_frame()
    index_return.name = 'idx_ret'
    ret_df = ret_df.join(index_return, how = 'inner')
    ri_minus_rf = ret_df['ret'] - rf/const.const.ANNUAL_SCALE
    rm_minus_rf = ret_df['idx_ret'] - rf/const.const.ANNUAL_SCALE
    rm_minus_rf_squared = rm_minus_rf**2
    independent_variable = pd.DataFrame([rm_minus_rf, rm_minus_rf_squared]).T.values
    model = LinearRegression().fit(independent_variable, ri_minus_rf)
    return [model.intercept_, model.coef_[0], model.coef_[1]]

# ------------------------------------------------
# 计算基金的excess return
# author: Zhongheng Shen, 041439
# ------------------------------------------------
def basicCal_calExcessReturn(
        fund_return,  # 基金收益率序列：pandas series
        bm_return  # 基准收益率序列：pandas series
):
    assert isinstance(fund_return, pd.Series), "基金收益率序列必须为pandas Series"
    assert isinstance(bm_return, pd.Series), "基准收益率序列必须为pandas Series"

    excess_return = (fund_return - bm_return).dropna()
    return excess_return

# ------------------------------------------------
# 计算给定收益序列的超额收益
# ------------------------------------------------
def basicCal_getExcessReturn(
        ret_series,   # A one column Series, nav return series
        benchmark_ret_series,   # A one column Series, benchmark return series
        freq,   # 'W' stands for weekly return, 'D' stands for daily return, 'M' stands for monthly return, default 'D'
        annualized=True  # 是否年化
):
    ret = basicCal_getPeriodReturn(ret_series, freq, annualized)
    benchmark_ret = basicCal_getPeriodReturn(benchmark_ret_series, freq, annualized)
    return ret - benchmark_ret

# ------------------------------------------------
# 计算相关性，输入为DataFrame，每列是一条数据
# 输入变量可以有NA，计算相关性时会自动滤掉
# ------------------------------------------------
def basicCal_Correlation(
        fund_return,  # 基金收益率序列：DataFrame
):
    assert isinstance(fund_return, pd.DataFrame), "基金收益率序列必须为pandas DataFrame"
    corr = fund_return.corr()
    return corr

# ------------------------------------------------
# 计算胜率，包括日/周/月/年胜率
# ------------------------------------------------
def basicCal_winningRate(
        ret_series,  # A one column Series, nav return series
        freq='W'     # 'D', 'W', 'M', 'Y' 对应日/周/月/年胜率
):
    assert isinstance(ret_series, pd.Series), "基金收益率序列必须为pandas Series"
    ret_df = ret_series.to_frame().reset_index()
    ret_df.columns = ['date', 'return']
    ret_df['year'] = pd.to_datetime(ret_df['date']).dt.year
    ret_df['month'] = pd.to_datetime(ret_df['date']).dt.month
    ret_df['week'] = pd.to_datetime(ret_df['date']).dt.isocalendar().week
    freqDiction = {
        'Y': ['year'],
        'M': ['year', 'month'],
        'W': ['year', 'month', 'week'],
        'D': ['date']
    }

    ret = ret_df.groupby(freqDiction[freq])['return'].apply(lambda x: (1+x).product()-1)
    result = (ret > 0).sum()/len(ret)
    return result

# ------------------------------------------------
# 计算给定收益序列的分年度/月度胜率
# 返回Series，index为year或year&month
# ------------------------------------------------
def basicCal_getCalendarwinningRate(
        ret_series,    # A one column Series, nav return series
        calendar='Y',  # 'Y' 分年度，'M' 分月度
        freq='W'      # 'W' stands for weekly return, 'D' stands for daily return, default 'D'
):
    calendarDiction, ret_df = _funCalendarHelper(ret_series, calendar)
    WinningRate = ret_df.groupby(calendarDiction[calendar])['return'].apply(
        lambda x: basicCal_winningRate(x, freq))
    return WinningRate

# ------------------------------------------------
# 计算给定收益序列的多个风险收益指标
# 返回dict,key为风险收益指标名称
# ------------------------------------------------
def basicCal_calPerformanceStats(
    ret_series,
    freq,  # 数据频率, W or D
    benchmark_ret_series=None,
    stats=const.const.COMMON_PERF_STATS  # 函数所需计算的stats list, 默认stats为'period_return', 'annualized_period_return', 'annualized_volatility', 'max_drawdown', 'sharpe_ratio', 'calmar'
):
    assert isinstance(ret_series, pd.Series), "收益率序列需为pd.series格式"
    assert freq in ("W", "D"), "频率只能为D或者W"
    assert set(stats) <= (set(const.const.COMMON_PERF_STATS) | set(const.const.EXTEND_PERF_STATS)), \
            "stats选项目前支持'period_return','annualized_period_return','annualized_volatility','max_drawdown','sharpe_ratio','calmar','current_drawdown'"
    result = dict()
    if ret_series.empty:
        if 'period_return' in stats:
            result['period_return'] = np.nan
        if 'annualized_period_return' in stats:
            result['annualized_period_return'] = np.nan
        if 'annualized_volatility' in stats:
            result['annualized_volatility'] = np.nan
        if 'max_drawdown' in stats:
            result['max_drawdown'] = np.nan
        if 'sharpe_ratio' in stats:
            result['sharpe_ratio'] = np.nan
        if 'calmar' in stats:
            result['calmar'] = np.nan
        if 'current_drawdown' in stats:
            result['current_drawdown'] = np.nan
        result['start_date'] = np.nan
        result['end_date'] = np.nan
    else:
        if benchmark_ret_series is not None:
            benchmark_ret_series = benchmark_ret_series.loc[ret_series.index[0]: ret_series.index[-1]]
            excess_ret_df = pd.merge(ret_series, benchmark_ret_series, how='left', left_index=True, right_index=True)
            excess_ret_series = excess_ret_df[ret_series.name] - excess_ret_df[benchmark_ret_series.name]

            def getSharpeRatio():
                if 'annualized_volatility' in stats and 'annualized_period_return' in stats:
                    return result['annualized_period_return'] / result['annualized_volatility']
                else:
                    return basicCal_getExcessReturn(ret_series, benchmark_ret_series, freq, annualized=True) / basicCal_getAnnualVol(excess_ret_series, freq=freq)

            def getCalmarRatio():
                if 'annualized_period_return' in stats and 'max_drawdown' in stats:
                    if result['max_drawdown'] != 0:
                        return - result['annualized_period_return'] / result['max_drawdown']
                    else:
                        return np.nan
                else:
                    max_drawdown = basicCal_getMaxDrawdown(excess_ret_series)
                    if max_drawdown != 0:
                        return - basicCal_getExcessReturn(ret_series, benchmark_ret_series, freq, annualized=True) / max_drawdown
                    else:
                        return np.nan

            if 'period_return' in stats:
                result['period_return'] = basicCal_getExcessReturn(ret_series, benchmark_ret_series, freq, annualized=False)
            if 'annualized_period_return' in stats:
                result['annualized_period_return'] = basicCal_getExcessReturn(ret_series, benchmark_ret_series, freq, annualized=True)
            if 'annualized_volatility' in stats:
                result['annualized_volatility'] = basicCal_getAnnualVol(excess_ret_series, freq=freq)
            if 'max_drawdown' in stats:
                result['max_drawdown'] = basicCal_getMaxDrawdown(excess_ret_series)
            if 'sharpe_ratio' in stats:
                result['sharpe_ratio'] = getSharpeRatio()
            if 'calmar' in stats:
                result['calmar'] = getCalmarRatio()
            if 'current_drawdown' in stats:
                result['current_drawdown'] = basicCal_getCurrentDrawdown(excess_ret_series)
            result['start_date'] = excess_ret_series.index[0]
            result['end_date'] = excess_ret_series.index[-1]
        else:
            if 'period_return' in stats:
                result['period_return'] = basicCal_getPeriodReturn(ret_series, freq=freq, annualized=False)
            if 'annualized_period_return' in stats:
                result['annualized_period_return'] = basicCal_getPeriodReturn(ret_series, freq=freq, annualized=True)
            if 'annualized_volatility' in stats:
                result['annualized_volatility'] = basicCal_getAnnualVol(ret_series, freq=freq)
            if 'max_drawdown' in stats:
                result['max_drawdown'] = basicCal_getMaxDrawdown(ret_series)
            if 'sharpe_ratio' in stats:
                result['sharpe_ratio'] = basicCal_getSharpeRatio(ret_series, freq=freq)
            if 'calmar' in stats:
                result['calmar'] = basicCal_getCalmarRatio(ret_series, freq)
            if 'current_drawdown' in stats:
                result['current_drawdown'] = basicCal_getCurrentDrawdown(ret_series)
            result['start_date'] = ret_series.index[0]
            result['end_date'] = ret_series.index[-1]
    return result

# ------------------------------------------------
# 计算给定收益序列的滚动持有胜率
# return: [0]: 胜率, [1]: 滚动持有年化收益, [2]: 滚动持有年化波动率, [3]: 滚动持有期最大回撤
# ------------------------------------------------
def basicCal_getRollingHoldPerformance(
    ret_series,
    freq,  # 数据频率, W or D
    rolling_hold, # float, 滚动持有期, 单位：年, 建议输入0.5, 1, 1.5, 2
    threshold=0 # float, 胜率比较基准
):
    assert isinstance(ret_series, pd.Series), "收益率序列需为pd.series格式"
    assert freq in ("W", "D"), "频率只能为D或者W"
    FreqDiction = {
        'D': const.const.ANNUAL_SCALE,
        'W': const.const.WEEK_SCALE
    }
    rolling_ann_ret = ((1 + ret_series).rolling(int(rolling_hold*FreqDiction[freq])).apply(np.prod)) ** (1/rolling_hold) - 1
    rolling_ann_ret = rolling_ann_ret.iloc[(rolling_hold * FreqDiction[freq] - 1):]
    rolling_wr = (rolling_ann_ret > threshold).sum() / rolling_ann_ret.shape[0]
    rolling_ann_vol = ret_series.rolling(int(rolling_hold*FreqDiction[freq])).apply(basicCal_getAnnualVol).dropna()
    rolling_mdd = ret_series.rolling(int(rolling_hold*FreqDiction[freq])).apply(basicCal_getMaxDrawdown).dropna()
    return rolling_wr, rolling_ann_ret, rolling_ann_vol, rolling_mdd

# ---------------------------------------------------------------------------------------------
# 获取起止日期范围内交易日的常数收益率序列
# 为中性等策略提供所需benchmark数据
# 返回 列名为[date, return_col_name(变量名)]的常数收益率df
# ---------------------------------------------------------------------------------------------
def basicCal_getConstBMCurve(
    start_date,                     # datetime.date instance
    end_date,                       # datetime.date instance
    const_return=0,                 # 常数收益率(年化数值)，默认为0，注意应是绝对数值，不是百分数，例如0.03
    return_col_name='bm_return'     # bm收益率列名
):
    trade_date = wind.wind_getSSECalendar()
    ret = trade_date[(trade_date['date'] >= start_date) & (trade_date['date'] <= end_date)]
    ret[return_col_name] = (1 + const_return) ** (1/const.const.ANNUAL_SCALE) - 1
    ret.reset_index(drop=True, inplace=True)
    return ret

