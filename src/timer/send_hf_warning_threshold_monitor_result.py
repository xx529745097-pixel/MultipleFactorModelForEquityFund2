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
# 通过企业微信机器人发送持仓私募基金触及预警线、止损线的情况
# ------------------------------------------------------
def timer_sendUnitPriceWarningResult(date):
    folder_path = 'D:/zhaozekun/FOF_Monitor/'
    image_path = folder_path + '私募预警线止损线监控-' + str(date) + '.png'
    hf_monitor_result = mntrVis.mntrVis_unitPriceWarning(date)
    dfi.export(hf_monitor_result, filename=image_path)
    robot_response = sendRobotMessage.sendRobotMessage('FOF数据监控', 'IMAGE', image_content=image_path)
    print(robot_response)
    return robot_response


if __name__ == '__main__':
    task_name = 'send_hf_warning_threshold_monitor_result'
    try:
        # 交易日才会进行发送，发送日期
        date = datetime.date.today()
        wind_calendar = wind.wind_getSSECalendar()
        if date in wind_calendar['date'].to_list():
            # 获取发送当日（T）的前2个交易日日期（T-2）
            execute_date = wind_calendar[wind_calendar['date'] <= date]['date'].iloc[-3]
            timer_sendUnitPriceWarningResult(execute_date)
    except Exception as error:
        # 正文添加报错信息 邮件通知
        exception_info = traceback.format_exc()
        error_message = 'Task： ' + task_name + '\n\n任务介绍： ' + config.timer_program_info[task_name]['description'] + \
                        '\n\n执行周期： ' + config.timer_program_info[task_name]['period'] + '\n\n报错信息：\n\n' + str(exception_info)
        sendMail.sendMail(send_to=["yanruofan@citics.com", "zhaozekun@citics.com"], subject=task_name+' 定时任务报错', text=error_message)
