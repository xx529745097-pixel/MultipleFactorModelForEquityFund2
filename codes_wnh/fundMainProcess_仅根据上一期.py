# -*- coding: utf-8 -*-
"""
Created on Wed Apr 28 16:18:47 2021

@author: 029200
"""

import pandas as pd
import numpy as np
import fundStrategy_仅根据上一期 as fs
import time
import WindPy as w
import datetime
w.w.start()

today = int(datetime.date.today().strftime("%Y%m%d"))
# lkbk = np.array([[-11,-10000],[-23,-20000],[-35,-30000]])
# freq = ["Q", "2Q","Y"]
# numoffund=[10,20,30,40,50]

lkbk = np.array([[-11,-10000]])
freq = ["Q"]
numoffund=[30]

df_fund,df_aum,df_nav,df_date = fs.dataPrepare(today)

for lkbki in lkbk:
    for freqi in freq:
        for numi in numoffund:
            fundUniverse = fs.loopMain(df_fund,df_aum,lkbki,freqi,today)
            rank = fs.ranking(fundUniverse,lkbki[1])
            portfolio = fs.strategy(rank,numi)
fundUniverse.to_excel('fundUniverse.xlsx')
portfolio.to_excel('portfolio_thisperiod.xlsx')
rank.to_excel('rank.xlsx')