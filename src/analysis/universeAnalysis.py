# ------------------------------------------------------
# 本文档用于关于基金行业的分析
# ------------------------------------------------------

import pandas as pd
import numpy as np
import copy
import src.data.zyyx as zyyx
import src.data.zyyx_cached as zyyx_cached
import src.data.wind as wind
import src.data.amdata as am
import src.data.irm as irm
import src.const as const
import src.data.custMF as custMF
import src.data.custHF as custHF
import src.data.custFOF as custFOF
import src.utils.Calculation as calc
import src.analysis.basicAnalysis as basicAnls
import datetime
from dateutil.relativedelta import relativedelta
import src.utils.Calculation as cal
import src.analysis.portfolioAnalysis as portAnls
import src.config as config
# ------------------------------------------------------
# 增加产品类型的helper函数
# ------------------------------------------------------
def _appendFundTypeHelper(data, data_source, category):
    assert data_source in ['zyyx', 'zyyx_cached', 'wind', 'custMF'], "目前data_source仅支持朝阳永续(zyyx)、朝阳永续缓存数据(zyyx_cached)、万德(wind)以及自定义公募(custMF)"
    if data_source in ['zyyx', 'zyyx_cached', 'custMF']:
        data['type_name'] = category[0]
    else:
        if category == ['2001010901000000', '2001010902010000']:
            data['type_name'] = '偏股型FOF'
        elif category == ['2001010902030000', '2001010903000000']:
            data['type_name'] = '偏债型FOF'
        elif category == ['2001010902010000', '2001010902020000', '2001010902030000', '2001010902040000']:
            data['type_name'] = '混合型FOF'
        elif category == ['2001010101000000', '2001010201000000']:
            data['type_name'] = '偏股型基金'
        elif category == ['2001010204000000']:
            data['type_name'] = '灵活配置型基金'
        elif category == ['2001010101000000', '2001010201000000', '2001010204000000']:
            data['type_name'] = '偏股及灵活配置型基金'
        elif category == ['2001010301000000', '2001010303000000', '2001010304000000']:
            data['type_name'] = '偏债型基金'
        elif category == ['2001010301000000']:
            data['type_name'] = '中长期纯债型基金'
        elif category == ['2001010302000000']:
            data['type_name'] = '短期纯债型基金'
        elif category == ['2001010303000000']:
            data['type_name'] = '混合债券型一级基金'
        elif category == ['2001010304000000']:
            data['type_name'] = '混合债券型二级基金'
        elif category == ['2001010902030000']:
            data['type_name'] = '偏债混合型FOF'
        elif category == ['300指数增强']:
            data['type_name'] = '300指数增强'
        elif category == ['500指数增强']:
            data['type_name'] = '500指数增强'
        elif category == ['低波动组合基金']:
            data['type_name'] = '低波动组合基金'
        elif category == ['中波动组合基金']:
            data['type_name'] = '中波动组合基金'
        elif category == ['高波动组合基金']:
            data['type_name'] = '高波动组合基金'
        elif category == ['低波动管理期货']:
            data['type_name'] = '低波动管理期货'
        elif category == ['中波动管理期货']:
            data['type_name'] = '中波动管理期货'
        elif category == ['高波动管理期货']:
            data['type_name'] = '高波动管理期货'
        else:
            data['type_name'] = '其他'
    return data

# ------------------------------------------------------
# 该函数负责返回一段时间内，某类Wind基金的所有产品的某一给定stat。
# ------------------------------------------------------
def univAnls_getWindUnivStats(
    start_date,
    end_date,
    category,   # input is an array, check const.WIND_SECTOR_CODE_MAP for details.
    stat
):
    product_list = wind.wind_getCurrentProductList(category, exclude_new_product=True, exclude_small_product=True)
    product_list_w_pm = wind.wind_getCurrentProductList(category, include_pm_info=True, exclude_new_product=True, exclude_small_product=True)
    pm_info = product_list_w_pm.groupby(['product_id'])['pm_name'].apply(lambda x: x.str.cat(sep=',')).to_frame().reset_index()
    product_list = product_list.merge(pm_info, how='left', on=['product_id'])
    universe_stats = wind.wind_getMFStats(product_list['product_id'].to_list(), start_date, end_date, [stat])
    universe_stats.dropna(inplace=True)
    universe_stats = universe_stats.merge(product_list[['product_name', 'product_id', 'company_short_name', 'pm_name', 'product_start_date']], on='product_id')
    universe_stats.rename(columns={'company_short_name': 'manager', 'product_start_date': 'start_date'}, inplace=True)
    universe_stats = _appendFundTypeHelper(universe_stats, 'wind', category)
    return universe_stats

# ------------------------------------------------------
# 该函数负责返回一段时间内，某类自定义MF基金的所有产品的某一给定stat。
# ------------------------------------------------------
def univAnls_getCustMFUnivStats(
    start_date,
    end_date,
    category,   # input is an arry of one element that depends on our own MF classification.
    stat
):
    product_list = wind.wind_getCurrentProductList(exclude_new_product=True)
    product_list_w_pm = wind.wind_getCurrentProductList(category, include_pm_info=True, exclude_new_product=True)
    pm_info = product_list_w_pm.groupby(['product_id'])['pm_name'].apply(lambda x: x.str.cat(sep=',')).to_frame().reset_index()
    product_list = product_list.merge(pm_info, how='left', on=['product_id'])
    candidate = custMF.custMF_getCustomizedProductClassifications(category[0])
    universe_stats = wind.wind_getMFStats(candidate['product_id'].to_list(), start_date, end_date, [stat])
    universe_stats.dropna(inplace=True)
    universe_stats = universe_stats.merge(product_list[['product_name', 'product_id', 'company_short_name', 'pm_name']], on='product_id')
    universe_stats.rename(columns={'company_short_name': 'manager'}, inplace=True)
    universe_stats = _appendFundTypeHelper(universe_stats, 'custMF', category)
    return universe_stats

# ------------------------------------------------------
# 对于单一指标，生成Top或Bottom的策略列表
# ------------------------------------------------------
def univAnls_listProductStats(
    as_of_date,
    data_source,
    category,                      # input is an array, for zyyx and custMF, only 1 element is allowed.
    stat,
    order_by_top = True,           # True or False
    rank_num=20,                   # Enter the number you want to get, e.g.,15 means Top 15 or Bottom 15 depends on the above params "order_by_top"
    exclude_small_manager = True   # Exclude or not manager less than 500MM RMB
):
    assert data_source in ['zyyx', 'zyyx_cached', 'wind', 'custMF'], "目前data_source仅支持朝阳永续(zyyx)、朝阳永续缓存数据(zyyx_cached)、万德(wind)以及自定义公募(custMF)"
    if data_source in ['zyyx', 'zyyx_cached']:
        universe_stats = zyyx.zyyx_getProductStats(as_of_date, as_of_date, category[0], stat) if data_source == 'zyyx' else zyyx_cached.zyyxCached_getCachedUnivProductReturn(as_of_date, as_of_date, category, [stat])
        manager_info = zyyx.zyyx_getManagerBasicInfo()
        manager_info = manager_info[['org_name', 'asset_mgt_scale_range']]
        if category[0] == '股票多头':
            universe_stats['manager'] = universe_stats['manager'].apply(lambda x: x.split('__')[0])
        universe_stats = pd.merge(universe_stats, manager_info, how='left', left_on='manager', right_on='org_name')
        universe_stats['公司规模'] = universe_stats['asset_mgt_scale_range'].apply(lambda x: '不详' if np.isnan(x) else const.const.ZYYX_AUM_RNAGE_MAP[str(x)])
        universe_stats.drop(axis=1, columns=['asset_mgt_scale_range', 'org_name'], inplace=True)
        if exclude_small_manager:
            if category[0] == '股票多头':  # 股票多头只保留50亿以上的
                universe_stats = universe_stats[~universe_stats['公司规模'].isin(['不详', '0-5亿', '5-10亿', '10-20亿', '20-50亿'])]
            else:
                universe_stats = universe_stats[~universe_stats['公司规模'].isin(['不详', '0-5亿'])]
    elif data_source == 'wind':
        universe_stats = univAnls_getWindUnivStats(as_of_date, as_of_date, category, stat)
    else:
        universe_stats = univAnls_getCustMFUnivStats(as_of_date, as_of_date, category, stat)

    universe_stats.sort_values(by=stat, ascending=order_by_top == False, inplace=True)
    schema = ['product_id', 'product_name', 'start_date', 'date', 'manager', 'type_name'] + [stat]
    if data_source in ['zyyx', 'zyyx_cached']:
        schema = schema + ['公司规模']
    else:
        schema = schema + ['pm_name']
    universe_stats = universe_stats[schema]
    result = universe_stats.iloc[:rank_num, ]
    result = _appendFundTypeHelper(result, data_source, category)
    result.reset_index(drop=True, inplace=True)
    return result

# ------------------------------------------------------
# 对于单一指标，生成轮动的分位数序列表格。
# ------------------------------------------------------
def univAnls_getRollingStats(
    start_date,
    end_date,
    data_source,
    category,       # input is an array, for zyyx and custMF, only 1 element is allowed.
    stat,
    percent_array=const.const.ZYYX_UNIV_ROLLING_PLOT,
    include_source_data=False  # 是否包含计算分位数的原始数据
):
    assert data_source in ['zyyx', 'zyyx_cached', 'wind', 'custMF'], "目前data_source仅支持朝阳永续(zyyx)、朝阳永续缓存数据(zyyx_cached)、万德(wind)以及自定义公募(custMF)"
    result = []
    id = 'manager' if data_source in ['zyyx', 'zyyx_cached'] else 'product_name'
    if data_source == 'zyyx':
        universe_stats = zyyx.zyyx_getProductStats(start_date, end_date, category[0], stat)
        universe_stats[stat] = universe_stats[stat].astype(float)
        universe_stats = universe_stats.groupby(by=[id]+['date'], as_index=False)[stat].median()
    elif data_source == 'zyyx_cached':
        assert stat in ['week_return', 'month_return', 'year_return'], "zyyx_cached数据源只支持week_return, month_return, year_return"
        universe_stats = zyyx_cached.zyyxCached_getCachedUnivProductReturn(start_date, end_date, category, [stat])
        universe_stats = universe_stats.groupby(by=[id]+['date'], as_index=False)[stat].median()
    elif data_source == 'wind':
        universe_stats = univAnls_getWindUnivStats(start_date, end_date, category, stat)
    else:
        universe_stats = univAnls_getCustMFUnivStats(start_date, end_date, category, stat)

    for percent in percent_array:
        percent_stats = universe_stats.groupby(by=['date'])[stat].quantile(percent)
        percent_stats.name = str(percent)
        result.append(percent_stats)

    output = pd.concat(result, axis=1)
    universe_count = universe_stats.groupby(by=['date']).count()
    universe_count = universe_count[[id]]
    output = pd.merge(output, universe_count, how='left', left_index=True, right_index=True)
    output.reset_index(inplace=True)
    output.rename(columns={id: 'id_count'}, inplace=True)

    # add type to the output
    output = _appendFundTypeHelper(output, data_source, category)
    if include_source_data:
        return output, universe_stats
    else:
        return output

# --------------------------------------------------------------------------------------------
# 对于给定的时间和一系列指标，生成其分布表格。
# data_source 选择zyyx_cached时，代表：有缓存数据的指标（return类的）从缓存取数，其他的仍从zyyx数据库取数
# --------------------------------------------------------------------------------------------
def univAnls_getUnivStatsDistribution(
    as_of_date,
    data_source,
    category,                                   # input is an array, for zyyx and custMF, only 1 element is allowed.
    stats=['y1_return_a', 'y1_jensen'],         # an array of stat, e.g., ['y1_return_a', 'y1_jensen']
    percent_array=const.const.ZYYX_UNIV_PERF_DISTRIBUTION
):
    assert data_source in ['zyyx', 'zyyx_cached', 'wind', 'custMF'], "目前data_source仅支持朝阳永续(zyyx)、朝阳永续缓存数据(zyyx_cached)、万德(wind)以及自定义公募(custMF)"
    result = []
    if data_source != 'zyyx_cached':
        for stat in stats:
            output = univAnls_getRollingStats(as_of_date, as_of_date, data_source, category, stat, percent_array)
            output['stats_name'] = stat
            result.append(output)
    else:
        # data_source 选择zyyx_cached时，代表：有缓存数据的指标（return类的）从缓存取数，其他的仍从zyyx数据库取数
        for stat in stats:
            if stat in ['week_return', 'month_return', 'year_return']:
                output = univAnls_getRollingStats(as_of_date, as_of_date, data_source, category, stat, percent_array)
            else:
                output = univAnls_getRollingStats(as_of_date, as_of_date, 'zyyx', category, stat, percent_array)
            output['stats_name'] = stat
            result.append(output)

    result = pd.concat(result)
    column_order = ['date', 'type_name', 'stats_name'] + [str(x) for x in percent_array]
    result = result.loc[:, column_order]
    result.reset_index(drop=True, inplace=True)
    return result

# ------------------------------------------------------
# 生成符合条件的产品列表
# ------------------------------------------------------
def univAnls_getQualifiedProducts(
    start_date,
    end_date,
    data_source,
    category,       # input is an array, for zyyx and custMF, only 1 element is allowed.
    stat,
    percentile,   # between 0 and 1, higher is better
    threshold,    # between 0 and 1, higher is better
    exclude_small_manager = True,  # Only works for zyyx, exclude mangager with AUM less than 500MM RMB.
):
    assert data_source in ['zyyx', 'wind', 'custMF'], "目前data_source仅支持朝阳永续(zyyx)、万德(wind)以及自定义公募(custMF)"
    stats_distribution = univAnls_getRollingStats(start_date, end_date, data_source, category, stat, [percentile])
    if data_source == 'zyyx':
        univ_stats = zyyx.zyyx_getProductStats(start_date, end_date, category[0], stat)
    elif data_source == 'wind':
        univ_stats = univAnls_getWindUnivStats(start_date, end_date, category, stat)
    else:
        univ_stats = univAnls_getCustMFUnivStats(start_date, end_date, category, stat)

    univ_stats = pd.merge(univ_stats, stats_distribution, how ='left', left_on='date', right_on='date', suffixes=(None, '_y'))
    univ_stats = univ_stats[ univ_stats[stat] > univ_stats[str(percentile)]]
    product_list = univ_stats.groupby(['product_id'], as_index=False)['date'].count()
    total_num = len(univ_stats['date'].unique())
    product_list['coverage'] = product_list['date']/total_num
    product_list = pd.merge(
        product_list[['product_id', 'coverage']],
        univ_stats[['product_id', 'product_name', 'manager']].drop_duplicates(),
        left_on='product_id',
        right_on='product_id'
    )
    product_list = product_list[product_list['coverage'] >= threshold]
    product_list['stats'] = stat
    if data_source == 'zyyx':  # append manager AUM
        manager_info = zyyx.zyyx_getManagerBasicInfo()
        manager_info['公司规模'] = manager_info['asset_mgt_scale_range'].apply(
            lambda x: '不详' if np.isnan(x) else const.const.ZYYX_AUM_RNAGE_MAP[str(x)])
        manager_info = manager_info[['org_name', '公司规模']]
        if category == '股票多头':
            product_list['manager'] = product_list['manager'].apply(lambda x: x.split('__')[0])
        product_list = pd.merge(product_list, manager_info, how='left', left_on='manager', right_on='org_name')
        del product_list['org_name']
        if exclude_small_manager:
            product_list = product_list[~product_list['公司规模'].isin(['不详', '0-5亿'])]
    product_list.reset_index(drop=True, inplace=True)
    return product_list

# ------------------------------------------------------
# 获取私募月度推荐列表
# ------------------------------------------------------
def univAnls_getHFMontlyRecommandedList(
    end_date,
    category,
    researcher,
    start_date=None
):
    if start_date is None:
        start_date = end_date - relativedelta(months=7)  # 回看月份+1，例如想回看6个月，这里months=7
    data = custHF.custHF_getHFMontlyRecommandedData(start_date, end_date, category, researcher=researcher)
    ref_data = custHF.custHF_getStrategyInfo()
    data = data.merge(ref_data[['strategy_id', 'strategy_name']], on='strategy_id', how='left')
    data.rename(columns={'researcher':'Researcher'}, inplace=True)
    data_list = data.groupby(["date", "Researcher"])["strategy_name"].apply(list)
    data = pd.DataFrame(data_list.tolist(), index=data_list.index).fillna("").T
    return data

# ------------------------------------------------------
# 获取公募模拟组合推荐产品列表，展示每次调仓首日的产品持仓
# ------------------------------------------------------
def univAnls_getMFMockPortRecommendProductList(
    start_date,     # 起始日期
    end_date,       # 截止日期
    mock_port_ids    # list, 模拟组合id
):
    # 展示每次调仓首日的持仓产品列表
    mock_port_holding_data = custMF.custMF_getMockPortHoldingData(start_date=start_date, end_date=end_date, mock_port_ids=mock_port_ids)
    mock_port_holding_compression = mock_port_holding_data.groupby(['date'], as_index=False)['product_id'].agg({'product_id': lambda x: set(x)})
    adjust_dates = mock_port_holding_compression[mock_port_holding_compression['product_id'] != mock_port_holding_compression['product_id'].shift(1)]['date'].to_list()
    mf_recommend_products = mock_port_holding_data[mock_port_holding_data['date'].isin(adjust_dates)]
    return mf_recommend_products

# ------------------------------------------------------
# 获取私募月度截面评级数据
# ------------------------------------------------------
def univAnls_getStrategyRatingSnapshot(
    end_date,
    category,
    rating='A',
    start_date=None
):
    assert rating in ('A', 'A+B')
    end_date = datetime.date(end_date.year, end_date.month, 1)
    if start_date is None:
        start_date = end_date - relativedelta(months=7)  # 回看月份+1，例如想回看6个月，这里months=7
    data = custHF.custHF_getStrategyRatingSnapshot(start_date, end_date)
    data = data[data['date'] >= start_date]
    data['day'] = pd.to_datetime(data['date']).dt.day
    data['year'] = pd.to_datetime(data['date']).dt.year
    data['month'] = pd.to_datetime(data['date']).dt.month
    data = data[data['day']==1]
    date_list = list(data.groupby(['year', 'month'])['date'].min())
    if category in ['主观权益', '套利策略']:
        strategy_info = custHF.custHF_getStrategyInfo(strategy_level_1=[category])
    else:
        strategy_info = custHF.custHF_getStrategyInfo(strategy_level_2=[category])
    rating_list = ['A'] if rating == 'A' else ['A', 'B']
    data = data[(data['date'].isin(date_list)) & (data['strategy_rating'].isin(rating_list)) & (data['strategy_id'].isin(list(strategy_info['strategy_id'])))]
    data['label'] = category
    return data
# ------------------------------------------------------
# 获取私募月度推荐收益序列
# ------------------------------------------------------
def univAnls_getHFMontlyRecommendedListReturn(
    start_date,
    end_date,
    category,
    freq='W',
    data_type='recommend',
    researcher=None,
    rating='A'
):
    if data_type == 'recommend':
        recommended_list = custHF.custHF_getHFMontlyRecommandedData(start_date, end_date, category, researcher)
    elif data_type == 'rating':
        recommended_list = univAnls_getStrategyRatingSnapshot(end_date, category, rating)

    recommended_list['year'] = pd.to_datetime(recommended_list['date']).dt.year
    recommended_list['month'] = pd.to_datetime(recommended_list['date']).dt.month
    del recommended_list['date']
    strategy_ids = recommended_list['strategy_id'].unique().tolist()
    return_data = custHF.custHF_getStrategyReturn(strategy_ids, start_date, end_date, freq)
    return_data['year'] = pd.to_datetime(return_data['date']).dt.year
    return_data['month'] = pd.to_datetime(return_data['date']).dt.month
    return_data = recommended_list.merge(return_data, on=['year', 'month', 'strategy_id'])
    ret = return_data.groupby(['label', 'date'], as_index=False)[['adj_return_rate']].mean()
    ret.sort_values(by='date', inplace=True)
    return ret

# ------------------------------------------------------
# 获取小组、研究员推荐、策略AB库表现情况
# ------------------------------------------------------
def univAnls_getHFMontlyRecommendedListPerfSummary(
    date,
    category,   # 除了主管多头，均为二级标签，500指增等
    start_date=None,
    data_type='recommend',
    researcher=None,
    rating='A'
):
    if start_date is None:
        start = date - relativedelta(months=7)  # 回看月份+1，例如想回看6个月，这里months=7
    else:
        start = start_date
    return_data = univAnls_getHFMontlyRecommendedListReturn(start, date, category, freq='W', data_type=data_type, researcher=researcher, rating=rating)
    if category == '主观权益' or category == '套利策略':
        invest_ids = custHF.custHF_getStrategyInfo(['在库已投'], strategy_level_1=[category])['strategy_id'].to_list()
        track_ids = custHF.custHF_getStrategyInfo(['跟踪'], strategy_level_1=[category])['strategy_id'].to_list()
        invest_track_ids = custHF.custHF_getStrategyInfo(['在库已投', '跟踪'], strategy_level_1=[category])['strategy_id'].to_list()
    else:
        invest_ids = custHF.custHF_getStrategyInfo(['在库已投'], strategy_level_2=[category])['strategy_id'].to_list()
        track_ids = custHF.custHF_getStrategyInfo(['跟踪'], strategy_level_2=[category])['strategy_id'].to_list()
        invest_track_ids = custHF.custHF_getStrategyInfo(['在库已投', '跟踪'], strategy_level_2=[category])['strategy_id'].to_list()

    RL_monthly_return = calc.basicCal_getCalendarPeriodReturn(pd.Series(return_data['adj_return_rate'].values, index=return_data['date']), 'M')
    RL_monthly_return = pd.DataFrame(RL_monthly_return).rename(columns={'return': 'HFMR'})
    final = copy.deepcopy(RL_monthly_return).reset_index()

    id_map = {'invest': invest_ids, 'track': track_ids, 'invest_track': invest_track_ids}
    for type in ['invest', 'track', 'invest_track']:
        temp_monthly_return = basicAnls.basicAnal_calMonthlyReturn(id_map[type], start, date, freq='W', data_type='HF')
        del temp_monthly_return['data_freq'], temp_monthly_return['benchmark_id']
        temp_monthly_return_mean = temp_monthly_return.mean(axis=1, skipna=True)
        temp_monthly_return_mean = pd.DataFrame(temp_monthly_return_mean).reset_index().rename(columns={0: type + '_mean'})
        temp_monthly_return_median = temp_monthly_return.median(axis=1, skipna=True)
        temp_monthly_return_median = pd.DataFrame(temp_monthly_return_median).reset_index().rename(columns={0: type+'_median'})

        # Calculate Rank
        temp_monthly_return = temp_monthly_return.merge(RL_monthly_return, left_index=True, right_index=True)
        temp = temp_monthly_return.T
        temp_monthly_return_rank = ((temp.rank() - 1) / (temp.notna().sum() - 1)).T['HFMR']
        temp_monthly_return_rank = pd.DataFrame(temp_monthly_return_rank).reset_index().rename(columns={'HFMR': type + '_rank'})  # 数字越大越好，1为最好
        final = final.merge(temp_monthly_return_mean, on=['year', 'month'])
        final = final.merge(temp_monthly_return_median, on=['year', 'month'])
        final = final.merge(temp_monthly_return_rank, on=['year', 'month'])

    RL_monthly_return.index = RL_monthly_return.index.to_frame().apply(lambda x: pd.Timestamp(x[0], x[1], 1), axis=1)
    # Fetch Univ Monthly Return
    univ_stat_monthly = zyyx_cached.zyyxCached_getCachedUnivProductReturn(start, date, [const.const.AMDATA_DB_TO_THIRD_PARTY_DB_MAP[category]], ['month_return'])
    univ_stat_monthly['year'] = pd.to_datetime(univ_stat_monthly['date']).dt.year
    univ_stat_monthly['month'] = pd.to_datetime(univ_stat_monthly['date']).dt.month
    univ_stat_monthly = univ_stat_monthly.groupby(['year', 'month', 'manager', 'product_id']).apply(lambda x: x[x['date'] == x['date'].max()]['month_return']).to_frame().reset_index().rename(columns={0: 'month_return'})
    univ_stat_monthly = univ_stat_monthly.groupby(['year', 'month', 'manager'], as_index=False)['month_return'].median()
    univ_stat_monthly.index = univ_stat_monthly.apply(lambda x: pd.Timestamp(x['year'], x['month'], 1), axis=1)
    univ_stat_monthly = univ_stat_monthly.pivot(columns='manager', values='month_return')
    univ_stat_monthly = RL_monthly_return.merge(univ_stat_monthly, left_index=True, right_index=True)

    # Calculate univ median
    univ_stat_monthly_median = univ_stat_monthly.median(axis=1, skipna=True)
    univ_stat_monthly_median = pd.DataFrame(univ_stat_monthly_median).reset_index().rename(columns={0: 'univ_median'})
    univ_stat_monthly_median['year'] = pd.to_datetime(univ_stat_monthly_median['index']).dt.year
    univ_stat_monthly_median['month'] = pd.to_datetime(univ_stat_monthly_median['index']).dt.month
    del univ_stat_monthly_median['index']
    final = final.merge(univ_stat_monthly_median, on=['year', 'month'], how='left')

    # Calculate RL in univ rank
    temp = univ_stat_monthly.T
    univ_monthly_return_rank = ((temp.rank() - 1) / (temp.notna().sum() - 1)).T['HFMR']
    univ_monthly_return_rank = pd.DataFrame(univ_monthly_return_rank).reset_index().rename(columns={'HFMR': 'univ_rank'})  # 数字越大越好，1为最好
    univ_monthly_return_rank['year'] = pd.to_datetime(univ_monthly_return_rank['index']).dt.year
    univ_monthly_return_rank['month'] = pd.to_datetime(univ_monthly_return_rank['index']).dt.month
    del univ_monthly_return_rank['index']
    final = final.merge(univ_monthly_return_rank, on=['year', 'month'], how='left')
    return final

# -------------------------------------------------------------------------
# 获取朝阳永续所有某一类别的所有产品的指定区间的收益率数据 基于本地缓存的week_return进行计算
# 返回: 所有产品的区间收益率dataframe, 包括产品信息、区间信息、freq、period_return列
# -------------------------------------------------------------------------
def univAnls_getUnivProductCustomizedPeriodReturn(
    start_date,
    end_date,
    category,
    data_source='zyyx_cached'
):
    assert data_source == 'zyyx_cached', "计算指定区间收益率功能目前数据源只支持本地缓存的week_return数据"

    all_ret = zyyx_cached.zyyxCached_getCachedUnivProductReturn(start_date, end_date, categories=[category], stats=['week_return'])
    # 筛选 取在start_date前90日以前成立的产品
    all_ret = all_ret[all_ret.start_date <= (start_date - datetime.timedelta(90))]
    ret_pivot = all_ret.pivot_table(values=['week_return'], index=['date'], columns=['product_id', 'product_name', 'manager', 'start_date'])
    # 清除最开始和最后一个日期点有缺失的数据列（结合上面的条件，卡出来的数据认为是有效数据点）
    ret_pivot = ret_pivot.dropna(axis=1, how='any', subset=[ret_pivot.index.max(), ret_pivot.index.min()])
    # 收益率cumprod, 计算得到指定period return
    nav_pivot = (ret_pivot + 1).cumprod()
    result = pd.DataFrame(nav_pivot.iloc[-1] - 1)
    # df整理
    result.columns = ['period_return']
    result = result.reset_index()
    result['period_start_date'] = nav_pivot.index.min()
    result['period_end_date'] = nav_pivot.index.max()
    result['freq'] = 'W'
    result['data_source'] = 'zyyx'
    result['type_name'] = category
    result = result[['product_id', 'product_name', 'manager', 'start_date', 'data_source', 'period_start_date', 'period_end_date', 'type_name', 'freq', 'period_return']]

    return result


# -------------------------------------------------------------------------
# 生成某一类产品自定义区间的风险收益特征分布
# 获取朝阳永续所有某一类别的所有产品的指定区间的产品绩效统计并计算分位数，通过缓存周度收益率计算
# -------------------------------------------------------------------------
def univAnls_getUnivCustomizedPeriodStatsDistribution(
    start_date,     # 开始日期
    end_date,       # 结束日期
    category,       # 产品类别
    stats=['period_return']     # 需要计算的绩效指标
):
    assert isinstance(start_date, datetime.date), "日期变量需为datetime.date 类型"
    assert isinstance(end_date, datetime.date), "日期变量需为datetime.date 类型"
    assert category in ['股票多头', '高波动管理期货', '中波动管理期货', '低波动管理期货', '300指数增强', '500指数增强',
                               '1000指数增强', '股票市场中性', '宏观策略', '套利策略', '高波动组合基金', '中波动组合基金', '低波动组合基金'], "输入分类不支持"
    all_ret = zyyx_cached.zyyxCached_getCachedUnivProductReturn(start_date, end_date, categories=[category], stats=['week_return'])
    # 筛选 取在start_date前90日以前成立的产品
    all_ret = all_ret[all_ret.start_date <= (start_date - datetime.timedelta(90))]
    ret_pivot = all_ret.pivot_table(values=['week_return'], index=['date'], columns=['product_id', 'product_name', 'manager', 'start_date'])
    # 清除最开始和最后一个日期点有缺失的数据列（结合上面的条件，卡出来的数据认为是有效数据点）
    ret_pivot = ret_pivot.dropna(axis=1, how='any', subset=[ret_pivot.index.max(), ret_pivot.index.min()])
    #  计算选定的绩效指标
    df_stats = ret_pivot.apply(cal.basicCal_calPerformanceStats, freq='W', stats=stats)
    df_stats.name = 'stats'
    df_stats = df_stats.reset_index()
    df_stats = df_stats[['product_id', 'product_name', 'manager', 'stats']]
    df_stats = pd.concat([df_stats[['product_id', 'product_name', 'manager']], pd.json_normalize(df_stats['stats'])], axis=1)
    #  对同一私募的同一个基金经理取指标中位数，认为是同策略产品
    universe_stats = df_stats.groupby(by=['manager'], as_index=False)[stats].median()
    percent_array = [str(x) for x in const.const.ZYYX_UNIV_PERF_DISTRIBUTION]
    result = pd.DataFrame(np.nan, columns=percent_array + ['count'], index=stats)
    for stat in stats:
        result.loc[stat, 'count'] = universe_stats[stat].count()
        for percent in percent_array:
            result.loc[stat, percent] = universe_stats[stat].quantile(float(percent))
    result.index.name = 'stats_name'
    result.reset_index(inplace=True)
    result['type_name'] = category
    result['start_date'] = ret_pivot.index.min()
    result['end_date'] = ret_pivot.index.max()
    result = result[['start_date', 'end_date', 'type_name', 'stats_name'] + percent_array]
    return result
# ------------------------------------------------------
# 将多个category的给定分位数的信息汇总的helper函数
# ------------------------------------------------------
def _allCategoryStatsDistributionHelper(
    as_of_date,
    data_source,
    categories,
    stats,
    percent_array=[0.5]
):
    assert data_source in ['zyyx'], "目前data_source仅支持朝阳永续(zyyx)"
    result = []
    for cat in categories:
        output = univAnls_getUnivStatsDistribution(as_of_date, data_source, [cat], stats, percent_array)
        output['data_source'] = data_source
        output = output[['date', 'data_source', 'type_name', 'stats_name']+[str(x) for x in percent_array]]
        result.append(output)
    result = pd.concat(result)
    return result

# ------------------------------------------------------------------------------------------------------
# 将多个category的全部产品的stat信息汇总的helper函数 目前限制只取（或计算）week_return, month_return, year_return 用于缓存数据
# 注：AMFOF_UNIVERSE_PRODUCT_STATS表中目前只有week_return是从zyyx数据库存入,
# 其他stats例如month_return,year_return 是通过week_return计算得到,不是直接自zyyx数据库存入
# ------------------------------------------------------------------------------------------------------
def _allCategoryProductsStatsHelper(
    as_of_date,
    data_source,
    categories,
    stat,
):
    assert data_source in ['zyyx'], "目前data_source仅支持朝阳永续(zyyx)"
    assert stat in ['week_return', 'month_return', 'year_return'], "目前stats只限week_return, month_return, year_return"
    result = []
    print(stat)
    if stat == 'week_return':
        for cat in categories:
            output = zyyx.zyyx_getProductStats(as_of_date, as_of_date, cat, stat)
            output['data_source'] = data_source
            output['stat_name'] = stat
            output['type_name'] = cat
            output['update_time'] = datetime.date.today()
            output = output.rename(columns={stat: 'stat_value'})
            output = output[['date', 'product_id', 'product_name', 'manager', 'start_date', 'data_source', 'type_name', 'stat_name', 'stat_value', 'update_time']]
            result.append(output)
            print(cat)
    elif stat in ['month_return', 'year_return']:
        for cat in categories:
            output = univAnls_getUnivProductCustomizedPeriodReturn(datetime.date(as_of_date.year, as_of_date.month if stat == 'month_return' else 1, 1), as_of_date, cat)
            output['date'] = output['period_end_date']
            output['stat_name'] = stat
            output['stat_value'] = output['period_return']
            output['update_time'] = datetime.date.today()
            output = output[['date', 'product_id', 'product_name', 'manager', 'start_date', 'data_source', 'type_name', 'stat_name', 'stat_value', 'update_time']]
            result.append(output)
            print(cat)

    result = pd.concat(result)
    return result


####################################################################
# WRITE API
####################################################################

# ------------------------------------------------------
# 将categories的stats分布信息存入AMData
# ------------------------------------------------------
def univAnls_cacheZYYXUnivDistribution(
    start_date,                 # DateTime.date instance
    end_date,                   # DateTime.date instance
    stats=['week_return'],      # check perf or risk table, e.g.,t_fund_weekly_performance for stats column names, e.g., y1_return_a
    categories=['300指数增强', '500指数增强', '1000指数增强', '股票市场中性', '低波动管理期货', '中波动管理期货', '高波动管理期货', '宏观策略', '套利策略'],  # list of categories
    percent_array=[0, 0.1, 0.25, 0.33, 0.4, 0.5, 0.6, 0.67, 0.75, 0.9, 1],  # list of quantile percents, please select subset of [0, 0.1, 0.25, 0.33, 0.4, 0.5, 0.6, 0.67, 0.75, 0.9, 1]
    insert=False,
):
    assert isinstance(start_date, datetime.date), "date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "date must be an instance of datetime.date"
    assert set(stats).issubset({'week_return'}), "目前stats只支持week_return"
    assert set(categories).issubset({'300指数增强', '500指数增强', '1000指数增强', '股票市场中性', '低波动管理期货', '中波动管理期货', '高波动管理期货', '宏观策略', '套利策略'}), \
            "categories需为300指数增强,500指数增强,1000指数增强,股票市场中性,低波动管理期货,中波动管理期货,高波动管理期货,宏观策略,套利策略 中的若干项"
    assert set(percent_array).issubset({0, 0.1, 0.25, 0.33, 0.4, 0.5, 0.6, 0.67, 0.75, 0.9, 1}), \
            "percent_array只支持0, 0.1, 0.25, 0.33, 0.4, 0.5, 0.6, 0.67, 0.75, 0.9, 1中的若干数字"
    if insert:
        assert set(percent_array) == {0, 0.1, 0.25, 0.33, 0.4, 0.5, 0.6, 0.67, 0.75, 0.9, 1}, \
            "percent_array insert时必须为全量"

    result = []
    sse_calendar = wind.wind_getSSECalendar()
    sse_calendar_list = sse_calendar['date'].to_list()
    for day_index in range((end_date-start_date).days + 1):
        date = start_date + datetime.timedelta(days=day_index)
        print(date)
        if date.weekday() != 4:  # 周频数据，insert日期均为周五
            continue
        if date in sse_calendar_list:  # 周五是交易日
            df = _allCategoryStatsDistributionHelper(date, 'zyyx', categories, stats, percent_array)
            result.append(df)
        else:  # 周五不是交易日
            last_trade_date = sse_calendar[sse_calendar['date'] <= date].iloc[-1][0]
            if (date - last_trade_date).days > 4:  # 本周内无交易日
                continue
            else:  # 周五非交易日且周内有交易日
                df = _allCategoryStatsDistributionHelper(last_trade_date, 'zyyx', categories, stats, percent_array)
                df['date'] = date
                result.append(df)
    result_df = pd.concat(result)

    if insert:
        # 依照AMFOF.INDEX_YIELD_INFO列名rename
        rename_mapping = {
            'date': 'dt',
            '0': 'n_000',
            '0.1': 'n_010',
            '0.25': 'n_025',
            '0.33': 'n_033',
            '0.4': 'n_040',
            '0.5': 'n_050',
            '0.6': 'n_060',
            '0.67': 'n_067',
            '0.75': 'n_075',
            '0.9': 'n_090',
            '1': 'n_100',
        }
        result_df.rename(columns=rename_mapping, inplace=True)

        # AMDATA数据库
        # Delete existing key if exists
        categories_str = ','.join(["'%s'" % x for x in categories])
        stats_str = ','.join(["'%s'" % x for x in stats])
        conn = am.amdata_connectAmdataDb()
        sql = "DELETE FROM AMFOF.INDEX_YIELD_INFO WHERE DT>=TO_DATE('{0}', 'yyyy-mm-dd') AND DT<=TO_DATE('{1}', 'yyyy-mm-dd') " \
              "AND TYPE_NAME in ({2}) AND STATS_NAME in ({3})"
        sql = sql.format(start_date, end_date, categories_str, stats_str)
        cur = conn.cursor()
        cur.execute(sql)
        conn.commit()

        # Write into database
        am.amdata_insertAMData(result_df, 'AMFOF.INDEX_YIELD_INFO')

        # IRM数据库
        # Delete existing key if exists
        categories_str = ','.join(["'%s'" % x for x in categories])
        stats_str = ','.join(["'%s'" % x for x in stats])
        conn = irm.irm_connectIRMDB()
        sql = "DELETE FROM irm.AMFOF_INDEX_YIELD_INFO WHERE DT>=DATE'{0}' AND DT<=DATE'{1}' " \
              "AND TYPE_NAME in ({2}) AND STATS_NAME in ({3})"
        sql = sql.format(str(start_date), str(end_date), categories_str, stats_str)
        cur = conn.cursor()
        cur.execute(sql)
        conn.commit()

        # Write into database
        irm.irm_insertIRMData(result_df, 'irm.AMFOF_INDEX_YIELD_INFO')


    return result_df

# ---------------------------------------------------------------------------------
# 将products的stats信息存入IRM数据库AMFOF_UNIVERSE_PRODUCT_STATS表
# 注：AMFOF_UNIVERSE_PRODUCT_STATS表中目前只有week_return是从zyyx数据库存入,
# 其他stats例如month_return,year_return 是通过week_return计算得到,不是直接自zyyx数据库存入
# FIXME 目前IT交接阶段，AMDATA和IRM的表同时都存
# ---------------------------------------------------------------------------------
def univAnls_cacheZYYXUnivProductStats(
    start_date,                 # DateTime.date instance
    end_date,                   # DateTime.date instance
    stat='week_return',         # 目前只支持week_return month_return year_return
    categories=['股票多头', '300指数增强', '500指数增强', '1000指数增强', '股票市场中性', '低波动管理期货', '中波动管理期货', '高波动管理期货', '宏观策略', '套利策略', '低波动组合基金', '中波动组合基金', '高波动组合基金'],  # list of categories
    insert=False,
):
    assert isinstance(start_date, datetime.date), "date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "date must be an instance of datetime.date"
    assert stat in ['week_return', 'month_return', 'year_return'], "目前stat只限week_return, month_return, year_return"
    assert set(categories).issubset({'股票多头', '300指数增强', '500指数增强', '1000指数增强', '股票市场中性', '低波动管理期货', '中波动管理期货', '高波动管理期货', '宏观策略', '套利策略', '低波动组合基金', '中波动组合基金', '高波动组合基金'}), \
            "categories需为股票多头,300指数增强,500指数增强,1000指数增强,股票市场中性,低波动管理期货,中波动管理期货,高波动管理期货,宏观策略,套利策略,低波动组合基金,中波动组合基金,高波动组合基金 中的若干项"

    result = []
    sse_calendar = wind.wind_getSSECalendar()
    sse_calendar_list = sse_calendar['date'].to_list()
    for day_index in range((end_date-start_date).days + 1):
        date = start_date + datetime.timedelta(days=day_index)
        print(date)
        if date.weekday() != 4:  # 周频数据，insert日期均为周五
            continue
        if date in sse_calendar_list:  # 周五是交易日
            df = _allCategoryProductsStatsHelper(date, 'zyyx', categories, stat)
            result.append(df)
        else:  # 周五不是交易日
            last_trade_date = sse_calendar[sse_calendar['date'] <= date].iloc[-1][0]
            if (date - last_trade_date).days > 4:  # 本周内无交易日
                continue
            else:  # 周五非交易日且周内有交易日
                df = _allCategoryProductsStatsHelper(last_trade_date, 'zyyx', categories, stat)
                df['date'] = date
                result.append(df)
    result_df = pd.concat(result)

    if insert:
        # 依照数据库列名rename
        result_df.rename(columns={'date': 'dt'}, inplace=True)

        # AMDATA数据库:
        # Delete existing key if exists
        categories_str = ','.join(["'%s'" % x for x in categories])
        stats_str = ','.join(["'%s'" % x for x in [stat]])
        conn = am.amdata_connectAmdataDb()
        sql = "DELETE FROM AMFOF.UNIVERSE_PRODUCT_STATS WHERE DT>=TO_DATE('{0}', 'yyyy-mm-dd') AND DT<=TO_DATE('{1}', 'yyyy-mm-dd') " \
              "AND TYPE_NAME in ({2}) AND STAT_NAME in ({3})"
        sql = sql.format(start_date, end_date, categories_str, stats_str)
        cur = conn.cursor()
        cur.execute(sql)
        conn.commit()

        # Write into database
        am.amdata_insertAMData(result_df, 'AMFOF.UNIVERSE_PRODUCT_STATS')

        # IRM数据库:
        # Delete existing key if exists
        categories_str = ','.join(["'%s'" % x for x in categories])
        stats_str = ','.join(["'%s'" % x for x in [stat]])
        conn = irm.irm_connectIRMDB()
        sql = "DELETE FROM irm.AMFOF_UNIVERSE_PRODUCT_STATS WHERE DT>=DATE'{0}' AND DT<=DATE'{1}' " \
              "AND TYPE_NAME in ({2}) AND STAT_NAME in ({3})"
        sql = sql.format(str(start_date), str(end_date), categories_str, stats_str)
        cur = conn.cursor()
        cur.execute(sql)
        conn.commit()

        # Write into database
        irm.irm_insertIRMData(result_df, 'irm.AMFOF_UNIVERSE_PRODUCT_STATS')

    return result_df

# ------------------------------------------------------
# 获取公募推荐策略损益情况汇总
# ------------------------------------------------------
def univAnls_getMFMockPortRecommendProductAttributionSummary(
    start_date,     # 起始日期
    end_date,       # 截止日期
    mock_port_ids,  # list, 模拟组合id
    benchmark=None  # 基准指数id
):
    mock_port_holding_data = custMF.custMF_getMockPortHoldingData(start_date=start_date, end_date=end_date, mock_port_ids=mock_port_ids)[['date', 'product_id']]
    # 用于纳入推荐产品对应的全部份额，只有存在多个份额的产品才会存在映射表中，否则需要手动将产品代码加入
    mf_related_product_map = wind.wind_getMFRelatedProductMap()
    # 内部函数，获取基金的全部关联份额代码
    def _get_all_related_product_ids(
        product_ids  # list, 产品id
    ):
        current_related_map = mf_related_product_map[mf_related_product_map['initial_product_id'].isin(product_ids) | mf_related_product_map['mapped_product_id'].isin(product_ids)]
        all_related_product_ids = list(set(product_ids + current_related_map['initial_product_id'].to_list() + current_related_map['mapped_product_id'].to_list()))
        return all_related_product_ids
    extended_mock_port_holding_data = mock_port_holding_data.groupby(['date']).apply(lambda x: pd.DataFrame({'product_id': _get_all_related_product_ids(x['product_id'].to_list())})).reset_index()[['date', 'product_id']]
    # 获取区间内已投股票型,偏股混合型和灵活配置型公募基金的产品列表，目的是为了减少持仓查询时传入的产品数量
    hist_holding_product_info = custFOF.custFOF_getFOFHistoricalHoldingProduct(start_date, end_date, include_holding_dates=False)
    equity_mf_product_info = wind.wind_getCurrentProductList(fund_types=['2001010101000000', '2001010201000000', '2001010204000000'], only_a_share=False)
    hist_holding_equity_mf_product_ids = hist_holding_product_info[hist_holding_product_info['product_id'].isin(equity_mf_product_info['product_id'].to_list())]['product_id'].unique().tolist()
    # 根据benchmark确定大类持仓范围，其中行业主题基准库对应基准库的最新全量持仓，非行业主题类基准对应行业主题基准库以外的股票型,偏股混合型和灵活配置型公募基金持仓
    if benchmark in config.mf_mock_port_industry_benchmark_pool_map.values():
        benchmark_pool_product_info = custMF.custMF_getMockPortHoldingData(start_date=end_date, end_date=end_date, mock_port_ids=[benchmark])
        benchmark_pool_extended_product_ids = _get_all_related_product_ids(benchmark_pool_product_info['product_id'].unique().tolist())
        category_product_ids = list(set(hist_holding_equity_mf_product_ids) & set(benchmark_pool_extended_product_ids))
    else:
        benchmark_pool_product_info = custMF.custMF_getMockPortHoldingData(start_date=end_date, end_date=end_date, mock_port_ids=list(config.mf_mock_port_industry_benchmark_pool_map.values()))
        benchmark_pool_extended_product_ids = _get_all_related_product_ids(benchmark_pool_product_info['product_id'].unique().tolist())
        category_product_ids = list(set(hist_holding_equity_mf_product_ids) - set(benchmark_pool_extended_product_ids))
    # 因当前存在少量推荐组合中的ETF基金不在基准库的情况，大类基金池的筛选上需要和推荐组合再取一次并集
    category_product_ids = list(set(category_product_ids) | set(extended_mock_port_holding_data['product_id'].unique().tolist()))
    category_holding = custFOF.custFOF_getFOFCachedHoldingValuationSheet(start_date, end_date, product_id=category_product_ids)
    # 获取模拟组合持仓产品的连续推荐区间
    full_dates = sorted(extended_mock_port_holding_data['date'].unique().tolist())
    product_recommend_interval_info = extended_mock_port_holding_data.groupby(['product_id']).apply(lambda x: pd.DataFrame(_getMFRecommendIntervalList(full_dates, x['date'].to_list()), columns=['interval_start', 'interval_end'])).reset_index()
    result = []
    interval_data_list = []
    # 按推荐区间进行遍历，每次批量处理同一推荐区间的所有产品
    for index, group in product_recommend_interval_info.groupby(['interval_start', 'interval_end'], as_index=False):
        interval_start = group['interval_start'].iloc[0]
        interval_end = group['interval_end'].iloc[0]
        # 计算收益贡献，按产品维度汇总
        df_details, df_sum = portAnls.anlsFOF_getFOFProductAttributionSummary(group['product_id'].to_list(), interval_start, interval_end, data_level='Product', fund_type='MF', benchmark=benchmark)
        df_sum['start_date'] = interval_start
        df_sum['end_date'] = interval_end
        interval_data_list.append(df_sum)
    if len(interval_data_list) > 0:
        interval_data_sum = pd.concat(interval_data_list, axis=0)
        category_holding_value = category_holding.groupby(['date'], as_index=False).agg({'VAL': 'sum'}).rename(columns={'VAL': 'VAL_sum'})
        category_holding_value = pd.merge(extended_mock_port_holding_data[['date', 'product_id']], category_holding_value,
                                     on='date', how='left').groupby('product_id', as_index=False).agg({'VAL_sum': 'mean'}).rename(columns={'VAL_sum': 'category_mean_holding_value'})
        interval_data_sum = interval_data_sum.groupby('product_id', as_index=False).agg(
            {'profit_sum': 'sum', 'product_name': 'first',
             'val_start': 'sum', 'val_end': 'sum', 'buy_vol': 'sum', 'buy_val': 'sum', 'sell_vol': 'sum',
             'sell_val': 'sum', 'start_date': 'min', 'end_date': 'max', 'excess_profit': 'sum', 'benchmark_profit':'sum'})
        interval_data_sum = pd.merge(interval_data_sum, category_holding_value, on='product_id', how='left')
        interval_data_sum['impact_factor'] = interval_data_sum['excess_profit'] * 10000 / interval_data_sum['category_mean_holding_value']
        result.append(interval_data_sum)
    result = pd.concat(result, axis=0).sort_values('impact_factor', ascending=False).reset_index(drop=True)
    result['benchmark'] = benchmark
    return result

# ------------------------------------------------------
# 获取私募推荐策略损益情况汇总
# ------------------------------------------------------
def univAnls_getHFMontlyRecommendedListAttributionSummary(
    end_date,
    category,
    start_date=None,
    data_type='recommend',
    researcher=None,
    rating='A'
):
    assert data_type in ('recommend', 'rating'), "数据类型，推荐列表recommend或评级列表rating"
    if start_date is None:
        start_date = end_date - relativedelta(months=7)  # 回看月份+1，例如想回看6个月，这里months=7
    if data_type == 'recommend':
        data = custHF.custHF_getHFMontlyRecommandedData(start_date, end_date, category, researcher=researcher)
    elif data_type == 'rating':
        data = univAnls_getStrategyRatingSnapshot(end_date, category, rating=rating, start_date=start_date)
    category_holding = _getPeriodStrategyHolding(start_date, end_date, category)
    data['date_3m_delay'] = data['date'] + relativedelta(months=3)-datetime.timedelta(days=1)
    data.loc[data['date_3m_delay'] > end_date, 'date_3m_delay'] = end_date
    result = []
    for index, group in data.groupby(['strategy_id'], as_index=False):
        interval_list = _getHFRecommendIntervalList(group)
        interval_data_list = []
        category_holding_list = []
        for interval in interval_list:
            try:
                df_details, df_sum = portAnls.anlsFOF_getFOFProductAttributionSummary([group['strategy_id'].iloc[0]], interval[0], interval[1],
                                                                                  data_level='Strategy', fund_type='HF', benchmark=config.hf_recommended_strategy_benchmark_map[category])
                df_sum['start_date'] = interval[0]
                df_sum['end_date'] = interval[1]
                interval_data_list.append(df_sum)
                category_holding_list.append(category_holding[(category_holding['date']>=interval[0])&(category_holding['date']<=interval[1])])
            except:
                continue
        if len(interval_data_list) > 0:
            interval_data_sum = pd.concat(interval_data_list, axis=0)
            if interval_data_sum.empty:
                pass
            else:
                interval_data_sum = interval_data_sum.groupby('strategy_id', as_index=False).agg(
                    {'profit_sum': 'sum', 'strategy_name': 'first',
                     'val_start': 'sum', 'val_end': 'sum', 'buy_vol': 'sum', 'buy_val': 'sum', 'sell_vol': 'sum',
                     'sell_val': 'sum', 'start_date': 'first', 'end_date': 'last', 'excess_profit': 'sum', 'benchmark_profit':'sum'})
                interval_data_sum.loc[0, 'category_mean_holding_value'] = pd.concat(category_holding_list, axis=0).groupby('date')['VAL'].sum().mean()
                interval_data_sum['impact_factor'] = interval_data_sum['excess_profit']*10000/interval_data_sum['category_mean_holding_value']
                result.append(interval_data_sum)
    result = pd.concat(result, axis=0).sort_values('impact_factor', ascending=False).reset_index(drop=True)
    result['benchmark'] = config.hf_recommended_strategy_benchmark_map[category]
    return result

# ------------------------------------------------------
# 内部函数，输入内容为每月私募策略推荐的信息，包含每月推荐日期，3个月后日期
# 每一次推荐都会包含开始日期和截止日期，如果区间存在重叠则对时间区间进行合并处理，以列表形式返回不重叠的时间区间，作为策略信息统计的有效区间
# 如[(datetime.date(2024,1,1),datetime.date(2024,3,31)),  (datetime.date(2024,6,1),datetime.date(2024,9,30))]
# ------------------------------------------------------
def _getHFRecommendIntervalList(
    data
):
    # 按照开始日期排序
    df = data.sort_values(by='date').reset_index(drop=True)
    # 初始化合并后的区间列表
    merged_intervals = []
    # 初始化当前区间
    current_start = df.loc[0, 'date']
    current_end = df.loc[0, 'date_3m_delay']
    # 遍历所有区间
    for i in range(1, len(df)):
        start = df.loc[i, 'date']
        end = df.loc[i, 'date_3m_delay']
        if start <= current_end:
            # 如果当前区间与下一个区间重叠，更新当前区间的结束日期
            current_end = max(current_end, end)
        else:
            # 如果不重叠，保存当前区间，并更新为新的区间
            merged_intervals.append((current_start, current_end))
            current_start = start
            current_end = end
    # 添加最后一个区间
    merged_intervals.append((current_start, current_end))
    return merged_intervals

# -------------------------------------------
# 内部函数 获取公募产品的连续推荐区间
# -------------------------------------------
def _getMFRecommendIntervalList(
    sorted_full_dates,     # 排序后的完整日期序列
    recommend_dates        # 推荐日期序列
):
    recommend_interval_list = []
    current_start = None
    current_end = None
    for date in sorted_full_dates:
        if date in recommend_dates:
            current_start = date if current_start is None else current_start
            current_end = date
        else: 
            if (current_start is not None) and (current_end is not None):
                recommend_interval_list.append((current_start, current_end))
                current_start = None
                current_end = None
    if (current_start is not None) and (current_end is not None):
        recommend_interval_list.append((current_start, current_end))
    return recommend_interval_list

# ------------------------------------------------------
# 内部函数，按照策略类型获取区间所持有的所有此类型持仓数据，数据源为持仓缓存表
# ------------------------------------------------------
def _getPeriodStrategyHolding(
        start_date,     # 开始日期
        end_date,       # 结束日期
        category        # 子策略分类
):
    hf_product_info = custHF.custHF_getProductInfo()
    if category in ['主观权益', '套利策略']:
        hf_product_info = hf_product_info[hf_product_info['label_level_1']==category]
    else:
        hf_product_info = hf_product_info[hf_product_info['label_level_2']==category]
    product_ids = hf_product_info['product_id'].to_list()
    data = custFOF.custFOF_getFOFCachedHoldingValuationSheet(start_date, end_date, product_id=product_ids)
    return data

# -----------------------------------
# 公募模拟组合推荐产品wind类型收益统计
# 收益指标取自wind ChinaMFPerformance
# -----------------------------------
def univAnls_getMFMockPortRecommendWindStylePerf(
    start_date,   # 开始日期
    end_date,     # 截止日期
    mock_port_ids=None,   # list, 公募模拟组合id, 默认None取全部持仓数据
    stats=const.const.WIND_MF_PERF_COMMON_STATS,   # 需要获取的stats list，对应ChinaMFPerformance表中的字段
    numeric_rank=False  # 是否将字符串排名转化成比值数值，默认为False
):
    assert isinstance(start_date, datetime.date), "start_date需为datetime.date类型"
    assert isinstance(end_date, datetime.date), "end_date需为datetime.date类型"
    holding_data = custMF.custMF_getMockPortHoldingData(start_date=start_date, end_date=end_date, mock_port_ids=mock_port_ids)
    del holding_data['product_name']  # 统一使用下方wind获取
    product_info = wind.wind_getCurrentProductList(include_pm_info=True, product_ids=holding_data['product_id'].unique().tolist(), only_a_share=False)
    product_info = product_info.groupby(['product_id'], as_index=False).agg({'product_name': 'first', 'pm_name': lambda x: ','.join([pm for pm in x])})
    holding_data = pd.merge(holding_data, product_info[['product_id', 'product_name', 'pm_name']], on='product_id', how='left')
    perf_res = wind.wind_getMFStats(fcode=holding_data['product_id'].unique().tolist(), startdate=start_date, enddate=end_date, stats=stats, MF=True)
    if numeric_rank:
        rank_cols = [col for col in perf_res.columns if '_sfrank_' in col]
        for col in rank_cols:
            perf_res[col] = perf_res[col].apply(lambda x: int(x.split('/')[0]) / int(x.split('/')[1]) if (isinstance(x, str) and ('/' in x)) else x)
    perf_res = pd.merge(holding_data[['portfolio_id', 'portfolio_name', 'product_id', 'product_name', 'pm_name']], perf_res, on='product_id', how='left')
    return perf_res
