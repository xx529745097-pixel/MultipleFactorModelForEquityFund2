import pandas as pd
import numpy as np
import datetime
import src.data.custHF as custHF
import src.data.custFOF as custFOF
import src.data.custMF as custMF
import src.data.amdata as am
import src.utils.Calculation as cal
import src.data.wind as wd
import src.data.wind_cached as wind_cached
import src.data.zyyx as zyyx
import src.data.zyyx_cached as zyyx_cached
import src.analysis.universeAnalysis as uniAnal
import src.const as const
from scipy.stats import percentileofscore
import src.utils.fof_calendar as calendar
import itertools

# ------------------------------------------------
# 计算给定策略的基础风险收益指标
# 返回dataframe
# ------------------------------------------------
def basicAnal_calPerformanceStats(
    ids,  # list, id, e.g. ['S0000045', 'S0000053', '000711.OF'], [{'中证500': {'000905.SH': 1}}], 输入指数数据时目前只支持wind
    start_date,  # DateTime.date instance
    end_date,  # DateTime.date instance
    freq,  # 数据频率，D或者W
    fund_type,  # 公募还是私募 "MF" or "HF" or "BM"(单一比较基准) or "COMMINGLE"(合成序列)
    benchmark_id=None,  # e.g. '000905.SH'
    data_level='Strategy',
    strategy_category=None,  # e.g. '500指增'，该参数用来和zyyx的数据对比，计算ranking
    stats=const.const.COMMON_PERF_STATS,  # 函数所需计算的stats list, 默认stats为'period_return', 'annualized_period_return', 'annualized_volatility', 'max_drawdown', 'sharpe_ratio', 'calmar'
    include_holding_amount=False,         # 是否merge上持有规模的信息
    latest_data_filter=False,             # 是否进一步筛选出具有最新数据的策略/产品，默认为否；具有最新数据定义为：距离所选date15个自然日内有数据
):
    assert isinstance(ids, list), "ids需为list"
    assert isinstance(start_date, datetime.date), "date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "date must be an instance of datetime.date"
    assert freq in ("D", "W"), "数据频率只支持D或者W"
    assert fund_type in ("MF", "HF", "BM", "CUSTOMIZED_BM", "COMMINGLE"), "fund_type需为MF或者HF或者BM或者CUSTOMIZED_BM或者COMMINGLE"
    assert data_level in ("Strategy", "Product"), "私募数据只支持策略和产品层面"
    if fund_type in ['BM', 'CUSTOMIZED_BM']:
        assert len(ids) == 1, "对于比较基准的绩效分析暂不支持多个比较基准同时传入"
        assert benchmark_id is None, "对比较基准等指数进行研究时请勿传入额外的benchmark_id"
        assert strategy_category is None, "对比较基准等指数进行分析时请勿传入策略排名相关参数"
    if fund_type == 'COMMINGLE':
        assert len(ids) == 1 and isinstance(ids[0], pd.DataFrame), "对于合成序列的分析暂不支持多个，同时请按照Dataframe格式输入参数"
        assert strategy_category is None, "对比较基准等指数进行分析时请勿传入策略排名相关参数"
    if include_holding_amount:
        assert fund_type == 'HF', "merge持仓规模的功能仅支持HF"

    result = dict()
    if fund_type == "MF":
        assert data_level == 'Product', "公募模式下，data_level仅支持Product层级"
        mf_data = wd.wind_getMFStats(ids, start_date, end_date, stats=['f_avgreturn_day'])
        if len(mf_data) == 0:
            return mf_data
        mf_data = mf_data.pivot_table(index='date', values='f_avgreturn_day', columns='product_id')
        for id in mf_data.columns:
            return_series = mf_data[id].dropna()
            if benchmark_id:
                benchmark_ret_series = wd.wind_getIndexReturn(benchmark_id, start_date, end_date, freq)
                result[id] = cal.basicCal_calPerformanceStats(return_series, freq='D', benchmark_ret_series=benchmark_ret_series, stats=stats)
            else:
                result[id] = cal.basicCal_calPerformanceStats(return_series, freq='D', stats=stats)
    elif fund_type == "HF":
        if data_level == 'Strategy':
            hf_data = custHF.custHF_getStrategyReturn(ids, start_date, end_date, freq)
            hf_data.rename(columns={'strategy_id': 'level_id', 'strategy_name': 'level_name'}, inplace=True)
        else:
            hf_data = custHF.custHF_getProductReturn(start_date, end_date, freq, ids)
            hf_data.rename(columns={'product_id': 'level_id', 'product_name': 'level_name'}, inplace=True)
        if len(hf_data) == 0:
            return hf_data
        hf_data = hf_data.pivot_table(index='date', values='adj_return_rate', columns='level_id')
        for id in hf_data.columns:
            return_series = hf_data[id].dropna()
            if benchmark_id:
                benchmark_ret_series = wd.wind_getIndexReturn(benchmark_id, start_date, end_date, freq)
                result[id] = cal.basicCal_calPerformanceStats(return_series, freq, benchmark_ret_series=benchmark_ret_series, stats=stats)
            else:
                result[id] = cal.basicCal_calPerformanceStats(return_series, freq, stats=stats)
    elif fund_type == "BM":   # BM分析模式
        bm_return_data = pd.DataFrame(wd.wind_getIndexReturn(ids[0], start_date, end_date, freq))
        for id in bm_return_data.columns:
            return_series = bm_return_data[id].dropna()
            result[id] = cal.basicCal_calPerformanceStats(return_series, freq, stats=stats)
    elif fund_type == "CUSTOMIZED_BM":   # BM分析模式
        bm_return_data = wind_cached.windCached_getCustomizedIndexReturn(ids[0], start_date, end_date, freq)
        return_series = bm_return_data[['date', 'index_return']].rename(columns={'index_return': ids[0]}).set_index('date')[ids[0]]
        result[ids[0]] = cal.basicCal_calPerformanceStats(return_series, freq, stats=stats)
    elif fund_type == "COMMINGLE":   # 合成序列的分析模式
        commingle_return_data = basicAnal_getCommingledSeriesReturn(ids[0], start_date, end_date, freq, benchmark=benchmark_id)
        commingle_return_pivot = commingle_return_data.pivot_table(index='date', values='adj_return_rate', columns='id')
        for id in commingle_return_pivot.columns:
            return_series = commingle_return_pivot[id].dropna()
            if benchmark_id:
                commingle_bm_return_pivot = commingle_return_data.pivot_table(index='date', values='bm_adj_return_rate', columns='id').add_suffix('_benchmark')
                benchmark_return_series = commingle_bm_return_pivot[id+'_benchmark'].dropna()
                result[id] = cal.basicCal_calPerformanceStats(return_series, freq, benchmark_ret_series=benchmark_return_series, stats=stats)
            else:
                result[id] = cal.basicCal_calPerformanceStats(return_series, freq, stats=stats)

    if strategy_category:
        assert fund_type == 'HF', '添加收益排名时，只支持私募进行zyyx的比较'
        assert freq == 'W', '添加收益排名时，只能使用周频数据'
        zyyx_strategy_category = const.const.AMDATA_DB_TO_THIRD_PARTY_DB_MAP[strategy_category]
        zyyx_product_stats = uniAnal.univAnls_getUnivProductCustomizedPeriodReturn(start_date, end_date, zyyx_strategy_category)
        zyyx_return_array = zyyx_product_stats.groupby(by=['manager'], as_index=False)['period_return'].median()['period_return']
        if benchmark_id:
            bm_year_return = cal.basicCal_getPeriodReturn(benchmark_ret_series, freq, annualized=False)
            zyyx_return_array = zyyx_return_array - bm_year_return
        for id in result.keys():
            result[id]['period_return_rank'] = percentileofscore(zyyx_return_array, result[id]['period_return'], kind='rank') / 100

    df = pd.DataFrame.from_dict(result).T
    df.reset_index(inplace=True)
    df.rename(columns={'index': 'id'}, inplace=True)
    # 是否需要在表格后merge上持仓的规模
    if include_holding_amount:
        level_cols_mapping = {
            'Product': {'id': 'product_id', 'name': 'product_name'},
            'Strategy': {'id': 'strategy_id', 'name': 'strategy_name'},
        }
        FOF_holding = custFOF.custFOF_getFOFHoldingData(end_date, end_date)
        hf_product_info = custHF.custHF_getProductInfo()[['product_id', 'strategy_id', 'strategy_name', 'company_id', 'company_short_name']]
        FOF_holding = pd.merge(FOF_holding, hf_product_info, how='left', on='product_id')  # 将策略、公司级信息拼接上
        grouped_holding = FOF_holding.groupby([level_cols_mapping[data_level]['id']], as_index=False).sum(). \
                            rename(columns={level_cols_mapping[data_level]['id']: 'id', 'product_NAV': 'holding_NAV'})
        df = pd.merge(df, grouped_holding[['id', 'holding_NAV']], on='id', how='left')
    if latest_data_filter:
        df = df[df['end_date'] >= end_date - datetime.timedelta(15)]
    return df

# ------------------------------------------------
# 计算给定私募策略的月度收益
# freq=W时结果可能不太准确，例：2022年2月周五为4，11，18和25日，计算2月的收益时实际使用了1月28日到2月25日的净值
# ------------------------------------------------
def basicAnal_calHFMonthlyReturn(
    ids,  # list, 策略id, e.g. ['S0000045', 'S0000053']
    start_date,  # DateTime.date instance
    end_date,  # DateTime.date instance
    freq='D',  # 数据频率，D或者W
    benchmark_id=None,  # e.g. '000905.SH'
    data_level='Strategy'
):
    assert isinstance(ids, list), "startegy_ids需为list"
    assert isinstance(start_date, datetime.date), "date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "date must be an instance of datetime.date"
    assert freq in ("D", "W"), "数据频率只支持D或者W"
    assert data_level in ("Strategy", "Product"), "私募数据只支持策略和产品层面"

    if benchmark_id:
        level_data = custHF.custHF_getHFReturn(ids, start_date, end_date, freq, data_level)
        level_data.set_index('date', inplace=True)
        benchmark_ret_series = wd.wind_getIndexReturn(benchmark_id, start_date, end_date, freq=freq)
        level_data = pd.merge(level_data, benchmark_ret_series, left_index=True, right_index=True, how='left')

        result = list()
        for id in ids:
            return_series = level_data.loc[level_data['level_id'] == id, 'adj_return_rate']
            monthly_return = cal.basicCal_getCalendarPeriodReturn(return_series, 'M')
            bm_return_series = level_data.loc[level_data['level_id'] == id, benchmark_id]
            bm_monthly_return = cal.basicCal_getCalendarPeriodReturn(bm_return_series, 'M')
            monthly_return=monthly_return-bm_monthly_return
            if not monthly_return.empty:
                monthly_return = monthly_return.to_frame(id)
                result.append(monthly_return)
        result = pd.concat(result, axis=1, join='outer').sort_index(ascending=False)

    else:
        level_data = custHF.custHF_getHFReturn(ids, start_date, end_date, freq, data_level)
        level_data.set_index('date', inplace=True)

        result = list()
        for id in ids:
            return_series = level_data.loc[level_data['level_id'] == id, 'adj_return_rate']
            monthly_return = cal.basicCal_getCalendarPeriodReturn(return_series, 'M')
            if not monthly_return.empty:
                monthly_return = monthly_return.to_frame(id)
                result.append(monthly_return)
        result = pd.concat(result, axis=1, join='outer').sort_index(ascending=False)


    result['data_freq'] = freq
    result['benchmark_id'] = benchmark_id
    return result

# ------------------------------------------------
# 计算给定私募策略的周度收益
# freq=W时结果可能不太准确，例：2022年2月周五为4，11，18和25日，计算2月的收益时实际使用了1月28日到2月25日的净值
# ------------------------------------------------
def basicAnal_calHFWeeklyReturn(
    ids,  # list, 策略id, e.g. ['S0000045', 'S0000053']
    start_date,  # DateTime.date instance
    end_date,  # DateTime.date instance
    freq='D',  # 数据频率，D或者W
    benchmark_id=None,  # e.g. '000905.SH'
    data_level='Strategy'
):
    assert isinstance(ids, list), "startegy_ids需为list"
    assert isinstance(start_date, datetime.date), "date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "date must be an instance of datetime.date"
    assert freq in ("D", "W"), "数据频率只支持D或者W"
    assert data_level in ("Strategy", "Product"), "私募数据只支持策略和产品层面"

    level_data = custHF.custHF_getHFReturn(ids, start_date, end_date, freq, data_level)
    level_data.set_index('date', inplace=True)
    result = list()
    for id in ids:
        return_series = level_data.loc[level_data['level_id'] == id, 'adj_return_rate']
        weekly_return = cal.basicCal_getCalendarPeriodReturn(return_series, 'W')
        if not weekly_return.empty:
            weekly_return = weekly_return.to_frame(id)
            result.append(weekly_return)
    result = pd.concat(result, axis=1, join='outer').sort_index(ascending=False)
    if benchmark_id:
        benchmark_ret_series = wd.wind_getIndexReturn(benchmark_id, start_date, end_date, freq='D')
        bm_weekly_return = cal.basicCal_getCalendarPeriodReturn(benchmark_ret_series, 'W')
        bm_weekly_return = bm_weekly_return.to_frame(benchmark_id)
        _df = pd.merge(result, bm_weekly_return, left_index=True, right_index=True, how='left')
        for strategy in result.columns:
            result[strategy] = _df[strategy] - _df[benchmark_id]
    result['data_freq'] = freq
    result['benchmark_id'] = benchmark_id
    return result

# ------------------------------------------------
# 计算给定公募策略的月度收益
# freq=W时结果可能不太准确，例：2022年2月周五为4，11，18和25日，计算2月的收益时实际使用了1月28日到2月25日的净值
# ------------------------------------------------
def basicAnal_calMFMonthlyReturn(
    ids,  # list, 策略id, e.g. ['S0000045', 'S0000053']
    start_date,  # DateTime.date instance
    end_date,  # DateTime.date instance
    freq='D',  # 数据频率，D或者W
    benchmark_id=None,  # e.g. '000905.SH'
    data_level='Strategy'
):
    assert isinstance(ids, list), "startegy_ids需为list"
    assert isinstance(start_date, datetime.date), "date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "date must be an instance of datetime.date"
    assert freq in ("D", "W"), "数据频率只支持D或者W"
    assert data_level in ("Strategy", "Product"), "私募数据只支持策略和产品层面"

    level_data = custMF.custMF_getMFReturn(ids, start_date, end_date, freq, data_level)
    level_data.set_index('date', inplace=True)
    result = list()
    for id in ids:
        return_series = level_data.loc[level_data['level_id'] == id, 'adj_return_rate']
        monthly_return = cal.basicCal_getCalendarPeriodReturn(return_series, 'M')
        if not monthly_return.empty:
            monthly_return = monthly_return.to_frame(id)
            result.append(monthly_return)
    result = pd.concat(result, axis=1, join='outer').sort_index(ascending=False)
    if benchmark_id:
        benchmark_ret_series = wd.wind_getIndexReturn(benchmark_id, start_date, end_date, freq=freq)
        bm_monthly_return = cal.basicCal_getCalendarPeriodReturn(benchmark_ret_series, 'M')
        bm_monthly_return = bm_monthly_return.to_frame(benchmark_id)
        _df = pd.merge(result, bm_monthly_return, left_index=True, right_index=True, how='left')
        for strategy in result.columns:
            result[strategy] = _df[strategy] - _df[benchmark_id]
    result['data_freq'] = freq
    result['benchmark_id'] = benchmark_id
    return result

# ------------------------------------------------
# 计算给定FOF组合的月度收益
# freq=W时结果可能不太准确，例：2022年2月周五为4，11，18和25日，计算2月的收益时实际使用了1月28日到2月25日的净值
# ------------------------------------------------
def basicAnal_calFOFMonthlyReturn(
    ids,  # list, 账户A6_ID
    start_date,  # DateTime.date instance
    end_date,  # DateTime.date instance
    freq='D',  # 数据频率，D或者W
    benchmark_id=None,  # 该参数为None时计算绝对收益，为'FOF_BM'时计算超额收益
    acc_nav=False  # 是否采用累计净值计算，部分FOF账户存在分红，单位净值计算有误的情况下使用
):
    assert isinstance(ids, list), "ids需为list"
    assert isinstance(start_date, datetime.date), "date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "date must be an instance of datetime.date"
    assert freq in ("D", "W"), "数据频率只支持D或者W"
    assert benchmark_id in (None, 'FOF_BM'), "FOF组合的月度收益，benchmark_id仅支持None, 'FOF_BM'"

    account_nav = custFOF.custFOF_getFOFNetValueAndReturn(start_date, end_date, ids, freq, include_benchmark=benchmark_id, acc_nav=acc_nav)
    result = list()
    ret_df = pd.pivot_table(account_nav, index='date', columns='portfolio_id', values='return')
    if benchmark_id:
        bm_ret_df = pd.pivot_table(account_nav, index='date', columns='portfolio_id', values='bm_return')
    for id in ids:
        monthly_return = cal.basicCal_getCalendarPeriodReturn(ret_df[id].dropna(), 'M')
        monthly_return = monthly_return.to_frame(id)
        if benchmark_id:
            bm_monthly_return = cal.basicCal_getCalendarPeriodReturn(bm_ret_df[id].dropna(), 'M')
            bm_monthly_return = bm_monthly_return.to_frame(id + '_benchmark')
            monthly_return = pd.merge(monthly_return, bm_monthly_return, left_index=True, right_index=True, how='left')
            monthly_return[id+'_excess'] = monthly_return[id] - monthly_return[id+'_benchmark']
        result.append(monthly_return)
    result = pd.concat(result, axis=1, join='outer').sort_index(ascending=False)
    result['data_freq'] = freq
    result['benchmark_id'] = benchmark_id
    return result

# ------------------------------------------------
# 计算给定策略的correlation
# ------------------------------------------------
def basicAnal_calCorrelation(
    ids_dict,  # dict, id with fund type, e.g. {'MF': ['000711.OF'], 'HF': ['S0000045', 'S0000053']}，可以只有MF或者HF
    start_date,  # DateTime.date instance
    end_date,  # DateTime.date instance
    freq,  # 数据频率，D或者W
    benchmark=None,  # 用来计算超额 e.g. '885001.WI', '000905.SH'
    specific_order=False  # Specific output orders depends on input orders
):
    assert isinstance(ids_dict, dict), "ids_dict需为dict，例：{'MF': ['000711.OF'], 'HF': ['S0000045', 'S0000053']}"
    assert isinstance(start_date, datetime.date), "date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "date must be an instance of datetime.date"
    assert freq in ("D", "W"), "数据频率只支持D或者W"

    for k in ids_dict.keys():
        assert k in ('MF', 'HF'), 'ids_dict的key只能为MF或者HF'

    if 'MF' in ids_dict.keys():
        mf_ids = ids_dict['MF']
        mf_data = wd.wind_getMFStats(mf_ids, start_date, end_date, stats=['f_avgreturn_day'])
        mf_data = mf_data.pivot_table(index='date', values='f_avgreturn_day', columns='product_id')
        if 'HF' in ids_dict.keys():
            hf_ids = ids_dict['HF']
            hf_data = custHF.custHF_getStrategyReturn(hf_ids, start_date, end_date, freq)
            hf_data = hf_data.pivot_table(index='date', values='adj_return_rate', columns='strategy_id')
            data = pd.merge(hf_data, mf_data, left_index=True, right_index=True, how='outer')
        else:
            data = mf_data
    else:
        hf_ids = ids_dict['HF']
        data = custHF.custHF_getStrategyReturn(hf_ids, start_date, end_date, freq)
        data = data.pivot_table(index='date', values='adj_return_rate', columns='strategy_id')
    if benchmark:
        bm_data = wd.wind_getIndexReturn(benchmark, start_date, end_date, freq)
        bm_data = bm_data.to_frame(benchmark)
        corr_df = data.copy()
        for id in data.columns:
            corr_df[id] = data[id] - bm_data[benchmark]
    else:
        corr_df = data.copy()

    if specific_order:
        id_order = []
        for key in ids_dict:
            id_order = id_order + ids_dict[key]
        id_order = [id for id in id_order if id in corr_df.columns]
        corr_df = corr_df[id_order]

    corr_df = cal.basicCal_Correlation(corr_df)
    return corr_df

# ------------------------------------------------
# 从return复原nav
# 如果是公募直接取净值
# ------------------------------------------------
def basicAnal_returnToNav(
    ids_dict,       # dict, id with fund type, e.g. {'MF': ['000711.OF'], 'HF': ['S0000045', 'S0000053']}，可以只有MF或者HF
    start_date,     # DateTime.date instance
    end_date,       # DateTime.date instance
    freq,           # 数据频率，D或者W
    benchmark=None,
    data_level='Strategy',
    excess_ret=False  # 是否计算超额净值，如果此项为True，benchmark不能为None,且ids_dict仅包含单一产品或单一策略
):
    data = _getFundIntegratedReturn(ids_dict, start_date, end_date, freq, data_level=data_level)
    ret_data = data.copy(deep=True)
    data = (data.fillna(0) + 1).cumprod(axis=0)

    if benchmark is not None:
        if excess_ret is True:
            # 取出id_dict中的id，整理为list
            dicts_value = list(ids_dict.values())
            id_list = list(itertools.chain(*dicts_value))
            assert len(id_list) == 1, "仅允许传入单一产品或策略"

            bm_ret_data = wd.wind_getIndexReturn(benchmark, start_date - datetime.timedelta(days=20), end_date, freq)
            ret_data[benchmark] = bm_ret_data
            bm_ret_data = bm_ret_data.to_frame().reset_index()
            prev_date = bm_ret_data[bm_ret_data['date'] < data.index[0]]['date'].sort_values().to_list()[-1]
            ret_data.loc[prev_date] = 0
            ret_data = ret_data.sort_index()
            ret_data['excess'] = ret_data[id_list[0]]-ret_data[benchmark]
            data = (ret_data+1).cumprod(axis=0)
            data.reset_index(inplace=True)
            ret_data.sort_values(by='date', inplace=True)
        else:
            bm_data = wd.wind_getIndexData(benchmark, start_date - datetime.timedelta(days=20), end_date, freq, method='last')
            prev_date = bm_data[bm_data['date'] < data.index[0]]['date'].sort_values().to_list()[-1]
            data.loc[prev_date] = 1
            data.sort_values(by='date', inplace=True)
            data.reset_index(inplace=True)
            bm_data = bm_data[bm_data['date'] >= prev_date][['date', 'close_price']]
            bm_data['nav'] = bm_data['close_price']/bm_data['close_price'].iloc[0]
            data = data.merge(bm_data[['date', 'nav']], on='date', how='left')
            data.rename(columns={'nav': benchmark}, inplace=True)
    else:
        data.loc[data.index[0]-datetime.timedelta(days=const.const.FREQ_INTERVAL[freq])] = 1
        data.reset_index(inplace=True)
        data.sort_values(by='date', inplace=True)

    return data

# ------------------------------------------------------
# 依照ID获取公募私募产品的return并将freq统一对齐
# 返回 包含日期date, ID product_id, 收益率 adj_return_rate, 数据频率 freq 的dataframe
# ------------------------------------------------------
def basicAnal_adjustFreqOfMFAndHFReturn(
    start_date,     # DateTime.date instance
    end_date,       # DateTime.date instance
    mf_product_ids, # 公募ID list, 可为空
    hf_product_ids  # 私募ID list, 可为空
):
    if mf_product_ids:
        mf_ret_d = wd.wind_getMFStats(mf_product_ids, start_date, end_date, stats=['f_avgreturn_day']).rename(columns={'f_avgreturn_day': 'adj_return_rate'})[['date', 'product_id', 'adj_return_rate']]
    else:
        mf_ret_d = pd.DataFrame(columns=['date', 'product_id', 'adj_return_rate'])
    if hf_product_ids:
        hf_ret_d = custHF.custHF_getProductReturn(start_date, end_date, 'D', hf_product_ids)[['date', 'product_id', 'adj_return_rate']]
        if set(hf_ret_d['product_id'].to_list()) == set(hf_product_ids):
        # 如果私募产品数据freq均为D,则无需统一降频
            all_product_ret = hf_ret_d.append(mf_ret_d)
            all_product_ret['freq'] = 'D'
        else:
        # 如果私募产品数据freq是混合的,则统一降为W
            hf_ret_w = custHF.custHF_getProductReturn(start_date, end_date, 'W', hf_product_ids)[['date', 'product_id', 'adj_return_rate']]
            if set(hf_ret_w['product_id'].to_list()) == set(hf_product_ids):
            # 如果依照周频取数能够全量取出
                mf_ret_w = calendar.calender_convertDailyReturnToWeekly(mf_ret_d, date_column_name='date', return_column_name='adj_return_rate', id_column_name='product_id')
                all_product_ret = hf_ret_w.append(mf_ret_w)
                all_product_ret['freq'] = 'W'
            else:
            # 如果依照周频取数仍无法取出全量数据，说明存在数据缺失
                raise AssertionError("{} 净值数据缺失".format(str(set(hf_product_ids)-set(hf_ret_w['product_id'].to_list()))))
    else:
        all_product_ret = mf_ret_d
        all_product_ret['freq'] = 'D'

    return all_product_ret

# ------------------------------------------------------
# 通过给定策略/产品/BM的权重配置Dataframe来获取合成后的收益率
# 权重配置Dataframe包含四列: series_name: 合成序列的名称（例如信盈稳健基准）, component_id: 成份序列的id（可以是策略产品id或bm的id）,
# component_weight: 成份权重, component_data_source: 成份数据来源，目前只支持wind，后续会支持公私募策略产品等等
# 支持输入多组配置，一并返回为长表
# ------------------------------------------------------
def basicAnal_getCommingledSeriesReturn(
    commingled_df,          # 合成序列成份等信息的Dataframe，格式见函数Header
    start_date,
    end_date,
    freq='D',               # 数据频率，D或者W
    rebalance_freq="D",     # 再平衡的频率，目前只支持日度再平衡
    benchmark=None,         # 是否包括比较基准数据并计算超额曲线。目前只有标准组合支持打开该参数，置为‘COMMINGLE_BM’，其他的请置为None
):
    assert isinstance(commingled_df, pd.DataFrame), "输入合成序列成份信息请输入指定Dataframe格式"
    assert {'series_name', 'component_id', 'component_weight', 'component_data_source'} <= set(commingled_df.columns), \
            "输入合成序列成份Dataframe请包含'series_name', 'component_id', 'component_weight', 'component_data_source'四列"
    assert freq in ("D", "W"), "freq需为D或者W"
    assert rebalance_freq == "D", "目前仅支持日度再平衡"
    if benchmark is not None:
        assert set(commingled_df['series_name'].tolist()) <= set(const.const.STANDARD_PORT_NAME_LIST)

    ret_result = []
    bm_ret_result = []
    # 对每一套配置循环取数
    for series_name in commingled_df['series_name'].unique():
        single_series = commingled_df[commingled_df['series_name'] == series_name]
        single_series_ret = pd.Series()
        benchmark_series_ret = pd.Series()
        # 对单一配置中的component进行循环取数
        for index, row in single_series.iterrows():
            assert row['component_data_source'] in ['wind', 'amdata'], "只支持基于wind的指数计算合成序列的收益或者从研究平台取出后端产品的收益率"
            if row['component_data_source'] == 'wind':
                component_ret = wd.wind_getIndexReturn(row['component_id'], start_date, end_date, freq) * row['component_weight']
                single_series_ret = component_ret if len(single_series_ret) == 0 else (single_series_ret+component_ret)
                if benchmark is not None:
                    benchmark_index_ret = pd.DataFrame(wd.wind_getIndexReturn(row['bm_index_id'], start_date, end_date, freq)).reset_index().rename(columns={row['bm_index_id']: 'adj_return_rate'})
                    benchmark_index_ret = benchmark_index_ret.set_index('date')['adj_return_rate'] * row['component_weight']
                    benchmark_series_ret = benchmark_index_ret if len(benchmark_series_ret) == 0 else (benchmark_series_ret + benchmark_index_ret)
            elif row['component_data_source'] == 'amdata':
                assert 'back_up_index_id' in commingled_df.columns, "使用后端产品数据计算标准组合时，对应产品均应配置好备用指数用于拼接"
                component_ret = custHF.custHF_getHFReturn([row['component_id']], start_date, end_date, freq, data_level='Product')
                backup_index_ret = pd.DataFrame(wd.wind_getIndexReturn(row['back_up_index_id'], start_date, end_date, freq)).reset_index().rename(columns={row['back_up_index_id']: 'adj_return_rate'})
                if not component_ret.empty and end_date >= datetime.date.today() - datetime.timedelta(7):
                    assert end_date <= component_ret['date'].max(), "标准组合中的后端产品数据尚未更新到所选日期，请调整日期参数"
                backup_index_ret = backup_index_ret[~backup_index_ret['date'].isin(component_ret['date'].tolist())]
                component_ret = component_ret.append(backup_index_ret)
                component_ret.sort_values('date', inplace=True)
                component_ret = component_ret.set_index('date')['adj_return_rate'] * row['component_weight']
                single_series_ret = component_ret if len(single_series_ret) == 0 else (single_series_ret + component_ret)
                if benchmark is not None:
                    benchmark_index_ret = pd.DataFrame(wd.wind_getIndexReturn(row['bm_index_id'], start_date, end_date, freq)).reset_index().rename(columns={row['bm_index_id']: 'adj_return_rate'})
                    benchmark_index_ret = benchmark_index_ret.set_index('date')['adj_return_rate'] * row['component_weight']
                    benchmark_series_ret = benchmark_index_ret if len(benchmark_series_ret) == 0 else (benchmark_series_ret + benchmark_index_ret)

        # 按照配置比例进行叠加后，存至变量
        single_series_ret = pd.DataFrame(single_series_ret).reset_index()
        single_series_ret.columns = ['date', 'adj_return_rate']
        single_series_ret['id'] = series_name
        # 如果收益率存在nan值，则所选区间内至少有一个成份缺数，可能导致数据错误，提示并报错
        assert single_series_ret['adj_return_rate'].isnull().sum() == 0, "所选区间内底层指数数据不全（可能是数据暂未更至最新日期或者序列成份的有效数据区间不同导致），请选择更适合的区间。"
        ret_result.append(single_series_ret)
        if benchmark is not None:
            benchmark_series_ret = pd.DataFrame(benchmark_series_ret).reset_index()
            benchmark_series_ret.columns = ['date', 'bm_adj_return_rate']
            benchmark_series_ret['id'] = series_name
            # 如果收益率存在nan值，则所选区间内至少有一个成份缺数，可能导致数据错误，提示并报错
            assert benchmark_series_ret['bm_adj_return_rate'].isnull().sum() == 0, "所选区间内底层指数数据不全（可能是数据暂未更至最新日期或者序列成份的有效数据区间不同导致），请选择更适合的区间。"
            bm_ret_result.append(benchmark_series_ret)

    ret_result = pd.concat(ret_result)
    if benchmark is not None:
        bm_ret_result = pd.concat(bm_ret_result)
        combined_ret_result = pd.merge(ret_result, bm_ret_result, on=['id', 'date'], how='left')
        combined_ret_result['excess_adj_return_rate'] = combined_ret_result['adj_return_rate'] - combined_ret_result['bm_adj_return_rate']
        return combined_ret_result
    else:
        return ret_result

# ------------------------------------------------------
# 通过给定策略/产品/BM的权重配置Dataframe来获取合成后的的净值曲线数据
# 权重配置Dataframe包含四列: series_name: 合成序列的名称（例如信盈稳健基准）, component_id: 成份序列的id（可以是策略产品id或bm的id）,
# component_weight: 成份权重, component_data_source: 成份数据来源，目前只支持wind，后续会支持公私募策略产品等等
# 支持输入多组配置，一并返回为长表
# ------------------------------------------------------
def basicAnal_getCommingledSeriesNav(
    commingled_df,          # 合成序列成份等信息的Dataframe，格式见函数Header
    start_date,
    end_date,
    freq='D',               # 数据频率，D或者W
    rebalance_freq="D",     # 再平衡的频率，目前只支持日度再平衡
    benchmark=None,         # 是否包括比较基准数据并计算超额曲线。目前只有标准组合支持打开该参数，置为‘COMMINGLE_BM’，其他的请置为None
):
    assert isinstance(commingled_df, pd.DataFrame), "输入合成序列成份信息请输入指定Dataframe格式"
    assert {'series_name', 'component_id', 'component_weight', 'component_data_source'} <= set(commingled_df.columns), \
            "输入合成序列成份Dataframe请包含'series_name', 'component_id', 'component_weight', 'component_data_source'四列"
    assert freq in ("D", "W"), "freq需为D或者W"
    assert rebalance_freq == "D", "目前仅支持日度再平衡"

    ret_result = basicAnal_getCommingledSeriesReturn(commingled_df, start_date, end_date, freq, rebalance_freq, benchmark)
    def _get_commingled_series_nav(ret_result, ret_col_name):
        nav_result = ret_result.pivot_table(index='date', values=ret_col_name, columns='id')
        nav_result = (nav_result.fillna(0) + 1).cumprod(axis=0)
        nav_result.loc[nav_result.index[0] - datetime.timedelta(days=const.const.FREQ_INTERVAL[freq])] = 1
        return nav_result
    nav_result = _get_commingled_series_nav(ret_result, 'adj_return_rate')
    if benchmark is not None:
        bm_nav_result = _get_commingled_series_nav(ret_result, 'bm_adj_return_rate')
        excess_nav_result = _get_commingled_series_nav(ret_result, 'excess_adj_return_rate')
        bm_nav_result = bm_nav_result.add_suffix('_benchmark')
        excess_nav_result = excess_nav_result.add_suffix('_excess')
        nav_result = pd.merge(nav_result, bm_nav_result, left_index=True, right_index=True, how='left')
        nav_result = pd.merge(nav_result, excess_nav_result, left_index=True, right_index=True, how='left')
    nav_result = nav_result.sort_index().reset_index()
    return nav_result

# ------------------------------------------------------------
# 计算回撤时序数据
# 目前支持对MF和HF的计算，可以选择是否带有benchmark以及是否计算超额回撤
# ------------------------------------------------------------
def basicAnal_getDrawdownSeries(
    ids_dict,       # dict, id with fund type, e.g. {'MF': ['000711.OF']}; 计算超额时，只有MF或者HF，传入总产品数量为1
    start_date,     # DateTime.date instance
    end_date,       # DateTime.date instance
    freq,           # 数据频率，D或者W
    benchmark,      # 基准, e.g. '885001.WI', '000905.SH, 可为None
    data_level='Strategy',
    excess_ret=False,   # 是否计算超额净值的回撤序列，如果此项为True，benchmark不能为None,且ids_dict仅包含单一产品或单一策略
):
    assert isinstance(ids_dict, dict), "ids_dict需为dict，例：{'MF': ['000711.OF'], 'HF': ['S0000045', 'S0000053']}"
    assert isinstance(start_date, datetime.date), "date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "date must be an instance of datetime.date"
    assert freq in ("D", "W"), "数据频率只支持D或者W"
    ret_data=_getFundIntegratedReturn(ids_dict, start_date,end_date,freq,data_level=data_level)

    if benchmark is not None:
        bm_ret_data = wd.wind_getIndexReturn(benchmark, start_date - datetime.timedelta(days=20), end_date, freq)
        ret_data[benchmark] = bm_ret_data
        ret_data.sort_index(inplace=True, ascending=True)
        if excess_ret:
            # 将dict中的产品或策略代码展开到一个list中
            dicts_value = list(ids_dict.values())
            id_list = list(itertools.chain(*dicts_value))
            assert len(id_list) == 1, "仅允许传入单一产品或策略"
            ret_data['excess'] = ret_data[id_list[0]]-ret_data[benchmark]

    ret_data.sort_index(inplace=True, ascending=True)
    drawdown_df = ret_data.copy(deep=True)
    # 计算各列的回撤序列
    for col in drawdown_df.columns:
        drawdown_df[col] = cal.basicCal_getCurrentDrawdown(ret_data[col], series_mode=True)
    drawdown_df = drawdown_df.sort_index(ascending=True).reset_index()
    drawdown_df['date'] = pd.to_datetime(drawdown_df['date']).dt.date

    return drawdown_df

# ------------------------------------------------------
# 工具函数 - 将展示绝对数值的df转换为展示相对排名(分位)，并将对应的列上色
# 具有灵活性，可指定需要处理的列名，其他不需要处理的保持原样
# ------------------------------------------------------
def basicAnal_Stat2Rank(
    data,  # 输入DataFrame格式的数据每列为同类的数据
    rank_cols,  # dict, key:需要将指标转换为相对排名的列名，value: True则代表值越小越好，排名越靠前，False反之；支持输入多列
):
    assert isinstance(data, pd.DataFrame), "请输入DataFrame格式的数据"
    assert type(rank_cols) == dict, '列名以及排序配置输入格式需为dict'
    assert set(rank_cols.keys()) <= set(list(data.columns)), '列名输入错误'

    data_rank = data.copy(deep=True)
    for col, method in rank_cols.items():
        data_rank[col] = data[col].rank(ascending=method, pct=True)

    return data_rank


# -------------------------------------- 私有函数 ----------------------------------------------------------- #

# ------------------------------------------------------------
# 获取整合好的基金收益率序列DataFrame
# 目前支持对MF和HF的收益率获取,可同时取,最后输出为收益率的pivot_table
# ------------------------------------------------------------
def _getFundIntegratedReturn(
        ids_dict,  # dict, id with fund type, e.g. {'MF': ['000711.OF'], 'HF': ['S0000045', 'S0000053']}
        start_date,  # DateTime.date instance
        end_date,  # DateTime.date instance
        freq,  # 数据频率，D或者W
        data_level='Strategy',
):
    assert isinstance(ids_dict, dict), "ids_dict需为dict，例：{'MF': ['000711.OF'], 'HF': ['S0000045', 'S0000053']}"
    assert isinstance(start_date, datetime.date), "date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "date must be an instance of datetime.date"
    assert 'FOF' not in ids_dict.keys(),"暂不支持FOF"
    assert freq in ("D", "W"), "数据频率只支持D或者W"
    if 'HF' in ids_dict.keys():
        hf_ids = ids_dict['HF']
        hf_data = custHF.custHF_getHFReturn(hf_ids, start_date, end_date, freq, data_level)
        hf_data = hf_data.pivot_table(index='date', values='adj_return_rate', columns='level_id')

        if 'MF' in ids_dict.keys():
            mf_ids = ids_dict['MF']
            mf_data = wd.wind_getMFStats(mf_ids, start_date, end_date, stats=['f_avgreturn_day'])
            mf_data = mf_data.pivot_table(index='date', values='f_avgreturn_day', columns='product_id')
            data = pd.merge(hf_data, mf_data, left_index=True, right_index=True, how='outer')
        else:
            data = hf_data
    else:
        mf_ids = ids_dict['MF']
        data = wd.wind_getMFStats(mf_ids, start_date, end_date, stats=['f_avgreturn_day'])
        data = data.pivot_table(index='date', values='f_avgreturn_day', columns='product_id')

    return data


# ------------------------------------------------
# 计算给定基准序列的月度收益
# ------------------------------------------------
def basicAnal_calBMMonthlyReturn(
    id,  #输入基准id；对于合成序列的分析，输入Dataframe进行配置
    start_date,  # DateTime.date instance
    end_date,  # DateTime.date instance
    freq='D',  # 数据频率，D或者W
    data_type='BM'  # 基准类型 BM,CUSTOMIZED_BM,COMMINGLE
):
    assert isinstance(start_date, datetime.date), "日期变量必须是datetime.date类型"
    assert isinstance(end_date, datetime.date), "日期变量必须是datetime.date类型"
    assert freq in ("D", "W"), "数据频率只支持D或者W"
    assert data_type in ( "BM", "CUSTOMIZED_BM", "COMMINGLE"), "仅支持BM,CUSTOMIZED_BM,COMMINGLE 类型基准"
    if data_type == "BM":   # BM模式
        bm_return_data = pd.DataFrame(wd.wind_getIndexReturn(id, start_date, end_date, freq))
        for bm_id in bm_return_data.columns:
            return_series = bm_return_data[bm_id]
    elif data_type == "CUSTOMIZED_BM":   # CUSTOMIZED_BM模式
        bm_return_data = wind_cached.windCached_getCustomizedIndexReturn(id, start_date, end_date, freq)
        return_series = bm_return_data[['date', 'index_return']].rename(columns={'index_return': id}).set_index('date')[id]
    elif data_type == "COMMINGLE":   # 合成序列模式
        commingle_return_data = basicAnal_getCommingledSeriesReturn(id, start_date, end_date, freq)
        commingle_return_data = commingle_return_data.pivot_table(index='date', values='adj_return_rate', columns='id')
        for bm_id in commingle_return_data.columns:
            return_series = commingle_return_data[bm_id]

    result = cal.basicCal_getCalendarPeriodReturn(return_series, 'M')
    result = result.to_frame()
    result['data_freq'] = freq
    result['benchmark_id'] = data_type
    return result

# ------------------------------------------------
# 计算给定基准序列的月度收益
# ------------------------------------------------
def basicAnal_calCommingleSeriesMonthlyReturn(
    id,  #对于合成序列的分析，输入Dataframe进行配置
    start_date,  # DateTime.date instance
    end_date,  # DateTime.date instance
    freq='D',  # 数据频率，D或者W
    benchmark_id=None,  # e.g. None or COMMINGLE_BM
):
    assert isinstance(start_date, datetime.date), "日期变量必须是datetime.date类型"
    assert isinstance(end_date, datetime.date), "日期变量必须是datetime.date类型"
    assert freq in ("D"), "数据频率只支持D"
    assert benchmark_id in (None, 'COMMINGLE_BM'), "BM, CUSTOMIZED_BM类型，benchmark_id 需为None或者COMMINGLE_BM"

    commingle_return_data = basicAnal_getCommingledSeriesReturn(id, start_date, end_date, freq, benchmark=benchmark_id)
    result = list()
    commingle_return_pivot = commingle_return_data.pivot_table(index='date', values='adj_return_rate', columns='id')
    if benchmark_id:
        commingle_bm_return_pivot = commingle_return_data.pivot_table(index='date', values='bm_adj_return_rate', columns='id')
    for col in commingle_return_pivot.columns:
        monthly_return = cal.basicCal_getCalendarPeriodReturn(commingle_return_pivot[col], 'M')
        monthly_return = monthly_return.to_frame(col)
        if benchmark_id:
            bm_monthly_return = cal.basicCal_getCalendarPeriodReturn(commingle_bm_return_pivot[col], 'M')
            bm_monthly_return = bm_monthly_return.to_frame(col + '_benchmark')
            monthly_return = pd.merge(monthly_return, bm_monthly_return, left_index=True, right_index=True, how='left')
            monthly_return[col + '_excess'] = monthly_return[col] - monthly_return[col + '_benchmark']
        result.append(monthly_return)
    result = pd.concat(result, axis=1, join='outer').sort_index(ascending=False)
    result['data_freq'] = freq
    result['benchmark_id'] = benchmark_id
    return result

# ------------------------------------------------
# 计算给定代码的月度收益
# ------------------------------------------------
def basicAnal_calMonthlyReturn(
    ids,  # list, 策略id, 或合成序列的dataframe e.g. ['S0000045', 'S0000053']
    start_date,  # DateTime.date instance
    end_date,  # DateTime.date instance
    freq='D',  # 数据频率，D或者W
    benchmark_id=None,  # e.g. '000905.SH'
    data_level='Strategy',  # 仅对 HF, MF,计算生效
    data_type='BM',  # 基准类型 BM,CUSTOMIZED_BM,COMMINGLE
    acc_nav=False  # 是否采用累计净值计算，部分FOF账户存在分红，单位净值计算有误的情况下使用
):
    assert isinstance(start_date, datetime.date), "日期变量必须是datetime.date类型"
    assert isinstance(end_date, datetime.date), "日期变量必须是datetime.date类型"
    assert freq in ("D", "W"), "数据频率只支持D或者W"
    assert data_level in ("Strategy", "Product"), "数据只支持策略和产品层面"
    assert data_type in ("BM", "CUSTOMIZED_BM", "COMMINGLE", "HF", "MF", "FOF"), "支持的类型有BM, CUSTOMIZED_BM, COMMINGLE, HF, MF, FOF"
    assert isinstance(ids, list), "输入值为列表"
    if data_type in ("BM", "CUSTOMIZED_BM"):
        assert len(ids) == 1, "BM, CUSTOMIZED_BM类型，输入list中元素仅允许包含1个"
        assert benchmark_id is None, "BM, CUSTOMIZED_BM类型，benchmark_id 需为None"
        result = basicAnal_calBMMonthlyReturn(ids[0],start_date, end_date, freq=freq, data_type=data_type)
    elif data_type == "HF":
        # 调用私募月度收益计算函数
        result = basicAnal_calHFMonthlyReturn(ids, start_date, end_date, freq=freq, benchmark_id=benchmark_id, data_level=data_level)
    elif data_type == "MF":
        # 调用公募月度收益计算函数
        result = basicAnal_calMFMonthlyReturn(ids, start_date, end_date, freq=freq, benchmark_id=benchmark_id, data_level=data_level)
    elif data_type == "FOF":
        # 调用FOF组合月度收益计算函数
        result = basicAnal_calFOFMonthlyReturn(ids, start_date, end_date, freq=freq, benchmark_id=benchmark_id, acc_nav=acc_nav)
    elif data_type == "COMMINGLE":
        # 调用COMMINGLE月度收益计算函数
        assert len(ids) == 1, "COMMINGLE类型，输入list中元素仅允许包含1个"
        assert benchmark_id in (None, 'COMMINGLE_BM'), "COMMINGLE类型，benchmark_id 需为None或者COMMINGLE_BM"
        result = basicAnal_calCommingleSeriesMonthlyReturn(ids[0], start_date, end_date, freq=freq, benchmark_id=benchmark_id)

    return result



