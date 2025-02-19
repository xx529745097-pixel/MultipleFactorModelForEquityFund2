# ---------------------------------------
# 监控类功能的分析函数
# ---------------------------------------

import numpy as np
import pandas as pd
import datetime
import math
import src.data.wind as wind
import src.data.amdata as amdata
import src.data.irm as irm
import src.utils.fof_calendar as calendar
import src.utils.Calculation as cal
import src.data.custHF as custHF
import src.data.custFOF as custFOF
import src.data.custMF as custMF
import src.data.wind as wd
import src.analysis.basicAnalysis as basicAnal
import src.analysis.portfolioAnalysis as portAnls
import src.analysis.indexFutureAnalysis as idxFutureAnls
import src.analysis.MFAnalysis as MFAnal
import src.analysis.universeAnalysis as univAnls
import src.config as config
import src.monitor_config as monitor_config
import src.const as const

# ------------------------------------------------------------------
# 监控持仓的私募基金是否都已具有业绩跟踪，是否都已标成在库已投，是否已收到净值邮件
# 将持有但未跟踪的产品进行输出提示
# ------------------------------------------------------------------
def mntrAnls_trackingHFNav(
    date,                       # 考察日期，看当期持有的私募基金是否已经有跟踪（收到净值）
    tracked_week_threshold=4,   # 判定为有业绩跟踪产品的阈值，默认四周内如有收到净值落库则判定为跟踪状态
):
    holding_data = custFOF.custFOF_getFOFHoldingData(date, date)
    ref_data = custFOF.custFOF_getFOFReferenceData(include_advisory_account=True)
    holding_data = pd.merge(holding_data, ref_data[['portfolio_id', 'portfolio_status', 'level_3_type', 'pm_name']], how='left', on='portfolio_id')
    # 统计时不考虑臻选户、万通1号、投顾账户、外部共管账户
    holding_data = holding_data[~holding_data['level_3_type'].str.contains('臻选').fillna(False)]
    for key in config.monitor_exclude_account['key_word']:
        holding_data = holding_data[~holding_data['portfolio_name'].str.contains(key).fillna(False)]
    holding_data = holding_data[~holding_data['pm_name'].fillna('').str.contains('|'.join(config.monitor_exclude_external_pm_list))]
    holding_data = holding_data[holding_data['portfolio_status'] == '正常运作']
    holding_hf_info = holding_data[holding_data['product_type'] == '私募基金']
    holding_hf_info['portfolio_name'] = holding_hf_info['portfolio_name'].apply(lambda x: str(x)+',')
    holding_hf_info['pm_name'] = holding_hf_info['pm_name'].apply(lambda x: str(x)+',')
    holding_hf_info = holding_hf_info.groupby(['date', 'product_id', 'product_name'], as_index=False).agg({'product_NAV': 'sum', 'portfolio_id': 'count', 'portfolio_name':'sum', 'pm_name':'sum'})
    hf_product_info = custHF.custHF_getProductInfo()[['product_id', 'product_type', 'company_short_name', 'strategy_name', 'label_level_1', 'label_level_2', 'primary_coverage']]
    holding_hf_info = pd.merge(holding_hf_info, hf_product_info, on='product_id', how='left')
    tracked_data = custHF.custHF_getProductReturn(date-datetime.timedelta(7*tracked_week_threshold), date, freq='W')
    # 筛选出近几周内无收益数据的已投私募 或 未标为在库已投、未明确一二级标签的已投私募：
    diff_data = holding_hf_info[(~holding_hf_info['product_id'].isin(tracked_data['product_id'].tolist())) | (holding_hf_info['product_type']!='在库已投') | (pd.isna(holding_hf_info['label_level_1']))]
    # 托管邮件获取情况，用于初步归因缺数原因（是未收到邮件（未读入）还是有邮件已读入但产品没配置净值信息）
    custodian_email_info = custHF.custHF_getHFCustodianDataIDMapping()
    # 如果产品有净值邮件读取记录，标记为"是"
    diff_data['email_nav_flag'] = diff_data['product_id'].apply(lambda x: '是' if x in custodian_email_info['product_id'].tolist() else '否')
    # 产品代码开头为70、90的标记为后端产品，展示时分块进行排序
    diff_data['back_end_flag'] = diff_data['product_id'].apply(lambda x: '是' if (x[:2] == '70' or x[:2] == '90') else '否')
    result = diff_data[['date', 'product_id', 'product_name', 'back_end_flag', 'product_type', 'label_level_1', 'label_level_2',
                        'product_NAV', 'portfolio_id', 'email_nav_flag', 'primary_coverage', 'portfolio_name', 'pm_name']].rename(columns={'portfolio_id': 'holding_portfolio_num'})
    return result

# ------------------------------------------------------------------
# 监控所有持仓私募基金触及预警线、止损线的情况，汇总展示
# ------------------------------------------------------------------
def mntrAnls_unitPriceWarning(
    date,                       # 考察日期，取该日期前最新的私募净值信息
    product_ids=None,           # product_ids list, 用于指定私募, 默认为None考察全部可取到数据的私募
    tracked_week_threshold=4,   # 判定私募净值为有效数据的阈值，默认设置为4周，4周以外的数据不纳入考虑
):
    # 基础数据获取整理
    start_date = date-datetime.timedelta(7*tracked_week_threshold)
    hf_nav_data_d = custHF.custHF_getProductReturn(start_date, date, 'D', product_ids, include_nav=True)
    hf_nav_data_w = custHF.custHF_getProductReturn(start_date, date, 'W', product_ids, include_nav=True)
    hf_nav_data = pd.concat([hf_nav_data_d, hf_nav_data_w]).sort_values('date')
    hf_nav_data = hf_nav_data.groupby('product_id').tail(1)  # 每个产品都取最新一天的数据
    hf_product_info = custHF.custHF_getProductInfo()[['product_id', 'product_short_name', 'product_type', 'warning_threshold', 'stop_loss_threshold',
                            'product_inception_date', 'company_short_name', 'strategy_name', 'label_level_1', 'label_level_2', 'primary_coverage']]
    hf_warning_data = pd.merge(hf_nav_data[['product_id', 'unit_value', 'acm_unit_value', 'date']], hf_product_info, on='product_id', how='left')
    hf_warning_data = hf_warning_data[hf_warning_data['product_type'] == '在库已投']
    # 没有维护预警线止损线的数据先直接skip
    hf_warning_data['warning_threshold_near'] = hf_warning_data['warning_threshold']*1.1
    hf_warning_data.loc[hf_warning_data['warning_threshold_near'] > 0.99, 'warning_threshold_near'] = 0.99
    check_col_list = ['warning_threshold_near','warning_threshold', 'stop_loss_threshold']
    for check_col in check_col_list:
        hf_warning_data[check_col+'_flag'] = hf_warning_data.apply(lambda x: ('是' if x['unit_value'] < x[check_col] else '否') if not pd.isna(x[check_col]) else None, axis=1)
    hf_warning_data = hf_warning_data[(hf_warning_data['warning_threshold_flag'] == '是') | (hf_warning_data['stop_loss_threshold_flag'] == '是') | (hf_warning_data['warning_threshold_near_flag'] == '是')]
    hf_warning_data['deviation'] = hf_warning_data['unit_value'] - hf_warning_data['warning_threshold']
    # 整理结果
    hf_warning_data = hf_warning_data.sort_values(['deviation'])
    hf_warning_data = hf_warning_data[['date', 'product_id','product_short_name', 'product_inception_date', 'unit_value', 'acm_unit_value',
                                        'warning_threshold', 'stop_loss_threshold', 'warning_threshold_near_flag', 'warning_threshold_flag', 'stop_loss_threshold_flag',
                                       'company_short_name', 'strategy_name', 'label_level_1', 'label_level_2','primary_coverage']]

    return hf_warning_data

# ----------------------------------------------------------------------------------
# 监控持仓的单一基金集中度情况(threshold 默认25%)、单一公司持仓集中度情况(threshold 默认35%),
# 活期存款比例情况(threshold 默认25%) 汇总展示
# ----------------------------------------------------------------------------------
def mntrAnls_FOFConcentrationWarning(
    date,                           # 考察日期，取该日期的持仓信息进行计算
    holding_product_threshold=0.25,  # 单一基金持仓集中度监控阈值，默认25%
    holding_company_threshold=0.35,  # 单一公司持仓集中度监控阈值，默认35%
):
    # 基础数据获取
    holding_data = custFOF.custFOF_getFOFHoldingData(date, date)
    ref_data = custFOF.custFOF_getFOFReferenceData()
    holding_data = pd.merge(holding_data, ref_data[['portfolio_id', 'portfolio_status', 'level_3_type', 'pm_name']], how='left', on='portfolio_id')
    hf_info = custHF.custHF_getProductInfo()[['product_id', 'strategy_name', 'label_level_1', 'label_level_2', 'company_short_name']]
    holding_data = pd.merge(holding_data, hf_info, on='product_id', how='left')

    # 按照配置信息，对账户和产品信息进行预处理
    # 统计时不考虑臻选户、万通1号、投顾账户
    holding_data = holding_data[~holding_data['level_3_type'].str.contains('臻选').fillna(False)]
    for key in config.monitor_exclude_account['key_word']:
        holding_data = holding_data[~holding_data['portfolio_name'].str.contains(key).fillna(False)]
    holding_data = holding_data[holding_data['portfolio_status'] == '正常运作']
    # 筛选成立三个月以上的账户，避免筛选出大量的活期存款集中度高的账户
    holding_data = holding_data[holding_data['inception_date'] <= date-datetime.timedelta(days=90)]
    # 按照配置的config剔除不纳入考虑的产品类型
    for level in config.holding_concentration_monitor_exclude_config.keys():
        holding_data = holding_data[~holding_data[level].isin(config.holding_concentration_monitor_exclude_config[level])]
    holding_data = holding_data[['date','portfolio_id', 'portfolio_name', 'level_3_type', 'pm_name', 'inception_date', 'NAV', 'product_id', 'product_name', 'product_type',
                                 'product_volume', 'product_NAV', 'product_weight', 'strategy_name', 'label_level_1', 'label_level_2', 'company_short_name']]

    # 计算公司持仓数据
    holding_company = holding_data.groupby(['date', 'portfolio_id', 'company_short_name'], as_index=False)['product_NAV', 'product_weight'].sum().\
                                    rename(columns={'product_NAV': 'company_NAV', 'product_weight': 'company_weight'})
    holding_data = pd.merge(holding_data, holding_company, on=['date', 'portfolio_id', 'company_short_name'], how='left')
    # 按照给定阈值筛选数据并排序
    holding_concentration_warning = holding_data[(holding_data['product_weight'] > holding_product_threshold) | (holding_data['company_weight'] > holding_company_threshold)]
    holding_concentration_warning.sort_values(['date', 'pm_name', 'level_3_type', 'portfolio_id', 'product_type', 'company_weight', 'product_weight'], ascending=False, inplace=True)
    holding_concentration_warning = holding_concentration_warning[['date', 'portfolio_name', 'level_3_type', 'pm_name', 'NAV', 'product_id', 'product_name', 'product_type',
                                                                   'product_NAV', 'product_weight', 'company_short_name', 'company_NAV', 'company_weight',
                                                                   'strategy_name', 'label_level_1', 'label_level_2']]
    return holding_concentration_warning

# -----------------------------------------------------------------------
# 监控所有具有业绩跟踪的私募基金最近一年的当前回撤情况，汇总展示，默认直接使用周频数据计算
# -----------------------------------------------------------------------
def mntrAnls_HFCurrentDrawdownWarning(
    date,                       # 考察日期，取该日期前最新的私募净值信息
    label_level_1,              # 产品的一级标签，发送时每个一级标签作为一个表进行发送
    freq='W',                   # 数据频率
    period='Recent_1Y',         # 默认考察最近一年区间的当前回撤
    tracked_week_threshold=4,   # 判定私募净值为有效数据的阈值，默认设置为4周，最新日期截至4周以外的产品不纳入考虑
):
    assert period == 'Recent_1Y', "目前默认只考察产品Recent_1Y区间的当前回撤"
    assert freq in ['D', 'W'], "数据频率只支持D和W"
    assert label_level_1 in config.product_current_drawdown_monitor_config['label_level_1'].keys(), "请先配置该类策略的当前回撤监控阈值"

    start_date = date - datetime.timedelta(7*tracked_week_threshold)
    hf_nav_data = custHF.custHF_getProductReturn(start_date, date, freq, include_nav=True).rename(columns={'date': 'nav_date'}).sort_values('nav_date')
    hf_nav_data = hf_nav_data.groupby('product_id').tail(1)  # 每个产品都取最新一天的数据
    hf_product_info = custHF.custHF_getProductInfo()[['product_id', 'product_short_name', 'product_type', 'company_short_name', 'strategy_name', 'label_level_1', 'label_level_2', 'primary_coverage']]
    hf_warning_data = pd.merge(hf_nav_data[['product_id', 'unit_value', 'nav_date']], hf_product_info, on='product_id', how='left')
    hf_warning_data = hf_warning_data[(hf_warning_data['product_type'] == '在库已投') & (hf_warning_data['label_level_1'] == label_level_1)]
    # 绩效数据获取，指数增强策略需要看超额回撤，故单独判断处理：
    perf_start_date, perf_end_date = calendar.calender_getStartEndDate(period, date)
    if label_level_1 == '指数增强':
        ie_product_perf_result = []
        ie_product_benchmark_dict = {'300指增': '000300.SH', '500指增': '000905.SH', '1000指增': '000852.SH'}
        for label_level_2 in ie_product_benchmark_dict.keys():
            performance_data = basicAnal.basicAnal_calPerformanceStats(hf_warning_data[hf_warning_data['label_level_2'] == label_level_2]['product_id'].tolist(),
                                                                       perf_start_date, perf_end_date, freq=freq,  fund_type='HF', benchmark_id=ie_product_benchmark_dict[label_level_2],
                                                                       data_level='Product', stats=['annualized_period_return','max_drawdown', 'current_drawdown']).\
                                                                        rename(columns={'id': 'product_id', 'start_date': 'perf_start_date', 'end_date': 'perf_end_date'})
            ie_product_perf_result.append(performance_data)
        performance_data = pd.concat(ie_product_perf_result)
    else:
        performance_data = basicAnal.basicAnal_calPerformanceStats(hf_warning_data['product_id'].tolist(), perf_start_date, perf_end_date, freq=freq,
                                    fund_type='HF', data_level='Product', stats=['annualized_period_return', 'max_drawdown', 'current_drawdown']).\
                                    rename(columns={'id': 'product_id', 'start_date': 'perf_start_date', 'end_date': 'perf_end_date'})

    hf_warning_data = pd.merge(hf_warning_data, performance_data, on='product_id', how='left')
    # 根据对每类策略设置的当前回撤监控阈值，进行筛选
    # 对于债券基金设置更细的监控阈值
    if label_level_1 in ['债券策略', '期货策略']:
        bond_hf_warning_data = []
        for label_level_2 in config.product_current_drawdown_monitor_config['label_level_1'][label_level_1].keys():
            bond_hf_warning_data.append(hf_warning_data[(hf_warning_data['label_level_2'] == label_level_2) & (hf_warning_data['current_drawdown'] <= config.product_current_drawdown_monitor_config['label_level_1'][label_level_1][label_level_2])])
        hf_warning_data = pd.concat(bond_hf_warning_data)
    elif label_level_1 in ['量化对冲']:
        bond_hf_warning_data = [
            hf_warning_data[(hf_warning_data['label_level_2'] == 'DMA') & (hf_warning_data['current_drawdown'] <= config.product_current_drawdown_monitor_config['label_level_1'][label_level_1]['DMA'])],
            hf_warning_data[(hf_warning_data['label_level_2'] != 'DMA') & (hf_warning_data['current_drawdown'] <= config.product_current_drawdown_monitor_config['label_level_1'][label_level_1]['其他'])],
        ]
        hf_warning_data = pd.concat(bond_hf_warning_data)
    elif label_level_1 in ['套利策略']:
        bond_hf_warning_data = [
            hf_warning_data[(hf_warning_data['label_level_2'] == '可转债套利') & (hf_warning_data['current_drawdown'] <= config.product_current_drawdown_monitor_config['label_level_1'][label_level_1]['可转债套利'])],
            hf_warning_data[(hf_warning_data['label_level_2'] != '可转债套利') & (hf_warning_data['current_drawdown'] <= config.product_current_drawdown_monitor_config['label_level_1'][label_level_1]['其他'])],
        ]
        hf_warning_data = pd.concat(bond_hf_warning_data)
    else:
        hf_warning_data = hf_warning_data[hf_warning_data['current_drawdown'] <= config.product_current_drawdown_monitor_config['label_level_1'][label_level_1]]
    # 整理结果
    hf_warning_data = hf_warning_data[['nav_date', 'product_id', 'product_short_name', 'company_short_name', 'strategy_name',
                                       'label_level_1', 'label_level_2', 'perf_start_date', 'perf_end_date', 'unit_value', 'annualized_period_return', 'max_drawdown', 'current_drawdown']]
    hf_warning_data['label_level_1'] = hf_warning_data['label_level_1'].apply(lambda x: '指数增强(超额)' if x == '指数增强' else x)
    hf_warning_data = hf_warning_data.sort_values(['label_level_1', 'label_level_2', 'nav_date', 'current_drawdown'])
    return hf_warning_data

# -----------------------------------------------------------------------
# 监控已投产品的收益表现，并根据产品类别新增基准、基差贡献等额外信息行
# -----------------------------------------------------------------------
def mntrAnls_HFDaliyReturn(
        hf_strategy,  # 预设策略类型 ['主观多头', '量化对冲', '套利策略', '期货策略', '债券策略', '300指增', '500指增','1000指增'
        date=datetime.datetime.today().date()-datetime.timedelta(days=7),
):
    assert hf_strategy in ['主观多头', '量化对冲', '套利策略', '期货策略', '债券策略', '可转债多头', '300指增', '500指增', '800指增', '1000指增及量化选股'], "目前仅支持['主观多头', '量化对冲', '套利策略', '期货策略', '债券策略', '可转债多头', '300指增', '500指增', '800指增', '1000指增及量化选股']"
    assert type(date) == datetime.date, "日期输入格式需为datetime.date"
    #  从config获取策略固定参数
    hf_strategy_config=config.hf_return_monitor_config[hf_strategy]
    addtional_row=hf_strategy_config['addtional_row']
    benchmark_id=hf_strategy_config['benchmark_id']
    excess_return=hf_strategy_config['excess_return']
    # 获取统计区间
    start_date = date
    end_date = date
    # 获取统计产品代码
    level_info = custHF.custHF_getProductInfo(['在库已投'], strategy_level_1=hf_strategy_config['level_1'], strategy_level_2=hf_strategy_config['level_2'])
    ids = level_info['product_id'].to_list()
    performance_data = basicAnal.basicAnal_calPerformanceStats(ids, start_date, end_date, 'D', "HF", benchmark_id=benchmark_id if excess_return else None, data_level='Product',stats=['period_return'])
    id_to_name = level_info.set_index('product_id')['product_short_name'].to_dict()
    performance_data['level_name'] = performance_data['id'].apply(lambda x: id_to_name[x])
    performance_data.sort_values(by='period_return', ascending=False, inplace=True)
    if addtional_row == 'BASIS':
        # 采用主力合约结算价计算期货收益率，基差贡献=区间指数收益率-期货收益率
        index = performance_data.index.tolist()
        contract_mapping_300 = idxFutureAnls.idxFutureAnls_getDailyContinuousContractMapping("IF", end_date)
        basis_300 = basicAnal.basicAnal_calPerformanceStats(['000300.SH'], start_date=start_date, end_date=end_date,freq='D',fund_type='BM')['period_return'] - \
                    basicAnal.basicAnal_calPerformanceStats([contract_mapping_300['IF.CFE']], start_date=start_date, end_date=end_date, freq='D',fund_type='BM')['period_return']
        contract_mapping_500 = idxFutureAnls.idxFutureAnls_getDailyContinuousContractMapping("IC", end_date)
        basis_500 = basicAnal.basicAnal_calPerformanceStats(['000905.SH'], start_date=start_date, end_date=end_date,freq='D',fund_type='BM')['period_return'] - \
                    basicAnal.basicAnal_calPerformanceStats([contract_mapping_500['IC.CFE']], start_date=start_date, end_date=end_date, freq='D',fund_type='BM')['period_return']
        contract_mapping_1000 = idxFutureAnls.idxFutureAnls_getDailyContinuousContractMapping("IM", end_date)
        basis_1000 = basicAnal.basicAnal_calPerformanceStats(['000852.SH'], start_date=start_date, end_date=end_date,freq='D',fund_type='BM')['period_return'] - \
                    basicAnal.basicAnal_calPerformanceStats([contract_mapping_1000['IM.CFE']], start_date=start_date, end_date=end_date, freq='D',fund_type='BM')['period_return']
        performance_data.loc['basis_300'] = {'period_return': basis_300.iloc[0], 'start_date': start_date, 'end_date': end_date, 'level_name': '300基差贡献(%s)' % (contract_mapping_300['IF.CFE'].split('.')[0])}
        performance_data.loc['basis_500'] = {'period_return': basis_500.iloc[0], 'start_date': start_date, 'end_date': end_date, 'level_name': '500基差贡献(%s)' % (contract_mapping_500['IC.CFE'].split('.')[0])}
        performance_data.loc['basis_1000'] = {'period_return': basis_1000.iloc[0], 'start_date': start_date, 'end_date': end_date, 'level_name': '1000基差贡献(%s)' % (contract_mapping_1000['IM.CFE'].split('.')[0])}
        # 使用新的索引顺序重新索引DataFrame，将新加入的行排在最前
        performance_data = performance_data.reindex(['basis_300', 'basis_500', 'basis_1000'] + index)
    elif addtional_row == 'BM':
        assert benchmark_id in ('000300.SH', '000905.SH', '000906.SH', '000852.SH', '885001.WI', '885008.CUSTOMIZED', 'CAMO2.WI'), "目前仅支持000300.SH, 000905.SH, 000906.SH, 000852.SH, 885001.WI, 885008.CUSTOMIZED, CAMO2.WI"
        benchmark_name = benchmark_id
        index = performance_data.index.tolist()
        if hf_strategy == '债券策略':
            benchmark_return = basicAnal.basicAnal_calPerformanceStats([benchmark_id], start_date=start_date, end_date=end_date, freq='D', fund_type='CUSTOMIZED_BM')['period_return']
            benchmark_name = '定制中长期纯债型基金指数'
        elif hf_strategy == '期货策略':
            benchmark_return = basicAnal.basicAnal_calPerformanceStats([benchmark_id], start_date=start_date, end_date=end_date, freq='D', fund_type='BM')['period_return']
            benchmark_name = 'CAMO2'
        else:
            benchmark_return = basicAnal.basicAnal_calPerformanceStats([benchmark_id], start_date=start_date, end_date=end_date, freq='D', fund_type='BM')['period_return']

        performance_data.loc['benchmark'] = {'period_return': benchmark_return.iloc[0], 'start_date': start_date,
                                             'end_date': end_date, 'level_name': '基准  ' + benchmark_name + '  绝对收益'}
        # 使用新的索引顺序重新索引DataFrame，将新加入的行排在最前
        performance_data = performance_data.reindex(['benchmark'] + index)
        if excess_return:
            performance_data.rename(columns={'period_return': 'period_return_excess'}, inplace=True)

    return performance_data

# ------------------------------------------------------------------
# 监控账户持有私募策略的规模是否达到策略上限的90%
# ------------------------------------------------------------------
def mntrAnls_HFStrategyLimitWarning(
    date,   # 考察日期，取该日期的持仓进行分析
    include_advisory=False  # 是否考虑投顾账户
):
    hf_product_info = custHF.custHF_getProductInfo()
    mf_product_info = custMF.custMF_getMFProductInfo()
    product_info = pd.concat([hf_product_info, mf_product_info], axis=0)
    # 对于监控补充项limit字段填充为0，保证在监控结果中始终展示
    # 公募产品product_info中不包含limit字段，因此对于补充项中的产品limit会填为0，未填充的会在结果汇总时过滤掉
    product_info.loc[product_info['company_id'].isin(monitor_config.holding_limit_monitor_result_supplements.keys()), 'limit'] = 0

    holding_data = custFOF.custFOF_getFOFHoldingData(date, date)
    if include_advisory is False:
        # 获取账户数据，不包含投顾账户
        account_info = custFOF.custFOF_getFOFReferenceData(include_advisory_account=False)
        # 保留非投顾账户持仓数据
        holding_data = holding_data[holding_data['portfolio_id'].isin(account_info['portfolio_id'].to_list())]
    holding_data = pd.merge(holding_data, product_info[['product_id', 'strategy_id', 'strategy_name', 'limit']], how='left', on='product_id')
    monitor_result = holding_data.groupby(['strategy_id', 'strategy_name'], as_index=False).agg({'product_NAV': 'sum', 'limit': 'last'})
    monitor_result.rename(columns={'product_NAV': 'strategy_NAV'}, inplace=True)
    monitor_result['limit'] *= 1e8
    monitor_result['90%limit'] = monitor_result['limit'] * 0.9
    monitor_result = monitor_result[monitor_result['strategy_NAV'] > monitor_result['90%limit']]

    return monitor_result

# -----------------------------------------
# 监控账户持有私募策略的规模是否达到管理人上限的90%，周度执行
# -----------------------------------------
def mntrAnls_getHFCompanyLimitWarning(
    date  # 考察日期
):
    hf_company_info = custHF.custHF_getCompanyInfo()
    mf_company_info = custMF.custMF_getMFCompanyInfo()
    company_info = pd.concat([hf_company_info, mf_company_info], axis=0)[['company_id', 'company_aum']]
    current_company_holding_info = portAnls.anlsFOF_getCurrentHoldingInfo(date=date, data_level='Company')[['company_id', 'company_name', 'total_NAV']]
    result = pd.merge(company_info[['company_id', 'company_aum']], current_company_holding_info, on='company_id', how='inner')
    # 根据协会备案规模进行筛选，仅针对私募
    result['limit'] = result['company_aum'].apply(lambda x: config.hf_company_total_holding_limit_mapping[x] if x in config.hf_company_total_holding_limit_mapping.keys() else None)
    # 对于监控补充项limit字段填充为0，保证在监控结果中始终展示，对补充项中的公募/私募均生效
    result.loc[result['company_id'].isin(monitor_config.holding_limit_monitor_result_supplements.keys()), 'limit'] = 0
    result['warning_limit'] = 0.9*result['limit']
    result = result[(result['total_NAV'] >= result['warning_limit']) & ~(result['company_id'].isin(['C0000101', 'C0001001']))].sort_values('total_NAV', ascending=False)  # 筛去公司后端和中诚信(协会数据不适配目前投资情况) 超过阈值90%时开始提醒
    return result

# ------------------------------------------------------------------
# 私享账户权益持仓分布每周监控并与上周/上月对比
# 包括按照投资经理的汇总以及总体情况
# 起止日期是指需要平均计算的时间区间，目前常见的使用场景是计算近30日的平均持仓
# ------------------------------------------------------------------
def mntrAnls_SXAccountEquityStrategyPropotion(
    start_date,
    end_date,
):
    sx_account = custFOF.custFOF_getSXAccountList(end_date)
    sx_account = sx_account[~sx_account['level_3_type'].str.contains('臻选')]
    sx_account = sx_account[sx_account['pm_name'].isin(const.const.SIXIANG_PM_LIST)]
    holding = custFOF.custFOF_getFOFHoldingData(start_date, end_date, sx_account['portfolio_id'].tolist())
    holding = portAnls._append_product_label_info(holding, include_company_strategy_info=True)
    holding = holding[holding['allocation_type']=='权益']
    holding['label_level_1'] = holding['label_level_1'].apply(lambda x: '主观权益' if x == '行业主题' else x)
    holding = pd.merge(sx_account, holding, on='portfolio_id', how='left')
    allocation_type_sum = holding.groupby(['pm_name', 'allocation_type'], as_index=False)['product_NAV'].sum()
    label_level_1_sum = holding.groupby(['pm_name', 'label_level_1'], as_index=False)['product_NAV'].sum()
    label_level_2_sum = holding.groupby(['pm_name', 'label_level_2'], as_index=False)['product_NAV'].sum()
    allocation_type_sum = allocation_type_sum.pivot(index='allocation_type', columns='pm_name', values='product_NAV').reset_index().rename(columns={'allocation_type': 'equity_type'})
    label_level_1_sum = label_level_1_sum.pivot(index='label_level_1', columns='pm_name', values='product_NAV').reset_index().rename(columns={'label_level_1': 'equity_type'})
    label_level_2_sum = label_level_2_sum.pivot(index='label_level_2', columns='pm_name', values='product_NAV').reset_index().rename(columns={'label_level_2': 'equity_type'})
    label_level_2_sum = label_level_2_sum[label_level_2_sum['equity_type'].isin(['300指增', '500指增', '800指增', '1000指增', '量化选股'])]
    label_level_2_sort_map = {'300指增': 0, '500指增': 1, '800指增': 2, '1000指增': 3, '量化选股': 4}
    label_level_2_sum['label_level_2_sort'] = label_level_2_sum['equity_type'].apply(lambda x: label_level_2_sort_map.get(x, 5))
    label_level_2_sum.sort_values('label_level_2_sort', inplace=True)
    del label_level_2_sum['label_level_2_sort']
    equity_holding_sum = pd.concat([allocation_type_sum, label_level_1_sum, label_level_2_sum]).fillna(0).reset_index(drop=True)
    equity_holding_sum['总计'] = equity_holding_sum[const.const.SIXIANG_PM_LIST].sum(axis=1)
    equity_holding_first_row = equity_holding_sum.iloc[0]
    equity_holding_weight = equity_holding_sum.copy(deep=True)
    equity_holding_weight[const.const.SIXIANG_PM_LIST + ['总计']] = equity_holding_sum[const.const.SIXIANG_PM_LIST + ['总计']].div(equity_holding_first_row[const.const.SIXIANG_PM_LIST + ['总计']])
    equity_holding_weight = equity_holding_weight[equity_holding_weight['equity_type'] != '权益']

    return equity_holding_weight


# ------------------------------------------------------------------
# 私享账户权益持仓分布(时点值或者多日平均的结果)与上周/上月对比
# 包括按照投资经理的汇总以及总体情况
# 需输入两组起止日期是指需要平均计算的时间区间，目前常见的使用场景是计算近30日的平均持仓
# ------------------------------------------------------------------
def mntrAnls_SXAccountEquityStrategyPropotionChg(
    w1_start_date,  # 上一周的数据的起始日期
    w1_end_date,
    w2_start_date,  # 新一周的数据的起始日期
    w2_end_date,
):
    w1_equity_holding_weight = mntrAnls_SXAccountEquityStrategyPropotion(w1_start_date, w1_end_date)
    w2_equity_holding_weight = mntrAnls_SXAccountEquityStrategyPropotion(w2_start_date, w2_end_date)
    equity_holding_weight_chg = w2_equity_holding_weight.copy(deep=True)
    equity_holding_weight_chg[const.const.SIXIANG_PM_LIST + ['总计']] = w2_equity_holding_weight[const.const.SIXIANG_PM_LIST + ['总计']].sub(w1_equity_holding_weight[const.const.SIXIANG_PM_LIST + ['总计']])

    return equity_holding_weight_chg

# ------------------------------------------------------------------
# 股指期货合约基差走势监控
# 选取当月(00), 次月(01), 当季(02)合约, 展示基差水平变化情况
# ------------------------------------------------------------------
def mntrAnls_StockIndexFuturesBasisLevel(
    futures_id,      # 股指期货合约代码 需在('IF', 'IC', 'IM', 'IH')中
    start_date,       # 起始日期
    end_date         # 截止日期
):
    assert futures_id in ['IF', 'IC', 'IM', 'IH'], "futures_id('IF','IC','IM','IH')"
    assert isinstance(start_date, datetime.date), "start_date输入类型需为datetime.date"
    assert isinstance(end_date, datetime.date), "end_date输入类型需为datetime.date"
    assert end_date <= datetime.date.today(), "不可使用未来日期"

    benchmark_index_id = const.const.STOCK_INDEX_FUTURES_BM_MAP[futures_id]['index_id']
    # 根据end_date的合约映射表挑选当月/次月/当季合约
    contract_mapping = idxFutureAnls.idxFutureAnls_getDailyContinuousContractMapping(futures_id, end_date)
    assert len(contract_mapping.keys()), "无数据: %s 股指期货合约映射表为空(CfuturesContractMapping)" % end_date
    mapping_futures_ids = [contract_mapping[key] for key in [futures_id + postfix for postfix in ['00.CFE', '01.CFE', '02.CFE', '03.CFE']]]
    futures_data = wd.wind_getStockIndexFutureData(futures_id, start_date, end_date)[['date', 'contract_id', 'settle_price', 'delist_date', 'ttm']]
    futures_data = futures_data.loc[futures_data['contract_id'].isin(mapping_futures_ids)]
    # 交易日口径
    wind_calendar = wind.wind_getSSECalendar()
    futures_data['ttm_tradedays'] = [len(wind_calendar[(wind_calendar['date'] >= begin) & (wind_calendar['date'] <= end)]) \
                                     for (begin, end) in zip(futures_data['date'], futures_data['delist_date'])]
    # 计算不同到期日期的剩余分红点位，同时merge上指数实际点位
    benchmark_dividend_adjustment_data = idxFutureAnls.idxFutureAnls_getIndexDividendAdjustmentSeries(index_id=benchmark_index_id, start_date=start_date, end_date=end_date, contract_delist_dates=futures_data['delist_date'].unique().tolist())
    futures_data = pd.merge(futures_data, benchmark_dividend_adjustment_data, on=['date', 'delist_date'], how='left')
    futures_data['px_diff'] = futures_data['settle_price'] - futures_data['benchmark_close']
    futures_data['adj_px_diff'] = futures_data['settle_price'] - futures_data['benchmark_close'] + futures_data['adjustment_points']
    futures_data['annualized_basis_return'] = ((1 + (futures_data['settle_price'] - futures_data['benchmark_close']) / futures_data['benchmark_close']) ** (const.const.ANNUAL_SCALE / (futures_data['ttm_tradedays'])) - 1)
    futures_data['dividend_adj_annualized_basis_return'] = ((1 + (futures_data['settle_price'] - futures_data['benchmark_close'] + futures_data['adjustment_points']) / futures_data['benchmark_close']) ** (const.const.ANNUAL_SCALE / (futures_data['ttm_tradedays'])) - 1)
    result = futures_data[['date', 'contract_id', 'settle_price', 'benchmark_close', 'adjustment_points', 'settled_adjustment_points',
                           'div_amount_settled_adjustment_points', 'non_settled_adjustment_points', 'px_diff', 'adj_px_diff', 'annualized_basis_return',
                           'dividend_adj_annualized_basis_return', 'ttm', 'ttm_tradedays', 'delist_date']]
    return result

# ------------------------------------------------------------------
# 股指期货基差贡献监控
# 每交易日日终和基差走势一起展示
# ------------------------------------------------------------------
def mntrAnls_StockIndexFuturesBasisContribution(
    date,            # 考察日期
    futures_id_list=['IF', 'IC', 'IM', 'IH']  # 输入类型为list, 沪深300, 中证500, 中证1000, 上证50
):
    assert isinstance(futures_id_list, list), "futures_id_list输入类型需为list"
    assert isinstance(date, datetime.date), "start_date输入类型需为datetime.date"
    assert date <= datetime.date.today(), "不可使用未来日期"
    result = pd.DataFrame()
    for futures_id in futures_id_list:
        benchmark_index_id = const.const.STOCK_INDEX_FUTURES_BM_MAP[futures_id]['index_id']
        benchmark_index_name = const.const.STOCK_INDEX_FUTURES_BM_MAP[futures_id]['index_name']
        contract_mapping = idxFutureAnls.idxFutureAnls_getDailyContinuousContractMapping(futures_id, date)
        assert len(contract_mapping.keys()), "无数据: %s 股指期货合约映射表为空(CfuturesContractMapping)" % date
        for postfix in ['00.CFE', '01.CFE', '02.CFE', '03.CFE']:
            contract_id = contract_mapping[futures_id+postfix]
            basis_contribution = basicAnal.basicAnal_calPerformanceStats([benchmark_index_id], start_date=date, end_date=date,freq='D',fund_type='BM')['period_return'] - \
                basicAnal.basicAnal_calPerformanceStats([contract_id], start_date=date, end_date=date, freq='D',fund_type='BM')['period_return']
            result.loc['%s(%s)' % (benchmark_index_name, futures_id), contract_id.split('.')[0][2:]] = basis_contribution.iloc[0]
    return result

# ------------------------------------------------------------------
# FOF账户近1年内持仓过的公募基金的基金经理变动情况
# ------------------------------------------------------------------
def mntrAnls_getMFManagerAdjustment(
    start_date,  # 起始日期
    end_date,    # 截止日期
):
    assert isinstance(start_date, datetime.date), "start_date输入类型需为datetime.date"
    assert isinstance(end_date, datetime.date), "end_date输入类型需为datetime.date"
    mf_product_info = wind.wind_getHistoricalProductList(include_pm_info=True)[['product_id', 'product_name', 'company_short_name', 'pm_id', 'pm_name', 'pm_start_date', 'pm_end_date']].drop_duplicates()  # 避免因基金类型变动产生的重复行
    hist_holding_product = custFOF.custFOF_getFOFHistoricalHoldingProduct(end_date-datetime.timedelta(days=365), end_date, include_holding_dates=False)
    hist_holding_product = pd.merge(hist_holding_product, wind.wind_getMFtype()[['product_id', 'type_name_lv1', 'type_name_lv2']], on='product_id', how='left')
    hist_holding_product = hist_holding_product[~(hist_holding_product['type_name_lv1'].isin(['货币市场型基金'])) & ~(hist_holding_product['type_name_lv2'].isin(['被动指数型基金', '被动指数型债券基金']))]
    mf_product_info = mf_product_info[mf_product_info['product_id'].isin(hist_holding_product['product_id'].to_list())]  # 筛选有持仓的产品
    # 新任/离任基金经理
    new_pm_product_info = mf_product_info.copy(deep=True)[(mf_product_info['pm_start_date'] >= start_date) & (mf_product_info['pm_start_date'] <= end_date)]
    new_pm_product_info['adjustment_type'] = '新任'
    new_pm_product_info['adjustment_date'] = new_pm_product_info['pm_start_date']
    left_pm_product_info = mf_product_info.copy(deep=True)[(mf_product_info['pm_end_date'] >= start_date) & (mf_product_info['pm_end_date'] <= end_date)]
    left_pm_product_info['adjustment_type'] = '离任'
    left_pm_product_info['adjustment_date'] = left_pm_product_info['pm_end_date']
    # end_date当日现任基金经理，新任和离任发布公告当日即生效
    product_current_pm = mf_product_info[(mf_product_info['pm_start_date']<=end_date) & (mf_product_info['pm_end_date'].isna() | (mf_product_info['pm_end_date']>end_date))].groupby(['product_id'], as_index=False).agg({'pm_name': lambda x: ','.join(x.to_list())})
    product_current_pm.rename(columns={'pm_name': 'current_pm'}, inplace=True)
    result = pd.concat([new_pm_product_info, left_pm_product_info], axis=0)
    result = pd.merge(result, product_current_pm, on=['product_id'], how='left')
    result = result[['adjustment_date', 'product_id', 'product_name', 'company_short_name', 'pm_name', 'adjustment_type', 'current_pm']].sort_values(['adjustment_type', 'adjustment_date'])
    result.reset_index(drop=True, inplace=True)
    result.rename(columns={
        'adjustment_date': '变动日期',
        'product_id': '产品ID',
        'product_name': '产品名称',
        'company_short_name': '管理人',
        'pm_name': '变动基金经理',
        'adjustment_type': '变动类型',
        'current_pm': '现任基金经理'
    }, inplace=True)
    return result

# ------------------------------------------------------------------
# 股票型ETF净申赎份额规模
# ------------------------------------------------------------------
def mntrAnls_getETFMarketLiquidShareNetChg(
    date,            # 考察日期
    tracked_days     # 跟踪天数
):
    assert isinstance(date, datetime.date), "date输入类型需为datetime.date"
    wind_calendar = wind.wind_getSSECalendar()
    start_date = wind_calendar[wind_calendar['date'] <= date]['date'].iloc[-tracked_days-2]  # 因深交所与上交所ETF份额公布时间有差异，需取至当日信息再作调整，此处向前多取两天用于计算份额变化
    mf_share_info = wind.wind_getMFShareInfo(latest_only=False, start_date=start_date, end_date=date)[['date', 'product_id', 'product_name', 'product_liquid_share', 'share_chg_reason']]
    mf_share_info['product_liquid_share'] /= 1e4  # 单位调整为亿份
    # 使用ETF一级投资类型信息对ETF产品进行筛选(股票型ETF可能会有重复的子分类标签)，仅保留股票型ETF
    etf_invest_type_data_level_1 = wind.wind_getETFInvestType(invest_type_level='level_1')
    equity_etf_share_info = pd.merge(mf_share_info, etf_invest_type_data_level_1, on='product_id', how='left')
    equity_etf_share_info = equity_etf_share_info[equity_etf_share_info['etf_invest_type_id_level_1'] == '1000009165000000']
    # ETF t-1日流通规模估算 1.上交所ETF: t-1日盘后流通份额 * t-1日单位净值  2.深交所ETF: t日盘前流通份额 * t-1日单位净值
    # 由于上交所披露ETF盘后份额，深交所披露ETF盘前份额，数据标记日期相差一天，需单独处理，统一标记为上交所盘后份额的日期
    # t-1日净申赎引起的规模变化=t-1日净申赎份额变化*t-1日基金净值
    sh_equity_etf_share_info = equity_etf_share_info[equity_etf_share_info['product_id'].str.endswith('.SH')].sort_values(['product_id', 'date']).copy()
    sh_equity_etf_share_info['exchange_market'] = 'SH'
    sz_equity_etf_share_info = equity_etf_share_info[equity_etf_share_info['product_id'].str.endswith('.SZ')].sort_values(['product_id', 'date']).copy()
    assert sz_equity_etf_share_info['date'].max() == date, f"深交所暂未发布{date}ETF盘前份额，请在数据发布后运行(深交所每日9:00前发布ETF盘前份额)"
    sz_equity_etf_share_info['date'] = sz_equity_etf_share_info.groupby(['product_id'])['date'].shift(1)  # 调整深交所份额日期
    sz_equity_etf_share_info['exchange_market'] = 'SZ'
    equity_etf_share_info = pd.concat([sh_equity_etf_share_info, sz_equity_etf_share_info.dropna()], axis=0)  # dropna去除日期为空的行
    equity_etf_share_info = equity_etf_share_info[equity_etf_share_info['date'] != date].sort_values(['product_id', 'date'])  # 剔除最新日期，相当于考察区间为[date-tracked_days-2, date-1]

    # 获取基金份额拆分信息
    equity_etf_share_split_info = wind.wind_getMFShareSplitInfo(start_date, date)
    equity_etf_share_split_info = equity_etf_share_split_info[equity_etf_share_split_info['product_id'].isin(equity_etf_share_info['product_id'].to_list())]
    equity_etf_share_info = pd.merge(equity_etf_share_info, equity_etf_share_split_info[['date', 'product_id', 'share_split_conversion_ratio']], on=['date', 'product_id'], how='left')
    equity_etf_share_info['share_split_flag'] = equity_etf_share_info['share_split_conversion_ratio'].apply(lambda x: False if pd.isna(x) else True)
    equity_etf_share_info['pre_adjusted_product_liquid_share'] = equity_etf_share_info.groupby(['product_id'])['product_liquid_share'].shift(1) * equity_etf_share_info['share_split_conversion_ratio']

    # 获取单位净值，反映ETF总净资产规模
    equity_etf_nav = wind.wind_getMFNav(start_date, date, product_id=equity_etf_share_info['product_id'].to_list())[['date', 'product_id', 'nav_unit']]
    equity_etf_share_info = pd.merge(equity_etf_share_info, equity_etf_nav, on=['date', 'product_id'], how='left')
    equity_etf_share_info['product_liquid_share_diff'] = equity_etf_share_info.groupby(['product_id'])['product_liquid_share'].transform('diff')
    # 对份额拆分当日的份额变动数量进行调整，份额变动=当日份额-上一日折算后份额
    equity_etf_share_info.loc[equity_etf_share_info['share_split_flag'], 'product_liquid_share_diff'] = equity_etf_share_info.loc[equity_etf_share_info['share_split_flag'], 'product_liquid_share'] \
                                                                                                        - equity_etf_share_info.loc[equity_etf_share_info['share_split_flag'], 'pre_adjusted_product_liquid_share']
    del equity_etf_share_info['share_split_conversion_ratio'], equity_etf_share_info['pre_adjusted_product_liquid_share']
    equity_etf_share_info['liquid_total_nav_diff'] = equity_etf_share_info['product_liquid_share_diff'] * equity_etf_share_info['nav_unit']
    equity_etf_share_info = equity_etf_share_info.dropna()  # drop掉首日nan值
    total_result = equity_etf_share_info.groupby(['date'], as_index=False).agg({'product_liquid_share_diff': 'sum', 'liquid_total_nav_diff': 'sum'})

    # 使用细分的二级标签进行分类，用于区分规模ETF与行业主题ETF
    etf_invest_type_data_level_2 = wind.wind_getETFInvestType(invest_type_level='level_2')[['product_id', 'etf_invest_type_id_level_2']]
    equity_etf_share_info = pd.merge(equity_etf_share_info, etf_invest_type_data_level_2, on='product_id', how='left')
    # 当前监控场景下，仅保留最后一日的变化结果用于展示
    equity_etf_share_info = equity_etf_share_info[equity_etf_share_info['date'] == equity_etf_share_info['date'].max()]
    broad_based_share_info = equity_etf_share_info[equity_etf_share_info['etf_invest_type_id_level_2'] == '1000009712000000']  # 规模指数
    other_share_info = equity_etf_share_info[equity_etf_share_info['etf_invest_type_id_level_2'] != '1000009712000000']  # 主题行业策略风格指数
    broad_based_bm_result = broad_based_share_info.groupby(['date', 'benchmark_id', 'benchmark_name'], as_index=False).agg(
        {'product_liquid_share_diff': 'sum', 'liquid_total_nav_diff': 'sum'}).sort_values(['date', 'liquid_total_nav_diff'], ascending=[True, False])
    other_bm_result = other_share_info.groupby(['date', 'benchmark_id', 'benchmark_name'], as_index=False).agg(
        {'product_liquid_share_diff': 'sum', 'liquid_total_nav_diff': 'sum'}).sort_values(['date', 'liquid_total_nav_diff'], ascending=[True, False])
    return {'total': total_result, 'broad_based': broad_based_bm_result, 'other': other_bm_result, 'share_split_info': equity_etf_share_split_info[equity_etf_share_split_info['date'] == equity_etf_share_info['date'].max()]}

# ------------------------------------------------------------------
# 私募估值表风险筛查监控1 风险筛查大表
# 重点关注场外衍生品/嵌套/债券/新三板/北交所投资等情况
# ------------------------------------------------------------------
def mntrAnls_HFValuationSheetAnlsTable(
    current_holding_date,         # 最新持仓考察日期
    valuation_sheet_start_date,   # 估值表回看开始日期
    valuation_sheet_end_date   # 估值表回看截止日期
):
    assert isinstance(current_holding_date, datetime.date), "current_holding_date输入类型需为datetime.date"
    assert isinstance(valuation_sheet_start_date, datetime.date), "valuation_sheet_start_date输入类型需为datetime.date"
    assert isinstance(valuation_sheet_end_date, datetime.date), "valuation_sheet_end_date输入类型需为datetime.date"
    # 最新产品持仓信息
    product_holding_info = portAnls.anlsFOF_getCurrentHoldingInfo(current_holding_date, data_level='Product')
    # 筛选私募基金持仓，剔除债券策略和后端产品
    product_holding_info = product_holding_info[(product_holding_info['product_type'] == '私募基金') & (~product_holding_info['label_level_1'].isin(['债券策略', '货币基金']))]
    product_holding_info = product_holding_info[product_holding_info['product_id'].apply(lambda x: True if x[:2] not in ('70', '90') else False)]
    product_holding_info = product_holding_info[['product_id', 'total_NAV']].rename(columns={'total_NAV': 'product_total_holding_NAV'})
    hf_product_info = custHF.custHF_getProductInfo()
    product_info_cols = ['company_id', 'company_short_name', 'strategy_name', 'product_id', 'product_short_name', 'trustee', 'primary_coverage']
    result = pd.merge(product_holding_info, hf_product_info[product_info_cols], how='left', on='product_id')
    company_nav = result.groupby(['company_id'], as_index=False).agg({'product_total_holding_NAV': 'sum'}).rename(columns={'product_total_holding_NAV': 'company_total_holding_NAV'})
    result = pd.merge(result, company_nav, how='left', on='company_id')
    result['is_citics_trustee'] = result['trustee'].fillna("无").apply(lambda x: '是' if '中信证券' in x else None)
    result['is_citics_customized'] = None
    # 估值表筛查区间
    result['interval_start_date'] = valuation_sheet_start_date
    result['interval_end_date'] = valuation_sheet_end_date
    # 估值表区间最新日期 历史最新日期
    product_history_valuation_sheet = custHF.custHF_getProductInfoFromValuationSheet(datetime.date(2010, 1, 1), valuation_sheet_end_date, product_ids=result['product_id'].unique().tolist(), include_subject_details=False)
    result = pd.merge(result, product_history_valuation_sheet[product_history_valuation_sheet['date'] >= valuation_sheet_start_date].groupby(['product_id']).agg({'date': 'max'}).rename(columns={'date': 'interval_latest_record'}), how='left', on='product_id')
    result = pd.merge(result, product_history_valuation_sheet.groupby(['product_id']).agg({'date': 'max'}).rename(columns={'date': 'hist_latest_record'}), how='left', on='product_id')
    # 风险科目筛查 按二级科目口径统计规模
    subject_cols = []
    for invest_type in config.valuation_sheet_risk_scan_subject_monitor_config.keys():
        subject_col_name = config.valuation_sheet_risk_scan_subject_monitor_config[invest_type]['col_name']
        subject_id_like_op = config.valuation_sheet_risk_scan_subject_monitor_config[invest_type]['subject_ids']
        # 仅统计估值表二级科目(先取二级估值表，再限制仅统计二级科目(new_subject_id长度为6)，即过滤一级科目)
        subject_id_like_product_info = custHF.custHF_getProductInfoFromValuationSheet(valuation_sheet_start_date, valuation_sheet_end_date, subject_id_starts_like=subject_id_like_op, valuation_level='二级', include_subject_details=True)
        subject_id_like_product_info = subject_id_like_product_info[subject_id_like_product_info['new_subject_id'].str.len() == 6]
        # 保留最新一期估值表中的内容(直接groupby取last会取到的是该科目的最后一条记录，并不一定是该产品的最新记录)
        subject_id_like_product_info = pd.merge(subject_id_like_product_info, result[['product_id', 'interval_latest_record']], left_on=['product_id', 'date'], right_on=['product_id', 'interval_latest_record'], how='inner')
        if invest_type == '北交所投资':  # 北交所投资使用科目名称筛选
            subject_id_like_product_info = subject_id_like_product_info[subject_id_like_product_info['subject_name'].str.contains('北交所')]
        if invest_type == '债券投资':  # 过滤可转债多头产品的债券投资检查
            cvrt_bond_products = hf_product_info[(hf_product_info['label_level_1'] == '可转债多头') | (hf_product_info['label_level_2'] == '可转债套利')]['product_id'].to_list()
            subject_id_like_product_info = subject_id_like_product_info[~subject_id_like_product_info['product_id'].isin(cvrt_bond_products)]
        # 对属于该风险类别的估值表科目净值(市值)求和
        valuation_sheet_subject_NAV = subject_id_like_product_info.groupby(['product_id'], as_index=False).agg({'subject_NAV': 'sum'}).rename(columns={'subject_NAV': subject_col_name + '_NAV'})
        valuation_sheet_subject_weight = subject_id_like_product_info.groupby(['product_id'], as_index=False).agg({'subject_weight': 'sum'}).rename(columns={'subject_weight': subject_col_name + '_权重'})
        result[subject_col_name] = result['product_id'].isin(valuation_sheet_subject_NAV['product_id'].to_list()).apply(lambda x: '是' if x else None)
        result = pd.merge(result, valuation_sheet_subject_NAV, on='product_id', how='left')
        result = pd.merge(result, valuation_sheet_subject_weight, on='product_id', how='left')
        subject_cols.append(subject_col_name)
        subject_cols.append(subject_col_name + '_NAV')
        subject_cols.append(subject_col_name + '_权重')
    # 二级估值表产品(包含披露二级及以上估值表产品)
    level2_valuation_products = custHF.custHF_getProductInfoFromValuationSheet(valuation_sheet_start_date, valuation_sheet_end_date, valuation_level='二级')['product_id'].unique().tolist()
    result['level2_valuation'] = result['product_id'].isin(level2_valuation_products).apply(lambda x: '是' if x else None)
    # 四级估值表产品(包含披露四级及以上估值表产品)
    level4_valuation_products = custHF.custHF_getProductInfoFromValuationSheet(valuation_sheet_start_date, valuation_sheet_end_date, valuation_level='四级')['product_id'].unique().tolist()
    result['level4_valuation'] = result['product_id'].isin(level4_valuation_products).apply(lambda x: '是' if x else None)
    # 估值表资产净值(市值)
    product_valuation_NAV = custHF.custHF_getProductInfoFromValuationSheet(valuation_sheet_start_date, valuation_sheet_end_date, subject_id_like='资产净值', include_subject_details=True).sort_values(['product_id', 'date'])
    product_valuation_NAV = product_valuation_NAV[product_valuation_NAV['subject_id'].isin(['资产净值', '基金资产净值:'])]  # 由于各托管人名称不同，先使用'资产净值'进行模糊查询再指定筛选
    latest_product_valuation_NAV = product_valuation_NAV.groupby(['product_id'], as_index=False).last()[['product_id', 'subject_NAV', 'date']]
    # 估值表日期的产品持仓规模 (为保证运行效率，仅取一次数据，对于区间估值表日期loop执行best effort逻辑)
    hist_holding_data = custFOF.custFOF_getFOFHoldingData(latest_product_valuation_NAV['date'].min() - datetime.timedelta(days=45), latest_product_valuation_NAV['date'].max(), include_portfolio_oa_id=True)
    hist_best_effort_holding_data = []
    for interval_latest_record_date in latest_product_valuation_NAV['date'].unique().tolist():
        hist_holding_data_slice = hist_holding_data[(hist_holding_data['date'] >= interval_latest_record_date - datetime.timedelta(days=45)) & (hist_holding_data['date'] <= interval_latest_record_date)].sort_values(['portfolio_oa_id', 'date'])
        hist_holding_data_slice = pd.merge(hist_holding_data_slice, hist_holding_data_slice.groupby(['portfolio_oa_id'], as_index=False).agg({'date': 'last'}).rename(columns={'date': 'latest_holding_date'}), on='portfolio_oa_id', how='left')
        hist_holding_data_slice = hist_holding_data_slice[hist_holding_data_slice['date'] == hist_holding_data_slice['latest_holding_date']]
        single_date_best_effort_res = hist_holding_data_slice.groupby(['product_id'], as_index=False).agg({'product_NAV': 'sum'}).rename(columns={'product_NAV': 'product_contemporary_holding_NAV'})
        single_date_best_effort_res['date'] = interval_latest_record_date
        hist_best_effort_holding_data.append(single_date_best_effort_res)
    hist_best_effort_holding_data = pd.concat(hist_best_effort_holding_data, axis=0)
    latest_product_valuation_NAV = pd.merge(latest_product_valuation_NAV, hist_best_effort_holding_data, on=['date', 'product_id'], how='left')
    latest_product_valuation_NAV.rename(columns={'subject_NAV': 'product_valuation_NAV', 'date': 'latest_NAV_date'}, inplace=True)
    result = pd.merge(result, latest_product_valuation_NAV, left_on=['interval_latest_record', 'product_id'], right_on=['latest_NAV_date', 'product_id'], how='left')
    result['product_valuation_NAV_threshold'] = result['product_valuation_NAV'].apply(lambda x: '是' if x < 1e7 else None)
    result['product_contemporary_holding_ratio'] = result['product_contemporary_holding_NAV'] / result['product_valuation_NAV']
    # 筛查结果汇总
    result = result[['company_id', 'company_short_name', 'company_total_holding_NAV', 'strategy_name', 'product_id', 'product_short_name', 'product_total_holding_NAV', 'trustee', 'is_citics_trustee', 'is_citics_customized'] +
                    subject_cols + ['interval_start_date', 'interval_end_date', 'interval_latest_record', 'level2_valuation', 'level4_valuation', 'primary_coverage', 'product_valuation_NAV', 'product_valuation_NAV_threshold',
                                    'product_contemporary_holding_NAV', 'product_contemporary_holding_ratio', 'hist_latest_record']]
    result.sort_values(['company_id', 'product_id'], inplace=True)
    result.reset_index(inplace=True, drop=True)
    return result

# -------------------------------
# 公募核心库收益监控 - 模拟组合维度
# -------------------------------
def mntrAnls_MFCorePoolMockPortPerf(
    date,   # 考察日期
):
    assert isinstance(date, datetime.date), "date需为datetime.date类型"
    # 模拟组合维度
    mock_port_perf_res = {}
    # 对于核心库汇总统计类结果，只展示收益率统计
    ret_perf_stats = [ret_stat for ret_stat in monitor_config.mf_core_pool_ret_rank_perf_stats.keys() if 'rank_' not in ret_stat]
    for core_pool in monitor_config.mf_core_pool_config.keys():
        core_pool_benchmark = monitor_config.mf_core_pool_config[core_pool]['benchmark']
        core_pool_mock_port_perf_res = pd.DataFrame()
        # benchmark部分
        for benchmark_id, benchmark_name in core_pool_benchmark.items():
            benchmark_row_res = {'portfolio_id': benchmark_id, 'portfolio_name': benchmark_name}
            benchmark_ret_series = wind.wind_getIndexReturn(idx_code=benchmark_id, start_date=date - datetime.timedelta(days=366), end_date=date, freq='D')
            for ret_perf_col in ret_perf_stats:
                period = monitor_config.mf_core_pool_ret_rank_perf_stats[ret_perf_col]['period']
                period_start_date, period_end_date = calendar.calender_getStartEndDate(period, date)
                benchmark_row_res[ret_perf_col] = cal.basicCal_getPeriodReturn(benchmark_ret_series.loc[period_start_date:period_end_date], freq='D', annualized=False)
            core_pool_mock_port_perf_res = core_pool_mock_port_perf_res.append(benchmark_row_res, ignore_index=True)
        # 代表模拟组合部分
        represent_mock_port = monitor_config.mf_core_pool_config[core_pool]['represent_mock_port']
        mock_port_ret_data = custMF.custMF_getMockPortNetValueAndReturn(start_date=date - datetime.timedelta(days=366), end_date=date, mock_port_ids=list(represent_mock_port.values()), freq='D')
        for represent_mock_port_name, represent_mock_port_id in represent_mock_port.items():
            represent_row_res = {'portfolio_id': '模拟组合', 'portfolio_name': represent_mock_port_name}
            represent_mock_port_ret_series = mock_port_ret_data[mock_port_ret_data['portfolio_id'] == represent_mock_port_id].set_index('date')['return']
            for ret_perf_col in ret_perf_stats:
                period = monitor_config.mf_core_pool_ret_rank_perf_stats[ret_perf_col]['period']
                period_start_date, period_end_date = calendar.calender_getStartEndDate(period, date)
                represent_row_res[ret_perf_col] = cal.basicCal_getPeriodReturn(represent_mock_port_ret_series.loc[period_start_date:period_end_date], freq='D', annualized=False)
            core_pool_mock_port_perf_res = core_pool_mock_port_perf_res.append(represent_row_res, ignore_index=True)
        mock_port_perf_res[core_pool] = core_pool_mock_port_perf_res[['portfolio_id', 'portfolio_name', '1D', '1W', '1M', '3M', '1Y', 'YTD']]
    return mock_port_perf_res

# -------------------------------
# 公募核心库收益监控 - 持仓维度
# -------------------------------
def mntrAnls_MFCorePoolMockPortRecommendProductPerf(
    date,   # 考察日期
):
    assert isinstance(date, datetime.date), "date需为datetime.date类型"
    # 从wind字段映射回stats类型
    ret_rank_perf_stats_rename_dict = dict([(monitor_config.mf_core_pool_ret_rank_perf_stats[stats_type]['wind_perf_col'], stats_type)
                                            for stats_type in monitor_config.mf_core_pool_ret_rank_perf_stats.keys()])
    # 产品维度
    product_perf_res = {}
    # 公募推荐分类
    for core_pool in monitor_config.mf_core_pool_config.keys():
        product_perf_res[core_pool] = {}
        type_level_1_perf_res_list = []
        mock_port_id_map = monitor_config.mf_core_pool_config[core_pool]['mock_port_id_map']
        # 遍历推荐分类下的一级分类，一级分类汇总得到汇总维度结果
        for type_level_1 in mock_port_id_map.keys():
            # ----------------------------
            # 产品维度：核心库->一级分类汇总结果
            # ----------------------------
            type_level_2_perf_res_list = []
            # 遍历推荐分类下的二级分类，打上type_level_2标签，二级分类汇总得到一级分类维度结果
            # 二级分类对应单一模拟组合
            for type_level_2 in mock_port_id_map[type_level_1].keys():
                type_level_2_perf_res = univAnls.univAnls_getMFMockPortRecommendWindStylePerf(start_date=date, end_date=date, mock_port_ids=[mock_port_id_map[type_level_1][type_level_2]],
                                                                                            stats=list(ret_rank_perf_stats_rename_dict.keys()), numeric_rank=True)
                type_level_2_perf_res.rename(columns=ret_rank_perf_stats_rename_dict, inplace=True)
                type_level_2_perf_res.insert(4, 'type_level_1', type_level_1)  # 插入type_level_1列
                type_level_2_perf_res.insert(5, 'type_level_2', type_level_2)  # 插入type_level_2列
                type_level_2_perf_res_list.append(type_level_2_perf_res)
            # 汇总成一级分类结果，删去不需要的列，债券推荐按1W收益率排名，权益推荐按1D收益率进行排名
            type_level_1_perf_res = pd.concat(type_level_2_perf_res_list, axis=0).sort_values(['type_level_2', '1W'] if core_pool == '债券核心库' else ['type_level_2', '1D'], ascending=False)
            type_level_1_perf_res_list.append(type_level_1_perf_res)
            del type_level_1_perf_res['portfolio_id'], type_level_1_perf_res['portfolio_name'], type_level_1_perf_res['date']
            product_perf_res[core_pool][type_level_1] = type_level_1_perf_res[['product_id', 'product_name', 'pm_name', 'type_level_2', '1D', 'rank_1D',
                                                                               '1W', 'rank_1W', '1M', 'rank_1M', '3M', 'rank_3M', '1Y', 'rank_1Y', 'YTD', 'rank_YTD']]
    # 收益模拟仅考虑场外基金
    equity_product_perf_res = pd.concat([type_level_1_perf_res[type_level_1_perf_res['product_id'].str.endswith('.OF')] for type_level_1_perf_res in product_perf_res['权益核心库'].values()], axis=0)
    equity_product_stock_holding_sim_ret = MFAnal.anlsMF_getMFStockHoldingSimulatedDailyReturn(date, equity_product_perf_res['product_id'].unique().tolist())
    del equity_product_stock_holding_sim_ret['date']
    return product_perf_res, equity_product_stock_holding_sim_ret


# -----------------------------------------
# 公募基金公司高管变动监控
# -----------------------------------------
def mntrAnls_getMFCompanyExecutivesAdjustment(
    start_date,  # 起始日期
    end_date     # 截止日期
):
    assert isinstance(start_date, datetime.date), "start_date输入类型需为datetime.date"
    assert isinstance(end_date, datetime.date), "end_date输入类型需为datetime.date"
    exec_adj_info = wd.wind_getMFCompanyExecutivesAdjustInfo(start_date, end_date)
    # 仅筛选公募基金公司
    exec_adj_info = exec_adj_info[exec_adj_info['company_type'] == '基金管理公司']
    exec_adj_info['adjust_type'] = exec_adj_info['exec_end_date'].apply(lambda x: '新聘' if pd.isna(x) else '离任')
    exec_adj_info.sort_values(['exec_end_date', 'company_name'], ascending=False, inplace=True)
    exec_adj_info['exec_end_date'].fillna('', inplace=True)
    del exec_adj_info['ann_date'], exec_adj_info['company_type']
    return exec_adj_info
