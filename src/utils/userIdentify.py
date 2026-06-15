import streamlit as st
import src.user_id_config as user_id_config


# ------------------------------------------------------
# 获取用户权限 对母子公司账户在网页的展示作限制和区分
# 对于本地运行的定时任务，不设限制
# ------------------------------------------------------
def user_identifier():
    # 对于本地运行的定时任务等程序，跳过识别
    if 'email' not in st.experimental_user.keys():
        return None
    # 对于网站用户，进入识别程序
    user_email = st.experimental_user['email']
    user_ip = st.experimental_user['ip']
    assert user_email in list(user_id_config.user_identification_map.keys()), "该账户未配置权限信息！"
    assert user_id_config.user_identification_map[user_email] in list(user_id_config.user_permissions_map.keys()), "未配置的权限信息！"
    # 此处支持对管理员账户的登录ip进行限制（如需限制需打开如下两行的注释）
    # 注意：目前无限制！
    # if user_email in user_id_config.admin_user_info['email']:
    #     assert user_ip in user_id_config.admin_user_info['ip'], "网站管理员账户仅支持堡垒机访问"
    return user_id_config.user_permissions_map[user_id_config.user_identification_map[user_email]]

# -----------------------------------
# 获取已认证用户的email地址 返回类型为list
# 测试环境下email为None 将发送至默认邮箱
# -----------------------------------
def user_getUserEmail():
    # 对于本地运行的任务或测试环境下的网页访问，返回默认邮箱
    if 'email' not in st.experimental_user.keys():
        return user_id_config.default_user_email
    # 对于网站用户，进入识别程序
    user_email = st.experimental_user['email']
    assert user_email in list(user_id_config.user_identification_map.keys()), "该账户未配置权限信息！"
    assert user_id_config.user_identification_map[user_email] in list(user_id_config.user_permissions_map.keys()), "未配置的权限信息！"
    return [user_email] if user_id_config.user_identification_map[user_email] not in ('Admin', 'Developer') else user_id_config.default_user_email
