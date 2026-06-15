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
import src.const as const
import src.utils.sendMail as sendMail
import src.data.wind_cached as wind_cached
import src.data.wind as wd
import src.analysis.CTAanalysis as cta

##########################################################
# 定制指数日频收益率缓存任务，每个交易日执行，缓存上一交易日的收益率
##########################################################
def timer_insertCustomizedIndexReturn(date):
    for index_id in const.const.CUSTOMIZED_BENCHMARK_LIST.values():
        print(index_id)
        if index_id == '885008.CUSTOMIZED':
            wind_cached.wind_cacheCustomizedIndexReturn(index_id, date, date, insert=True)
        elif index_id == 'CTA_MANAGER_INDEX_01.CUSTOMIZED' and execute_date.weekday()==2:
            cta.ctaAnls_calCTACustomizedIndexReturn(date-datetime.timedelta(days=14), date, insert=True)

    return

if __name__ == '__main__':
    task_name = 'insert_customized_index_return'
    try:
        date = datetime.date.today()
        wind_calendar = wd.wind_getSSECalendar()
        if date in wind_calendar['date'].to_list():
            # 获取当日（T）的前1个交易日日期（T-1）
            execute_date = wind_calendar[wind_calendar['date'] < date]['date'].iloc[-1]
            timer_insertCustomizedIndexReturn(execute_date)
    except Exception as error:
        # 正文添加报错信息 邮件通知
        exception_info = traceback.format_exc()
        error_message = 'Task： ' + task_name + '\n\n任务介绍： ' + config.timer_program_info[task_name]['description'] + \
                        '\n\n执行周期： ' + config.timer_program_info[task_name]['period'] + '\n\n报错信息：\n\n' + str(exception_info)
        sendMail.sendMail(send_to=["yanruofan@citics.com", "zhaozekun@citics.com", "chenziheng@citics.com"], subject=task_name + ' 定时任务报错',
                          text=error_message)
