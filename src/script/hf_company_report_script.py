import io
import os
import sys
import zipfile
import datetime
import traceback
import pandas as pd
import psutil
sys.path.append('D:/fof_web')
import src.utils.sendMail as sendMail
import src.data.custHF as custHF
import src.script_config as script_config
import src.utils.scriptManager as scriptManager
from reports.hf_company_report import hf_company_report


def script_sendHFCompanyReport(
    strategy_ids,  # 前端选择的策略
    date,  # 报告日期
    anls_start_date,  # 分析开始日期
    target_email_address  # 发送邮箱
):
    strategy_info = custHF.custHF_getStrategyInfo()
    strategy_info = strategy_info[strategy_info['strategy_id'].isin(strategy_ids)]
    company_ids = strategy_info['company_id'].unique().tolist()
    doc_res = {}
    for i, company_id in enumerate(company_ids):
        company_short_name = strategy_info[strategy_info['company_id'] == company_id]['company_short_name'].iloc[0]
        strategy_ids = strategy_info[strategy_info['company_id'] == company_id]['strategy_id'].to_list()
        doc_bio = io.BytesIO()
        doc_bio = hf_company_report.doc_generateHFCompanyReport(company_id=company_id, strategy_ids=strategy_ids, date=date,
                                                                freq='W', anls_start_date=anls_start_date, doc_output_path=doc_bio)
        doc_res['{}_深度报告_{}.docx'.format(company_short_name, date)] = doc_bio
    # 写入压缩文件
    zip_bio = io.BytesIO()
    with zipfile.ZipFile(zip_bio, 'w', zipfile.ZIP_DEFLATED) as zfile:
        for doc_name, doc_bio in doc_res.items():
            zfile.writestr(zinfo_or_arcname=doc_name, data=doc_bio.getvalue())
    # 发送至用户邮箱
    sendMail.sendMail(send_to=target_email_address,
                      subject="深度报告生成结果-" + str(date),
                      text=f"老师您好！\n\n    请查收生成的{'，'.join(strategy_info['company_short_name'].unique().tolist())}深度报告，谢谢！\n\nMARS - Multi-Asset Research Solution",
                      attached_files={f'深度报告生成结果-{date}.zip': zip_bio})
    return zip_bio


if __name__ == '__main__':
    script_id = 'hf_company_report_script'  # script id 请与当前脚本文件名及script_config的key值一致
    script_pid = os.getpid()  # 获取当前脚本的pid
    create_time = datetime.datetime.fromtimestamp(psutil.Process(script_pid).create_time())  # 获取当前脚本启动时间
    exception_flag = False  # 用于在finally模块中判断是否发生异常
    try:
        # 检查入参 数据类型转换
        assert len(sys.argv) == 5, "入参数量有误，请再次确认输入为strategy_ids_str，date_str，anls_start_date_str，target_email_address_str四个参数"
        strategy_ids_str = sys.argv[1]
        date_str = sys.argv[2]
        anls_start_date_str = sys.argv[3]
        target_email_address_str = sys.argv[4]
        strategy_ids = strategy_ids_str.split(',')
        date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
        anls_start_date = datetime.datetime.strptime(anls_start_date_str, '%Y-%m-%d').date()
        target_email_address = target_email_address_str.split(',')

        # start 在数据库中写入进程信息
        scriptManager.script_recordScriptStart(pid=os.getpid(), create_time=create_time, script_id=script_id, user_email=target_email_address, insert=True)
        # 生成并发送报告
        script_sendHFCompanyReport(strategy_ids, date, anls_start_date, target_email_address)
    except Exception as error:
        exception_flag = True  # 发生异常，exception_flag标记为True
        # 正文添加报错信息 邮件通知
        exception_info = traceback.format_exc()
        error_message = 'PID： ' + str(script_pid) + '\n\nCreate time： ' + str(create_time) + '\n\nScript id： ' + script_id + \
                        '\n\nScript desc： ' + script_config.script_program_info[script_id]['description'] + '\n\n报错信息：\n\n' + str(exception_info)
        print(error_message)
        sendMail.sendMail(send_to=["zhaozekun@citics.com", "qianchangan@citics.com"], subject=script_id+' 脚本任务报错', text=error_message)
    finally:
        # terminate 在数据库中写入进程信息,若未发生异常process_status=0,若发生异常process_status=-1
        terminate_time = datetime.datetime.now()
        scriptManager.script_recordScriptTermination(pid=script_pid, create_time=create_time, terminate_time=terminate_time, process_status=-1 if exception_flag else 0, insert=True, is_monitor=False)
