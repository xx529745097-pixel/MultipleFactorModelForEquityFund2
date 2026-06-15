#######################################
# 定时任务程序，未经允许，请不要在本地跑这个程序！！！
#######################################
import traceback
import pandas as pd
import numpy as np
import datetime
import sys
sys.path.append('D:/fof_web')
import src.analysis.universeAnalysis as univAnls
import src.utils.sendMail as sendMail
import src.config as config


# -----------------------------------------------------------------------
# 插入上周五和上上周五的ZYYX universe 各类别分位数信息的函数
# -----------------------------------------------------------------------
def timer_insertZYYXUnivDistribution(date):
    # 该定时任务仅周五执行，存入上周五和上上周五的对应数据
    last_friday = date - datetime.timedelta(days=7)
    friday_before_last_friday = date - datetime.timedelta(days=14)
    univAnls.univAnls_cacheZYYXUnivDistribution(friday_before_last_friday, last_friday, insert=True)
    return


if __name__ == '__main__':
    task_name = 'insert_zyyx_universe_distribution'
    try:
        execute_date = datetime.date.today()
        if execute_date.weekday() == 4:  # 仅周五执行
            timer_insertZYYXUnivDistribution(execute_date)
    except Exception as error:
        # 正文添加报错信息 邮件通知
        exception_info = traceback.format_exc()
        error_message = 'Task： ' + task_name + '\n\n任务介绍： ' + config.timer_program_info[task_name]['description'] + \
                        '\n\n执行周期： ' + config.timer_program_info[task_name]['period'] + '\n\n报错信息：\n\n' + str(exception_info)
        sendMail.sendMail(send_to=["yanruofan@citics.com", "zhaozekun@citics.com"], subject=task_name+' 定时任务报错', text=error_message)
