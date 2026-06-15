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

# -----------------------------------------------------------------
# 通过企业微信机器人发送账户持有单一基金(阈值25%)、单一公司(阈值35%)集中度情况
# -----------------------------------------------------------------
def timer_sendFOFConcentrationWarningResult(date):
    folder_path = 'D:/zhaozekun/FOF_Monitor/'
    image_path = folder_path + '持仓集中度监控-' + str(date) + '.png'
    hf_monitor_result = mntrVis.mntrVis_FOFConcentrationWarning(date)
    dfi.export(hf_monitor_result, filename=image_path, max_rows=-1)
    robot_response = sendRobotMessage.sendRobotMessage('FOF数据监控', 'IMAGE', image_content=image_path)
    print(robot_response)
    return robot_response


if __name__ == '__main__':
    task_name = 'send_holding_concentration_monitor_result'
    try:
        # 交易日才会进行发送
        date = datetime.date.today()
        wind_calendar = wind.wind_getSSECalendar()
        if date in wind_calendar['date'].to_list():
            execute_date = wind_calendar[wind_calendar['date'] <= date]['date'].iloc[-4]
            timer_sendFOFConcentrationWarningResult(execute_date)
    except Exception as error:
        # 正文添加报错信息 邮件通知
        exception_info = traceback.format_exc()
        error_message = 'Task： ' + task_name + '\n\n任务介绍： ' + config.timer_program_info[task_name]['description'] + \
                        '\n\n执行周期： ' + config.timer_program_info[task_name]['period'] + '\n\n报错信息：\n\n' + str(exception_info)
        sendMail.sendMail(send_to=["yanruofan@citics.com", "zhaozekun@citics.com"], subject=task_name+' 定时任务报错', text=error_message)
