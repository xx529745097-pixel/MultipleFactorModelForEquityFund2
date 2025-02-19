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
# 向IRM推送持有产品列表，每个交易日（T）22点执行，推送范围为：T-1和T-8之间持仓产品列表的并集
#################################################
def timer_insertHoldingProductList(date):
    # 调用获取持仓列表函数并写入数据库
    portAnls.anlsFOF_holdingProductList(date, insert=True)
    return

if __name__ == '__main__':
    task_name = 'insert_holding_product_list'
    try:
        execute_date = datetime.date.today()
        wind_calendar = wd.wind_getSSECalendar()['date'].to_list()
        if execute_date in wind_calendar:
            timer_insertHoldingProductList(execute_date)
    except Exception as error:
        # 正文添加报错信息 邮件通知
        exception_info = traceback.format_exc()
        error_message = 'Task： ' + task_name + '\n\n任务介绍： ' + config.timer_program_info[task_name]['description'] + \
                        '\n\n执行周期： ' + config.timer_program_info[task_name]['period'] + '\n\n报错信息：\n\n' + str(
            exception_info)
        sendMail.sendMail(send_to=["yanruofan@citics.com", "zhaozekun@citics.com", "chenziheng@citics.com"], subject=task_name + ' 定时任务报错',
                          text=error_message)
