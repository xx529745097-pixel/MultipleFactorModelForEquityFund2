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
# 通过企业微信机器人发送持仓私募基金最近一年的当前回撤情况
# 日频和周频的数据均发送，提供两期之间的对比提示
# ------------------------------------------------------
def timer_sendHFCurrentDrawdownWarningResult(
    date,   # 监控的数据日期
    freq,   # 监控所使用的数据频率
):
    wind_calendar = wind.wind_getSSECalendar()
    folder_path = 'D:/zhaozekun/FOF_Monitor/'
    image_path = folder_path + '私募当前回撤监控-' + freq + '-' + str(date) + '.png'
    comparison_date = wind_calendar[wind_calendar['date'] < date]['date'].iloc[-1] if freq == 'D' else date - datetime.timedelta(7)
    hf_monitor_result = mntrVis.mntrVis_HFCurrentDrawdownWarning(date, freq)
    comparison_hf_monitor_result = mntrVis.mntrVis_HFCurrentDrawdownWarning(comparison_date, freq).data
    # 取出本期新增出现的产品
    comparison_hf_monitor_result = hf_monitor_result.data[~(hf_monitor_result.data['产品ID'].isin(comparison_hf_monitor_result['产品ID'].tolist()))]
    dfi.export(hf_monitor_result, filename=image_path, max_rows=-1)
    # 如果结果为空，则不发送消息
    if not hf_monitor_result.data.empty:
        # 如果两期对比有新增的产品，则文字提示
        if not comparison_hf_monitor_result.empty:
            comparison_warning = "【数据监控】 当前回撤监控" + ("(日频)" if freq == 'D' else "(周频)") + " - 本期新出现产品\n"
            for label_level_1 in comparison_hf_monitor_result['一级标签'].unique():
                comparison_warning += str(label_level_1) + ": " + str(comparison_hf_monitor_result[comparison_hf_monitor_result['一级标签']==label_level_1]['产品名称'].tolist()) + "\n"
            sendRobotMessage.sendRobotMessage('FOF数据监控助手', 'TEXT', text_content=comparison_warning[:-1])
        robot_response = sendRobotMessage.sendRobotMessage('FOF数据监控助手', 'IMAGE', image_content=image_path)
    else:
        robot_response = '因结果为空，未发送消息'
    print(robot_response)
    return robot_response


if __name__ == '__main__':
    task_name = 'send_hf_current_drawdown_monitor_result'
    try:
        # 交易日才会进行发送
        date = datetime.date.today()
        wind_calendar = wind.wind_getSSECalendar()
        if date in wind_calendar['date'].to_list():
            # 获取发送当日（T）的前2个交易日日期（T-2），执行日频数据监控
            daily_execute_date = wind_calendar[wind_calendar['date'] <= date]['date'].iloc[-3]
            timer_sendHFCurrentDrawdownWarningResult(daily_execute_date, 'D')
            # 如果今日是周二，则也发送周频数据监控
            if date.weekday() == 1:
                weekly_execute_date = date - datetime.timedelta(4)
                timer_sendHFCurrentDrawdownWarningResult(weekly_execute_date, 'W')
    except Exception as error:
        # 正文添加报错信息 邮件通知
        exception_info = traceback.format_exc()
        error_message = 'Task： ' + task_name + '\n\n任务介绍： ' + config.timer_program_info[task_name]['description'] + \
                        '\n\n执行周期： ' + config.timer_program_info[task_name]['period'] + '\n\n报错信息：\n\n' + str(exception_info)
        sendMail.sendMail(send_to=["yanruofan@citics.com", "zhaozekun@citics.com"], subject=task_name+' 定时任务报错', text=error_message)
