#######################################
# 定时任务程序，未经允许，请不要在本地跑这个程序！！！
#######################################
import traceback
import pandas as pd
import numpy as np
import sys
import psutil
sys.path.append('D:/fof_web')
import datetime
import src.config as config
import src.const as const
import src.data.irm as irm
import src.utils.sendMail as sendMail
import src.data.wind as wind
import src.utils.scriptManager as scriptManager

#################################################
# 监控运行异常的脚本进程，定期清理并更新进程状态信息
#################################################
def timer_insertScriptProcessStatus(
    time,  # 查询时间
    tracked_days  # 回溯天数
):
    # 对于在timer中扫出的已终止进程，通过邮件告知触发用户
    updated_res = scriptManager.script_recordRunningScriptProcessInfo(time, tracked_days)
    for index, row in updated_res.iterrows():
        target_email = row['user_email'].split(',')
        terminate_message = f"老师您好！\n\n    您 {row['create_time']} 在平台触发的 '{row['script_desc']}' 脚本任务已被终止，" + \
                            "抱歉给您带来不便，如有疑问请随时与我们联系，谢谢！\n\nMARS - Multi-Asset Research Solution"
        sendMail.sendMail(
            send_to=list(set(["zhaozekun@citics.com", "qianchangan@citics.com"] + target_email)),
            subject=f"'{row['script_desc']}'脚本任务已终止", text=terminate_message)
    return

if __name__ == '__main__':
    task_name = 'insert_script_process_status'
    try:
        timer_insertScriptProcessStatus(time=datetime.datetime.now(), tracked_days=14)
    except Exception as error:
        # 正文添加报错信息 邮件通知
        exception_info = traceback.format_exc()
        error_message = 'Task： ' + task_name + '\n\n任务介绍： ' + config.timer_program_info[task_name]['description'] + \
                        '\n\n执行周期： ' + config.timer_program_info[task_name]['period'] + '\n\n报错信息：\n\n' + str(exception_info)
        print(error_message)
        sendMail.sendMail(send_to=["yanruofan@citics.com", "zhaozekun@citics.com", "chenziheng@citics.com", "qianchangan@citics.com"], subject=task_name+' 定时任务报错', text=error_message)
