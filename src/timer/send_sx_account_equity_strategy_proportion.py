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
from dateutil.relativedelta import relativedelta

# --------------------------------------------------------------------
# 通过企业微信机器人(私享服务支持)发送私享账户权益持仓分布每周监控并与上周对比
# 每个周五交易日的15:00发送
# --------------------------------------------------------------------
def timer_sendSXAccountEquityStrategyPropotion(
    date,   # 监控的数据日期
):
    wind_calendar = wind.wind_getSSECalendar()
    date = wind_calendar[wind_calendar['date'] <= date]['date'].iloc[-1]
    folder_path = 'D:/zhaozekun/FOF_Monitor/'
    image_path_1 = folder_path + '私享账户权益持仓分布-' + str(date) + '.png'
    hf_monitor_result_1 = mntrVis.mntrVis_SXAccountEquityStrategyPropotion(date, date)
    dfi.export(hf_monitor_result_1, filename=image_path_1)
    image_path_2 = folder_path + '私享账户权益持仓分布周度变化-' + str(date) + '.png'
    hf_monitor_result_2 = mntrVis.mntrVis_SXAccountEquityStrategyPropotionChg(date-datetime.timedelta(7), date-datetime.timedelta(7), date, date,
                                                                              image_caption='各投资经理权益持仓中  各类产品占比(时点值)   较上周变化情况')
    dfi.export(hf_monitor_result_2, filename=image_path_2)
    image_path_3 = folder_path + '私享账户权益持仓分布月度变化-' + str(date) + '.png'
    hf_monitor_result_3 = mntrVis.mntrVis_SXAccountEquityStrategyPropotionChg(date-relativedelta(months=1), date-relativedelta(months=1), date, date,
                                                                              image_caption='各投资经理权益持仓中  各类产品占比(时点值)   较上月变化情况')
    dfi.export(hf_monitor_result_3, filename=image_path_3)
    robot_response = sendRobotMessage.sendRobotMessage('私享服务支持', 'TEXT', text_content="各位老师，以下是权益类产品持仓占比以及变化情况(时点值)")
    robot_response = sendRobotMessage.sendRobotMessage('私享服务支持', 'IMAGE', image_content=image_path_1)
    robot_response = sendRobotMessage.sendRobotMessage('私享服务支持', 'IMAGE', image_content=image_path_2)
    robot_response = sendRobotMessage.sendRobotMessage('私享服务支持', 'IMAGE', image_content=image_path_3)
    print(robot_response)
    return robot_response


if __name__ == '__main__':
    task_name = 'send_sx_account_equity_strategy_proportion'
    try:
        # 交易日才会进行发送
        date = datetime.date.today()
        wind_calendar = wind.wind_getSSECalendar()
        if date in wind_calendar['date'].to_list():
            execute_date = wind_calendar[wind_calendar['date'] <= date]['date'].iloc[-4]
            timer_sendSXAccountEquityStrategyPropotion(execute_date)

    except Exception as error:
        # 正文添加报错信息 邮件通知
        exception_info = traceback.format_exc()
        error_message = 'Task： ' + task_name + '\n\n任务介绍： ' + config.timer_program_info[task_name]['description'] + \
                        '\n\n执行周期： ' + config.timer_program_info[task_name]['period'] + '\n\n报错信息：\n\n' + str(exception_info)
        sendMail.sendMail(send_to=["yanruofan@citics.com", "zhaozekun@citics.com", "chenziheng@citics.com"], subject=task_name+' 定时任务报错', text=error_message)
