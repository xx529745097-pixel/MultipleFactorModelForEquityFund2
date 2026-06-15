# ------------------------------------------------------------------------------------------
# This file contains the functions used to interact with
# IRM database 研究平台数据库
# 注：IRM数据库基于MySql, sql语句是区分大小写的, 表名前缀irm必须是小写, 列名需根据实际情况, 目前都是大写
# ------------------------------------------------------------------------------------------
import pymysql

# ------------------------------------------------------------------------
# IRM database connection
# ------------------------------------------------------------------------
def irm_connectIRMDB():
    conn = pymysql.connect(user="fofuser@IRM#obcloud01", password="Fofirm2023", host="10.80.138.38", port=28830, database="irm", charset='utf8')
    return conn

# ------------------------------------------------------------------------
# 向IRM数据库写入数据
# ------------------------------------------------------------------------
def irm_insertIRMData(
    dataframe,      # 需要写入的数据
    table_name,     # 需要写入的表格的名字，例如：IRM.AMFOF_INDEX_YIELD_INFO
):
    conn = irm_connectIRMDB()
    keys = ', '.join(dataframe.iloc[0, :].keys())  # 第一行就是对应的列名
    values = ', '.join(
        ["%s" for i in range(1, len(dataframe.dtypes) + 1)])  # pymysql的executemany需要拼接成(%s,%s,......)的形式
    insert_sql = 'INSERT INTO {table} ({keys}) VALUES ({values})'.format(
        table=table_name,
        keys=keys,
        values=values
    )
    # 建立游标
    cursor = conn.cursor()
    # 　批量插入，将结果数据转为列表嵌套列表
    data_total_list = dataframe.values.tolist()
    #   转成元组列表
    data_total_list_tuple = [tuple(data) for data in data_total_list]
    try:
        cursor.executemany(insert_sql, data_total_list_tuple)
        conn.commit()
        print('success')
        cursor.close()
    except Exception as e:
        print('Failed:' + str(e))


# # ------------------------------------------------------------------------
# # 如何删除数据的例子
# # ------------------------------------------------------------------------
# conn = irm_connect()
# sql = "DELETE FROM irm.AMFOF_INDEX_YIELD_INFO WHERE dt = DATE'2022-04-21'"
# cur = conn.cursor()
# cur.execute(sql)
# conn.commit()
