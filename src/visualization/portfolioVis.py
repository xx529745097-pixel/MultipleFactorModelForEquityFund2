import datetime
import numpy as np
import pandas as pd
import seaborn as sns
import dataframe_image as dfi
from bs4 import BeautifulSoup as bs
import matplotlib.pyplot as plt
import src.visualization.basicVis as basicVis
import src.analysis.portfolioAnalysis as portAnls
import altair as alt
import src.data.custFOF as custFOF
import src.data.custHF as custHF
import src.const as const
import src.config as config
import src.utils.fof_calendar as calendar
from matplotlib import cm
plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams["font.family"] = ["simhei"]

# ------------------------------------------------------
# 获取投资组合的整合信息
# ------------------------------------------------------
def visFOF_getSingleFOFHoldingData(
    date,
    portfolio_id,
    sector_type=None,   # 产品分类标准，默认为None, 展示的sector_type包括allocation_type,label_level_1,label_level_2三类；或者依照输入字符串进行展示，可选'allocation_type','label_level_1','label_level_2','product_type'
    rank_num=0,         # 是否做前N大持仓的筛选，默认为0，不筛选全量展示；输入不为0时，按照前rank_num进行筛选
    include_cost_info=False  # 是否包含买入成本价格、当前价格、持仓份额信息
):
    # 定义网页版sector type的集合: ['allocation_type', 'label_level_1', 'label_level_2', 'product_type', None]
    web_sector_type_list = ['allocation_type', 'label_level_1', 'label_level_2', 'product_type']
    assert sector_type in web_sector_type_list+[None], \
        "持仓分类标准输入需在'allocation_type','label_level_1','label_level_2','product_type',None的范围内"

    result = portAnls.anlsFOF_getSingleFOFHoldingData(date, portfolio_id, include_cost_info=include_cost_info)
    if sector_type:
        # 对每一层次的分类标签列分别设置排序规则, 将'其他'标签按自定义顺序排列至最后
        for sector_type_col_name in web_sector_type_list:
            sector_type_col_seq = result[sector_type_col_name].sort_values(ascending=False).unique().tolist()
            if '其他' in sector_type_col_seq:
                sector_type_col_seq.remove('其他')
                sector_type_col_seq.append('其他')
            result[sector_type_col_name] = result[sector_type_col_name].astype('category').cat.set_categories(sector_type_col_seq)
        # ascending 设置为True表示按照模板的正序顺序进行排序, weight默认False降序
        result.sort_values(by=web_sector_type_list+['product_weight'],
                           ascending=[True for _ in web_sector_type_list]+[False], inplace=True)
    else:
        result.sort_values(by='product_weight', ascending=False, inplace=True)
    if rank_num:
        assert sector_type is None, '做前N大持仓的筛选时, sector_type需设为None'
        result = result.head(rank_num)
    result = result[['portfolio_name', 'NAV', 'product_id', 'product_name', 'product_NAV', 'product_weight'] + ([sector_type] if sector_type else ['allocation_type', 'label_level_1', 'label_level_2']) + (['unit_cost', 'unit_val', 'product_volume', 'product_appreciation'] if include_cost_info else [])]
    rename_dict = {
        'portfolio_name': '组合名称',
        'NAV': '组合规模',
        'product_id': '产品ID',
        'product_name': '产品名称',
        'product_NAV': '产品规模',
        'product_weight': '产品权重',
        'unit_cost': '单位成本',
        'unit_val': '估值价格',
        'product_volume': '持仓份额',
        'product_appreciation': '估值增值',
        'allocation_type': '大类配置类型',
        'label_level_1': '一级标签',
        'label_level_2': '二级标签',
    }
    result.rename(columns=rename_dict, inplace=True)
    result.reset_index(drop=True, inplace=True)
    formatter = {'组合规模': '{:,.2f}', '产品规模': '{:,.2f}', '产品权重': '{:.2%}', '单位成本': '{:,.4f}', '估值价格': '{:,.4f}', '持仓份额': '{:,.2f}', '估值增值': '{:,.2f}'}
    def trade_type_color(val):
        color_list = []
        for v in val:
            if pd.isnull(v):
                color_list.append('color: black')
            elif v > 0:
                color_list.append('color: red')
            elif v < 0:
                color_list.append('color: green')
            else:
                color_list.append('color: black')
        return (color_list)
    result = result.style.format(formatter).applymap(lambda x: 'color: transparent' if pd.isnull(x) else '').background_gradient(subset=['产品规模', '产品权重'], cmap='Reds', low=0, high=config.cmap_range_adjust_coef).hide_index()
    if include_cost_info:
        result = result.apply(trade_type_color, axis=0, subset=['估值增值'])
    return result

# ------------------------------------------------------
# 获取投资组合的整合信息的图表
# ------------------------------------------------------
def visFOF_getFOFTopHolding(
    date,
    pm_name,
    type=None,
    client_region=None,
    product_type=None,
    level='产品',
    rank_num=None
):
    if pm_name == '全部':
        pm_name = None
    if product_type == '全部':
        product_type = None
    result = portAnls.anlsFOF_getFOFTopHolding(date, pm_name, type, client_region, product_type, level, rank_num)
    result['NAV'] = result['NAV'].round(2)
    formatter = {'Weight': '{:.2%}', 'NAV': '{:,}'}
    result = result.style.format(formatter).background_gradient(subset=['NAV', 'Weight'], cmap='Reds', low=0, high=config.cmap_range_adjust_coef)
    return result

# ------------------------------------------------------
# 获取投资组合的持仓类别信息的图示
# ------------------------------------------------------
def visFOF_getFOFSectorInfo(
    date,
    pm_name,
    type=None,
    client_region=None,
    level='product_type',      # Other options: 'label_level_1', 'label_level_2', 'allocation_type'
    portfolio_id=None,   # Default is all portfolio
):
    if pm_name == '全部':
        pm_name = None

    result = portAnls.anlsFOF_getFOFSectorInfo(date, pm_name, type, client_region, level, portfolio_id)
    base = alt.Chart(result).mark_arc().encode(
        theta=alt.Theta('sector_weight:Q', stack=True),
        color=alt.Color(level+':N'),
    )
    pie = base.mark_arc(outerRadius=120)
    text = base.mark_text(radius=140, size=10).encode(text=alt.Text('sector_weight:Q', format='.2%'))
    table_result = result.copy(deep=True)
    rename_dict = {
        'product_type': '产品类型',
        'label_level_1': '一级标签',
        'label_level_2': '二级标签',
        'allocation_type': '大类配置类型',
        'sector_NAV': '规模',
        'sector_weight': '权重'
    }
    table_result.rename(columns=rename_dict, inplace=True)
    table_result['规模'] = table_result['规模'].round(2)
    formatter = {'规模': '{:,}', '权重': '{:.2%}'}
    table_result = table_result.style.format(formatter).background_gradient(subset=['规模', '权重'], cmap='Reds', low=0, high=config.cmap_range_adjust_coef).hide_index()
    return {'chart': pie+text, 'table': table_result}

# ------------------------------------------------------
# 获取投资组合的持仓类别变化的图示
# ------------------------------------------------------
def visFOF_getFOFSectorChange(
    start_date,     # 比较区间的起始日期
    end_date,       # 比较区间的结束日期
    portfolio_id,   # 单一的组合id, string形式
    level='product_type',      # Other options: 'label_level_1', 'label_level_2', 'allocation_type'
):
    result = portAnls.anlsFOF_getFOFSectorChange(start_date, end_date, portfolio_id, level)
    result.rename(columns={
        'product_type': '产品类型',
        'label_level_1': '一级标签',
        'label_level_2': '二级标签',
        'allocation_type': '大类配置类型',
        'start_sector_weight': str(start_date)+'权重',
        'end_sector_weight': str(end_date)+'权重',
        'change': '变化值',
        'portfolio_id': '组合ID'
    }, inplace=True)
    del result['组合ID']
    table_result = result.copy(deep=True)
    sign_map = {1: "增加", -1: "减少", 0: "不变"}
    table_result['变化方向'] = np.sign(table_result['变化值']).apply(lambda x: sign_map[x])
    def change_direction_color(val):
        color_list = []
        for v in val:
            if str(v) == '增加':
                color_list.append('color: red')
            elif str(v) == '减少':
                color_list.append('color: green')
            else:
                color_list.append('color: black')
        return (color_list)
    formatter = {str(start_date)+'权重': '{:.2%}', str(end_date)+'权重': '{:.2%}', '变化值': '{:.2%}'}
    new_cmap = sns.diverging_palette(**config.cmap_kwargs)
    table_result = table_result.style.format(formatter).set_properties(**{'text-align': 'center'})\
        .background_gradient(subset=['变化值'], cmap=new_cmap, low=config.cmap_range_adjust_coef, high=config.cmap_range_adjust_coef, axis=0, vmin=-result['变化值'].abs().max(axis=0), vmax=result['变化值'].abs().max(axis=0)).apply(change_direction_color, axis=0, subset=['变化方向']).hide_index()
    return table_result

# ------------------------------------------------------
# 获取投资组合的持仓类别信息的时序数据
# ------------------------------------------------------
def visFOF_getFOFSectorInfoTS(
    date,
    period,
    pm_name,
    type=None,
    client_region=None,
    level='product_type',   # Other options: 'label_level_1', 'label_level_2', 'allocation_type'
    portfolio_id=None,      # Default is all portfolio
    start_date=None,        # for Customized period
    mf_wind_allocation_type=False,  # 是否需要结合wind标签信息，给公募产品打上权益类的大类资产标签，默认不使用
):
    if pm_name == '全部':
        pm_name = None

    start_date, end_date = calendar.calender_getStartEndDate(period, date, start_date)
    result = portAnls.anlsFOF_getFOFSectorInfo(end_date, pm_name, type, client_region, level, portfolio_id, data_mode='TS', start_date=start_date, mf_wind_allocation_type=mf_wind_allocation_type)
    result['date'] = pd.to_datetime(result['date']).dt.date
    result['year'] = result['date'].apply(lambda x: x.year)
    result['month'] = result['date'].apply(lambda x: x.month)
    result['is_year_last_date'] = (result['date'].isin(result[['date', 'year']].groupby(by='year').last()['date'].to_list())).apply(lambda x: '是' if x == True else '否')
    result['is_month_last_date'] = (result['date'].isin(result[['date', 'year', 'month']].groupby(by=['year', 'month']).last()['date'].to_list())).apply(lambda x: '是' if x == True else '否')
    ref_data = custFOF.custFOF_getFOFReferenceData(include_advisory_account=True)
    port_name = ref_data[ref_data['portfolio_id'] == portfolio_id]['portfolio_name'].iloc[0]
    result['portfolio_name'] = port_name
    table_result = result.copy(deep=True)[['date', 'portfolio_name', 'allocation_type', 'sector_NAV', 'sector_weight', 'year', 'month', 'is_year_last_date', 'is_month_last_date']]
    chart = alt.Chart(result, title='【实际数据】账户持仓分布时序图 - %s'%(port_name)).mark_area().encode(
        x='date',
        y=alt.Y('sector_weight', stack='normalize'),
        color=level,
        tooltip=['date', level, {'field': 'sector_weight', 'format': '.2%'}]
    )

    return table_result, chart.interactive()

# ---------------------------------------------------------------------
# 获取FOF账户在指定区间内的Mirabelli收益率归因按照选择分类层级的汇总数据
# 输出内容包括对应层级的收益归因统计表，和收益归因的横向柱状图
# ---------------------------------------------------------------------
def visFOF_getFOFMirabelliAttributionbySector(
    portfolio_id,  # 投资组合的ID, str
    date,
    period,
    start_date=None,
    level='product_type',   # Other options: 'label_level_1', 'label_level_2', 'allocation_type', 'company_name', 'strategy_name', 'product_name'
    fee_display=True,       # 是否展示归因结果中的费用项，以适配不同使用场景
):
    result = portAnls.anlsFOF_getFOFMirabelliAttributionbySector(portfolio_id, date, period, start_date, level)
    rename_dict = {
        'product_type': '产品类型',
        'label_level_1': '一级标签',
        'label_level_2': '二级标签',
        'allocation_type': '大类配置类型',
        'company_name': '公司',
        'strategy_name': '策略',
        'product_name': '产品',
        'portfolio_name': '名称',
        'product_mirabelli_attribution': '收益归因',
        'start_date': '开始日期',
        'end_date': '截止日期',
    }
    result.rename(columns=rename_dict, inplace=True)
    result_col_order = result.columns.drop(['开始日期', '截止日期']).values.tolist()
    result_col_order.insert(1, '截止日期')
    result_col_order.insert(1, '开始日期')
    result = result[result_col_order]
    # 如果选择不展示费用项，总计项也不展示
    if not fee_display:
        result = result[~result[rename_dict[level]].isin(['费用及杂项', '总计'])]

    table_result = result.copy(deep=True)
    formatter = {'收益归因': '{:.4%}'}
    new_cmap = sns.diverging_palette(**config.cmap_kwargs)
    table_result = table_result.style.format(formatter).set_properties(**{'text-align': 'center'})\
        .background_gradient(subset=['收益归因'], cmap=new_cmap, low=config.cmap_range_adjust_coef, high=config.cmap_range_adjust_coef, axis=0, vmin=-result['收益归因'].abs().max(axis=0), vmax=result['收益归因'].abs().max(axis=0)).hide_index()

    result = result[result[rename_dict[level]] != '总计']
    max_ytick = result['收益归因'].abs().max()*1.01
    min_ytick = -max_ytick
    title_string = '区间收益归因 - ' + rename_dict[level] + ' - ' + str(result['开始日期'].iloc[0]) + ' - ' + str(result['截止日期'].iloc[0])
    nearest = alt.selection_single(nearest=True, on='mouseover', empty='none')
    chart_result = alt.Chart(result, title=title_string).mark_bar().encode(
            x=alt.X('收益归因', scale=alt.Scale(domain=[min_ytick, max_ytick]), title='收益归因',axis=alt.Axis(format='%')),
            y=alt.Y(rename_dict[level]+':N', sort='-x'),
            color=alt.condition(alt.datum.收益归因 > 0, alt.value("red"), alt.value("green")),
            tooltip=[rename_dict[level], {'field':'收益归因','format':'.4%'}],
            text=rename_dict[level],
            )
    point = chart_result.mark_point().encode(
            opacity=alt.condition(nearest, alt.value(1), alt.value(0)),
            y=alt.Y(rename_dict[level] + ':N', sort='-x'),
            ).add_selection(nearest)

    return table_result, chart_result

# ---------------------------------------------------------------------
# 获取FOF账户在指定区间内的Mirabelli收益率归因按照选择分类层级的汇总数据
# 输出内容包括对应层级的收益归因统计表，和收益归因的横向柱状图
# ---------------------------------------------------------------------
def visFOF_getFOFMirabelliAttributionCumSeries(
    portfolio_id,  # 投资组合的ID, str
    date,
    period,
    start_date=None,
    level='product_type',   # Other options: 'label_level_1', 'label_level_2', 'allocation_type', 'company_name', 'strategy_name', 'product_name'
    fee_display=True,       # 是否展示归因结果中的费用项，以适配不同使用场景
):
    result = portAnls.anlsFOF_getFOFMirabelliAttributionCumSeries(portfolio_id, date, period, start_date, level)
    rename_dict = {
        'product_type': '产品类型',
        'label_level_1': '一级标签',
        'label_level_2': '二级标签',
        'allocation_type': '大类配置类型',
        'company_name': '公司',
        'strategy_name': '策略',
        'product_name': '产品',
        'portfolio_name': '名称',
        'date': '日期',
        'product_mirabelli_attribution': '单日收益归因',
        'product_mirabelli_attribution_cumsum': '累计收益归因',
    }
    result.rename(columns=rename_dict, inplace=True)
    date_list = result['日期'].unique()
    level_col = rename_dict[level]
    # 如果选择不展示费用项，组合收益也不展示
    if not fee_display:
        result = result[~result[level_col].isin(['费用及杂项', '组合收益'])]

    table_result = result.copy(deep=True)
    result["日期"] = result["日期"].apply(pd.Timestamp)
    max_ytick = result['累计收益归因'].abs().max()*1.01
    min_ytick = -max_ytick
    nearest = alt.selection_single(nearest=True, on='mouseover', empty='none')
    selection = alt.selection_multi(nearest=True, fields=[level_col], bind='legend', name='名称')
    title_string = "收益归因时序图 - " + level_col + " - " + str(date_list[1]) + ' - ' + str(date_list[-1])
    result1 = result[result[level_col] != '组合收益']
    result2 = result[result[level_col] == '组合收益']
    base = alt.Chart(result1, title=title_string).mark_line().encode(
            x=alt.X('日期:T', title='日期', axis=alt.Axis(format='%Y/%m/%d')),
            y=alt.Y('累计收益归因', scale=alt.Scale(domain=[min_ytick, max_ytick]), title='收益归因'),
            color=alt.Color(level_col, scale=alt.Scale(scheme='category20')),
            tooltip=['日期', level_col, {'field': '累计收益归因', 'format': '.4%'}],
            opacity=alt.condition(selection, alt.value(1), alt.value(0.1))
            )
    lines = base.add_selection(selection)
    if fee_display:
        area = alt.Chart(result2).mark_area().encode(
                x=alt.X('日期:T', title='日期', axis=alt.Axis(format='%Y/%m/%d')),
                y=alt.Y('累计收益归因', scale=alt.Scale(domain=[min_ytick, max_ytick]), title='收益归因', axis=alt.Axis(format='%')),
                color=alt.value('pink'),
                tooltip=['日期', level_col, {'field': '累计收益归因', 'format': '.4%', 'title': '累计收益'}],
                opacity=alt.condition(selection, alt.value(1), alt.value(0.1))
                ).add_selection(nearest)
        chart_result = alt.layer(area, lines).interactive().configure_axisX(labelAngle=0)
    else:
        chart_result = lines

    return table_result, chart_result

# ---------------------------------------------------------------------
# 获取FOF账户在指定区间内的Mirabelli月度收益率归因
# 按照每个自然月，对各level的收益贡献进行汇总
# ---------------------------------------------------------------------
def visFOF_getFOFMirabelliMonthlyAttribution(
    portfolio_id,  # 投资组合的ID, str
    date,
    num_trailing_month=6,  # 展示过去几个月的收益,默认6个月
    level='product_type',  # Other options: 'label_level_1', 'label_level_2', 'allocation_type', 'company_name', 'strategy_name', 'product_name'
    fee_display=True,      # 是否展示归因结果中的费用项，以适配不同使用场景
):
    result = portAnls.anlsFOF_getFOFMirabelliMonthlyAttribution(portfolio_id, date, num_trailing_month, level)
    rename_dict = {
        'product_type': '产品类型',
        'label_level_1': '一级标签',
        'label_level_2': '二级标签',
        'allocation_type': '大类配置类型',
        'company_name': '公司',
        'strategy_name': '策略',
        'product_name': '产品',
        'portfolio_name': '名称',
        'date': '日期',
        'month': '月',
        'year': '年',
        'start_date': '开始日期',
        'end_date': '截止日期',
        'data_type': '数据类型',
        'product_mirabelli_attribution': '月度收益归因',
    }
    result.rename(columns=rename_dict, inplace=True)
    date_list = result['日期'].unique()
    level_col = rename_dict[level]
    # 如果选择不展示费用项，组合收益也不展示
    if not fee_display:
        result = result[~result[level_col].isin(['费用及杂项', '组合收益'])]

    table_result = result.copy(deep=True)
    nearest = alt.selection_single(nearest=True, on='mouseover', empty='none')
    selection = alt.selection_multi(nearest=True, fields=[level_col], bind='legend', name='名称')
    title_string = "月度收益归因 - " + level_col + " - " + str(date_list[0]) + ' - ' + str(date_list[-1])
    base = alt.Chart(result[['名称', level_col, '月度收益归因', '数据类型', '日期']], title=title_string).mark_bar().encode(
            x=alt.X('数据类型', title='数据类型', sort=None),
            y=alt.Y('月度收益归因', title='月度收益归因', axis=alt.Axis(format='%')),
            column=alt.Column('日期', sort=alt.EncodingSortField(field='order', order='ascending')),
            color=alt.Color(level_col, scale=alt.Scale(scheme='category20')),
            tooltip=['日期', level_col, {'field':'月度收益归因','format':'.4%'}],
            opacity=alt.condition(selection, alt.value(1), alt.value(0.1))
            ).properties(width=150).configure_header(titleFontSize=14, labelFontSize=14)
    chart_result = base.add_selection(selection)

    return table_result, chart_result

# ------------------------------------------------------
# 获取投资组合AUM分布的图示
# ------------------------------------------------------
def visFOF_getFOFAUMDistribution(
    date,
    pm_name=None,
    port_type=None,
    client_region=None,
    chart_dimension='level_1_type',  # 绘图时数据展开的维度，选择范围：'level_1_type','level_2_type','level_3_type','management_type',
):
    if pm_name == '全部':
        pm_name = None
    nav_result, account_result = portAnls.anlsFOF_getFOFAUMDistribution(date, pm_name, port_type, client_region, chart_dimension)
    nav_result['portfolio_NAV'] = nav_result['portfolio_NAV']/1e8
    nav_result.rename(columns={'portfolio_NAV': 'portfolio_NAV(亿)'}, inplace=True)
    nav_table_result = nav_result.copy(deep=True)
    nav_result.drop(nav_result.tail(1).index, inplace=True)  # 只有表格展示合计数据，柱状图不展示合计数据
    nav_result = alt.Chart(nav_result).mark_bar().encode(
        x='portfolio_NAV(亿):Q',
        y=alt.Y(chart_dimension+":N", sort='-x')
    )
    text = nav_result.mark_text(
    align='left',
    baseline='middle',
    dx=3).encode(text=alt.Text('portfolio_NAV(亿):Q', format='.2f'))
    nav_table_result['portfolio_NAV(亿)'] = nav_table_result['portfolio_NAV(亿)'].round(2)
    formatter = {'portfolio_NAV(亿)': '{:,}'}
    nav_table_result = nav_table_result.style.format(formatter).background_gradient(subset=['portfolio_NAV(亿)'], cmap='Reds', low=0, high=config.cmap_range_adjust_coef).hide_index()

    account_result.rename(columns={'portfolio_count': '账户数量'}, inplace=True)
    account_table_result = account_result.copy(deep=True)
    account_result.drop(account_result.tail(1).index, inplace=True)  # 只有表格展示合计数据，柱状图不展示合计数据
    account_result = alt.Chart(account_result).mark_bar().encode(
        x='账户数量:Q',
        y=alt.Y(chart_dimension + ":N", sort='-x')
    )
    text = account_result.mark_text(
        align='left',
        baseline='middle',
        dx=3).encode(text=alt.Text('账户数量:Q', format='{:,d}'))
    formatter = {'账户数量': '{:,d}'}
    account_table_result = account_table_result.style.format(formatter).background_gradient(subset=['账户数量'], cmap='Reds', low=0, high=config.cmap_range_adjust_coef).hide_index()
    return {'portfolio_NAV': {'chart': nav_result, 'table': nav_table_result}, 'portfolio_count': {'chart': account_result, 'table': account_table_result}}

# ----------------------------------------------------------------
# FOF组合投资的底层资产（产品或策略或公司）超过某一比例阈值的规模和比例数据展示
# ----------------------------------------------------------------
def visFOF_getFOFListByAsset(
    date,
    level_ids,      # 产品或策略或公司ids, 与level选项对应
    product_type,   # 目前支持 私募产品, 公募产品, 现金
    level,          # 资产层级 目前支持 产品 策略 公司
    pm_name=None,
    port_type=None,
    client_region=None,
    percent_threshold=0.01,
    detail_mode=False,      # 资产层级选择策略、公司时，展示底层产品的持仓情况
):
    if pm_name == '全部':
        pm_name = None
    rename_dict = {'portfolio_name': '组合名称',
                   'level_3_type': '三级分类',
                   'product_name': '产品名称',
                   'product_volume': '持仓份额',
                   'product_NAV': '产品规模',
                   'product_weight': '产品权重',
                   'strategy_name': '策略名称',
                   'strategy_NAV': '策略规模',
                   'strategy_weight': '策略权重',
                   'company_name': '公司名称',
                   'company_NAV': '公司规模',
                   'company_weight': '公司权重',
                   'pm_name': '投资经理',
                   'client_region': '客户区域'}
    level_cols_mapping = {
        '产品': {'NAV': 'product_NAV', 'weight': 'product_weight'},
        '策略': {'NAV': 'strategy_NAV', 'weight': 'strategy_weight'},
        '公司': {'NAV': 'company_NAV', 'weight': 'company_weight'},
    }
    def hyperlink(x):
        ret = f"""<a target="_blank" href="/FOF组合分析/?sidebar1=True&date1=%s&sector1=%s&port1=%s">%s</a>""" % (date.strftime('%Y-%m-%d'), '', x, x)
        return ret
    result = portAnls.anlsFOF_getFOFListByAsset(date, level_ids, product_type, level, pm_name, port_type, client_region, percent_threshold, detail_mode)
    # 展示产品一级反查持仓结果时(level为产品时和detail_mode为True时)，会展示持仓量product_position
    formatter = {rename_dict[level_cols_mapping[level]['weight']]: '{:.2%}', rename_dict[level_cols_mapping[level]['NAV']]: '{:,.2f}', rename_dict['product_volume']: '{:,.2f}'}
    gradient_subset = [level_cols_mapping[level]['weight'], level_cols_mapping[level]['NAV']] + (['product_volume'] if level == '产品' else [])
    if detail_mode:
        formatter.update({rename_dict['product_weight']: '{:.2%}', rename_dict['product_NAV']: '{:,.2f}'})
        gradient_subset += ['product_weight', 'product_NAV', 'product_volume']
    result = result.rename(columns=rename_dict)
    html_result = result.copy()
    html_result[rename_dict['portfolio_name']] = html_result[rename_dict['portfolio_name']].apply(lambda x: hyperlink(x) if x != '合计' else x)
    gradient_subset = [rename_dict[e] for e in gradient_subset]
    html_result = html_result.style.format(formatter).background_gradient(subset=gradient_subset, cmap='Reds', low=0, high=config.cmap_range_adjust_coef).highlight_null('white')
    html_result = html_result.render(escape=False)
    html_result = bs(html_result, 'lxml').prettify()
    return html_result, result

# ------------------------------------------------------
# FOF组合账户总览
# ------------------------------------------------------
def visFOF_platformOverview(
    date,
    period,
    portfolio_types,
    sector_type,
    pm_name,
    start_date,
    client_region=None,     # 筛选客户区域
):
    if pm_name == '全部':
        pm_name = None
    if period != 'Customized':
        start_date = None
    result = portAnls.anlsFOF_platformOverview(date, period, portfolio_types, const.const.WEB_SECTOR_TYPE_LIST[sector_type], pm_name, start_date=start_date, include_flag=True, client_region=client_region)
    result['AUM'] = result['AUM']/1e8
    result['t0_available_cash'] = result['t0_available_cash']/1e4
    def hyperlink(x):
        ret = f"""<a target="_blank" href="/FOF组合分析/?sidebar1=True&date1=%s&sector1=%s&port1=%s">%s</a>""" % (
    date.strftime('%Y-%m-%d'), sector_type, x, x)
        return ret

    # 避免下载文件中有超链接乱码，设置辅助列，保证表格重新排序后数据的准确性
    result['portfolio_name_str'] = result['portfolio_name']
    result['portfolio_name'] = result['portfolio_name'].apply(lambda x: hyperlink(x))
    result = result.sort_values(['advisory_or_not', 'level_3_type', 'AUM'], ascending=[True, True, False], na_position='last').reset_index(drop=True)  # 将投顾账户排在最后
    result_port_name_str = result['portfolio_name_str'].copy(deep=True)
    del result['portfolio_type'], result['portfolio_name_str'], result['advisory_or_not']

    result.rename(columns={
        'date': '日期',
        'portfolio_name':'名称',
        'level_3_type': '三级分类',
        'portfolio_type': '类型',
        'inception_date': '成立日期',
        't0_available_cash': 'T0资金(万)',
        'AUM': '规模(亿)',
        'NAV': '净值',
        'YTD_flag': 'YTD',
        'SI_flag': 'SI',
        'period':'区间',
        'period_return': '收益',
        'annualized_period_return': '年化收益',
        'annualized_volatility': '波动率',
        'max_drawdown':'最大回撤',
        'sharpe_ratio': '夏普',
        'calmar': '卡玛',
        'current_drawdown':'当前回撤'}, inplace=True)

    formatter = {
        '规模(亿)': lambda x: "{:.2f}".format(x),
        'T0资金(万)': lambda x: "{:,.2f}".format(x),
        '净值': lambda x: "{:.4f}".format(x),
        '收益': lambda x: "{:.2%}".format(x),
        '年化收益': lambda x: "{:.2%}".format(x),
        '波动率': lambda x: "{:.2%}".format(x) if not isinstance(x, str) else x,
        '最大回撤': lambda x: "{:.2%}".format(x),
        '当前回撤': lambda x: "{:.2%}".format(x),
        '夏普': lambda x: "{:.2f}".format(x) if not isinstance(x, str) else x,
        '卡玛': lambda x: "{:.2f}".format(x),
    }

    sector_col = custFOF.custFOF_getUnderlyingLabelInfo(const.const.WEB_SECTOR_TYPE_LIST[sector_type])
    for col in sector_col+['其他']:
        formatter[col] = lambda x: "{:.2%}".format(x)
    del result['portfolio_id']
    dfs = result.reset_index(drop=True).style.format(formatter=None, na_rep="").format(formatter, na_rep="")  # 缺失值填充范围根据formatter范围确定， formatter=None表示对所有列应用
    dfs = dfs.set_table_styles([{"selector": "th,tr", "props": [("white-space", "nowrap"), ("word-break", "keep-all"), ('text-align', 'center')]},
    ]).set_properties(**{'text-align': 'center'})

    def color_col(col, pattern_map, default=''):
        return np.select(
            [col.str.contains(k, na=False) for k in pattern_map.keys()],
            [f'color: {v}' for v in pattern_map.values()],
            default=default
        ).astype(str)

    new_cmap = sns.diverging_palette(**config.cmap_kwargs)
    for col in result.columns.drop(['日期', '名称', '三级分类', '成立日期', '净值', '区间']):
        if col == '波动率':
            dfs = dfs.background_gradient(subset=col, cmap=sns.diverging_palette(**config.vol_cmap_kwargs), low=config.cmap_range_adjust_coef, high=config.cmap_range_adjust_coef, axis=0)
        elif col in ['最大回撤', '当前回撤']:
            dfs = dfs.background_gradient(subset=col, cmap=new_cmap, low=config.cmap_range_adjust_coef, high=config.cmap_range_adjust_coef, axis=0)
        elif col in ['收益', '年化收益', '夏普', '卡玛']:
            dfs = dfs.background_gradient(subset=col, cmap=new_cmap, low=config.cmap_range_adjust_coef, high=config.cmap_range_adjust_coef, axis=0,
                                        vmin=(-result[col].abs().max(axis=0)),
                                        vmax=result[col].abs().max(axis=0))
        elif col in sector_col:
            dfs = dfs.bar(subset=col, color='lightblue')
        elif col == '规模(亿)':
            dfs = dfs.bar(subset=col, color='#ffbb8b')
        elif col == 'T0资金(万)':
            dfs = dfs.bar(subset=col, color=['light_green', '#ffbb8b'])
        elif col in ['YTD', 'SI']:
            dfs.apply(color_col, pattern_map={'红': 'red', '黄': 'yellow', '绿': 'green'}, subset=[col])
    dfs = dfs.highlight_null('white')
    html = dfs.render(escape=False)
    html = bs(html, 'lxml').prettify()
    dfs.data['名称'] = result_port_name_str  # 下载数据时，名称列不使用超链接，方便使用
    return html, dfs

# ------------------------------------------------------
# 获取单一FOF账户基本信息
# ------------------------------------------------------
def visFOF_getSingleFoFBasicInfo(
        portfolio_id,   # FOF组合代码
        date            # FOF组合净值及规模日期，向前取最近一天净值及规模
):
    all_accounts = custFOF.custFOF_getFOFReferenceData(include_advisory_account=True, include_additional_info=True)
    this_account = all_accounts[all_accounts['portfolio_id'] == portfolio_id]
    account_nav = custFOF.custFOF_getFOFNetValueAndReturn(date - datetime.timedelta(days=30), date, [portfolio_id], freq=this_account['freq'].iloc[0])
    t0_available_cash = custFOF.custFOF_getT0AvailableCash()
    this_account = pd.merge(this_account, t0_available_cash, on='portfolio_id', how='left')
    # 针对金额法估值的产品，无单位净值数据，但仍支持查看T0可用以及其他基本信息
    if len(account_nav):
        account_nav = account_nav.sort_values('date').iloc[-1]
        this_account['nav'] = account_nav['NAV']
        this_account['aum'] = account_nav['AUM']
        this_account['nav_date'] = account_nav['date']
    this_account = this_account[['portfolio_name', 'level_3_type', 'pm_name'] + (['nav_date', 'nav', 'aum'] if len(account_nav) else []) + ['t0_available_cash', 'inception_date', 'client_region', 'client_office', 'client_manager', 'client_type', 'benchmark']]
    this_account.rename(columns={'portfolio_name': '组合名称', 'level_3_type': '账户类型', 'pm_name': '投资经理', 'nav_date': '净值日期', 'nav': '单位净值', 'aum': '组合规模', 't0_available_cash': 'T0可用资金', 'inception_date': '成立日期',
                                 'client_region': '客户区域', 'client_office': '区域分支机构', 'client_manager': '客户经理', 'client_type': '客户类型', 'benchmark': '投委会基准'}, inplace=True)
    return this_account

# ------------------------------------------------------
# 获取投资组合底层各类策略的绩效表现汇总表
# ------------------------------------------------------
def visFOF_getFOFSubCategoryPerfTable(
    date,
    periods,
    portfolio_id,
    sub_category,
    start_date=None,  # This parameter ONLY works for period list contains Customized
    mode='COMMON_ACCOUNT',  # 目前获取子策略收益序列支持两种模式：1. COMMON_ACCOUNT：非投顾账户，利用归因模型结果，对T日子策略贡献按照T-1权重进行放缩还原，形成收益率序列;
                            # 2.ADVISORY_ACCOUNT：投顾账户，直接利用子策略持仓权重，和可得的产品收益率进行计算
    display_mode='ppt',     # 支持ppt和web两种展示模式，ppt是写死的多period多指标；web是支持单选period，展示子策略、基准、超额在该period的所有指标
    customized_bm=None,     # 支持自定义选择对比基准，默认为None则使用默认config；如果选择则需给定{'benchmark_source': 'wind', 'benchmark': 'CAMO2.WI', 'name': '中信证券商品动量2.0'}结构的字典
):
    assert display_mode in ('ppt', 'web'), "仅支持ppt和web两种展示模式"
    if display_mode == 'ppt':
        assert 'Customized' not in periods, "ppt子策略展示模式不支持自选区间"
        assert start_date is None, "ppt子策略展示模式不支持自选区间"
    else:
        assert len(periods) == 1, "web子策略展示模式仅支持选择一个period"
    result = []
    for period in periods:
        this_result = portAnls.anlsFOF_getFOFSubCategoryPerfTable(date, period, portfolio_id, sub_category, start_date, mode, customized_bm)
        this_result['period'] = period
        if len(this_result) != 0:
            result.append(this_result)
    if not result:
    # 对应Sub Category无结果输出
        return None
    result = pd.concat(result)
    result = result.reset_index()
    result.rename(columns={
        'period_return': '区间收益率',
        'annualized_period_return': '年化区间收益率',
        'max_drawdown': '最大回撤',
        'sharpe_ratio': '夏普',
        'calmar': '卡玛比',
        'annualized_volatility': '年化波动率',
        'level_name': '名称',
        'start_date': '开始日期',
        'end_date': '截止日期',
        'year_return_rank': '今年以来收益率排名',
        'period': '统计区间',
        'freq': '数据频率'
    }, inplace=True)

    # 记录不同时间区间的数据频率情况
    freq_dict = result[['统计区间', '数据频率']].set_index('统计区间').to_dict(orient='dict')['数据频率']

    result['名称'] = result['名称'].apply(lambda x: '相对超额' if x == 'excess_return' else x)
    result[['区间收益率', '年化区间收益率', '最大回撤', '年化波动率', '夏普', '卡玛比']] = result[['区间收益率', '年化区间收益率', '最大回撤', '年化波动率', '夏普', '卡玛比']].astype(float)
    if display_mode == 'ppt':
        perf_result = pd.pivot_table(result, index=['index', '名称'], columns=['统计区间'], values=['区间收益率', '年化区间收益率', '最大回撤', '年化波动率', '夏普', '卡玛比'])
        perf_result['截止日期'] = max(result['截止日期'])
        perf_result['开始日期'] = min(result['开始日期'])
        perf_result.reset_index(inplace=True)

        # 展示时只取有数据的列，防止账户年份不足 或 最近period无数据但之前有数据，导致的取数错误
        perf_result_origin_col = [('名称', ''), ('开始日期', ''), ('截止日期', ''), ('区间收益率', 'Recent_1M'), ('区间收益率', 'Recent_3M'), ('区间收益率', 'YTD'), ('区间收益率', '2024'), ('区间收益率', '2023'),
                                ('区间收益率', '2022'), ('区间收益率', '2021'), ('区间收益率', 'SI'), ('年化区间收益率', 'SI'), ('最大回撤', 'YTD'), ('最大回撤', 'SI'), ('年化波动率', 'YTD'), ('年化波动率', 'SI'),
                                ('夏普', 'YTD'), ('夏普', 'SI'), ('卡玛比', 'YTD'), ('卡玛比', 'SI')]
        perf_result_col = list(set(perf_result_origin_col).intersection(set(perf_result.columns)))
        # 交集运算后元素顺序混乱，按照原序重新排列
        perf_result_col.sort(key=perf_result_origin_col.index)
        perf_result = perf_result[perf_result_col]

        # 更新列名中的period字段，加入freq的信息
        perf_result_col_with_freq = [(col[0], col[1] + ' (' + freq_dict[col[1]] + ')') if col[1] else col for col in perf_result.columns]
        perf_result.columns = pd.MultiIndex.from_tuples(perf_result_col_with_freq)
    else:
        perf_result = result[['名称', '统计区间', '开始日期','截止日期','区间收益率','年化区间收益率','最大回撤','年化波动率','夏普','卡玛比']]

    formatter = {
        '区间收益率': lambda x: "{:.2%}".format(x),
        '年化区间收益率': lambda x: "{:.2%}".format(x),
        '年化波动率': lambda x: "{:.2%}".format(x) if not isinstance(x, str) else x,
        '最大回撤': lambda x: "{:.2%}".format(x),
        '夏普': lambda x: "{:.2f}".format(x) if not isinstance(x, str) else x,
        '卡玛比': lambda x: "{:.2f}".format(x),
        '年化区间超额收益': lambda x: "{:.2%}".format(x),
        '开始日期': lambda x: x.strftime("%Y-%m-%d"),
        '截止日期': lambda x: x.strftime("%Y-%m-%d"),
        '名称': lambda x: str(x),
        '今年以来收益率排名': lambda x: "{:.2%}".format(x),
        '统计区间': lambda x: str(x)
    }
    performance_data = perf_result
    format_dict = {
        col_key: formatter[level]
        for level in formatter
        for col_key in [col for col in performance_data if col[0] == level]
    } if display_mode == 'ppt' else formatter
    new_cmap = sns.diverging_palette(**config.cmap_kwargs)
    d1 = dict(selector="th", props=[('text-align', 'center'), ('border', '1px solid black')])
    d2 = dict(selector='caption',
              props=[('text-align', 'center'), ('font-weight', 'bold'), ('color', 'black'), ('font-size', '125%')])
    _df_caption = '绩效数据, ' + '统计区间: ' + str(periods) + ', 比较基准: ' + str(performance_data['名称'][1])
    df = performance_data.reset_index(drop=True).style.format(format_dict, na_rep="") \
        .set_properties(**{'width': '100', 'text-align': 'center'}) \
        .set_caption(_df_caption).set_table_styles([d1]) \
        .set_table_styles([d2], overwrite=False).hide_index()  # hide_index,不显示第一列无用index
    for col in performance_data.columns.drop(['名称', '开始日期', '截止日期']):
        if '年化波动率' in col:
            df = df.background_gradient(subset=[col], cmap=sns.diverging_palette(**config.vol_cmap_kwargs), low=config.cmap_range_adjust_coef, high=config.cmap_range_adjust_coef, axis=0)
        elif '最大回撤' in col:
            df = df.background_gradient(subset=[col], cmap=new_cmap, low=config.cmap_range_adjust_coef, high=config.cmap_range_adjust_coef, axis=0)
        elif '统计区间' not in col:
            df = df.background_gradient(subset=[col], cmap=new_cmap, low=config.cmap_range_adjust_coef, high=config.cmap_range_adjust_coef, axis=0,
                                        vmin=(-performance_data[col].abs().max(axis=0)),
                                        vmax=performance_data[col].abs().max(axis=0))
    df = df.highlight_null('white')
    return df

# ------------------------------------------------------
# 获取投资组合底层各类策略及比较基准的净值曲线图
# ------------------------------------------------------
def visFOF_getFOFSubCategoryPerfChart(
    date,
    period,
    portfolio_id,
    sub_category,
    start_date=None,  # This parameter ONLY works for period list contains Customized
    mode='COMMON_ACCOUNT',  # 目前获取子策略收益序列支持两种模式：1. COMMON_ACCOUNT：非投顾账户，利用归因模型结果，对T日子策略贡献按照T-1权重进行放缩还原，形成收益率序列;
                            # 2.ADVISORY_ACCOUNT：投顾账户，直接利用子策略持仓权重，和可得的产品收益率进行计算
    customized_bm=None,     # 支持自定义选择对比基准，默认为None则使用默认config；如果选择则需给定{'benchmark_source': 'wind', 'benchmark': 'CAMO2.WI', 'name': '中信证券商品动量2.0'}结构的字典
):
    result = portAnls.anlsFOF_getFOFSubCategoryPerfChart(date, period, portfolio_id, sub_category, start_date, mode, customized_bm)
    if result.empty:
    # 对应Sub Category无结果输出
        return None
    result["date"] = result["date"].apply(pd.Timestamp)
    max_ytick = result['nav'].max() * 1.01
    min_ytick = result['nav'].min() * 0.99
    nearest = alt.selection_single(nearest=True, on='mouseover', empty='none')
    selection = alt.selection_multi(fields=['id'], bind='legend', name='名称')
    color_map = alt.Scale(domain=[result.loc[result['nav_type']=='category','id'].iloc[0],result.loc[result['nav_type']=='bm','id'].iloc[0],
                                  result.loc[result['nav_type']=='excess','id'].iloc[0]], range=['#4674a4',  '#f58518' ,'#ff2b2b'])
    title_string = "产品底层策略超额表现, 统计区间: " + str(period) + ", 数据频率: " + str(result['freq'].iloc[0])
    base = alt.Chart(result, title=title_string).mark_line().encode(
        x=alt.X('date:T', title='日期', axis=alt.Axis(format='%Y/%m/%d')),
        y=alt.Y('nav', scale=alt.Scale(domain=[min_ytick, max_ytick]), title='区间累计收益'),
        color=alt.Color('id', legend=alt.Legend(title='', orient='bottom', direction='horizontal', labelLimit=0, columns=2),scale=color_map ),
        tooltip=['id', 'date', 'nav'],
        opacity=alt.condition(selection, alt.value(1), alt.value(0.1))
    )
    point = base.mark_point().encode(
        opacity=alt.condition(nearest, alt.value(1), alt.value(0))
    ).add_selection(nearest)
    lines = base.add_selection(selection)
    c = alt.layer(lines, point).interactive().configure_axisX(labelAngle=0)

    return c

# ------------------------------------------------------
# 获取投资组合底层各类策略的月度收益
# ------------------------------------------------------
def visFOF_getFOFSubCategoryMonthlyReturn(
    date,
    portfolio_id,
    sub_category,
    num_trailing_month=None,  # 展示过去几个月的收益
    mode='COMMON_ACCOUNT',  # 目前获取子策略收益序列支持两种模式：1. COMMON_ACCOUNT：非投顾账户，利用归因模型结果，对T日子策略贡献按照T-1权重进行放缩还原，形成收益率序列;
    # 2.ADVISORY_ACCOUNT：投顾账户，直接利用子策略持仓权重，和可得的产品收益率进行计算
):
    result = portAnls.anlsFOF_getFOFSubCategoryMonthlyReturn(date, 'SI', portfolio_id, sub_category, mode)
    if result.empty:
        return None
    portfolio_name = result['portfolio_name'].iloc[0]
    freq = result['freq'].iloc[0]
    result = result[['port_monthly_return', 'bm_monthly_return', 'excess_monthly_return']]
    result = result.iloc[:num_trailing_month, :]
    col_dict = {
        'port_monthly_return': portfolio_name + '-' +sub_category,
        'bm_monthly_return': config.port_label_mapping[sub_category]['name'],
        'excess_monthly_return': '相对超额',
    }
    result.rename(columns=col_dict, inplace=True)
    result.dropna(axis=1, how='all', inplace=True)
    result.reset_index(inplace=True)
    result['index'] = result['year'].astype(str) + '-' + result['month'].astype(str)
    result.drop(['year', 'month'], axis=1, inplace=True)
    result.set_index('index', inplace=True)
    result.index.name = '名称'  # 为了将最终表格的首列列名（实际上是index的name）更新为“名称”
    result = result.T
    formatter = dict(zip(list(result.columns), [lambda x: "{:.2%}".format(x)] * len(result.columns)))
    new_cmap = sns.diverging_palette(**config.cmap_kwargs)
    _df_caption = "底层策略月度数据, " + portfolio_name + '-' + sub_category + ", 比较基准: " + config.port_label_mapping[sub_category]['name'] + ", 数据频率: " + freq
    d1 = dict(selector="th", props=[('text-align', 'center'), ("white-space", "nowrap"), ("word-break", "keep-all")])  # 禁用内容换行，避免行高被挤压得过大
    d2 = dict(selector='caption',
              props=[('text-align', 'center'), ('font-weight', 'bold'), ('color', 'black'), ('font-size', '125%')])
    df = result.style.format(formatter, na_rep="").set_properties(**{'width': '100', 'text-align': 'center'}) \
        .set_caption(_df_caption).set_table_styles([d1]).set_table_styles([d2], overwrite=False)
    df = df.background_gradient(cmap=new_cmap, low=config.cmap_range_adjust_coef, high=config.cmap_range_adjust_coef, axis=0, vmin=-result.abs().max().max(), vmax=result.abs().max().max())
    df = df.highlight_null('white')
    return df

# ------------------------------------------------------
# 私享账户分类型业绩展示
# ------------------------------------------------------
def visFOF_SXAccountPerfStatsSummary(
    date,
    pm_name='全部',
    account_aum=0,
    inception_before=datetime.date.today() - datetime.timedelta(days=90),
    output_type='平均数',   # '平均数', '加权平均数', '中位数'
    period='YTD',
    account_type=None,
    account_area='全部',
    start_date=None,
    include_account_type_convert=True,  # 是否纳入发生私享臻选转换的账户，默认为纳入
    include_pm_convert=True,            # 是否纳入投资经理转换的账户，默认为纳入
    convert_account_as_whole=True,      # 是否将转换账户前后绩效视为一体(对私享臻选的转换和投资经理的转换同时生效)，默认视为一体
    include_client_special_need=True,   # 是否将具有客户特殊需求的账户纳入，默认为纳入
    display_mode='web',                 # 展示模式，web代表网页展示，表格正常上色；ppt代表投委会ppt模式，表格不上色
):
    if pm_name == '全部':
        pm_name = None
    if account_area == '全部':
        account_area = None
    if period != 'Customized':
        start_date = None
    result = portAnls.anlsFOF_getSXAccountPerfStatsSummary(date=date, pm_name=pm_name, account_aum=account_aum,
                                                   inception_before=inception_before, output_type=output_type,
                                                   period=period, account_type=account_type, account_area=account_area, start_date=start_date,
                                                    include_account_type_convert=include_account_type_convert, include_pm_convert=include_pm_convert,
                                                    convert_account_as_whole=convert_account_as_whole, include_client_special_need=include_client_special_need)
    result.rename(columns={'level_3_type':'账户类型',
                           'account_num':'账户数',
                           'period_return':'区间收益率',
                           'annualized_period_return':'区间年化收益',
                           'annualized_volatility':'区间年化波动',
                           'max_drawdown':'区间最大回撤',
                           'max_period_return':'最大区间收益',
                           'min_period_return':'最小区间收益',
                           'bm_period_return':'基准区间收益',
                           'bm_annualized_period_return': '基准区间年化收益',
                           'bm_max_drawdown': '基准区间最大回撤',
                           'bm_annualized_volatility': '基准区间年化波动',
                           'excess_period_return':'区间超额收益'}, inplace=True)
    formatter = {'账户数量': '{:.0f}', '区间收益率': '{:.2%}', '区间年化收益': '{:.2%}', '区间年化波动':'{:.2%}',
                 '区间最大回撤': '{:.2%}','最大区间收益': '{:.2%}', '最小区间收益': '{:.2%}','基准区间收益':'{:.2%}','基准区间年化收益':'{:.2%}','基准区间最大回撤':'{:.2%}', '基准区间年化波动':'{:.2%}', '区间超额收益':'{:.2%}'}
    ret_subset = ['区间收益率', '区间年化收益', '最小区间收益', '最大区间收益', '基准区间收益', '基准区间年化收益', '区间超额收益']
    mdd_subset = ['区间最大回撤', '基准区间最大回撤']
    vol_subset = ['区间年化波动', '基准区间年化波动']
    new_cmap = sns.diverging_palette(**config.cmap_kwargs)
    d1 = dict(selector="th", props=[('text-align', 'center')])
    d2 = dict(selector='caption', props=[('text-align', 'center'), ('font-weight', 'bold'), ('color', 'black'), ('font-size', '125%')])
    _df_caption = ('私享账户统计, ' if account_type != config.specific_FOF_product_line['sixiang+huixiang'] else '私享和慧享账户汇总统计, ') + 'period: ' + period + ', data frequency: D' + ',method:' + output_type
    if display_mode == 'web':
        df = result.style.format(formatter, na_rep="").set_properties(**{'width': '100', 'text-align': 'center'}) \
            .background_gradient(subset=ret_subset, cmap=new_cmap,
                                 low=config.cmap_range_adjust_coef, high=config.cmap_range_adjust_coef, axis=0,
                                 vmin=-result[ret_subset].abs().max().max(), vmax=result[ret_subset].abs().max().max()) \
            .background_gradient(subset=mdd_subset, cmap=new_cmap,
                                 low=config.cmap_range_adjust_coef, high=config.cmap_range_adjust_coef, axis=0) \
            .background_gradient(subset=vol_subset, cmap=sns.diverging_palette(**config.vol_cmap_kwargs),
                                 low=config.cmap_range_adjust_coef, high=config.cmap_range_adjust_coef, axis=0) \
            .set_caption(_df_caption)\
            .set_table_styles([d1])\
            .set_table_styles([d2], overwrite=False).hide_index().highlight_null('white')
    else:
        del result['基准区间年化收益'], result['基准区间最大回撤'], result['基准区间年化波动']
        df = result.style.format(formatter, na_rep="").set_properties(**{'width': '100', 'text-align': 'center'}) \
            .set_caption(_df_caption) \
            .set_table_styles([d1]) \
            .set_table_styles([d2], overwrite=False).hide_index().highlight_null('white')
    return df

# ------------------------------------------------------
# 私享账户区间收益气泡图
# ------------------------------------------------------
def visFOF_SXAccountReturnDrawdownBubbleMap(
    date,
    xaxis,  # 横轴绘制最大回撤、当前回撤或是波动
    pm_name='全部',
    account_aum=0,
    inception_before=datetime.date.today() - datetime.timedelta(days=90),
    period='YTD',
    account_type=None,
    account_area='全部',
    start_date=None,
    include_account_type_convert=True,  # 是否纳入发生私享臻选转换的账户，默认为纳入
    include_pm_convert=True,  # 是否纳入投资经理转换的账户，默认为纳入
    convert_account_as_whole=True,  # 是否将转换账户前后绩效视为一体(对私享臻选的转换和投资经理的转换同时生效)，默认视为一体
    include_client_special_need=True,  # 是否将具有客户特殊需求的账户纳入，默认为纳入
):
    if pm_name == '全部':
        pm_name = None
    if account_area == '全部':
        account_area = None
    if period != 'Customized':
        start_date = None
    period_perf = portAnls.anlsFOF_getSXAccountReturnDrawdownBubbleMap(date=date, xaxis=xaxis, pm_name=pm_name,
                                                                       account_aum=account_aum, inception_before=inception_before, period=period,
                                                                       account_type=account_type, account_area=account_area, start_date=start_date,
                                                                       include_account_type_convert=include_account_type_convert, include_pm_convert=include_pm_convert,
                                                                       convert_account_as_whole=convert_account_as_whole, include_client_special_need=include_client_special_need)
    xaxis_mapping = {
        'stat': {
            '最大回撤': 'max_drawdown',
            '当前回撤': 'current_drawdown',
            '波动': 'annualized_volatility'
        },
        'title': {
            '最大回撤': '区间最大回撤',
            '当前回撤': '区间当前回撤',
            '波动': '区间年化波动'
        },
    }

    base = alt.Chart(period_perf).mark_circle().encode(
            x=alt.X(xaxis_mapping['stat'][xaxis], title=xaxis_mapping['title'][xaxis], scale=alt.Scale(zero=False), axis=alt.Axis(format='.2%')),
            y=alt.Y('period_return', scale=alt.Scale(zero=False, padding=1), title='区间收益率', axis=alt.Axis(format='.2%')),
            color='level_3_type',
            size='AUM',
            tooltip=[alt.Tooltip('portfolio_name'),
                     alt.Tooltip('level_3_type'),
                     alt.Tooltip('pm_name'),
                     alt.Tooltip('AUM'),
                     alt.Tooltip('period_return', format=".2%"),
                     alt.Tooltip(xaxis_mapping['stat'][xaxis], format=".2%")]
            ).interactive()

    return base

# ------------------------------------------------------
# 私享账户分类型时序收益
# ------------------------------------------------------
def visFOF_SXAccountAvgNavPlot(
    date,
    pm_name='全部',
    account_scale=0,
    inception_before=datetime.date.today(),
    output_type='平均数',   # '平均数', '加权平均数', '中位数'
    period='YTD',
    account_type=None,
    account_area='全部',
    start_date=None,
    include_account_type_convert=True,  # 是否纳入发生私享臻选转换的账户，默认为纳入
    include_pm_convert=True,  # 是否纳入投资经理转换的账户，默认为纳入
    convert_account_as_whole=True,  # 是否将转换账户前后绩效视为一体(对私享臻选的转换和投资经理的转换同时生效)，默认视为一体
    include_client_special_need=True,  # 是否将具有客户特殊需求的账户纳入，默认为纳入
):
    if pm_name == '全部':
        pm_name = None
    if account_area == '全部':
        account_area = None
    if period != 'Customized':
        start_date = None
    result = portAnls.anlsFOF_getSXAccountAvgNav(date, pm_name, account_scale, inception_before, output_type,
                                                 period, account_type, account_area, start_date=start_date,
                                                 include_account_type_convert=include_account_type_convert, include_pm_convert=include_pm_convert,
                                                 convert_account_as_whole=convert_account_as_whole, include_client_special_need=include_client_special_need)
    _result = []
    for type in result.keys():
        temp = result[type].reset_index()
        temp.loc[:, 'type'] = type
        _result.append(temp)
    _result = pd.concat(_result, axis=0)
    _result.columns = ['date', 'nav', 'type']

    _result['date'] = pd.to_datetime(_result['date'])
    base = alt.Chart(_result).mark_line().encode(
            x=alt.X('date:T', title='日期', axis=alt.Axis(format='%Y/%m/%d')),
            y=alt.Y('nav', scale=alt.Scale(domain=[_result['nav'].min()*0.99, _result['nav'].max()*1.01]), title='账户%s' % output_type),
            color='type',
            tooltip=['date', 'nav', 'type']
            )
    hover = alt.selection(type='single', on='mouseover', nearest=True, empty='none')
    point = base.mark_circle().encode(
        size=alt.condition(~hover, alt.value(15), alt.value(55))
    ).add_selection(hover)
    return (base + point).interactive()

# ----------------------------------------------------------------------------------------------------------------
# PM投资情况 红黄绿灯情况汇总
# 返回：flag_table: 红黄绿灯按账户数量、规模汇总的比重数据表格; group_table: 不同产品系列的规模、绩效、超额绩效、红绿灯统计的汇总表格
# 返回：count_weight_chart: 红黄绿灯按数量饼状图; AUM_weight_chart: 红黄绿灯按规模饼状图
# ----------------------------------------------------------------------------------------------------------------
def visFOF_pmFlagOverview(
    date,
    period,
    pm_name,                    # None表示全部投资经理
    start_date=None,            # for Customized period
):
    flag_result, group_result = portAnls.anlsFOF_pmFlagOverview(date, period, pm_name, start_date)

    # flag比重表格和饼图部分
    col_dict = {
        'YTD_flag': '表现情况',
        'portfolio_count': '数量',
        'count_weight': '数量占比',
        'AUM': '规模(亿)',
        'AUM_weight': '规模占比',
        'portfolio_type': '账户类型',
        'period_return': '今年以来平均收益率',
        'excess_period_return': '今年以来平均超额收益率',
        '红': '红灯',
        '黄': '黄灯',
        '绿': '绿灯',
    }
    flag_describes = {
        '绿': '绿灯（业绩达到投委会基准）',
        '黄': '黄灯（业绩不达基准小于2%）',
        '红': '红灯（业绩不达基准超2%）',
        '合计': '合计'
    }
    flag_result['AUM'] = flag_result['AUM'] / 1e8
    group_result['AUM'] = group_result['AUM'] / 1e8
    flag_result.rename(columns=col_dict, inplace=True)
    group_result.rename(columns=col_dict, inplace=True)
    flag_table_result = flag_result.copy(deep=True)
    flag_table_result = flag_table_result.replace(flag_describes)
    flag_table_result = flag_table_result[['表现情况', '数量', '数量占比', '规模(亿)', '规模占比']]  # 列顺序重整
    flag_result.drop(flag_result.tail(1).index, inplace=True)  # 只有表格展示合计数据
    flag_result = flag_result.replace({'绿': '绿灯', '黄': '黄灯', '红': '红灯'})
    cmap = {
        '红灯': '#ff4242',
        '黄灯': '#f7e300',
        '绿灯': '#79dc01'
    }
    count_weight_base = alt.Chart(flag_result, title="账户达标情况（数量占比）").mark_arc().encode(
        theta=alt.Theta('数量占比:Q', stack=True),
        color=alt.Color('表现情况:N', scale=alt.Scale(domain=list(cmap.keys()), range=list(cmap.values()))),
    )
    count_weight_chart = count_weight_base.mark_arc() + count_weight_base.mark_text(radius=100, size=12).encode(text=alt.Text('数量占比:Q', format='.2%'))
    AUM_weight_base = alt.Chart(flag_result, title="账户达标情况（规模占比）").mark_arc().encode(
        theta=alt.Theta('规模占比:Q', stack=True),
        color=alt.Color('表现情况:N', scale=alt.Scale(domain=list(cmap.keys()), range=list(cmap.values()))),
    )
    AUM_weight_chart = AUM_weight_base.mark_arc() + AUM_weight_base.mark_text(radius=100, size=12).encode(text=alt.Text('规模占比:Q', format='.2%'))
    d1 = dict(selector="th", props=[('text-align', 'center')])
    d2 = dict(selector='caption', props=[('text-align', 'center'), ('font-weight', 'bold'), ('color', 'black')])
    formatter = {'规模(亿)': '{:,.2f}', '数量占比': '{:.2%}', '规模占比': '{:.2%}'}
    flag_table = flag_table_result.style.format(formatter, na_rep='').set_properties(**{'text-align': 'center'}).\
                background_gradient(subset=['数量占比', '规模占比'], cmap='Reds', low=0, high=config.cmap_range_adjust_coef).\
                set_table_styles([d1]).set_table_styles([d2], overwrite=False).hide_index().highlight_null('white')

    # flag结合绩效的汇总大表
    new_cmap = sns.diverging_palette(**config.cmap_kwargs)
    new_formatter = {'规模(亿)': '{:,.2f}', '今年以来平均收益率': '{:.2%}', '今年以来平均超额收益率': '{:.2%}'}
    group_table = group_result.style.format(new_formatter, na_rep='').set_properties(**{'text-align': 'center'}).set_table_styles([d1]).set_table_styles([d2], overwrite=False)
    for col in group_result.columns.drop(['账户类型']):
        if col in ['数量', '规模(亿)']:
            group_table = group_table.background_gradient(subset=col, cmap='Reds', low=0, high=config.cmap_range_adjust_coef, axis=0)
        elif col in ['今年以来平均收益率', '今年以来平均超额收益率']:
            group_table = group_table.background_gradient(subset=col, cmap=new_cmap, low=config.cmap_range_adjust_coef, high=config.cmap_range_adjust_coef, axis=0, vmin=-group_result[col].abs().max(axis=0), vmax=group_result[col].abs().max(axis=0))
    group_table = group_table.hide_index().highlight_null('white')

    return {'flag_table': flag_table, 'group_table': group_table, 'count_weight_chart': count_weight_chart, 'AUM_weight_chart': AUM_weight_chart}

# ------------------------------------------------------------------------------
# 账户区间绩效即基准超额收益汇总，每个账户一行
# 目前用于投委会报告前三页 - 集合产品A类账户的代表账户绩效汇总
# 返回代表账户绩效、对应基准绩效、红绿灯情况
# ------------------------------------------------------------------------------
def visFOF_keyAccountPerfSummary(
    port_ids,   # 输入账户id list
    date,
    period,
    start_date=None
):
    result = portAnls.anlsFOF_keyAccountPerfSummary(port_ids, date, period, start_date)
    del result['portfolio_id']
    rename_dict = {
        'port_strategy_type': '账户策略类别',
        'portfolio_name': '账户名称',
        'level_3_type': '账户三级标签',
        'pm_name': '投资经理',
        'AUM': '规模（万元）',
        'period': '绩效区间',
        'start_date': '开始日期',
        'end_date': '截止日期',
        'period_return': '区间收益',
        'annualized_period_return': '年化收益',
        'annualized_volatility': '年化波动率',
        'max_drawdown': '最大回撤',
        'bm_period_return': '投委会基准收益',
        'excess_period_return': '超额收益',
        'YTD_flag': 'YTD红绿灯',
        'SI_flag': 'SI红绿灯',
    }
    result.rename(columns=rename_dict, inplace=True)

    formatter = {
        '规模（万元）': lambda x: "{:,.2f}".format(x),
        '区间收益': lambda x: "{:.2%}".format(x),
        '年化收益': lambda x: "{:.2%}".format(x),
        '年化波动率': lambda x: "{:.2%}".format(x) if not isinstance(x, str) else x,
        '最大回撤': lambda x: "{:.2%}".format(x) if not isinstance(x, str) else x,
        '投委会基准收益': lambda x: "{:.2%}".format(x),
        '超额收益': lambda x: "{:.2%}".format(x),
    }

    dfs = result.reset_index(drop=True).style.format(formatter, na_rep="")
    dfs = dfs.set_table_styles([{"selector": "th,tr", "props": [("white-space", "nowrap"), ("word-break", "keep-all"), ('text-align', 'center')]},
    ]).set_properties(**{'text-align': 'center'})

    def color_col(col, pattern_map, default=''):
        return np.select(
            [col.str.contains(k, na=False) for k in pattern_map.keys()],
            [f'color: {v}' for v in pattern_map.values()],
            default=default
        ).astype(str)

    for col in result.columns.drop(['账户策略类别', '账户名称', '绩效区间', '开始日期', '截止日期', '投资经理']):
        if col in ['YTD红绿灯', 'SI红绿灯']:
            dfs.apply(color_col, pattern_map={'红': 'red', '黄': 'yellow', '绿': 'green'}, subset=[col])
        elif col in ['规模（万元）']:
            dfs.bar(subset=[col], color='pink', vmin=0)
    dfs = dfs.highlight_null('white').hide_index()

    return dfs

# ---------------------------------------------------------
# 获取投资组合多头行业穿透
# 私募公募整合时仅支持申万一级分布，只看公募可以对行业分类以及报告期进行选择
# 返回：table: 行业比重表; chart: 行业饼状图
# ---------------------------------------------------------
def visFOF_FOFIndustryLookThrough(
    date,                   # 持仓数据日期，输入格式:datetime.date
    portfolio_id,
    company='SW',           # 行业分类标准，输入格式:str，'SW' or 'CITICS'
    level=1,                # 行业分类级别，输入格式:int
    top_num=10,             # 前N大行业
    mask_h_shares=True,     # 是否将港股的行业全部置为“港股”，默认为是
    report_date=None,       # 报告日期控制，默认为空，以date之前前最新报告为准；报告日期输入格式:datetime.date
):
    result = portAnls.anlsFOF_getFOFIndustryLookThrough(date, portfolio_id, company, level, top_num, mask_h_shares, report_date)
    # 行业穿透
    industry_result = result['industry']
    if industry_result.empty:
        return {'industry_table': industry_result, 'industry_chart': None, 'market_table': None, 'product_table': None}
    del industry_result['portfolio_id'], industry_result['equity_total_weight']
    rename_dict = {
        'industry': '行业',
        'industry_weight_in_port': '行业占整体组合比重',
        'industry_weight': '行业占多头比重',
        'portfolio_name': '组合名称',
        'date': '持仓数据日期',
        'NAV': '组合规模',
        'industry_NAV': '行业规模',
        'industry_level': '行业分类等级',
        'report_date': '行业分类参考报告期'
    }
    industry_level_map = {
        'company': {'SW': '申万', 'CITICS': '中信'},
        'level': {1: '一级', 2: '二级', 3: '三级'}
    }
    top_num_str = "全部行业，" if top_num == 999 else ("前" + str(top_num) + "大行业，")
    title = "行业穿透：展示" + top_num_str + "\n行业分类：" + industry_level_map['company'][company] + industry_level_map['level'][level]
    industry_result.rename(columns=rename_dict, inplace=True)
    industry_result['行业分类等级'] = industry_result['行业分类等级'].apply(lambda x: industry_level_map['company'][x.split('_')[0]] + industry_level_map['level'][int(x.split('_')[1])])
    industry_result['行业分类等级'] = industry_result.apply(lambda x: '恒生一级' if '港股' in x['行业'] else x['行业分类等级'], axis=1)
    # industry table
    industry_table_result = industry_result.copy(deep=True)
    col_list = ['组合名称', '组合规模', '持仓数据日期', '行业分类参考报告期', '行业分类等级', '行业', '行业规模', '行业占整体组合比重', '行业占多头比重']
    industry_table_result = industry_table_result[col_list]
    formatter = {
        '组合规模': '{:,.2f}',
        '行业规模': '{:,.2f}',
        '行业占整体组合比重': '{:.2%}',
        '组合多头比重': '{:.2%}',
        '行业占多头比重': '{:.2%}',
    }
    industry_table_result = industry_table_result.style.format(formatter).background_gradient(subset=['组合规模', '行业规模', '行业占整体组合比重', '行业占多头比重'], cmap='Reds', low=0, high=config.cmap_range_adjust_coef).hide_index()
    industry_table_result = industry_table_result.highlight_null('white')
    # industry chart
    industry_chart_result = _complex_pie_chart(industry_result.iloc[:-1][['行业', '行业占多头比重']], title)  # 画饼图时需删去最后一行合计数据

    # 市场穿透
    lookthrough_market_result = result['market']
    lookthrough_market_result.rename(columns={
        'portfolio_name': '组合名称',
        'NAV': '组合规模',
        'date': '持仓数据日期',
        'market': '所属市场',
        'market_NAV': '市场规模',
        'market_weight_in_port': '市场占整体组合比重',
        'market_weight': '市场占多头比重',
    }, inplace=True)
    lookthrough_market_result = lookthrough_market_result.style.format({'组合规模': '{:,.2f}', '市场规模': '{:,.2f}', '市场占整体组合比重': '{:.2%}', '市场占多头比重': '{:.2%}'}) \
        .background_gradient(subset=['市场规模', '市场占整体组合比重', '市场占多头比重'], cmap='Reds', low=0, high=config.cmap_range_adjust_coef).hide_index().highlight_null('white')

    # 参与穿透的多头产品
    lookthrough_holding_result = result['product']
    lookthrough_holding_result.rename(columns={
        'portfolio_name': '组合名称',
        'NAV': '组合规模',
        'date': '持仓数据日期',
        'product_id': '产品ID',
        'product_name': '产品名称',
        'product_NAV': '产品规模',
        'product_weight': '产品权重',
        'product_type': '产品类型',
        'allocation_type': '大类配置类型',
        'label_level_1': '一级标签',
        'label_level_2': '二级标签'
    }, inplace=True)
    lookthrough_holding_result = lookthrough_holding_result.style.format({'组合规模': '{:,.2f}', '产品规模': '{:,.2f}', '产品权重': '{:.2%}'})\
        .background_gradient(subset=['产品规模', '产品权重'], cmap='Reds', low=0, high=config.cmap_range_adjust_coef).hide_index().highlight_null('white')
    return {'industry_table': industry_table_result, 'industry_chart': industry_chart_result, 'market_table': lookthrough_market_result, 'product_table': lookthrough_holding_result}

# ------------------------------------------------------
# 获取FOF账户的历史交易的汇总统计数据
# ------------------------------------------------------
def visFOF_summarizeTradesHistoricalFlow(
    start_date,
    end_date,
    pm_name=None,
    portfolio_type=None,  # FOF产品线类型，传入None或者dict. 传入None时不加筛选取所有FOF产品信息
    summary_level=None,
    client_region=None,
):
    if pm_name == '全部':
        pm_name = None

    result = portAnls.anlsFOF_summarizeTradesHistoricalFlow(start_date, end_date, pm_name, portfolio_type, summary_level, client_region)
    rename_dict = {
        'start_date': '起始日期',
        'end_date': '截止日期',
        'product_type': '产品类型',
        'label_level_1': '一级标签',
        'label_level_2': '二级标签',
        'allocation_type': '大类配置类型',
        'product_name': '产品',
        'strategy_name': '策略',
        'company_name': '公司'
    }
    result.rename(columns=rename_dict, inplace=True)
    formatter = {column: '{:,.2f}' for column in set(list(result.columns)) - set(rename_dict.values())}
    new_cmap = sns.diverging_palette(**config.cmap_kwargs)
    table_result = result.style.format(formatter).set_properties(**{'text-align': 'center'}) \
        .background_gradient(subset=['净买入'], cmap=new_cmap, low=config.cmap_range_adjust_coef, high=config.cmap_range_adjust_coef, axis=0, vmin=-result['净买入'].abs().max(axis=0), vmax=result['净买入'].abs().max(axis=0))
    table_result = table_result.highlight_null('white').hide_index()
    return table_result

# ------------------------------------------------------
# 获取FOF账户的历史交易数据
# ------------------------------------------------------
def visFOF_getTradeHistoricalFlow(
    start_date,
    end_date,
    portfolio_ids=None,     # list, 账户A6_ID, 为None时查询全部port的结果
    trade_type=None,        # 用于对交易类型筛选
    num_limit=0,            # 用于筛选最近N条交易记录,方便在ppt等媒介进行放置展示,为0时该参数不启用(正常展示所有记录)
    product_ids=None        # list, 用于筛选持仓产品, 为None时查询全部port的结果
):
    if trade_type == '全部':
        trade_type = None
    result = portAnls.anlsFOF_getTradeHistoricalFlow(start_date, end_date, portfolio_ids, trade_type, product_ids=product_ids)
    if num_limit:
        result = result.tail(num_limit)
    del result['portfolio_id'], result['trade_market'], result['trade_confirm_date']
    rename_dict = {
        'portfolio_name': '组合名称',
        'trade_date': '交易日期',
        'product_id': '产品ID',
        'product_name': '产品名称',
        'product_type': '产品类型',
        'trade_type': '交易类型',
        'trade_price': '交易价格',
        'trade_volume': '交易量',
        'trade_amount': '交易金额',
        'pm_name': '投资经理'
    }
    result.rename(columns=rename_dict, inplace=True)
    col_list = ['组合名称', '产品ID', '产品名称', '产品类型', '交易日期', '交易类型', '交易价格', '交易量', '交易金额', '投资经理']
    table_result = result[col_list]
    formatter = {
        '交易价格': '{:,.4f}',
        '交易量': '{:,.2f}',
        '交易金额': '{:,.2f}',
    }
    def trade_type_color(val):
        color_list = []
        for v in val:
            if str(v) == '买入':
                color_list.append('color: red')
            elif str(v) == '卖出':
                color_list.append('color: green')
            else:
                color_list.append('color: black')
        return (color_list)
    table_result = table_result.style.format(formatter).background_gradient(subset=['交易金额', '交易量'], cmap='Reds', low=0, high=config.cmap_range_adjust_coef)
    table_result = table_result.apply(trade_type_color, axis=0, subset=['交易类型'])
    table_result = table_result.highlight_null('white').hide_index()

    return table_result

# ------------------------------------------------------
# 获取FOF账户的在途交易指令数据
# ------------------------------------------------------
def visFOF_getTradeFutureFlow(
    start_date,
    end_date,
    portfolio_ids=None,     # list, 账户A6_ID, 为None时查询全部port的结果
    simplified_mode=False,  # 简化输出模式，省略一些基础信息列用于轻量化展示
):
    result = custFOF.custFOF_getTradeFutureFlow(start_date, end_date, portfolio_ids)
    del result['portfolio_id']
    rename_dict = {
        'portfolio_name': '组合名称',
        'trade_entry_date': '指令录入日期',
        'trade_execute_date': '计划执行日期',
        'product_id': '产品ID',
        'product_name': '产品名称',
        'trade_type': '交易类型',
        'trade_volume': '交易份额/金额',
        'trade_channel': '交易渠道',
        'confirm_status': '受理状态',
        'pm_name': '录单人'
    }
    result.rename(columns=rename_dict, inplace=True)
    col_list = ['产品名称', '计划执行日期', '交易类型', '交易份额/金额', '受理状态', '录单人'] if simplified_mode else ['组合名称', '产品ID', '产品名称', '指令录入日期', '计划执行日期', '交易类型', '交易份额/金额', '交易渠道', '受理状态', '录单人']
    table_result = result[col_list]
    formatter = {
        '交易份额/金额': '{:,.2f}',
    }
    def trade_type_color(val):
        color_list = []
        for v in val:
            if str(v) in ['理财认购', '首次申购', '理财申购', '理财转入']:
                color_list.append('color: red')
            elif str(v) in ['全部赎回', '理财赎回', '理财转出']:
                color_list.append('color: green')
            else:
                color_list.append('color: black')
        return (color_list)
    table_result = table_result.style.format(formatter).background_gradient(subset=['交易份额/金额'], cmap='Reds', low=0, high=config.cmap_range_adjust_coef)
    table_result = table_result.apply(trade_type_color, axis=0, subset=['交易类型'])
    table_result = table_result.highlight_null('white').hide_index()

    return table_result

# -------------------------------------------------------------------------------------------
# 获取单一FOF账户未来某时间点的估算持仓情况
# 目前仅从camp获得私募的在途交易指令数据，进行拼接估算
# 在途指令的交易类型包括：理财认购、首次申购、理财申购、全部赎回、理财赎回、理财转入、理财转出，根据交易类型特征去估算未来的持仓情况
# -------------------------------------------------------------------------------------------
def visFOF_estimateFutureHoldingData(
    scheduled_date,                     # 指定的未来日期，早于该日期的在途交易都会按照已成交估算
    portfolio_ids,                      # list, 账户A6_ID
    include_initial_trade_date=False    # 是否加入首次申购日期, 默认为False
):
    result = portAnls.anlsFOF_estimateFutureHoldingData(scheduled_date, portfolio_ids, include_initial_trade_date=include_initial_trade_date)
    del result['portfolio_id'], result['portfolio_name'], result['NAV'], result['inception_date'], result['COST'], result['VAL'], result['product_type']
    # 前端数据表格标签排序优化，逻辑类比组合持仓数据
    for sector_type_col_name in ['allocation_type', 'label_level_1']:
        sector_type_col_seq = result[sector_type_col_name].sort_values(ascending=False).unique().tolist()
        if '其他' in sector_type_col_seq:
            sector_type_col_seq.remove('其他')
            sector_type_col_seq.append('其他')
        result[sector_type_col_name] = result[sector_type_col_name].astype('category').cat.set_categories(sector_type_col_seq)
    result.sort_values(by=['allocation_type', 'label_level_1', 'product_weight'], ascending=[True, True, False], inplace=True)
    result = result.reset_index(drop=True)
    rename_dict = {
        'date': '估算基准日期',
        'product_id': '产品ID',
        'product_name': '产品名称',
        'product_NAV': '产品规模',
        'product_weight': '产品权重',
        'unit_val': '估值价格',
        'product_appreciation': '估值增值',
        'allocation_type': '大类配置类型',
        'label_level_1': '一级标签',
        'trade_execute_date': '计划执行日期',
        'trade_type': '交易类型',
        'confirm_status': '受理状态',
        'initial_trade_date': '首次交易日期'
    }
    result.rename(columns=rename_dict, inplace=True)
    col_list = ['估算基准日期', '产品ID', '产品名称', '产品权重', '产品规模', '估值价格', '估值增值', '大类配置类型', '一级标签',
                '计划执行日期', '交易类型', '受理状态'] + (['首次交易日期'] if include_initial_trade_date else [])
    table_result = result[col_list]
    formatter = {
        '产品权重': '{:.2%}',
        '产品规模': '{:,.2f}',
        '估值价格': '{:.4f}',
        '估值增值': '{:,.2f}',
    }
    def trade_type_color(val):
        color_list = []
        for v in val:
            if pd.isnull(v):
                color_list.append('color: black')
            elif v > 0:
                color_list.append('color: red')
            elif v < 0:
                color_list.append('color: green')
            else:
                color_list.append('color: black')
        return (color_list)
    table_result = table_result.style.format(formatter).background_gradient(subset=['产品权重', '产品规模'], cmap='Reds', low=0, high=config.cmap_range_adjust_coef).hide_index()
    table_result = table_result.applymap(lambda x: 'color: white' if pd.isnull(x) else 'color: black')
    table_result = table_result.apply(trade_type_color, axis=0, subset=['估值增值'])

    return table_result

# -------------------------------------------------------------------------------------------
# 获取单一FOF账户未来某时间点的估算持仓并计算持仓类别汇总数据，绘制饼图
# 目前仅从camp获得私募的在途交易指令数据，进行拼接估算
# -------------------------------------------------------------------------------------------
def visFOF_estimateFutureHoldingSectorInfo(
    scheduled_date,                     # 指定的未来日期，早于该日期的在途交易都会按照已成交估算
    portfolio_ids,                      # list, 账户A6_ID
    level='product_type',               # 持仓类别汇总维度 Other options: label_level_1, label_level_2, allocation_type
):
    result = portAnls.anlsFOF_estimateFutureHoldingSectorInfo(scheduled_date, portfolio_ids, level)
    base = alt.Chart(result).mark_arc().encode(
        theta=alt.Theta('sector_weight:Q', stack=True),
        color=alt.Color(level+':N'),
    )
    pie = base.mark_arc(outerRadius=100)
    text = base.mark_text(radius=120, size=10).encode(text=alt.Text('sector_weight:Q', format='.2%'))
    table_result = result.copy(deep=True)
    rename_dict = {
        'product_type': '产品类型',
        'label_level_1': '一级标签',
        'label_level_2': '二级标签',
        'allocation_type': '大类配置类型',
        'sector_NAV': '规模',
        'sector_weight': '权重'
    }
    table_result.rename(columns=rename_dict, inplace=True)
    table_result['规模'] = table_result['规模'].round(2)
    formatter = {'规模': '{:,}', '权重': '{:.2%}'}
    table_result = table_result.style.format(formatter).background_gradient(subset=['规模', '权重'], cmap='Reds', low=0, high=config.cmap_range_adjust_coef).hide_index()
    return {'chart': pie+text, 'table': table_result}

# ----------------------------------------------------------------
# FOF组合投资的底层资产（产品或策略或公司）反查历史交易记录的汇总
# ----------------------------------------------------------------
def visFOF_getTradeHistoricalFlowSummaryByAsset(
    start_date,
    end_date,
    level_ids,      # 产品或策略或公司ids, 与level选项对应
    product_type,   # 目前支持 私募产品, 公募产品, 现金
    level,          # 资产层级 目前支持 产品 策略 公司
    pm_name=None,
    port_type=None,
    client_region=None,
    detail_mode=False,  # 展示详细交易记录
):
    if pm_name == '全部':
        pm_name = None
    result = portAnls.anlsFOF_getTradeHistoricalFlowSummaryByAsset(start_date, end_date, level_ids, product_type, level, pm_name, port_type, client_region, detail_mode)
    if result.empty:
        return result
    if detail_mode:
        rename_dict = {
            'portfolio_name': '组合名称',
            'trade_date': '交易日期',
            'product_id': '产品ID',
            'company_name': '公司名称',
            'strategy_name': '策略名称',
            'product_name': '产品名称',
            'trade_type': '交易类型',
            'trade_price': '交易价格',
            'trade_volume': '交易量',
            'trade_amount': '交易金额',
            'pm_name': '投资经理'
        }
        result.rename(columns=rename_dict, inplace=True)
        formatter = {
            '交易价格': '{:,.4f}',
            '交易量': '{:,.2f}',
            '交易金额': '{:,.2f}',
        }
        def trade_type_color(val):
            color_list = []
            for v in val:
                if str(v) == '买入':
                    color_list.append('color: red')
                elif str(v) == '卖出':
                    color_list.append('color: green')
                else:
                    color_list.append('color: black')
            return (color_list)

        table_result = result.style.format(formatter).background_gradient(subset=['交易金额', '交易量'], cmap='Reds', low=0, high=config.cmap_range_adjust_coef)
        table_result = table_result.apply(trade_type_color, axis=0, subset=['交易类型'])
        table_result = table_result.highlight_null('white').hide_index()
    else:
        rename_dict = {
            'portfolio_name': '组合名称',
            'company_name': '公司名称',
            'strategy_name': '策略名称',
            'product_name': '产品名称',
            'product_id': '产品ID',
            'pm_name': '投资经理',
            '买入': '买入金额',
            '卖出': '卖出金额',
            '净买入': '净买入金额',
        }
        result.rename(columns=rename_dict, inplace=True)
        formatter = {'买入金额': '{:,.2f}', '卖出金额': '{:,.2f}', '净买入金额': '{:,.2f}'}
        new_cmap = sns.diverging_palette(**config.cmap_kwargs)
        table_result = result.style.format(formatter).set_properties(**{'text-align': 'center'}) \
                    .background_gradient(subset=['净买入金额'], cmap=new_cmap, low=config.cmap_range_adjust_coef, high=config.cmap_range_adjust_coef, axis=0, vmin=-result['净买入金额'].abs().max(axis=0), vmax=result['净买入金额'].abs().max(axis=0)) \
                    .background_gradient(subset=['买入金额'], cmap='Reds', low=0, high=config.cmap_range_adjust_coef) \
                    .background_gradient(subset=['卖出金额'], cmap='Greens', low=0, high=config.cmap_range_adjust_coef)
        table_result = table_result.highlight_null('white').hide_index()
    return table_result

# ----------------------------------------------------------------
# FOF组合投资的底层资产（产品或策略或公司）反查在途交易记录的汇总
# ----------------------------------------------------------------
def visFOF_getTradeFutureFlowSummaryByAsset(
    start_date,
    end_date,
    level_ids,      # 产品或策略或公司ids, 与level选项对应
    product_type,   # 目前只支持 私募产品
    level,          # 资产层级 目前支持 产品 策略 公司
    pm_name=None,   # 会按照账户投资经理和交易录单人取并集去筛选
    port_type=None,
    client_region=None,
):
    if pm_name == '全部':
        pm_name = None
    result = portAnls.anlsFOF_getTradeFutureFlowSummaryByAsset(start_date, end_date, level_ids, product_type, level, pm_name, port_type, client_region)
    if result.empty:
        return result
    del result['portfolio_id'], result['company_id'], result['strategy_id']
    rename_dict = {
        'portfolio_name': '组合名称',
        'trade_entry_date': '指令录入日期',
        'trade_execute_date': '计划执行日期',
        'product_id': '产品ID',
        'product_name': '产品名称',
        'company_name': '公司',
        'strategy_name': '策略',
        'trade_type': '交易类型',
        'trade_volume': '交易份额/金额',
        'trade_channel': '交易渠道',
        'confirm_status': '受理状态',
        'pm_name': '投资经理',
        'execute_pm_name': '录单人',
    }
    result.rename(columns=rename_dict, inplace=True)
    col_list = ['组合名称', '产品ID', '产品名称'] + ([level] if level in ('公司', '策略') else []) + ['指令录入日期', '计划执行日期', '交易类型', '交易份额/金额', '交易渠道', '受理状态', '投资经理', '录单人']
    table_result = result[col_list]
    formatter = {
        '交易份额/金额': '{:,.2f}',
    }
    def trade_type_color(val):
        color_list = []
        for v in val:
            if str(v) in ['理财认购', '首次申购', '理财申购', '理财转入']:
                color_list.append('color: red')
            elif str(v) in ['全部赎回', '理财赎回', '理财转出']:
                color_list.append('color: green')
            else:
                color_list.append('color: black')
        return (color_list)
    table_result = table_result.style.format(formatter).background_gradient(subset=['交易份额/金额'], cmap='Reds', low=0, high=config.cmap_range_adjust_coef)
    table_result = table_result.apply(trade_type_color, axis=0, subset=['交易类型'])
    table_result = table_result.highlight_null('white').hide_index()
    return table_result

# ----------------------------------------------------------------
# FOF组合投委会基准的信息展示
# 能够展示全量的时序上的投委会基准成分情况
# ----------------------------------------------------------------
def visFOF_getFOFInvestCommiteeBMDetail(
    date=None,          # 数据日期(观察日期)，默认取该账户在所有区间的投委会基准情况，用于判断是否发生过变更以及进行时序分析
    portfolio_id=None,  # 默认取全量数据，指定账户请输入账户ID的list
):
    port_bm_data = portAnls.anlsFOF_getFOFInvestCommiteeBMDetail(date, portfolio_id)
    if port_bm_data.empty:
        return port_bm_data
    del port_bm_data['portfolio_oa_id'], port_bm_data['portfolio_id'], port_bm_data['bm_allocation_type_order']
    rename_dict = {
        'portfolio_name': '组合名称',
        'bm_id': '指数ID',
        'bm_name': '指数名称',
        'bm_weight': '指数权重',
        'coefficient': '固定收益率数值',
        'bm_allocation_type': '所属大类资产类型',
        'effect_from': '基准生效日期',
        'effect_to': '基准失效日期',
    }
    port_bm_data.rename(columns=rename_dict, inplace=True)
    formatter = {
        '指数权重': '{:.0%}',
        '固定收益率数值': lambda x: "{:.2%}".format(x) if x is not None else x,
    }
    table_result = port_bm_data.style.format(formatter).highlight_null('white').hide_index()

    return table_result

# ----------------------------------------------------------------
# FOF组合相对投委会基准的择时分析
# 基准成分的收益率（800 CAMO2 885008）运行mock组合，并与基准进行对比
# 对组合的模拟回测会按照交易日期，取在三个大类上的delta权重变化进行调仓，对基准的模拟是每半年度进行再平衡(回到中枢)，中枢变化时也再平衡
# 模拟组合仓位都是100%，非权益、CTA的仓位均由885008补全
# 输出：投资组合和投委会基准的mock组合的净值曲线nav_chart、各资产权重时序图weight_chart、绩效对比perf_stats
# ----------------------------------------------------------------
def visFOF_getFOFPositionTimingAnalysisResult(
    portfolio_id,       # 投资组合的ID, str
    date,
    period,
    start_date=None,
    single_asset=None,  # 是否只考虑单资产的择时效果，默认考虑账户整体，输入None；目前支持输入“EQUITY”、“CTA”选项，单独进行分析
):
    single_asset_map = {'EQUITY': '权益', 'CTA': 'CTA'}
    port_mock_result, bm_mock_result, perf_result = portAnls.anlsFOF_FOFPositionTimingAnalysis(portfolio_id, date, period, start_date, single_asset)

    # 净值曲线
    mock_excess_result = pd.merge(port_mock_result[['date', 'return', 'id']].rename(columns={'return': 'port_return'}),
                                  bm_mock_result[['date', 'return']].rename(columns={'return': 'bm_return'}), on='date')
    mock_excess_result['return'] = mock_excess_result['port_return'] - mock_excess_result['bm_return']
    mock_excess_result['nav'] = (mock_excess_result['return'] + 1).cumprod()
    del mock_excess_result['port_return'], mock_excess_result['bm_return']
    mock_excess_result.loc[mock_excess_result['date'] == mock_excess_result['date'].min(), 'nav'] = 1
    mock_excess_result['id'] = '择时效果(超额净值)'
    bm_id = '比较基准' + '(' + ((single_asset_map[single_asset] + '部分') if single_asset else '') + '模拟)'
    bm_mock_result['id'] = bm_id
    nav_result = pd.concat([port_mock_result, bm_mock_result, mock_excess_result])
    color_map = alt.Scale(domain=[list(set(nav_result['id']) - {bm_id, '择时效果(超额净值)'})[0], bm_id, '择时效果(超额净值)'], range=['#4674a4', '#f58518', '#ff2b2b'])
    nav_result["date"] = nav_result["date"].apply(pd.Timestamp)
    max_ytick = nav_result['nav'].max() * 1.01
    min_ytick = nav_result['nav'].min() * 0.99
    nearest = alt.selection_single(nearest=True, on='mouseover', empty='none')
    selection = alt.selection_multi(fields=['id'], bind='legend', name='名称')
    title_string = "【模拟数据】仓位择时分析-模拟组合净值时序图, 统计区间: " + str(period) + ", 数据频率: D"
    base = alt.Chart(nav_result[['date', 'id', 'nav']], title=title_string).mark_line().encode(
        x=alt.X('date:T', title='日期', axis=alt.Axis(format='%Y/%m/%d')),
        y=alt.Y('nav', scale=alt.Scale(domain=[min_ytick, max_ytick]), title='区间Nav'),
        color=alt.Color('id', scale=color_map),
        tooltip=['id', 'date', {'field': 'nav', 'format': ',.4f'}],
        opacity=alt.condition(selection, alt.value(1), alt.value(0.1))
    )
    point = base.mark_point().encode(
        opacity=alt.condition(nearest, alt.value(1), alt.value(0))
    ).add_selection(nearest)
    lines = base.add_selection(selection)
    nav_chart = alt.layer(lines, point).interactive().configure_axisX(labelAngle=0)

    # 各类资产权重时序图
    title_string = "【模拟数据】仓位择时分析-账户的模拟组合资产权重时序图, 统计区间: " + str(period) + ", 数据频率: D"
    port_mock_weight = port_mock_result.copy(deep=True)
    port_mock_weight[list(set(port_mock_weight.columns) & {'权益', 'CTA', '绝对收益'})] = port_mock_weight[list(set(port_mock_weight.columns) & {'权益', 'CTA', '绝对收益'})].div(port_mock_weight['nav'], axis=0)
    port_mock_melt_weight = port_mock_weight[set(port_mock_weight.columns) & {'date', '权益', 'CTA', '绝对收益'}].melt(id_vars=['date'], value_name='weight')
    port_weight_chart = alt.Chart(port_mock_melt_weight, title=title_string).mark_area().encode(
            x=alt.X('date:T', title='日期', axis=alt.Axis(format='%Y/%m/%d')),
            y=alt.Y('weight', title='sector_weight', axis=alt.Axis(format='.2%')),
            color='allocation_type',
            tooltip=['date', 'allocation_type', {'field': 'weight', 'format': '.2%', 'title': 'sector_weight'}],
    )
    # 添加客户申赎日的highlight标识
    port_highlight_trade_date = port_mock_result[port_mock_result['highlight_trade_date'] == 'SUBSCRIPTION_REDEEM']
    port_highlight_trade_date['date_label'] = '客户申赎日期'
    if len(port_highlight_trade_date):
        port_highlight_chart = alt.Chart(port_highlight_trade_date[['date', 'date_label']]).mark_point(size=120, shape='diamond', filled=True).encode(
                x='date:T',
                y=alt.value(1),  # 将y值设置为常数
                color=alt.Color('date_label:N'),
                tooltip=['date:T', 'date_label:N'],
        ).properties(
                title='客户申赎日期'  # 添加图层的标题
        )
        port_weight_chart = port_weight_chart + port_highlight_chart

    title_string = "【模拟数据】仓位择时分析-基准的模拟组合资产权重时序图, 统计区间: " + str(period) + ", 数据频率: D"
    bm_mock_weight = bm_mock_result.copy(deep=True)
    bm_mock_weight[list(set(bm_mock_weight.columns) & {'权益', 'CTA', '绝对收益'})] = bm_mock_weight[list(set(bm_mock_weight.columns) & {'权益', 'CTA', '绝对收益'})].div(bm_mock_weight['nav'], axis=0)
    bm_mock_melt_weight = bm_mock_weight[set(bm_mock_weight.columns) & {'date', '权益', 'CTA', '绝对收益'}].melt(id_vars=['date'], value_name='weight')
    bm_weight_chart = alt.Chart(bm_mock_melt_weight, title=title_string).mark_area().encode(
            x=alt.X('date:T', title='日期', axis=alt.Axis(format='%Y/%m/%d')),
            y=alt.Y('weight', title='sector_weight', axis=alt.Axis(format='.2%')),
            color='allocation_type',
            tooltip=['date', 'allocation_type', {'field': 'weight', 'format': '.2%', 'title': 'sector_weight'}],
    )
    # 添加基准再平衡日的highlight标识
    bm_highlight_trade_date = bm_mock_result[bm_mock_result['highlight_trade_date'] == 'REBALANCE']
    bm_highlight_trade_date['date_label'] = '基准再平衡日期'
    if len(bm_highlight_trade_date):
        bm_highlight_chart = alt.Chart(bm_highlight_trade_date[['date', 'date_label']]).mark_point(size=120, shape='diamond', filled=True).encode(
                x='date:T',
                y=alt.value(1),  # 将y值设置为常数
                color=alt.Color('date_label:N'),
                tooltip=['date:T', 'date_label:N'],
        ).properties(
                title='基准再平衡日期'  # 添加图层的标题
        )
        bm_weight_chart = bm_weight_chart + bm_highlight_chart

    # 绩效表格
    perf_result.rename(columns={
        'period_return': '区间收益率',
        'annualized_period_return': '年化区间收益率',
        'max_drawdown': '最大回撤',
        'sharpe_ratio': '夏普',
        'calmar': '卡玛比',
        'annualized_volatility': '年化波动率',
        'mock_name': '名称',
        'start_date': '开始日期',
        'end_date': '截止日期',
        'year_return_rank': '今年以来收益率排名',
        'period': '统计区间',
        'freq': '数据频率'
    }, inplace=True)

    perf_result[['区间收益率', '年化区间收益率', '最大回撤', '年化波动率', '夏普', '卡玛比']] = perf_result[['区间收益率', '年化区间收益率', '最大回撤', '年化波动率', '夏普', '卡玛比']].astype(float)
    perf_result = perf_result[['名称', '统计区间', '开始日期', '截止日期', '区间收益率', '年化区间收益率', '最大回撤', '年化波动率', '夏普', '卡玛比']]
    formatter = {
        '区间收益率': lambda x: "{:.2%}".format(x),
        '年化区间收益率': lambda x: "{:.2%}".format(x),
        '年化波动率': lambda x: "{:.2%}".format(x) if not isinstance(x, str) else x,
        '最大回撤': lambda x: "{:.2%}".format(x),
        '夏普': lambda x: "{:.2f}".format(x) if not isinstance(x, str) else x,
        '卡玛比': lambda x: "{:.2f}".format(x),
        '年化区间超额收益': lambda x: "{:.2%}".format(x),
        '开始日期': lambda x: x.strftime("%Y-%m-%d"),
        '截止日期': lambda x: x.strftime("%Y-%m-%d"),
        '名称': lambda x: str(x),
        '今年以来收益率排名': lambda x: "{:.2%}".format(x),
        '统计区间': lambda x: str(x)
    }
    performance_data = perf_result

    new_cmap = sns.diverging_palette(**config.cmap_kwargs)
    d1 = dict(selector="th", props=[('text-align', 'center')])
    d2 = dict(selector='caption',
              props=[('text-align', 'center'), ('font-weight', 'bold'), ('color', 'black'), ('font-size', '125%')])
    _df_caption = '仓位择时分析-模拟绩效数据, 数据频率：D'
    perf_table = performance_data.reset_index(drop=True).style.format(formatter, na_rep="") \
        .set_properties(**{'width': '100', 'text-align': 'center'}) \
        .set_caption(_df_caption).set_table_styles([d1]) \
        .set_table_styles([d2], overwrite=False).hide_index()  # hide_index,不显示第一列无用index
    for col in performance_data.columns.drop(['名称', '开始日期', '截止日期']):
        if '年化波动率' in col:
            perf_table = perf_table.background_gradient(subset=[col], cmap=sns.diverging_palette(**config.vol_cmap_kwargs), low=config.cmap_range_adjust_coef, high=config.cmap_range_adjust_coef, axis=0)
        elif '最大回撤' in col:
            perf_table = perf_table.background_gradient(subset=[col], cmap=new_cmap, low=config.cmap_range_adjust_coef, high=config.cmap_range_adjust_coef, axis=0)
        elif '统计区间' not in col:
            perf_table = perf_table.background_gradient(subset=[col], cmap=new_cmap, low=config.cmap_range_adjust_coef, high=config.cmap_range_adjust_coef, axis=0,
                                        vmin=(-performance_data[col].abs().max(axis=0)),
                                        vmax=performance_data[col].abs().max(axis=0))
    perf_table = perf_table.highlight_null('white')

    return {'nav_chart': nav_chart, 'port_weight_chart': port_weight_chart, 'bm_weight_chart': bm_weight_chart, 'perf_table': perf_table}

# -------------------------------------------------------------------------------------------
# 获取FOF账户从今日至未来某日期的T0可用资金的估算情况
# 目前利用从camp获得私募的在途交易指令数据，叠加平台前端用户输入/缓存的交易试算指令进行计算
# 输出包括T0可用金额变化的时序表，以及在途交易和录入试算指令合并后的明细表
# -------------------------------------------------------------------------------------------
def visFOF_estimateFutureT0AvailableCashSerie(
    portfolio_ids,      # list, 账户A6_ID
    scheduled_date,     # 指定的未来日期，早于该日期的在途交易和试算指令都会按照已成交估算
):
    assert scheduled_date > datetime.date.today(), "指定的未来日期应晚于今天"
    assert len(portfolio_ids) == 1, "目前估算未来持仓时限制单账户计算"

    estimate_result = portAnls.anlsFOF_estimateFutureT0AvailableCashSerie(portfolio_ids, scheduled_date)
    t0_available_details = estimate_result['t0_available_details'].copy(deep=True)
    combined_scheduled_trade = estimate_result['combined_scheduled_trade'].copy(deep=True)

    # T0时序信息
    t0_available_detail_table = t0_available_details.copy(deep=True)
    t0_available_detail_table.sort_values('trade_date', inplace=True)
    t0_available_series = t0_available_details[['portfolio_id', 'portfolio_name', 'trade_date', 'today_t0_available']].drop_duplicates()
    # T0时序信息明细情况(能够对应解释每日T0变化)
    t0_available_change_details = t0_available_details[['trade_date', 'product_id', 'product_name', 'trade_type', 'trade_volume', 'trade_amount', 'trade_channel']]
    t0_available_change_details['trade_amount'] = t0_available_change_details.apply(lambda x: -1 * x['trade_amount'] if x['trade_type'] not in ['全部赎回', '理财赎回', '理财转出', '卖出'] else x['trade_amount'], axis=1)

    t0_available_series_chart = alt.Chart(t0_available_series, title=t0_available_series['portfolio_name'].iloc[0]+ ' T0可用时序变化(预估)').mark_bar(size=20).encode(
        alt.X('trade_date', axis=alt.Axis(title='日期', format='%Y-%m-%d')),
        alt.Y('today_t0_available', axis=alt.Axis(title='T0可用金额')),
        color=alt.condition(
            alt.datum.today_t0_available > 0,
            alt.value('lightblue'),  # 正数为蓝色
            alt.value('orange')  # 负数为橙色
        ),
        tooltip=[
            alt.Tooltip('today_t0_available', title='T0可用金额', format=',.2f'),
            alt.Tooltip('trade_date', title='日期')
        ]
    )

    # T0时序变化明细图,为了让时间轴与上图对齐,目前使用fill0的方法
    t0_available_change_details['trade_amount'].fillna(0, inplace=True)
    t0_available_change_details['product_name'].fillna('', inplace=True)
    t0_available_details_chart = alt.Chart(t0_available_change_details, title=t0_available_series['portfolio_name'].iloc[0]+ ' T0可用时序变化明细(预估)').mark_bar(size=20).encode(
        alt.X('trade_date', axis=alt.Axis(title='日期', format='%Y-%m-%d')),
        alt.Y('trade_amount', axis=alt.Axis(title='T0可用金额变化')),
        color=alt.Color('product_name', legend=alt.Legend(orient='bottom', direction='horizontal', columns=8)),
        tooltip=[
            alt.Tooltip('product_name', title='产品名称'),
            alt.Tooltip('trade_amount', title='金额变化', format=',.2f'),
            alt.Tooltip('trade_date', title='日期')
        ]
    )

    rename_dict = {
        'portfolio_name': '组合名称',
        'pm_name': '投资经理/录单人',
        'trade_date': '日期',
        'today_t0_available': '当日预估T0可用',
        'scheduled_trade_type': '指令录入类型',
        'product_id': '产品ID',
        'product_name': '产品名称',
        'trade_type': '交易类型',
        'trade_volume': '交易份额',
        'trade_amount': '交易金额',
        'trade_channel': '交易渠道',
        'confirm_status': '受理状态',
    }
    t0_available_detail_table.rename(columns=rename_dict, inplace=True)
    t0_available_detail_table = t0_available_detail_table[list(rename_dict.values())]
    formatter = {
        '当日预估T0可用': lambda x: "{:,.2f}".format(x) if pd.notna(x) else x,
        '交易份额': lambda x: "{:,.2f}".format(x) if pd.notna(x) else x,
        '交易金额': lambda x: "{:,.2f}".format(x) if pd.notna(x) else x,
    }
    def trade_type_color(val):
        color_list = []
        for v in val:
            if str(v) in ['理财认购', '首次申购', '理财申购', '理财转入', '申购', '买入']:
                color_list.append('color: red')
            elif str(v) in ['全部赎回', '理财赎回', '理财转出', '卖出']:
                color_list.append('color: green')
            else:
                color_list.append('color: black')
        return (color_list)
    t0_available_detail_table = t0_available_detail_table.style.format(formatter).background_gradient(subset=['交易金额'], cmap='Reds', low=0, high=config.cmap_range_adjust_coef)
    t0_available_detail_table = t0_available_detail_table.apply(trade_type_color, axis=0, subset=['交易类型'])
    t0_available_detail_table = t0_available_detail_table.highlight_null('white').hide_index()

    return {'t0_available_series_chart': t0_available_series_chart.interactive(), 't0_available_details_chart': t0_available_details_chart.interactive(), 't0_available_detail_table': t0_available_detail_table}

# ------------------------------------------------------
# FOF账户区间超额收益-跟踪误差(超额波动率)气泡图
# 仅统计需要考核基准的信盈类和非信盈类账户，不包括臻选等定制业务
# ------------------------------------------------------
def visFOF_getFOFExcessReturnTrackingErrorBubbleMap(
    date,           # 考察日期
    pm_name='全部',  # 投资经理
    period='YTD',   # 统计区间， YTD, 2023, 2022, ...
    account_type=None,  # FOF产品线类型，传入None或者dict. 传入None时不加筛选取所有FOF产品信息
    sector_type='allocation_type',  # 投资经理持仓分布分类标准
    start_date=None,
    inception_before=datetime.date.today() - datetime.timedelta(days=90),
    tracking_error_threshold=0,  # 跟踪误差阈值
):
    if pm_name == '全部':
        pm_name = None
    if period != 'Customized':
        start_date = None
    period_perf = portAnls.anlsFOF_getFOFExcessReturnTrackingErrorBubbleMap(date=date, pm_name=pm_name, period=period, account_type=account_type, sector_type=sector_type,
                                                                                                  start_date=start_date, inception_before=inception_before, tracking_error_threshold=tracking_error_threshold)
    sector_distribution = portAnls.anlsFOF_getFOFPMSectorDistribution(date=date, sector_type=sector_type, portfolio_ids=period_perf['portfolio_id'].to_list(), include_summary_row=True)
    period_perf['AUM'] /= 1e8  # 单位转成亿
    chart_data = period_perf.copy(deep=True)
    # 画气泡图和分位线
    bubble_chart = alt.Chart(chart_data).mark_circle().encode(
        x=alt.X('annualized_volatility', title='区间跟踪误差', scale=alt.Scale(zero=False), axis=alt.Axis(format='.2%')),
        y=alt.Y('period_return', scale=alt.Scale(zero=False, padding=1), title='区间超额收益率', axis=alt.Axis(format='.2%')),
        color=alt.Color('over_threshold_flag:N', title='是否达标', scale=alt.Scale(domain=['达标', '未达标'], range=['gray', 'darkorange'])),
        shape='kpi_type',
        size=alt.Size('AUM:Q', legend=None),
        tooltip=[{'field': 'portfolio_name', 'title': '组合名称'},
                 {'field': 'level_3_type', 'title': '三级分类'},
                 {'field': 'pm_name', 'title': '投资经理'},
                 {'field': 'AUM', 'title': '组合规模', 'format': ','},
                 {'field': 'period_return', 'title': '区间超额', 'format': '.2%'},
                 {'field': 'annualized_volatility', 'title': '跟踪误差', 'format': '.2%'}]
    ).interactive()
    quantile_df = pd.DataFrame({
        '跟踪误差': ['10%分位', '25%分位', '50%分位', '75%分位', '90%分位'],
        'value': [chart_data['annualized_volatility'].quantile(q) for q in [0.1, 0.25, 0.5, 0.75, 0.9]]
    })
    quantile_lines = alt.Chart(quantile_df).mark_rule(strokeWidth=2, strokeDash=[5, 5]).encode(
        x='value',
        color=alt.Color('跟踪误差:N'),
        tooltip=[alt.Tooltip('跟踪误差'), alt.Tooltip('value', format='.2%')]
    ).interactive()
    chart_res = alt.layer(bubble_chart, quantile_lines).resolve_scale(color='independent', shape='independent')

    # 持仓分布情况，按投资经理汇总，对于多个投资经理共管产品进行拆分处理
    type_labels = [type_label for type_label in sector_distribution.columns if type_label not in ('date', 'pm_name')]
    sector_distribution = sector_distribution.rename(columns={'date': '持仓日期', 'pm_name': '投资经理'}).set_index('投资经理')
    d1 = dict(selector="th", props=[('text-align', 'center')])
    d2 = dict(selector='caption', props=[('text-align', 'center'), ('font-weight', 'bold'), ('color', 'black')])
    sector_distribution_formatter = {
        type_label: lambda x: "{:.2%}".format(x) for type_label in type_labels
    }
    sector_distribution_table_res = sector_distribution.style.format(sector_distribution_formatter, na_rep="") \
        .set_properties(**{'width': '100', 'text-align': 'center'}) \
        .set_table_styles([d1]) \
        .set_table_styles([d2], overwrite=False) \
        .background_gradient(subset=type_labels, cmap='Reds', low=0, high=config.cmap_range_adjust_coef, vmin=sector_distribution[type_labels].min().min(),
                             vmax=sector_distribution[type_labels].max().max(), axis=0).highlight_null('white').hide_index()

    # 跟踪误差超过阈值的产品汇总
    over_threshold_table_res = period_perf[period_perf['over_threshold_flag'] == '未达标'][['portfolio_name', 'level_3_type', 'start_date', 'end_date', 'period_return',
                                                                               'annualized_volatility', 'AUM', 'pm_name', 'benchmark']].copy(deep=True)
    over_threshold_table_res = over_threshold_table_res.rename(
        columns={
            'portfolio_name': '名称',
            'start_date': '开始日期',
            'end_date': '截止日期',
            'period_return': '超额收益',
            'annualized_volatility': '跟踪误差',
            'level_3_type': '三级分类',
            'AUM': '规模(亿)',
            'pm_name': '投资经理',
            'benchmark': '基准'
        }
    ).reset_index(drop=True)
    def hyperlink(x):
        ret = f"""<a target="_blank" href="/FOF组合分析/?sidebar1=True&date1=%s&sector1=%s&port1=%s">%s</a>""" % (
    date.strftime('%Y-%m-%d'), list(const.const.WEB_SECTOR_TYPE_LIST.keys())[0], x, x)
        return ret
    over_threshold_html_res = over_threshold_table_res.copy(deep=True)
    over_threshold_html_res['名称'] = over_threshold_html_res['名称'].apply(lambda x: hyperlink(x))
    default_body_style = dict(selector='', props=[('white-space', 'nowrap'), ('text-align', 'center')])
    benchmark_style = {'基准': [{'selector': '', 'props': [('white-space', 'nowrap'), ('overflow', 'hidden'), ('text-overflow', 'ellipsis'), ('text-align', 'left')]}]}
    over_threshold_formatter = {'超额收益': '{:.2%}', '跟踪误差': '{:.2%}', '规模(亿)': '{:,.2f}'}
    over_threshold_html_res = over_threshold_html_res.style.format(over_threshold_formatter, na_rep='')\
            .background_gradient(subset='超额收益', cmap=sns.diverging_palette(**config.cmap_kwargs), low=config.cmap_range_adjust_coef, high=config.cmap_range_adjust_coef,
                                 axis=0, vmin=-over_threshold_html_res['超额收益'].abs().max(axis=0), vmax=over_threshold_html_res['超额收益'].abs().max(axis=0))\
        .background_gradient(subset='跟踪误差', cmap=sns.diverging_palette(**config.vol_cmap_kwargs), low=config.cmap_range_adjust_coef, high=config.cmap_range_adjust_coef, axis=0) \
        .bar(subset='规模(亿)', color='#ffbb8b') \
        .set_table_styles([d1], overwrite=False)\
        .set_table_styles([d2], overwrite=False) \
        .set_table_styles([default_body_style], overwrite=False)\
        .set_table_styles(benchmark_style, overwrite=False).highlight_null('white')
    over_threshold_html_res = over_threshold_html_res.render(escape=False)
    over_threshold_html_res = bs(over_threshold_html_res, 'lxml').prettify()
    return {'chart': chart_res, 'sector_distribution_table': sector_distribution_table_res, 'over_threshold_html': over_threshold_html_res, 'over_threshold_table': over_threshold_table_res}

# ----------------------------------------------- 私有函数 ----------------------------------------------------------- #

# ---------------------------------------------------------
# 绘制带有引导线标签的饼状图,用行业穿透等分组较多数据场景
# 返回：plt对象
# ---------------------------------------------------------
def _complex_pie_chart(
    data,   # dataframe，项目、权重两列
    title,  # 图表标题
):
    c_data = data.set_index('行业').T
    # 绘制圆环图，并返回饼块对象
    figure = plt.figure(figsize=(6, 6))
    colors = sns.color_palette('pastel', 9)
    wedges, texts = plt.pie(c_data.iloc[0], wedgeprops={"width": 0.4}, textprops={"fontsize": 'x-small'}, colors=colors)
    # 构造annotate四数的**kwargs参数，设置引导线线型
    kw = dict(arrowprops=dict(arrowstyle="-"), zorder=0, va="center", fontsize='xx-small')
    # 遍历饼块绘制注释标签和引导线
    for i, p in enumerate(wedges):
        # 根据matolotlib,Datches,wedae对象的theta1和theta2参数计算饼块均分点的角度
        ang = (p.theta2 - p.theta1) / 2.0 + p.theta1
        # 根据角度的弧度计算 饼块均分点的坐标 (引导线的起点)
        y = np.sin(np.deg2rad(ang))
        x = np.cos(np.deg2rad(ang))
        # 根据X的值即角度所在象限确走引导线的对齐方式
        horizontalalignment = {-1: "right", 1: "left"}[int(np.sign(x))]
        # 设置引导线的连接方式
        connectionstyle = "angle,angleA=0,angleB={}".format(ang)
        kw["arrowprops"].update({"connectionstyle": connectionstyle})
        # 绘制注释标签和引导线
        plt.annotate(
            c_data.columns[i] + ' ' + c_data[c_data.columns[i]].iloc[0].__format__('.2%'),
            xy=(x, y),
            xytext=(1.35 * np.sign(x), 1.4 * y),
            horizontalalignment=horizontalalignment,
            **kw
        )
    plt.title(title, x=0.5, y=0.45, fontsize=6)
    plt.show()
    return figure

# ------------------------------------------------------
# 私享慧享账户、安享账户，按照PM维度分别统计管理账户的红黄绿灯情况汇总
# ------------------------------------------------------
def visFOF_accountFlagSummary(
    date,  # 统计日期
    account_type='sixiang_huixiang'  # 账户类型，私享慧享，安享账户
):
    assert account_type in ('sixiang_huixiang', 'anxiang'), '分类为私享慧享账户，安享账户'
    result = portAnls.anlsFOF_accountFlagSummary(date, account_type=account_type)
    rename_dict = {
        'pm_name': '投资经理',
    }
    result.rename(columns=rename_dict, inplace=True)
    formatter = {
        '账户数': lambda x: "{:.0f}".format(x),
        '红': lambda x: "{:.2%}".format(x),
        '黄': lambda x: "{:.2%}".format(x),
        '绿': lambda x: "{:.2%}".format(x),
    }
    dfs = result.reset_index(drop=True).style.format(formatter, na_rep="")
    dfs = dfs.set_properties(**{'text-align': 'center'})
    dfs = dfs.highlight_null('white').hide_index()
    # HTML格式设置控制展示表格的列宽
    css_style = """
    <style>
        table {
            width: 900px;  /* 设置表格总宽度 */
            table-layout: fixed;
        }
        th, td {
            text-align: center;
            white-space: nowrap;
            word-break: keep-all;
        }
    </style>
    """
    # 先转化为 HTML
    result = (css_style + dfs.render())
    return result
