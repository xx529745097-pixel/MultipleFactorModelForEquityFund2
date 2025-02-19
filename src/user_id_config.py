
######################################################################################
# 用户类型与权限的对应表 为区分母子公司所属账户的展示及功能
# 用户类型 Developer: 开发者  Admin: 超级管理员  Parent: 母公司用户  Subsidiary: 子公司用户
# 权限范围：限制母公司 限制子公司 开发者模式
######################################################################################
user_permissions_map = {
    'Admin': None,
    'Developer': None,
    'Parent': ['母公司'],
    'Subsidiary': ['子公司'],
    'External': ['外部用户']
}

######################################################################################
# 用户权限信息表 区分母子公司所属账户的展示及功能
# 注意：为新用户添加网站权限时需更新下表
# 用户类型 Developer: 开发者  Admin: 超级管理员  Parent: 母公司用户  Subsidiary: 子公司用户  External: 部门外部用户
######################################################################################
user_identification_map = {
    # Special Users
    None: 'Developer',
    'test@localhost.com': 'Developer',
    'fof_super_admin@citics.com': 'Admin',
    'fof_parent_admin@citics.com': 'Parent',
    'fof_subsidiary_admin@citics.com': 'Subsidiary',
    # Ordinary Users
    'weixing@citics.com': 'Subsidiary',
    'zengminrui@citics.com': 'Subsidiary',
    'yanruofan@citics.com': 'Subsidiary',
    'chenshuo@citics.com': 'Subsidiary',
    'chenxiaofei@citics.com': 'Subsidiary',
    'chenxiaoxuan@citics.com': 'Subsidiary',
    'raojiayi@citics.com': 'Subsidiary',
    'wangchongyang@citics.com': 'Subsidiary',
    'wangnanhao@citics.com': 'Subsidiary',
    'rui_wang@citics.com': 'Parent',
    'xupeng3@citics.com': 'Subsidiary',
    'xuzhihua@citics.com': 'Subsidiary',
    'yangning@citics.com': 'Subsidiary',
    'jiongzhang@citics.com': 'Subsidiary',
    'chengjiakang@citics.com': 'Subsidiary',
    'chenjunying@citics.com': 'Subsidiary',
    'gaoyaxin@citics.com': 'Subsidiary',
    'liuchang5@citics.com': 'Subsidiary',
    'liujingli@citics.com': 'Subsidiary',
    'xiayineng@citics.com': 'Subsidiary',
    'lijingyao@citics.com': 'Subsidiary',
    'limengjia@citics.com': 'Subsidiary',
    'zhangzhuohan@citics.com': 'Subsidiary',
    'zhaoxinyue@citics.com': 'Subsidiary',
    'xujunwei@citics.com': 'Subsidiary',
    'zhaozekun@citics.com': 'Subsidiary',
    'limingyu@citics.com': 'Subsidiary',
    'chenziheng@citics.com': 'Subsidiary',
    'qianchangan@citics.com': 'Subsidiary',
    'kongmingyue@citics.com': 'Subsidiary',
    'chenxiangwei@citics.com': 'Subsidiary',
    'yangzhao@citics.com': 'Subsidiary',
    'jinqizhong@citics.com': 'Subsidiary',
    'xurun@citics.com': 'Subsidiary',
    'wen_wen@citics.com': 'Subsidiary',
    'yuzhiyuan@citics.com': 'Subsidiary',
    'lanjinhai@citics.com': 'Subsidiary',
    # External Users
    'heyun@citics.com': 'External'
}

######################################################################################
# 网站管理员账户表
# 注意：如果需要限制管理员账户在堡垒机上登录使用、判断机器IP，则会使用此表，不符要求则assert提示
# 注意：目前无ip限制！
######################################################################################
admin_user_info = {
    # admin账户email
    'email': ['fof_super_admin@citics.com', 'fof_parent_admin@citics.com', 'fof_subsidiary_admin@citics.com'],
    # 目前组内的堡垒机ip
    'ip': ['172.22.218.24', '172.24.130.184'],
}

###############################################
# 本地运行的任务或测试环境下的网页访问的默认邮箱地址配置
###############################################
default_user_email = ['zhaozekun@citics.com']
