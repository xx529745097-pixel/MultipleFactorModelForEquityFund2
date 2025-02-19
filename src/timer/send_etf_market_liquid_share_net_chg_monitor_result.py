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

# ------------------------------------------------------------------
# 近20交易日股票型ETF净申赎份额规模
# ------------------------------------------------------------------
def timer_sendETFMarketLiquidShareNetChg(
    date,            # 考察日期
    tracked_days=20  # 跟踪天数
):
    folder_path = 'D:/zhaozekun/FOF_Monitor/'
    chart_path = folder_path + '股票型ETF净申赎份额-' + str(date) + '.png'
    table_1_path = folder_path + '股票型ETF挂钩指数净申赎份额规模-宽基指数-' + str(date) + '.png'
    table_2_path = folder_path + '股票型ETF挂钩指数净申赎份额规模-行业主题等指数-' + str(date) + '.png'
    result = mntrVis.mntrVis_getETFMarketLiquidShareNetChg(date, tracked_days)
    # summary
    result_summary_chart = result['summary_chart']
    result_summary_chart.save(chart_path, format='png', scale_factor=1.6)
    # 规模指数
    result_broad_based_table = result['broad_based_table']
    dfi.export(result_broad_based_table, table_1_path)
    # 主题行业策略风格指数
    result_other_table = result['other_table']
    dfi.export(result_other_table, table_2_path)
    # 份额调整事件
    share_split_info_msg = result['share_split_info']
    # 发送部分
    if share_split_info_msg:
        robot_response = sendRobotMessage.sendRobotMessage('FOF测试机器人', 'TEXT', text_content=share_split_info_msg)
        print(robot_response)
    robot_response = sendRobotMessage.sendRobotMessage('FOF数据监控助手', 'IMAGE', image_content=chart_path)
    print(robot_response)
    robot_response = sendRobotMessage.sendRobotMessage('FOF数据监控助手', 'IMAGE', image_content=table_1_path)
    print(robot_response)
    robot_response = sendRobotMessage.sendRobotMessage('FOF数据监控助手', 'IMAGE', image_content=table_2_path)
    print(robot_response)
    return


if __name__ == '__main__':
    task_name = 'send_etf_market_liquid_share_net_chg_monitor_result'
    try:
        # 交易日才会进行发送
        date = datetime.date.today()
        wind_calendar = wind.wind_getSSECalendar()
        if date in wind_calendar['date'].to_list():
            # 获取发送当日日期（T），执行日频数据监控
            timer_sendETFMarketLiquidShareNetChg(date)
    except Exception as error:
        # 正文添加报错信息 邮件通知
        exception_info = traceback.format_exc()
        error_message = 'Task： ' + task_name + '\n\n任务介绍： ' + config.timer_program_info[task_name]['description'] + \
                        '\n\n执行周期： ' + config.timer_program_info[task_name]['period'] + '\n\n报错信息：\n\n' + str(exception_info)
        print(error_message)
        sendMail.sendMail(send_to=["yanruofan@citics.com", "zhaozekun@citics.com", "chenziheng@citics.com", "qianchangan@citics.com"], subject=task_name+' 定时任务报错', text=error_message)