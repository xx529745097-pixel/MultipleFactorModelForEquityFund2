# ------------------------------------------------------
# 本文档用于关于基金行业的分析的可视化输出
# ------------------------------------------------------

import datetime
import pandas as pd
import dataframe_image as dfi
import matplotlib.pyplot as plt
import src.const as const
import src.analysis.universeAnalysis as ua
import src.data.zyyx as zyyx
import src.data.wind as wind
import src.const as const
import src.config as config
import seaborn as sns

plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False

# ------------------------------------------------------
# 对于单一指标，画出其各分位数轮动变化情况。
# ------------------------------------------------------
def univVis_plotRollingStats(
    start_date,
    end_date,
    data_source,
    category,              # an array of category, for zyyx and custMF, only one element is accepted
    stat,                  # a string
    local_path=None,       # the path you would like to save the image
    picture_name=None,     # the name of the picture you want to save
    single_manager=None,   # only contains two columns, date and stat
    output_include_data=False # 输出是否包含计算过程中的额外分位数数据
):
    if data_source in ['zyyx', 'zyyx_cached']:
        exclude_date = [ datetime.date(2012,1,1),   datetime.date(2012,1,27), datetime.date(2012,10,7),
                     datetime.date(2012,12,31), datetime.date(2013,2,17), datetime.date(2013,12,31),
                     datetime.date(2015,1,4),   datetime.date(2016,1,1),  datetime.date(2016,2,14),
                     datetime.date(2016,10,7),  datetime.date(2017,1,1),  datetime.date(2017,10,6),
                     datetime.date(2017,10,8),  datetime.date(2018,10,5), datetime.date(2018,10,7),
                     datetime.date(2018,12,31), datetime.date(2019,2,10), datetime.date(2019,12,31),
                     datetime.date(2021,1,1)]
        stats_map = const.const.ZYYX_STATS_MAP
    else:
        exclude_date = []
        stats_map = const.const.WIND_STATS_MAP

    output, universe_stats = ua.univAnls_getRollingStats(start_date, end_date, data_source, category, stat, include_source_data=True)
    output = output[~output['date'].isin(exclude_date)]
    universe_stats = universe_stats[~universe_stats['date'].isin(exclude_date)]
    universe_stats.rename(columns={'manager': 'label'}, inplace=True)

    if single_manager is not None:
        single_manager['label'] = 'input_series'
        universe_stats = pd.concat([single_manager[['label', 'date', stat]], universe_stats], axis=0)
        universe_stats['rank'] = universe_stats.groupby(by=['date'])[stat].rank(ascending=True, pct=True)
        rank_data = universe_stats.loc[universe_stats['label'] == 'input_series', ]
        output = pd.merge(output, single_manager[['date'] + [stat]], on='date')
        output = pd.merge(output, rank_data[['date', 'rank']], on='date')
        manager_stat = output[stat]
        del rank_data['label']
    plt.rcParams['figure.figsize'] = (6, 3)
    fig, ax1 = plt.subplots()
    ax2 = ax1.twinx()

    x = output['date']
    y_1 = output['0.1']
    y_2 = output['0.25']
    y_3 = output['0.5']
    y_4 = output['0.75']
    y_5 = output['0.9']
    count = output['id_count']

    ax1.plot(x, y_1, 'w')
    ax1.plot(x, y_2, 'w')
    ax1.plot(x, y_3, 'w')
    ax1.plot(x, y_4, 'w')
    ax1.plot(x, y_5, 'w')
    ax2.plot(x, count, 'k', linestyle=':', alpha=0.3)
    if single_manager is not None:
        ax1.plot(x, manager_stat, 'b')

    ax1.fill_between(x,y_1, y_2, facecolor='green',alpha=0.6)
    ax1.fill_between(x,y_2, y_3, facecolor='lightgreen', alpha=0.6)
    ax1.fill_between(x, y_3, y_4, color = "#F78181", alpha=0.6)
    ax1.fill_between(x, y_4, y_5, color = '#FF0000', alpha=0.6)
    ax1.tick_params(axis='x', labelrotation=45)
    plt.ylabel(stats_map[stat])
    plt.title(output['type_name'].iloc[0])
    ax1.grid(axis='y', linestyle='--')
    if local_path is not None and picture_name is not None:
        local_path = local_path + '/' + picture_name + '.png'
        plt.savefig(local_path)
        return
    else:
        if output_include_data:
            return fig, rank_data
        else:
            return fig

# ------------------------------------------------------
# 生成关于universe top和bottom的可视化表格
# ------------------------------------------------------
def univVis_listProductStats(
    as_of_date,
    data_source,
    category,              # an array of category, for zyyx and custMF, only one element is accepted
    stat,                  # a string
    chrome_path=None,      # the chrome.exe path
    local_path=None,       # the path you would like to save the image
    picture_name=None,     # the name of the picture you want to save
    order_by_top=True,     # True or False
    rank_num=20,
    exclude_small_manager=False
):
    result = ua.univAnls_listProductStats(as_of_date, data_source, category, stat, order_by_top, rank_num, exclude_small_manager=exclude_small_manager)
    if data_source in ['zyyx', 'zyyx_cached']:
        stat_new_name = const.const.ZYYX_STATS_MAP[stat]
    else:
        stat_new_name = const.const.WIND_STATS_MAP[stat]

    result.rename(columns={'product_id': '产品编码', 'product_name': '产品名称', 'date': '日期', 'start_date': '成立日期',
                           'pm_name': '投资经理', 'manager': '管理人', 'type_name': '标签', stat: stat_new_name}, inplace=True)
    formatter = {stat_new_name: '{:.2%}'}
    colors = 'Reds' if order_by_top else 'Greens'
    result = result.style.format(formatter).background_gradient(subset=[stat_new_name], cmap=colors)
    if chrome_path is not None and local_path is not None and picture_name is not None:
        local_path = local_path + '/' + picture_name + '.png'
        dfi.export(result, local_path, chrome_path=chrome_path)
        return
    else:
        return result

# --------------------------------------------------------------------------------------------
# 生成关于Universe的风险收益特征分布
# data_source 选择zyyx_cached时，代表：有缓存数据的指标（return类的）从缓存取数，其他的仍从zyyx数据库取数
# --------------------------------------------------------------------------------------------
def univVis_getUnivStatsDistribution(
    as_of_date,
    data_source,
    category,                   # an array of category, for zyyx and custMF, only one element is accepted
    stats,                      # an array of stat
    chrome_path=None,           # the chrome.exe path
    local_path=None,            # the path you would like to save the image
    picture_name=None,          # the name of the picture you want to save
):
    if data_source in ['zyyx', 'zyyx_cached']:
        percent_array = const.const.ZYYX_UNIV_PERF_DISTRIBUTION
        stats_map = const.const.ZYYX_STATS_MAP
    else:
        percent_array = const.const.WIND_UNIV_PERF_DISTRIBUTION
        stats_map = const.const.WIND_STATS_MAP

    distribution = ua.univAnls_getUnivStatsDistribution(as_of_date, data_source, category, stats, percent_array)
    percent_list = [ str(x) for x in percent_array]
    formatter = dict(zip(percent_list, ['{:.2%}'] * len(percent_list)))
    distribution['stats_name'] = distribution['stats_name'].apply(lambda x: stats_map[x])
    distribution = distribution.style.format(formatter).background_gradient(axis=1, cmap='Reds', low=0, high=config.cmap_range_adjust_coef)
    if chrome_path is not None and local_path is not None and picture_name is not None:
        local_path = local_path + '/' + picture_name + '.png'
        dfi.export(distribution, local_path, chrome_path=chrome_path)
        return
    else:
        return distribution


# --------------------------------------------------------------------------------------------
# 生成关于Universe的风险收益特征分布
# 指定区间计算, 从朝阳永续缓存数据库获取周度收益率计算
# --------------------------------------------------------------------------------------------
def univVis_getUnivCustomizedPeriodStatsDistribution(
    start_date,
    end_date,
    category,                   # an array of category, for zyyx, only one element is accepted
    stats,                      # an array of stat
):
    assert isinstance(start_date, datetime.date), "日期变量需为datetime.date 类型"
    assert isinstance(end_date, datetime.date), "日期变量需为datetime.date 类型"
    assert category in ['股票多头', '高波动管理期货', '中波动管理期货', '低波动管理期货', '300指数增强', '500指数增强',
                               '1000指数增强', '股票市场中性', '宏观策略', '套利策略', '高波动组合基金', '中波动组合基金', '低波动组合基金'], "输入分类不支持"
    assert set(stats) <= set(const.const.ZYYX_CUSTOMIZED_STATS_MAP.keys())
    distribution = ua.univAnls_getUnivCustomizedPeriodStatsDistribution(start_date, end_date, category, stats=stats)
    distribution['stats_name'] = distribution['stats_name'].apply(lambda x: const.const.ZYYX_CUSTOMIZED_STATS_MAP[x])
    percent_list = [str(x) for x in const.const.ZYYX_UNIV_PERF_DISTRIBUTION]
    formatter = dict(zip(percent_list, ['{:.2%}'] * len(percent_list)))
    distribution = distribution.style.format(formatter).background_gradient(axis=1, cmap='Reds', low=0, high=config.cmap_range_adjust_coef, subset=percent_list)
    return distribution
# ------------------------------------------------------
# 生成符合条件的基金列表
# ------------------------------------------------------
def univVis_getQualifiedProducts(
    start_date,
    end_date,
    data_source,
    category,                       # an array of category, for zyyx and custMF, only one element is accepted
    stat,                           # a string
    percentile,                     # between 0 and 1, higher is better
    threshold,                      # between 0 and 1, higher is better
    chrome_path=None,               # the chrome.exe path
    local_path=None,                # the path you would like to save the image
    picture_name=None,              # the name of the picture you want to save
    exclude_small_manager = True,   # Only works for zyyx, exclude mangager with AUM less than 500MM RMB.
):
    required_columns = ['product_id', 'stats', 'coverage', 'manager', 'product_name']
    if data_source == 'zyyx':
        required_columns = required_columns + ['公司规模']
        stats_map = const.const.ZYYX_STATS_MAP
    else:
        stats_map = const.const.WIND_STATS_MAP

    product_list = ua.univAnls_getQualifiedProducts(start_date, end_date, data_source, category, stat, percentile, threshold, exclude_small_manager)
    product_list = product_list[required_columns]
    product_list['stats'] = product_list['stats'].apply(lambda x: stats_map[x])
    product_list.sort_values(by='coverage', ascending=False, inplace=True)
    product_list.rename(columns={'product_id': '产品编码', 'stats': '指标', 'coverage': '覆盖率',
                                 'product_name': '产品名称', 'manager': '管理人'}, inplace=True)
    product_list = product_list.style.format({'覆盖率': '{:.2%}'}).background_gradient(subset=['覆盖率'], cmap='Reds', low=0, high=config.cmap_range_adjust_coef)
    if chrome_path is not None and local_path is not None and picture_name is not None:
        local_path = local_path + '/' + picture_name + '.png'
        dfi.export(product_list, local_path, chrome_path=chrome_path)
        return
    else:
        return product_list

# ------------------------------------------------------
# 对于单一指标，画出其各分位数轮动变化情况，同时可以画出一个产品的线。
# ------------------------------------------------------
def univVis_plotRollingStatsWProducts(
    start_date,
    end_date,
    data_source,
    category,       # an array of category, for zyyx and custMF, only one element is accepted
    stat,           # a string
    product_ids,    # so far, only support single product id, for HF Monthly Recommanded List, it's ['HFMR'], for HF Strategy Rating, it's ['HFSR']
    local_path=None,
    picture_name=None,
    researcher=None,
    data_type='recommend',
    rating='A',
    output_include_data=False,  # 输出是否包含计算过程中的额外分位数数据
):
    assert len(product_ids) == 1, "目前只支持对单一产品进行该分析"
    if data_source in ['zyyx', 'zyyx_cached']:
        if product_ids[0] == 'HFMR':
            product_stats = ua.univAnls_getHFMontlyRecommendedListReturn(start_date, end_date, category[0], freq='W', researcher=researcher, data_type=data_type, rating=rating)
            product_stats[stat] = (product_stats['adj_return_rate'] + 1).cumprod()-1
            category = [const.const.AMDATA_DB_TO_THIRD_PARTY_DB_MAP[category[0]]]
        else:
            universe_stats = zyyx.zyyx_getProductStats(start_date, end_date, category[0], stat)
            product_stats = universe_stats[universe_stats['product_id'].isin(product_ids)]
    else:
        product_stats = wind.wind_getMFStats(product_ids, start_date, end_date, [stat])
    if output_include_data:
        fig, rank_data = univVis_plotRollingStats(start_date, end_date, data_source, category, stat, local_path,
                                                  picture_name, product_stats, output_include_data=output_include_data)
        rank_data.rename(columns={'year_return': '收益', 'rank': '市场同类排名'}, inplace=True)
        new_cmap = sns.diverging_palette(**config.cmap_kwargs)
        rank_data['year_month'] = rank_data['date'].apply(lambda x: str(x.year) + '-' + str(x.month))
        rank_data = rank_data.groupby(['year_month'], as_index=False).last()
        rank_data = rank_data[['date', '收益', '市场同类排名']].set_index('date').T
        formatter = dict(zip(list(rank_data.columns), [lambda x: "{:.2%}".format(x)] * len(rank_data.columns)))
        df = rank_data.style.format(formatter, na_rep="")
        df = df.background_gradient(cmap=new_cmap, low=config.cmap_range_adjust_coef, high=config.cmap_range_adjust_coef, axis=1)
        return fig, df
    else:
        fig = univVis_plotRollingStats(start_date, end_date, data_source, category, stat, local_path,
                                       picture_name, product_stats, output_include_data=output_include_data)
        return fig


# ------------------------------------------------------
# 对于单一指标，画出其根据x与y轴stats的散点图，同时标记关注的产品
# ------------------------------------------------------
def univVis_plotScatterFigure(
    as_of_date,
    data_source,
    category,
    x_axis_stat,
    y_axis_stat,
    highlighted=None,   # highlighted can be a dataframe that contains id, x_axis_stat and y_axis_stat
):
    if data_source == 'zyyx':
        return "ZYYX data source is Not Supported yet."
    elif data_source == 'wind':
        x_stat = ua.univAnls_getWindUnivStats(as_of_date, as_of_date, category, x_axis_stat)
        y_stat = ua.univAnls_getWindUnivStats(as_of_date, as_of_date, category, y_axis_stat)
        stat_map = const.const.WIND_STATS_MAP
    else:
        x_stat = ua.univAnls_getCustMFUnivStats(as_of_date, as_of_date, category, x_axis_stat)
        y_stat = ua.univAnls_getCustMFUnivStats(as_of_date, as_of_date, category, y_axis_stat)
        stat_map = const.const.WIND_STATS_MAP

    result = x_stat.merge(y_stat[['product_id']+[y_axis_stat]], how='inner', on='product_id')
    if highlighted is not None:
        result = result.merge(highlighted, how='outer', on=['product_id']+[x_axis_stat, y_axis_stat])
        highlighted_ids = highlighted['product_id'].unique()
        result['indicator'] = result['product_id'].apply(lambda x: "Highlighted" if x in highlighted_ids else "Other")
        result.rename(columns={x_axis_stat: stat_map[x_axis_stat], y_axis_stat: stat_map[y_axis_stat]}, inplace=True)
        sns.jointplot(data=result, x=stat_map[x_axis_stat], y=stat_map[y_axis_stat], hue='indicator')
    else:
        result.rename(columns={x_axis_stat: stat_map[x_axis_stat], y_axis_stat: stat_map[y_axis_stat]}, inplace=True)
        sns.jointplot(data=result, x=stat_map[x_axis_stat], y=stat_map[y_axis_stat])
    return

# ------------------------------------------------------
# 获取私募月度推荐列表
# ------------------------------------------------------
def univVis_getHFMontlyRecommandedList(
    date,
    category,
    start_date=None,
    data_type='recommend',
    researcher=None,
    rating='A'
):
    assert data_type in ('recommend', 'rating'), "数据类型，推荐列表recommend或评级列表rating"
    if data_type == 'recommend':
        data = ua.univAnls_getHFMontlyRecommandedList(date, category, researcher, start_date=start_date)
        data = data.T.reset_index()
        data['date'] = data['date'].dt.date
        data = data.set_index('date').T
    elif data_type == 'rating':
        data = ua.univAnls_getStrategyRatingSnapshot(date, category, rating=rating, start_date=start_date)
        data_list = data.groupby(['date'])["strategy_name"].apply(list)
        data = pd.DataFrame(data_list.tolist(), index=data_list.index).fillna("").T
    return data

# ------------------------------------------------------
# 获取公募模拟组合产品推荐区间
# ------------------------------------------------------
def univVis_getMFMockPortRecommendProductList(
    start_date,     # 起始日期
    end_date,       # 截止日期
    mock_port_ids   # list, 模拟组合id
):
    mf_recommend_products = ua.univAnls_getMFMockPortRecommendProductList(start_date=start_date, end_date=end_date, mock_port_ids=mock_port_ids)
    group = mf_recommend_products.groupby(['date'])['product_name'].apply(list).sort_index(ascending=False)
    res = pd.DataFrame(group.tolist(), index=group.index).fillna('').T
    return res

# ------------------------------------------------------
# 获取私募过去6个月的月度以及YTD在库里和行业排名及行业库里情况
# ------------------------------------------------------
def univAnls_getHFMontlyRecommendedListPerfSummary(
    date,
    category,
    start_date=None,
    data_type='recommend',
    researcher=None,
    rating='A'
):
    result = ua.univAnls_getHFMontlyRecommendedListPerfSummary(date, category, start_date=start_date, data_type=data_type, researcher=researcher, rating=rating)
    result['index'] = result['year'].astype(str) + '-' + result['month'].astype(str)
    result.drop(['year', 'month'], axis=1, inplace=True)
    result.rename(columns={'HFMR': '推荐组合', 'invest_mean': '核心库平均', 'invest_median': '核心库中位数', 'invest_rank': '核心库排名',
                           'track_mean': '跟踪库平均', 'track_median': '跟踪库中位数', 'track_rank': '跟踪库排名',
                           'invest_track_mean': '核心加跟踪库平均', 'invest_track_median': '核心加跟踪库中位数', 'invest_track_rank': '核心加跟踪库排名',
                           'univ_median': '行业中位数', 'univ_rank': '行业排名'}, inplace=True)
    result.set_index('index', inplace=True)
    result = result.T
    formatter = dict(zip(list(result.columns), [lambda x: "{:.2%}".format(x)] * len(result.columns)))
    new_cmap = sns.diverging_palette(**config.cmap_kwargs)
    df = result.style.format(formatter, na_rep="")
    df = df.background_gradient(subset=(['核心库排名', '跟踪库排名', '核心加跟踪库排名', '行业排名'], df.columns), cmap=new_cmap, low=config.cmap_range_adjust_coef, high=config.cmap_range_adjust_coef, axis=1, vmin=0, vmax=1)
    df = df

    return df

# ----------------------------------
# 推买贡献标准Layout私有函数
# 统一私募/公募推买贡献展示格式
# ----------------------------------
def _getRecommendAttributionSummaryStdLayout(
    summary_result,   # 推荐贡献结果
    fund_type         # 基金类型，'HF'或'MF'
):
    assert fund_type in ('HF', 'MF'), "fund_type需为'HF'或'MF'"
    summary_result.sort_values(by='impact_factor', ascending=False)
    rename_dict = {
        'strategy_id': '策略代码',
        'product_id': '产品代码',
        'benchmark': '基准',
        'strategy_name': '策略名称',
        'product_name': '产品名称',
        'start_date': '最早开始日期',
        'end_date': '最晚结束日期',
        'profit_sum': '累计收益（万）',
        'benchmark_profit': '基准收益（万）',
        'excess_profit': '超额收益（万）',
        'val_start': '初始持仓价值（万）',
        'val_end': '期末持仓价值（万）',
        'val_mean': '平均持仓价值（万）',
        'buy_vol': '期间买入份额（万）',
        'buy_val': '期间买入金额（万）',
        'sell_vol': '期间卖出份额（万）',
        'sell_val': '期间卖出金额（万）',
        'category_mean_holding_value': '大类策略日平均持仓（万）',
        'impact_factor': '影响系数'
    }
    summary_result.rename(columns=rename_dict, inplace=True)
    adjust_col = ['累计收益（万）', '基准收益（万）', '超额收益（万）', '大类策略日平均持仓（万）', '初始持仓价值（万）',
                  '期末持仓价值（万）', '期间买入份额（万）', '期间买入金额（万）', '期间卖出份额（万）', '期间卖出金额（万）']
    summary_result[adjust_col] /= 10000
    formatter = dict(zip(adjust_col + ['影响系数'], [lambda x: "{:,.2f}".format(x)]*(len(adjust_col)+1)))
    new_cmap = sns.diverging_palette(**config.cmap_kwargs)
    d1 = dict(selector="th", props=[('text-align', 'center')])
    d2 = dict(selector='caption', props=[('text-align', 'center'), ('font-weight', 'bold'), ('color', 'black'), ('font-size', '125%')])

    # 中间显示变量
    info_dict = {
        '平均影响系数': "{:.2f}".format(summary_result['影响系数'].mean()),
        '净申购份额(万)': "{:.2f}".format(summary_result['期间买入份额（万）'].sum() - summary_result['期间卖出份额（万）'].sum()),
        '总超额收益(万)': "{:.2f}".format(summary_result['超额收益（万）'].sum()),
        '基准': summary_result['基准'].iloc[0]
    }
    result = summary_result[['策略名称' if fund_type == 'HF' else '产品名称', '最早开始日期', '最晚结束日期', '影响系数'] + adjust_col]
    df = result.reset_index(drop=True).style.format(formatter, na_rep="")\
        .set_properties(**{'width': '100', 'text-align': 'center'}).set_table_styles([d1])\
        .set_table_styles([d2], overwrite=False)
    for col in result.columns.drop(['策略名称' if fund_type == 'HF' else '产品名称', '最早开始日期', '最晚结束日期']):
        if col in ['影响系数', '累计收益（万）', '基准收益（万）', '超额收益（万）']:
            df = df.background_gradient(subset=col, cmap=new_cmap, low=config.cmap_range_adjust_coef,
                                        high=config.cmap_range_adjust_coef, axis=0,
                                        vmin=(-result[col].abs().max(axis=0)),
                                        vmax=result[col].abs().max(axis=0))
        else:
            df = df.background_gradient(subset=col, cmap=new_cmap, low=config.cmap_range_adjust_coef, high=config.cmap_range_adjust_coef, axis=0,
                                        vmin=0, vmax=result[col].abs().max(axis=0))
    df = df.highlight_null('white')
    return df, info_dict

# ------------------------------------------------------
# 获取私募推荐策略损益情况汇总
# ------------------------------------------------------
def univVis_getHFMontlyRecommendedListAttributionSummary(
    date,                   # 日期
    category,               # 策略分类
    start_date=None,
    data_type='recommend',  # 来源，recommend or rating
    researcher=None,        # 研究员选项，仅对recommend生效
    rating='A'              # 评级选项，仅对rating生效
):
    summary_result = ua.univAnls_getHFMontlyRecommendedListAttributionSummary(date, category, start_date=start_date, data_type=data_type, researcher=researcher, rating=rating)
    df, info_dict = _getRecommendAttributionSummaryStdLayout(summary_result, 'HF')
    return df, info_dict

# ------------------------------------------------------
# 获取公募推荐策略损益情况汇总
# ------------------------------------------------------
def univVis_getMFMockPortRecommendProductAttributionSummary(
    start_date,     # 起始日期
    end_date,       # 截止日期
    mock_port_ids,  # list, 模拟组合id
    benchmark=None  # 基准指数id
):
    summary_result = ua.univAnls_getMFMockPortRecommendProductAttributionSummary(start_date, end_date, mock_port_ids, benchmark)
    df, info_dict = _getRecommendAttributionSummaryStdLayout(summary_result, 'MF')
    return df, info_dict
