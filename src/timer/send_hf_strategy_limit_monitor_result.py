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
# 通过企业微信机器人(FOF数据监控助手)发送账户持有私募策略触达上限(阈值90%)的情况
# 周一-五发送数据不含投顾，发送数据的截至日期为T-3；周一额外发送完整版，包含投顾数据，发送数据的截至日期为上上周五
# 每个交易日9:00发送
# --------------------------------------------------------------------
def timer_sendHFStrategyLimitMonitorResult(
    date,   # 监控的数据日期
    include_advisory=False
):
    wind_calendar = wind.wind_getSSECalendar()
    date = wind_calendar[wind_calendar['date'] <= date]['date'].iloc[-1]
    folder_path = 'D:/zhaozekun/FOF_Monitor/'
    file_name = '含投顾-' if include_advisory else '不含投顾-'
    image_path = folder_path + '持有规模超过90%容量上限的私募策略-'+file_name+str(date) + '.png'
    hf_monitor_result = mntrVis.mntrVis_HFStrategyLimitWarning(date, include_advisory=include_advisory)
    dfi.export(hf_monitor_result, filename=image_path)
    robot_response = sendRobotMessage.sendRobotMessage('FOF数据监控助手', 'IMAGE', image_content=image_path)
    print(robot_response)
    return robot_response


if __name__ == '__main__':
    task_name = 'send_hf_strategy_limit_monitor_result'
    try:
        # 交易日才会进行发送
        date = datetime.date.today()
        wind_calendar = wind.wind_getSSECalendar()
        if date in wind_calendar['date'].to_list():
            print(date)
            # 周一-五发送数据不含投顾 发送日期为T-3
            execute_date = wind_calendar[wind_calendar['date'] <= date]['date'].iloc[-4]
            timer_sendHFStrategyLimitMonitorResult(execute_date, include_advisory=False)
            # 周一额外发送完整版，包含投顾数据，发送数据的日期为上上周五
            if date.weekday() == 0:
                execute_date = wind_calendar[(wind_calendar['date'].apply(lambda x: x.weekday() == 4)) & (wind_calendar['date'] <= date)]['date'].iloc[-2]
                timer_sendHFStrategyLimitMonitorResult(execute_date, include_advisory=True)
            print('发送日期-' + date.strftime("%Y-%m-%d") + '，数据截至日期-' + execute_date.strftime("%Y-%m-%d"))
    except Exception as error:
        # 正文添加报错信息 邮件通知
        exception_info = traceback.format_exc()
        error_message = 'Task： ' + task_name + '\n\n任务介绍： ' + config.timer_program_info[task_name]['description'] + \
                        '\n\n执行周期： ' + config.timer_program_info[task_name]['period'] + '\n\n报错信息：\n\n' + str(exception_info)
        print(error_message)
        sendMail.sendMail(send_to=["yanruofan@citics.com", "zhaozekun@citics.com", "chenziheng@citics.com"], subject=task_name+' 定时任务报错', text=error_message)
