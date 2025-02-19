# -*- coding: utf-8 -*-
"""
Created on Wed Apr 28 16:18:47 2021

@author: 029200
"""

import pandas as pd
import numpy as np
import fundStrategy_stock_final as fs
import time
# import WindPy as w
import datetime
# w.w.start()

today = int(datetime.date.today().strftime("%Y%m%d"))
# lkbk = np.array([[-11,-10000],[-23,-20000],[-35,-30000]])
# freq = ["Q", "2Q","Y"]
# numoffund=[10,20,30,40,50]

lkbk = np.array([[-11,-10000]])
freq = ["Q"]
numoffund=[30]

df_fund,df_aum,df_nav,df_date = fs.dataPrepare(today)

resultAll = pd.DataFrame(columns=["lkbk","freq","numoffund","absRet","vol","maxDD","sharpe","relRet","trackerror","informationR"])
for lkbki in lkbk:
    for freqi in freq:
        for numi in numoffund:
            print (str(lkbki[0])+" "+str(lkbki[1])+" "+str(freqi)+" "+str(numi))
            t1 = time.time()
            fundUniverse = fs.loopMain(df_fund,df_aum,lkbki,freqi,today)
            rank = fs.ranking(fundUniverse,lkbki[1])
            portfolio = fs.strategy(rank,numi)
            indexSeries = fs.backTesting(portfolio)
            retAnalysis = fs.retAnalysis(indexSeries)
            turnover = fs.turnover(portfolio)
            t2 = time.time()
            print(t2-t1)
fundUniverse.to_excel('fundUniverse.xlsx')
rank.to_excel('rank.xlsx')
portfolio.to_excel('portfolio.xlsx')
indexSeries.to_excel('stockIndex.xlsx')
#
# portfolio = pd.read_excel('portfolioCC30.xlsx')
# portfolio = portfolio[['date','fcode','weight']]
# new_portfolio = pd.DataFrame()
#
# extra_fund = pd.DataFrame(data=['006165.OF','006729.OF','161017.SZ','006682.OF','518880.SH','001302.OF','510880.SH'],columns=['fcode'])
# extra_fund['weight'] = 0.05
# extra_fund.loc[extra_fund['fcode'] == '510880.SH','weight'] = 0.2
# for date in portfolio['date'].unique():
#     tmp = portfolio.loc[portfolio['date'] == date]
#     if date > 20190630:
#         tmp['weight'] = 0.5/30
#         tmp = tmp.append(extra_fund)
#         tmp['date'].fillna(method='ffill', inplace=True)
#     new_portfolio = new_portfolio.append(tmp)


