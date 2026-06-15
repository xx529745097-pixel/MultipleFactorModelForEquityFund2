#######################################
# 定时任务程序，未经允许，请不要在本地跑这个程序！！！
#######################################

import pandas as pd
import numpy as np
import datetime
import sys
sys.path.append('D:/fof_web')
import src.const as const
import src.analysis.barraAnalysis as barraAnls
import src.analysis.portfolioAnalysis as portAnls
import src.data.wind as wind


#######################################
# 往数据库插入每日股指的Barra因子暴露数据，目前是T-3
#######################################
def timer_insertIndexBarraFactorExposure(
    date=datetime.date.today()-datetime.timedelta(days=3)
):
    wind_calendar = wind.wind_getSSECalendar()['date'].to_list()
    index_list = const.const.INDEX_NAME_TO_CODE_MAP.keys()
    if date in wind_calendar:
        for index in index_list:
            barraAnls.barraAnal_calAndWriteIndexBarraFactorExposure(index, date, date, insert=True)
    else:
        return

def timer_insertFOFPerfStats(
    date=datetime.date.today()-datetime.timedelta(days=3)
):
    wind_calendar = wind.wind_getSSECalendar()['date'].to_list()
    # if date == datetime.date(date.year, date.month, 1) and date.month != 1:
    #     portAnls.anlsFOF_calAndCacheFOFPerfStats(date, 'YTLDLM', insert=True)
    if date in wind_calendar:
        portAnls.anlsFOF_calAndCacheFOFPerfStats(date, 'YTD', date, insert=True)
    return

date = datetime.date(2022,11,13)
for x in range(7):
    this_date = date - datetime.timedelta(days=x)
    timer_insertFOFPerfStats(this_date)

# #######################################
# # main函数
# #######################################
# def main():
#     timer_insertIndexBarraFactorExposure()
#
# main()