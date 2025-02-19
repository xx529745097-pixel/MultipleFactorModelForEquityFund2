import pandas as pd
import datetime
from dateutil.relativedelta import relativedelta
import numpy as np
import sqlalchemy
from dateutil.parser import parse
from matplotlib import pyplot as plt
# import Calculation as Cal
# import wind

class dbaseConn():
       def __init__(self):
              ora_connect_str = "oracle://wangnanhao:40!VEz6QX@10.23.153.15:21010/wind"
              self.dbengine = sqlalchemy.create_engine(ora_connect_str, poolclass=sqlalchemy.pool.NullPool)
              return

def adjustDate(lkbk,freqi,date):
       db = dbaseConn()
       dbconn = db.dbengine.connect()

       sql = "select TRADE_DAYS " \
             "from AShareCalendar " \
             "where S_INFO_EXCHMARKET = 'SSE' and TRADE_DAYS > 20100101 and TRADE_DAYS <= '{}' " \
             "order by TRADE_DAYS"

       Tdates = pd.read_sql_query(sql.format(date), dbconn)
       Tdates['year'] = Tdates['trade_days'].str[:4]
       Tdates['month'] = Tdates['trade_days'].str[4:6]

       # 设定换仓节点，取月末最后一个交易日
       if freqi == 'Q':
           Tdates = Tdates.loc[Tdates['month'].isin(['01', '04', '07', '10'])].reset_index(drop=True)
       if freqi == 'Y':
           Tdates = Tdates.loc[Tdates['month'].isin(['01'])].reset_index(drop=True)
       if freqi == '2Q':
           Tdates = Tdates.loc[Tdates['month'].isin(['01', '07'])].reset_index(drop=True)

       adjustDate = Tdates.groupby(['year', 'month'])[['trade_days']].last()
       adjustDate.columns = ['date']
       adjustDate.reset_index(drop=True, inplace=True)
       adjustDate = adjustDate[['date']].astype(int)
       adjustDate['sdate'] = adjustDate['date'] + lkbk
       adjustDate = adjustDate.loc[adjustDate['date'] > 20140101].reset_index(drop=True)
       adjustDate = adjustDate[['sdate', 'date']]

       return adjustDate

def dataPrepare(today):
       db = dbaseConn()
       dbconn = db.dbengine.connect()
       # length(a.f_info_windcode)!=10，带！的(11位)不能去，只把带F的（10位）去掉。带！的是转型过的基金，F开头的是香港互认基金
       # a.F_INFO_ISINITIAL =1，只考虑初始份额，A份额
       # 基于df_fund去构建fundUniverse，所以把df_fund的范围约定的最严格即可，比如考虑历史的基金分类
       sql_fund = "select a.f_info_windcode as fcode,a.F_INFO_SETUPDATE as sdate,a.F_INFO_MATURITYDATE as edate," \
                  " b.F_INFO_FUNDMANAGER as fmname,b.F_INFO_MANAGER_STARTDATE as fmsdate,b.F_INFO_MANAGER_LEAVEDATE as fmedate, " \
                  " c.S_INFO_SECTOR as type, c.S_INFO_SECTORENTRYDT as sector_sdate, c.S_INFO_SECTOREXITDT as sector_edate " \
                  " from (select * from ChinaMutualFundDescription )a, (select * from ChinaMutualFundManager)b,(select * from ChinaMutualFundSector)c" \
                  " where a.f_info_windcode=b.f_info_windcode and a.f_info_windcode=c.f_info_windcode and length(a.f_info_windcode)!=10" \
                  " and a.F_INFO_ISINITIAL =1 and c.S_INFO_SECTOR in ('2001010101000000','2001010201000000','2001010204000000')" \
                  " order by a.f_info_windcode,b.F_INFO_MANAGER_STARTDATE"


       df_fund = pd.read_sql_query(sql_fund, dbconn)
       df_fund.replace({"type": {"2001010101000000": "普通股票型", "2001010201000000": "偏股混合型基金", "2001010204000000": "灵活配置型基金"}}, inplace=True)
       df_fund["fmedate"] = df_fund["fmedate"].fillna(today)
       df_fund['sector_edate'] = df_fund['sector_edate'].fillna(today)

       df_fund = df_fund.loc[df_fund['fmsdate'].notnull()].reset_index(drop=True)
       df_fund = df_fund.loc[df_fund['fmedate'].notnull()].reset_index(drop=True)
       df_fund = df_fund.loc[df_fund['sector_sdate'].notnull()].reset_index(drop=True)
       df_fund = df_fund.loc[df_fund['sector_edate'].notnull()].reset_index(drop=True)
       df_fund[["fmedate", "fmsdate", "sector_sdate", "sector_edate"]] = df_fund[["fmedate", "fmsdate", "sector_sdate", "sector_edate"]].astype("int")

       # 提取合并资产净值，根据发布日期导出，并ffill na
       sql_aum = "select a.f_info_windcode as fcode,b.ann_date as adate,b.netasset_total as taum" \
                 " from (select * from ChinaMutualFundDescription where length(f_info_windcode)!=10 and f_info_isinitial =1 )a," \
                 " (select * from ChinaMutualFundNAV)b," \
                 "(select * from ChinaMutualFundSector where s_info_sector in ('2001010101000000','2001010201000000','2001010204000000'))c" \
                 " where a.f_info_windcode=b.f_info_windcode and a.f_info_windcode=c.f_info_windcode " \
                 " order by a.f_info_windcode,b.price_date"

       df_aum = pd.read_sql_query(sql_aum, dbconn)
       df_aum["adate"] = df_aum["adate"].astype("int")

       df_aum_unstack = df_aum.pivot_table(values="taum",index="adate",columns="fcode")
       df_aum_unstack = df_aum_unstack.fillna(method="ffill")

       # 复权净值，考虑分红再投资
       sql_nav = "select a.f_info_windcode as fcode,b.price_date as tdate,b.F_NAV_ADJUSTED as nav" \
                 " from (select * from ChinaMutualFundDescription )a, (select * from ChinaMutualFundNAV where price_date>20140101)b,(select * from ChinaMutualFundSector)c" \
                 " where a.f_info_windcode=b.f_info_windcode and a.f_info_windcode=c.f_info_windcode and length(a.f_info_windcode)!=10" \
                 " and a.F_INFO_ISINITIAL =1 and c.S_INFO_SECTOR in ('2001010101000000','2001010201000000','2001010204000000') " \
                 " order by a.f_info_windcode,b.price_date"
        
       df_nav = pd.read_sql_query(sql_nav, dbconn)
        
       sql_dt = "select trade_days as tdate from AShareCalendar where S_INFO_EXCHMARKET='SSE' and trade_days>20140101 "\
                " and trade_days<= '{}' order by trade_days"
       df_date = pd.read_sql_query(sql_dt.format(today), dbconn)
       df_date = df_date.set_index("tdate")
       df_date.index = df_date.index.astype("int")
       dbconn.close()

       df_aum = pd.merge(df_date, df_aum_unstack, how='left', left_index=True, right_index=True)
       df_aum = df_aum.fillna(method="ffill")
       
       return df_fund, df_aum, df_nav, df_date
   
def loopMain(df_fund,df_aum,lkbki,freqi,today):


       ads = adjustDate(lkbki[1],freqi,today)

       fundId = np.unique(df_fund["fcode"])
       fundUniverse = pd.DataFrame(columns=["date", "fcode"])
       for codei in fundId:
          data_temp = df_fund.query("fcode == @codei").copy()
          if data_temp['fmedate'].max()<ads.iat[0,1]:
              continue
          for i, ini in enumerate(ads["date"]):
              sdate_temp = ads.iat[i, 0]
              edate_temp = ads.iat[i, 1]
              if data_temp.query("(fmsdate<@sdate_temp)&(fmedate>=@edate_temp)").shape[0] > 0: # 任何一个基金经理任职超过一年
                  temp = data_temp.query("(fmsdate<@sdate_temp)&(fmedate>=@edate_temp)")
                  if temp.query("(sector_sdate<=@edate_temp)&(sector_edate>=@edate_temp)").shape[0] > 0: # 满足上一个条件的基金中，edate时是股票或偏股基金
                    fundUniverse = pd.concat(
                           [fundUniverse, pd.DataFrame([ini, codei], index=["date", "fcode"]).T])
        

       fundUniverse["curQ"] = np.nan
       fundUniverse.reset_index(drop=True, inplace=True)

       for ci, codei in enumerate(fundUniverse.index):
           try:
               fundUniverse.iat[ci,2] = df_aum[fundUniverse.iat[ci,1]].loc[fundUniverse.iat[ci,0]]
           except:
               continue

       fundUniverse = fundUniverse.query("curQ>200000000").reset_index(drop=True)
       fundUniverse = fundUniverse.drop("curQ", 1)

       db = dbaseConn()
       dbconn = db.dbengine.connect()
       sql = "select a.S_INFO_WINDCODE as fcode, a.F_PRT_ENDDATE as edate, a.F_PRT_STOCKTONAV as stktonav " \
             "from (select * from ChinaMutualFundAssetPortfolio)a, " \
             "(select * from ChinaMutualFundSector where s_info_sector in ('2001010101000000','2001010201000000','2001010204000000'))c " \
             "where a.S_INFO_WINDCODE=c.F_INFO_WINDCODE " \
             "order by a.S_INFO_WINDCODE,a.F_PRT_ENDDATE"
       StktoNav = pd.read_sql_query(sql, dbconn)
       StktoNav = StktoNav.drop_duplicates(subset=['fcode','edate']).reset_index(drop=True)
       df_stktonav = StktoNav.groupby('fcode')['stktonav'].rolling(window=4).mean().reset_index()[['fcode', 'stktonav']]
       df_stktonav['edate'] = StktoNav['edate']
       df_stktonav['stktonav'].fillna(method='backfill', inplace=True)
       df_stktonav['adate'] = pd.to_datetime(df_stktonav['edate']).dt.date + relativedelta(months=1)
       df_stktonav['year'] = pd.to_datetime(df_stktonav['adate']).dt.year
       df_stktonav['month'] = pd.to_datetime(df_stktonav['adate']).dt.month

       fundUniverse['adate'] = pd.to_datetime(fundUniverse['date'].astype(str)).dt.date
       fundUniverse['year'] = pd.to_datetime(fundUniverse['adate']).dt.year
       fundUniverse['month'] = pd.to_datetime(fundUniverse['adate']).dt.month

       fundUniverse = pd.merge(fundUniverse, df_stktonav[['year','month','fcode','stktonav']], how='left', on=['year','month','fcode'])
       fundUniverse = fundUniverse.loc[fundUniverse['stktonav'] >= 50].reset_index(drop=True)
       fundUniverse = fundUniverse[['date','fcode']]


       return fundUniverse

def ranking(fund,lkbk,stable = True):
#    定义最新日期
    import WindPy as w
    w.w.start()

#    wind db 环境配置
    db = dbaseConn()
    dbconn = db.dbengine.connect()

    today = int(datetime.date.today().strftime("%Y%m%d"))

    sql = "select TRADE_DAYS " \
          "from AShareCalendar " \
          "where S_INFO_EXCHMARKET = 'SSE' and TRADE_DAYS > 20100101 and TRADE_DAYS <= '{}' " \
          "order by TRADE_DAYS"

    Tdates = pd.read_sql_query(sql.format(today), dbconn)
    Tdates['year'] = Tdates['trade_days'].str[:4]
    Tdates['month'] = Tdates['trade_days'].str[4:6]
    Tdates['week'] = pd.to_datetime(Tdates['trade_days']).dt.isocalendar().week
    Tdates['year'] = Tdates['year'].astype(int)
    Tdates.loc[(Tdates['month'] == '12') & (Tdates['week'] == 1), 'year'] += 1 # 解决某年最后几天是下一年第一周的问题
    Weekdays = Tdates.groupby(['year', 'week'])[['trade_days']].last()
    Weekdays.reset_index(drop=True, inplace=True)

    date_list = (fund['date'].sort_values().unique()).tolist()

    output = pd.DataFrame()
    output_dfx = pd.DataFrame()
    for date in date_list:
        temp = fund.loc[fund['date'] == date].reset_index(drop=True)

        WSS = w.w.wss([','.join(temp['fcode'])], "risk_jensen,risk_sharpe,risk_stock,risk_time","startDate=" + str(int(date) + lkbk) + ";endDate=" + str(date) + ";period=2;returnType=1;riskFreeRate=1;index=000001.SH")
        df = pd.DataFrame(WSS.Data, index=WSS.Fields, columns=WSS.Codes).T
        WSS = w.w.wss([','.join(temp['fcode'])],  "fund_dq_status", "tradeDate=" + str(date))
        df_status = pd.DataFrame(WSS.Data, index=WSS.Fields, columns=WSS.Codes).T

        if len(temp['fcode']) < 1000:
            sql = "select F_INFO_WINDCODE as fcode, PRICE_DATE as fdate, F_NAV_ADJUSTED as nav_adj " \
                  "from ChinaMutualFundNAV " \
                  "where F_INFO_WINDCODE in {} " \
                  "and PRICE_DATE >= '{}' and PRICE_DATE <= '{}' " \
                  "order by F_INFO_WINDCODE, PRICE_DATE"
            nav_daily = pd.read_sql_query(sql.format(tuple(temp['fcode']), str(int(date) + lkbk), str(date)), dbconn)
        else: # 长度大于1000时sql IN 会超限
            sql = "select F_INFO_WINDCODE as fcode, PRICE_DATE as fdate, F_NAV_ADJUSTED as nav_adj " \
                  "from ChinaMutualFundNAV " \
                  "where PRICE_DATE >= '{}' and PRICE_DATE <= '{}' " \
                  "order by F_INFO_WINDCODE, PRICE_DATE"

            nav_daily = pd.read_sql_query(sql.format(str(int(date) + lkbk), str(date)), dbconn)
            nav_daily = nav_daily.loc[nav_daily['fcode'].isin(temp['fcode'])].reset_index(drop=True)

        nav_weekly = nav_daily.loc[nav_daily['fdate'].isin(Weekdays['trade_days'])]
        nav_weekly = pd.pivot_table(nav_weekly, columns='fcode', index='fdate', values='nav_adj')
        nav_weekly = nav_weekly.fillna(method='ffill')

        ret_weekly = nav_weekly.diff(1)/nav_weekly.iloc[:,:].shift(1)
        ret_weekly = ret_weekly.T
        ret_weekly = round(ret_weekly, 12) # 调整精度

        ret_weekly_rank = ret_weekly.rank(ascending=True, method='min')
        ret_weekly_sharpe = ret_weekly_rank.mean(axis=1)/ret_weekly_rank.std(axis=1)
        ret_weekly_sharpe = round(ret_weekly_sharpe, 12)  # 调整精度
        df['stability'] = ret_weekly_sharpe

        dfx = pd.DataFrame(df)
        dfx['date'] = date
        df_rank = df.rank(ascending=True, method='min')
        # df_rank['NETASSET_TOTAL'] = df['NETASSET_TOTAL'].rank(ascending=False, method='min') # Size 逆序
        # df_rank['BETA'] = df['BETA'].rank(ascending=False, method='min')  # Size 逆序

        if stable:
            df_rank['score'] = df_rank['RISK_JENSEN'] * 0.2 + df_rank['RISK_SHARPE'] * 0.4 + df_rank[
                'RISK_STOCK'] * 0.1 + df_rank['RISK_TIME'] * 0.1 + df_rank['stability'] * 0.2
        else:
               df_rank['score'] = df_rank['RISK_CALMAR'] * 0.2 + df_rank['RISK_JENSEN'] * 0.2 + df_rank[
                      'RISK_TIME'] * 0.2 + df_rank['NETASSET_TOTAL'] * 0.2
        # df_rank['star'] = df_rank[['score']].apply(lambda x: pd.qcut(x, q=[0, 0.1, 0.325, 0.675, 0.9, 1], labels=[1,2,3,4,5]))
        df_rank['status'] = df_status
        df_rank.sort_values(by='score', ascending=False, inplace=True)
        result = df_rank[['score', 'status']].reset_index()
        result['score'] = round(result['score'], 2)
        result['date'] = date
        result.columns = ['fcode', 'score', 'status', 'date']
        WSS = w.w.wss([','.join(result['fcode'])], "fund_fundmanageroftradedate", "tradeDate=" + str(date))
        result['pm'] = pd.DataFrame(WSS.Data).T
        WSS = w.w.wss([','.join(result['fcode'])], "netasset_total", "unit=1;tradeDate=" + str(date))
        result['nav'] = pd.DataFrame(WSS.Data).T
        WSS = w.w.wss([','.join(result['fcode'])], "sec_name")
        result['product_name'] = pd.DataFrame(WSS.Data).T
        result = result.sort_values(by=['score', 'nav'], ascending=False).reset_index(drop=True)
        # result = result.loc[(result['status'] == ('开放申购|开放赎回')) | (result['status'] == ('暂停大额申购|开放赎回'))].reset_index(drop=True)
        result = result.loc[result['status'] == ('开放申购|开放赎回')].reset_index(drop=True)
        result = result.loc[(~result['product_name'].str.contains('定开')) & (~result['product_name'].str.contains('持有'))].reset_index(drop=True)
        result.drop_duplicates(subset=['pm'], inplace=True)
        result = result[['fcode', 'score', 'status', 'date', 'nav']]

        output = output.append(result).reset_index(drop=True)
        result.index=result['fcode']
        output_dfx = output_dfx.append(dfx)
    w.w.stop()
    output_dfx.to_excel('result_total.xlsx')
    return output
   
def strategy(input,numoffund):
    output = input[~pd.isnull(input["status"])]
    # output = output.loc[(~output['status'].str.contains('暂停申购')) & (~output['status'].str.contains('暂停赎回'))
    #                   & (~output['status'].str.contains('封闭期'))]
    # output = output.loc[(output['status'].str.contains('开放申购')) & (output['status'].str.contains('开放赎回'))]

    # portfolio = output.groupby("date").apply(lambda x: x.sort_values(by="score",ascending = False).iloc[:numoffund])
    # portfolio = portfolio.set_index("date").reset_index()
    # portfolio = portfolio[["date","fcode"]].copy()
    # return portfolio

    date_list = output['date'].unique()
    portfolio = output.loc[output['date'] == date_list[0]].sort_values(by='score', ascending=False).iloc[:numoffund].reset_index(drop=True)
    portfolio = portfolio[['date', 'fcode', 'score','status','nav']]

    # 缓冲池
    for i, date in enumerate(date_list[1:]):
        portfolio_new = output.loc[output['date'] == date].sort_values(by='score', ascending=False).iloc[:int(numoffund*3)].reset_index(drop=True).copy()
        portfolio_old = portfolio.loc[portfolio['date'] == date_list[i]].copy()
        portfolio_old['old_score'] = 10000000000000
        target = pd.merge(portfolio_new, portfolio_old[['fcode', 'old_score']], how='left', on=['fcode'])
        target['old_score'].fillna(0, inplace=True)
        target['score'] = target['score'] + target['old_score']
        target['score'] = round(target['score'], 2)
        target = target.sort_values(by=['score','nav'], ascending=[False, False]).iloc[:numoffund]
        # target = target[['date', 'fcode']]
        portfolio = portfolio.append(target)

    portfolio.reset_index(drop=True, inplace=True)
    weight = portfolio.groupby('date')['fcode'].apply(lambda x: 1 / len(x)).to_frame().rename(columns={'fcode': 'weight'}).reset_index()
    weight['date'] = weight['date'].astype(int)
    portfolio = pd.merge(portfolio, weight, on='date', how='left')

    return portfolio

def backTesting(df_fund):
    db = dbaseConn()
    dbconn = db.dbengine.connect()
    df_fund['date'] = df_fund['date'].astype(int)
    calDate = pd.DataFrame(df_fund['date'].unique(), columns=['calDate'])  # 计算日

    today = datetime.date.today().strftime("%Y%m%d")

    # A股交易日历;SSE:上海交易所 SZSE:深圳交易所 SHN:沪股通 SZN:深股通
    sql = "select TRADE_DAYS " \
          "from AShareCalendar " \
          "where S_INFO_EXCHMARKET = 'SSE' " \
          "order by TRADE_DAYS"

    AShareCalendar = pd.read_sql_query(sql, dbconn).astype(int)
    df_fund_days = pd.merge(AShareCalendar, calDate, left_on=['trade_days'], right_on=['calDate'], how='left')
    df_fund_days['adjustDate'] = df_fund_days['trade_days'].shift(-1)  # 第一个交易日换仓
    df_fund_days.dropna(inplace=True)
    df_fund_days.reset_index(drop=True, inplace=True)
    df_fund_days = df_fund_days.astype(int)
    df_fund_days.drop(['trade_days'], axis=1, inplace=True)

    df_fund = pd.merge(df_fund, df_fund_days, left_on=['date'], right_on=['calDate'], how='left')
    df_fund.drop(['date'], axis=1, inplace=True)

    ZX30index = AShareCalendar.loc[(AShareCalendar['trade_days'] >= df_fund_days['adjustDate'][0])
                                   & (AShareCalendar['trade_days'] <= int(today))].reset_index(drop=True)
    ZX30index['index'] = 1000

    ZX30index = pd.merge(ZX30index, df_fund_days, left_on=['trade_days'], right_on=['adjustDate'], how='left')
    ZX30index.fillna(method='ffill', inplace=True)
    ZX30index = ZX30index.astype(int)

    index_initial = 1000
    for calDate in ZX30index['calDate'].unique():
        portfolio = df_fund.loc[df_fund['calDate'] == calDate].reset_index(drop=True)
        portfolio = portfolio.sort_values(by=['fcode']).reset_index(drop=True)
        trade_days = ZX30index.loc[ZX30index['calDate'] == calDate]['trade_days'].to_list()
        T0_index = AShareCalendar.loc[AShareCalendar['trade_days'] == trade_days[0]].index
        T_10 = int(AShareCalendar.loc[T0_index - 20, 'trade_days'])  # 之前10个交易日，留出空间，以免有些沪港深基金没有净值

        sql = "select F_INFO_WINDCODE, PRICE_DATE, F_NAV_ADJUSTED " \
              "from ChinaMutualFundNAV " \
              "where PRICE_DATE >={} and PRICE_DATE <={} and F_INFO_WINDCODE in {} " \
              "order by F_INFO_WINDCODE, PRICE_DATE"
        Nav = pd.read_sql_query(sql.format(T_10, trade_days[-1], tuple(portfolio['fcode'])), dbconn)

        temp = pd.pivot_table(data=Nav, index=['price_date'], columns=['f_info_windcode'], values=['f_nav_adjusted'])
        temp.fillna(method='ffill', inplace=True)  # 填充净值
        Nav = pd.DataFrame(temp.unstack())
        Nav.reset_index(inplace=True)
        Nav.drop('level_0', axis=1, inplace=True)
        Nav.rename(columns={0: 'f_nav_adjusted'}, inplace=True)

        Nav['return'] = Nav.groupby(['f_info_windcode'])['f_nav_adjusted'].diff(1) / Nav.groupby(['f_info_windcode'])[
            'f_nav_adjusted'].shift(1)
        Nav['price_date'] = Nav['price_date'].astype(int)
        Nav = Nav.loc[Nav['price_date'] >= trade_days[0]].reset_index(drop=True)
        Nav['acc_return'] = Nav.groupby(['f_info_windcode'])['return'].apply(lambda x: (x + 1).cumprod() - 1)
        Nav = Nav.sort_values(by=['price_date', 'f_info_windcode']).reset_index(drop=True)

        for days in trade_days:
            Index = ZX30index.loc[ZX30index['trade_days'] == days].index
            acc_ret = Nav.loc[Nav['price_date'] == days].reset_index(drop=True)
            weight = portfolio[['fcode', 'weight']]
            weight = pd.merge(weight, acc_ret, left_on='fcode', right_on='f_info_windcode', how='left')
            ZX30index.loc[Index, ['index']] = index_initial * (sum(weight['acc_return'] * weight['weight']) + 1)

        index_initial = float(ZX30index.loc[ZX30index['trade_days'] == trade_days[-1], 'index'])

    ZX30index = ZX30index[['trade_days', 'index']]
    return ZX30index

def retAnalysis(indexSeries):
    index = indexSeries.copy()
    index['trade_days'] = pd.to_datetime(index['trade_days'],format='%Y%m%d').dt.date
    index.set_index('trade_days', inplace=True)
    index['index'] = index['index']/index['index'].shift(1)-1
    index.dropna(inplace=True)
    ret_product = index['index']
    ret_index = wind.wind_getIndexReturn('885001.WI', datetime.date(2014,2,11), datetime.date.today(), freq='D')

    ret_product_year = Cal.basicCal_getCalendarPeriodReturn(ret_product)
    ret_index_year = Cal.basicCal_getCalendarPeriodReturn(ret_index)
    mdd_product_year = Cal.basicCal_getCalendarMaxDrawdown(ret_product)
    mdd_index_year = Cal.basicCal_getCalendarMaxDrawdown(ret_index)
    sharpe_product_year = Cal.basicCal_getCalendarSharpeRatio(ret_product)
    sharpe_index_year = Cal.basicCal_getCalendarSharpeRatio(ret_index)
    winningRate_product_year = Cal.basicCal_getCalendarwinningRate(ret_product)
    winningRate_index_year = Cal.basicCal_getCalendarwinningRate(ret_index)

    result_year = pd.concat([ret_product_year, ret_index_year, mdd_product_year, mdd_index_year,
                             sharpe_product_year, sharpe_index_year, winningRate_product_year, winningRate_index_year],
                            axis=1)

    # 修改函数时注意column name的匹配
    result_year.columns = ['return_product', 'return_index', 'MaxDrawdown_product', 'MaxDrawdown_index',
                           'Sharpe_product', 'Sharpe_index', 'WeeklywinningRate_product', 'WeeklywinningRate_index']

    result_period = pd.DataFrame(data=[[Cal.basicCal_getPeriodReturn(ret_product, 'D'),
                                        Cal.basicCal_getPeriodReturn(ret_index, 'D'),
                                        Cal.basicCal_getMaxDrawdown(ret_product),
                                        Cal.basicCal_getMaxDrawdown(ret_index),
                                        Cal.basicCal_getSharpeRatio(ret_product, 'D'),
                                        Cal.basicCal_getSharpeRatio(ret_index, 'D'),
                                        Cal.basicCal_winningRate(ret_product),
                                        Cal.basicCal_winningRate(ret_index)]],
                                 index=['period_performance'],
                                 columns=['return_product', 'return_index', 'MaxDrawdown_product', 'MaxDrawdown_index',
                                          'Sharpe_product', 'Sharpe_index', 'WeeklywinningRate_product',
                                          'WeeklywinningRate_index'])
    result = result_period.append(result_year)
    return result

def turnover(portfolio):
    df = portfolio.copy()
    df.fillna(0, inplace=True)
    df['new'] = np.where(df['old_score']>0, 0, 1)
    result = df[['date', 'new']].groupby('date').apply(lambda x: x['new'].sum()/len(x['new'])).to_frame().rename(columns={0: 'turnover'})
    return result