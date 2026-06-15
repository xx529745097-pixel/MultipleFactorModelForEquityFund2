# -----------------------------------------------------------------------
# Barra相关数据提取
# -----------------------------------------------------------------------
import pandas as pd
from src.data.amdata import *
import src.data.irm as irm
import datetime
import src.const as const
import src.utils.Calculation as basicCal


# ------------------------------------------------------------------------
# 读取Barra daily factor return
# ------------------------------------------------------------------------
def barra_getBarraFactorDailyReturn(
    start_date,  # DateTime.date instance, eg: datetime.date(2021, 1, 1)
    end_date,  # DateTime.date instance, eg: datetime.date(2021, 10, 1)
    factor_list=None  # python list
):
    assert isinstance(start_date, datetime.date), "start_date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "end_date must be an instance of datetime.date"
    start_date = start_date.strftime("%Y-%m-%d")
    end_date = end_date.strftime("%Y-%m-%d")
    amdata_conn = amdata_connectAmdataDb()
    sql = "SELECT * FROM AMDATA.SRC_BARRA_DLYFACRET WHERE D_DT >= TO_DATE('{}', 'YYYY-MM-DD') AND D_DT <= TO_DATE('{}', 'YYYY-MM-DD')"
    df_factor_return = pd.read_sql_query(sql.format(start_date, end_date), amdata_conn).rename(columns=str.lower)
    df_factor_return = pd.pivot_table(df_factor_return, index=['d_dt'], columns=['c_factor'], values=['n_factorreturn'])['n_factorreturn']
    df_factor_return.columns.name = ''
    df_factor_return.reset_index(inplace=True)
    df_factor_return.rename(columns={'d_dt': 'date'}, inplace=True)
    df_factor_return['date'] = pd.to_datetime(df_factor_return['date']).dt.date
    if factor_list:
        assert isinstance(factor_list, list), "factor list must be a list"
        df_factor_return = df_factor_return[['date'] + factor_list]
    df_factor_return.columns = map(str.lower, df_factor_return)
    amdata_conn.close()
    return df_factor_return

# ------------------------------------------------------------------------
# 读取个股在barra factor上的暴露
# ------------------------------------------------------------------------
def barra_getStockExposure(
    method,  # "discrete" or "continuous", discrete指提取非连续日期的数据，需要和date_list联合使用， continuous指提取连续时序数据，须和start_date以及end_date联合使用
    factor_type,  # either "STYLE" or "INDUSTRY"
    start_date=None,  # DateTime.date instance, eg: datetime.date(2021, 1, 1)
    end_date=None,  # DateTime.date instance, eg: datetime.date(2021, 1, 1)
    stock_list=None,
    date_list=None  # date_list 只在method为discrete时有用
):
    assert method in ("discrete", "continuous"), "method只能为discrete或者continuous"
    assert factor_type in ("STYLE", "INDUSTRY"), "因子类型只能是STYLE或者INDUSTRY"
    amdata_conn = amdata_connectAmdataDb()

    if method == "discrete":
        assert date_list, "日期列表不能为空"
        assert all([isinstance(date, datetime.date) for date in date_list]), "日期列表必须全部为datetime.date"
        date_list = [x.strftime("%Y-%m-%d") for x in date_list]
        sql_date_list = ','.join(["TO_DATE('%s', 'YYYY-MM-DD')" % x for x in date_list])
        if stock_list:
            if len(stock_list) > 500:
                stock_list = basicCal.basicCal_cut(stock_list, 500)
                temp_list = []
                for sl in stock_list:
                    sql = "SELECT * FROM AMDATA.SRC_BARRA_ASSET_EXPOSURE WHERE D_DT IN ({}) AND C_SECU_ID IN ({}) AND C_FACTOR_TYPE = '{}'"
                    df = pd.read_sql_query(sql.format(sql_date_list, ','.join(["'%s'" % x for x in sl]), factor_type), amdata_conn).rename(columns=str.lower)
                    temp_list.append(df)
                df = pd.concat(temp_list, axis=0)
            else:
                sql = "SELECT * FROM AMDATA.SRC_BARRA_ASSET_EXPOSURE WHERE D_DT IN ({}) AND C_SECU_ID IN ({}) AND C_FACTOR_TYPE = '{}'"
                df = pd.read_sql_query(sql.format(sql_date_list, ','.join(["'%s'" % x for x in stock_list]), factor_type), amdata_conn).rename(columns=str.lower)
        else:
            sql = "SELECT * FROM AMDATA.SRC_BARRA_ASSET_EXPOSURE WHERE D_DT IN ({}) AND C_FACTOR_TYPE = '{}'"
            df = pd.read_sql_query(sql.format(sql_date_list, factor_type), amdata_conn).rename(columns=str.lower)

    else:
        assert isinstance(start_date, datetime.date), "start_date must be an instance of datetime.date"
        assert isinstance(end_date, datetime.date), "end_date must be an instance of datetime.date"
        start_date = start_date.strftime("%Y-%m-%d")
        end_date = end_date.strftime("%Y-%m-%d")
        if stock_list:
            if len(stock_list) > 500:
                stock_list = basicCal.basicCal_cut(stock_list, 500)
                temp_list = []
                for sl in stock_list:
                    sql = "SELECT * FROM AMDATA.SRC_BARRA_ASSET_EXPOSURE WHERE D_DT >= TO_DATE('{}', 'YYYY-MM-DD') AND D_DT <= TO_DATE('{}', 'YYYY-MM-DD')\
                     AND C_SECU_ID IN ({}) AND C_FACTOR_TYPE = '{}'"
                    df = pd.read_sql_query(sql.format(start_date, end_date, ','.join(["'%s'" % x for x in sl]), factor_type), amdata_conn).rename(columns=str.lower)
                    temp_list.append(df)
                df = pd.concat(temp_list, axis=0)
            else:
                sql = "SELECT * FROM AMDATA.SRC_BARRA_ASSET_EXPOSURE WHERE D_DT >= TO_DATE('{}', 'YYYY-MM-DD') AND D_DT <= TO_DATE('{}', 'YYYY-MM-DD') AND \
                C_SECU_ID IN ({}) AND C_FACTOR_TYPE = '{}'"
                df = pd.read_sql_query(sql.format(start_date, end_date, ','.join(["'%s'" % x for x in stock_list]), factor_type), amdata_conn).rename(columns=str.lower)
        else:
            sql = "SELECT * FROM AMDATA.SRC_BARRA_ASSET_EXPOSURE WHERE D_DT >= TO_DATE('{}', 'YYYY-MM-DD') AND D_DT <= TO_DATE('{}', 'YYYY-MM-DD') AND C_FACTOR_TYPE = '{}'"
            df = pd.read_sql_query(sql.format(start_date, end_date, factor_type), amdata_conn).rename(columns=str.lower)

    df.rename(columns={'d_dt': 'date', 'c_secu_id': 'stock_id', 'c_factor': 'factor', 'n_exposure': 'exposure', 'c_factor_type': 'factor_type'}, inplace=True)
    df['factor'] = df['factor'].apply(lambda x: x.lower())
    df['date'] = pd.to_datetime(df['date']).dt.date  # convert timestamp to datetime.date
    amdata_conn.close()
    return df

# ------------------------------------------------------------------------
# 从数据库中读取某一指数的barra因子暴露，如果没有就需要重新计算并写入
# ------------------------------------------------------------------------
def barra_readIndexBarraFactorExposure(
    start_date,  # DateTime.date instance
    end_date,  # DateTime.date instance
    index_codes=None  # list, must be in "HS300", "ZZ100", "ZZ500", "ZZ800", "ZZ1000"
):
    assert isinstance(start_date, datetime.date), "date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "date must be an instance of datetime.date"

    conn = irm.irm_connectIRMDB()
    sql = "SELECT * FROM irm.AMFOF_PRODUCT_BARRA_EXPOSURE WHERE DT >= DATE'{}' AND DT <= DATE'{}' "
    if index_codes:
        assert isinstance(index_codes, list), "index_codes需为list类型"
        assert set(index_codes) <= {"HS300", "ZZ100", "ZZ500", "ZZ800", "ZZ1000"}, "目前只支持沪深300，中证100， 中证500， 中证800， 中证1000"
        sql += "AND ID_CODE IN ({}) ".format(','.join(["'%s'" % const.const.INDEX_NAME_TO_CODE_MAP[index_code] for index_code in index_codes]))
    df = pd.read_sql_query(sql.format(start_date, end_date), conn).rename(columns=str.lower)
    conn.close()
    df.rename(columns={'dt': 'date', 'id_code': 'index_code', 'sz': 'size'}, inplace=True)
    df.drop(['id_type'], axis=1, inplace=True)
    df.sort_values(by='date', ascending=True, inplace=True)
    return df