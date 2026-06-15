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
# 向IRM推送账户最新策略持有规模信息，回看区间为T至T-45，取各账户最新持仓数据
#################################################
def timer_insertCurrentHoldingStrategyInfo(date):
    # 调用获取持仓列表函数并写入数据库
    portAnls.anlsFOF_cacheCurrentStrategyHoldingInfo(date, insert=True)
    return

if __name__ == '__main__':
    task_name = 'insert_current_holding_strategy_info'
    try:
        date = datetime.date.today()
        wind_calendar = wd.wind_getSSECalendar()
        if date in wind_calendar['date'].to_list():
            timer_insertCurrentHoldingStrategyInfo(date)
    except Exception as error:
        # 正文添加报错信息 邮件通知
        exception_info = traceback.format_exc()
        error_message = 'Task： ' + task_name + '\n\n任务介绍： ' + config.timer_program_info[task_name]['description'] + \
                        '\n\n执行周期： ' + config.timer_program_info[task_name]['period'] + '\n\n报错信息：\n\n' + str(exception_info)
        print(error_message)
        sendMail.sendMail(send_to=["yanruofan@citics.com", "zhaozekun@citics.com", "chenziheng@citics.com", "qianchangan@citics.com"], subject=task_name+' 定时任务报错', text=error_message)