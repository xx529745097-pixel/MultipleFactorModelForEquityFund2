# ------------------------------------------------------
# 本文档用于从AMFOF数据、IRM研究平台数据库读取缓存的朝阳永续相关数据
# ------------------------------------------------------

import pandas as pd
import datetime
import src.data.amdata as am
import src.data.irm as irm


# ------------------------------------------------------
# 获取缓存的朝阳永续策略universe分位数数据
# ------------------------------------------------------
def zyyxCached_getCachedUnivDistribution(
    start_date,             # 起始日期，输入格式:datetime.date
    end_date,               # 结束日期，输入格式:datetime.date
    categories,             # list, e.g. ['300指数增强']
    stats,                  # list, e.g. ['week_return']
    percent_array=[0.5],    # list of quantile percents, please select subset of [0, 0.1, 0.25, 0.33, 0.4, 0.5, 0.6, 0.67, 0.75, 0.9, 1]
):
    assert isinstance(start_date, datetime.date), "date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "date must be an instance of datetime.date"
    assert set(stats).issubset({'week_return'}), "目前stats只支持week_return"
    assert set(categories).issubset({'300指数增强', '500指数增强', '1000指数增强', '股票市场中性', '低波动管理期货', '中波动管理期货', '高波动管理期货', '宏观策略', '套利策略'}), \
            "categories需为300指数增强,500指数增强,1000指数增强,股票市场中性,低波动管理期货,中波动管理期货,高波动管理期货,宏观策略,套利策略 中的若干项"
    assert set(percent_array).issubset({0, 0.1, 0.25, 0.33, 0.4, 0.5, 0.6, 0.67, 0.75, 0.9, 1}), \
            "percent_array缓存分位数只包含0, 0.1, 0.25, 0.33, 0.4, 0.5, 0.6, 0.67, 0.75, 0.9, 1"

    conn = irm.irm_connectIRMDB()
    amdata_col_mapping = {
        '0': 'N_000',
        '0.1': 'N_010',
        '0.25': 'N_025',
        '0.33': 'N_033',
        '0.4': 'N_040',
        '0.5': 'N_050',
        '0.6': 'N_060',
        '0.67': 'N_067',
        '0.75': 'N_075',
        '0.9': 'N_090',
        '1': 'N_100',
    }
    percent_col = [amdata_col_mapping[str(x)] for x in percent_array]
    percent_str = ','.join(["%s" % x for x in percent_col])
    categories_str = ','.join(["'%s'" % x for x in categories])
    stats_str = ','.join(["'%s'" % x for x in stats])
    sql = "SELECT DT, DATA_SOURCE, TYPE_NAME, STATS_NAME, {0}" \
          " FROM irm.AMFOF_INDEX_YIELD_INFO WHERE (TYPE_NAME in ({1}) AND STATS_NAME in ({2})" \
          " AND DT >= DATE'{3}' AND DT <= DATE'{4}') ORDER BY TYPE_NAME, DT ASC"
    ret = pd.read_sql_query(sql.format(percent_str, categories_str, stats_str, start_date, end_date), conn)
    rename_mapping = {'DT': 'date', 'DATA_SOURCE': 'data_source', 'TYPE_NAME': 'category', 'STATS_NAME': 'stats'}
    rename_mapping.update(dict(zip(amdata_col_mapping.values(), amdata_col_mapping.keys())))  # 将amdata_col_mapping的key/value对调并加入rename_mapping
    ret.rename(columns=rename_mapping, inplace=True)
    ret['date'] = pd.to_datetime(ret['date']).dt.date
    conn.close()
    return ret


# ------------------------------------------------------
# 获取缓存的朝阳永续universe product return数据
# ------------------------------------------------------
def zyyxCached_getCachedUnivProductReturn(
    start_date,             # 起始日期，输入格式:datetime.date
    end_date,               # 结束日期，输入格式:datetime.date
    categories,             # list, e.g. ['300指数增强']
    stats,                  # list, e.g. ['week_return']
):
    assert isinstance(start_date, datetime.date), "date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "date must be an instance of datetime.date"
    assert set(stats).issubset({'week_return', 'month_return', 'year_return'}), "目前stats只支持week_return"
    assert set(categories).issubset({'股票多头', '300指数增强', '500指数增强', '1000指数增强', '股票市场中性', '低波动管理期货', '中波动管理期货', '高波动管理期货', '宏观策略', '套利策略', '低波动组合基金', '中波动组合基金', '高波动组合基金'}), \
            "categories需为股票多头,300指数增强,500指数增强,1000指数增强,股票市场中性,低波动管理期货,中波动管理期货,高波动管理期货,宏观策略,套利策略,低波动组合基金,中波动组合基金,高波动组合基金 中的若干项"
    assert len(stats) == 1, "目前stats只支持单一输入"

    irm_conn = irm.irm_connectIRMDB()
    categories_str = ','.join(["'%s'" % x for x in categories])
    stats_str = ','.join(["'%s'" % x for x in stats])
    sql = "SELECT DT, PRODUCT_ID, PRODUCT_NAME, MANAGER, START_DATE, DATA_SOURCE, TYPE_NAME, STAT_NAME, STAT_VALUE" \
          " FROM irm.AMFOF_UNIVERSE_PRODUCT_STATS WHERE (TYPE_NAME in ({0}) AND STAT_NAME in ({1})" \
          " AND DT>=DATE'{2}' AND DT<=DATE'{3}') ORDER BY TYPE_NAME, DT ASC"
    ret = pd.read_sql_query(sql.format(categories_str, stats_str, start_date, end_date), irm_conn)
    rename_mapping = {'DT': 'date', 'PRODUCT_ID': 'product_id', 'PRODUCT_NAME': 'product_name', 'MANAGER': 'manager',
                      'START_DATE': 'start_date', 'DATA_SOURCE': 'data_source', 'TYPE_NAME': 'type_name', 'STAT_NAME': 'stat_name', 'STAT_VALUE': 'stat_value'}
    ret.rename(columns=rename_mapping, inplace=True)
    ret['date'] = pd.to_datetime(ret['date']).dt.date
    ret[stats[0]] = ret['stat_value']
    ret = ret[['date', 'product_id', 'product_name', 'manager', 'start_date', 'data_source', 'type_name', stats[0]]]
    ret[stats[0]] = ret[stats[0]].astype(float)
    irm_conn.close()
    return ret

