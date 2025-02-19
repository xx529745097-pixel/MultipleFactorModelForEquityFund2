#######################################
# 定时任务程序，未经允许，请不要在本地跑这个程序！！！
#######################################
import traceback
import datetime
import sys

import pandas as pd

sys.path.append('D:/fof_web')
import src.utils.sendMail as sendMail
import src.config as config
import src.utils.fof_calendar as calendar
import src.visualization.monitorVis as mntrVis
import dataframe_image as dfi
import src.utils.sendRobotMessage as sendRobotMessage
import src.data.wind as wind
import src.data.custHF as custHF
import src.analysis.basicAnalysis as basicAnal
import time
# ------------------------------------------------------
# 通过企业微信机器人发送持仓私募基金每日收益情况跟踪，T日发送T-2日数据,此处输入值需为T-2
# ------------------------------------------------------
def timer_sendHoldingHFDaliyReturnResult(date):
    # 如果输入日期为非交易日，则寻找当前最新的交易日期来取持仓数据
    wind_calendar = wind.wind_getSSECalendar()
    # 获取输入日期前5个交易日，统计每天在库已投的产品数量，并取最大值
    date_range = wind_calendar[wind_calendar['date'] <= date]['date'].iloc[-6:-1]
    monitor_history_list = []
    print(datetime.datetime.now().strftime("%Y-%m-%d_%H:%M:%S") + ' 历史信息计算')
    for test_date in date_range:
        ids = custHF.custHF_getProductInfo(['在库已投'])['product_id'].to_list()
        performance_data = basicAnal.basicAnal_calPerformanceStats(ids, test_date, test_date, 'D', "HF", data_level='Product', stats=['period_return'])
        monitor_history_list.append(performance_data)
        print(datetime.datetime.now().strftime("%Y-%m-%d_%H:%M:%S") + ' ' + test_date.strftime("%Y-%m-%d") + ' 在库已投且有收益率产品数量 ' + str(len(performance_data)))
    product_max_num = pd.concat(monitor_history_list, axis=0).groupby('end_date')['id'].count().max()
    # 获取输入日期的日监控数据
    folder_path = 'D:/zhaozekun/FOF_Monitor/'
    image_path_list = []
    monitor_list = []
    for hf_strategy in config.hf_return_monitor_config.keys():
        print(datetime.datetime.now().strftime("%Y-%m-%d_%H:%M:%S")+' 子策略收益计算-'+hf_strategy)
        image_path = folder_path + hf_strategy+'持仓私募产品收益' + str(date) + '.png'
        hf_monitor_result = mntrVis.mntrVis_HFDaliyReturn(hf_strategy, date=date)
        monitor_list.append(hf_monitor_result.data)
        dfi.export(hf_monitor_result, filename=image_path)
        image_path_list.append(image_path)
    # 如果输入日期的产品缺失数量相较于前5个交易日最大数量不超20%，向微信发送监控表，缺失超20%发送缺失数据提示，额外信息行数为7，从总数中减去
    monitor_product_num = (len(pd.concat(monitor_list, axis=0))-7)
    print(datetime.datetime.now().strftime("%Y-%m-%d_%H:%M:%S")+' 等待发送，目标日期的监控产品数-'+str(monitor_product_num))
    # 通过循环检查时间实现定时发送，目前设定为当时间大于等于8点30分发送
    while True:
        time_now = datetime.datetime.now().time()
        if time_now >= datetime.time(8, 30):
            if monitor_product_num > (product_max_num * 0.8):
                # 等待计算完成后统一发送，防止计算过慢的情况下出现消息不连续
                for image_path in image_path_list:
                    print(datetime.datetime.now().strftime("%Y-%m-%d_%H:%M:%S") + ' 发送图片 ' + image_path)
                    robot_response = sendRobotMessage.sendRobotMessage('FOF数据监控助手', 'IMAGE', image_content=image_path)
                    print(robot_response)
            else:
                robot_response = sendRobotMessage.sendRobotMessage('FOF数据监控助手', 'TEXT', text_content="【数据监控】\r 收益监控缺失数据产品数量超过20%，排查中")
                print(robot_response)
            break
        else:
            # 每隔20秒检查一次时间
            time.sleep(20)
    return


if __name__ == '__main__':
    task_name = 'send_hf_daliy_return_monitor_result'
    try:
        # 交易日才会进行发送，发送日期
        date = datetime.date.today()
        wind_calendar = wind.wind_getSSECalendar()
        if date in wind_calendar['date'].to_list():
            # 获取发送当日（T）的前2个交易日日期（T-2）
            execute_date = wind_calendar[wind_calendar['date'] <= date]['date'].iloc[-3]
            timer_sendHoldingHFDaliyReturnResult(execute_date)
    except Exception as error:
        # 正文添加报错信息 邮件通知
        exception_info = traceback.format_exc()
        error_message = 'Task： ' + task_name + '\n\n任务介绍： ' + config.timer_program_info[task_name]['description'] + \
                        '\n\n执行周期： ' + config.timer_program_info[task_name]['period'] + '\n\n报错信息：\n\n' + str(exception_info)
        print(error_message)
        sendMail.sendMail(send_to=["yanruofan@citics.com", "zhaozekun@citics.com", "chenziheng@citics.com"], subject=task_name+' 定时任务报错', text=error_message)
