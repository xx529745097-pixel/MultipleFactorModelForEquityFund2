#######################################
# 定时任务程序，未经允许，请不要在本地跑这个程序！！！
#######################################
import traceback
import datetime
import sys
sys.path.append('D:/fof_web')
import src.utils.sendMail as sendMail
import src.config as config
import src.utils.fof_calendar as calendar
import src.visualization.monitorVis as mntrVis
import dataframe_image as dfi
import src.utils.sendRobotMessage as sendRobotMessage
import src.data.wind as wind

# ------------------------------------------------------
# 通过企业微信机器人发送近一周公募基金公司高管和基金经理的变动情况
# ------------------------------------------------------
def timer_sendMFMemberAdjustment(
    date,            # 监控的数据日期
):
    folder_path = 'D:/zhaozekun/FOF_Monitor/'
    # 周频发送近一周的变动情况
    start_date = date - datetime.timedelta(days=7)
    end_date = date - datetime.timedelta(days=1)
    exec_adj_image_path = folder_path + '基金公司高管变动-' + str(date) + '.png'
    manager_adj_image_path = folder_path + '公募基金经理变动-' + str(date) + '.png'
    exec_adj_res = mntrVis.mntrVis_getMFCompanyExecutivesAdjustment(start_date, end_date)
    manager_adj_res = mntrVis.mntrVis_getMFManagerAdjustment(start_date, end_date)
    dfi.export(exec_adj_res, exec_adj_image_path)
    dfi.export(manager_adj_res, manager_adj_image_path)
    if len(exec_adj_res.data):
        robot_response = sendRobotMessage.sendRobotMessage('FOF数据监控助手', 'IMAGE', image_content=exec_adj_image_path)
    else:  # 无变动数据时使用文本提醒
        robot_response = sendRobotMessage.sendRobotMessage('FOF数据监控助手', 'TEXT', text_content='【数据监控】基金公司高管变动\n本周暂无变动情况')
    print(robot_response)
    if len(manager_adj_res.data):
        robot_response = sendRobotMessage.sendRobotMessage('FOF数据监控助手', 'IMAGE', image_content=manager_adj_image_path)
    else:  # 无变动数据时使用文本提醒
        robot_response = sendRobotMessage.sendRobotMessage('FOF数据监控助手', 'TEXT', text_content='【数据监控】公募基金经理变动\n本周暂无变动情况')
    print(robot_response)
    return robot_response


if __name__ == '__main__':
    task_name = 'send_mf_member_adjustment_monitor_result'
    try:
        # 每周一发送
        date = datetime.date.today()
        if date.weekday() == 0:
            # 获取发送当日日期（T），执行周频数据监控
            timer_sendMFMemberAdjustment(date)
    except Exception as error:
        # 正文添加报错信息 邮件通知
        exception_info = traceback.format_exc()
        error_message = 'Task： ' + task_name + '\n\n任务介绍： ' + config.timer_program_info[task_name]['description'] + \
                        '\n\n执行周期： ' + config.timer_program_info[task_name]['period'] + '\n\n报错信息：\n\n' + str(exception_info)
        print(error_message)
        sendMail.sendMail(send_to=["yanruofan@citics.com", "zhaozekun@citics.com", "chenziheng@citics.com", "qianchangan@citics.com"], subject=task_name+' 定时任务报错', text=error_message)