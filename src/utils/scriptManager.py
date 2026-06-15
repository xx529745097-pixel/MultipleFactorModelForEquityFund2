import datetime
import os
import time
import subprocess
import threading
import pandas as pd
import psutil
import src.const as const
import src.data.irm as irm
import src.script_config as script_config
import src.utils.userIdentify as userIdentify
import src.utils.sendMail as sendMail


############################
# script脚本触发程序
############################
def script_triggerScriptTask(
    script_id,  # 脚本名称
    args_list=None  # list，脚本运行参数，参数需为str类型
):
    assert script_id in script_config.script_program_info.keys(), "script_id未注册，请先在script_program_info注册脚本信息"
    target_email_address = userIdentify.user_getUserEmail()
    command = script_config.script_program_info[script_id]['command']
    script_path = script_config.script_program_info[script_id]['script_path']
    exec_line = [command, script_path]
    if args_list:
        assert isinstance(args_list, list), "args_list需为list类型"
        exec_line += args_list
    # 启动进程
    process = subprocess.Popen(
        exec_line,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,  # 将stderr重定向到stdout
        text=True,
        encoding='utf-8',
        errors='ignore',
        bufsize=1  # 行缓冲
    )
    # 启动daemon守护线程来打印输出并进行超时管理(当前代码无需等待守护线程完成即可正常退出)
    # 注意此处的守护线程的父进程是平台streamlit进程，因此当父进程结束时，守护线程也会同步结束
    threading.Thread(target=script_timeoutScriptTask, args=[process, script_config.script_program_info[script_id]['timeout_sec'],
                           script_config.script_program_info[script_id]['description'], target_email_address], daemon=True).start()
    threading.Thread(target=script_screenScriptTask, args=[process, script_config.script_program_info[script_id]['description'], target_email_address], daemon=True).start()
    return process

###################################
# 脚本启动记录
# 通过脚本文件调用，在数据库中写入运行状态
###################################
def script_recordScriptStart(
    pid,          # 进程pid
    create_time,   # 进程创建时间
    script_id,    # script id
    user_email,   # list, 用户email
    insert=False  # 是否将进程信息写入数据库
):
    assert script_id in script_config.script_program_info.keys(), "script_id未定义，需先在script_config.script_program_info注册脚本"
    process_info = pd.DataFrame(columns=['pid', 'create_time', 'script_id', 'script_desc', 'user_email', 'timeout_sec', 'terminate_time', 'process_status', 'update_time'])
    process_info = process_info.append({'pid': pid, 'create_time': create_time, 'script_id': script_id, 'script_desc': script_config.script_program_info[script_id]['description'],
                                        'user_email': ','.join(user_email), 'timeout_sec': script_config.script_program_info[script_id]['timeout_sec'],
                                        'terminate_time': None, 'process_status': 1, 'update_time': datetime.datetime.now()}, ignore_index=True)
    # 写入数据库
    if insert:
        irm.irm_insertIRMData(process_info, 'irm.AMFOF_PLATFORM_SCRIPT_PROCESS_INFO')
    print(f"PID: {pid} - Script Desc: {script_config.script_program_info[script_id]['description']}({','.join(user_email)}) - Start!")
    return

# #########################################################
# 脚本终止记录
# 通过脚本文件的finally模块或超时管理线程调用，在数据库中写入终止状态
# #########################################################
def script_recordScriptTermination(
    pid,              # 进程pid
    create_time,       # 进程启动时间
    terminate_time,         # 进程结束时间
    process_status,   # 进程状态， '0'-正常终止，'-1'-异常中断，'-2'-超时
    insert=False,     # 是否将进程信息写入数据库
    is_monitor=False  # 是否为定时任务调用
):
    assert process_status in script_config.script_process_status_map.keys(), "process_status需为script_config.script_process_status_map中定义的状态"
    # 写入数据库
    if insert:
        # 通过pid和create_time定位进程记录, 更新进程状态信息
        # sql数据库的最小datetime精度为秒，会存在四舍五入导致的偏差，判断时采用+/- 1s区间
        conn = irm.irm_connectIRMDB()
        if not is_monitor:
            sql = "update irm.AMFOF_PLATFORM_SCRIPT_PROCESS_INFO set TERMINATE_TIME={}, PROCESS_STATUS='{}', UPDATE_TIME='{}' where PID='{}' and CREATE_TIME between {} and {} "
            sql = sql.format("STR_TO_DATE('{}', '%Y-%m-%d %H:%i:%s')".format(str(terminate_time)), process_status, datetime.datetime.now(),
                             pid, "STR_TO_DATE('{}', '%Y-%m-%d %H:%i:%s')".format(str(create_time-datetime.timedelta(seconds=const.const.SCRIPT_TIME_EPSILON))),
                             "STR_TO_DATE('{}', '%Y-%m-%d %H:%i:%s')".format(str(create_time+datetime.timedelta(seconds=const.const.SCRIPT_TIME_EPSILON))))
        else:  # 对于异常进程监控定时任务，不对terminate_time进行填充，保留原始状态(留空)
            sql = "update irm.AMFOF_PLATFORM_SCRIPT_PROCESS_INFO set PROCESS_STATUS='{}', UPDATE_TIME='{}' where PID='{}' and CREATE_TIME between {} and {} "
            sql = sql.format(process_status, datetime.datetime.now(), pid, "STR_TO_DATE('{}', '%Y-%m-%d %H:%i:%s')".format(str(create_time-datetime.timedelta(seconds=const.const.SCRIPT_TIME_EPSILON))),
                             "STR_TO_DATE('{}', '%Y-%m-%d %H:%i:%s')".format(str(create_time+datetime.timedelta(seconds=const.const.SCRIPT_TIME_EPSILON))))
        cur = conn.cursor()
        cur.execute(sql)
        conn.commit()
        conn.close()
    print(f"PID: {pid} - Terminated!")
    return

#############################
# script脚本超时管理程序(异步线程运行)
#############################
def script_timeoutScriptTask(
    process,       # 脚本进程对象
    timeout_sec,   # 超时限制
    script_desc,   # 打印输出时的进程标识信息
    target_email_address  # list,触发脚本的用户邮箱
):
    # try防止极端情况下pid传入时process已经结束出现的报错
    try:
        create_time = datetime.datetime.fromtimestamp(psutil.Process(process.pid).create_time())  # 获取脚本进程启动时间
        while True:
            curr_time = datetime.datetime.now()
            # 如果进程已经结束，则退出循环
            if process.poll() is not None:
                break
            # 超时检查
            elif (curr_time - create_time).seconds >= timeout_sec:
                process_pid = process.pid
                # process.kill()方法不会发送 SIGTERM 信号,脚本将不会进入finally块直接结束,因此需要直接调用一次script_recordScriptTermination来写入状态
                process.kill()
                print(f"PID: {process_pid} - Script Desc: {script_desc}({','.join(target_email_address)}) - Timeout! Killed!")
                script_recordScriptTermination(pid=process_pid, create_time=create_time, terminate_time=datetime.datetime.now(), process_status=-2, insert=True, is_monitor=False)
                sendMail.sendMail(send_to=target_email_address+['zhaozekun@citics.com', 'qianchangan@citics.com'], subject=script_desc+' 脚本任务超时',
                                  text=f"老师您好！\n\n    您触发的 PID:{process_pid}-{script_desc} 脚本已超过设定最长运行时间 - {timeout_sec}s，已自动终止并释放资源，给您带来不便请谅解！\n\nMARS - Multi-Asset Research Solution")
                break
            else:
                time.sleep(1)  # 每隔1秒检查一次
    except Exception as e:
        print(e)

############################
# script脚本输出打印程序(异步线程运行)
############################
def script_screenScriptTask(
    process,  # 脚本进程
    script_desc,  # 打印输出时的进程标识信息
    target_email_address  # list,触发脚本的用户邮箱
):
    try:
        # 持续读取子进程的输出并检测进程状态
        while True:
            # 获取输出
            line = process.stdout.readline()
            # 若process进程已结束(包括正常结束和超时终止)，退出当前守护线程
            if (not line) or (process.poll() is not None):
                break
            print(f"PID: {process.pid} - Script Desc: {script_desc}({','.join(target_email_address)}) - Output: {line}", end='')
    except Exception as e:
        print(e)

#############################
# 获取脚本进程信息
#############################
def script_getScriptProcessInfo(
    create_time_start,  # create_time开始时间
    create_time_end  # create_time截止时间
):
    conn = irm.irm_connectIRMDB()
    sql = "select * from irm.AMFOF_PLATFORM_SCRIPT_PROCESS_INFO where CREATE_TIME between {} and {} "
    select_sql = sql.format("STR_TO_DATE('{}', '%Y-%m-%d %H:%i:%s')".format(str(create_time_start)),
                            "STR_TO_DATE('{}', '%Y-%m-%d %H:%i:%s')".format(str(create_time_end)))
    res = pd.read_sql(select_sql, conn).rename(columns=str.lower)
    # datetime类型空值在mysql数据库中存储为'0000-00-00 00:00:00'，在转换时需要添加errors='coerce'参数避免报错
    res['create_time'] = pd.to_datetime(res['create_time'], errors='coerce')
    res['terminate_time'] = pd.to_datetime(res['terminate_time'], errors='coerce')
    res['update_time'] = pd.to_datetime(res['update_time'], errors='coerce')
    res['process_status'] = res['process_status'].apply(int)
    res.reset_index(drop=True, inplace=True)
    conn.close()
    return res

################################
# 更新运行状态脚本的进程信息
################################
def script_recordRunningScriptProcessInfo(
    time,  # 查询时间
    tracked_days  # 回溯天数
):
    assert isinstance(time, datetime.datetime), "time需为datetime类型"
    create_time_start = time - datetime.timedelta(days=tracked_days)
    process_info = script_getScriptProcessInfo(create_time_start, time)
    res = process_info.copy()  # 更新结果
    updated_index = []  # 记录更新的index行
    for index, row in process_info.iterrows():
        if row['process_status'] == 1:  # 检查仍标记为'1'-'Running'中状态的进程
            process_pid = row['pid']
            process_create_time = row['create_time']
            try:
                # 尝试获取process_pid进程
                process = psutil.Process(pid=process_pid)  # 若当前不存在该pid进程则该行报错
                process_status = process.is_running()  # 进程状态，若进程正在运行则为True，若已经终止但尚未被清理则返回False
                if process_status:  # 若该pid对应的进程仍在运行，通过create_time判断是否为同一脚本进程
                    assert abs((process_create_time - process.create_time()).seconds) < const.const.SCRIPT_TIME_EPSILON, \
                        "根据create_time判断，pid相同但不是同一个进程，原进程已终止"  # 若不是同一个进程则跳转至except
            except:
                process_status = False
            if not process_status:  # 如果进程已经终止
                # 通过定时任务检查出终止的进程状态，统一标记为'-1'-'Exception'
                res.loc[index, 'process_status'] = -1
                res.loc[index, 'update_time'] = datetime.datetime.now()
                updated_index.append(index)
    # 删除并重新写入覆盖
    conn = irm.irm_connectIRMDB()
    del_sql = "delete from irm.AMFOF_PLATFORM_SCRIPT_PROCESS_INFO where CREATE_TIME between {} and {} ".format(
        "STR_TO_DATE('{}', '%Y-%m-%d %H:%i:%s')".format(str(create_time_start)),
        "STR_TO_DATE('{}', '%Y-%m-%d %H:%i:%s')".format(str(time)))
    cur = conn.cursor()
    cur.execute(del_sql)
    conn.commit()
    conn.close()
    irm.irm_insertIRMData(res, 'irm.AMFOF_PLATFORM_SCRIPT_PROCESS_INFO')
    # 仅返回更新的条目
    updated_res = res.loc[updated_index, :].copy()
    return updated_res
