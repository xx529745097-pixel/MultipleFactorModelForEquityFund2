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

# def backtest(
#         portfolio_df,                  # 每期持仓组合，包含：product_id,date(datetime.date格式),weight
#         end_date
# ):
#     dbconn = wind.wind_connectWindDB()
#     portfolio_df['date'] = portfolio_df['date'].apply(lambda x: x.date())
#     portfolio_df = portfolio_df.sort_values('date')
#     portfolio_df['product_id'] = otc_to_inside(portfolio_df['product_id'].tolist())
#     # portfolio_df['date'] = portfolio_df['date'].apply(lambda x: wind_getLastTradeDates([x])[0])
#     BackTestDates = portfolio_df['date'].unique().tolist()
#     # error_products = []
#     for i in range(len(BackTestDates)):
#         portfolio = portfolio_df[portfolio_df['date'] == BackTestDates[i]]
#         startdate = BackTestDates[i]
#         if i < len(BackTestDates) - 1:
#             enddate = BackTestDates[i + 1]
#         else:
#             enddate = end_date
#
#         sql_code_1 = "select  F_INFO_WINDCODE as product_id, F_NAV_ADJUSTED as nav, PRICE_DATE as trade_date " \
#                      "from  ChinaMutualFundNAV " \
#                      "where  PRICE_DATE >= {0} and PRICE_DATE <= {1} and F_INFO_WINDCODE in {2} "
#         sql_code_2 = "select  S_INFO_WINDCODE as product_id, S_DQ_CLOSE as nav, TRADE_DT as trade_date " \
#                      "from  CMFIndexEOD " \
#                      "where  TRADE_DT >= {0} and TRADE_DT <= {1} and F_INFO_WINDCODE in {2} "
#         codes = portfolio['product_id'].tolist()
#         if len(codes) < 1:
#             return BackTestDates[i] + ' no portfolio'
#         if len(codes) == 1:
#             BackTestReturn_fund = pd.read_sql_query(
#                 sql_code_1.format(startdate.strftime("%Y%m%d"), enddate.strftime("%Y%m%d"), ("F_INFO_WINDCODE = "+codes[0]), dbconn)
#             BackTestReturn_index = pd.read_sql_query(
#                 sql_code_2.format(startdate.strftime("%Y%m%d"), enddate.strftime("%Y%m%d")), ("F_INFO_WINDCODE = "+codes[0]), dbconn)
#         if len(codes) >= 1000:
#             return "单期持仓超过1000只，请使用backtest_1000函数"
#         else:
#             BackTestReturn_fund = pd.read_sql_query(sql_code_1.format(startdate.strftime("%Y%m%d"), enddate.strftime("%Y%m%d"),
#                                                      ("F_INFO_WINDCODE = "+str(tuple(codes))), dbconn)
#             BackTestReturn_index = pd.read_sql_query(sql_code_2.format(startdate.strftime("%Y%m%d"), enddate.strftime("%Y%m%d")),
#                                                      ("F_INFO_WINDCODE = "+str(tuple(codes))), dbconn)
#
#         BackTestReturn = pd.concat([BackTestReturn_fund, BackTestReturn_index])
#         BackTestReturn = pd.merge(BackTestReturn, portfolio[['product_id', 'weight']], how = 'left')
#
#         # 剔除净值披露数据不完整的基金，将持仓均分到同类基金中
#         Trade_days = wind.wind_getSSECalendar()
#         Trade_days = Trade_days[Trade_days['date'] >= startdate]
#         Trade_days = Trade_days[Trade_days['date'] <= enddate]
#         Trade_days['date'] = Trade_days['date'].apply(lambda x: x.strftime("%Y%m%d"))
#         Trade_days.rename(columns = {'date':'trade_date'}, inplace = True)
#         BackTestReturn = pd.merge(BackTestReturn, Trade_days, how = 'inner')
#         fundcodes = BackTestReturn['product_id'].unique()
#         for fundcode in fundcodes:
#             df_temp = BackTestReturn[BackTestReturn['product_id'] == fundcode]
#             if len(df_temp) != len(Trade_days):
#                 class_temp = portfolio[portfolio['product_id'] == fundcode].reset_index()['class'][0]
#                 fund_count = len(portfolio[portfolio['class'] == class_temp])
#                 weight_temp = portfolio[portfolio['product_id'] == fundcode].reset_index()['weight'][0]/(fund_count-1)
#                 portfolio = portfolio[portfolio['product_id'] != fundcode]
#                 portfolio['weight'] = portfolio.apply(lambda x: (x['weight']+weight_temp) if x['class'] == class_temp else x['weight'], axis = 1)
#         BackTestReturn = BackTestReturn.drop('weight', axis = 1)
#         BackTestReturn = pd.merge(BackTestReturn, portfolio[['product_id', 'weight']] , on = 'product_id', how = 'inner')
#
#         def nav_process(x):
#             benchmark = BackTestReturn[BackTestReturn['product_id'] == x['product_id']]
#             benchmark = benchmark[benchmark['trade_date'] == wind_getNextTradeDates([startdate])[0].strftime("%Y%m%d")]
#             try:
#                 return x['nav']/benchmark['nav'].tolist()[0]
#             except Exception as e:
#                 print(BackTestReturn[BackTestReturn['product_id'] == x['product_id']])
#                 print(startdate.strftime("%Y%m%d"))
#
#         BackTestReturn['nav'] = BackTestReturn.apply(nav_process, axis = 1)
#         BackTestReturn['asset_value'] = BackTestReturn['nav']*BackTestReturn['weight']
#         nav_df = BackTestReturn.groupby('trade_date').sum().reset_index()
#         if i == 0:
#             nav_df['asset_value'] = nav_df['asset_value'] / nav_df['asset_value'][0]
#             nav_output = nav_df[['trade_date', 'asset_value']]
#         else:
#             nav_df['asset_value'] = nav_df['asset_value'] / nav_df['asset_value'][0] * nav_output['asset_value'].tolist()[-1]
#             nav_output = pd.merge(nav_output, nav_df[['trade_date', 'asset_value']][1:], how = 'outer')
#             nav_output = nav_output.reset_index(drop = True)
#
#     last_row = 0
#     for i in range(1, len(nav_output)):
#         if abs(nav_output.loc[i, 'asset_value'] / nav_output.loc[last_row, 'asset_value'] - 1) > 0.15:
#             nav_output.drop(index = i, inplace = True)
#         else:
#             last_row = i
#     nav_output.reset_index(drop = True, inplace = True)
#     plt.plot(nav_output['trade_date'], nav_output['asset_value'], label='portfolio')
#     plt.legend()
#     plt.title('portfolio backtest')
#     plt.show()
#     return nav_output

def backtest(portfolio_df, end_date):
    # 1. 预处理持仓数据
    portfolio_df = portfolio_df.copy()
    portfolio_df['date'] = pd.to_datetime(portfolio_df['date']).dt.date

    # 2. 排序并转换产品ID
    portfolio_df = portfolio_df.sort_values('date')
    portfolio_df['product_id'] = otc_to_inside(portfolio_df['product_id'].tolist())
    BackTestDates = portfolio_df['date'].unique()

    # 3. 获取交易日历
    dbconn = wind.wind_connectWindDB()
    Trade_days_df = wind.wind_getSSECalendar()

    # 确保日期列是datetime类型
    if not pd.api.types.is_datetime64_any_dtype(Trade_days_df['date']):
        Trade_days_df['date'] = pd.to_datetime(Trade_days_df['date'])

    # 创建交易日期字符串列
    Trade_days_df['trade_date_str'] = Trade_days_df['date'].dt.strftime("%Y%m%d")

    # 创建交易日集合，用于快速查找
    trade_days_set = set(Trade_days_df['trade_date_str'].tolist())

    # 4. 预取所有产品净值数据
    all_products = portfolio_df['product_id'].unique()
    if len(all_products) == 0:
        return pd.DataFrame(columns=['trade_date', 'asset_value'])

    # 获取所有需要的数据日期范围
    min_date = min(BackTestDates)
    max_date = end_date

    # 优化的净值数据获取函数
    def fetch_nav_data():
        # 基金净值查询
        fund_query = f"""
            SELECT F_INFO_WINDCODE AS product_id, 
                   F_NAV_ADJUSTED AS nav, 
                   PRICE_DATE AS trade_date_str
            FROM ChinaMutualFundNAV 
            WHERE PRICE_DATE >= '{min_date.strftime("%Y%m%d")}' 
              AND PRICE_DATE <= '{max_date.strftime("%Y%m%d")}'
              AND F_INFO_WINDCODE IN ({','.join([f"'{p}'" for p in all_products])})
        """

        # 指数净值查询
        index_query = f"""
            SELECT S_INFO_WINDCODE AS product_id, 
                   S_DQ_CLOSE AS nav, 
                   TRADE_DT AS trade_date_str
            FROM CMFIndexEOD 
            WHERE TRADE_DT >= '{min_date.strftime("%Y%m%d")}' 
              AND TRADE_DT <= '{max_date.strftime("%Y%m%d")}'
              AND S_INFO_WINDCODE IN ({','.join([f"'{p}'" for p in all_products])})
        """

        fund_data = pd.read_sql(fund_query, dbconn)
        index_data = pd.read_sql(index_query, dbconn)

        # 确保索引唯一
        fund_data.reset_index(drop=True, inplace=True)
        index_data.reset_index(drop=True, inplace=True)

        return pd.concat([fund_data, index_data], ignore_index=True)

    all_nav_data = fetch_nav_data()
    all_nav_data.reset_index(drop=True, inplace=True)

    # 5. 主循环优化
    nav_output = pd.DataFrame()
    prev_end_nav = 1.0  # 记录前一期最后净值
    end_date_str = end_date.strftime("%Y%m%d")

    for i, current_date in enumerate(BackTestDates):
        # 5.1 获取当前持仓
        portfolio = portfolio_df[portfolio_df['date'] == current_date].copy()
        start_date = current_date

        # 确定结束日期
        if i < len(BackTestDates) - 1:
            period_end_date = BackTestDates[i + 1]
        else:
            period_end_date = end_date

        # 5.2 筛选当前期的净值数据
        start_str = start_date.strftime("%Y%m%d")
        end_str = period_end_date.strftime("%Y%m%d")

        # 5.3 检查起始日期是否为交易日
        if start_str not in trade_days_set:
            next_trade_days = Trade_days_df[
                (Trade_days_df['trade_date_str'] >= start_str) &
                (Trade_days_df['trade_date_str'] <= end_str)
                ]

            if not next_trade_days.empty:
                adjusted_start_str = next_trade_days.iloc[0]['trade_date_str']
                print(f"信息: 起始日期 {start_str} 不是交易日，使用下一个交易日 {adjusted_start_str} 作为替代")
                start_str = adjusted_start_str
            else:
                print(f"警告: 起始日期 {start_str} 不是交易日，且在该期内没有找到交易日，跳过该期")
                continue

        # 5.4 筛选净值数据
        period_mask = (all_nav_data['trade_date_str'] >= start_str) & \
                      (all_nav_data['trade_date_str'] <= end_str)
        period_data = all_nav_data[period_mask].copy()
        period_data.reset_index(drop=True, inplace=True)

        # 5.5 合并权重数据
        portfolio.reset_index(drop=True, inplace=True)
        period_data = period_data.merge(
            portfolio[['product_id', 'weight']],
            on='product_id',
            how='inner'
        )
        period_data.reset_index(drop=True, inplace=True)

        # 5.6 检查净值完整性
        current_trade_days = Trade_days_df[
            (Trade_days_df['date'] >= pd.Timestamp(start_date)) &
            (Trade_days_df['date'] <= pd.Timestamp(period_end_date))
            ]['trade_date_str'].unique()

        # 5.7 处理不完整产品
        expected_count = len(current_trade_days)
        product_counts = period_data.groupby('product_id')['trade_date_str'].nunique().reset_index()
        incomplete_products = product_counts[product_counts['trade_date_str'] < expected_count]['product_id'].tolist()

        if incomplete_products:
            period_data = period_data[~period_data['product_id'].isin(incomplete_products)]
            portfolio = portfolio[~portfolio['product_id'].isin(incomplete_products)]
            total_removed_weight = portfolio.loc[portfolio['product_id'].isin(incomplete_products), 'weight'].sum()

            if total_removed_weight > 0 and len(portfolio) > 0:
                portfolio['weight'] += total_removed_weight / len(portfolio)
                period_data = period_data.merge(
                    portfolio[['product_id', 'weight']],
                    on='product_id',
                    how='left',
                    suffixes=('', '_new')
                )
                period_data['weight'] = period_data['weight_new']
                period_data.drop(columns=['weight_new'], inplace=True)

        period_data.reset_index(drop=True, inplace=True)

        # 5.8 净值归一化 - 修复索引问题
        # 获取起始日期的净值作为基准，确保每个产品只有一条记录
        start_navs = period_data[period_data['trade_date_str'] == start_str]

        if start_navs.empty:
            available_dates = period_data['trade_date_str'].unique()
            if len(available_dates) > 0:
                available_dates_sorted = sorted(available_dates)
                for date_str in available_dates_sorted:
                    if date_str >= start_str:
                        alternative_start_date = date_str
                        break
                else:
                    alternative_start_date = available_dates_sorted[-1]

                print(f"信息: 在起始日期 {start_str} 没有净值数据，使用替代日期 {alternative_start_date} 作为基准")
                start_navs = period_data[period_data['trade_date_str'] == alternative_start_date]

                if not start_navs.empty:
                    # 确保每个产品只有一条记录
                    start_navs = start_navs.drop_duplicates('product_id').set_index('product_id')['nav']
                else:
                    print(f"警告: 在替代日期 {alternative_start_date} 也没有净值数据，跳过该期")
                    continue
            else:
                print(f"警告: 在日期范围 {start_str} 到 {end_str} 没有可用净值数据，跳过该期")
                continue
        else:
            # 确保每个产品只有一条记录
            start_navs = start_navs.drop_duplicates('product_id').set_index('product_id')['nav']

        # 创建基准净值映射，确保索引唯一
        nav_base = start_navs

        # 使用更安全的合并方法替代map
        period_data = period_data.merge(
            nav_base.reset_index().rename(columns={'nav': 'base_nav'}),
            on='product_id',
            how='left'
        )

        # 避免除以零错误
        period_data['normalized_nav'] = period_data['nav'] / period_data['base_nav'].replace(0, np.nan)

        # 5.9 计算资产价值
        period_data['asset_value'] = period_data['normalized_nav'] * period_data['weight']
        daily_nav = period_data.groupby('trade_date_str', as_index=False)['asset_value'].sum()
        daily_nav = daily_nav.rename(columns={'trade_date_str': 'trade_date'})
        daily_nav.reset_index(drop=True, inplace=True)

        if daily_nav.empty:
            print(f"警告: 在日期 {start_date} 到 {period_end_date} 期间没有净值数据，跳过该期")
            continue

        # 6.0 连接净值曲线
        start_value = daily_nav['asset_value'].iloc[0]
        if abs(start_value) < 1e-8:
            print(f"警告: 起始资产价值接近零 ({start_value:.6f})，跳过该期: {start_date} 到 {period_end_date}")
            continue

        if nav_output.empty:
            daily_nav['asset_value'] /= start_value
            nav_output = daily_nav[['trade_date', 'asset_value']].copy()
            nav_output.reset_index(drop=True, inplace=True)
        else:
            # 排除起始日以避免重复
            if len(daily_nav) > 1:
                daily_nav = daily_nav.iloc[1:]

            daily_nav['asset_value'] = daily_nav['asset_value'] / start_value * prev_end_nav
            nav_output = pd.concat([nav_output, daily_nav], ignore_index=True)

        prev_end_nav = nav_output['asset_value'].iloc[-1]

    # 7. 确保包含到end_date的数据
    if not nav_output.empty:
        last_trade_date = nav_output['trade_date'].iloc[-1] if len(nav_output) > 0 else None
        if last_trade_date != end_date_str:
            end_date_data = all_nav_data[all_nav_data['trade_date_str'] == end_date_str].copy()

            if not end_date_data.empty:
                last_portfolio = portfolio_df[portfolio_df['date'] == BackTestDates[-1]]
                end_date_data = end_date_data.merge(
                    last_portfolio[['product_id', 'weight']],
                    on='product_id',
                    how='inner'
                )

                # 使用最后一天的净值计算
                end_date_data['asset_value'] = end_date_data['nav'] * end_date_data['weight']
                daily_value = end_date_data['asset_value'].sum()

                # 添加到输出
                new_row = pd.DataFrame({
                    'trade_date': [end_date_str],
                    'asset_value': [daily_value]
                })
                nav_output = pd.concat([nav_output, new_row], ignore_index=True)

    # 8. 过滤异常波动
    if not nav_output.empty:
        nav_output.reset_index(drop=True, inplace=True)
        nav_output['pct_change'] = nav_output['asset_value'].pct_change().abs().fillna(0)
        nav_output = nav_output[nav_output['pct_change'] <= 0.15]
        nav_output.drop(columns=['pct_change'], inplace=True)
        nav_output.reset_index(drop=True, inplace=True)

    # 9. 结果可视化
    if not nav_output.empty:
        # 确保日期唯一
        nav_output = nav_output.drop_duplicates(subset='trade_date', keep='last')
        nav_output['trade_date_dt'] = pd.to_datetime(nav_output['trade_date'], format='%Y%m%d')
        nav_output = nav_output.sort_values('trade_date_dt')
        nav_output.reset_index(drop=True, inplace=True)

        plt.figure(figsize=(12, 6))
        plt.plot(nav_output['trade_date_dt'], nav_output['asset_value'], label='portfolio')
        plt.legend()
        plt.title('portfolio backtest')
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.show()

    return nav_output[['trade_date', 'asset_value']] if not nav_output.empty else pd.DataFrame()

Class = 'HandF'
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