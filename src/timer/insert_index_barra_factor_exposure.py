#######################################
# 定时任务程序，未经允许，请不要在本地跑这个程序！！！
#######################################
import traceback
import pandas as pd
import numpy as np
import datetime
import sys
sys.path.append('D:/fof_web')
import src.const as const
import src.config as config
import src.analysis.barraAnalysis as barraAnls
import src.analysis.portfolioAnalysis as portAnls
import src.data.wind as wind
import src.utils.fof_calendar as calendar
import src.utils.sendMail as sendMail


def timer_insertIndexBarraFactorExposure(date):
    wind_calendar = wind.wind_getSSECalendar()['date'].to_list()
    index_list = const.const.INDEX_NAME_TO_CODE_MAP.keys()
    if date in wind_calendar:
        for index in index_list:
            barraAnls.barraAnal_calAndWriteIndexBarraFactorExposure(index, date, date, insert=True)
    else:
        return


if __name__ == '__main__':
    task_name = 'insert_index_barra_factor_exposure'
    try:
        execute_date = calendar.calender_getFOFProperDate(mode='cache', delta_date=1)
        if execute_date:
            timer_insertIndexBarraFactorExposure(execute_date)
    except Exception as error:
        # 正文添加报错信息 邮件通知
        exception_info = traceback.format_exc()
        error_message = 'Task： ' + task_name + '\n\n任务介绍： ' + config.timer_program_info[task_name]['description'] + \
                        '\n\n执行周期： ' + config.timer_program_info[task_name]['period'] + '\n\n报错信息：\n\n' + str(exception_info)
        sendMail.sendMail(send_to=["yanruofan@citics.com", "zhaozekun@citics.com"], subject=task_name+' 定时任务报错', text=error_message)
