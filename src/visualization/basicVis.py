import numpy as np
import pandas as pd
import datetime
import altair as alt
import src.data.custHF as custHF
import src.data.custFOF as custFOF
import src.data.custMF as custMF
import src.data.wind as wd
import src.data.wind_cached as wind_cached
import src.analysis.basicAnalysis as basicAnal
import src.analysis.portfolioAnalysis as anlsFOF
import src.utils.fof_calendar as calendar
import src.const as const
import src.config as config
import matplotlib.pyplot as plt
import seaborn as sns
import itertools


plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False



# ------------------------------------------------------
# visualize关于风险收益指标的表格
# ------------------------------------------------------
def basicVis_PerformanceStats(
    ids,  # list, id, e.g. ['S0000045', 'S0000053'] or ['000711.OF']
    period,  # 统计区间
    freq,  # 数据频率，D或者W
    fund_type,  # 公募还是私募 "MF" or "HF"
    benchmark_id=None,  # 基准，e.g. 000905.SH
    date=datetime.datetime.today().date(),
    data_level='Strategy',
    start_date=None,        # This parameter ONLY works for period equal to Customized
    strategy_category=None,  # e.g. '500指增'，该参数用来和zyyx的数据对比，计算ranking
    stats=const.const.COMMON_PERF_STATS,  # 函数所需计算的stats list, 默认stats为'period_return', 'annualized_period_return', 'annualized_volatility', 'max_drawdown', 'sharpe_ratio', 'calmar'
    include_holding_amount=False,         # 是否merge上持有规模的信息
    latest_data_filter=False,             # 是否进一步筛选出具有最新数据的策略/产品，默认为否；具有最新数据定义为：距离所选date15个自然日内有数据
):
    assert isinstance(ids, list), "ids需为list"
    assert type(date) == datetime.date, '日期输入格式需为datetime.date'
    assert freq in ("D", "W"), "freq需为D或者W"
    assert fund_type in ("MF", "HF"), "fund_type需为MF或者HF"
    assert data_level in ("Strategy", "Product"), "私募数据只支持策略和产品层面"
    if fund_type == 'MF':
        assert freq == 'D', '公募请使用D'

    start_date, end_date = calendar.calender_getStartEndDate(period, date, start_date)
    performance_data = basicAnal.basicAnal_calPerformanceStats(ids, start_date, end_date, freq, fund_type, benchmark_id, data_level, strategy_category, stats, include_holding_amount, latest_data_filter)
    if fund_type == 'MF':
        mf_product_info = wd.wind_getCurrentProductList()
        id_to_name = mf_product_info.set_index('product_id')['product_name']
    else:
        if data_level == 'Strategy':
            level_info = custHF.custHF_getStrategyInfo()
            id_to_name = level_info.set_index('strategy_id')['strategy_name'].to_dict()
        else:
            level_info = custHF.custHF_getProductInfo()
            id_to_name = level_info.set_index('product_id')['product_short_name'].to_dict()
    performance_data['level_name'] = performance_data['id'].apply(lambda x: id_to_name[x])
    performance_data.sort_values(by='period_return', ascending=False, inplace=True)
    rename_map = {
        'period_return': '区间收益率',
        'annualized_period_return': '年化区间收益率',
        'max_drawdown': '最大回撤',
        'sharpe_ratio': '夏普',
        'calmar': '卡玛比',
        'annualized_volatility': '年化波动率',
        'level_name': '名称',
        'start_date': '开始日期',
        'end_date': '截止日期',
        'period_return_rank': '收益率排名',
        'current_drawdown': '当前回撤',
        'holding_NAV': '持有规模'
    }
    performance_data.rename(columns=rename_map, inplace=True)

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
        '收益率排名': lambda x: "{:.2%}".format(x),
        '当前回撤': lambda x: "{:.2%}".format(x),
        '持有规模': lambda x: "{:,.2f}".format(x),
    }
    new_cmap = sns.diverging_palette(**config.cmap_kwargs)
    d1 = dict(selector="th", props=[('text-align', 'center')])
    d2 = dict(selector='caption', props=[('text-align', 'center'), ('font-weight', 'bold'), ('color', 'black'), ('font-size', '125%')])
    perf_col = [rename_map[stat] for stat in stats]
    strategy_category_col = ['收益率排名'] if strategy_category else []
    holding_amount_col = ['持有规模'] if include_holding_amount else []
    if period != 'Today':
        performance_data = performance_data[['名称', '开始日期', '截止日期'] + perf_col + strategy_category_col + holding_amount_col]
    else:
        performance_data = performance_data[['名称', '开始日期', '截止日期', '区间收益率'] + strategy_category_col + holding_amount_col]

    if benchmark_id:
        _df_caption = 'Performance Stats, ' + 'period: ' + period + ', data frequency: ' + freq + ', benchmark: ' + benchmark_id
    else:
        _df_caption = 'Performance Stats, ' + 'period: ' + period + ', data frequency: ' + freq
    df = performance_data.reset_index(drop=True).style.format(formatter, na_rep="")\
        .set_properties(**{'width': '100', 'text-align': 'center'})\
        .set_caption(_df_caption)\
        .set_table_styles([d1])\
        .set_table_styles([d2], overwrite=False)
    for col in performance_data.columns.drop(['名称', '开始日期', '截止日期']):
        if col == '年化波动率':
            df = df.background_gradient(subset=col, cmap=sns.diverging_palette(**config.vol_cmap_kwargs), low=config.cmap_range_adjust_coef, high=config.cmap_range_adjust_coef, axis=0)
        elif col in ['最大回撤', '收益率排名', '当前回撤']:
            df = df.background_gradient(subset=col, cmap=new_cmap, low=config.cmap_range_adjust_coef, high=config.cmap_range_adjust_coef, axis=0)
        elif col == '持有规模':
            df = df.background_gradient(subset=col, cmap='Reds', low=0, high=config.cmap_range_adjust_coef, axis=0)
        else:
            df = df.background_gradient(subset=col, cmap=new_cmap, low=config.cmap_range_adjust_coef, high=config.cmap_range_adjust_coef, axis=0,
                                        vmin=(-performance_data[col].abs().max(axis=0)),
                                        vmax=performance_data[col].abs().max(axis=0))
    df = df.highlight_null('white')
    return df

# ------------------------------------------------------
# 获取单一FOF账户的区间底层私募表现，可展示实际持有的首尾时间确定绩效计算区间
# ------------------------------------------------------
def basicVis_FOFHoldingPerformanceStats(
    portfolio_id,  # FOF组合代码
    period,  # 统计区间
    end_date,  # 统计截止日期
    freq,  # 数据频率，D或者W
    start_date=None,  # 统计开始日期
    fund_type='HF',  # 基金类型，仅支持'HF'或'MF'
    stats=const.const.COMMON_PERF_STATS,  # 函数所需计算的stats list, 默认stats为'period_return', 'annualized_period_return', 'annualized_volatility', 'max_drawdown', 'sharpe_ratio', 'calmar'
    include_holding_amount=False, # 是否merge上持有规模的信息
    include_history_holding=False,
    on_exact_holding_period=False  # 是否按实际持有的首尾时间展示
):
    assert freq in ("D", "W"), "freq需为D或者W"
    performance_data = anlsFOF.anlsFOF_getSingleFOFHoldingPerformanceStats(portfolio_id, period, end_date, freq, start_date=start_date, fund_type=fund_type, include_holding_amount=include_holding_amount,
                                                                             include_history_holding=include_history_holding, on_exact_holding_period=on_exact_holding_period)
    if fund_type == 'HF':
        level_info = custHF.custHF_getProductInfo()[['product_id', 'product_short_name']].rename(columns={'product_short_name': 'product_name'})
    else:  # MF
        level_info = wd.wind_getCurrentProductList(product_ids=performance_data['id'].unique().tolist(), include_pm_info=False, only_a_share=False)[['product_id', 'product_name']]
    id_to_name = level_info.set_index('product_id')['product_name'].to_dict()
    performance_data['level_name'] = performance_data['id'].apply(lambda x: id_to_name[x])
    performance_data.sort_values(by=['end_date', 'period_return'], ascending=False, inplace=True)
    rename_map = {
        'period_return': '区间收益率',
        'annualized_period_return': '年化区间收益率',
        'max_drawdown': '最大回撤',
        'sharpe_ratio': '夏普',
        'calmar': '卡玛比',
        'annualized_volatility': '年化波动率',
        'level_name': '名称',
        'start_date': '开始日期',
        'end_date': '截止日期',
        'period_return_rank': '收益率排名',
        'current_drawdown': '当前回撤',
        'product_NAV': '持有规模',
        'product_weight': '产品权重'
    }
    performance_data.rename(columns=rename_map, inplace=True)

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
        '收益率排名': lambda x: "{:.2%}".format(x),
        '当前回撤': lambda x: "{:.2%}".format(x),
        '持有规模': lambda x: "{:,.2f}".format(x),
        '产品权重': lambda x: "{:.2%}".format(x),
    }
    d1 = dict(selector="th", props=[('text-align', 'center')])
    d2 = dict(selector='caption', props=[('text-align', 'center'), ('font-weight', 'bold'), ('color', 'black'), ('font-size', '125%')])
    perf_col = [rename_map[stat] for stat in stats]
    holding_amount_col = ['持有规模', '产品权重'] if include_holding_amount else []
    performance_data = performance_data[['名称', '开始日期', '截止日期'] + perf_col + holding_amount_col]
    new_cmap = sns.diverging_palette(**config.cmap_kwargs)
    if period != 'Today':
        performance_data = performance_data[['名称', '开始日期', '截止日期'] + perf_col  + holding_amount_col]
    else:
        performance_data = performance_data[['名称', '开始日期', '截止日期', '区间收益率'] + holding_amount_col]
    _df_caption = 'Holding Period Performance Stats, ' + 'period: ' + period + ', data frequency: ' + freq
    df = performance_data.reset_index(drop=True).style.format(formatter, na_rep="")\
        .set_properties(**{'width': '100', 'text-align': 'center'})\
        .set_caption(_df_caption)\
        .set_table_styles([d1])\
        .set_table_styles([d2], overwrite=False)
    for col in performance_data.columns.drop(['名称', '开始日期', '截止日期']):
        if col == '年化波动率':
            df = df.background_gradient(subset=col, cmap=sns.diverging_palette(**config.vol_cmap_kwargs),
                                        low=config.cmap_range_adjust_coef, high=config.cmap_range_adjust_coef, axis=0)
        elif col in ['最大回撤', '当前回撤']:
            df = df.background_gradient(subset=col, cmap=new_cmap, low=config.cmap_range_adjust_coef,
                                        high=config.cmap_range_adjust_coef, axis=0)
        elif col in ['持有规模', '产品权重']:
            df = df.background_gradient(subset=col, cmap='Reds', low=0,
                                        high=config.cmap_range_adjust_coef, axis=0,
                                        vmin=performance_data[col].abs().min(axis=0),
                                        vmax=performance_data[col].abs().max(axis=0))

        else:
            df = df.background_gradient(subset=col, cmap=new_cmap, low=config.cmap_range_adjust_coef,
                                        high=config.cmap_range_adjust_coef, axis=0,
                                        vmin=(-performance_data[col].abs().max(axis=0)),
                                        vmax=performance_data[col].abs().max(axis=0))
    df = df.highlight_null('white')
    return df

# --------------------------------------------------------------------
# 计算单一策略的基础风险收益指标
# 返回 单一策略风险收益指标dataframe，每一个period对应一行，表头为各类风险指标
# --------------------------------------------------------------------
def basicVis_calSingleFundPerfStatsPeriodAsRow(
    id,    # 输入公募\私募\FOF账户\比较基准 输入id；对于合成序列的分析，输入Dataframe进行配置
    date,
    freq,  # 数据频率，D或者W
    type,  # 公募\私募\账户\比较基准\合成序列 "MF" or "HF" or "FOF" or "BM" or "CUSTOMIZED_BM" or "COMMINGLE"
    periods=['YTD', 'YTLDLM', '2024', '2023', '2022', '2021', '2020', '2019', 'SI'],
    benchmark_id=None,      # e.g. '000905.SH', type == 'FOF'时,该参数为None时计算绝对perf，为"FOF_BM"时计算超额perf
    data_level='Strategy',  # type == 'FOF'或'BM'时该参数不起作用
    start_date=None,        # This parameter ONLY works for period list contains Customized
    stats=const.const.COMMON_PERF_STATS,  # 函数所需计算的stats list, 默认stats为'period_return', 'annualized_period_return', 'annualized_volatility', 'max_drawdown', 'sharpe_ratio', 'calmar'
    acc_nav=False   # 是否采用累计净值计算，部分账户存在分红，单位净值计算有误的情况下使用
):
    if type in ['BM', 'CUSTOMIZED_BM']:
        assert benchmark_id is None, "对比较基准等指数进行研究时请勿传入额外的benchmark_id"
    result, benchmark_id = _calSingleFundPerfStatsPretreatment(id, date, freq, type, periods, benchmark_id, data_level, start_date=start_date, summary_mode=False, stats=stats, acc_nav=acc_nav)

    formatter = {
        '区间收益率': lambda x: "{:.2%}".format(x),
        '年化区间收益率': lambda x: "{:.2%}".format(x),
        '年化波动率': lambda x: "{:.2%}".format(x) if not isinstance(x, str) else x,
        '最大回撤': lambda x: "{:.2%}".format(x),
        '当前回撤': lambda x: "{:.2%}".format(x),
        '夏普': lambda x: "{:.2f}".format(x) if not isinstance(x, str) else x,
        '卡玛比': lambda x: "{:.2f}".format(x),
        '年化区间超额收益': lambda x: "{:.2%}".format(x),
        '开始日期': lambda x: x.strftime("%Y-%m-%d"),
        '截止日期': lambda x: x.strftime("%Y-%m-%d"),
        '名称': lambda x: str(x),
        '收益率排名': lambda x: "{:.2%}".format(x),
        '统计区间': lambda x: str(x)
    }
    new_cmap = sns.diverging_palette(**config.cmap_kwargs)
    d1 = dict(selector="th", props=[('text-align', 'center')])
    d2 = dict(selector='caption', props=[('text-align', 'center'), ('font-weight', 'bold'), ('color', 'black'), ('font-size', '125%')])
    performance_data = result[['名称', '统计区间', '开始日期', '截止日期', '区间收益率', '年化区间收益率', '年化波动率', '最大回撤', '夏普', '卡玛比'] + (['当前回撤'] if 'current_drawdown' in stats else [])]
    if benchmark_id:
        _df_caption = '绩效数据, ' + '统计区间: ' + str(periods) + ', 数据频率: ' + freq + ', 比较基准: ' + str(benchmark_id)
    else:
        _df_caption = '绩效数据, ' + '统计区间: ' + str(periods) + ', 数据频率: ' + freq
    df = performance_data.reset_index(drop=True).style.format(formatter, na_rep="")\
        .set_properties(**{'width': '100', 'text-align': 'center'})\
        .set_caption(_df_caption).set_table_styles([d1])\
        .set_table_styles([d2], overwrite=False)
    for col in performance_data.columns.drop(['名称', '统计区间', '开始日期', '截止日期']):
        if col == '年化波动率':
            df = df.background_gradient(subset=col, cmap=sns.diverging_palette(**config.vol_cmap_kwargs), low=config.cmap_range_adjust_coef, high=config.cmap_range_adjust_coef, axis=0)
        elif col in ['最大回撤', '当前回撤']:
            df = df.background_gradient(subset=col, cmap=new_cmap, low=config.cmap_range_adjust_coef, high=config.cmap_range_adjust_coef, axis=0)
        else:
            df = df.background_gradient(subset=col, cmap=new_cmap, low=config.cmap_range_adjust_coef, high=config.cmap_range_adjust_coef, axis=0,
                                        vmin=(-performance_data[col].abs().max(axis=0)),
                                        vmax=performance_data[col].abs().max(axis=0))
    df = df.highlight_null('white')
    return df

# --------------------------------------------------------------------------
# 计算单一策略的基础+比较基准+超额的风险收益指标汇总
# 返回 包含策略、比较基准、相对超额三行数据，具有风险收益指标和period两级表头的dataframe
# --------------------------------------------------------------------------
def basicVis_calSingleFundPerfStatsSummaryPeriodAsColWithBM(
    id,
    date,
    freq,  # 数据频率，D或者W
    type,  # 公募\私募\账户 "MF" or "HF" or "FOF"
    periods=['YTD', 'YTLDLM', '2024', '2023', '2022', '2021', '2020', '2019', 'SI'],
    benchmark_id=None,  # e.g. '000905.SH', type == 'FOF'时,该参数为None时计算绝对perf，为"FOF_BM"时计算超额perf
    data_level='Strategy',  # type == 'FOF'时该参数不起作用
    simple_mode=False,  # 简化模式，减少展示列数, 设定为True后只展示收益率，显示periods参数指定的区间收益率
    include_title=True,
    acc_nav=False  # 是否采用累计净值计算，部分FOF账户存在分红，单位净值计算有误的情况下使用
):
    # 如果FOF账户有benchmark数据则打开summary_mode，策略、基准、超额的完整三行绩效数据，否则返回策略本身的绩效数据
    summary_mode = True if benchmark_id else False
    result, benchmark_id = _calSingleFundPerfStatsPretreatment(id, date, freq, type, periods, benchmark_id, data_level, summary_mode=summary_mode, acc_nav=acc_nav)

    result[['区间收益率', '年化区间收益率', '最大回撤', '年化波动率', '夏普', '卡玛比']] = result[['区间收益率', '年化区间收益率', '最大回撤', '年化波动率', '夏普', '卡玛比']].astype(float)
    perf_result = pd.pivot_table(result, index=['portfolio_id'], columns=['统计区间'], values=['区间收益率', '年化区间收益率', '最大回撤', '年化波动率', '夏普', '卡玛比'])
    perf_result['截止日期'] = max(result['截止日期'])
    perf_result['开始日期'] = min(result['开始日期'])
    perf_result.reset_index(inplace=True)
    perf_result['名称'] = perf_result['portfolio_id'].apply(lambda x: result[['portfolio_id', '名称']].set_index('portfolio_id').to_dict(orient='dict')['名称'][x])

    # 展示时只取有数据的列，防止账户年份不足 或 最近period无数据但之前有数据，导致的取数错误
    if simple_mode:
        perf_result_origin_col = [('名称', ''), ('开始日期', ''), ('截止日期', '')]+[('区间收益率', period) for period in periods]
    else:
        perf_result_origin_col = [('名称', ''), ('开始日期', ''), ('截止日期', ''), ('区间收益率', 'Recent_1M'), ('区间收益率', 'Recent_3M'),
                                  ('区间收益率', 'YTD'), ('区间收益率', '2024'), ('区间收益率', '2023'),
                                  ('区间收益率', '2022'), ('区间收益率', '2021'), ('区间收益率', 'SI'), ('年化区间收益率', 'SI'), ('最大回撤', 'YTD'),
                                  ('最大回撤', 'SI'), ('年化波动率', 'YTD'), ('年化波动率', 'SI'),
                                  ('夏普', 'YTD'), ('夏普', 'SI'), ('卡玛比', 'YTD'), ('卡玛比', 'SI')]
    perf_result_col = list(set(perf_result_origin_col).intersection(set(perf_result.columns)))
    # 交集运算后元素顺序混乱，按照原序重新排列
    perf_result_col.sort(key=perf_result_origin_col.index)
    perf_result = perf_result[perf_result_col]
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
        '收益率排名': lambda x: "{:.2%}".format(x),
        '统计区间': lambda x: str(x)
    }
    performance_data = perf_result
    format_dict = {
        col_key: formatter[level]
        for level in formatter
        for col_key in [col for col in performance_data if col[0] == level]
    }
    new_cmap = sns.diverging_palette(**config.cmap_kwargs)
    d1 = dict(selector="th", props=[('text-align', 'center'), ('border', '1px solid black')])
    d2 = dict(selector='caption', props=[('text-align', 'center'), ('font-weight', 'bold'), ('color', 'black'), ('font-size', '125%')])
    if include_title:
        if benchmark_id:
            _df_caption = '绩效数据, ' + '统计区间: ' + str(periods) + ', 数据频率: ' + freq + ', 比较基准: ' + str(benchmark_id)
        else:
            _df_caption = '绩效数据, ' + '统计区间: ' + str(periods) + ', 数据频率: ' + freq
    else:
        _df_caption = ''
    df = performance_data.reset_index(drop=True).style.format(format_dict, na_rep="")\
        .set_properties(**{'width': '100', 'text-align': 'center'})\
        .set_caption(_df_caption).set_table_styles([d1])\
        .set_table_styles([d2], overwrite=False).hide_index()
    for col in performance_data.columns.drop(['名称', '开始日期', '截止日期']):
        if '年化波动率' in col:
            df = df.background_gradient(subset=[col], cmap=sns.diverging_palette(**config.vol_cmap_kwargs), low=config.cmap_range_adjust_coef, high=config.cmap_range_adjust_coef, axis=0)
        elif '最大回撤' in col:
            df = df.background_gradient(subset=[col], cmap=new_cmap, low=config.cmap_range_adjust_coef, high=config.cmap_range_adjust_coef, axis=0)
        else:
            df = df.background_gradient(subset=[col], cmap=new_cmap, low=config.cmap_range_adjust_coef, high=config.cmap_range_adjust_coef, axis=0,
                                        vmin=(-performance_data[col].abs().max(axis=0)),
                                        vmax=performance_data[col].abs().max(axis=0))
    df = df.highlight_null('white')
    return df

# ------------------------------------------------------
# visualize correlation
# ------------------------------------------------------
def basicVis_plotCorrelation(
    ids_dict,           # dict, id with fund type, e.g. {'MF': ['000711.OF'], 'HF': ['S0000045', 'S0000053']}，可以只有MF或者HF
    period,             # 统计区间， YTD, YTLDLM, 2022, 2021, 2020, 2019, SI (since　inception）,Custom
    freq,               # 数据频率，D或者W
    benchmark=None,     # 基准, e.g. '885001.WI', '000905.SH'
    date=datetime.datetime.today().date(),
    start_date=None,        # This parameter ONLY works for period equal to Customized
    specific_order=False,
    display_mode='ppt'
):
    assert isinstance(ids_dict, dict), "ids_dict需为dict，例：{'MF': ['000711.OF'], 'HF': ['S0000045', 'S0000053']}"
    assert type(date) == datetime.date, '日期输入格式需为datetime.date'
    assert freq in ("D", "W"), "freq需为D或者W"
    assert display_mode in ('ppt', 'web')

    start_date, end_date = calendar.calender_getStartEndDate(period, date, start_date)
    corr_df = basicAnal.basicAnal_calCorrelation(ids_dict, start_date, end_date, freq, benchmark, specific_order=specific_order)
    strategy_info = custHF.custHF_getStrategyInfo()
    id_to_name = strategy_info.set_index('strategy_id')['strategy_name'].to_dict()
    mf_product_info = wd.wind_getCurrentProductList(only_a_share=False)  # 部分组合投的C份额
    mf_id_to_name = mf_product_info.set_index('product_id')['product_name']
    id_to_name.update(mf_id_to_name)
    corr_df.rename(columns=id_to_name, inplace=True)
    corr_df = corr_df.T.rename(columns=id_to_name)
    if period != 'SI':
        start_date_text = start_date.strftime("%Y-%m-%d")
    else:
        start_date_text = '成立以来'
    title_string = "相关系数：" + start_date_text + "到" + end_date.strftime("%Y-%m-%d") + ", benchmark:" + str(benchmark)
    if display_mode == 'ppt':
        fig, ax = plt.subplots(figsize=(15, 12), dpi=200)
        fontsize = np.clip(27 - 0.675*len(corr_df), 6.45, 18)  # 动态调整显示字体大小
        sns.heatmap(corr_df.round(2), annot=True, annot_kws={"size": fontsize}, cmap=sns.diverging_palette(**config.cmap_kwargs), vmin=-1, vmax=1)
        ax.set_title(title_string, fontsize=1.2*fontsize)
        plt.xticks(rotation=90, fontsize=fontsize)
        plt.yticks(rotation=0, fontsize=fontsize)
        result = ax.get_figure()
    elif display_mode == 'web':
        corr_df.index.name = 'index'
        corr_long =corr_df.reset_index().melt(id_vars='index')
        corr_long.columns = ['横轴', '纵轴', '相关性']
        variable_order = list(corr_df.columns)
        # 绘制相关性热力图
        heatmap = alt.Chart(corr_long, title=title_string).mark_rect().encode(
            x=alt.X('纵轴:O', sort=variable_order, title=''),
            y=alt.Y('横轴:O', sort=variable_order, title=''),
            color=alt.Color('相关性:Q',
                            scale=alt.Scale(range=['#2ecc71', '#f7f7f7', '#e74c3c'], domain=[-1, 0, 1])),
            tooltip=['横轴', '纵轴', {'field': '相关性', 'format': '.2f'}],
        )
        # 添加文本标签
        text = heatmap.mark_text(baseline='middle').encode(
            text=alt.Text('相关性:Q', format='.2f'),
            color=alt.value('black'),
        )
        # 组合图表
        result = heatmap + text
    return result


# ------------------------------------------------------
# 净值曲线画图
# ------------------------------------------------------
def basicVis_plotNav(
    ids_dict,   # dict, id with fund type, e.g. {'MF': ['000711.OF'], 'HF': ['S0000045', 'S0000053']}, 可以只有MF或者HF
                # or {'FOF': '704425'}，FOF用于单账户分析，只输入FOF
                # or {'BM': ['000905.SH']}，BM模式用于对比较基准的分析，目前只支持输入wind指数
                # or {'COMMINGLE': Dataframe}，COMMINGLE模式用于对合成序列的分析，输入Dataframe进行配置
    period,  # 统计区间
    freq,  # 数据频率，D或者W
    benchmark=None,  # 基准, e.g. '885001.WI', '000905.SH'; 对于FOF, 'FOF_BM'代表使用投委会基准，None代表不添加基准
    date=datetime.datetime.today().date() - datetime.timedelta(days=2),
    data_level='Strategy',  # Only works for HF
    start_date=None,    # This parameter ONLY works for period equal to Customized
    excess_ret=False,   # 是否计算超额净值，如果此项为True，benchmark不能为None,且ids_dict仅包含单一产品或单一策略
    display_mode='web',  # 'web': 网站展示用，legend画在右侧 'ppt': ppt插图用，legend画在下方
    include_title=True,  # 是否包含图的标题，默认包含
    acc_nav=False  # 是否采用累计净值计算，部分FOF账户存在分红，单位净值计算有误的情况下使用
):
    assert isinstance(ids_dict, dict), "ids_dict需为dict，例：{'MF': ['000711.OF'], 'HF': ['S0000045', 'S0000053']} " \
                                       "或 {'FOF': '704425'}"
    if 'FOF' in ids_dict.keys():
        assert type(ids_dict['FOF']) == str, "输入FOF仅用于单账户净值分析，例{'FOF': '704425'}"
        assert benchmark in (None, 'FOF_BM'), "FOF benchmark参数只支持None和FOF_BM"
    if 'BM' in ids_dict.keys():
        assert len(ids_dict['BM']) == 1, "对于比较基准的绩效分析暂不支持多个比较基准同时传入"
        assert type(ids_dict['BM']) == list, "输入BM信息请使用id list"
        assert benchmark is None, "BM分析模式下 benchmark参数只支持None"
    if 'CUSTOMIZED_BM' in ids_dict.keys():
        assert len(ids_dict['CUSTOMIZED_BM']) == 1, "对于比较基准的绩效分析暂不支持多个比较基准同时传入"
        assert type(ids_dict['CUSTOMIZED_BM']) == list, "输入BM信息请使用id list"
        assert benchmark is None, "CUSTOMIZED_BM分析模式下 benchmark参数只支持None"
    if 'COMMINGLE' in ids_dict.keys():
        assert isinstance(ids_dict['COMMINGLE'], pd.DataFrame), "输入COMMINGLE合成序列的配置信息请使用Dataframe格式"
        assert benchmark in (None, 'COMMINGLE_BM'), "COMMINGLE合成序列分析模式下 benchmark参数只支持None和COMMINGLE_BM"
    if excess_ret:
        assert set(ids_dict.keys()) <= {'MF', 'HF', 'FOF'}, "超额净值曲线目前支持对HF、MF、FOF进行绘制"
        assert benchmark is not None, "选择计算超额净值曲线时，需包含基准，benchmark不能为None"
    assert type(date) == datetime.date, '日期输入格式需为datetime.date'
    assert freq in ("D", "W"), "freq需为D或者W"
    assert data_level in ("Strategy", "Product"), "私募数据只支持策略和产品层面"

    color_map = alt.Scale()
    if 'FOF' in ids_dict.keys():
        benchmark_id_map = {None: False, 'FOF_BM': True}
        result = anlsFOF.anlsFOF_getAccountNav(date, ids_dict['FOF'], period, freq, start_date, include_benchmark=benchmark_id_map[benchmark], include_excess=excess_ret, acc_nav=acc_nav)
        if benchmark:
            level_info = custFOF.custFOF_getFOFReferenceData()
            FOF_benchmark = level_info[level_info['portfolio_id'] == ids_dict['FOF']]['benchmark'].iloc[0]
            bm_result = result[['date', 'bm_nav', 'id']].copy(deep=True)
            bm_result['id'] = '比较基准'
            bm_result.rename(columns={'bm_nav': 'nav'}, inplace=True)
            if excess_ret:
                excess_result = result[['date', 'excess_nav', 'id']].copy(deep=True)
                excess_result['id'] = '超额净值'
                excess_result.rename(columns={'excess_nav': 'nav'}, inplace=True)
                result = pd.concat([result[['date', 'nav', 'id']], bm_result, excess_result], axis=0)
                color_map = alt.Scale(domain=[list(set(result['id']) - set(['比较基准', '超额净值']))[0], '比较基准', '超额净值'],
                                      range=['#4674a4', '#f58518', '#ff2b2b'])
            else:
                result = result[['date', 'nav', 'id']].append(bm_result)
                color_map = alt.Scale(domain=[list(set(result['id']) - set(['比较基准']))[0], '比较基准'],
                                      range=['#4674a4', '#f58518'])

    elif 'BM' in ids_dict.keys():
        start_date, end_date = calendar.calender_getStartEndDate(period, date, start_date)
        nav_df = wd.wind_getIndexData(ids_dict['BM'][0], start_date, end_date, freq, method='last')[['date', 'index_code', 'close_price']].\
                                        rename(columns={'index_code': 'id', 'close_price': 'nav'})
        result = nav_df
    elif 'CUSTOMIZED_BM' in ids_dict.keys():
        start_date, end_date = calendar.calender_getStartEndDate(period, date, start_date)
        nav_df = wind_cached.windCached_getCustomizedIndexNav(ids_dict['CUSTOMIZED_BM'][0], start_date, end_date, freq)[['date', 'index_id', 'nav']].\
                                        rename(columns={'index_id': 'id'})
        result = nav_df
    elif 'COMMINGLE' in ids_dict.keys():
        start_date, end_date = calendar.calender_getStartEndDate(period, date, start_date)
        result = []
        nav_df = basicAnal.basicAnal_getCommingledSeriesNav(ids_dict['COMMINGLE'], start_date, end_date, freq, benchmark=benchmark)
        nav_df.set_index('date', inplace=True)
        nav_df.sort_values(by=nav_df.index[-1], axis=1, ascending=False, inplace=True)
        for col in nav_df.columns:
            nav = nav_df[col].reset_index()
            nav.loc[:, 'type'] = '比较基准' if 'benchmark' in col else ('超额净值' if 'excess' in col else col)
            nav.columns = ['date', 'nav', 'id']
            result.append(nav)
        result = pd.concat(result, axis=0)
        if benchmark:
            color_map = alt.Scale(domain=[list(set(result['id']) - set(['比较基准', '超额净值']))[0], '比较基准', '超额净值'], range=['#4674a4', '#f58518', '#ff2b2b'])
    else:
        start_date, end_date = calendar.calender_getStartEndDate(period, date, start_date)
        result = []
        if data_level == 'Strategy':
            level_info = custHF.custHF_getStrategyInfo()
            id_to_name = level_info.set_index('strategy_id')['strategy_name'].to_dict()
        else:
            level_info = custHF.custHF_getProductInfo()
            id_to_name = level_info.set_index('product_id')['product_short_name'].to_dict()
        mf_product_info = wd.wind_getCurrentProductList()
        mf_id_to_name = mf_product_info.set_index('product_id')['product_name']
        id_to_name.update(mf_id_to_name)
        id_to_name.update({'excess': '超额净值'})
        nav_df = basicAnal.basicAnal_returnToNav(ids_dict, start_date, end_date, freq, benchmark, data_level, excess_ret)
        nav_df.set_index('date', inplace=True)
        nav_df.sort_values(by=nav_df.index[-1], axis=1, ascending=False, inplace=True)
        for col in nav_df.columns:
            nav = nav_df[col].reset_index()
            nav.loc[:, 'type'] = id_to_name[col] if col in id_to_name.keys() else col
            nav.columns = ['date', 'nav', 'id']
            result.append(nav)
        result = pd.concat(result, axis=0)

    result["date"] = result["date"].apply(pd.Timestamp)
    max_ytick = result['nav'].max()*1.01
    min_ytick = result['nav'].min()*0.99
    nearest = alt.selection_single(nearest=True, on='mouseover', empty='none')
    selection = alt.selection_multi(fields=['id'], bind='legend', name='名称')
    title_string = ("超额" if excess_ret else "") + "净值时序图, 统计区间: " + str(period) + ", 数据频率: " + str(freq)
    if include_title:
        if 'FOF' in ids_dict.keys():
            title_string = "统计区间: " + str(period) + (", 比较基准: " + FOF_benchmark if benchmark else "")
        if 'COMMINGLE' in ids_dict.keys() and benchmark is not None:
            title_string += (", 比较基准: " + const.const.STANDARD_PORT_BM_NAME_DICT[list(set(result['id']) - set(['比较基准', '超额净值']))[0]])
    else:
        title_string=''
    base = alt.Chart(result, title=title_string).mark_line().encode(
            x=alt.X('date:T', title='日期', axis=alt.Axis(format='%Y/%m/%d')),
            y=alt.Y('nav', scale=alt.Scale(domain=[min_ytick, max_ytick]), title='指数点位' if 'BM' in ids_dict.keys() else '区间Nav'),
            color=alt.Color('id', scale=color_map) if display_mode == 'web' else alt.Color('id',scale=color_map, legend=alt.Legend(title='', orient='bottom')),
            tooltip=['id', 'date', {'field':'nav','format':',.4f'}],
            opacity=alt.condition(selection, alt.value(1), alt.value(0.1))
            )
    point = base.mark_point().encode(
            opacity=alt.condition(nearest, alt.value(1), alt.value(0))
            ).add_selection(nearest)
    lines = base.add_selection(selection)
    c = alt.layer(lines, point).interactive().configure_axisX(labelAngle=0)
    return c

# ------------------------------------------------------
# 月度收益画图，支持私募、FOF组合、基准、公募
# ------------------------------------------------------
def basicVis_monthlyReturn(
    ids,  # list, id,
    freq,  # 数据频率，D或者W
    num_trailing_month=None,  # 展示过去几个月的收益
    benchmark_id=None,  # 基准，e.g. 000905.SH
    date=datetime.datetime.today().date(),
    data_level='Strategy',
    single_id_only=False,  # If set to be True, return all months' return in a better format
    sort_method='first_column',  # 排序方式，first_column即按照首列降序，否则按照index降序
    data_type='HF',  # 输入list代码的类型
    acc_nav=False  # 是否采用累计净值计算，部分FOF账户存在分红，单位净值计算有误的情况下使用
):
    assert isinstance(date, datetime.date), "日期变量必须是datetime.date类型"
    assert freq in ("D", "W"), "数据频率只支持D或者W"
    assert data_level in ("Strategy", "Product"), "数据只支持策略和产品层面"
    assert data_type in ("BM", "CUSTOMIZED_BM", "COMMINGLE", "HF", "MF", "FOF"), "支持的类型有BM, CUSTOMIZED_BM, COMMINGLE, HF, MF, FOF"
    assert isinstance(ids, list), "输入值为列表"

    result = basicAnal.basicAnal_calMonthlyReturn(ids, const.const.COMMINGLE_SI_START_DATE if data_type=='COMMINGLE'
                                                    else (const.const.BM_SI_START_DATE if data_type in ("BM", "CUSTOMIZED_BM") else const.const.SI_START_DATE),
                                                    date, freq=freq, benchmark_id=benchmark_id, data_level=data_level, data_type=data_type, acc_nav=acc_nav)
    result.drop(['data_freq', 'benchmark_id'], axis=1, inplace=True)
    result = result.iloc[:num_trailing_month, :]
    if data_type == 'HF':
        if data_level == 'Strategy':
            level_info = custHF.custHF_getStrategyInfo()
            id_to_name = level_info.set_index('strategy_id')['strategy_name'].to_dict()
        else:
            level_info = custHF.custHF_getProductInfo()
            id_to_name = level_info.set_index('product_id')['product_short_name'].to_dict()
        result.rename(columns=id_to_name, inplace=True)
    elif data_type == 'MF':
        if data_level == 'Strategy':
            level_info = custMF.custMF_getMFStrategyInfo()
            id_to_name = level_info.set_index('strategy_id')['strategy_name'].to_dict()
        else:
            level_info = wd.wind_getCurrentProductList(product_ids=ids, include_pm_info=False, only_a_share=False)
            id_to_name = level_info.set_index('product_id')['product_full_name'].to_dict()
        result.rename(columns=id_to_name, inplace=True)
    elif data_type == 'FOF':
        level_info = custFOF.custFOF_getFOFReferenceData(include_advisory_account=True)
        benchmark_id = level_info[level_info['portfolio_id'] == ids[0]]['benchmark'].iloc[0]
        id_to_name = level_info.set_index('portfolio_id')['portfolio_name'].to_dict()
        chinese_suffix_map = {'benchmark': '比较基准', 'excess': '相对超额'}
        result.rename(columns=lambda x: id_to_name[x.split('_')[0]] if len(x.split('_')) == 1 else id_to_name[x.split('_')[0]] + '_' + chinese_suffix_map[x.split('_')[1]],inplace=True)
    elif data_type == 'COMMINGLE':
        if single_id_only:
            assert len(ids) == 1, '基准分析只允许有一个ID'
            data_type = 'Benchmark'
            id_to_name = {'Benchmark': ids[0]['series_name'].iloc[0]}
            ids = ['Benchmark']
        else:
            benchmark_id = '对应私享基准'
            chinese_suffix_map = {'benchmark': '比较基准', 'excess': '相对超额'}
            result.rename(columns=lambda x: x if len(x.split('_')) == 1 else x.split('_')[0] + '_' + chinese_suffix_map[x.split('_')[1]],inplace=True)
    elif data_type in ("BM", "CUSTOMIZED_BM"):
        assert len(ids) == 1, '基准分析只允许有一个ID'
        data_type = 'Benchmark'
        ids = ['Benchmark']
        id_to_name = {'Benchmark': 'return'}

    result.dropna(axis=1, how='all', inplace=True)
    result.reset_index(inplace=True)
    result['year'] = result['year'].astype(str)
    result['index'] = result['year'] + '-' + result['month'].astype(str)
    if single_id_only:
        assert len(ids) == 1, '只允许有一个ID'
        assert num_trailing_month == None, '显示所有月份收益，该参数保持None'
        result = pd.pivot_table(result, index='year', columns='month', values=id_to_name[ids[0]])
        df = result.sort_index(ascending=False)
    else:
        result.drop(['year', 'month'], axis=1, inplace=True)
        result.set_index('index', inplace=True)
        result.index.name = '名称'
        result = result.T
        if sort_method == 'first_column':
            df = result.sort_values(by=result.columns[0], ascending=False)
        else:
            df = result.sort_index(ascending=True)
    formatter = dict(zip(list(df.columns), [lambda x: "{:.2%}".format(x)] * len(df.columns)))
    new_cmap = sns.diverging_palette(**config.cmap_kwargs)
    d1 = dict(selector="th", props=[('text-align', 'center')])
    d2 = dict(selector='caption', props=[('text-align', 'center'), ('font-weight', 'bold'), ('color', 'black'), ('font-size', '125%')])
    if benchmark_id:
        _df_caption = data_type + " Monthly Return, " + "benchmark: " + benchmark_id
    else:
        _df_caption =data_type + " Monthly Return"

    df = df.style.format(formatter, na_rep="").set_properties(**{'width': '100', 'text-align': 'center'})\
         .set_caption(_df_caption).set_table_styles([d1]).set_table_styles([d2], overwrite=False)
    df = df.background_gradient(cmap=new_cmap, low=config.cmap_range_adjust_coef, high=config.cmap_range_adjust_coef, axis=0, vmin=-result.abs().max().max(), vmax=result.abs().max().max())
    df = df.highlight_null('white')
    return df

# ------------------------------------------------------
# 私募周度收益画图
# ------------------------------------------------------
def basicVis_HFWeeklyReturn(
    ids,  # list, id, e.g.
    freq,  # 数据频率，D或者W
    num_trailing_week=None,  # 展示过去几个周的收益
    benchmark_id=None,  # 基准，e.g. 000905.SH
    date=datetime.datetime.today().date(),
    data_level='Strategy',
    single_id_only=False # If set to be True, return all weeks' return in a better format
):
    assert (type(date) == datetime.date), '日期输入格式需为datetime.date'
    assert data_level in ("Strategy", "Product"), "私募数据只支持策略和产品层面"

    result = basicAnal.basicAnal_calHFWeeklyReturn(ids, datetime.date(1990, 1, 1), date, freq, benchmark_id, data_level)
    result.drop(['data_freq', 'benchmark_id'], axis=1, inplace=True)
    result = result.iloc[:num_trailing_week, :]
    if data_level == 'Strategy':
        level_info = custHF.custHF_getStrategyInfo()
        id_to_name = level_info.set_index('strategy_id')['strategy_name'].to_dict()
    else:
        level_info = custHF.custHF_getProductInfo()
        id_to_name = level_info.set_index('product_id')['product_short_name'].to_dict()
    result.rename(columns=id_to_name, inplace=True)
    result.dropna(axis=1, how='all', inplace=True)
    result.reset_index(inplace=True)
    result['index'] = result['year'].astype(str) + '-' + result['week'].astype(str)
    if single_id_only:
        assert len(ids) == 1, '只允许有一个ID'
        assert num_trailing_week == None, '显示所有周度收益，该参数保持None'
        result = pd.pivot_table(result, index='year', columns='week', values=id_to_name[ids[0]])
        result.sort_index(ascending=False, inplace=True)
    else:
        result.drop(['year', 'week'], axis=1, inplace=True)
        result.set_index('index', inplace=True)
        result = result.T
    formatter = dict(zip(list(result.columns), [lambda x: "{:.2%}".format(x)] * len(result.columns)))
    new_cmap = sns.diverging_palette(150, 10, s=1000, l=20, n=20, as_cmap=True)
    d1 = dict(selector="th", props=[('text-align', 'center')])
    d2 = dict(selector='caption', props=[('text-align', 'center'), ('font-weight', 'bold'), ('color', 'black'), ('font-size', '125%')])
    if benchmark_id:
        _df_caption = "HF Weekly Return, " + "benchmark: " + benchmark_id
    else:
        _df_caption = "HF Weekly Return"
    df = result.sort_values(result.columns[0], ascending=False).style.format(formatter, na_rep="").background_gradient(cmap=new_cmap, axis=0).highlight_null('white').set_properties(**{'width': '100', 'text-align': 'center'}).set_caption(_df_caption).set_table_styles([d1]).set_table_styles([d2], overwrite=False)
    return df

# ------------------------------------------------------
# 回撤曲线画图
# ------------------------------------------------------
def basicVis_plotDrawdownSeries(
    ids_dict,               # dict, id with fund type, e.g. {'MF': ['000711.OF'], 只有MF或者HF，传入id数量必须为1
    period,                 # 统计区间
    freq,                   # 数据频率，D或者W
    benchmark,              # 基准, e.g. '885001.WI', '000905.SH', None
    date=datetime.datetime.today().date() - datetime.timedelta(days=2),
    data_level='Strategy',  # Only works for HF
    start_date=None,        # This parameter ONLY works for period equal to Customized
    excess_ret=False,            # 是否计算超额净值的回撤序列，如果此项为True，benchmark不能为None,且ids_dict仅包含单一产品或单一策略
    display_mode='web'      # 'web': 网站展示用，legend画在右侧 'ppt': ppt插图用，legend画在下方
):
    assert isinstance(ids_dict, dict), "ids_dict需为dict，例：{'MF': ['000711.OF'], 'HF': ['S0000045', 'S0000053']} "
    assert 'FOF' not in ids_dict.keys(), "暂不支持FOF产品计算"
    assert type(date) == datetime.date, '日期输入格式需为datetime.date'
    assert freq in ("D", "W"), "freq需为D或者W"
    assert data_level in ("Strategy", "Product"), "私募数据只支持策略和产品层面"
    if excess_ret:
        assert benchmark is not None, "计算超额回撤时必须传入基准"
        # 将dict中的产品或策略代码展开到一个list中
        dicts_value = list(ids_dict.values())
        id_list = list(itertools.chain(*dicts_value))
        assert len(id_list) == 1, "计算超额回撤时，仅允许传入单一产品或策略"

    #获取数据
    start_date, end_date = calendar.calender_getStartEndDate(period, date, start_date)
    result = []
    if data_level == 'Strategy':
        level_info = custHF.custHF_getStrategyInfo()
        id_to_name = level_info.set_index('strategy_id')['strategy_name'].to_dict()
    else:
        level_info = custHF.custHF_getProductInfo()
        id_to_name = level_info.set_index('product_id')['product_short_name'].to_dict()
    mf_product_info = wd.wind_getCurrentProductList()
    mf_id_to_name = mf_product_info.set_index('product_id')['product_name']
    id_to_name.update(mf_id_to_name)
    id_to_name.update({'excess': '超额回撤'})
    drawdown_df = basicAnal.basicAnal_getDrawdownSeries(ids_dict, start_date, end_date, freq, benchmark, data_level, excess_ret=excess_ret)
    drawdown_df.set_index('date', inplace=True)
    drawdown_df.sort_values(by=drawdown_df.index[-1], axis=1, ascending=False, inplace=True)
    for col in drawdown_df.columns:
        nav = drawdown_df[col].reset_index()
        nav.loc[:, 'type'] = id_to_name[col] if col in id_to_name.keys() else col
        nav.columns = ['date', 'drawdown', 'id']
        result.append(nav)
    result = pd.concat(result, axis=0)
    # 画图
    result["date"] = result["date"].apply(pd.Timestamp)
    nearest = alt.selection_single(nearest=True, on='mouseover', empty='none')
    selection = alt.selection_multi(fields=['id'], bind='legend', name='名称')
    title_string = "回撤时序图, 统计区间: " + str(period) + ", 数据频率: " + str(freq)
    base = alt.Chart(result, title=title_string).mark_line().encode(
            x=alt.X('date:T', title='日期', axis=alt.Axis(format='%Y/%m/%d')),
            y=alt.Y('drawdown', title='回撤',axis=alt.Axis(format='%')),
            color='id' if display_mode == 'web' else alt.Color('id', legend=alt.Legend(title='', orient='bottom')),
            tooltip=['id', 'date', {'field':'drawdown','format':'.2%'}],
            opacity=alt.condition(selection, alt.value(1), alt.value(0.1))
            )
    point = base.mark_point().encode(
            opacity=alt.condition(nearest, alt.value(1), alt.value(0))
            ).add_selection(nearest)
    lines = base.add_selection(selection)
    chart = alt.layer(lines, point).interactive().configure_axisX(labelAngle=0)
    return chart

# ------------------------------------------------------
# 工具函数 - 将展示绝对数值的df转换为展示相对排名(分位)，并将对应的列上色
# 具有灵活性，可指定需要处理的列名，其他不需要处理的保持原样
# ------------------------------------------------------
def basicVis_Stat2Rank(
    data,  # 输入DataFrame格式的数据每列为同类的数据
    rank_cols,  # dict, key:需要将指标转换为相对排名的列名，value: True则代表该指标越大越好，其排名分位数越大、越靠前，False反之；支持输入多列
):
    assert isinstance(data, pd.DataFrame), "请输入DataFrame格式的数据"
    assert type(rank_cols) == dict, '列名以及排序配置输入格式需为dict'
    assert set(rank_cols.keys()) <= set(list(data.columns)), '列名输入错误'

    result = basicAnal.basicAnal_Stat2Rank(data, rank_cols)
    new_cmap = sns.diverging_palette(**config.cmap_kwargs)
    d1 = dict(selector="th", props=[('text-align', 'center')])
    d2 = dict(selector='caption', props=[('text-align', 'center'), ('font-weight', 'bold'), ('color', 'black'), ('font-size', '125%')])
    formatter = dict((col, lambda x: "{:.2%}".format(x)) for col in rank_cols.keys())
    df = result.style.format(formatter, na_rep="")\
        .set_properties(**{'width': '100', 'text-align': 'center'})\
        .set_table_styles([d1])\
        .set_table_styles([d2], overwrite=False)
    for col in rank_cols.keys():
        df = df.background_gradient(subset=col, cmap=new_cmap, low=config.cmap_range_adjust_coef, high=config.cmap_range_adjust_coef, vmin=0, vmax=1, axis=0)
    df = df.highlight_null('white')

    return df


# -------------------------------------- 私有函数 ----------------------------------------------------------- #

# ------------------------------------------------------
# 计算单一策略的基础风险收益指标或“基础+比较基准+超额”指标汇总的预处理函数
# 返回值 result为指标dataframe benchmark为比较基准名称string
# ------------------------------------------------------
def _calSingleFundPerfStatsPretreatment(
    id,    # 输入公募\私募\FOF账户\比较基准 输入id；对于合成序列的分析，输入Dataframe进行配置
    date,
    freq,  # 数据频率，D或者W
    type,  # 公募\私募\账户\比较基准\合成序列 "MF" or "HF" or "FOF" or "BM" or "COMMINGLE"
    periods=['YTD', 'YTLDLM', '2024', '2023', '2022', '2021', '2020', '2019', 'SI'],
    benchmark_id=None,  # e.g. '000905.SH', type == 'FOF'时,该参数为None时计算绝对perf，为"FOF_BM"时计算超额perf
    data_level='Strategy',  # type == 'FOF'时该参数不起作用
    start_date=None,        # This parameter ONLY works for period list contains Customized
    summary_mode=False,     # True:计算单一策略的基础+比较基准+超额的风险收益指标汇总multi-index表格  False:计算单一策略的基础风险收益指标表格
    stats=const.const.COMMON_PERF_STATS,  # 函数所需计算的stats list, 默认stats为'period_return', 'annualized_period_return', 'annualized_volatility', 'max_drawdown', 'sharpe_ratio', 'calmar'
    acc_nav=False  # 是否采用累计净值计算，部分FOF账户存在分红，单位净值计算有误的情况下使用
):
    start_date_input = start_date
    if type in ['BM', 'CUSTOMIZED_BM']:
        assert benchmark_id is None, "对比较基准等指数进行研究时请勿传入额外的benchmark_id"
    result = []
    for period in periods:
        start_date, end_date = calendar.calender_getStartEndDate(period, date, start_date_input if period == 'Customized' else None)
        if type == 'FOF':
            assert period != 'YTLDLM', 'FOF不支持YTLDLM参数'
            assert benchmark_id in (None, 'FOF_BM'), 'FOF组合 benchmark_id输入只支持None和FOF_BM'
            benchmark_id_map = {None: False, 'FOF_BM': True}
            this_result = anlsFOF.anlsFOF_calFOFPerfStats(date, [id], period, freq, benchmark=benchmark_id_map[benchmark_id],
                                                          start_date=start_date if period == 'Customized' else None, summary_mode=summary_mode, stats=stats, acc_nav=acc_nav)
        else:
            this_result = basicAnal.basicAnal_calPerformanceStats([id], start_date, end_date, freq, type, benchmark_id, data_level, stats=stats)
        this_result['period'] = period
        if len(this_result) != 0:
            result.append(this_result)
    result = pd.concat(result)
    if type == 'MF':
        mf_product_info = wd.wind_getCurrentProductList()
        id_to_name = mf_product_info.set_index('product_id')['product_name']
        result['level_name'] = result['id'].apply(lambda x: id_to_name[x])
    elif type == 'HF':
        if data_level == 'Strategy':
            level_info = custHF.custHF_getStrategyInfo()
            id_to_name = level_info.set_index('strategy_id')['strategy_name'].to_dict()
        else:
            level_info = custHF.custHF_getProductInfo()
            id_to_name = level_info.set_index('product_id')['product_short_name'].to_dict()
        result['level_name'] = result['id'].apply(lambda x: id_to_name[x])
    elif type == 'FOF':
        level_info = custFOF.custFOF_getFOFReferenceData(include_advisory_account=True)
        id_to_name = level_info.set_index('portfolio_id')['portfolio_name'].to_dict()
        if summary_mode:
            chinese_suffix_map = {'benchmark': '比较基准', 'excess': '相对超额'}
        result['level_name'] = result['portfolio_id'].apply(lambda x: id_to_name[x] if len(x.split('_')) == 1 else
                                id_to_name[x.split('_')[0]] + '_' + chinese_suffix_map[x.split('_')[1]])
        FOF_benchmark = level_info[level_info['portfolio_id'] == id]['benchmark'].iloc[0]
    elif type == 'COMMINGLE':
        result['level_name'] = result['id']
    elif type == 'BM':
        result['level_name'] = result['id'].apply(lambda x: dict(zip(const.const.WEB_BENCHMARK_LIST.values(), const.const.WEB_BENCHMARK_LIST.keys()))[x])
    elif type == 'CUSTOMIZED_BM':
        result['level_name'] = result['id'].apply(lambda x: dict(zip(const.const.CUSTOMIZED_BENCHMARK_LIST.values(), const.const.CUSTOMIZED_BENCHMARK_LIST.keys()))[x])
    result.rename(columns={
        'period_return': '区间收益率',
        'annualized_period_return': '年化区间收益率',
        'max_drawdown': '最大回撤',
        'sharpe_ratio': '夏普',
        'calmar': '卡玛比',
        'annualized_volatility': '年化波动率',
        'current_drawdown': '当前回撤',
        'level_name': '名称',
        'start_date': '开始日期',
        'end_date': '截止日期',
        'period_return_rank': '收益率排名',
        'period': '统计区间'
    }, inplace=True)

    # 此处还需return一个benchmark用来写表格标题
    benchmark = FOF_benchmark if (type == 'FOF' and benchmark_id is not None) else \
                (const.const.STANDARD_PORT_BM_NAME_DICT[result['id'].iloc[0]] if (type == 'COMMINGLE' and benchmark_id is not None) else benchmark_id)
    return result, benchmark

