#######################################
# 定时任务程序，未经允许，请不要在本地跑这个程序！！！
#######################################
import traceback
import pandas as pd
import numpy as np
import sys
sys.path.append('D:/fof_web')
import datetime
import src.config as config
import src.utils.sendMail as sendMail
import src.data.wind_cached as wind_cached
import src.data.wind as wd

#################################################
# wind基金指数成份缓存任务，每月1号执行
#################################################
def timer_insertWindFundIndexComponent():
    for index_id in config.wind_index_component_cache_config.keys():
        print(index_id)
        wind_cached.wind_cacheWindMFIndexComponent(index_id, insert=True)
    return

if __name__ == '__main__':
    task_name = 'insert_wind_fund_index_component'
    try:
        execute_date = datetime.date.today()
        if execute_date.day == 1:
            timer_insertWindFundIndexComponent()
    except Exception as error:
        # 正文添加报错信息 邮件通知
        exception_info = traceback.format_exc()
        error_message = 'Task： ' + task_name + '\n\n任务介绍： ' + config.timer_program_info[task_name]['description'] + \
                        '\n\n执行周期： ' + config.timer_program_info[task_name]['period'] + '\n\n报错信息：\n\n' + str(exception_info)
        sendMail.sendMail(send_to=["yanruofan@citics.com", "zhaozekun@citics.com", "chenziheng@citics.com"], subject=task_name + ' 定时任务报错',
                          text=error_message)
