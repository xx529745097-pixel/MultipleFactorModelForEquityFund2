# ---------------------------------------
# 监控类功能的可视化函数
# ---------------------------------------
import numpy as np
import pandas as pd
import datetime
import src.data.custHF as custHF
import src.data.custFOF as custFOF
import src.const as const
import src.config as config
import src.monitor_config as monitor_config
import src.analysis.monitorAnalysis as mntrAnal
import src.analysis.barraAnalysis as barraAnal
import src.analysis.portfolioAnalysis as portAnls
import src.data.wind as wd
import altair as alt
import matplotlib.pyplot as plt
from matplotlib import cm, ticker
import seaborn as sns
plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False

# ------------------------------------------------------------------
# 监控持仓的私募基金是否都已具有业绩跟踪，是否都已标成在库已投，是否已收到净值邮件
# 将持有但未跟踪的产品进行输出提示
# ------------------------------------------------------------------
def mntrVis_trackingHFNav(
    date,                       # 考察日期，看当期持有的私募基金是否已经有跟踪（收到净值）
    tracked_week_threshold=4,   # 判定为有业绩跟踪产品的阈值，默认三周内如有收到净值落库则判定为跟踪状态
):
    result = mntrAnal.mntrAnls_trackingHFNav(date, tracked_week_threshold)
    del result['portfolio_name'], result['pm_name']  # 暂不展示涉及的具体账户和pm
    result.sort_values(by=['back_end_flag', 'product_NAV'], ascending=[True, False], inplace=True)
    result.reset_index(drop=True, inplace=True)
    result.rename(columns={
        'date': '持仓数据日期',
        'product_id': '产品ID',
        'product_name': '产品名称',
        'product_type': '产品状态',
        'back_end_flag': '是否后端',
        'label_level_1': '一级标签',
        'label_level_2': '二级标签',
        'product_NAV': '持有总规模',
        'holding_portfolio_num': '持有账户数',
        'email_nav_flag': '是否已读入净值邮件（等待配置净值序列）',
        'primary_coverage': '主研究员',
    }, inplace=True)
    formatter = {
        '持有账户数': lambda x: int(x),
        '持有总规模': lambda x: "{:,.2f}".format(x),
    }
    d1 = dict(selector="th", props=[('text-align', 'center')])
    d2 = dict(selector='caption', props=[('text-align', 'center'), ('font-weight', 'bold'), ('color', 'black'), ('font-size', '125%')])
    caption = '有持仓但暂无业绩跟踪的私募产品情况（仅分析除臻选、投顾、共管外的持仓）  ' + str(date)
    df = result.reset_index(drop=True).style.format(formatter, na_rep="")\
        .set_properties(**{'width': '150', 'text-align': 'center'}).set_table_styles([d1]).set_table_styles([d2], overwrite=False)\
        .set_caption(caption).background_gradient(subset=['持有账户数', '持有总规模'], cmap='Reds', low=0, high=config.cmap_range_adjust_coef).highlight_null('white')

    return df

# ------------------------------------------------------------------
# 监控所有持仓私募基金触及预警线、止损线的情况，汇总展示
# ------------------------------------------------------------------
def mntrVis_unitPriceWarning(
    date,                       # 考察日期，取该日期前最新的私募净值信息
    product_ids=None,           # product_ids list, 用于指定私募, 默认为None考察全部可取到数据的私募
    tracked_week_threshold=2,   # 判定私募净值为有效数据的阈值，默认设置为2周，2周以外的数据不纳入考虑
):
    result = mntrAnal.mntrAnls_unitPriceWarning(date, product_ids, tracked_week_threshold)
    rename_dict = {
        'date': '数据日期',
        'product_id': '产品ID',
        'product_short_name': '产品名称',
        'unit_value': '单位净值',
        'warning_threshold': '预警线',
        'stop_loss_threshold': '止损线',
        'warning_threshold_near_flag': '临近预警线(预警线*1.1)',
        'warning_threshold_flag': '触达预警线',
        'stop_loss_threshold_flag': '触达止损线',
    }
    result = result[list(rename_dict.keys())]
    result.reset_index(drop=True, inplace=True)
    result.rename(columns=rename_dict, inplace=True)
    formatter = {
        '单位净值': lambda x: "{:,.4f}".format(x),
        '预警线': lambda x: "{:,.2f}".format(x),
        '止损线': lambda x: "{:,.2f}".format(x),
    }
    d1 = dict(selector="th", props=[('text-align', 'center')])
    d2 = dict(selector='caption', props=[('text-align', 'center'), ('font-weight', 'bold'), ('color', 'black'), ('font-size', '100%')])
    caption = '私募基金触及预警线、止损线的情况  ' + str(date)
    df = result.reset_index(drop=True).style.format(formatter, na_rep="")\
        .set_properties(**{'width': '120', 'text-align': 'center'}).set_table_styles([d1]).set_table_styles([d2], overwrite=False)\
        .set_caption(caption).applymap(lambda x: 'background-color: pink' if x=='是' else '', subset=['临近预警线(预警线*1.1)', '触达预警线', '触达止损线'])\
        .highlight_null('white')

    return df


# ----------------------------------------------------------------------------------
# 监控持仓的单一基金集中度情况(threshold 默认25%)、单一公司持仓集中度情况(threshold 默认35%),
# 活期存款比例情况(threshold 默认25%) 汇总展示
# ----------------------------------------------------------------------------------
def mntrVis_FOFConcentrationWarning(
    date,                           # 考察日期，取该日期的持仓信息进行计算
    holding_product_threshold=0.25,  # 单一基金持仓集中度监控阈值，默认25%
    holding_company_threshold=0.35,  # 单一公司持仓集中度监控阈值，默认35%
):
    result = mntrAnal.mntrAnls_FOFConcentrationWarning(date, holding_product_threshold, holding_company_threshold)
    rename_dict = {
        'date': '数据日期',
        'portfolio_name': '名称',
        'pm_name': '投资经理',
        'NAV': '账户规模',
        'product_name': '产品',
        'product_weight': '产品权重',
        'company_short_name': '公司',
        'company_weight': '公司权重',
    }
    result = result[list(rename_dict.keys())]
    result.reset_index(drop=True, inplace=True)
    result.rename(columns=rename_dict, inplace=True)
    formatter = {
        '账户规模': lambda x: "{:,.2f}".format(x),
        '产品权重': lambda x: "{:.2%}".format(x),
        '公司权重': lambda x: "{:.2%}".format(x),
    }
    d1 = dict(selector="th", props=[('text-align', 'center')])
    d2 = dict(selector='caption', props=[('text-align', 'center'), ('font-weight', 'bold'), ('color', 'black'), ('font-size', '100%')])
    caption = '账户持有单一基金(阈值25%)、单一公司(阈值35%)集中度预警  ' + str(date)
    df = result.reset_index(drop=True).style.format(formatter, na_rep="")\
        .set_properties(**{'width': '120', 'text-align': 'center'}).set_table_styles([d1]).set_table_styles([d2], overwrite=False)\
        .set_caption(caption).background_gradient(subset=['产品权重', '公司权重'], cmap='Reds', low=0, high=config.cmap_range_adjust_coef).highlight_null('white')

    return df


# -----------------------------------------------------------------------
# 监控所有具有业绩跟踪的私募基金最近一年的当前回撤情况，汇总展示，
# 支持日频和周频计算
# -----------------------------------------------------------------------
def mntrVis_HFCurrentDrawdownWarning(
    date,                       # 考察日期，取该日期前最新的私募净值信息
    freq='W',                   # 数据频率
    period='Recent_1Y',         # 默认考察Recent_1Y区间的当前回撤
    tracked_week_threshold=2,   # 判定私募净值为有效数据的阈值，默认设置为2周，最新日期截至2周以外的产品不纳入考虑
):
    result = []
    for label_level_1 in config.product_current_drawdown_monitor_config['label_level_1'].keys():
        perf_result = mntrAnal.mntrAnls_HFCurrentDrawdownWarning(date, label_level_1, freq, period, tracked_week_threshold)
        result.append(perf_result)
    result = pd.concat(result)

    rename_dict = {
        'product_id': '产品ID',
        'product_short_name': '产品名称',
        'label_level_1': '一级标签',
        'label_level_2': '二级标签',
        'perf_start_date': '数据起始日期',
        'perf_end_date': '数据截止日期',
        'annualized_period_return': '年化收益率',
        'max_drawdown': '最大回撤',
        'current_drawdown': '当前回撤',
    }
    result = result[list(rename_dict.keys())]
    result.reset_index(drop=True, inplace=True)
    result.rename(columns=rename_dict, inplace=True)
    formatter = {
        '年化收益率': lambda x: "{:.2%}".format(x),
        '最大回撤': lambda x: "{:.2%}".format(x),
        '当前回撤': lambda x: "{:.2%}".format(x),
    }
    new_cmap = sns.diverging_palette(**config.cmap_kwargs)
    d1 = dict(selector="th", props=[('text-align', 'center')])
    d2 = dict(selector='caption', props=[('text-align', 'center'), ('font-weight', 'bold'), ('color', 'black'), ('font-size', '100%')])
    caption = '最近一年的当前回撤预警' + ('-日频' if freq == 'D' else '-周频') + '  ' + str(date)
    df = result.reset_index(drop=True).style.format(formatter, na_rep="")\
        .set_properties(**{'width': '120', 'text-align': 'center'}).set_table_styles([d1]).set_table_styles([d2], overwrite=False)\
        .set_caption(caption).background_gradient(subset=['年化收益率', '最大回撤', '当前回撤'], cmap=new_cmap, low=config.cmap_range_adjust_coef, high=config.cmap_range_adjust_coef, axis=0).highlight_null('white')

    return df

# -----------------------------------------------------------------------
# 监控持仓私募基金收益情况,支持指定日期区间
# -----------------------------------------------------------------------
def mntrVis_HFDaliyReturn(
    hf_strategy,  # 预设策略类型 ['主观多头', '量化对冲', '套利策略', '期货策略', '债券策略', '300指增', '500指增','1000指增']
    date=datetime.datetime.today().date()-datetime.timedelta(days=7), # 结束日期
):
    assert hf_strategy in ['主观多头', '量化对冲', '套利策略', '期货策略', '债券策略', '可转债多头', '300指增', '500指增', '800指增', '1000指增及量化选股'], "目前仅支持['主观多头', '量化对冲', '套利策略', '期货策略', '债券策略', '可转债多头', '300指增', '500指增', '800指增', '1000指增及量化选股']"
    assert type(date) == datetime.date, "日期输入格式需为datetime.date"
    performance_data = mntrAnal.mntrAnls_HFDaliyReturn(hf_strategy, date=date)

    rename_map = {
        'period_return': '区间收益率',
        'level_name': '名称',
        'start_date': '开始日期',
        'end_date': '截止日期',
        'period_return_excess': '区间<span style="color: red;">超额</span>收益'
    }
    performance_data.rename(columns=rename_map, inplace=True)

    formatter = {
        '区间收益率': lambda x: "{:.2%}".format(x),
        '开始日期': lambda x: x.strftime("%Y-%m-%d"),
        '截止日期': lambda x: x.strftime("%Y-%m-%d"),
        '名称': lambda x: str(x),
        '区间<span style="color: red;">超额</span>收益': lambda x: "{:.2%}".format(x)
    }
    new_cmap = sns.diverging_palette(**config.cmap_kwargs)
    d1 = dict(selector="th", props=[('text-align', 'center')])
    d2 = dict(selector='caption', props=[('text-align', 'center'), ('font-weight', 'bold'), ('color', 'black'), ('font-size', '125%')])
    return_col = ['区间<span style="color: red;">超额</span>收益'] if '区间<span style="color: red;">超额</span>收益' in list(performance_data.columns) else ['区间收益率']
    performance_data = performance_data[['名称', '开始日期', '截止日期'] + return_col]


    _df_caption = hf_strategy + ' 持仓产品收益监控 '+ date.strftime('%Y-%m-%d')
    df = performance_data.reset_index(drop=True).style.format(formatter, na_rep="")\
        .set_properties(**{'width': '150', 'text-align': 'center'})\
        .set_caption(_df_caption)\
        .set_table_styles([d1])\
        .set_table_styles([d2], overwrite=False)
    for col in performance_data.columns.drop(['名称', '开始日期', '截止日期']):
        if col == '持有规模':
            df = df.background_gradient(subset=col, cmap='Reds', low=0, high=config.cmap_range_adjust_coef, axis=0)
        else:
            df = df.background_gradient(subset=col, cmap=new_cmap, low=config.cmap_range_adjust_coef, high=config.cmap_range_adjust_coef, axis=0,
                                        vmin=(-performance_data[col].abs().max(axis=0)),
                                        vmax=performance_data[col].abs().max(axis=0))

    df = df.highlight_null('white')

    return df

# ------------------------------------------------------------------
# 监控私享账户持有私募策略的规模是否达到策略上限的90%
# ------------------------------------------------------------------
def mntrVis_HFStrategyLimitWarning(
    date,   # 考察日期，取该日期的持仓进行分析
    include_advisory=True
):
    if include_advisory:
        assert date.weekday() == 4, "当包含投顾数据时，确认日期为周五"
    result = mntrAnal.mntrAnls_HFStrategyLimitWarning(date, include_advisory=include_advisory)
    rename_map = {
        'strategy_id': '策略ID',
        'strategy_name': '策略名称',
        'strategy_NAV': '持有规模',
        'limit': '策略容量上限',
        '90%limit': '90%*策略容量上限',
    }
    result.rename(columns=rename_map, inplace=True)
    formatter = {
        '持有规模': lambda x: "{:,.2f}".format(x),
        '策略容量上限': lambda x: "{:,.2f}".format(x),
        '90%*策略容量上限': lambda x: "{:,.2f}".format(x),
    }

    d1 = dict(selector="th", props=[('text-align', 'center')])
    d2 = dict(selector='caption', props=[('text-align', 'center'), ('font-weight', 'bold'), ('color', 'black'), ('font-size', '100%')])
    title_string= '(含投顾数据)' if include_advisory else '(不含投顾数据)'
    caption = '持有规模超过90%容量上限的策略' + title_string + '  ' + str(date)
    df = result.reset_index(drop=True).style.format(formatter, na_rep="")\
        .set_properties(**{'width': '120', 'text-align': 'center'}).set_table_styles([d1]).set_table_styles([d2], overwrite=False)\
        .set_caption(caption).background_gradient(subset=['持有规模', '策略容量上限', '90%*策略容量上限'], cmap='Reds', low=0, high=config.cmap_range_adjust_coef, axis=0).highlight_null('white')

    return df

# ------------------------------------------------------------------
# 监控账户持有私募策略的规模是否达到管理人上限的90%，周度执行
# ------------------------------------------------------------------
def mntrVis_getHFCompanyLimitWarning(
    date  # 考察日期
):
    result = mntrAnal.mntrAnls_getHFCompanyLimitWarning(date=date)[['company_id', 'company_name', 'company_aum', 'total_NAV', 'limit', 'warning_limit']]
    result.rename(columns={
        'company_id': '公司ID',
        'company_name': '公司名称',
        'company_aum': '协会AUM信息',
        'total_NAV': '持有规模',
        'limit': '公司容量上限',
        'warning_limit': '90%*公司容量上限'
    }, inplace=True)
    formatter = {
        '持有规模': lambda x: "{:,.2f}".format(x),
        '公司容量上限': lambda x: "{:,.2f}".format(x),
        '90%*公司容量上限': lambda x: "{:,.2f}".format(x),
    }
    d1 = dict(selector="th", props=[('text-align', 'center')])
    d2 = dict(selector='caption', props=[('text-align', 'center'), ('font-weight', 'bold'), ('color', 'black'), ('font-size', '100%')])
    caption = '持有规模超过90%容量上限的管理人' + '  ' + str(date)
    dfs = result.reset_index(drop=True).style.format(formatter, na_rep="")\
        .set_properties(**{'width': '120', 'text-align': 'center'}).set_table_styles([d1]).set_table_styles([d2], overwrite=False)\
        .set_caption(caption).background_gradient(subset=['持有规模', '公司容量上限', '90%*公司容量上限'], cmap='Reds', low=0, high=config.cmap_range_adjust_coef, axis=0).highlight_null('white')
    return dfs

# ------------------------------------------------------------------
# 私享账户权益持仓分布每周监控并与上周/上月对比
# 包括按照投资经理的汇总以及总体情况
# 起止日期是指需要平均计算的时间区间，目前常见的使用场景是计算近30日的平均持仓
# ------------------------------------------------------------------
def mntrVis_SXAccountEquityStrategyPropotion(
    start_date,
    end_date,
):
    result = mntrAnal.mntrAnls_SXAccountEquityStrategyPropotion(start_date, end_date)
    rename_map = {
        'equity_type': '权益类产品',
    }
    result.rename(columns=rename_map, inplace=True)
    formatter = {
        pm: lambda x: "{:.2%}".format(x) for pm in const.const.SIXIANG_PM_LIST + ['总计']
    }
    d1 = dict(selector="th", props=[('text-align', 'center')])
    d2 = dict(selector='caption', props=[('text-align', 'center'), ('font-weight', 'bold'), ('color', 'black'), ('font-size', '100%')])
    caption = '各投资经理权益持仓中  各类产品占比情况(时点值)' + ' - ' + str(end_date)
    df = result.reset_index(drop=True).style.format(formatter, na_rep="")\
        .set_properties(**{'width': '120', 'text-align': 'center'}).set_table_styles([d1]).set_table_styles([d2], overwrite=False)\
        .set_caption(caption).background_gradient(subset=const.const.SIXIANG_PM_LIST + ['总计'], cmap='Reds', low=0, high=config.cmap_range_adjust_coef, axis=0).highlight_null('white').hide_index()

    return df


# ------------------------------------------------------------------
# 私享账户权益持仓分布与上周/上月对比
# 包括按照投资经理的汇总以及总体情况
# 需输入两组起止日期是指需要平均计算的时间区间，目前常见的使用场景是计算近30日的平均持仓
# ------------------------------------------------------------------
def mntrVis_SXAccountEquityStrategyPropotionChg(
    w1_start_date,  # 上一周的数据的起始日期
    w1_end_date,
    w2_start_date,  # 新一周的数据的起始日期
    w2_end_date,
    image_caption=None,  # 图表标题
):
    result = mntrAnal.mntrAnls_SXAccountEquityStrategyPropotionChg(w1_start_date, w1_end_date, w2_start_date, w2_end_date)
    rename_map = {
        'equity_type': '权益类产品',
    }
    result.rename(columns=rename_map, inplace=True)
    formatter = {
        pm: lambda x: "{:.2%}".format(x) for pm in const.const.SIXIANG_PM_LIST + ['总计']
    }
    new_cmap = sns.diverging_palette(**config.cmap_kwargs)
    d1 = dict(selector="th", props=[('text-align', 'center')])
    d2 = dict(selector='caption', props=[('text-align', 'center'), ('font-weight', 'bold'), ('color', 'black'), ('font-size', '100%')])
    caption = (str(image_caption) + ' - ' + str(w2_end_date)) if image_caption is not None else ('数据日期 - ' + str(w2_end_date))
    df = result.reset_index(drop=True).style.format(formatter, na_rep="")\
        .set_properties(**{'width': '120', 'text-align': 'center'}).set_table_styles([d1]).set_table_styles([d2], overwrite=False)\
        .set_caption(caption).background_gradient(subset=const.const.SIXIANG_PM_LIST + ['总计'], cmap=new_cmap, low=config.cmap_range_adjust_coef, high=config.cmap_range_adjust_coef, axis=0,
                                                  vmin=-result[const.const.SIXIANG_PM_LIST + ['总计']].abs().max().max(), vmax=result[const.const.SIXIANG_PM_LIST + ['总计']].abs().max().max()).highlight_null('white').hide_index()

    return df


# ------------------------------------------------------------------
# 股指期货合约基差走势监控
# 合约选取当月(00), 次月(01), 当季(02), 展示最近10个交易日的基差变化情况
# ------------------------------------------------------------------
def mntrVis_PlotStockIndexFuturesBasisLevel(
    start_date,   # 起始日期
    end_date,     # 截止日期
    futures_id_list=['IF', 'IC', 'IM', 'IH']  # 沪深300, 中证500, 中证1000, 上证50
):
    fig, axs = plt.subplots(len(futures_id_list), 4, figsize=(25, 15), dpi=200)
    adjustment_points_res = pd.DataFrame()
    # 基差走势
    for i in range(len(futures_id_list)):
        futures_id = futures_id_list[i]
        result = mntrAnal.mntrAnls_StockIndexFuturesBasisLevel(futures_id, start_date, end_date)
        adjustment_points_res = adjustment_points_res.append(result[result['date'] == result['date'].max()].sort_values(['date', 'contract_id']).copy())
        result['date'] = result['date'].apply(lambda x: x.strftime('%Y-%m-%d'))  # 避免画图时自动填充非交易日日期
        contract_code_list = sorted(result['contract_id'].unique().tolist(), reverse=False)
        for j in range(len(contract_code_list)):
            contract_code = contract_code_list[j]
            benchmark_name = const.const.STOCK_INDEX_FUTURES_BM_MAP[futures_id]['index_name']
            contract_result = result[result['contract_id'] == contract_code].set_index('date').reindex(result['date'].unique()).sort_index()
            contract_result['dividend_adj_benchmark_close'] = contract_result['benchmark_close'] - contract_result['adjustment_points']
            dividend_adj_annualized_basis_return = contract_result[['annualized_basis_return', 'dividend_adj_annualized_basis_return']].fillna(0)  # 当数据不足时fillna，用bar占位使得坐标轴日期展示完整且上下对齐
            contract_ax = axs[i][j]
            contract_ax_twin = contract_ax.twinx()
            contract_result[['benchmark_close', 'dividend_adj_benchmark_close', 'settle_price']].rename(columns={'benchmark_close': benchmark_name, 'dividend_adj_benchmark_close': '%s(到期分红调整)' % benchmark_name, 'settle_price': contract_code}).plot(ax=contract_ax, style=['-', '--', '-'], linewidth=2)
            bc1 = contract_ax_twin.bar(dividend_adj_annualized_basis_return.index, dividend_adj_annualized_basis_return['annualized_basis_return'].values, align='edge', width=-0.4, color='gray', alpha=0.2, label='年化基差(右轴)')
            bc2 = contract_ax_twin.bar(dividend_adj_annualized_basis_return.index, dividend_adj_annualized_basis_return['dividend_adj_annualized_basis_return'].values, align='edge', width=0.4, color='darkred', alpha=0.5, label='含分红年化基差(右轴)')
            contract_ax.set_xticks(contract_result.index, labels=contract_result.index, rotation=90)  # 展示x轴全部日期
            contract_ax.set_ylim(0.95 * contract_result['benchmark_close'].min(), 1.05 * contract_result['benchmark_close'].max())
            contract_ax_twin.set_ylim(-2*dividend_adj_annualized_basis_return.abs().max().max(), 2*dividend_adj_annualized_basis_return.abs().max().max())
            contract_ax.set_title('%s合约基差走势' % (contract_code.split('.')[0]), fontsize=16)
            contract_ax.set_title("距交割日期:%d交易日" % (contract_result['ttm_tradedays'].iloc[-1]-1), loc="right", fontsize=10)
            formatter = ticker.FuncFormatter(lambda y, _: '{:.2%}'.format(y))
            contract_ax_twin.yaxis.set_major_formatter(formatter)
            contract_ax_twin.bar_label(bc1, fmt='{:,.2%}', fontsize=7)
            contract_ax_twin.bar_label(bc2, fmt='{:,.2%}', fontsize=7)
            contract_ax.legend(loc='upper left')
            contract_ax_twin.legend(loc='upper right')
            contract_ax.grid(axis='y')
    fig.tight_layout()

    # 分红点位明细
    rename_dict = {
        'contract_id': '合约代码',
        'settle_price': '合约结算价',
        'benchmark_close': '指数收盘价',
        'adj_px_diff': '分红调整价差',
        'px_diff': '原始价差',
        'adjustment_points': '剩余分红点数',
        'settled_adjustment_points': '剩余分红点数(事实)',
        'div_amount_settled_adjustment_points': '剩余分红点数(预测-有预案)',
        'non_settled_adjustment_points': '剩余分红点数(预测-无预案)',
        'delist_date': '交割日期'
    }
    d1 = dict(selector="th", props=[('text-align', 'center')])
    d2 = dict(selector='caption', props=[('text-align', 'center'), ('font-weight', 'bold'), ('color', 'black'), ('font-size', '100%')])
    caption = '股指剩余分红点数 ' + str(adjustment_points_res['date'].iloc[0])
    formatter = {
        '合约结算价': lambda x: "{:.2f}".format(x),
        '指数收盘价': lambda x: "{:.2f}".format(x),
        '分红调整价差': lambda x: "{:.2f}".format(x),
        '原始价差': lambda x: "{:.2f}".format(x),
        '剩余分红点数': lambda x: "{:.2f}".format(x),
        '剩余分红点数(事实)': lambda x: "{:.2f}".format(x),
        '剩余分红点数(预测-有预案)': lambda x: "{:.2f}".format(x),
        '剩余分红点数(预测-无预案)': lambda x: "{:.2f}".format(x)
    }
    table_result = adjustment_points_res[rename_dict.keys()].reset_index(drop=True).rename(columns=rename_dict).style.format(formatter, na_rep="")\
        .set_properties(**{'width': '100', 'text-align': 'center'}).set_table_styles([d1]).set_table_styles([d2], overwrite=False)\
        .set_caption(caption).hide_index()
    return fig, table_result

# ------------------------------------------------------------------
# 股指期货基差贡献监控
# 每交易日日终和基差走势一起展示
# ------------------------------------------------------------------
def mntrVis_StockIndexFuturesBasisContribution(
    date,            # 考察日期
    futures_id_list=['IF', 'IC', 'IM', 'IH']  # 输入类型为list, 沪深300, 中证500, 中证1000, 上证50
):
    result = mntrAnal.mntrAnls_StockIndexFuturesBasisContribution(date, futures_id_list)
    d1 = dict(selector="th", props=[('text-align', 'center')])
    d2 = dict(selector='caption', props=[('text-align', 'center'), ('font-weight', 'bold'), ('color', 'black'), ('font-size', '100%')])
    caption = '股指期货合约日度基差贡献 ' + str(date)
    new_cmap = sns.diverging_palette(**config.cmap_kwargs)
    dfs = result.style.format("{:.2%}", na_rep="")\
        .set_properties(**{'width': '120', 'text-align': 'center'}).set_table_styles([d1]).set_table_styles([d2], overwrite=False).set_caption(caption)
    dfs = dfs.background_gradient(subset=result.columns, cmap=new_cmap, low=config.cmap_range_adjust_coef, high=config.cmap_range_adjust_coef,
                                              vmin=-result.abs().max().max(), vmax=result.abs().max().max(), axis=0).highlight_null('white')
    return dfs

# ------------------------------------------------------------------
# FOF账户近1年内持仓过的公募基金的基金经理变动情况
# ------------------------------------------------------------------
def mntrVis_getMFManagerAdjustment(
    start_date,  # 起始日期
    end_date,    # 截止日期
):
    result = mntrAnal.mntrAnls_getMFManagerAdjustment(start_date, end_date)
    d1 = dict(selector="th", props=[('text-align', 'center')])
    d2 = dict(selector='caption',
              props=[('text-align', 'center'), ('font-weight', 'bold'), ('color', 'black'), ('font-size', '125%')])
    caption = ('公募基金经理变动 统计区间: %s-%s' % (start_date, end_date))
    dfs = result.style.set_properties(**{'width': '120', 'text-align': 'center'}) \
        .set_table_styles([d1]).set_table_styles([d2], overwrite=False).set_caption(caption).hide_index()
    return dfs

# ------------------------------------------------------------------
# 近20交易日股票型ETF净申赎份额规模
# ------------------------------------------------------------------
def mntrVis_getETFMarketLiquidShareNetChg(
    date,            # 考察日期
    tracked_days     # 跟踪天数
):
    result = mntrAnal.mntrAnls_getETFMarketLiquidShareNetChg(date, tracked_days)
    total_result = result['total']
    broad_based_bm_result = result['broad_based']
    other_bm_result = result['other']
    share_split_info = result['share_split_info']

    total_result['date'] = total_result['date'].apply(lambda x: x.strftime('%Y-%m-%d'))
    total_result['cum_diff'] = total_result['product_liquid_share_diff'].cumsum()
    bar_res = total_result[['date', 'product_liquid_share_diff']].copy()
    base1 = alt.Chart(bar_res, title=f"股票型ETF净申赎份额 {bar_res['date'].iloc[-1]}").encode(
        x=alt.X('date', axis=alt.Axis(title=None, grid=False, labelAngle=-90), scale=alt.Scale(padding=20))
    )
    bar = base1.mark_bar(opacity=0.3, size=20).encode(
        y=alt.Y('product_liquid_share_diff:Q', axis=alt.Axis(title='份额变动(亿份)', format='.0f', grid=True),
                scale=alt.Scale(domain=[-bar_res['product_liquid_share_diff'].abs().max() * 1.02, bar_res['product_liquid_share_diff'].abs().max() * 1.02])),
        color=alt.condition(alt.datum.product_liquid_share_diff >= 0, alt.value('darkred'), alt.value('green')),  # 根据数值正负填充颜色
        tooltip=['date', {'field': 'product_liquid_share_diff', 'format': '.2f'}]
    )
    text = bar.mark_text(
        align='center',
        baseline='middle',
        dy=0  # 偏移标签偏移量
    ).encode(text=alt.Text('product_liquid_share_diff:Q', format='.2f'))

    line_res = total_result[['date', 'cum_diff']].copy()
    line_res['type'] = '累计份额变动'
    base2 = alt.Chart(line_res).encode(
        x=alt.X('date', axis=alt.Axis(title=None, grid=False, labelAngle=-90), scale=alt.Scale(padding=20))
    )
    line = base2.mark_line().encode(
        y=alt.Y('cum_diff:Q', axis=alt.Axis(title='累计份额变动(亿份)', grid=False),
              scale=alt.Scale(domain=[line_res['cum_diff'].min() * 0.98, line_res['cum_diff'].max() * 1.02])),
        color=alt.Color('type', legend=alt.Legend(title='', orient='top-right', offset=10)),
        tooltip=['date', {'field': 'cum_diff', 'format': '.2f'}]
    )
    summary_chart = alt.layer(bar+text, line).resolve_scale(
        y='independent'
    )
    summary_chart = summary_chart.properties(width=700, height=350)

    # 展示挂钩指数口径规模变动前/后N名
    def cal_relative_bm_rank_table(
        bm_result,  # data
        equity_bm_tracked_num  # 股票ETF挂钩指数异动展示个数
    ):
        bm_result.rename(columns={
            'date': '日期',
            'benchmark_id': '指数代码',
            'benchmark_name': '指数名称',
            'product_liquid_share_diff': '份额变动(亿份)',
            'liquid_total_nav_diff': '规模变动(亿元)'
        }, inplace=True)
        top_result = bm_result.iloc[:equity_bm_tracked_num].copy()
        top_result['类型'] = ['Top %d' % i for i in range(1, equity_bm_tracked_num+1)]
        bottom_result = bm_result.iloc[-equity_bm_tracked_num:].copy()
        bottom_result['类型'] = ['Bottom %d' % i for i in range(equity_bm_tracked_num, 0, -1)]
        top_bottom_result = pd.concat([top_result, bottom_result], axis=0)
        new_cmap = sns.diverging_palette(**config.cmap_kwargs)
        d1 = dict(selector="th", props=[('text-align', 'center')])
        d2 = dict(selector='caption', props=[('text-align', 'center'), ('font-weight', 'bold'), ('color', 'black'), ('font-size', '125%')])
        formatter = {'份额变动(亿份)': lambda x: "{:,.2f}".format(x), '规模变动(亿元)': lambda x: "{:,.2f}".format(x)}
        res = top_bottom_result.style.format(formatter, na_rep="") \
            .set_properties(**{'width': '100', 'text-align': 'center'}) \
            .set_table_styles([d1]).set_table_styles([d2], overwrite=False)
        for col in ['规模变动(亿元)']:
            res = res.background_gradient(subset=[col], cmap=new_cmap, low=config.cmap_range_adjust_coef,
                                 high=config.cmap_range_adjust_coef, vmin=(-top_bottom_result[col].abs().max()),
                                 vmax=top_bottom_result[col].abs().max(), axis=0)
        return res.highlight_null('white').hide_index()
    # 对规模指数和非规模指数分别生成结果
    broad_based_bm_table = cal_relative_bm_rank_table(broad_based_bm_result, 5).set_caption("股票型ETF挂钩指数净申赎份额规模 - 宽基指数")
    other_bm_table = cal_relative_bm_rank_table(other_bm_result, 10).set_caption("股票型ETF挂钩指数净申赎份额规模 - 行业、主题等指数")
    # 份额调整事件
    if not share_split_info.empty:
        share_split_info['message'] = share_split_info.apply(lambda x: f"'{x['product_id']} {x['product_name']}'在{x['date']}发生'{x['share_split_type']}'类型份额调整，折算比例为{x['share_split_conversion_ratio']:.2%}", axis=1)
        share_split_info_msg = "【ETF份额调整】\n" + "\n".join(share_split_info['message'].to_list())
    else:
        share_split_info_msg = None
    return {'summary_chart': summary_chart, 'broad_based_table': broad_based_bm_table, 'other_table': other_bm_table, 'share_split_info': share_split_info_msg}

# ------------------------------------------------
# 私募估值表风险筛查系列监控 基于风险筛查底表
# 监控结果:
# 1. 风险筛查底表('valuation_sheet_anls_base_table')
# 2. 有风险持仓产品数量统计('risky_holding_product_stats')
# 3. 有风险持仓的产品信息('risky_holding_product_info')
# 4. 区间内缺失估值表的产品信息('valuation_sheet_missing_product_info')
# 5. 各研究员老师覆盖产品信息('researcher_product_info_dfs_dict')
# ------------------------------------------------
def mntrVis_HFValuationSheetAnls(
    current_holding_date,         # 最新持仓考察日期
    valuation_sheet_start_date,   # 估值表回看开始日期
    valuation_sheet_end_date   # 估值表回看截止日期
):
    # styler设置
    formatter = {'所占比例': '{:.2%}', 'FOF持仓该产品规模': '{:,.2f}'}
    d1 = dict(selector="th", props=[('text-align', 'center')])
    d2 = dict(selector='caption', props=[('text-align', 'center'), ('font-weight', 'bold'), ('color', 'black'), ('font-size', '100%')])
    res = {}
    # 获取底表
    anls_table = mntrAnal.mntrAnls_HFValuationSheetAnlsTable(current_holding_date, valuation_sheet_start_date, valuation_sheet_end_date)
    anls_table.rename(columns={
        'company_id': '管理人ID',
        'company_short_name': '管理人名称',
        'company_total_holding_NAV': 'FOF对该管理人持仓总规模',
        'strategy_name': '策略名称',
        'product_id': '产品ID',
        'product_short_name': '产品名称',
        'product_total_holding_NAV': 'FOF持仓该产品规模',
        'trustee': '产品托管机构',
        'is_citics_trustee': '产品是否为中信托管',
        'is_citics_customized': '产品是否为中信定制',
        'interval_start_date': '区间开始日期',
        'interval_end_date': '区间截止日期',
        'interval_latest_record': '估值表区间最新日期',
        'level2_valuation': '产品是否有二级估值表',
        'level4_valuation': '产品是否有四级估值表',
        'primary_coverage': '负责研究员',
        'product_valuation_NAV': '产品估值表净值',
        'product_valuation_NAV_threshold': '估值表净值小于1000万',
        'product_contemporary_holding_NAV': '估值表日期FOF持仓规模',
        'product_contemporary_holding_ratio': '估值表日期FOF持仓占产品总规模的比例',
        'hist_latest_record': '估值表历史最新日期'
    }, inplace=True)
    # -------------------------
    # 1. 私募产品估值表风险筛查底表
    # -------------------------
    res_valuation_sheet_anls_base_table = anls_table.copy()
    format_cols = ['FOF对该管理人持仓总规模', 'FOF持仓该产品规模', '产品估值表净值', '估值表日期FOF持仓规模']
    risk_subject_NAV_cols = [subject_dict['col_name']+'_NAV' for subject_dict in config.valuation_sheet_risk_scan_subject_monitor_config.values()]
    risk_subject_weight_cols = [subject_dict['col_name'] + '_权重' for subject_dict in config.valuation_sheet_risk_scan_subject_monitor_config.values()]
    for col in format_cols+risk_subject_NAV_cols:
        res_valuation_sheet_anls_base_table[col] = res_valuation_sheet_anls_base_table[col].apply(lambda x: "" if pd.isna(x) else "{:,.2f}".format(x))
    for col in risk_subject_weight_cols:
        res_valuation_sheet_anls_base_table[col] = res_valuation_sheet_anls_base_table[col].apply(lambda x: "" if pd.isna(x) else "{:.2%}".format(x))
    res_valuation_sheet_anls_base_table['估值表日期FOF持仓占产品总规模的比例'] = res_valuation_sheet_anls_base_table['估值表日期FOF持仓占产品总规模的比例'].apply(lambda x: "" if pd.isna(x) else "{:.2%}".format(x))
    res['valuation_sheet_anls_base_table'] = res_valuation_sheet_anls_base_table

    # ------------------------
    # 2. 产品估值表风险持仓统计
    # ------------------------
    res_risky_holding_product_stats = anls_table.copy()
    res_risky_holding_product_stats = res_risky_holding_product_stats.agg({'产品ID': 'count',
                                             '产品是否有二级估值表': 'count',
                                             '产品是否有四级估值表': 'count',
                                             '产品是否为中信托管': 'count',
                                             '场外衍生品': 'count',
                                             '其他资管产品': 'count',
                                             '债券': 'count',
                                             '新三板': 'count',
                                             '北交所': 'count'
                                             }).rename('数量').to_frame()
    res_risky_holding_product_stats.rename(index={'产品ID': '已投产品',
                                     '产品是否有二级估值表': '收到二级估值表',
                                     '产品是否有四级估值表': '收到四级估值表',
                                     '产品是否为中信托管': '产品为中信托管',
                                     '场外衍生品': '产品投资场外衍生品',
                                     '其他资管产品': '产品有嵌套',
                                     '债券': '产品投资债券',
                                     '新三板': '产品投资新三板',
                                     '北交所': '产品投资北交所'
                                     }, inplace=True)
    res_risky_holding_product_stats['所占比例'] = (res_risky_holding_product_stats['数量'] / res_risky_holding_product_stats.loc['已投产品', '数量'])
    caption_risky_holding_product_stats = '{} 产品估值表风险持仓统计 区间: {}-{}'.format(current_holding_date, valuation_sheet_start_date, valuation_sheet_end_date)
    res_risky_holding_product_stats_dfs = res_risky_holding_product_stats.reset_index().rename(columns={'index': ''}).style.format(formatter, na_rep="").set_properties(**{'width': '120', 'text-align': 'center'}) \
        .set_table_styles([d1]).set_table_styles([d2], overwrite=False).set_caption(caption_risky_holding_product_stats).hide_index()
    res['risky_holding_product_stats'] = res_risky_holding_product_stats_dfs

    # ------------------------
    # 3. 产品估值表风险持仓信息
    # ------------------------
    res_risky_holding_product_info = anls_table.copy()
    risk_cols = [subject_dict['col_name'] for subject_dict in config.valuation_sheet_risk_scan_subject_monitor_config.values()]  # 筛选有风险持仓的产品
    # FIXME 对于风险持仓科目暂手动设置阈值0.1%，仅保留持仓比例在阈值以上的产品
    res_risky_holding_product_info['风险持仓科目'] = res_risky_holding_product_info.apply(lambda x: ';'.join([col + '(' + '{:.2%}'.format(x[col+'_权重']) + ')' for col in risk_cols if x[col+'_权重'] >= 1e-3]), axis=1)  # 仅展示权重超过阈值的风险持仓产品
    res_risky_holding_product_info = res_risky_holding_product_info[res_risky_holding_product_info['风险持仓科目'] != ''][['产品ID', '产品名称', 'FOF持仓该产品规模', '估值表区间最新日期', '产品是否有四级估值表', '风险持仓科目', '负责研究员']]
    caption_risky_holding_product_info = "{} 产品估值表风险持仓信息(仅保留0.1%以上持仓) 区间: {}-{}".format(current_holding_date, valuation_sheet_start_date, valuation_sheet_end_date)
    res_risky_holding_product_info_dfs = res_risky_holding_product_info.sort_values('负责研究员').reset_index(drop=True).style.format(formatter, na_rep="").set_properties(**{'width': '120', 'text-align': 'center'})\
        .set_table_styles([d1]).set_table_styles([d2], overwrite=False).set_caption(caption_risky_holding_product_info).highlight_null('yellow', subset=['产品是否有四级估值表'])
    res['risky_holding_product_info'] = res_risky_holding_product_info_dfs

    # --------------------------------------------------------------------
    # 4. 产品估值表未读入清单(反馈给IT定期梳理邮件发送情况维护邮件配置和读入代码)
    # --------------------------------------------------------------------
    res_valuation_sheet_missing_product_info = anls_table.copy()[['产品ID', '产品名称', '估值表区间最新日期', '估值表历史最新日期', '产品托管机构']]
    caption_valuation_sheet_missing_product_info = "{} 产品估值表未读入清单 区间: {}-{}".format(current_holding_date, valuation_sheet_start_date, valuation_sheet_end_date)
    res_valuation_sheet_missing_product_info_dfs = res_valuation_sheet_missing_product_info[res_valuation_sheet_missing_product_info['估值表区间最新日期'].isna()].reset_index(drop=True).style.set_properties(**{'width': '120', 'text-align': 'center'})\
        .set_table_styles([d1]).set_table_styles([d2], overwrite=False).set_caption(caption_valuation_sheet_missing_product_info)
    res['valuation_sheet_missing_product_info'] = res_valuation_sheet_missing_product_info_dfs

    # ---------------------------------------------------------------
    # 5. 区间内各研究员覆盖产品估值表信息(用于检查漏发或发送间隔过长的情况)
    # ---------------------------------------------------------------
    res_valuation_sheet_anls_product_info = anls_table.copy()[['产品ID', '产品名称', 'FOF持仓该产品规模', '估值表区间最新日期', '估值表历史最新日期', '负责研究员']]
    caption_valuation_sheet_anls_product_info = "{} 产品估值表信息 区间: {}-{}".format(current_holding_date, valuation_sheet_start_date, valuation_sheet_end_date)
    res_researcher_product_info_dfs_dict = {}
    for researcher in res_valuation_sheet_anls_product_info['负责研究员'].dropna().unique().tolist():  # dropna 忽略研究员为空的情况
        researcher_product_info_dfs = res_valuation_sheet_anls_product_info[res_valuation_sheet_anls_product_info['负责研究员'] == researcher].sort_values('估值表区间最新日期', na_position='first').reset_index(drop=True)\
            .style.format(formatter, na_rep="").set_properties(**{'width': '120', 'text-align': 'center'}).set_table_styles([d1]).set_table_styles([d2], overwrite=False)\
            .highlight_null('yellow', subset=['估值表区间最新日期']).set_caption(caption_valuation_sheet_anls_product_info)
        res_researcher_product_info_dfs_dict[researcher] = researcher_product_info_dfs
    res['researcher_product_info_dfs_dict'] = res_researcher_product_info_dfs_dict
    return res

# -------------------------------
# 公募核心库收益监控
# -------------------------------
def mntrVis_MFCorePoolDailyPerf(
    date,   # 考察日期
):
    holding_product_perf_table_res, equity_product_sim_ret = mntrAnal.mntrAnls_MFCorePoolMockPortRecommendProductPerf(date)
    mock_port_perf_table_res = mntrAnal.mntrAnls_MFCorePoolMockPortPerf(date)
    report_message = f"【{date}公募核心库监控】" + \
                     f"\n权益方面，核心中核心{mock_port_perf_table_res['权益核心库'][mock_port_perf_table_res['权益核心库']['portfolio_name'] == '核心中核心']['1D'].iloc[0]:.2%}，" + \
                     f"偏股混合型基金指数{mock_port_perf_table_res['权益核心库'][mock_port_perf_table_res['权益核心库']['portfolio_name'] == '偏股混合型基金指数']['1D'].iloc[0]:.2%}。" + \
                     f"今年以来，核心中核心{mock_port_perf_table_res['权益核心库'][mock_port_perf_table_res['权益核心库']['portfolio_name'] == '核心中核心']['YTD'].iloc[0]:.2%}，" + \
                     f"偏股混合型基金指数{mock_port_perf_table_res['权益核心库'][mock_port_perf_table_res['权益核心库']['portfolio_name'] == '偏股混合型基金指数']['YTD'].iloc[0]:.2%}。" + \
                     "\n品种方面，{}".format('，'.join([str(industry)+f"{mock_port_perf_table_res['权益核心库'][mock_port_perf_table_res['权益核心库']['portfolio_name'] == industry]['1D'].iloc[0]:.2%}"
                                                     for industry in mock_port_perf_table_res['权益核心库'][mock_port_perf_table_res['权益核心库']['portfolio_name'].isin(monitor_config.mf_core_pool_config['权益核心库']['mock_port_id_map']['行业主题基金'].keys())]\
                                                    .sort_values('1D', ascending=False)['portfolio_name'].to_list()])) + \
                     "。\n-近一日涨幅靠前的产品有：\n{}".format('，\n'.join([row['product_name'] + '-' + row['pm_name'] + "，" + f"{row['1D']:.2%}"
                                             for i, row in holding_product_perf_table_res['权益核心库']['行业主题基金'].dropna().sort_values('1D', ascending=False).iloc[:4].iterrows()])) + \
                     "。\n-近一日涨幅靠后的产品有：\n{}".format('，\n'.join([row['product_name'] + '-' + row['pm_name'] + "，" + f"{row['1D']:.2%}"
                                             for i, row in holding_product_perf_table_res['权益核心库']['行业主题基金'].dropna().sort_values('1D', ascending=True).iloc[:4].iterrows()])) + \
                     "。\n-净值模拟方面，异动大于1%的产品有：\n" + \
                     "{}".format('，\n'.join([row['product_name'] + '-' + row['pm_name'] + "，" + f"{row['ret_diff']:.2%}"
                                             for i, row in equity_product_sim_ret[equity_product_sim_ret['ret_diff'].abs() >= 0.01].iterrows()])) + \
                     f"\n\n债券方面，纯债核心库{mock_port_perf_table_res['债券核心库'][mock_port_perf_table_res['债券核心库']['portfolio_name'] == '纯债基金推荐组合']['1D'].iloc[0]:.2%}，" + \
                     f"中长期纯债基金指数{mock_port_perf_table_res['债券核心库'][mock_port_perf_table_res['债券核心库']['portfolio_name'] == '中长期纯债基金指数']['1D'].iloc[0]:.2%}，" + \
                     "\n-纯债品种中，{}，涨幅领先。".format('，\n'.join([row['product_name'] + '-' + row['pm_name'] + "，" + f"{row['1D']:.2%}"
                                             for i, row in holding_product_perf_table_res['债券核心库']['纯债基金'].dropna().sort_values('1D', ascending=False).iloc[:1].iterrows()])) + \
                     "{}，涨幅靠后。".format('，\n'.join([row['product_name'] + '-' + row['pm_name'] + "，" + f"{row['1D']:.2%}"
                                             for i, row in holding_product_perf_table_res['债券核心库']['纯债基金'].dropna().sort_values('1D', ascending=False).iloc[-1:].iterrows()])) + \
                     "\n-固收+品种中，{}，涨幅领先。".format('，\n'.join([row['product_name'] + '-' + row['pm_name'] + "，" + f"{row['1D']:.2%}"
                                     for i, row in holding_product_perf_table_res['债券核心库']['固收+基金'].dropna().sort_values('1D',ascending=False).iloc[:1].iterrows()])) + \
                     "{}，涨幅靠后。".format('，\n'.join([row['product_name'] + '-' + row['pm_name'] + "，" + f"{row['1D']:.2%}"
                                            for i, row in holding_product_perf_table_res['债券核心库']['固收+基金'].dropna().sort_values('1D', ascending=False).iloc[-1:].iterrows()]))

    info_rename_dict = {'product_id': '产品ID', 'product_name': '产品名称', 'pm_name': '基金经理', 'type_level_2': '基金类型',
                        'portfolio_id': 'ID', 'portfolio_name': '名称', 'product_daily_ret': '1D', 'product_sim_daily_ret': 'Sim_1D', 'ret_diff': 'Diff'}
    # 全量收益列名，用于下方上色
    ret_cols = [col for col in monitor_config.mf_core_pool_ret_rank_perf_stats.keys() if 'rank' not in col]
    # styler格式
    new_cmap = sns.diverging_palette(**config.cmap_kwargs)
    d1 = dict(selector="th", props=[('text-align', 'center')])
    d2 = dict(selector='caption',
              props=[('text-align', 'center'), ('font-weight', 'bold'), ('color', 'black'), ('font-size', '125%')])
    formatter = {}
    for col in list(monitor_config.mf_core_pool_ret_rank_perf_stats.keys()) + ['Sim_1D', 'Diff']:
        formatter[col] = lambda x: "{:.2%}".format(x)
    # 产品维度结果
    holding_product_perf_styler_res = {}
    for core_pool in holding_product_perf_table_res.keys():
        holding_product_perf_styler_res[core_pool] = {}
        for type_level_1 in holding_product_perf_table_res[core_pool].keys():
            type_level_1_perf_table_res = holding_product_perf_table_res[core_pool][type_level_1].copy().reset_index(drop=True)
            type_level_1_perf_table_res.rename(columns=info_rename_dict, inplace=True)
            caption = f"{date} 公募{core_pool}产品收益监控 - {type_level_1}"
            type_level_1_perf_styler_res = type_level_1_perf_table_res.style.format(formatter, na_rep="无数据")\
                .set_properties(**{'min-width': '80', 'text-align': 'center'})\
                .set_table_styles([d1]).set_table_styles([d2], overwrite=False).set_caption(caption)
            for col in ret_cols:
                type_level_1_perf_styler_res = type_level_1_perf_styler_res.background_gradient(subset=[col], cmap=new_cmap, low=config.cmap_range_adjust_coef, high=config.cmap_range_adjust_coef,
                                                                                                vmin=(-type_level_1_perf_table_res[col].abs().max()), vmax=type_level_1_perf_table_res[col].abs().max(), axis=0)
            holding_product_perf_styler_res[core_pool][type_level_1] = type_level_1_perf_styler_res.highlight_null('white').hide_index()
    # 汇总维度结果
    mock_port_perf_styler_res = {}
    for core_pool in mock_port_perf_table_res.keys():
        core_pool_mock_port_perf_table_res = mock_port_perf_table_res[core_pool].copy().reset_index(drop=True)
        core_pool_mock_port_perf_table_res.rename(columns=info_rename_dict, inplace=True)
        caption = f"{date} 公募{core_pool}模拟组合收益统计"
        core_pool_mock_port_perf_styler_res = core_pool_mock_port_perf_table_res.style.format(formatter, na_rep="无数据") \
            .set_properties(**{'min-width': '80', 'text-align': 'center'}) \
            .set_table_styles([d1]).set_table_styles([d2], overwrite=False).set_caption(caption)
        mock_port_perf_styler_res[core_pool] = core_pool_mock_port_perf_styler_res.highlight_null('white').hide_index()
    # 收益模拟结果
    equity_product_sim_ret.rename(columns=info_rename_dict, inplace=True)
    caption = f"{date} 公募权益核心库基金收益模拟"
    equity_product_sim_ret_styler_res = equity_product_sim_ret.style.format(formatter, na_rep="无数据") \
        .set_properties(**{'min-width': '80', 'text-align': 'center'}) \
        .set_table_styles([d1]).set_table_styles([d2], overwrite=False).set_caption(caption)
    for col in ['1D', 'Sim_1D', 'Diff']:
        equity_product_sim_ret_styler_res = equity_product_sim_ret_styler_res.background_gradient(subset=[col], cmap=new_cmap, low=config.cmap_range_adjust_coef, high=config.cmap_range_adjust_coef,
                                                                                                      vmin=(-equity_product_sim_ret[col].abs().max()), vmax=equity_product_sim_ret[col].abs().max(), axis=0).highlight_null('white').hide_index()
    return {'holding_product_perf': holding_product_perf_styler_res, 'mock_portfolio_perf': mock_port_perf_styler_res, 'equity_product_sim_ret': equity_product_sim_ret_styler_res, 'message': report_message}
# -----------------------------------------
# 公募基金公司高管变动监控
# -----------------------------------------
def mntrVis_getMFCompanyExecutivesAdjustment(
    start_date,  # 起始日期
    end_date     # 截止日期
):
    exec_adj_info = mntrAnal.mntrAnls_getMFCompanyExecutivesAdjustment(start_date, end_date)
    exec_adj_info.rename(columns={
        'company_name': '基金公司',
        'exec_name': '姓名',
        'exec_position': '职位',
        'exec_start_date': '任职日期',
        'exec_end_date': '离职日期',
        'adjust_type': '变动类型'
    }, inplace=True)
    d1 = dict(selector="th", props=[('text-align', 'left')])
    d2 = dict(selector='caption', props=[('text-align', 'center'), ('font-weight', 'bold'), ('color', 'black'), ('font-size', '125%')])
    caption = ('基金公司高管变动 统计区间: %s-%s' % (start_date, end_date))
    res = exec_adj_info.style.set_properties(**{'min-width': '80', 'text-align': 'left'}) \
        .set_table_styles([d1]).set_table_styles([d2], overwrite=False).set_caption(caption).hide_index()
    return res
