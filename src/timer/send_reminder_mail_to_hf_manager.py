#######################################
# 定时任务程序，未经允许，请不要在本地跑这个程序！！！
#######################################
import traceback
import datetime
import sys
sys.path.append('D:/fof_web')
import src.utils.sendMail as sendMail
import src.config as config
import src.data.wind as wind

# ------------------------------------------------------
# 向管理人发邮件，提醒管理人发送估值表等材料
# 每个月第三个交易日10:00执行发送，每交易日运行任务进行日期检查
# ------------------------------------------------------
def timer_sendReminderMailToHFManager():
    signature = """
    \n\n\n\n\n
    赵泽坤
    FOF业务部
    中信证券资产管理有限公司 
    座机: 010-60833627  
    邮箱:zhaozekun@citics.com
    北京朝阳区亮马桥路48号中信证券大厦16层
    邮编: 100026
    """
    for company in config.mail_send_to_hf_manager.keys():
        print('已发送：' + company)
        sendMail.sendMail(
            send_to=config.mail_send_to_hf_manager[company]['send_to'],
            subject=config.mail_send_to_hf_manager[company]['subject'],
            text=config.mail_send_to_hf_manager[company]['text']+signature,
            carbon_copy_to=config.mail_send_to_hf_manager[company]['carbon_copy_to']
        )

if __name__ == '__main__':
    task_name = 'send_reminder_mail_to_hf_manager'
    try:
        # 交易日才会进行发送
        today = datetime.date.today()
        wind_calendar = wind.wind_getSSECalendar()['date'].to_list()
        current_month_trading_days = [day for day in wind_calendar if
                                      day.year == today.year and day.month == today.month]
        if current_month_trading_days and today == current_month_trading_days[2]:
            # 获取发送当日日期（T），执行日频数据监控
            timer_sendReminderMailToHFManager()
        else:
            print('非执行日期，执行日期为每个月第三个交易日')
    except Exception as error:
        # 正文添加报错信息 邮件通知
        exception_info = traceback.format_exc()
        error_message = 'Task： ' + task_name + '\n\n任务介绍： ' + config.timer_program_info[task_name]['description'] + \
                        '\n\n执行周期： ' + config.timer_program_info[task_name]['period'] + '\n\n报错信息：\n\n' + str(
            exception_info)
        print(error_message)
        sendMail.sendMail(send_to=["yanruofan@citics.com", "zhaozekun@citics.com", "chenziheng@citics.com", "qianchangan@citics.com"], subject=task_name + ' 定时任务报错', text=error_message)