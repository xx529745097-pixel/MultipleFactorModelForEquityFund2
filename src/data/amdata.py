# ------------------------------------------------------
# This file contains all functions used to interact with
# AMFOF database
# ------------------------------------------------------
import pandas as pd
import sqlalchemy
import datetime
import cx_Oracle

# ------------------------------------------------------------------------
# amfof database connection
# Author: Zhongheng Shen, 041439
# ------------------------------------------------------------------------
def amdata_connectAmdataDb():
    conn = cx_Oracle.connect('AMFOF_READER/AMFOF600030@172.24.129.72:1521/amdata')
    return conn

# ------------------------------------------------------------------------
# 向数据库写入数据
# ------------------------------------------------------------------------
def amdata_insertAMData(
    dataframe,      # 需要写入的数据
    table_name,     # 需要写入的表格的名字，例如：AMFOF.INDEX_YIELD_INFO
):
    conn = cx_Oracle.connect('AMFOF_READER/AMFOF600030@172.24.129.72:1521/amdata')
    keys = ', '.join(dataframe.iloc[0, :].keys())  # 第一行就是对应的列明
    values = ':' + ',:'.join(
        str(i) for i in range(1, len(dataframe.dtypes) + 1))  # 就是为了拼接成(:1,:2,:3,:4)的形式，那个元组的括号在sql里面有了，必须用元组

    insert_sql='INSERT INTO {table} ({keys}) VALUES ({values})'.format(
        table=table_name,
        keys=keys,
        values=values
    )
    # 建立游标
    cursor = conn.cursor()
    # 　批量插入，将结果数据转为列表嵌套列表
    data_total_list = dataframe.values.tolist()
    try:
        cursor.executemany(insert_sql, data_total_list)
        conn.commit()
        print('success')
        cursor.close()
    except Exception as e:
        print('Failed:' + e)

# ------------------------------------------------------------------------
# 如何删除数据的例子
# ------------------------------------------------------------------------
# conn = cx_Oracle.connect('AMFOF_READER/AMFOF600030@172.22.135.164:1521/amdata')
# sql = "DELETE FROM AMFOF.FOF_HOLDING_INFO WHERE data_dt = DATE'2022-04-21'"
# cur = conn.cursor()
# cur.execute(sql)
# conn.commit()

# # ------------------------------------------------------------------------
# # 计算私募基金日度、周度、月度收益
# # Author: Zhongheng Shen, 041439
# # ------------------------------------------------------------------------
# def amdata_getHFProductReturn(
#         product_id,  # SLY771.OF
#         start_date,  # DateTime.date instance
#         end_date,  # DateTime.date instance
#         freq  # string, must be one of ('D', 'W', 'M')
# ):
#     assert product_id.endswith(".OF"), "product_id must be a string ending with .OF"
#     assert freq in ["D", "W", "M"], "frequency must be one of ('D', 'W', 'M')"
#     assert isinstance(start_date, datetime.date), "start_date must be an instance of datetime.date"
#     assert isinstance(end_date, datetime.date), "end_date must be an instance of datetime.date"
#
#     start_date = start_date.strftime("%Y-%m-%d")
#     end_date = end_date.strftime("%Y-%m-%d")
#
#     amdata_conn = amdata_connectAmdataDb()
#     sql = "SELECT * FROM AMFOF_DEV.V_FUND_DAILY_VAL WHERE DT >= TO_DATE('{}', 'YYYY-MM-DD') AND DT <= TO_DATE('{}', 'YYYY-MM-DD') AND SECU_ID = '{}'"
#     df_fund = pd.read_sql_query(sql.format(start_date, end_date, product_id), amdata_conn)
#     df_fund.index = pd.to_datetime(df_fund['dt'], format="%Y-%m-%d")
#     df_fund.sort_index(ascending=True, inplace=True)
#     amdata_conn.close()
#
#     SSE_trade_dates = wind.wind_getSSECalendar()
#     SSE_trade_dates.index = pd.to_datetime(SSE_trade_dates['trade_days'], format="%Y-%m-%d")
#     SSE_trade_dates_period = SSE_trade_dates.loc[df_fund.index[0]: df_fund.index[-1]]
#
#     df_fund['daily_return'] = (df_fund['fund_acu_unit_value'].diff(1) / df_fund['fund_unit_value'].shift(1)).fillna(0)
#     df_fund['cum_daily_return'] = (1 + df_fund['daily_return']).cumprod()
#
#     if freq == "D":
#         fund_index_set = set(df_fund.index.to_list())
#         SSE_trade_dates_period_set = set(SSE_trade_dates_period.index.to_list())
#         assert len(fund_index_set & SSE_trade_dates_period_set) / len(SSE_trade_dates_period_set) >= 0.9, "底层数据数量和交易所日历相比过少"
#         final_return = df_fund['daily_return'].drop(index=df_fund.index[0])
#     elif freq == "W":
#         final_return = df_fund.resample("W-Fri").last()['cum_daily_return'].pct_change().dropna()
#     elif freq == "M":
#         final_return = df_fund.resample("M").last()['cum_daily_return'].pct_change().dropna()
#     final_return.name = product_id
#     final_return.index = final_return.index.date
#     final_return.index.name = "date"
#     return final_return

# ------------------------------------------------------------------------
# 从amfof中读取referential data
# Author: Zhongheng Shen, 041439
# ------------------------------------------------------------------------
# def amdata_get_hf_product_referential_data_from_amdata():
#
#     sql = "SELECT CODE, NAME, SECU_FUL_NM, INVESTED, MGR, STRATEGY_NM, START_DATE, PERFORM_FEE_TYPE, AMDATA, UPDATE_TIME, AUTHORIZED, " \
#           "DATA_FREQ FROM AMFOF_DEV.V_PRIVATE_FUND_INFO"
#
#     amdata_conn = amdata_connect_amdata_db()
#     df = pd.read_sql_query(sql, amdata_conn)
#     amdata_conn.close()
#
#     return df

# ------------------------------------------------------------------------
# 读取公募核心库
# ------------------------------------------------------------------------
def amdata_getMFCoreList():
    amdata_conn = amdata_connectAmdataDb()
    sql = "SELECT * FROM AMFOF.SRC_PUBLIC_FUND_LABEL"
    df = pd.read_sql_query(sql, amdata_conn).rename(columns=str.lower)
    dic = {'secu_id': 'product_id', 'secu_nm': 'product_shortname', 'fund_investor': 'manager', 'fund_type': 'product_type', 'update_time': 'update_time'}
    df = df.rename(dic, axis = 1)
    amdata_conn.close()
    return df