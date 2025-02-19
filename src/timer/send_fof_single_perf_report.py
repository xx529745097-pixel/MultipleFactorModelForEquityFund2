#######################################
# 定时任务程序，未经允许，请不要在本地跑这个程序！！！
#######################################
import traceback
import pandas as pd
import numpy as np
import datetime
import sys
import os
sys.path.append('D:/fof_web')
import src.analysis.universeAnalysis as univAnls
import src.utils.sendMail as sendMail
import src.config as config
import reports.fof_single_perf_report.fof_single_perf_report as fof_report


def timer_sendFOFSinglePerfReports(date):
    # 该定时任务在每月3号(含)到10号(不含)之间的周六20:00执行
    ldlm = datetime.date(date.year, date.month, 1) - datetime.timedelta(1)  # last date of last month
    result_dict = {}
    folder_path = 'D:/zhaozekun/FOF_Single_Perf_Report/'
    # 遍历每位PM的循环
    for pm, pm_info in config.key_accounts_config.items():
        result_dict[pm] = {}
        # 遍历PM每个重点账户的循环
        for port_id, port_name in pm_info['key_accounts'].items():
            try:
                ppt_path = folder_path + 'FOF组合分析报告-' + port_name + '-' + str(ldlm) + '.pptx'
                excel_path = folder_path + 'FOF组合分析报告-' + port_name + '-' + str(ldlm) + '.xlsx'
                fof_report.ppt_fofSinglePerfReport(ldlm, port_id, ppt_path, excel_path)
                result_dict[pm][os.path.basename(ppt_path)] = ppt_path
                result_dict[pm][os.path.basename(excel_path)] = excel_path
            except Exception as error:
                # 生成时报错的账户邮件单独通知
                exception_info = traceback.format_exc()
                error_message = '报错账户： ' + pm + port_id + port_name + '\n\n报错信息：\n\n' + str(exception_info)
                sendMail.sendMail(send_to=["yanruofan@citics.com", "zhaozekun@citics.com"], subject='send_fof_single_perf_report 定时任务存在账户报错: ' + pm + port_id + port_name, text=error_message)
        # 已生成的报告邮件发出
        sendMail.sendMail(send_to=[pm_info['mail_address'], "zhaozekun@citics.com"], subject="重点账户组合分析报告汇总-"+str(ldlm),
                          text="老师您好！\n\n    请查收本月的重点账户组合分析报告，谢谢！\n\nFOF Data Analytics Platform",
                          attached_files=result_dict[pm])
        print(pm+"老师邮件已发出")
    return


if __name__ == '__main__':
    task_name = 'send_fof_single_perf_report'
    try:
        execute_date = datetime.date.today()
        if execute_date.weekday() == 5:  # 仅在周六进入下述逻辑判断
            # 如果date>=3 说明上月月末的FOF周报已有(FOFperf已缓存) 且上月最后一个周五的universe也被缓存，具有运行条件
            # 如果date>=10号 意味着3号(含)以后的第一个周六已跑过一遍
            # 所以日期逻辑是每月 3号(含)到10号(不含)之间的一个周六去运行
            if 3 <= execute_date.day < 10:
                timer_sendFOFSinglePerfReports(execute_date)
    except Exception as error:
        # 正文添加报错信息 邮件通知
        exception_info = traceback.format_exc()
        error_message = 'Task： ' + task_name + '\n\n任务介绍： ' + config.timer_program_info[task_name]['description'] + \
                        '\n\n执行周期： ' + config.timer_program_info[task_name]['period'] + '\n\n报错信息：\n\n' + str(exception_info)
        sendMail.sendMail(send_to=["yanruofan@citics.com", "zhaozekun@citics.com"], subject=task_name+' 定时任务报错', text=error_message)
