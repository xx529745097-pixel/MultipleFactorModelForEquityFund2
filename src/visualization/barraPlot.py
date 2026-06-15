# -----------------------------------------------------------------------
# barra相关分析作图模块
# -----------------------------------------------------------------------
import statsmodels.api as sm
import datetime
import altair as alt
import pandas as pd
import numpy as np
import src.analysis.barraAnalysis as barraAnal
import src.utils.fof_calendar as calendar
import src.const as const
import src.config as config
import seaborn as sns
from matplotlib import cm, pyplot as plt
from dateutil.relativedelta import relativedelta
from src.data import custHF as custHF
plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False

# -----------------------------------------------------------------------
# barra风格因子净值曲线画图
# -----------------------------------------------------------------------
def visBarra_plotFactorNav(
    style_factor_list,  # list
    period,  # 统计区间
    date,
    start_date=None,  # This parameter ONLY works for period equal to Customized
):
    start_date = start_date if period == 'Customized' else None
    start_date, end_date = calendar.calender_getStartEndDate(period, date, start_date)
    style_factor_nav = barraAnal.barraAnal_calFactorNav(start_date, end_date, style_factor_list)
    # 逆透视, 方便后续使用altair绘图
    result = pd.melt(style_factor_nav, id_vars='date', var_name='style_factor', value_name='nav')
    nearest = alt.selection_single(nearest=True, on='mouseover', empty='none')
    selection = alt.selection_multi(fields=['style_factor'], bind='legend', name='风格因子')
    title_string = "风格因子净值曲线, 统计区间: " + str(period) + ", 数据频率: D"
    base = alt.Chart(result, title=title_string).mark_line().encode(
        x=alt.X('date:T', title='日期', axis=alt.Axis(format='%Y/%m/%d')),
        y=alt.Y('nav', title='区间Nav', scale=alt.Scale(domain=[0.99*result['nav'].min(), 1.01*result['nav'].max()])),
        color=alt.Color('style_factor'),
        tooltip=['style_factor', 'date', {'field': 'nav', 'format': ',.4f'}],
        opacity=alt.condition(selection, alt.value(1), alt.value(0.1))
    )
    point = base.mark_point().encode(
        opacity=alt.condition(nearest, alt.value(1), alt.value(0))
    ).add_selection(nearest)
    lines = base.add_selection(selection)
    c = alt.layer(lines, point).interactive().configure_axisX(labelAngle=0)
    return c, style_factor_nav

# -----------------------------------------------------------------------
# barra风格因子区间收益指标表格
# -----------------------------------------------------------------------
def visBarra_FactorPerfStats(
    style_factor_list,  # list
    period,  # 统计区间
    date,
    start_date=None,  # This parameter ONLY works for period equal to Customized
):
    start_date = start_date if period == 'Customized' else None
    start_date, end_date = calendar.calender_getStartEndDate(period, date, start_date)
    performance_data = barraAnal.barraAnal_calFactorPerf(start_date, end_date, style_factor_list)
    formatter = {
        '风格因子': lambda x: str(x),
        '区间收益率': lambda x: "{:.2%}".format(x),
        '年化区间收益率': lambda x: "{:.2%}".format(x),
        '年化波动率': lambda x: "{:.2%}".format(x) if not isinstance(x, str) else x,
        '最大回撤': lambda x: "{:.2%}".format(x),
        '夏普': lambda x: "{:.2f}".format(x) if not isinstance(x, str) else x,
        '卡玛比': lambda x: "{:.2f}".format(x),
        '开始日期': lambda x: x.strftime("%Y-%m-%d"),
        '截止日期': lambda x: x.strftime("%Y-%m-%d"),
    }
    rename_map = {
        'style_factor': '风格因子',
        'period_return': '区间收益率',
        'annualized_period_return': '年化区间收益率',
        'annualized_volatility': '年化波动率',
        'max_drawdown': '最大回撤',
        'sharpe_ratio': '夏普',
        'calmar': '卡玛比',
        'start_date': '开始日期',
        'end_date': '截止日期',
    }
    performance_data.rename(columns=rename_map, inplace=True)
    perf_prefix_cols = ['风格因子', '开始日期', '截止日期', '区间收益率']
    if period != 'Today':
        performance_data = performance_data[perf_prefix_cols + performance_data.columns.drop(perf_prefix_cols).to_list()]
    else:
        performance_data = performance_data[perf_prefix_cols]
    _df_caption = 'Performance Stats, ' + 'period: ' + period + ', data frequency: D'
    new_cmap = sns.diverging_palette(**config.cmap_kwargs)
    d1 = dict(selector="th", props=[('text-align', 'center')])
    d2 = dict(selector='caption',  props=[('text-align', 'center'), ('font-weight', 'bold'), ('color', 'black'), ('font-size', '125%')])
    df = performance_data.reset_index(drop=True).style.format(formatter, na_rep="") \
        .set_properties(**{'width': '100', 'text-align': 'center'}) \
        .set_caption(_df_caption) \
        .set_table_styles([d1]) \
        .set_table_styles([d2], overwrite=False)
    for col in performance_data.columns.drop(['风格因子', '开始日期', '截止日期']):
        if col == '年化波动率':
            df = df.background_gradient(subset=col, cmap=sns.diverging_palette(**config.vol_cmap_kwargs), low=config.cmap_range_adjust_coef, high=config.cmap_range_adjust_coef, axis=0)
        elif col == '最大回撤':
            df = df.background_gradient(subset=col, cmap=new_cmap, low=config.cmap_range_adjust_coef, high=config.cmap_range_adjust_coef, axis=0)
        else:
            df = df.background_gradient(subset=col, cmap=new_cmap, low=config.cmap_range_adjust_coef, high=config.cmap_range_adjust_coef, axis=0,
                                        vmin=(-performance_data[col].abs().max(axis=0)), vmax=performance_data[col].abs().max(axis=0))
    df = df.highlight_null('white')
    return df

#####################
# 周报/月报画图函数
#####################
# -----------------------------------------------------------------------
# 画barra factor return correlation
# -----------------------------------------------------------------------
def visBarra_FactorCorrPlot(
    start_date,  # DateTime.date instance, eg: datetime.date(2021, 1, 1)
    end_date,  # DateTime.date instance, eg: datetime.date(2021, 10, 1)
    rolling_window,  # int, 使用过去多少天的数据来计算correlation
    factor_list=None,  # python list
    fig_title=None,  # graph's title
    save_path=None  # 图片存储地址
):
    factor_corr_data = barraAnal.barraAnal_calFactorCorr(start_date, end_date, rolling_window, factor_list)
    factor_corr_data.set_index("date", inplace=True)
    fig = plt.figure(figsize=(10, 5))
    fig.set_dpi(200)
    ax1 = fig.add_subplot(111)
    pct_25 = np.percentile(factor_corr_data['factor_corr'].values, 25)
    pct_75 = np.percentile(factor_corr_data['factor_corr'].values, 75)
    ax1.plot(factor_corr_data.index, factor_corr_data['factor_corr'], label='factor correlation', linewidth=1, color='grey')
    _, trend = sm.tsa.filters.hpfilter(factor_corr_data['factor_corr'], 14400)
    ax1.plot(factor_corr_data.index, trend, label='factor correlation (hp filtered)', linewidth=1, color='black')
    ax1.axhline(y=pct_25, color='red', label='25 percentile', linestyle='--', linewidth=1)
    ax1.axhline(y=pct_75, color='dodgerblue', label='75 percentile', linestyle='--', linewidth=1)
    ax1.grid(0)
    ax1.legend(loc='best', ncol=2)
    ax1.spines['top'].set_visible(False)
    ax1.spines['right'].set_visible(False)
    ax1.spines['bottom'].set_color('black')
    ax1.spines['left'].set_color('black')
    if fig_title:
        ax1.set_title(fig_title, fontsize=15)
    plt.show()
    if save_path:
        plt.savefig(save_path + "/" + fig_title + start_date.strftime("%Y%m%d") + "_" + end_date.strftime("%Y%m%d") + ".png")

    return

# -----------------------------------------------------------------------
# 画barra factor performance
# -----------------------------------------------------------------------
def visBarra_plotFactorPerformance(
    start_date,  # DateTime.date instance, eg: datetime.date(2021, 1, 1)
    end_date,  # DateTime.date instance, eg: datetime.date(2021, 1, 1)
    factor_list=None  # python list
):
    factor_perf = barraAnal.barraAnal_calFactorNav(start_date, end_date, factor_list)
    factor_perf.set_index('date', inplace=True)
    fig, ax = plt.subplots(figsize=(12, 6), dpi=350)
    colors = cm.get_cmap('jet')
    c = colors(np.linspace(0, 1, len(factor_perf.columns)))
    for i, col in enumerate(factor_perf.columns):
            ax.plot(factor_perf.index, factor_perf[col], label=col, linewidth=0.8, color=c[i])
    ax.legend(loc=2, bbox_to_anchor=(1, 1), borderaxespad=0.5, frameon=False)
    ax.yaxis.grid(True, linestyle='--')
    ax.xaxis.grid(False)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['bottom'].set_color('black')
    ax.spines['left'].set_color('black')
    ax.set_title('Barra Factor Performance: ' + start_date.strftime("%Y-%m-%d") + ' to ' + end_date.strftime("%Y-%m-%d"))
    plt.show()
    return

# -----------------------------------------------------------------------
# 画barra factor weekly/monthly performance, 表格形式
# -----------------------------------------------------------------------
def visBarra_factorMonthlyReturn(
    num_trailing_month,  # 展示过去几个月的收益
    factor_list=None  # python list
):
    assert isinstance(num_trailing_month, int), "num_trailing_month should be an int instance"
    today = datetime.datetime.today().date()
    ldlm = datetime.date(today.year, today.month, 1) - datetime.timedelta(1)  # ldlm: last date of last month
    start_date = ldlm - relativedelta(months=num_trailing_month)
    result = barraAnal.barraAnal_calFactorReturn(start_date, ldlm, 'M', factor_list)
    result = result.iloc[:num_trailing_month, :]
    result.reset_index(inplace=True)
    result['index'] = result['year'].astype(str) + '-' + result['month'].astype(str)
    result.drop(['year', 'month'], axis=1, inplace=True)
    result.set_index('index', inplace=True)
    result = result.T
    formatter = dict(zip(list(result.columns), [lambda x: "{:.2%}".format(x)] * len(result.columns)))
    new_cmap = sns.diverging_palette(**config.cmap_kwargs)
    d1 = dict(selector="th", props=[('text-align', 'center')])
    d2 = dict(selector='caption', props=[('text-align', 'center'), ('font-weight', 'bold'), ('color', 'black'), ('font-size', '125%')])
    _df_caption = 'Barra factor return: last ' + str(num_trailing_month) + ' Months'
    df = result.style.format(formatter, na_rep="").background_gradient(cmap=new_cmap, low=config.cmap_range_adjust_coef, high=config.cmap_range_adjust_coef, axis=0).highlight_null('white').set_properties(
        **{'width': '100', 'text-align': 'center'}).set_caption(_df_caption).set_table_styles([d1]).set_table_styles([d2], overwrite=False)
    return df

# ------------------------------------------------------
# 画某一天某一类型（level2)的量化、多头产品的某一因子暴露
# CS: Cross sectional
# ------------------------------------------------------
def visBarra_HFBarraFactorRelaExposureCS(
    date,  # datetime.date
    strategy,  # '500指增', '300指增', '1000指增'
    factor  # const.const.BARRA_STYLE_FACTOR
):
    assert isinstance(date, datetime.date), 'date must be an instance of datetime.date'
    assert strategy in ('500指增', '300指增', '1000指增', '300对冲', '500对冲', '平衡', '价值', '轮动'), '目前只支持指增、中性、主观权益类策略'
    assert factor in const.const.BARRA_STYLE_FACTOR, '可选因子名称请查阅const.const.BARRA_STYLE_FACTOR'
    strategy_benchmark_mapping = {
        '500指增': 'ZZ500',
        '300指增': 'HS300',
        '1000指增': 'ZZ1000',
        '300对冲': 'HS300',
        '500对冲': 'ZZ500',
        '平衡': 'ZZ800',
        '价值': 'ZZ800',
        '轮动': 'ZZ800'
    }
    if strategy == '300对冲':
        product_info = custHF.custHF_getProductInfo(product_status=['在库已投'], strategy_level_2=['市场中性'])
        fund_ids = list(config.product_additional_label['300对冲'].keys())
    elif strategy == '500对冲':
        product_info = custHF.custHF_getProductInfo(product_status=['在库已投'], strategy_level_2=['市场中性'])
        fund_ids = list(set(product_info['product_id'].to_list()) - set(config.product_additional_label['300对冲'].keys()))
    else:
        product_info = custHF.custHF_getProductInfo(product_status=['在库已投'], strategy_level_2=[strategy])
        fund_ids = product_info['product_id'].to_list()
    data_source = 'CustodianFunda' if strategy in ['平衡', '价值', '轮动'] else 'CustodianQuant'
    benchmark = 'ZERO_BM' if strategy in ['平衡', '价值', '轮动'] else strategy_benchmark_mapping[strategy]
    barra_factor_rela_expo = barraAnal.barraAnal_calRelativeBarraFactorExposure(benchmark, date, date, data_source)
    barra_factor_rela_expo = pd.merge(barra_factor_rela_expo, product_info[['product_id', 'product_short_name']], left_on='product_id', right_on='product_id', how='left')
    barra_factor_rela_expo = barra_factor_rela_expo[barra_factor_rela_expo['product_id'].isin(fund_ids)]
    barra_factor_rela_expo.sort_values(by='product_short_name', inplace=True, ascending=False)
    fig, ax = plt.subplots(figsize=(10, 10 * 0.618))
    barra_factor_rela_expo.plot.bar(x='product_short_name', y=factor.lower()+'_excess', color='navy', ax=ax)
    ax.set_title(strategy + factor + '超额暴露：' + date.strftime('%Y-%m-%d'), fontsize=18)
    plt.xticks(fontsize=12)
    plt.tight_layout()
    figure = plt.gcf()
    return figure


# ------------------------------------------------------
# 画某一量化、多头产品的风格因子暴露时序图
# TS: Time series
# ------------------------------------------------------
def visBarra_HFBarraFactorRelaExposureTS(
    start_date,  # datetime.date
    end_date,  # datetime.date
    product_id,  # 产品代码 'SGR167.OF'
    benchmark,  # ZZ500, HS300, ZZ1000, ZZ800, ZERO_BM, Customized
    factor_list=None,  # 可选择只画部分因子
    customized_bm_weight_dict=None,  # dict, 仅当benchmark为Customized时生效
    fund_data_source='CustodianQuant'  # "CustodianQuant" or "CustodianFunda"
):
    assert isinstance(start_date, datetime.date), 'start_date must be an instance of datetime.date'
    assert isinstance(end_date, datetime.date), 'end_date must be an instance of datetime.date'
    assert benchmark in ('ZZ500', 'HS300', 'ZZ1000', 'ZZ800', 'ZERO_BM', 'Customized'), 'benchmark只能为ZZ500, HS300, ZZ1000, ZZ800, ZERO_BM, Customized中的一个'
    product_info = custHF.custHF_getProductInfo()
    product_name = product_info.set_index('product_id')['product_short_name'].to_dict()[product_id]
    barra_factor_rela_expo = barraAnal.barraAnal_calRelativeBarraFactorExposure(index_code=benchmark, start_date=start_date, end_date=end_date,
                                                                                fund_data_source=fund_data_source, fund_id=product_id, customized_bm_weight_dict=customized_bm_weight_dict)
    assert product_id in barra_factor_rela_expo['product_id'].to_list(), '托管数据中不存在该产品'
    barra_factor_rela_expo = barra_factor_rela_expo[barra_factor_rela_expo['product_id'] == product_id]
    if factor_list:
        barra_factor_rela_expo = barra_factor_rela_expo[['date'] + [x + '_excess' for x in factor_list]]
    else:
        barra_factor_rela_expo = barra_factor_rela_expo[['date'] + [x for x in barra_factor_rela_expo.columns if x.endswith('_excess')]]
    barra_factor_rela_expo.sort_values('date', inplace=True)
    barra_factor_rela_expo['date'] = barra_factor_rela_expo['date'].apply(pd.Timestamp)
    customized_title_str = '+'.join([f'{v:.2%}*{k}' for k, v in customized_bm_weight_dict.items() if v > 0]) if benchmark == 'Customized' else ''

    # 风格因子时序暴露
    melted = pd.melt(barra_factor_rela_expo, id_vars=['date'], value_vars=[x for x in barra_factor_rela_expo.columns if x.endswith('_excess')],
                     var_name='style_factor', value_name='exposure')
    nearest = alt.selection_single(nearest=True, on='mouseover', empty='none')
    selection = alt.selection_multi(fields=['style_factor'], bind='legend', name='style_factor')
    base = alt.Chart(melted, title='风格因子时序暴露-{} benchmark: '.format(product_name) + (
        customized_title_str if benchmark == 'Customized' else benchmark)).mark_line().encode(
        alt.X('date:T', axis=alt.Axis(title='日期', format='%Y/%m/%d')),
        alt.Y('exposure', axis=alt.Axis(title='因子暴露水平')),
        color=alt.Color('style_factor'),
        tooltip=['date', 'style_factor', {'field': 'exposure', 'format': '.4f'}],
        opacity=alt.condition(selection, alt.value(1), alt.value(0.1)))
    point = base.mark_point().encode(
        opacity=alt.condition(nearest, alt.value(1), alt.value(0))
    ).add_selection(nearest)
    lines = base.add_selection(selection)
    ts_exposure_chart_result = alt.layer(lines, point).interactive().configure_axisX(labelAngle=0)

    # 日截面风格因子暴露柱状图
    end_date_barra_factor_rela_expo = barra_factor_rela_expo[barra_factor_rela_expo['date'] == barra_factor_rela_expo['date'].max()]
    melted = pd.melt(end_date_barra_factor_rela_expo, id_vars=['date'], value_vars=[x for x in end_date_barra_factor_rela_expo.columns if x.endswith('_excess')],
                     var_name='style_factor', value_name='exposure')
    end_date_exposure_chart_result = alt.Chart(melted, title='{}日截面风格因子暴露-{} benchmark: '.format(end_date, product_name) + (customized_title_str if benchmark == 'Customized' else benchmark)).mark_bar().encode(
        alt.X('style_factor', axis=alt.Axis(title='风格因子')),
        alt.Y('exposure', axis=alt.Axis(title='因子暴露水平'), sort='-x'),
        color=alt.Color('style_factor'),
        tooltip=['style_factor', {'field': 'exposure', 'format': '.4f'}]
    ).interactive()

    return ts_exposure_chart_result, end_date_exposure_chart_result

# ------------------------------------------------------
# 画某一量化、多头产品的超额收益拆解
# ------------------------------------------------------
def visBarra_decomposeExcessReturn(
    product_id,  # 产品代码 'SGR167.OF'
    start_date,  # datetime.date instance
    end_date,  # datetime.date instance
    return_benchmark,  # must be in "HS300", "ZZ100", "ZZ500", "ZZ800", "ZZ1000", "ZERO_BM", "ZERO_BM" for market neutral
    holding_benchmark,  # must be in "HS300", "ZZ100", "ZZ500", "ZZ800", "ZZ1000", "ZERO_BM", "ZERO_BM" for market neutral
    fund_data_source='CustodianQuant' #  "CustodianQuant" or "CustodianFunda"
):
    assert fund_data_source in ("ValuationSheet", "CustodianQuant", "CustodianFunda"), "基金数据来源只能是CustodianQuant、CustodianFunda"
    product_info = custHF.custHF_getProductInfo()
    product_name = product_info.set_index('product_id')['product_short_name'].to_dict()[product_id]
    pure_alpha, barra_factor_excess_return, product_excess_return, single_factor_excess_return = barraAnal.barraAnal_decomposeExcessReturn(product_id, start_date, end_date, return_benchmark, holding_benchmark, fund_data_source=fund_data_source)
    res = pd.concat([(pure_alpha.fillna(0) + 1).cumprod().rename('剥离风格因子的超额'),
                     (barra_factor_excess_return.fillna(0) + 1).cumprod().rename('风格因子超额'),
                     (product_excess_return.fillna(0) + 1).cumprod().rename('产品超额')], axis=1, join='inner')
    res.index.name = 'date'
    res.reset_index(inplace=True)
    res['date'] = res['date'].apply(pd.Timestamp)
    melted = pd.melt(res, id_vars=['date'], value_vars=['剥离风格因子的超额', '风格因子超额', '产品超额'], var_name='收益类别', value_name='Nav')
    max_ytick = melted['Nav'].max()*1.01
    min_ytick = melted['Nav'].min()*0.99
    nearest = alt.selection_single(nearest=True, on='mouseover', empty='none')
    selection = alt.selection_multi(fields=['收益类别'], bind='legend', name='收益类别')
    base = alt.Chart(melted, title='{}超额收益拆解 业绩基准:{} 持仓基准:{}'.format(product_name, return_benchmark, holding_benchmark)).mark_line().encode(
        alt.X('date:T', axis=alt.Axis(title='日期', format='%Y/%m/%d')),
        alt.Y('Nav', scale=alt.Scale(domain=[min_ytick, max_ytick]), axis=alt.Axis(title='Nav')),
        color=alt.Color('收益类别'),
        tooltip=['date', '收益类别', {'field': 'Nav', 'format': '.4f'}],
        opacity=alt.condition(selection, alt.value(1), alt.value(0.1)))
    point = base.mark_point().encode(
        opacity=alt.condition(nearest, alt.value(1), alt.value(0))
    ).add_selection(nearest)
    lines = base.add_selection(selection)
    chart_result = alt.layer(lines, point).interactive().configure_axisX(labelAngle=0)
    return chart_result


# ------------------------------------------------------
# 获取私募量化产品超额收益拆分汇总表
# ------------------------------------------------------
def visBarra_decomposeExcessReturnTable(
    start_date,         # datetime.date instance
    end_date,           # datetime.date instance
    strategy,           #300指增，500指增
    return_benchmark,  # must be in "HS300", "ZZ100", "ZZ500", "ZZ800", "ZZ1000", "ZERO_BM", "ZERO_BM" for market neutral
    holding_benchmark=None,  # must be in "HS300", "ZZ100", "ZZ500", "ZZ800", "ZZ1000", "ZERO_BM", "ZERO_BM" for market neutral
):
    assert isinstance(start_date, datetime.date), 'date must be an instance of datetime.date'
    assert isinstance(end_date, datetime.date), 'date must be an instance of datetime.date'
    assert strategy in ('500指增', '300指增', '1000指增', '300对冲', '500对冲'), '目前只支持指增和中性类策略'
    if strategy == '300对冲':
        fund_ids = list(config.product_additional_label['300对冲'].keys())
    elif strategy == '500对冲':
        product_info = custHF.custHF_getProductInfo(product_status=['在库已投'], strategy_level_2=['市场中性'])
        fund_ids = list(set(product_info['product_id'].to_list()) - set(config.product_additional_label['300对冲'].keys()))
    else:
        product_info = custHF.custHF_getProductInfo(product_status=['在库已投'], strategy_level_2=[strategy])
        fund_ids = product_info['product_id'].to_list()
    # 对于非中性产品，可简化输入，仅需输入业绩benchmark
    if holding_benchmark == None:
        holding_benchmark = return_benchmark
    result = barraAnal.barraAnal_decomposeExcessReturnTable(start_date, end_date, return_benchmark, holding_benchmark, fund_ids)
    format_dict = {'pure_alpha': '{:.2%}', 'barra_excess': '{:.2%}', 'product_excess': '{:.2%}'}
    result.rename(columns={'barra_factor_excess_return': 'barra_excess', 'product_excess_return': 'product_excess'},inplace=True)
    new_cmap = sns.diverging_palette(**config.cmap_kwargs)
    for factor in const.const.BARRA_STYLE_FACTOR:
        format_dict[factor.lower()]='{:.2%}'
    df = result.style.format(format_dict)
    vmax_for_cmap = result[result.columns.drop(['product_id', 'product_short_name', 'benchmark', 'start_date', 'end_date'])].abs().max().max()
    for col in format_dict.keys():
        df = df.background_gradient(subset=col, cmap=new_cmap, low=config.cmap_range_adjust_coef, high=config.cmap_range_adjust_coef, axis=0, vmin=-vmax_for_cmap, vmax=vmax_for_cmap)
    df = df.highlight_null('white')
    return df