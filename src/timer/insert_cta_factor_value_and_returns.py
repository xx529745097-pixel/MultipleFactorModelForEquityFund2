#######################################
# 定时任务程序，未经允许，请不要在本地跑这个程序！！！
#######################################
import traceback
import pandas as pd
import numpy as np
import datetime
import sys
sys.path.append('D:/fof_web')

import src.config as config

import src.data.wind as wind
import src.utils.fof_calendar as calendar
import src.utils.sendMail as sendMail
import src.analysis.ctaFactorAnalysis as ctaFactAnal


def timer_insertCtaFactorValueAndReturns(date_start, date_end):
    print('执行开始日期：', date_start)
    print('执行截止日期：', date_end)
    ctaFactAnal.ctaFactAnal_cacheCtaFactorAndReturns(date_start, date_end, insert=True)


if __name__=='__main__':
    task_name = 'insert_cta_factor_value_and_returns'

    try:
        execute_date = datetime.date.today()
        if execute_date.weekday() in (0, 1, 2, 3, 4):
            timer_insertCtaFactorValueAndReturns(execute_date - datetime.timedelta(days=60), execute_date)
    except  Exception as error:
        # 正文添加报错信息 邮件通知
        exception_info = traceback.format_exc()
        error_message = 'Task： ' + task_name + '\n\n任务介绍： ' + config.timer_program_info[task_name]['description'] + \
                        '\n\n执行周期： ' + config.timer_program_info[task_name]['period'] + '\n\n报错信息：\n\n' + str(exception_info)
        print(error_message)
        sendMail.sendMail(send_to=["yanruofan@citics.com", "zhaozekun@citics.com", "chenziheng@citics.com"], subject=task_name+' 定时任务报错', text=error_message)


