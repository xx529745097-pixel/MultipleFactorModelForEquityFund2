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
# 通过企业微信机器人发送持仓私募基金是否已有业绩跟踪的情况
# ------------------------------------------------------
def timer_sendHoldingHFTrackMonitorResult(date):
    folder_path = 'D:/zhaozekun/FOF_Monitor/'
    image_path = folder_path + '有持仓但无业绩跟踪私募监控-' + str(date) + '.png'
    hf_monitor_result = mntrVis.mntrVis_trackingHFNav(date, tracked_week_threshold=2)
    dfi.export(hf_monitor_result, filename=image_path)
    robot_response = sendRobotMessage.sendRobotMessage('FOF数据监控', 'IMAGE', image_content=image_path)
    print(robot_response)
    return robot_response


if __name__ == '__main__':
    task_name = 'send_hf_track_monitor_result'
    try:
        # 交易日才会进行发送
        date = datetime.date.today()
        wind_calendar = wind.wind_getSSECalendar()
        if date in wind_calendar['date'].to_list():
            execute_date = wind_calendar[wind_calendar['date'] <= date]['date'].iloc[-4]
            timer_sendHoldingHFTrackMonitorResult(execute_date)
    except Exception as error:
        # 正文添加报错信息 邮件通知
        exception_info = traceback.format_exc()
        error_message = 'Task： ' + task_name + '\n\n任务介绍： ' + config.timer_program_info[task_name]['description'] + \
                        '\n\n执行周期： ' + config.timer_program_info[task_name]['period'] + '\n\n报错信息：\n\n' + str(exception_info)
        print(error_message)
        sendMail.sendMail(send_to=["yanruofan@citics.com", "zhaozekun@citics.com"], subject=task_name+' 定时任务报错', text=error_message)
