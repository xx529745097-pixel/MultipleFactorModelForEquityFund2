#######################################
# 定时任务程序，未经允许，请不要在本地跑这个程序！！！
#######################################
import traceback
import pandas as pd
import numpy as np
import datetime
import sys
sys.path.append('D:/fof_web')
import src.data.basic_cached as basicCached
import src.utils.sendMail as sendMail
import src.config as config


if __name__ == '__main__':
    task_name = 'insert_strategy_rating_snapshot'
    try:
        execute_date = datetime.date.today()
        basicCached.basicCached_cacheStrategyRatingSnapshot(execute_date, insert=True)
    except Exception as error:
        # 正文添加报错信息 邮件通知
        exception_info = traceback.format_exc()
        error_message = 'Task： ' + task_name + '\n\n任务介绍： ' + config.timer_program_info[task_name]['description'] + \
                        '\n\n执行周期： ' + config.timer_program_info[task_name]['period'] + '\n\n报错信息：\n\n' + str(exception_info)
        sendMail.sendMail(send_to=["yanruofan@citics.com", "zhaozekun@citics.com"], subject=task_name+' 定时任务报错', text=error_message)