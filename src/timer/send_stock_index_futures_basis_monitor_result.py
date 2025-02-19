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
# 通过企业微信机器人发送股指期货基差走势图
# 根据当日股指期货连续合约映射表选取当月/次月/当季合约
# ------------------------------------------------------
def timer_sendStockIndexFuturesBasisLevelAndContrib(
    date,            # 监控的数据日期
    tracked_days=5  # 回看天数
):
    wind_calendar = wind.wind_getSSECalendar()
    folder_path = 'D:/zhaozekun/FOF_Monitor/'
    start_date = wind_calendar[wind_calendar['date'] <= date]['date'].iloc[-tracked_days]
    end_date = wind_calendar[wind_calendar['date'] <= date]['date'].iloc[-1]
    basis_level_image_path = folder_path + '股指期货基差走势监控-' + str(date) + '.png'
    adjustment_points_path = folder_path + '股指剩余分红点数-' + str(date) + '.png'
    basis_level_result_fig, adjustment_points_table_result = mntrVis.mntrVis_PlotStockIndexFuturesBasisLevel(start_date, end_date)
    basis_level_result_fig.savefig(basis_level_image_path, bbox_inches='tight')
    dfi.export(adjustment_points_table_result, adjustment_points_path)
    basis_level_contribution_path = folder_path + '股指期货基差贡献监控-' + str(date) + '.png'
    basis_level_contribution_result = mntrVis.mntrVis_StockIndexFuturesBasisContribution(date)
    dfi.export(basis_level_contribution_result, basis_level_contribution_path)
    robot_response1 = sendRobotMessage.sendRobotMessage('FOF数据监控助手', 'IMAGE', image_content=basis_level_image_path)
    print(robot_response1)
    # 剩余分红点数的结果目前不发至大群，先发至测试群辅助check
    robot_response2 = sendRobotMessage.sendRobotMessage('FOF测试机器人', 'IMAGE', image_content=adjustment_points_path)
    print(robot_response2)
    robot_response3 = sendRobotMessage.sendRobotMessage('FOF数据监控助手', 'IMAGE', image_content=basis_level_contribution_path)
    print(robot_response3)
    return


if __name__ == '__main__':
    task_name = 'send_stock_index_futures_basis_monitor_result'
    try:
        # 交易日才会进行发送
        date = datetime.date.today()
        wind_calendar = wind.wind_getSSECalendar()
        if date in wind_calendar['date'].to_list():
            # 获取发送当日日期（T），执行日频数据监控
            timer_sendStockIndexFuturesBasisLevelAndContrib(date, tracked_days=5)
    except Exception as error:
        # 正文添加报错信息 邮件通知
        exception_info = traceback.format_exc()
        error_message = 'Task： ' + task_name + '\n\n任务介绍： ' + config.timer_program_info[task_name]['description'] + \
                        '\n\n执行周期： ' + config.timer_program_info[task_name]['period'] + '\n\n报错信息：\n\n' + str(exception_info)
        print(error_message)
        sendMail.sendMail(send_to=["yanruofan@citics.com", "zhaozekun@citics.com", "chenziheng@citics.com", "qianchangan@citics.com"], subject=task_name+' 定时任务报错', text=error_message)