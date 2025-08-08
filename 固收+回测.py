import os.path
import time

import pandas as pd
import datetime
from dateutil.relativedelta import relativedelta
import numpy as np
import sqlalchemy
from dateutil.parser import parse
from matplotlib import pyplot as plt
import src.utils.Calculation as Cal
import src.data.wind as wind
import src.analysis.MFAnalysis as MFanls
import src.utils.backtest as bt
import fstrat_config
import warnings
warnings.filterwarnings('ignore')
import pulp


def towindcode(x):
    if x[0] == '1':
        x = x[:-2] + 'SZ'
    if x[0] == '5':
        x = x[:-2] + 'SH'
    return x

def otc_to_inside(list1):
    import sqlalchemy
    import os

    os.environ['NLS_LANG'] = 'SIMPLIFIED CHINESE_CHINA.UTF8'
    ora_connect_str  = 'oracle://xujunwei:40!VEz6QX@10.23.153.15:21010/wind'
    dbengine = sqlalchemy.create_engine(ora_connect_str, poolclass=sqlalchemy.pool.NullPool)
    dbconn = dbengine.connect()
    sql = "select F_INFO_WINDCODE " \
          "from ChinaMutualFundDescription "
    df = pd.read_sql_query(sql, dbconn)
    list2 = df['f_info_windcode'].tolist()
    for i in range(len(list1)):
        if list1[i] not in list2:
            list1[i] = towindcode(list1[i])
    return list1

def wind_getNextTradeDates(
        list_of_dates      # 输入list。
):
    calender = wind.wind_getSSECalendar()
    df_of_dates = pd.DataFrame({'date': list_of_dates})
    df_of_dates['trade_date'] = df_of_dates['date'].apply(lambda x: min(calender[calender['date'] >= x]['date']))
    return df_of_dates['trade_date'].tolist()


def backtest(
        portfolio_df,                  # 每期持仓组合，包含：product_id,date(datetime.date格式),weight
        end_date
):
    dbconn = wind.wind_connectWindDB()
    portfolio_df['date'] = portfolio_df['date'].apply(lambda x: x.date())
    portfolio_df = portfolio_df.sort_values('date')
    portfolio_df['product_id'] = otc_to_inside(portfolio_df['product_id'].tolist())
    # portfolio_df['date'] = portfolio_df['date'].apply(lambda x: wind_getLastTradeDates([x])[0])
    BackTestDates = portfolio_df['date'].unique().tolist()
    # error_products = []
    for i in range(len(BackTestDates)):
        portfolio = portfolio_df[portfolio_df['date'] == BackTestDates[i]]
        startdate = BackTestDates[i]
        if i < len(BackTestDates) - 1:
            enddate = BackTestDates[i + 1]
        else:
            enddate = end_date

        sql_code_1 = "select  F_INFO_WINDCODE as product_id, F_NAV_ADJUSTED as nav, PRICE_DATE as trade_date " \
                     "from  ChinaMutualFundNAV " \
                     "where  PRICE_DATE >= {0} and PRICE_DATE <= {1} "
        sql_code_2 = "select  S_INFO_WINDCODE as product_id, S_DQ_CLOSE as nav, TRADE_DT as trade_date " \
                     "from  CMFIndexEOD " \
                     "where  TRADE_DT >= {0} and TRADE_DT <= {1} "
        codes = portfolio['product_id'].tolist()
        if len(codes) < 1:
            return BackTestDates[i] + ' no portfolio'
        BackTestReturn_fund = pd.read_sql_query(sql_code_1.format(startdate.strftime("%Y%m%d"), enddate.strftime("%Y%m%d")), dbconn)
        BackTestReturn_fund = BackTestReturn_fund[BackTestReturn_fund['product_id'].isin(codes)]
        BackTestReturn_index = pd.read_sql_query(sql_code_2.format(startdate.strftime("%Y%m%d"), enddate.strftime("%Y%m%d")), dbconn)
        BackTestReturn_index = BackTestReturn_index[BackTestReturn_index['product_id'].isin(codes)]

        BackTestReturn = pd.concat([BackTestReturn_fund, BackTestReturn_index])
        BackTestReturn = pd.merge(BackTestReturn, portfolio[['product_id', 'weight']], how = 'left')

        # 剔除净值披露数据不完整的基金，将持仓均分到同类基金中
        Trade_days = wind.wind_getSSECalendar()
        Trade_days = Trade_days[Trade_days['date'] >= startdate]
        Trade_days = Trade_days[Trade_days['date'] <= enddate]
        Trade_days['date'] = Trade_days['date'].apply(lambda x: x.strftime("%Y%m%d"))
        Trade_days.rename(columns = {'date':'trade_date'}, inplace = True)
        BackTestReturn = pd.merge(BackTestReturn, Trade_days, how = 'inner')
        fundcodes = BackTestReturn['product_id'].unique()
        for fundcode in fundcodes:
            df_temp = BackTestReturn[BackTestReturn['product_id'] == fundcode]
            if len(df_temp) != len(Trade_days):
                class_temp = portfolio[portfolio['product_id'] == fundcode].reset_index()['class'][0]
                fund_count = len(portfolio[portfolio['class'] == class_temp])
                weight_temp = portfolio[portfolio['product_id'] == fundcode].reset_index()['weight'][0]/(fund_count-1)
                portfolio = portfolio[portfolio['product_id'] != fundcode]
                portfolio['weight'] = portfolio.apply(lambda x: (x['weight']+weight_temp) if x['class'] == class_temp else x['weight'], axis = 1)
        BackTestReturn = BackTestReturn.drop('weight', axis = 1)
        BackTestReturn = pd.merge(BackTestReturn, portfolio[['product_id', 'weight']] , on = 'product_id', how = 'inner')

        def nav_process(x):
            benchmark = BackTestReturn[BackTestReturn['product_id'] == x['product_id']]
            benchmark = benchmark[benchmark['trade_date'] == wind_getNextTradeDates([startdate])[0].strftime("%Y%m%d")]
            try:
                return x['nav']/benchmark['nav'].tolist()[0]
            except Exception as e:
                print(BackTestReturn[BackTestReturn['product_id'] == x['product_id']])
                print(startdate.strftime("%Y%m%d"))

        BackTestReturn['nav'] = BackTestReturn.apply(nav_process, axis = 1)
        BackTestReturn['asset_value'] = BackTestReturn['nav']*BackTestReturn['weight']
        nav_df = BackTestReturn.groupby('trade_date').sum().reset_index()
        if i == 0:
            nav_df['asset_value'] = nav_df['asset_value'] / nav_df['asset_value'][0]
            nav_output = nav_df[['trade_date', 'asset_value']]
        else:
            nav_df['asset_value'] = nav_df['asset_value'] / nav_df['asset_value'][0] * nav_output['asset_value'].tolist()[-1]
            nav_output = pd.merge(nav_output, nav_df[['trade_date', 'asset_value']][1:], how = 'outer')
            nav_output = nav_output.reset_index(drop = True)

    last_row = 0
    for i in range(1, len(nav_output)):
        if abs(nav_output.loc[i, 'asset_value'] / nav_output.loc[last_row, 'asset_value'] - 1) > 0.15:
            nav_output.drop(index = i, inplace = True)
        else:
            last_row = i
    nav_output.reset_index(drop = True, inplace = True)
    plt.plot(nav_output['trade_date'], nav_output['asset_value'], label='portfolio')
    plt.legend()
    plt.title('portfolio backtest')
    plt.show()
    return nav_output

Class = 'L'
df1 = pd.read_excel('债基-输出结果/固收+基金打分结果_2024-07-01_{}.xlsx'.format(Class))
df2 = pd.read_excel('债基-输出结果/固收+基金打分结果_2024-10-01_{}.xlsx'.format(Class))
df3 = pd.read_excel('债基-输出结果/固收+基金打分结果_2025-01-01_{}.xlsx'.format(Class))
df4 = pd.read_excel('债基-输出结果/固收+基金打分结果_2025-04-01_{}.xlsx'.format(Class))
df1 = df1.sort_values('score_x')
df2 = df2.sort_values('score_x')
df3 = df3.sort_values('score_x')
df4 = df4.sort_values('score_x')

## top20%
df1_top = df1[:len(df1)//5][['date','product_id','product_name']]
df1_top['weight'] = 1/len(df1_top)
df2_top = df2[:len(df2)//5][['date','product_id','product_name']]
df2_top['weight'] = 1/len(df2_top)
df3_top = df3[:len(df3)//5][['date','product_id','product_name']]
df3_top['weight'] = 1/len(df3_top)
df4_top = df4[:len(df4)//5][['date','product_id','product_name']]
df4_top['weight'] = 1/len(df4_top)
df_top = pd.concat([df1_top, df2_top, df3_top, df4_top]).reset_index(drop = True)
df_top['class'] = 1
## bottom20%
df1_bottom = df1[-len(df1)//5:][['date','product_id','product_name']]
df1_bottom['weight'] = 1/len(df1_bottom)
df2_bottom = df2[-len(df2)//5:][['date','product_id','product_name']]
df2_bottom['weight'] = 1/len(df2_bottom)
df3_bottom = df3[-len(df3)//5:][['date','product_id','product_name']]
df3_bottom['weight'] = 1/len(df3_bottom)
df4_bottom = df4[-len(df4)//5:][['date','product_id','product_name']]
df4_bottom['weight'] = 1/len(df4_bottom)
df_bottom = pd.concat([df1_bottom, df2_bottom, df3_bottom, df4_bottom]).reset_index(drop = True)
df_bottom['class'] = 1

df_top['product_id'] = otc_to_inside(df_top['product_id'])
df_bottom['product_id'] = otc_to_inside(df_bottom['product_id'])
nav_df1 = backtest(df_top, datetime.date(2025,7, 1))
nav_df1.to_excel('债基-输出结果/top20%回测-{}.xlsx'.format(Class))
nav_df2 = backtest(df_bottom, datetime.date(2025,7, 1))
nav_df2.to_excel('债基-输出结果/bottom20%回测-{}.xlsx'.format(Class))