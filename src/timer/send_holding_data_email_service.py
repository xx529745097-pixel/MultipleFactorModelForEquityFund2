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
import src.data.custFOF as custFOF
import src.analysis.portfolioAnalysis as portAnls

# ------------------------------------------------------
# 通过邮件将具有标签信息的持仓总表通过email发送至投资经理邮箱
# ------------------------------------------------------
def timer_sendHoldingDataEmailService(
    date,            # 监控的数据日期
):
    holding = portAnls.anlsFOF_getFOFHoldingDataWithProductLabel(date)
    ref = custFOF.custFOF_getFOFReferenceData()     # 限制账户范围，保证只有子公司账户被发送
    holding = holding[holding['portfolio_id'].isin(ref['portfolio_id'].tolist())]
    rename_dict = {
        'portfolio_name': '组合名称',
        'portfolio_id': '组合ID',
        'NAV': '组合规模',
        'date': '数据日期',
        'product_id': '产品ID',
        'product_name': '产品名称',
        'product_type': '产品类型',
        'product_volume': '持仓份额',
        'product_weight': '产品权重',
        'product_NAV': '产品规模',
        'label_level_1': '一级标签',
        'label_level_2': '二级标签',
        'allocation_type': '大类配置类型',
        'unit_cost': '单位成本',
        'unit_val': '估值价格',
        'product_appreciation': '估值增值',
    }
    holding = holding.rename(columns=rename_dict)
    holding = holding[list(rename_dict.values())]
    folder_path = 'D:/zhaozekun/Holding_Data/'
    holding.to_excel(folder_path + '持仓数据汇总.xlsx', index=False)
    sendMail.sendMail(send_to=['chenshuo@citics.com', 'zhaozekun@citics.com'], subject="持仓数据汇总-"+str(execute_date), text="",
                      attached_files={'持仓数据汇总.xlsx': folder_path + '持仓数据汇总.xlsx'})
    return


if __name__ == '__main__':
    task_name = 'send_holding_data_email_service'
    try:
        # 交易日才会进行发送
        date = datetime.date.today()
        wind_calendar = wind.wind_getSSECalendar()
        if date in wind_calendar['date'].to_list():
            execute_date = wind_calendar[wind_calendar['date'] <= date]['date'].iloc[-3]
            timer_sendHoldingDataEmailService(execute_date)
    except Exception as error:
        # 正文添加报错信息 邮件通知
        exception_info = traceback.format_exc()
        error_message = 'Task： ' + task_name + '\n\n任务介绍： ' + config.timer_program_info[task_name]['description'] + \
                        '\n\n执行周期： ' + config.timer_program_info[task_name]['period'] + '\n\n报错信息：\n\n' + str(exception_info)
        print(error_message)
        sendMail.sendMail(send_to=["zhaozekun@citics.com", "chenziheng@citics.com", "qianchangan@citics.com"], subject=task_name+' 定时任务报错', text=error_message)