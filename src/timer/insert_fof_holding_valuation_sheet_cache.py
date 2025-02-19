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
import src.analysis.portfolioAnalysis as portAnls
import src.data.wind as wd

#################################################
# 向IRM推送账户调整后的持仓数据，逻辑为T日写入 T-16至T-2日数据
#################################################
def timer_insertFOFHoldingValuationSheetCache(date):
    # 调用获取持仓列表函数并写入数据库
    wind_calendar = wd.wind_getSSECalendar()
    start_date = wind_calendar[wind_calendar['date'] < date]['date'].iloc[-16]
    end_date = wind_calendar[wind_calendar['date'] < date]['date'].iloc[-2]
    print('update_range:' + start_date.strftime('%Y-%m-%d') + '  ' + end_date.strftime('%Y-%m-%d'))
    data, error_info = portAnls.anlsFOF_cacheFOFHoldingValuationSheet(start_date=start_date, end_date=end_date, insert=True)
    print(error_info)
    return

if __name__ == '__main__':
    task_name = 'insert_fof_holding_valuation_sheet_cache'
    try:
        date = datetime.date.today()
        wind_calendar = wd.wind_getSSECalendar()
        if date in wind_calendar['date'].to_list():
            timer_insertFOFHoldingValuationSheetCache(date)
    except Exception as error:
        # 正文添加报错信息 邮件通知
        exception_info = traceback.format_exc()
        error_message = 'Task： ' + task_name + '\n\n任务介绍： ' + config.timer_program_info[task_name]['description'] + \
                        '\n\n执行周期： ' + config.timer_program_info[task_name]['period'] + '\n\n报错信息：\n\n' + str(exception_info)
        print(error_message)
        sendMail.sendMail(send_to=["yanruofan@citics.com", "zhaozekun@citics.com", "chenziheng@citics.com", "qianchangan@citics.com"], subject=task_name+' 定时任务报错', text=error_message)