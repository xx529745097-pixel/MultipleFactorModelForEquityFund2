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
import src.data.zyyx_cached as zyyx_cached
import src.analysis.portfolioAnalysis as PortAnal
import src.analysis.MFAnalysis as MFAnal
import src.analysis.fundamentalFundAnalysis as FFAnal
import src.analysis.quantFundAnalysis as QFAnal
import src.config as config
import src.const as const


# --------------------------------------------------------------------------------------
# 获取定制指数的行业权重情况，用于计算行业超低配
# 该结果存在缓存表，每次季报披露完毕后会更新最新日期数据入表
# --------------------------------------------------------------------------------------
def industryAnls_getCustomizedIndexIndustryWeight(
    index_id,   # 指数ID，目前支持四种自定义指数，详见assert
    date,
    company,    # 分类标准，输入格式:str，'SW' or 'CITICS'
    level,      # 分类级别，输入格式:int
):
    assert index_id in ('881001.WI', '885001.EQUAL_WEIGHTED', '885001.AUM_WEIGHTED', '885007.EQUAL_WEIGHTED', '885007.AUM_WEIGHTED', 'BALANCED_MF_CUSTOMIZED.EQUAL_WEIGHTED', 'BALANCED_MF_CUSTOMIZED.AUM_WEIGHTED'), \
        "行业超低配基准仅支持'881001.WI', '885001.EQUAL_WEIGHTED', '885001.AUM_WEIGHTED', '885007.EQUAL_WEIGHTED', '885007.AUM_WEIGHTED', 'BALANCED_MF_CUSTOMIZED.EQUAL_WEIGHTED', 'BALANCED_MF_CUSTOMIZED.AUM_WEIGHTED'"
    assert (company == 'SW' or company == 'CITICS'), 'company必须为SW或CITICS'
    assert (type(level) == int), 'level输入格式需为int'
    industry_level = company + '_' + str(level)
    conn = irm.irm_connectIRMDB()
    sql = "SELECT * FROM irm.AMFOF_CUSTOMIZED_INDEX_INDUSTRY_WEIGHT WHERE index_id = '{0}' AND industry_level = '{1}' AND index_data_date <= DATE'{2}'"
    index_industry_weight = pd.read_sql_query(sql.format(index_id, industry_level, date), conn).rename(columns=str.lower)
    index_industry_weight = index_industry_weight[index_industry_weight['index_data_date'] == index_industry_weight['index_data_date'].max()]
    conn.close()
    return index_industry_weight

# --------------------------------------------------------------------------------------
# 获取FOF账户、公募、多头私募和量化私募的行业超低配情况
# 取出截至给定日期最新的行业占比，目前对于FOF账户和私募产品，行业只支持SW1级行业
# 选择中证指数做对比时，会把港股&美股剔除并重新把权重张成100%
# --------------------------------------------------------------------------------------
def industryAnls_getIndustryExposure(
    report_date,            # 日期，公募或私募产品所取报告日期或是指FOF账户所依据的持仓日期，输入格式:datetime.date
    ids,                    # 账户或者基金代码，list格式
    fund_type,              # 传入的账户或产品类型，包括FOF MF HF
    benchmark_id,           # 对比的指数id
    company='SW',           # 行业分类标准，输入格式:str，'SW' or 'CITICS'
    level=1,                # 行业分类级别，输入格式:int
):
    assert fund_type in ['FOF', 'MF', 'HF'], "行业计算函数的fund_type可选FOF、MF、HF"
    assert len(ids) == 1, "做行业超低配分析时仅限于单个账户or产品"
    assert benchmark_id in ('000300.SH', '000905.SH', '000906.SH', '000852.SH', '881001.WI', '885001.EQUAL_WEIGHTED', '885001.AUM_WEIGHTED', '885007.EQUAL_WEIGHTED', '885007.AUM_WEIGHTED', 'ZERO_BM', 'BALANCED_MF_CUSTOMIZED.EQUAL_WEIGHTED', 'BALANCED_MF_CUSTOMIZED.AUM_WEIGHTED'),\
        "行业超低配基准仅支持'000300.SH', '000905.SH', '000906.SH', '000852.SH', '881001.WI', '885001.EQUAL_WEIGHTED', '885001.AUM_WEIGHTED', '885007.EQUAL_WEIGHTED', '885007.AUM_WEIGHTED', 'ZERO_BM', 'BALANCED_MF_CUSTOMIZED.EQUAL_WEIGHTED', 'BALANCED_MF_CUSTOMIZED.AUM_WEIGHTED'"
    if fund_type == 'FOF':
        # 如果持仓数据包含私募多头，则目前仅支持申万一级的行业，已在内层函数assert
        product_industry = PortAnal.anlsFOF_getFOFIndustryLookThrough(report_date, ids[0], company, level, top_num=999, mask_h_shares=False)['industry']
        product_industry = product_industry[['portfolio_id', 'portfolio_name', 'industry', 'industry_weight', 'industry_level', 'date', 'report_date']]
        product_industry = product_industry[product_industry['industry'] != '合计']
    elif fund_type == 'MF':
        product_industry = MFAnal.anlsMF_getListedMFIndustryWeightDetails(report_date, ids, company, level, mask_h_shares=False, expand_weight=True)
    elif fund_type == 'HF':
        assert company == 'SW' and level == 1, "私募的行业穿透和超低配计算目前只支持申万一级"
        qf_product_industry = QFAnal.qfa_getListedQuantFundIndustryWeightDetails(report_date, ids, expand_weight=True)
        ff_product_industry = FFAnal.ffa_getListedFundaFundIndustryWeightDetails(report_date, ids, expand_weight=True, mask_h_shares=False)
        product_industry = pd.concat([qf_product_industry, ff_product_industry])

    id_str = 'portfolio_id' if fund_type == 'FOF' else 'product_id'
    # 判断是否有公募持仓行业数据报告期未对齐的情况，如有未对齐则report_date存储的是一个str(list)的形式，则取出其中更早的那个日期进行指数的超低配计算
    data_report_date = product_industry.report_date.iloc[0] if isinstance(product_industry.report_date.iloc[0], datetime.date) \
                        else datetime.datetime.strptime(eval(product_industry.report_date.iloc[0])[0], '%Y-%m-%d').date()   # 取得行业数据的实际日期
    # 如果选择A股指数，需先剔除港股/美股权重并重新把A股权重张成100%
    if benchmark_id in ('000300.SH', '000905.SH', '000906.SH', '000852.SH', '881001.WI'):
        product_industry = product_industry[~(product_industry['industry'].str.contains('港股') | product_industry['industry'].str.contains('美股'))]
        a_stock_weight_sum = product_industry.groupby([id_str])['industry_weight'].sum().to_dict()
        product_industry['industry_weight'] = product_industry.apply(lambda x: x['industry_weight']/a_stock_weight_sum[x[id_str]], axis=1)

    # 获取指数的行业比重
    if benchmark_id == 'ZERO_BM':
        # 零基准默认基准行业配置均为0
        combined_result = product_industry
        combined_result['index_industry_weight'] = 0
        combined_result['industry_diff'] = combined_result['industry_weight'] - combined_result['index_industry_weight']
    else:
        if benchmark_id in ('000300.SH', '000905.SH', '000906.SH', '000852.SH'):
            index_industry = wd.wind_getIndexIndustryWeight(benchmark_id, data_report_date, company, level).rename(columns={'industry_weight': 'index_industry_weight'})
        else:
            # 对于定制的行业超低配基准，从缓存的表里取数，提升效率
            index_industry = industryAnls_getCustomizedIndexIndustryWeight(benchmark_id, data_report_date, company, level).rename(columns={'industry_weight': 'index_industry_weight'})
        index_industry = index_industry[index_industry['index_data_date'] == index_industry['index_data_date'].max()]
        combined_result = pd.merge(product_industry, index_industry[['industry', 'index_industry_weight', 'index_data_date']], on='industry', how='outer')
        combined_result[['industry_weight', 'index_industry_weight']] = combined_result[['industry_weight', 'index_industry_weight']].fillna(0)
        combined_result = combined_result.fillna(method='ffill')
        combined_result['industry_diff'] = combined_result['industry_weight'] - combined_result['index_industry_weight']

    return combined_result


# -----------------------------------------------------------------------------------------
# 获取FOF账户、公募、多头私募和量化私募的行业超低配一段时间内的变化情况，目前是取近四周的情况
# 目前对于私募产品，行业只支持SW1级行业，对于会把港股剔除并重新把权重张成100%
# -----------------------------------------------------------------------------------------
def industryAnls_getIndustryExposureSeries(
    report_date,            # 日期，公募或私募产品所取报告日期或是指FOF账户所依据的持仓日期，输入格式:datetime.date
    ids,                    # 账户或者基金代码，list格式
    fund_type,              # 传入的账户或产品类型，包括FOF MF HF
    benchmark_id,           # 对比的指数id
    company='SW',           # 行业分类标准，输入格式:str，'SW' or 'CITICS'
    level=1,                # 行业分类级别，输入格式:int
    look_back_weeks=4,      # 回看周数，目前回看四周(包括本周)
):
    date_list = [report_date - datetime.timedelta(i*7) for i in range(look_back_weeks)]
    result = []
    for date in date_list:
        result.append(industryAnls_getIndustryExposure(date, ids, fund_type, benchmark_id, company, level))
    result = pd.concat(result)
    return result


####################################################################
# WRITE API
####################################################################
# --------------------------------------------------------------------------------------
# 使用wind数据计算定制指数的行业权重情况，并缓存，用于计算行业超低配
# 每次季报披露完毕后会手动触发最新日期数据入表
# --------------------------------------------------------------------------------------
def industryAnls_cacheCustomizedIndexIndustryWeight(
    index_id,   # 指数ID，目前支持四种自定义指数，详见assert
    date,
    company,    # 分类标准，输入格式:str，'SW' or 'CITICS'
    level,      # 分类级别，输入格式:int
    insert=False,
):
    assert index_id in ('881001.WI', '885001.EQUAL_WEIGHTED', '885001.AUM_WEIGHTED', '885007.EQUAL_WEIGHTED', '885007.AUM_WEIGHTED', 'BALANCED_MF_CUSTOMIZED.EQUAL_WEIGHTED', 'BALANCED_MF_CUSTOMIZED.AUM_WEIGHTED'), \
        "行业超低配基准的缓存仅支持'881001.WI', '885001.EQUAL_WEIGHTED', '885001.AUM_WEIGHTED', '885007.EQUAL_WEIGHTED', '885007.AUM_WEIGHTED', 'BALANCED_MF_CUSTOMIZED.EQUAL_WEIGHTED', 'BALANCED_MF_CUSTOMIZED.AUM_WEIGHTED'"
    assert (company == 'SW' or company == 'CITICS'), 'company必须为SW或CITICS'
    assert (type(level) == int), 'level输入格式需为int'
    index_industry = wd.wind_getIndexIndustryWeight(index_id, date, company, level)
    index_industry = index_industry[index_industry['index_data_date'] == index_industry['index_data_date'].max()]
    data_date = index_industry['index_data_date'].iloc[0]
    index_name_map = {
        '881001.WI': '万得全A',
        '885001.EQUAL_WEIGHTED': '偏股混-等权',
        '885001.AUM_WEIGHTED': '偏股混-市值加权',
        'BALANCED_MF_CUSTOMIZED.EQUAL_WEIGHTED': '均衡型基金-等权',
        'BALANCED_MF_CUSTOMIZED.AUM_WEIGHTED': '均衡型基金-市值加权',
        '885007.EQUAL_WEIGHTED': '二级债基-等权',
        '885007.AUM_WEIGHTED': '二级债基-市值加权',
    }
    industry_level = company + '_' + str(level)
    index_industry['index_name'] = index_industry['index_id'].apply(lambda x: index_name_map[x])
    index_industry['industry_level'] = industry_level
    index_industry['update_time'] = datetime.date.today()

    if insert:
        # 如果重复日期数据
        conn = irm.irm_connectIRMDB()
        sql = "DELETE FROM irm.AMFOF_CUSTOMIZED_INDEX_INDUSTRY_WEIGHT WHERE index_id = '{0}' AND industry_level = '{1}' AND index_data_date = DATE'{2}'"
        sql = sql.format(index_id, industry_level, data_date.strftime('%Y-%m-%d'))
        cur = conn.cursor()
        cur.execute(sql)
        conn.commit()

        # 写入数据库
        irm.irm_insertIRMData(index_industry, 'irm.AMFOF_CUSTOMIZED_INDEX_INDUSTRY_WEIGHT')
        conn.close()

    return index_industry
