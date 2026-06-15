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

def timer_insertFOFPerfStats(date):
    # 为了防止长假期间数据源更新慢导致缓存数据错误的问题，将cache执行日期区间拓至15天，历史日期会被多次运行覆盖，保证数据最新最准
    # FIXME 后续可根据服务器性能对缓存任务区间长度的设置进行优化
    portAnls.anlsFOF_calAndCacheFOFPerfStats(date, 'YTD', cache_start_date=date-datetime.timedelta(15), insert=True)
    return


if __name__ == '__main__':
    task_name = 'insert_fof_perf_stats'
    try:
        execute_date = calendar.calender_getFOFProperDate(mode='cache', delta_date=3)
        if execute_date:
            timer_insertFOFPerfStats(execute_date)
    except Exception as error:
        # 正文添加报错信息 邮件通知
        exception_info = traceback.format_exc()
        error_message = 'Task： ' + task_name + '\n\n任务介绍： ' + config.timer_program_info[task_name]['description'] + \
                        '\n\n执行周期： ' + config.timer_program_info[task_name]['period'] + '\n\n报错信息：\n\n' + str(exception_info)
        sendMail.sendMail(send_to=["yanruofan@citics.com", "zhaozekun@citics.com"], subject=task_name+' 定时任务报错', text=error_message)
