####################
# 脚本状态id map
####################
script_process_status_map = {
    1: 'Running',
    0: 'Successfully Terminated',
    -1: 'Exception',
    -2: 'Timeout',
}

###########################
# 脚本任务信息
###########################
script_program_info = {
    'hf_company_report_script': {
        'description': '私募深度报告',  # 脚本描述
        'command': 'python',  # 执行指令
        'script_path': 'src/script/hf_company_report_script.py',  # 脚本路径，统一放在src/script目录下
        'timeout_sec': 7200,  # 单位(秒)
    }
}
