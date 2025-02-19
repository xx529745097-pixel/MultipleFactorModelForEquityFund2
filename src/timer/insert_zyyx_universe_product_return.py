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


# -----------------------------------------------------------------------------------------
# 插入上周五和上上周五的ZYYX universe 各类别product week_return month_return year_return的函数，当截止日期为月末最后一个周五时，刷新历史数据
# -----------------------------------------------------------------------------------------
def timer_insertZYYXUnivProductReturn(date):
    # 该定时任务仅周五执行，存入上周五和上上周五的对应数据
    last_friday = date - datetime.timedelta(days=7)
    friday_before_last_friday = date - datetime.timedelta(days=14)
    # 生成日期范围，找到范围内的季度最后一个周五
    dates = pd.date_range(start=date - datetime.timedelta(days=30), end=date + datetime.timedelta(days=30))
    df = pd.DataFrame(dates, columns=['Date'])
    fridays = df[df['Date'].dt.weekday == 4]
    last_fridays_of_months = fridays.groupby(fridays['Date'].dt.to_period('M')).max()
    if last_friday in list(last_fridays_of_months['Date'].dt.date):
        # last_friday为每月最后一个周五时缓存刷新，缓存时间从前一年1月1日开始
        previous_year_start_date = datetime.date(date.year, 1, 1)
        univAnls.univAnls_cacheZYYXUnivProductStats(previous_year_start_date, last_friday, stat='week_return', insert=True)
        univAnls.univAnls_cacheZYYXUnivProductStats(previous_year_start_date, last_friday, stat='month_return', insert=True)
        univAnls.univAnls_cacheZYYXUnivProductStats(previous_year_start_date, last_friday, stat='year_return', insert=True)
    else:
        univAnls.univAnls_cacheZYYXUnivProductStats(friday_before_last_friday, last_friday, stat='week_return', insert=True)
        univAnls.univAnls_cacheZYYXUnivProductStats(friday_before_last_friday, last_friday, stat='month_return', insert=True)
        univAnls.univAnls_cacheZYYXUnivProductStats(friday_before_last_friday, last_friday, stat='year_return', insert=True)
    return



if __name__ == '__main__':
    task_name = 'insert_zyyx_universe_product_return'
    try:
        execute_date = datetime.date.today()
        if execute_date.weekday() == 4:  # 仅周五执行
            timer_insertZYYXUnivProductReturn(execute_date)
    except Exception as error:
        # 正文添加报错信息 邮件通知
        exception_info = traceback.format_exc()
        error_message = 'Task： ' + task_name + '\n\n任务介绍： ' + config.timer_program_info[task_name]['description'] + \
                        '\n\n执行周期： ' + config.timer_program_info[task_name]['period'] + '\n\n报错信息：\n\n' + str(exception_info)
        sendMail.sendMail(send_to=["yanruofan@citics.com", "zhaozekun@citics.com"], subject=task_name+' 定时任务报错', text=error_message)