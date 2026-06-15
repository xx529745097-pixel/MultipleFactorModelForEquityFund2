from scipy import stats
import pandas as pd
import numpy as np
import warnings
import datetime
import src.data.irm as irm
from src.const import *
import src.data.cta as ctaData
import src.config as config
warnings.filterwarnings('ignore')

# ------------------------------------------------
# 偏度因子计算函数
# ------------------------------------------------
def ctaFactAnal_factorSkew(
        df_all,  # 所有合约数据表
        rolling_window,  # 滚动计算周期
        shift_window  # 需要向未来移动的周期数，实际移动周期为 shift_window
):
    df_return_adjust = pd.pivot_table(df_all, values='return',
                                      index='date', columns='code')
    df_return_adjust_shift = df_return_adjust.shift(shift_window)
    df_skew = df_return_adjust_shift.rolling(rolling_window, min_periods=rolling_window).skew()
    df_skew = df_skew.stack().reset_index().rename(
        columns={0: 'skew_{}'.format(rolling_window)})
    return df_skew

# ------------------------------------------------
# 波动率因子计算函数，收益率方差/均值
# ------------------------------------------------
def ctaFactAnal_factorVar(
        df_all,  # 所有合约数据表
        rolling_window,  # 滚动计算周期
        shift_window  # 需要向未来移动的周期数，实际移动周期为 shift_window
):
    df_return_adjust = pd.pivot_table(df_all, values='return', index='date', columns='code')
    df_return_adjust_shift = df_return_adjust.shift(shift_window)

    def _inner_get_var_mean(df):
        try:
            wave = df.var() / abs(df.mean())
        except ZeroDivisionError:
            wave = np.nan
        return wave

    df_wave = df_return_adjust_shift.rolling(rolling_window, min_periods=rolling_window).apply(_inner_get_var_mean)
    df_wave = df_wave.stack().reset_index().rename(
        columns={0: 'wave_{}'.format(rolling_window)})
    return df_wave

# ------------------------------------------------
# 标准差因子计算函数
# ------------------------------------------------
def ctaFactAnal_factorStd(
        df_all,  # 所有合约数据表
        rolling_window,  # 滚动计算周期
        shift_window  # 需要向未来移动的周期数，实际移动周期为 shift_window
):
    df_return_adjust = pd.pivot_table(df_all, values='return',
                                      index='date', columns='code')
    df_return_adjust_shift = df_return_adjust.shift(shift_window)

    def _inner_get_std(df):
        try:
            wave = df.std()
        except ZeroDivisionError:
            wave = np.nan
        return wave

    df_wave = df_return_adjust_shift.rolling(rolling_window, min_periods=rolling_window).apply(_inner_get_std)
    df_wave = df_wave.stack().reset_index().rename(
        columns={0: 'wave_{}'.format(rolling_window)})
    return df_wave

# ------------------------------------------------
# 流动性因子计算函数
# ------------------------------------------------
def ctaFactAnal_factorFluidity(
        df_all,  # 所有合约数据表
        rolling_window,  # 滚动计算周期
        shift_window  # 需要向未来移动的周期数，实际移动周期为 shift_window
):
    df_all['return_volume'] = abs(df_all['return']) / df_all['amount']
    df_all['return_volume'] = df_all['return_volume'].replace([np.inf, -np.inf], np.nan)
    df_return_volume_adjust = pd.pivot_table(df_all, values='return_volume',
                                             index='date', columns='code')
    df_return_volume_adjust_shift = df_return_volume_adjust.shift(shift_window)
    df_all.drop(['return_volume'], axis=1, inplace=True)

    def _inner_get_fluidity(df):
        fluidity = df.mean()
        return fluidity

    df_fluidity = df_return_volume_adjust_shift.rolling(rolling_window, min_periods=rolling_window). \
        apply(_inner_get_fluidity)
    df_fluidity = df_fluidity.stack().reset_index().rename(
        columns={0: 'fluidity_{}'.format(rolling_window)})
    return df_fluidity

# ------------------------------------------------
# 动量因子计算函数
# ------------------------------------------------
def ctaFactAnal_factorMomentum(
        df_all,  # 所有合约数据表
        rolling_window,  # 滚动计算周期
        shift_window  # 需要向未来移动的周期数，实际移动周期为 shift_window
):
    """获取时序动量"""
    df_return_adjust = pd.pivot_table(df_all, values='return',
                                      index='date', columns='code')
    df_return_adjust_shift = df_return_adjust.shift(shift_window)

    def _inner_get_momentum(df):
        # 计算过去rolling_window个交易日该合约的时序动量
        momentum = (df + 1).cumprod().iloc[-1]
        return momentum

    df_wave = ctaFactAnal_factorStd(df_all, 125, shift_window)
    df_wave.rename(columns={'wave_125': 'cv'}, inplace=True)
    df_momentum = df_return_adjust_shift.rolling(rolling_window, min_periods=rolling_window) \
        .apply(_inner_get_momentum)
    df_momentum = df_momentum.stack().reset_index().rename(
        columns={0: 'momentum'})
    df_momentum = pd.merge(df_momentum, df_wave, on=['date', 'code'], how='inner')
    df_momentum['momentum_{}'.format(rolling_window)] = (df_momentum['momentum'] - 1) / df_momentum['cv'] + 1
    return df_momentum[['date', 'code', 'momentum_{}'.format(rolling_window)]]

# ------------------------------------------------
# 展期收益率因子计算函数
# ------------------------------------------------
def ctaFactAnal_factorCarry(
        df_all,  # 所有合约数据表
        rolling_window,  # 滚动计算周期
        shift_window  # 需要向未来移动的周期数，实际移动周期为 shift_window
):
    df_all['settle_differ'] = np.log(df_all['close']) - \
                              np.log(df_all['close_second'])
    df_settle_differ_adjust = pd.pivot_table(df_all, values='settle_differ',
                                             index='date', columns='code')
    df_settle_differ_adjust = df_settle_differ_adjust.shift(shift_window)
    df_all['date_diff'] = (pd.to_datetime(df_all['delist_second']) -
                           pd.to_datetime(df_all['delist'])).dt.days
    df_date_differ_adjust = pd.pivot_table(df_all, values='date_diff',
                                           index='date', columns='code')
    df_date_differ_adjust = df_date_differ_adjust.shift(shift_window)
    df_date_differ_adjust = df_date_differ_adjust.replace(0, np.nan)

    df_all.drop(['settle_differ', 'date_diff'], axis=1, inplace=True)

    df_carry = df_settle_differ_adjust * 365 / df_date_differ_adjust
    df_carry = df_carry.rolling(rolling_window, min_periods=rolling_window).mean()
    df_carry = df_carry.stack().reset_index().rename(
        columns={0: 'carry'})
    return df_carry

# ------------------------------------------------
# 基差动量计算函数
# ------------------------------------------------
def ctaFactAnal_factorBasisMomentum(
        df_all,  # 所有合约数据表
        rolling_window,  # 滚动计算周期
        shift_window  # 需要向未来移动的周期数，实际移动周期为 shift_window
):
    df_return_adjust = pd.pivot_table(df_all, values='return',
                                      index='date', columns='code')
    df_return_adjust_shift = df_return_adjust.shift(shift_window)
    df_return_second_adjust = pd.pivot_table(df_all, values='return_second',
                                             index='date', columns='code')
    df_return_second_adjust = df_return_second_adjust.shift(shift_window)

    def _inner_get_cumprod(df):
        return df.cumprod().iloc[-1:]

    df_return_main = (df_return_adjust_shift + 1).rolling(rolling_window, min_periods=rolling_window). \
        apply(_inner_get_cumprod)
    df_return_second = (df_return_second_adjust + 1).rolling(rolling_window, min_periods=rolling_window). \
        apply(_inner_get_cumprod)
    df_basis_momentum = df_return_main - df_return_second
    df_basis_momentum = df_basis_momentum.stack().reset_index().rename(
        columns={0: 'basis_momentum_{}'.format(rolling_window)})
    return df_basis_momentum

# ------------------------------------------------
# 价值因子计算函数
# ------------------------------------------------
def ctaFactAnal_factorValue(
        df_all,  # 所有合约数据表
        shift_window  # 需要向未来移动的周期数，实际移动周期为 shift_window
):
    df_all['settle_log'] = np.log(df_all['close'] / df_all['close_next'])
    df_settle_differ_adjust = pd.pivot_table(df_all, values='settle_log',
                                             index='date', columns='code')
    df_settle_differ_adjust = df_settle_differ_adjust.shift(shift_window)
    df_all['month_diff'] = (df_all['delist_next'] - df_all['delist'])/datetime.timedelta(days = 30)

    df_month_differ_adjust = pd.pivot_table(df_all, values='month_diff',
                                            index='date', columns='code')
    df_month_differ_adjust = df_month_differ_adjust.shift(shift_window)
    df_month_differ_adjust = df_month_differ_adjust.replace(0, np.nan)

    df_all.drop(['settle_log', 'month_diff'], axis=1, inplace=True)

    df_value = df_settle_differ_adjust * 12 / df_month_differ_adjust  #统一调整为12个月的数据
    df_value = df_value.stack().reset_index().rename(
        columns={0: 'value'})
    return df_value

# ------------------------------------------------
# 期限结构因子计算函数
# ------------------------------------------------
def ctaFactAnal_factorTerm(
        df_all,  # 所有合约数据表
        rolling_window,  # 滚动计算周期
        shift_window  # 需要向未来移动的周期数，实际移动周期为 shift_window
):
    df_carry = ctaFactAnal_factorCarry(df_all, rolling_window, shift_window)
    df_carry['quntile_carry'] = df_carry.groupby('date', as_index=False)['carry'].rank(ascending=True, pct=True)
    df_value = ctaFactAnal_factorValue(df_all, shift_window)
    df_value['quntile_value'] = df_value.groupby('date',  as_index=False)['value'].rank(ascending=True, pct=True)
    df_term = pd.merge(df_carry, df_value, on=['date', 'code'], how='inner')
    df_term['term_structure'] = df_term['quntile_carry'] * 0.5 + df_term['quntile_value'] * 0.5
    return df_term[['date', 'code', 'term_structure']]
# ------------------------------------------------
# 计算库存因子
# ------------------------------------------------
def ctaFactAnal_factorWarehouse(
        factor_df,  # 库存数据表
        shift_window # 需要向未来移动的周期数，实际移动周期为 shift_window
):
    # 去空值
    factor_df = factor_df.replace(np.inf, np.nan)
    factor_df = factor_df.replace(-np.inf, np.nan)
    factor_df = factor_df.replace(0, np.nan)
    # 去极值
    data_median = factor_df.quantile(0.5, axis=0)
    new_median = ((factor_df - data_median).abs()).quantile(0.5, axis=0)
    max_range = data_median + 5 * new_median
    min_range = data_median - 5 * new_median
    clean_factor = factor_df.clip(min_range, max_range, axis=1)
    miu = clean_factor.mean(axis=1)
    sig = clean_factor.std(axis=1)
    accord_factor = clean_factor.sub(miu, axis=0).div(sig, axis=0)
    factor_warehouse = accord_factor.reset_index()
    factor_warehouse = factor_warehouse.set_index('date')
    factor_warehouse = factor_warehouse.shift(shift_window)
    factor_warehouse = factor_warehouse.stack().reset_index()
    factor_warehouse.rename(columns={'level_1': 'code', 0: 'warehouse'}, inplace=True)
    factor_warehouse['code'] = [code.split('.')[0] for code in factor_warehouse['code']]
    factor_warehouse = factor_warehouse.loc[factor_warehouse.code.isin(const.SELECTED_FUTURES_LIST)]
    return factor_warehouse

# ------------------------------------------------
# 选择合约，输出对应合约的持仓方向
# ------------------------------------------------
def _select_contract(
        df_factor,  # 因子序列
        ascending,  # 是否是反向因子，若1为正向 0为负向
        high,  # 多头阈值
        low,  # 空头阈值
        kind  # 截面因子为'cross',时序因子为'series'
):
    """
    选择每个交易日要交易的合约并得到交易方向
    输出：
    df_contract
    tradedate code  factor_value signal
    20160106   A       0.5         1
    """
    assert kind in ('cross', 'series')
    assert ascending in (1, 0)
    name = df_factor.columns[2]

    if kind == 'cross':
        def _sort_factor_value(df):
            # 对因子值进行排序，得到各因子的序号所在的分位数
            df['quantitle'] = df[name]. \
                apply(lambda x: stats.percentileofscore(
                df[name], x, kind='weak'))
            return df

        df_factor = df_factor.groupby('date',
                                      as_index=True).apply(_sort_factor_value).reset_index()
        # 筛选多头合约和空头合约
        if ascending == 1:
            df_long = df_factor.loc[df_factor['quantitle'] > high]
            df_short = df_factor.loc[df_factor['quantitle'] < low]
        elif ascending == 0:
            df_long = df_factor.loc[df_factor['quantitle'] < low]
            df_short = df_factor.loc[df_factor['quantitle'] > high]
        else:
            print("输入错误")
    elif kind == 'series':
        if ascending == 1:
            df_long = df_factor.loc[df_factor[name] \
                                    > high]
            df_short = df_factor.loc[df_factor[name] \
                                     < low]
        elif ascending == 0:
            df_long = df_factor.loc[df_factor[name] \
                                    < low]
            df_short = df_factor.loc[df_factor[name] \
                                     > high]
        else:
            print("输入错误")
    else:
        print("输入错误")
    # 根据多空头增加signal，多头为1，空头为-1
    df_long['signal'] = 1
    df_short['signal'] = -1
    # 合并得到所需的合约列表
    df_contract = pd.concat([df_long, df_short], axis=0, ignore_index=True)
    df_contract = df_contract[['date', 'code', name, 'signal']]
    return df_contract


# ------------------------------------------------
# 为持仓合约分配权重函数
# ------------------------------------------------
def _weight_distribution(
        df_contract,  # 带交易方向的品种数据
        df_cv,  # 波动率
        method='equal'  # 加权方法
):
    """
    输入：
    df_contract
    tradedate code factor_value signal
    20160106   A      0.5         1

    df_cv
    tradedate code  cv   amount
    20160106  A    0.13  10000
    method 有多个取值，默认为equal
    输出：
    df_contract_weight
    tradedate code factor_value signal   weight
    20160106   A      0.5         1       0.5
    """
    def _get_equal_weight(df):
        df['weight'] = 0.5 / df.shape[0]
        return df

    def _get_cv_weight(df):
        cv_sum = (1 / df['cv']).sum()
        df['weight'] = (1 / df['cv']) / cv_sum
        return df

    if method == 'equal':
        df_contract = df_contract.groupby(['date', 'signal'],
                                          as_index=True).apply(_get_equal_weight).reset_index()
        df_contract_weight = df_contract
    elif method == 'cv':
        df_contract = pd.merge(df_contract, df_cv, on=['date', 'code'],
                               how='inner')
        df_contract = df_contract.groupby(['date'],
                                          as_index=True).apply(_get_cv_weight).reset_index()
        df_contract_weight = df_contract
    else:
        pass
    return df_contract_weight


# ------------------------------------------------
# 因子收益计算函数
# ------------------------------------------------
def _cal_return(
        df_main,  # 主力合约
        df_contract_weight  # 合约权重
):
    """
        输入：
        df_contract_weight
        tradedate code  factor_name signal  weight
        20160106   A     0.5         1       0.5
        输出：
        df_factor_return的例子：
        tradedate  factor_name
        20160106     0.01
        20160107    -0.01
        """
    name = df_contract_weight.columns[2]
    df_contract_weight = pd.merge(df_contract_weight,
                                  df_main[['date', 'code', 'return']],
                                  on=['date', 'code'], how='left')

    def _inner_cal_factor_return(df):
        factor_return = df['signal'] * df['weight'] * df['return']
        return factor_return

    df_contract_weight[name] = df_contract_weight.apply(
        _inner_cal_factor_return, axis=1)
    df_factor_return = df_contract_weight.groupby(['date'])[name]. \
        sum().reset_index()
    return df_factor_return

# ------------------------------------------------
# 因子回测，计算因子收益率
# ------------------------------------------------
def ctaFactAnal_calSingleFactorReturn(
        factor_name,  # 因子名
        df_factor,  # 因子值
        df_main,  # 主力合约
        df_wave,  # 波动率
        kind,  # 截面因子为'cross',时序因子为'series'
        ascending=1,  # 是否是反向因子，若1为正向 0为负向
        high=1,  # 多头阈值
        low=1,  # 空头阈值
        method='cv',  # 权重分配方式，'cv'代表按照波动率进行分配权重
        shift_window=2 # 默认延迟2天，T日因子用于决定T+1日仓位，T+2日计算T+1到T+2日的收益
):
    df_factor_copy = df_factor.copy(deep=True)
    df_wave_copy = df_wave.copy(deep=True)
    df_factor_copy[df_factor_copy.columns[2]] = df_factor_copy.sort_values(by='date').groupby('code')[df_factor_copy.columns[2]].shift(shift_window)
    df_wave_copy['cv'] = df_wave_copy.sort_values(by='date').groupby('code')['cv'].shift(shift_window)
    df_factor_copy = df_factor_copy.dropna(subset=[df_factor_copy.columns[2]])
    df_wave_copy = df_wave_copy.dropna(subset=['cv'])
    factor_concract = _select_contract(df_factor_copy, kind=kind, ascending=ascending, high=high, low=low)
    factor_contract_weight = _weight_distribution(factor_concract, method=method, df_cv=df_wave_copy)
    factor_return = _cal_return(df_main, factor_contract_weight)
    factor_contract_weight = pd.merge(factor_contract_weight,
                                      df_main[['date', 'code', 'return']],
                                      on=['date', 'code'],
                                      how='inner')
    factor_contract_info = pd.merge(factor_contract_weight, pd.DataFrame(list(const.FUTURES_SECTOR_DICT.items()), columns=['code', 'type']), on=['code'], how='left').dropna()
    factor_return.rename(columns={'code': factor_name + '_' + kind}, inplace=True)
    factor_contract_info.rename(columns={factor_name: 'factor_value'}, inplace=True)
    factor_contract_info['factor_name'] = factor_name
    factor_contract_info['factor_return_code'] = factor_name + '_' + kind
    return factor_contract_info, factor_return

# ------------------------------------------------
# 根据开始和结束日期，获取数据、计算因子，计算因子收益率，返回
# factor_mat_meltform, factor_return_day, factor_return_info，分别为期货因子，因子日度收益率，因子收益计算信息
# ------------------------------------------------
def ctaFactAnal_calCtaFactors(
    df_all, # 所有合约行情
    df_warehouse_data # 库存信息
):
    # 获取计算所需数据
    # 计算因子
    shift_window = 0
    # 125日 标准差
    df_wave = ctaFactAnal_factorStd(df_all, 125, 0)
    df_wave.rename(columns={'wave_125': 'cv'}, inplace=True)

    #   因子、收益、回测信息字典
    dict_factor_df = {}
    # 具体计算每个因子取值
    # 5日波动率
    print('Step 2.1 5日波动率因子计算')
    dict_factor_df['df_wave_5'] = ctaFactAnal_factorVar(df_all, 5, shift_window)

    # 22日波动率
    print('Step 2.2 22日波动率因子计算')
    dict_factor_df['df_wave_22'] = ctaFactAnal_factorVar(df_all, 22, shift_window)

    # 255日流动性因子
    print('Step 2.3 255日流动性因子计算')
    dict_factor_df['df_fluidity_255'] = ctaFactAnal_factorFluidity(df_all, 255, shift_window)

    # 5日动量因子
    print('Step 2.4 5日动量因子计算')
    dict_factor_df['df_momentum_5'] = ctaFactAnal_factorMomentum(df_all, 5, shift_window)

    # 22日动量因子
    print('Step 2.6 22日动量因子计算')
    dict_factor_df['df_momentum_22'] = ctaFactAnal_factorMomentum(df_all, 22, shift_window)

    # 66日动量因子
    print('Step 2.7 66日动量因子计算')
    dict_factor_df['df_momentum_66'] = ctaFactAnal_factorMomentum(df_all, 66, shift_window)

    # 256日偏度因子
    print('Step 2.8 256日偏度因子计算')
    dict_factor_df['df_skew_256'] = ctaFactAnal_factorSkew(df_all, 256, shift_window)

    # 5日基差动量因子
    print('Step 2.9 5日基差动量因子计算')
    dict_factor_df['df_basis_momentum_5'] = ctaFactAnal_factorBasisMomentum(df_all, 5, shift_window)

    # 22日基差动量因子
    print('Step 2.10 22日基差动量因子计算')
    dict_factor_df['df_basis_momentum_22'] = ctaFactAnal_factorBasisMomentum(df_all, 22, shift_window)

    # 展期收益率因子
    print('Step 2.11 展期收益率因子计算')
    dict_factor_df['df_carry'] = ctaFactAnal_factorCarry(df_all, 5, shift_window)

    # 价值因子
    print('Step 2.12 价值因子计算')
    dict_factor_df['df_value'] = ctaFactAnal_factorValue(df_all, shift_window)

    # 库存因子
    print('Step 2.13 库存因子计算')
    dict_factor_df['df_warehouse'] = ctaFactAnal_factorWarehouse(df_warehouse_data, shift_window)

    # 期限结构因子计算
    print('Step 2.14 期限结构因子计算')
    dict_factor_df['df_term_structure'] = ctaFactAnal_factorTerm(df_all, 5, shift_window)

    list_temp = [f.set_index(['date', 'code']) for f in dict_factor_df.values()]
    factor_mat = pd.concat(list_temp, axis=1)
    factor_mat_meltform = factor_mat.reset_index().melt(id_vars=['date', 'code'], var_name='factor_name', value_name='factor_value')

    # 把因子合并到一起
    factor_mat_meltform['factor_type'] = 'CTA'
    factor_mat_meltform['data_source'] = 'CITICSAM'
    factor_mat_meltform['freq'] = 'D'
    factor_mat_meltform['updatetime'] = datetime.datetime.today()
    factor_mat_meltform['date'] = pd.to_datetime(factor_mat_meltform['date']).dt.date

    return dict_factor_df, factor_mat_meltform

# ------------------------------------------------
# 主要函数，根据开始和结束日期，获取数据、计算因子，计算因子收益率，返回
# factor_mat_meltform, factor_return_day, factor_return_info，分别为期货因子，因子日度收益率，因子收益计算信息
# ------------------------------------------------
def ctaFactAnal_calCtaFactorReturns(
    df_all,
    df_main,
    dict_cta_factors
):

    # 因子分层阈值
    high = config.CTA_factor_long_short_threshold['high_threshold']
    low = config.CTA_factor_long_short_threshold['low_threshold']
    # 125日 标准差
    df_wave = ctaFactAnal_factorStd(df_all, 125, 0)
    df_wave.rename(columns={'wave_125': 'cv'}, inplace=True)

    #   因子、收益、回测信息字典
    dict_factor_return = {}
    dict_factor_return_info = {}
    # 具体计算每个因子取值
    # 5日波动率
    print('Step 3.1 5日波动率因子收益计算')
    dict_factor_return_info['df_wave_5'], dict_factor_return['df_wave_5'] = ctaFactAnal_calSingleFactorReturn('wave_5', dict_cta_factors['df_wave_5'], df_main, df_wave, kind='cross', ascending=1, high=high, low=low)
    # 22日波动率
    print('Step 3.2 22日波动率因子收益计算')
    dict_factor_return_info['df_wave_22'], dict_factor_return['df_wave_22'] = ctaFactAnal_calSingleFactorReturn('wave_22', dict_cta_factors['df_wave_22'], df_main, df_wave, kind='cross', ascending=1, high=high, low=low)
    # 255日流动性因子
    print('Step 3.3 255日流动性因子收益计算')
    dict_factor_return_info['df_fluidity_255'], dict_factor_return['df_fluidity_255'] = ctaFactAnal_calSingleFactorReturn('fluidity_255', dict_cta_factors['df_fluidity_255'], df_main, df_wave, kind='cross', ascending=1, high=high, low=low)
    # 5日动量因子截面收益率
    print('Step 3.4 5日动量因子截面收益计算')
    dict_factor_return_info['df_momentum_5_cross'], dict_factor_return['df_momentum_5_cross'] = ctaFactAnal_calSingleFactorReturn('momentum_5', dict_cta_factors['df_momentum_5'], df_main, df_wave, kind='cross', ascending=1, high=high, low=low)
    # 5日动量因子时序收益率
    print('Step 3.5 5日动量因子时序收益计算')
    dict_factor_return_info['df_momentum_5_series'], dict_factor_return['df_momentum_5_series'] = ctaFactAnal_calSingleFactorReturn('momentum_5', dict_cta_factors['df_momentum_5'], df_main, df_wave, kind='series', ascending=1, high=1, low=1)
    # 22日动量因子截面收益率
    print('Step 3.6 22日动量因子截面收益计算')
    dict_factor_return_info['df_momentum_22_cross'], dict_factor_return['df_momentum_22_cross'] = ctaFactAnal_calSingleFactorReturn('momentum_22', dict_cta_factors['df_momentum_22'], df_main, df_wave, kind='cross', ascending=1, high=high, low=low)
    # 22日动量因子时序收益率
    print('Step 3.7 22日动量因子时序收益计算')
    dict_factor_return_info['df_momentum_22_series'], dict_factor_return['df_momentum_22_series'] = ctaFactAnal_calSingleFactorReturn('momentum_22', dict_cta_factors['df_momentum_22'], df_main, df_wave, kind='series', ascending=1, high=1, low=1)
    # 66日动量因子截面收益率
    print('Step 3.8 66日动量因子截面收益计算')
    dict_factor_return_info['df_momentum_66_cross'], dict_factor_return['df_momentum_66_cross'] = ctaFactAnal_calSingleFactorReturn('momentum_66', dict_cta_factors['df_momentum_66'], df_main, df_wave, kind='cross', ascending=1, high=high, low=low)
    # 66日动量因子时序收益率
    print('Step 3.9 66日动量因子时序收益计算')
    dict_factor_return_info['df_momentum_66_series'], dict_factor_return['df_momentum_66_series'] = ctaFactAnal_calSingleFactorReturn('momentum_66', dict_cta_factors['df_momentum_66'], df_main, df_wave, kind='series', ascending=1, high=1, low=1)
    # 256日偏度因子
    print('Step 3.10 256日偏度因子收益计算')
    dict_factor_return_info['df_skew_256'], dict_factor_return['df_skew_256'] = ctaFactAnal_calSingleFactorReturn('skew_256', dict_cta_factors['df_skew_256'], df_main, df_wave, kind='cross', ascending=0, high=high, low=low)
    # 5日基差动量因子
    print('Step 3.11 5日基差动量因子收益计算')
    dict_factor_return_info['df_basis_momentum_5'], dict_factor_return['df_basis_momentum_5'] = ctaFactAnal_calSingleFactorReturn('basis_momentum_5', dict_cta_factors['df_basis_momentum_5'], df_main, df_wave, kind='cross', ascending=1, high=high, low=low)
    # 22日基差动量因子
    print('Step 3.12 22日基差动量因子收益计算')
    dict_factor_return_info['df_basis_momentum_22'], dict_factor_return['df_basis_momentum_22'] = ctaFactAnal_calSingleFactorReturn('basis_momentum_22', dict_cta_factors['df_basis_momentum_22'], df_main, df_wave, kind='cross', ascending=1, high=high, low=low)
    # 展期收益率因子
    print('Step 3.13 展期收益率因子收益计算')
    dict_factor_return_info['df_carry'], dict_factor_return['df_carry'] = ctaFactAnal_calSingleFactorReturn('carry', dict_cta_factors['df_carry'], df_main, df_wave, kind='cross', ascending=1, high=high, low=low)
    # 价值因子
    print('Step 3.14 价值因子收益计算')
    dict_factor_return_info['df_value'], dict_factor_return['df_value'] = ctaFactAnal_calSingleFactorReturn('value', dict_cta_factors['df_value'], df_main, df_wave, kind='cross', ascending=1, high=high, low=low)
    # 库存因子
    print('Step 3.15 库存因子收益计算')
    dict_factor_return_info['df_warehouse'], dict_factor_return['df_warehouse'] = ctaFactAnal_calSingleFactorReturn('warehouse', dict_cta_factors['df_warehouse'], df_main, df_wave, kind='cross', ascending=0, high=high, low=low)
    # 期限结构因子
    print('Step 3.16 原始期限结构因子收益计算')
    dict_factor_return_info['df_term_structure'], dict_factor_return['df_term_structure'] = ctaFactAnal_calSingleFactorReturn('term_structure', dict_cta_factors['df_term_structure'], df_main, df_wave, kind='cross', ascending=1, high=high, low=low)

    # 把因子合并到一起
    factor_list = list(dict_factor_return.values())
    for i in range(len(factor_list)):
        if i == 0:
            factor_return_day = factor_list[i]
        else:
            factor_return_day = pd.merge(factor_return_day, factor_list[i], on=['date'], how='inner')

    factor_return_day = factor_return_day.melt(id_vars='date', var_name='factor_name', value_name='factor_return')
    factor_return_info = pd.concat(dict_factor_return_info.values(), axis=0)

    factor_return_day['factor_type'] = 'CTA'
    factor_return_day['data_source'] = 'CITICSAM'
    factor_return_day['freq'] = 'D'
    factor_return_day['updatetime'] = datetime.datetime.today()
    factor_return_day['date'] = pd.to_datetime(factor_return_day['date']).dt.date
    factor_return_info.rename(columns={'code': 'future_id',
     'return': 'future_return',
     'type': 'future_section',
     'factor_return_code': 'factor_return_name',
     'signal': 'signal_flag',
     'cv': 'volatility'}, inplace=True)
    factor_return_info['data_source'] = 'CITICSAM'
    del factor_return_info['index']
    return factor_return_day, factor_return_info


# ------------------------------------------------
# 根据开始和结束日期，获取数据、计算因子，计算因子收益率，返回
# 因子日度收益率，分别为期货因子，因子收益计算信息
# ------------------------------------------------
def ctaFactAnal_cacheCtaFactorAndReturns(
    date_start,  # 开始日期
    date_end,  # 结束日期
    insert=False # 是否写入数据库
):
    #获取计算所需数据
    data_start_date = date_start - datetime.timedelta(days=450)
    print('获取数据开始日期：', data_start_date)
    print('Step 1 获取原始数据')
    dict_data = ctaData.cta_getFactorsCalculationData(data_start_date, date_end)
    df_all_contract = dict_data['all_contract']  #行情信息
    df_main_contract = dict_data['main_contract']
    df_warehouse_data = dict_data['warehouse_data']    #库存信息

    print('Step 2 CTA因子计算')
    dict_factor_df, factor_mat_meltform = ctaFactAnal_calCtaFactors(df_all_contract, df_warehouse_data)

    print('Step 3 CTA因子收益率计算')
    factor_return, factor_return_info = ctaFactAnal_calCtaFactorReturns(df_all_contract, df_main_contract, dict_factor_df)
    factor_mat_meltform_insert = factor_mat_meltform.loc[(factor_mat_meltform['date'] >= date_start) & (factor_mat_meltform['date'] <= date_end), ]
    factor_return_insert = factor_return.loc[(factor_return['date'] >= date_start) & (factor_return['date'] <= date_end), ]
    factor_return_info_insert = factor_return_info.loc[(factor_return_info['date'] >= date_start) & (factor_return_info['date'] <= date_end), ]
    factor_return_insert = factor_return_insert.fillna(value='None')
    factor_mat_meltform_insert = factor_mat_meltform_insert.fillna(value='None')
    factor_return_info_insert = factor_return_info_insert.fillna(value='None')

    if insert and len(factor_return_insert) > 0:
        print('Step 4 清理数据库缓存')
        conn = irm.irm_connectIRMDB()
        sql = "DELETE FROM irm.factor_value_table WHERE date>= DATE'{0}' and date <= DATE'{1}' and data_source = 'CITICSAM'"
        sql = sql.format(date_start.strftime('%Y-%m-%d'), date_end.strftime('%Y-%m-%d'))
        sql2 = "DELETE FROM irm.factor_return_table WHERE date>= DATE'{0}' and date <= DATE'{1}' and data_source = 'CITICSAM'"
        sql2 = sql2.format(date_start.strftime('%Y-%m-%d'), date_end.strftime('%Y-%m-%d'))
        sql3 = "DELETE FROM irm.amfof_factor_return_info_cta WHERE date>= DATE'{0}' and date <= DATE'{1}' and data_source = 'CITICSAM'"
        sql3 = sql3.format(date_start.strftime('%Y-%m-%d'), date_end.strftime('%Y-%m-%d'))
        cur = conn.cursor()
        cur.execute(sql)
        cur.execute(sql2)
        cur.execute(sql3)
        conn.commit()

        print('Step 5 因子和因子收益率写入数据库')
        irm.irm_insertIRMData(factor_mat_meltform_insert, 'irm.factor_value_table')
        irm.irm_insertIRMData(factor_return_insert, 'irm.factor_return_table')
        irm.irm_insertIRMData(factor_return_info_insert, 'irm.amfof_factor_return_info_cta')
        print('数据缓存成功')

    return {'factor_return': factor_return_insert, 'factor_return_info': factor_return_info, 'factor_mat_meltform': factor_mat_meltform_insert}






