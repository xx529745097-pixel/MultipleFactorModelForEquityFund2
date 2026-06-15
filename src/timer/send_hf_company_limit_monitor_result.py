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

# --------------------------------------------------------------------
# 私募管理人层级最新持仓规模预警监控，每周发送账户持有私募管理人规模触达上限(阈值90%)的情况
# 最新持仓规模根据各账户最新持仓信息聚合
# --------------------------------------------------------------------
def timer_sendHFCompanyLimitMonitorResult(
    date,   # 监控的数据日期
):
    folder_path = 'D:/zhaozekun/FOF_Monitor/'
    image_path = folder_path + '持有规模超过90%容量上限的私募管理人-'+str(date) + '.png'
    hf_monitor_result = mntrVis.mntrVis_getHFCompanyLimitWarning(date)
    dfi.export(hf_monitor_result, filename=image_path)
    if len(hf_monitor_result.data):
        robot_response = sendRobotMessage.sendRobotMessage('FOF数据监控助手', 'IMAGE', image_content=image_path)
    else:  # 无数据时使用文本提醒
        empty_info = '【数据监控】\n本周暂无持有规模超过90%容量上限的私募管理人'
        robot_response = sendRobotMessage.sendRobotMessage('FOF数据监控助手', 'TEXT', text_content=empty_info)
    print(robot_response)
    return robot_response


if __name__ == '__main__':
    task_name = 'send_hf_company_limit_monitor_result'
    try:
        # 每周一发送
        date = datetime.date.today()
        if date.weekday() == 0:
            # 获取发送当日日期（T），执行周频数据监控
            timer_sendHFCompanyLimitMonitorResult(date)
    except Exception as error:
        # 正文添加报错信息 邮件通知
        exception_info = traceback.format_exc()
        error_message = 'Task： ' + task_name + '\n\n任务介绍： ' + config.timer_program_info[task_name]['description'] + \
                        '\n\n执行周期： ' + config.timer_program_info[task_name]['period'] + '\n\n报错信息：\n\n' + str(
            exception_info)
        print(error_message)
        sendMail.sendMail(send_to=["yanruofan@citics.com", "zhaozekun@citics.com", "chenziheng@citics.com", "qianchangan@citics.com"], subject=task_name + ' 定时任务报错', text=error_message)