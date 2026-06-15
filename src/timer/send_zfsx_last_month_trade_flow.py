#######################################
# 定时任务程序，未经允许，请不要在本地跑这个程序！！！
#######################################
import traceback
import datetime
import sys
sys.path.append('D:/fof_web')
import src.utils.sendMail as sendMail
import src.config as config
import src.data.custFOF as custFOF
import src.visualization.portfolioVis as portVis
import src.utils.fof_calendar as calendar
import src.visualization.monitorVis as mntrVis
import dataframe_image as dfi
import src.utils.sendRobotMessage as sendRobotMessage
import src.data.wind as wind

# -----------------------------------------------
# 每月月初通过企业微信机器人发送上月浙分私享交易明细
# -----------------------------------------------
def timer_sendZFSXLastMonthTradeFlow(
    date,            # 监控的数据日期
):
    folder_path = 'D:/zhaozekun/FOF_Monitor/'
    file_path = folder_path + '浙分-私享-{}月交易数据'.format(date.month-1 if date.month != 1 else 12) + '.xlsx'
    # 获取上个月的起止日期
    end_date = datetime.date(date.year, date.month, 1) - datetime.timedelta(days=1)
    start_date = datetime.date(end_date.year, end_date.month, 1)
    ref_data = custFOF.custFOF_getFOFReferenceData(None, config.specific_FOF_product_line['pure_sixiang'], client_region=['浙江'],
                                                   include_advisory_account=True, user_permission_setting=True)
    result = portVis.visFOF_getTradeHistoricalFlow(start_date, end_date, ref_data['portfolio_id'].dropna().to_list()).data.sort_values('组合名称')  # 部分投顾账户未取到portfolio_id，通过dropna筛去
    result = result[result['交易量'] != 0]
    result.to_excel(file_path, index=None)
    robot_response = sendRobotMessage.sendRobotMessage('FOF私享服务(浙分)', 'FILE', file_content=file_path)
    print(robot_response)
    return robot_response


if __name__ == '__main__':
    task_name = 'send_zfsx_last_month_trade_flow'
    try:
        # 每月第5个交易日发送，日频检查发送日期
        date = datetime.date.today()
        wind_calendar = wind.wind_getSSECalendar()
        target_date = wind_calendar[wind_calendar['date'] >= datetime.date(date.year, date.month, 1)]['date'].iloc[4]
        if date == target_date:
            timer_sendZFSXLastMonthTradeFlow(date)
    except Exception as error:
        # 正文添加报错信息 邮件通知
        exception_info = traceback.format_exc()
        error_message = 'Task： ' + task_name + '\n\n任务介绍： ' + config.timer_program_info[task_name]['description'] + \
                        '\n\n执行周期： ' + config.timer_program_info[task_name]['period'] + '\n\n报错信息：\n\n' + str(exception_info)
        print(error_message)
        sendMail.sendMail(send_to=["yanruofan@citics.com", "zhaozekun@citics.com", "chenziheng@citics.com", "qianchangan@citics.com"], subject=task_name+' 定时任务报错', text=error_message)