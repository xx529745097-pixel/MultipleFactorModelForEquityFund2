import numpy as np
import pandas as pd
import datetime
import src.data.custHF as custHF
import src.const as const
import src.config as config
import src.analysis.industryAnalysis as industryAnal
import src.analysis.barraAnalysis as barraAnal
import src.data.wind as wd
import matplotlib.pyplot as plt
from matplotlib import cm, ticker
import seaborn as sns
plt.rcParams['axes.unicode_minus'] = False


# ------------------------------------------------------
# 获取FOF账户或公募私募产品行业超低配的汇总表和柱状图
# ------------------------------------------------------
def industryVis_getIndustryExposure(
    report_date,            # 量化私募产品所取托管报告的日期，输入格式:datetime.date
    ids,                    # 账户或者基金代码，list格式
    fund_type,              # 传入的账户或产品类型，包括FOF MF HF
    benchmark_id,           # 对比的指数id
    company='SW',           # 行业分类标准，输入格式:str，'SW' or 'CITICS'
    level=1,                # 行业分类级别，输入格式:int
):
    result = industryAnal.industryAnls_getIndustryExposure(report_date, ids, fund_type, benchmark_id, company, level)
    if fund_type == 'HF':
        level_info = custHF.custHF_getProductInfo()
        id_to_name = level_info.set_index('product_id')['product_short_name'].to_dict()
    elif fund_type == 'MF':
        level_info = wd.wind_getCurrentProductList(product_ids=ids)
        id_to_name = level_info.set_index('product_id')['product_name'].to_dict()
    if fund_type in ['HF', 'MF']:
        result['product_name'] = result['product_id'].apply(lambda x: id_to_name.get(x, ''))
    id_str = 'portfolio_id' if fund_type == 'FOF' else 'product_id'
    name_str = 'portfolio_name' if fund_type == 'FOF' else 'product_name'
    result = result[[id_str, name_str, 'report_date', 'industry_level', 'industry', 'industry_weight', 'index_industry_weight', 'industry_diff']]
    industry_level_map = {
        'company': {'SW': '申万', 'CITICS': '中信'},
        'level': {1: '一级', 2: '二级', 3: '三级'}
    }
    result['industry_level'] = industry_level_map['company'][company] + industry_level_map['level'][level]
    result['industry_level'] = result.apply(lambda x: '恒生一级' if '港股' in x['industry'] else x['industry_level'], axis=1)
    benchmark_name_map = {
        '000906.SH': '中证800', '000300.SH': '沪深300', '000905.SH': '中证500', '000852.SH': '中证1000', '881001.WI': '万得全A',
        '885001.EQUAL_WEIGHTED': '偏股混(等权)', '885001.AUM_WEIGHTED': '偏股混(市值加权)',  'ZERO_BM': '零基准',
        '885007.EQUAL_WEIGHTED': '二级债基(等权)', '885007.AUM_WEIGHTED': '二级债基(市值加权)',
        'BALANCED_MF_CUSTOMIZED.EQUAL_WEIGHTED': '均衡型基金(等权)', 'BALANCED_MF_CUSTOMIZED.AUM_WEIGHTED': '均衡型基金(市值加权)'
    }
    benchmark_name = benchmark_name_map[benchmark_id]
    rename_dict = {
        id_str: 'ID',
        name_str: '名称',
        'industry_level': '行业分类等级',
        'industry': '行业',
        'report_date': '报告数据日期',
        'industry_weight': '行业权重',
        'index_industry_weight': benchmark_name+'行业权重',
        'industry_diff': '行业超低配'
    }
    result = result.rename(columns=rename_dict)
    table_result = result.copy(deep=True)
    new_cmap = sns.diverging_palette(**config.cmap_kwargs)
    table_result = table_result.style.format({'行业权重': '{:.2%}', benchmark_name+'行业权重': '{:.2%}', '行业超低配': '{:.2%}'}).\
                    background_gradient(subset=['行业权重', benchmark_name+'行业权重'], cmap='Reds', low=0, high=config.cmap_range_adjust_coef).\
                    background_gradient(subset='行业超低配', cmap=new_cmap, low=config.cmap_range_adjust_coef, high=config.cmap_range_adjust_coef, axis=0,
                                        vmin=-result['行业超低配'].abs().max(axis=0), vmax=result['行业超低配'].abs().max(axis=0))
    fig, ax = plt.subplots(figsize=(10, 10 * 0.618))
    result.sort_values('行业超低配', ascending=False).plot.bar(x='行业', y='行业超低配', ax=ax)
    ax.set_title(result['名称'].iloc[0] + ' ' + industry_level_map['company'][company] + industry_level_map['level'][level]+
                 ' 相对' + benchmark_name + '行业超低配 ' + report_date.strftime('%Y-%m-%d'), fontsize=18)
    plt.xticks(fontsize=min(600/len(result), 12))   # 动态字体大小
    plt.tight_layout()
    formatter = ticker.FuncFormatter(lambda y, _: '{:.2%}'.format(y))
    plt.gca().yaxis.set_major_formatter(formatter)
    plt.grid(ls='--', axis='y')
    figure = plt.gcf()
    return table_result, figure


# -----------------------------------------------------------------------------------------
# 获取FOF账户、公募、多头私募和量化私募的行业超低配一段时间内的变化情况，目前是取近四周的情况
# 目前对于私募产品，行业只支持SW1级行业，对于会把港股剔除并重新把权重张成100%
# -----------------------------------------------------------------------------------------
def industryVis_getIndustryExposureSeries(
    report_date,            # 日期，公募或私募产品所取报告日期或是指FOF账户所依据的持仓日期，输入格式:datetime.date
    ids,                    # 账户或者基金代码，list格式
    fund_type,              # 传入的账户或产品类型，包括FOF MF HF
    benchmark_id,           # 对比的指数id
    company='SW',           # 行业分类标准，输入格式:str，'SW' or 'CITICS'
    level=1,                # 行业分类级别，输入格式:int
    look_back_weeks=4,      # 回看周数，目前回看四周(包括本周)
):
    result = industryAnal.industryAnls_getIndustryExposureSeries(report_date, ids, fund_type, benchmark_id, company, level, look_back_weeks)
    if fund_type == 'HF':
        level_info = custHF.custHF_getProductInfo()
        id_to_name = level_info.set_index('product_id')['product_short_name'].to_dict()
    elif fund_type == 'MF':
        level_info = wd.wind_getCurrentProductList(product_ids=ids)
        id_to_name = level_info.set_index('product_id')['product_name'].to_dict()
    if fund_type in ['HF', 'MF']:
        result['product_name'] = result['product_id'].apply(lambda x: id_to_name.get(x, ''))
    id_str = 'portfolio_id' if fund_type == 'FOF' else 'product_id'
    name_str = 'portfolio_name' if fund_type == 'FOF' else 'product_name'
    result = result[[id_str, name_str, 'report_date', 'industry_level', 'industry', 'industry_weight', 'index_industry_weight', 'industry_diff']]
    industry_level_map = {
        'company': {'SW': '申万', 'CITICS': '中信'},
        'level': {1: '一级', 2: '二级', 3: '三级'}
    }
    result['industry_level'] = industry_level_map['company'][company] + industry_level_map['level'][level]
    rename_dict = {
        id_str: 'ID',
        name_str: '名称',
        'industry_level': '行业分类等级',
        'industry': '行业',
        'report_date': '数据日期',
        'industry_weight': '行业权重',
        'index_industry_weight': benchmark_id+'行业权重',
        'industry_diff': '行业超低配'
    }
    benchmark_name_map = {
        '000906.SH': '中证800', '000300.SH': '沪深300', '000905.SH': '中证500', '000852.SH': '中证1000', '881001.WI': '万得全A',
        '885001.EQUAL_WEIGHTED': '偏股混(等权)', '885001.AUM_WEIGHTED': '偏股混(市值加权)',  'ZERO_BM': '零基准',
        '885007.EQUAL_WEIGHTED': '二级债基(等权)', '885007.AUM_WEIGHTED': '二级债基(市值加权)',
        'BALANCED_MF_CUSTOMIZED.EQUAL_WEIGHTED': '均衡型基金(等权)', 'BALANCED_MF_CUSTOMIZED.AUM_WEIGHTED': '均衡型基金(市值加权)'
    }
    benchmark_name = benchmark_name_map[benchmark_id]
    result = result.rename(columns=rename_dict)
    result = result.sort_values(by='数据日期')
    pivot_result = result.pivot(index='行业', values='行业超低配', columns='数据日期')
    pivot_result = pivot_result.sort_values(by=pivot_result.columns[-1], ascending=False)
    fig, ax = plt.subplots(figsize=(10, 10 * 0.618))
    ax = pivot_result.plot(kind="bar", figsize=(10, 10 * 0.618))
    ax.legend(fontsize=12,loc="upper right")
    ax.set_title(result['名称'].iloc[0] + ' ' + industry_level_map['company'][company] + industry_level_map['level'][level]+
                 ' 相对' + benchmark_name +'行业超低配趋势 ' + str(result['数据日期'].min()) + '至' + str(result['数据日期'].max()), fontsize=16)
    plt.xticks(fontsize=12)
    plt.yticks(fontsize=12)
    plt.tight_layout()
    formatter = ticker.FuncFormatter(lambda y, _: '{:.2%}'.format(y))
    plt.gca().yaxis.set_major_formatter(formatter)
    plt.grid(ls='--', axis='y')
    figure = plt.gcf()
    return figure