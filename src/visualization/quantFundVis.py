import pandas as pd
import datetime
import src.data.custHF as custHF
import src.config as config
import src.data.quantFundData as qfd
import matplotlib.pyplot as plt
from matplotlib import ticker
import seaborn as sns
import altair as alt

plt.rcParams['axes.unicode_minus'] = False


# ------------------------------------------------------
# 画某一量化产品的换手率时序图
# ------------------------------------------------------
def qfv_quantFundTurnOver(
        start_date,  # datetime.date
        end_date,  # datetime.date
        product_id,  # 产品代码 'SGR167.OF'
):
    assert isinstance(start_date, datetime.date), 'start_date must be an instance of datetime.date'
    assert isinstance(end_date, datetime.date), 'end_date must be an instance of datetime.date'

    product_info = custHF.custHF_getProductInfo()
    product_name = product_info.set_index('product_id')['product_short_name'].to_dict()[product_id]
    quant_fund_data = qfd.qfd_getQuantFundsExposure(start_date, end_date)
    assert product_id in quant_fund_data['product_id'].to_list(), '托管数据中不存在该产品'
    quant_fund_data = quant_fund_data[quant_fund_data['product_id'] == product_id]
    quant_fund_data = quant_fund_data[['date', 'turnover_near_one_month', 'turnover_near_one_year', 'net_asset_val']]
    quant_fund_data['turnover_near_one_month'] *= 12
    quant_fund_data['date'] = quant_fund_data['date'].apply(pd.Timestamp)
    melted = pd.melt(quant_fund_data[['date', 'turnover_near_one_month', 'turnover_near_one_year']], id_vars='date',
                     value_vars=['turnover_near_one_month', 'turnover_near_one_year'])
    base1 = alt.Chart(quant_fund_data, title=product_name + ' 换手率及资产规模').encode(
        alt.X('date', axis=alt.Axis(title=None, format='%Y/%m/%d'))
    )
    bar = base1.mark_bar(opacity=0.3, color='#57A44C').encode(
        alt.Y('net_asset_val', axis=alt.Axis(title='net_asset_val', titleColor='#57A44C')),
        tooltip=['date', {'field': 'net_asset_val', 'format': ',.2f'}]
    )
    nearest = alt.selection_single(nearest=True, on='mouseover', empty='none')
    selection = alt.selection_multi(fields=['variable'], bind='legend', name='variable')
    base2 = alt.Chart(melted).mark_line(interpolate='monotone').encode(
        alt.X('date', axis=alt.Axis(title=None, format='%Y/%m/%d')),
        alt.Y('value', axis=alt.Axis(title='turnover', titleColor='#5276A7')),
        color='variable',
        tooltip=['date', {'field': 'value', 'format': ',.2f'}]
    )
    lines = base2.add_selection(selection)
    points = base2.mark_point().encode(
        opacity=alt.condition(nearest, alt.value(1), alt.value(0))
    ).add_selection(nearest)
    Chart = alt.layer(bar, lines, points).resolve_scale(
        y='independent'
    )
    return Chart.interactive()

# ------------------------------------------------------
# 画某一类量化产品某一时间截面的近一月换手率（年化）
# ------------------------------------------------------
def qfv_quantFundTurnOverCS(
    date,  # datetime.date
    strategy  # '500指增', '300指增', '1000指增', '市场中性'
):
    assert isinstance(date, datetime.date), 'date must be an instance of datetime.date'
    assert strategy in ('500指增', '300指增', '1000指增', '市场中性', '300对冲', '500对冲'), '目前只支持500指增、300指增、1000指增、市场中性类策略'
    if strategy == '300对冲':
        product_info = custHF.custHF_getProductInfo(product_status=['在库已投'], strategy_level_2=['市场中性'])
        fund_ids = list(config.product_additional_label['300对冲'].keys())
    elif strategy == '500对冲':
        product_info = custHF.custHF_getProductInfo(product_status=['在库已投'], strategy_level_2=['市场中性'])
        fund_ids = list(set(product_info['product_id'].to_list()) - set(config.product_additional_label['300对冲'].keys()))
    else:
        product_info = custHF.custHF_getProductInfo(product_status=['在库已投'], strategy_level_2=[strategy])
        fund_ids = product_info['product_id'].to_list()
    quant_fund_data = qfd.qfd_getQuantFundsExposure(date, date)
    quant_fund_data = quant_fund_data[quant_fund_data['product_id'].isin(fund_ids)]
    quant_fund_data = pd.merge(quant_fund_data, product_info[['product_id', 'product_short_name']], left_on='product_id', right_on='product_id', how='left')
    quant_fund_data = quant_fund_data[['product_short_name', 'turnover_near_one_month']]
    quant_fund_data['turnover_near_one_month'] = 12 * quant_fund_data['turnover_near_one_month']
    quant_fund_data.sort_values(by='product_short_name', inplace=True, ascending=False)
    fig, ax = plt.subplots(figsize=(10, 10 * 0.618))
    quant_fund_data.plot.bar(x='product_short_name', y='turnover_near_one_month', color='navy', ax=ax)
    ax.set_title(strategy + '近一月换手率(年化)' + date.strftime('%Y-%m-%d'), fontsize=18)
    plt.xticks(fontsize=12)
    plt.tight_layout()
    figure = plt.gcf()
    return figure

# ------------------------------------------------------
# 画某一类量化产品某一时间的资产比例图
# ------------------------------------------------------
def qfv_quantFundAssetRatio(
    date,  # datetime.date
    strategy  # '500指增', '300指增', '1000指增', '市场中性'
):
    assert isinstance(date, datetime.date), 'date must be an instance of datetime.date'
    assert strategy in ('500指增', '300指增', '1000指增', '市场中性', '300对冲', '500对冲'), '目前只支持500指增、300指增、1000指增、市场中性类策略'
    if strategy == '300对冲':
        product_info = custHF.custHF_getProductInfo(product_status=['在库已投'], strategy_level_2=['市场中性'])
        fund_ids = list(config.product_additional_label['300对冲'].keys())
    elif strategy == '500对冲':
        product_info = custHF.custHF_getProductInfo(product_status=['在库已投'], strategy_level_2=['市场中性'])
        fund_ids = list(set(product_info['product_id'].to_list()) - set(config.product_additional_label['300对冲'].keys()))
    else:
        product_info = custHF.custHF_getProductInfo(product_status=['在库已投'], strategy_level_2=[strategy])
        fund_ids = product_info['product_id'].to_list()
    quant_fund_data = qfd.qfd_getQuantFundsExposure(date, date)
    quant_fund_data = quant_fund_data[quant_fund_data['product_id'].isin(fund_ids)]
    quant_fund_data = pd.merge(quant_fund_data, product_info[['product_id', 'product_short_name']], left_on='product_id', right_on='product_id', how='left')
    quant_fund_data = quant_fund_data[['date', 'product_short_name', 'cash', 'stock', 'bond', 'repo', 'future', 'option']]
    quant_fund_data.set_index('product_short_name', inplace=True)
    quant_fund_data.sort_index(inplace=True, ascending=False)
    plt.style.use('seaborn-white')
    plt.rcParams['font.sans-serif'] = ['SimHei']
    fig, ax = plt.subplots(figsize=(10, 10 * 0.618))
    quant_fund_data.plot(kind="bar", stacked=True, ax=ax)
    ax1 = ax.twinx()
    quant_fund_data['net_exposure'] = quant_fund_data['stock'] + quant_fund_data['future']
    ax1.scatter(ax.get_xticks(), quant_fund_data['net_exposure'], marker='^', color='black', label='净敞口（右）', s=300)
    ax.set_title(strategy + '资产比例以及净敞口：' + date.strftime('%Y-%m-%d'), fontsize=18)
    ax.legend(loc=2, bbox_to_anchor=(1, 1), borderaxespad=6, fontsize=12)
    ax.yaxis.set_major_formatter(ticker.PercentFormatter(xmax=1, decimals=2))
    ax1.yaxis.set_major_formatter(ticker.PercentFormatter(xmax=1, decimals=2))
    ax1.legend(loc='best')
    plt.xticks(fontsize=12)
    plt.grid(ls='--', axis='y')
    plt.tight_layout()
    figure = plt.gcf()
    return figure

# ------------------------------------------------------
# 画某一类量化产品某一时间的资产比例图，净敞口图
# ------------------------------------------------------
def qfv_quantFundAssetRatioTS(
    start_date,  # datetime.date
    end_date,  # datetime.date
    product_id
):
    assert isinstance(start_date, datetime.date), 'start_date must be an instance of datetime.date'
    assert isinstance(end_date, datetime.date), 'end_date must be an instance of datetime.date'
    product_info = custHF.custHF_getProductInfo()
    quant_fund_data = qfd.qfd_getQuantFundsExposure(start_date, end_date, product_ids=[product_id])
    quant_fund_data = pd.merge(quant_fund_data, product_info[['product_id', 'product_short_name']], on='product_id', how='left')
    quant_fund_data = quant_fund_data[['date', 'cash', 'stock', 'bond', 'repo', 'future', 'option']]
    quant_fund_data['净敞口'] = quant_fund_data['stock'] + quant_fund_data['future']
    quant_fund_data['date'] = quant_fund_data['date'].apply(pd.Timestamp)
    rename_dict = {
        'cash': '现金',
        'stock': '股票',
        'bond': '债券',
        'repo': '逆回购',
        'future': '期货',
        'option': '期权'
    }
    quant_fund_data.rename(columns=rename_dict, inplace=True)
    result = quant_fund_data.melt('date', var_name='asset_type', value_name='value')
    selection = alt.selection_multi(fields=['asset_type'], bind='legend', name='名称')
    base = alt.Chart(result[result['asset_type'] != '净敞口']).mark_area().encode(
            x=alt.X('date:T', title='日期', axis=alt.Axis(format='%Y/%m/%d')),
            y=alt.Y('value', title='比例', axis=alt.Axis(format='.2%')),
            color=alt.Color('asset_type', title='资产类型'),
            tooltip=[
                alt.Tooltip('asset_type:N', title="资产类型"),
                alt.Tooltip('date:T', title="日期", format='%Y-%m-%d'),  # 设置tooltip中的日期格式为 YYYY-MM-DD
                alt.Tooltip('value:Q', title="比例", format='.2%')],
            opacity=alt.condition(selection, alt.value(1), alt.value(0.1))
            )
    asset_ratio = base.add_selection(selection)
    # 新增 net_exposure 线
    nearest = alt.selection_single(nearest=True, on='mouseover', empty='none')
    net_exposure = alt.Chart(result[result['asset_type'] == '净敞口']).mark_line().encode(
        x=alt.X('date:T', title='日期', axis=alt.Axis(format='%Y/%m/%d')),
        y=alt.Y('value', title='净敞口', axis=alt.Axis(format='.2%')),
        color=alt.Color('asset_type', title=' '),
        tooltip=[
            alt.Tooltip('date:T', title="日期", format='%Y-%m-%d'),
            alt.Tooltip('value:Q', title="净敞口", format='.2%')
        ]
    )
    point = net_exposure.mark_point().encode(
        opacity=alt.condition(nearest, alt.value(1), alt.value(0))
    ).add_selection(nearest)
    net_exposure_line = alt.layer(net_exposure, point).properties(
        width=400,
        height=200
    )
    return asset_ratio, net_exposure_line

# ------------------------------------------------------
# 画成分股占比柱状图，并返回成分股数据
# ------------------------------------------------------
def qfv_quantFundIndexComponentRatio(
    date,  # datetime.date
    strategy  # '500指增', '300指增', '1000指增', '市场中性'
):
    assert isinstance(date, datetime.date), 'date must be an instance of datetime.date'
    assert strategy in ('500指增', '300指增', '1000指增', '市场中性', '300对冲', '500对冲'), '目前只支持500指增、300指增、1000指增、市场中性类策略'
    if strategy == '300对冲':
        product_info = custHF.custHF_getProductInfo(product_status=['在库已投'], strategy_level_2=['市场中性'])
        fund_ids = list(config.product_additional_label['300对冲'].keys())
    elif strategy == '500对冲':
        product_info = custHF.custHF_getProductInfo(product_status=['在库已投'], strategy_level_2=['市场中性'])
        fund_ids = list(set(product_info['product_id'].to_list()) - set(config.product_additional_label['300对冲'].keys()))
    else:
        product_info = custHF.custHF_getProductInfo(product_status=['在库已投'], strategy_level_2=[strategy])
        fund_ids = product_info['product_id'].to_list()
    quant_fund_data = qfd.qfd_getQuantFundsExposure(date, date)
    quant_fund_data = quant_fund_data[quant_fund_data['product_id'].isin(fund_ids)]
    quant_fund_data = pd.merge(quant_fund_data, product_info[['product_id', 'product_short_name']], left_on='product_id', right_on='product_id', how='left')
    rename_dict = {'date': '日期',
                   'product_short_name': '名称',
                   'stock_amount': '股票数量',
                   'stock': '股票仓位',
                   'component_ratio_300': '300成分股占比',
                   'component_ratio_500': '500成分股占比',
                   'component_ratio_1000': '1000成分股占比',
                   'component_ratio_2000': '2000成分股占比',
                   'component_ratio_others': '其他股票占比',
                   'component_ratio_micro': 'wind微盘成分股占比',
                   }
    quant_fund_data.rename(columns=rename_dict, inplace=True)
    component_ratio_columns = ['300成分股占比', '500成分股占比', '1000成分股占比', '2000成分股占比', '其他股票占比', 'wind微盘成分股占比']
    quant_fund_data[component_ratio_columns] = quant_fund_data[component_ratio_columns].multiply(quant_fund_data['股票仓位'], axis=0)
    quant_fund_data_table = quant_fund_data[list(rename_dict.values())]

    formatter = dict(zip(['股票数量', '股票仓位'] + component_ratio_columns, [lambda x: "{:,.0f}".format(x)] + [lambda x: "{:.2%}".format(x)] * len(['股票仓位'] + component_ratio_columns)))
    new_cmap = sns.diverging_palette(**config.cmap_kwargs)
    d1 = dict(selector="th", props=[('text-align', 'center')])
    d2 = dict(selector='caption', props=[('text-align', 'center'), ('font-weight', 'bold'), ('color', 'black'), ('font-size', '125%')])
    quant_fund_data_table = quant_fund_data_table.style.format(formatter, na_rep="").set_properties(**{'width': '100', 'text-align': 'center'})\
         .set_table_styles([d1]).set_table_styles([d2], overwrite=False)
    quant_fund_data_table = quant_fund_data_table.background_gradient(subset=component_ratio_columns ,cmap=new_cmap, low=config.cmap_range_adjust_coef, high=config.cmap_range_adjust_coef, axis=1)
    quant_fund_data_table = quant_fund_data_table.highlight_null('white')
    quant_fund_data_melt = quant_fund_data[component_ratio_columns+['日期', '名称']].melt(id_vars=['日期', '名称'], value_name='成分股比例', var_name='指数成分')
    selection = alt.selection_multi(nearest=True, fields=['指数成分'], bind='legend', name='名称')
    title_string = date.strftime('%Y-%m-%d') + "成分股比例(股票仓位调整后)"
    quant_fund_data_melt['堆叠顺序'] = quant_fund_data_melt['指数成分'].apply(lambda x: component_ratio_columns.index(x))
    base = alt.Chart(quant_fund_data_melt, title=title_string).mark_bar().encode(
            x=alt.X('名称', title='名称', sort=alt.EncodingSortField(field='名称', order='descending'), axis=alt.Axis(labelLimit=200)),
            y=alt.Y('成分股比例', title='成分股比例', axis=alt.Axis(format='%')),
            color=alt.Color('指数成分', scale=alt.Scale(domain=component_ratio_columns, scheme='category20')),
            order=alt.Order('堆叠顺序:Q', sort='descending'),
            tooltip=['名称', '指数成分', {'field': '成分股比例', 'format': '.2%'}],
            opacity=alt.condition(selection, alt.value(1), alt.value(0.1))
            ).properties(width=150, height=600).configure_header(titleFontSize=14, labelFontSize=14)
    chart_result = base.add_selection(selection)

    return chart_result, quant_fund_data_table