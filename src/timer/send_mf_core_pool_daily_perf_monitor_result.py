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
# 通过企业微信机器人发送公募核心库每日收益情况跟踪，T日发送T-1日数据
# ------------------------------------------------------
def timer_sendMFCorePoolDailyPerf(
    date,            # 监控的数据日期
):
    folder_path = 'D:/zhaozekun/FOF_Monitor/'
    product_perf_template_path = folder_path + '公募{}收益监控 - {}' + str(date) + '.png'
    product_sim_ret_path = folder_path + '公募权益核心库基金收益模拟' + str(date) + '.png'
    portfolio_perf_template_path = folder_path + '公募{}模拟组合收益统计' + str(date) + '.png'
    res = mntrVis.mntrVis_MFCorePoolDailyPerf(date)
    product_perf_res = res['holding_product_perf']
    portfolio_perf_res = res['mock_portfolio_perf']
    equity_product_sim_ret = res['equity_product_sim_ret']
    report_message = res['message']
    send_file_path_list = []
    # 产品收益
    for core_pool in product_perf_res.keys():
        for type_level_1 in product_perf_res[core_pool].keys():
            product_perf_path = product_perf_template_path.format(core_pool, type_level_1)
            dfi.export(product_perf_res[core_pool][type_level_1], product_perf_path)
            send_file_path_list.append(product_perf_path)
    # 基金收益模拟
    dfi.export(equity_product_sim_ret, product_sim_ret_path)
    send_file_path_list.append(product_sim_ret_path)
    # 模拟组合收益
    for core_pool in portfolio_perf_res.keys():
        portfolio_perf_path = portfolio_perf_template_path.format(core_pool)
        dfi.export(portfolio_perf_res[core_pool], portfolio_perf_path)
        send_file_path_list.append(portfolio_perf_path)
    # 发送部分
    for file_path in send_file_path_list:
        robot_response = sendRobotMessage.sendRobotMessage('FOF数据监控助手', 'IMAGE', image_content=file_path)
        print(robot_response)
    # 发送摘要文本
    robot_response = sendRobotMessage.sendRobotMessage('FOF测试机器人', 'TEXT', text_content=report_message)
    print(robot_response)
    return


if __name__ == '__main__':
    task_name = 'send_mf_core_pool_daily_perf_monitor_result'
    try:
        # 交易日才会进行发送
        date = datetime.date.today()
        wind_calendar = wind.wind_getSSECalendar()
        if date in wind_calendar['date'].to_list():
            execute_date = wind_calendar[wind_calendar['date'] <= date]['date'].iloc[-2]
            timer_sendMFCorePoolDailyPerf(execute_date)
    except Exception as error:
        # 正文添加报错信息 邮件通知
        exception_info = traceback.format_exc()
        error_message = 'Task： ' + task_name + '\n\n任务介绍： ' + config.timer_program_info[task_name]['description'] + \
                        '\n\n执行周期： ' + config.timer_program_info[task_name]['period'] + '\n\n报错信息：\n\n' + str(exception_info)
        print(error_message)
        sendMail.sendMail(send_to=["yanruofan@citics.com", "zhaozekun@citics.com", "chenziheng@citics.com", "qianchangan@citics.com"], subject=task_name+' 定时任务报错', text=error_message)