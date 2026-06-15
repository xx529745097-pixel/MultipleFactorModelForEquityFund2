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
import src.utils.sendMail as sendMail
import src.config as config
import src.utils.fof_calendar as calendar
import src.visualization.monitorVis as mntrVis
import dataframe_image as dfi
import src.utils.sendRobotMessage as sendRobotMessage

# ------------------------------------------------
# 私募估值表风险筛查系列监控 基于风险筛查底表
# 监控结果:
# 1. 风险筛查底表('valuation_sheet_anls_base_table')
# 2. 有风险持仓产品数量统计('risky_holding_product_stats')
# 3. 有风险持仓的产品信息('risky_holding_product_info')
# 4. 区间内缺失估值表的产品信息('valuation_sheet_missing_product_info')
# 5. 各研究员老师覆盖产品信息('researcher_product_info_dfs_dict')
# ------------------------------------------------
def timer_sendHFValuationSheetAnlsMonitorResult(
    date  # 监控日期(最新持仓观察日期与估值表回看区间截止日期)
):
    folder_path = 'D:/qianchangan/HF_Valuation_Sheet_Anls_Monitor/'
    # 监控月频执行 估值表回看区间为上季度初至今(覆盖大于一个季度)
    quarter_beginning_map = {1: datetime.date(date.year - 1, 10, 1),
                             2: datetime.date(date.year, 1, 1),
                             3: datetime.date(date.year, 4, 1),
                             4: datetime.date(date.year, 7, 1)}
    fdlq = quarter_beginning_map[(date.month - 1) // 3 + 1]  # first date of last quarter, 根据当前日期进行上季度开始日期映射
    res = mntrVis.mntrVis_HFValuationSheetAnls(current_holding_date=date, valuation_sheet_start_date=fdlq, valuation_sheet_end_date=date)
    res_valuation_sheet_anls_base_table = res['valuation_sheet_anls_base_table']
    res_risky_holding_product_stats_dfs = res['risky_holding_product_stats']
    res_risky_holding_product_info_dfs = res['risky_holding_product_info']
    res_valuation_sheet_missing_product_info_dfs = res['valuation_sheet_missing_product_info']
    res_researcher_product_info_dfs_dict = res['researcher_product_info_dfs_dict']

    # 1. 风险筛查底表
    anls_table_excel_path = folder_path + '私募估值表持仓风险筛查底表' + '-' + str(date) + '.xlsx'
    res_valuation_sheet_anls_base_table.to_excel(anls_table_excel_path)
    # 2. 产品风险持仓统计
    risky_holding_product_stats_image_path = folder_path + '产品风险持仓统计' + '-' + str(date) + '.png'
    dfi.export(res_risky_holding_product_stats_dfs, risky_holding_product_stats_image_path)
    # 3. 产品风险持仓信息
    risky_holding_product_info_image_path = folder_path + '产品风险持仓信息' + '-' + str(date) + '.png'
    dfi.export(res_risky_holding_product_info_dfs, risky_holding_product_info_image_path, max_rows=-1)
    # 4. 产品估值表未读入清单
    valuation_sheet_missing_product_info_image_path = folder_path + '产品估值表未读入清单' + '-' + str(date) + '.png'
    valuation_sheet_missing_product_info_excel_path = folder_path + '产品估值表未读入清单' + '-' + str(date) + '.xlsx'
    dfi.export(res_valuation_sheet_missing_product_info_dfs, valuation_sheet_missing_product_info_image_path, max_rows=-1)
    res_valuation_sheet_missing_product_info_dfs.data.to_excel(valuation_sheet_missing_product_info_excel_path)
    # 5. 各研究员老师覆盖产品信息
    researcher_attach_path_dict = {}
    # 遍历每位Researcher的循环
    for researcher in res_researcher_product_info_dfs_dict.keys():
        researcher_attach_path_dict[researcher] = folder_path + '研究员覆盖产品估值表信息' + '-' + researcher + '-' + str(date) + '.png'
        dfi.export(res_researcher_product_info_dfs_dict[researcher], researcher_attach_path_dict[researcher])

    # -----------
    # 发送部分
    # -----------
    # 数据监控机器人发送
    robot_response = sendRobotMessage.sendRobotMessage('FOF数据监控助手', 'IMAGE', image_content=risky_holding_product_stats_image_path)
    robot_response = sendRobotMessage.sendRobotMessage('FOF数据监控助手', 'IMAGE', image_content=risky_holding_product_info_image_path)
    print("机器人监控发送完毕")
    # 邮件发送
    sendMail.sendMail(send_to=["zhaozekun@citics.com", "chenziheng@citics.com", "qianchangan@citics.com"],
                      subject="私募估值表持仓风险筛查底表-" + str(date),
                      text="老师您好！\n\n    请查收本期私募估值表持仓风险筛查底表，谢谢！ \n\nFOF Data Analytics Platform",
                      attached_files={os.path.basename(anls_table_excel_path): anls_table_excel_path})
    print("风险筛查底表邮件已发出")
    sendMail.sendMail(send_to=["zhaozekun@citics.com", "chenziheng@citics.com", "qianchangan@citics.com"],
                      subject="私募估值表缺失产品列表-" + str(date),
                      text="老师您好！\n\n    请查收本期私募估值表缺失产品列表，谢谢！ \n\nFOF Data Analytics Platform",
                      attached_files={os.path.basename(valuation_sheet_missing_product_info_excel_path): valuation_sheet_missing_product_info_excel_path})
    print("估值表缺失产品列表邮件已发出")
    # 遍历每位Researcher的循环
    for researcher in res_researcher_product_info_dfs_dict.keys():
        if researcher in config.strategy_researcher_email_info.keys():  # 已配置邮件地址的研究员老师
            sendMail.sendMail(send_to=[config.strategy_researcher_email_info[researcher], "zhaozekun@citics.com", "chenziheng@citics.com", "qianchangan@citics.com"],
                              subject="研究员覆盖产品估值表信息-" + researcher + '-' + str(date),
                              text="老师您好！\n\n    请查收本期产品估值表信息，谢谢！\n\nFOF Data Analytics Platform",
                              attached_files={os.path.basename(researcher_attach_path_dict[researcher]): researcher_attach_path_dict[researcher]})
            print(researcher + "老师邮件已发出")
    return

if __name__ == '__main__':
    task_name = 'send_hf_valuation_sheet_anls_monitor_result'
    try:
        # 每月第二个周五执行
        execute_date = datetime.date.today()
        if execute_date.weekday() == 4:  # 仅在周五进入下述逻辑判断
            if (execute_date.day > 7) and (execute_date.day <= 14):
                timer_sendHFValuationSheetAnlsMonitorResult(execute_date)
    except Exception as error:
        # 正文添加报错信息 邮件通知
        exception_info = traceback.format_exc()
        error_message = 'Task： ' + task_name + '\n\n任务介绍： ' + config.timer_program_info[task_name]['description'] + \
                        '\n\n执行周期： ' + config.timer_program_info[task_name]['period'] + '\n\n报错信息：\n\n' + str(exception_info)
        print(error_message)
        sendMail.sendMail(send_to=["yanruofan@citics.com", "zhaozekun@citics.com", "chenziheng@citics.com", "qianchangan@citics.com"], subject=task_name + ' 定时任务报错', text=error_message)
