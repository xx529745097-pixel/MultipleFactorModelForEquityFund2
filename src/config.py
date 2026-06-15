#################################################
# 获取FOF组合底层各类策略标签级别、比较基准数据源、比较基准代码、比较基准中文名
# 由于私募新规后朝阳永续缺数,目前所有子策略默认基准都先使用wind指数
#################################################
port_label_mapping = {
    '股票多头': {'label_key': ['主观权益', '指数增强', '行业主题', 'ETF'], 'label_level': 'label_level_1', 'benchmark_source': 'wind',
             'benchmark': '000906.SH', 'name': '中证800指数'},
    '主观权益': {'label_key': ['主观权益'], 'label_level': 'label_level_1', 'benchmark_source': 'wind',
             'benchmark': '000906.SH', 'name': '中证800指数'},
    '行业主题': {'label_key': ['行业主题'], 'label_level': 'label_level_1', 'benchmark_source': 'wind',
             'benchmark': '000906.SH', 'name': '中证800指数'},
    'ETF': {'label_key': ['ETF'], 'label_level': 'label_level_1', 'benchmark_source': 'wind',
             'benchmark': '000906.SH', 'name': '中证800指数'},
    '纯债基金': {'label_key': ['纯债基金'], 'label_level': 'label_level_2', 'benchmark_source': 'wind',
             'benchmark': '885008.WI', 'name': '中长期纯债型基金指数'},
    '二级债基': {'label_key': ['二级债基'], 'label_level': 'label_level_2', 'benchmark_source': 'wind',
             'benchmark': '885007.WI', 'name': '万得混合债券型二级基金指数'},
    '300指增': {'label_key': ['300指增'], 'label_level': 'label_level_2', 'benchmark_source': 'wind',
              'benchmark': '000300.SH', 'name': '沪深300指数'},
    '500指增': {'label_key': ['500指增'], 'label_level': 'label_level_2', 'benchmark_source': 'wind',
              'benchmark': '000905.SH', 'name': '中证500指数'},
    '1000指增': {'label_key': ['1000指增'], 'label_level': 'label_level_2', 'benchmark_source': 'wind',
               'benchmark': '000852.SH', 'name': '中证1000指数'},
    '市场中性': {'label_key': ['市场中性'], 'label_level': 'label_level_2', 'benchmark_source': 'wind',
             'benchmark': '885008.WI', 'name': '中长期纯债型基金指数'},
    '量化对冲': {'label_key': ['量化对冲'], 'label_level': 'label_level_1', 'benchmark_source': 'wind',
             'benchmark': '885008.WI', 'name': '中长期纯债型基金指数'},
    'CTA': {'label_key': ['期货策略'], 'label_level': 'label_level_1', 'benchmark_source': 'wind',
               'benchmark': 'CAMO2.WI', 'name': '中信证券商品动量2.0'},
    '低波动CTA': {'label_key': ['低波动CTA'], 'label_level': 'label_level_2', 'benchmark_source': 'wind',
               'benchmark': 'CAMO2.WI', 'name': '中信证券商品动量2.0'},
    '中波动CTA': {'label_key': ['中波动CTA'], 'label_level': 'label_level_2', 'benchmark_source': 'wind',
               'benchmark': 'CAMO2.WI', 'name': '中信证券商品动量2.0'},
    '高波动CTA': {'label_key': ['高波动CTA'], 'label_level': 'label_level_2', 'benchmark_source': 'wind',
               'benchmark': 'CAMO2.WI', 'name': '中信证券商品动量2.0'},
    '宏观策略': {'label_key': ['宏观策略'], 'label_level': 'label_level_2', 'benchmark_source': 'wind',
             'benchmark': '000906.SH', 'name': '中证800指数'},
    '套利策略': {'label_key': ['套利策略'], 'label_level': 'label_level_1', 'benchmark_source': 'wind',
             'benchmark': '885008.WI', 'name': '中长期纯债型基金指数'},
    '稳健类策略': {'label_key': ['量化对冲', '套利策略', '债券策略'], 'label_level': 'label_level_1', 'benchmark_source': 'wind',
             'benchmark': '885008.WI', 'name': '中长期纯债型基金指数'},
}

#####################################################################
# 获取具体FOF产品线对应的四级标签：一级、二级、三级分类和管理类型，当前支持私享
#####################################################################
specific_FOF_product_line = {
    'sixiang': {
        'level_1_type': ['单一定制'],
        'level_2_type': ['财富委', '财富委线下直销', '机构定制'],
        'level_3_type': ['纯债型', '保守型', '稳健型', '平衡型', '积极型', '进取型', '臻选类', '臻选A', '臻选B', '臻选C', '臻选D'],
        'management_type': ['定制业务', '主动管理'],
    },
    'huixiang': {
        'level_1_type': ['单一定制'],
        'level_2_type': ['中国银行'],
        'level_3_type': ['稳健型'],
        'management_type': ['主动管理'],
    },
    'sixiang+huixiang': {
        'level_1_type': ['单一定制'],
        'level_2_type': ['财富委', '财富委线下直销', '机构定制', '中国银行'],
        'level_3_type': ['保守型', '稳健型', '平衡型', '积极型', '进取型'],  # 经沟通私享慧享暂时删去纯债型，安享账户分类包含其他纯债型账户
        'management_type': ['定制业务', '主动管理'],
    },
    # 与京利老师沟通确认，安享系列里面也带上财富委线下直销的债券类策略
    'anxiang': {
        'level_1_type': ['单一定制'],
        'level_2_type': ['财富委', '财富委线下直销', '机构定制'],
        'level_3_type': ['纯债型'],
        'management_type': ['定制业务', '主动管理'],
    },
    'pure_sixiang': {
        'level_1_type': ['单一定制'],
        'level_2_type': ['机构定制', '财富委', '财富委线下直销'],
        'level_3_type': ['平衡型', '积极型', '稳健型', '保守型', '进取型', '纯债型'],
        'management_type': ['定制业务', '主动管理']
    },
}

#####################################################################
# 发送邮箱程序sendMail.py的发件人密码配置，如需新增请找赵泽坤
#####################################################################
send_mail_passwords = {
    "amfof@citics.com": "uqufraxwapdfmemt",
    "amfofdata@citics.com": "gbfjhqxnkvdynyvt",
    "zhaozekun@citics.com": "yutmqvyhrczmyrph",
}

#####################################################################################
# 月度发送重点账户组合分析报告的账户配置信息
# 程序发送的邮件附件不得超过28M,为防止邮件拒收，单个PM账户过多时则拆分config,分多封邮件发送
# 一般情况下,一封邮件附件容量支持5个以内的账户报告
#####################################################################################
key_accounts_config = {
    "张泂": {
        'mail_address': 'jiongzhang@citics.com',
        'key_accounts': {
            '21644': '天合9号',
            '21796': '星云55号',
            '21344': '财富配置1号',
            '21498': '财富配置2号',
            '21713': '财富全天候1号',
        }
    },
    "曾旻睿_part_1": {
        'mail_address': 'zengminrui@citics.com',
        'key_accounts': {
            '21511': '财富优选CTA策略1号',
            '21520': '财富精选指数增强1号',
            '701822': '财富私享交银稳健25号',
            '21942': '财富私享南银FOF1期',
        }
    },
    "曾旻睿_part_2": {
        'mail_address': 'zengminrui@citics.com',
        'key_accounts': {
            '703971': '财富私享投资771号',
            '704657': '财富私享投资1203号',
            '704050': '财富私享投资809号',
            '704859': '财富私享投资1681号',
        }
    },
    "曾旻睿_part_3": {
        'mail_address': 'zengminrui@citics.com',
        'key_accounts': {
            '704479': '财富私享投资851号',
            '704485': '财富私享投资1071号',
            '700924': '浙盈1号',
        }
    },
    "曾旻睿_part_4": {
        'mail_address': 'zengminrui@citics.com',
        'key_accounts': {
            '705383': '财富私享投资2255号',
            '705395': '财富私享投资2300号',
            '705392': '信圆1号',
        }
    },
    "曾旻睿_part_5": {
        'mail_address': 'zengminrui@citics.com',
        'key_accounts': {
            '21995': '信盈积极（季初）1号',
            '22012': '信盈积极（季中）1号',
            '21996': '信盈积极（季末）1号',
        }
    },
    "曾旻睿_part_6": {
        'mail_address': 'zengminrui@citics.com',
        'key_accounts': {
            '21680': '天衡1号',
            '21711': '天衡11号',
            '21712': '天衡15号',
        }
    },
    "陈朔_part_1": {
        'mail_address': 'chenshuo@citics.com',
        'key_accounts': {
            '22001': '信盈稳健（季末）1号',
            '22000': '信盈稳健（季初）1号',
            '22014': '信盈稳健（季中）1号',
        }
    },
    "陈朔_part_2": {
        'mail_address': 'chenshuo@citics.com',
        'key_accounts': {
            '22037': '信盈稳健（季初）2号',
            '22049': '信盈稳健（季中）2号',
            '22065': '信盈稳健（季末）2号',
            '300386': '信选量化多头1号',
        }
    },
    "杨宁": {
        'mail_address': 'yangning@citics.com',
        'key_accounts': {
            '21785': '善建进取1号',
            '21429': '信享盛世1号',
        }
    },
    "王锐": {
        'mail_address': 'rui_wang@citics.com',
        'key_accounts': {
            '300021': '私享权益FOF1号',
            '300070': '锐选FOF1号',
        }
    },
    "汪崇阳_part_1": {
        'mail_address': 'wangchongyang@citics.com',
        'key_accounts': {
            '21718': '信赢1号',
            '21747': '信赢2号',
            '20800': '中信证券财富优选',
        }
    },
    "汪崇阳_part_2": {
        'mail_address': 'wangchongyang@citics.com',
        'key_accounts': {
            '704712': '慧享128号',
            '21835': '星河35号',
            '21833': '星云61号',
            '705074': '星辰多策略2号',
        }
    },
    "闫若凡_part_1": {
        'mail_address': 'yanruofan@citics.com',
        'key_accounts': {
            '705233': '信亿1号',
            '705245': '慧享定制188号',
            '22059': '汇享平衡1号',
            '22094': '汇享指增1号',
        }
    },
    "闫若凡_part_2": {
        'mail_address': 'yanruofan@citics.com',
        'key_accounts': {
            '21998': '信盈平衡（季末）1号',
            '21997': '信盈平衡（季初）1号',
            '22013': '信盈平衡（季中）1号',
        }
    },
    "王南浩_part_1": {
        'mail_address': 'wangnanhao@citics.com',
        'key_accounts': {
            '21768': '建享平衡1号',
            '21769': '建享平衡2号',
        }
    },
    "王南浩_part_2": {
        'mail_address': 'wangnanhao@citics.com',
        'key_accounts': {
            '22116': '信盈稳安（季初）1号',
            '22124': '信盈稳安（季中）1号',
            '22130': '信盈稳安（季末）1号',
        }
    },
    "王南浩_part_3": {
        'mail_address': 'wangnanhao@citics.com',
        'key_accounts': {
            '300284': '信选机遇FOF1号',
            '300476': '信选机遇FOF2号',
            '300366': '信选稳健1期',
            '300367': '信选稳健2期',
        }
    },
    "许智华": {
        'mail_address': 'xuzhihua@citics.com',
        'key_accounts': {
            '701934': '华夏人寿FOF1号',
        }
    },
}

#####################################################################
# 投委会报告个人汇总页 - 账户系列划分和需要详细单账户分析的配置信息
# 目前账户系列按照关键字匹配的方式进行分类
#####################################################################
invest_commitee_key_accounts_config = {
    "张泂": {
        'mail_address': 'jiongzhang@citics.com',
        'account_groups': {
            '天合': '天合系列',
            '财富全天候': '财富全天候',
            '建悦盛世': '建悦盛世',
            '星河': '星河多策略',
            '财富配置': '财富配置',
            '财富安享': '财富安享',
            '财富私享': '财富私享',
        },
        'key_accounts': {
            '21630': '天合7号',
        }
    },
    "曾旻睿": {
        'mail_address': 'zengminrui@citics.com',
        'account_groups': {
            '财富私享': '财富私享',
            '信享至上': '信享至上',
            '财富精选指数增强': '财富精选指数增强',
            '财富优选CTA': '财富优选CTA策略',
            '浙盈': '浙盈系列',
            '智赢': '智赢系列',
            '圆融睿享': '圆融睿享多策略',
            '财富精选量化': '财富精选量化策略',
            '龙鑫': '龙鑫',
            '隆和尊享': '隆和尊享',
            '天衡': '天衡系列',
        },
        'key_accounts': {
            '21511': '财富优选CTA策略1号',
            '21520': '财富精选指数增强1号',
        }
    },
    "陈朔": {
        'mail_address': 'chenshuo@citics.com',
        'account_groups': {
            '财富私享': '财富私享',
            '信盈': '信盈系列',
            '创盈': '创盈系列',
            '朝云': '朝云系列',
        },
        'key_accounts': {
            '702892': '财富私享投资390号',
        }
    },
    "杨宁": {
        'mail_address': 'yangning@citics.com',
        'account_groups': {
            '财富私享': '财富私享',
            '信享盛世': '信享盛世',
            '慧享': '中行私行全委-慧享定制',
            '善建进取': '善建进取',
            '世家华传': '世家华传',
            '外贸财富': '外贸财富',
        },
        'key_accounts': {
            '21785': '善建进取1号',
            '21429': '信享盛世1号',
        }
    },
    "王锐": {
        'mail_address': 'rui_wang@citics.com',
        'account_groups': {
            '财富私享': '财富私享',
        },
        'key_accounts': {
            '300021': '私享权益FOF1号',
            '300070': '锐选FOF1号',
        }
    },
    "汪崇阳": {
        'mail_address': 'wangchongyang@citics.com',
        'account_groups': {
            '星辰多策略': '星辰多策略',
            '财富私享': '财富私享',
            '稳盈添利': '稳盈添利',
            '湘盈': '湘盈',
            '慧享': '中行私行全委-慧享定制',
            '鼎利': '鼎利',
            '星云': '星云',
            '星河': '星河',
            '信赢': '信盈',
            '财富优选': '财富优选',
        },
        'key_accounts': {
            '20800': '中信证券财富优选',
        }
    },
    "闫若凡": {
        'mail_address': 'yanruofan@citics.com',
        'account_groups': {
            '财富私享': '财富私享',
            '信亿': '财富私享',
            '慧享': '慧享',
            '信享': '财富私享',
        },
        'key_accounts': {
            '704869': '财富私享投资1691号',
            '705233': '信亿1号',
            '705245': '慧享定制188号',
            '21998': '信盈平衡（季末）1号',
        }
    },
    "王南浩": {
        'mail_address': 'wangnanhao@citics.com',
        'account_groups': {
            '财富私享': '财富私享',
            '晋盈': '财富私享',
            '建享平衡': '建享平衡',
            '信享': '财富私享',
            '财富盛远': '财富盛远',
            '智选30': '智选30',
            '天衡': '天衡FOF',
        },
        'key_accounts': {
            '21768': '建享平衡1号',
            '300284': '外贸信托信选机遇FOF1号',
        }
    },
    "饶嘉懿": {
        'mail_address': 'raojiayi@citics.com',
        'account_groups': {
            '财富私享': '财富私享',
            '晋盈': '财富私享',
            '信享': '财富私享',
        },
        'key_accounts': {
            '705186': '财富私享投资1825号',
        }
    },
}

#####################################################################
# 投委会报告第1/2/3页 - 集合产品A类账户的代表账户绩效汇总 - 配置汇总表
# key: port_id, value: port_name 账户名称 port_strategy_type 策略类别
#####################################################################
invest_commitee_pooled_key_accounts_config = {
    '21520': {'port_name': '财富精选指数增强1号', 'port_strategy_type': '指数增强'},
    '21763': {'port_name': '智选30FOF1号', 'port_strategy_type': '主动权益'},
    '21835': {'port_name': '星河35号FOF', 'port_strategy_type': '主动权益'},
    '21776': {'port_name': '湘盈FOF1号', 'port_strategy_type': '主动权益'},
    '21511': {'port_name': '财富优选CTA策略1号FOF', 'port_strategy_type': 'CTA'},
    '21785': {'port_name': '善建进取1号FOF', 'port_strategy_type': '主动权益'},
    '21429': {'port_name': '信享盛世1号FOF', 'port_strategy_type': '主动权益'},
    '20800': {'port_name': '中信证券财富优选', 'port_strategy_type': '主动权益'},
    '21796': {'port_name': '星云55号', 'port_strategy_type': '稳健型'},
    '21344': {'port_name': '财富配置1号FOF集合', 'port_strategy_type': '稳健型'},
    '21713': {'port_name': '财富全天候1号FOF', 'port_strategy_type': '积极型'},
    '21942': {'port_name': '财富私享南银FOF1期', 'port_strategy_type': '平衡型'},
    '21768': {'port_name': '建享平衡1号FOF', 'port_strategy_type': '平衡型'},
    '21481': {'port_name': '建悦盛世5号FOF', 'port_strategy_type': '积极型'},
    '21630': {'port_name': '天合7号FOF', 'port_strategy_type': '稳健型'},
    '21680': {'port_name': '天衡1号FOF', 'port_strategy_type': '积极型'},
    '21996': {'port_name': '信盈积极（季末）1号', 'port_strategy_type': '积极型'},
    '21998': {'port_name': '信盈平衡（季末）1号', 'port_strategy_type': '平衡型'},
    '22001': {'port_name': '信盈稳健（季末）1号', 'port_strategy_type': '稳健型'},
    '21718': {'port_name': '信赢1号FOF', 'port_strategy_type': '稳健型'},
    '705074': {'port_name': '星辰多策略2号FOF', 'port_strategy_type': '稳健型'},
}

##########################################################################
# 投委会报告第1/2/3页 - 集合产品A类账户的代表账户绩效汇总 - 配置明细表 用于配置多页分开展示
# key: 页面顺序 value: port_id list
##########################################################################
invest_commitee_pooled_key_accounts_multi_pages_config = {
    '信盈': {
        '22001': {'port_name': '信盈稳健（季末）1号', 'port_strategy_type': '稳健型'},
        '21998': {'port_name': '信盈平衡（季末）1号', 'port_strategy_type': '平衡型'},
        '21996': {'port_name': '信盈积极（季末）1号', 'port_strategy_type': '积极型'},
    },
    '主动权益': {
        '21763': {'port_name': '智选30FOF1号', 'port_strategy_type': '主动权益'},
        '21835': {'port_name': '星河35号FOF', 'port_strategy_type': '主动权益'},
        '21785': {'port_name': '善建进取1号FOF', 'port_strategy_type': '主动权益'},
        '21429': {'port_name': '信享盛世1号FOF', 'port_strategy_type': '主动权益'},
        '20800': {'port_name': '中信证券财富优选', 'port_strategy_type': '主动权益'},
    },
    '指数增强': {
        '21520': {'port_name': '财富精选指数增强1号', 'port_strategy_type': '指数增强'},
    },
    'CTA': {
        '21511': {'port_name': '财富优选CTA策略1号FOF', 'port_strategy_type': 'CTA'},
    },
    '稳健型': {
        '705074': {'port_name': '星辰多策略2号FOF', 'port_strategy_type': '稳健型'},
        '21796': {'port_name': '星云55号', 'port_strategy_type': '稳健型'},
        '21344': {'port_name': '财富配置1号FOF集合', 'port_strategy_type': '稳健型'},
        '21630': {'port_name': '天合7号FOF', 'port_strategy_type': '稳健型'},
        '21718': {'port_name': '信赢1号FOF', 'port_strategy_type': '稳健型'},
    },
    '平衡型': {
        '21942': {'port_name': '财富私享南银FOF1期', 'port_strategy_type': '平衡型'},
        '21768': {'port_name': '建享平衡1号FOF', 'port_strategy_type': '平衡型'},
    },
    '积极型': {
        '21713': {'port_name': '财富全天候1号FOF', 'port_strategy_type': '积极型'},
        '21481': {'port_name': '建悦盛世5号FOF', 'port_strategy_type': '积极型'},
        '21680': {'port_name': '天衡1号FOF', 'port_strategy_type': '积极型'},
    },
}

#####################################################################
# 定时任务timer程序信息
#####################################################################
timer_program_info = {
    'insert_fof_perf_stats': {
        'description': 'FOF组合YTD绩效缓存任务',
        'period': '每天0:00执行',
    },
    'insert_index_barra_factor_exposure': {
        'description': '指数BARRA因子暴露缓存任务',
        'period': '每天23:00执行',
    },
    'insert_strategy_rating_snapshot': {
        'description': '公募私募策略评级储存任务',
        'period': '每天23:30执行',
    },
    'insert_zyyx_universe_distribution': {
        'description': 'ZYYX universe分位数缓存任务',
        'period': '每周五23:00执行',
    },
    'send_fof_single_perf_report': {
        'description': '重点账户组合分析报告批量发送任务',
        'period': '每月3号(含)到10号(不含)之间的周六9:00执行',
    },
    'insert_zyyx_universe_product_return': {
        'description': 'ZYYX universe product return 缓存任务',
        'period': '每周五22:00执行',
    },
    'send_hf_track_monitor_result': {
        'description': '通过企业微信机器人(FOF数据监控)发送持仓私募基金是否已有业绩跟踪的情况',
        'period': '每个工作日10:00执行',
    },
    'send_hf_warning_threshold_monitor_result': {
        'description': '通过企业微信机器人(FOF数据监控)发送持仓私募基金触及预警线、止损线的情况',
        'period': '每个工作日10:01执行',
    },
    'send_holding_concentration_monitor_result': {
        'description': '通过企业微信机器人(FOF数据监控)发送账户持有单一基金(阈值25%)、单一公司(阈值35%)集中度情况',
        'period': '每个工作日10:02执行',
    },
    'send_hf_current_drawdown_monitor_result': {
        'description': '通过企业微信机器人(FOF数据监控助手)发送持仓私募基金最近一年的当前回撤情况',
        'period': '每个工作日8:35执行',
    },
    'insert_holding_product_list': {
        'description': '向IRM推送持有产品列表，执行当日为T，发送内容为T-1和T-8持仓产品的并集',
        'period': '每交易日22:00执行',
    },
    'send_hf_daliy_return_monitor_result': {
        'description': '通过企业微信机器人发送持仓私募基金日度收益情况，T日发送T-2日',
        'period': '每交易日8:20执行，8:30发送结果',
    },
    'insert_customized_index_return': {
        'description': '定制指数日频收益率缓存任务，每个交易日执行',
        'period': '每交易日21:00执行',
    },
    'insert_wind_fund_index_component': {
        'description': 'wind基金指数成份缓存任务，每月1号执行',
        'period': '每月1号21:10执行',
    },
    'send_hf_strategy_limit_monitor_result': {
        'description': '通过企业微信机器人(FOF数据监控助手)发送账户持有私募策略触达上限(阈值90%)的情况, 每周一额外发送数据含投顾日期为上上周五数据',
        'period': '每交易日9:00执行',
    },
    'send_sx_account_equity_strategy_proportion': {
        'description': '通过企业微信机器人(私享服务支持)发送私享账户权益持仓分布每周监控并与上周对比',
        'period': '每个周五交易日15:00执行',
    },
    'send_stock_index_futures_basis_monitor_result': {
        'description': '通过企业微信机器人(FOF数据监控助手)发送股指期货基差走势图与基差贡献',
        'period': '每交易日17:00执行',
    },
    'insert_cta_factor_value_and_returns':{
        'description': 'CTA因子、因子收益率计算与缓存，每交易日',
        'period': '每交易日22:00执行',
    },
    'send_mf_member_adjustment_monitor_result': {
        'description': '通过企业微信机器人(FOF数据监控助手)每周发送公募高管和基金经理变动情况',
        'period': '每周一16:00执行',
    },
    'send_etf_market_liquid_share_net_chg_monitor_result':{
        'description': '通过企业微信机器人(FOF数据监控助手)每交易日发送ETF全市场净申购赎回份额',
        'period': '每交易日08:45执行',
    },
    'insert_current_holding_strategy_info': {
        'description': '最新持仓策略规模信息缓存，存入当前存续各账户的最新持仓数据，每交易日执行',
        'period': '每交易日22:05执行'
    },
    'send_hf_company_limit_monitor_result': {
        'description': '私募管理人层级最新持仓规模预警监控，每周发送账户持有私募管理人规模触达上限(阈值90%)的情况',
        'period': '每周一09:05执行'
    },
    'send_reminder_mail_to_hf_manager': {
        'description': '向管理人发邮件，提醒管理人发送估值表等材料',
        'period': '每个月第三个交易日10:00执行发送，每交易日运行任务进行日期检查',
    },
    'send_hf_valuation_sheet_anls_monitor_result': {
        'description': '私募产品估值表风险筛查系列监控，月度发送筛查结果',
        'period': '每月第二个周五10:30执行'
    },
    'send_zfsx_last_month_trade_flow': {
        'description': '浙分私享上月交易明细发送',
        'period': '每月第5个交易日10:00执行发送，每日进行日期检查'
    },
    'insert_script_process_status': {
        'description': '监控并更新脚本进程运行状态',
        'period': '每日23:00执行'
    },
    'insert_fof_holding_valuation_sheet_cache': {
        'description': '向IRM推送账户调整后的持仓数据(包括归因模型的中间变量，可作为归因分析的计算输入)，逻辑为T日写入T-16至T-2日数据',
        'period': '每日21:00执行'
    },
    'send_mf_core_pool_daily_perf_monitor_result': {
        'description': '通过企业微信机器人发送公募核心库每日收益情况跟踪，T日发送T-1日',
        'period': '每日8:15执行'
    },
    'send_holding_data_email_service': {
        'description': '通过邮件将具有标签信息的持仓总表通过email发送至投资经理邮箱，T日晚发送T-2日',
        'period': '每日19:00执行'
    }
}

#####################################################################
# 后端含权益持仓的产品信息, 用于多头行业穿透时计算至产品底层
# key: product_id value: portfolio_id product_name
#####################################################################
back_end_product_info = {
    '9099BB.OF': {'portfolio_id': '21835', 'product_name': '中信星河35号FOF'},
    '90999S.OF': {'portfolio_id': '21763', 'product_name': '智选30FOF1号'},
    '9099BC.OF': {'portfolio_id': '21833', 'product_name': '中信星云61号FOF'},
}

#####################################################################
# 异常账户信息, 在计算私享perf均值时需要筛去异常账户
#####################################################################
abnormal_accounts_info = {
    '704399': {'portfolio_name': '财富私享投资705号FOF', 'description': '客户未完全清算，账户内仅存少量现金导致净值异常'},
}

#####################################################################
# CAMP交易流数据的交易类型、产品类型映射关系配置
#####################################################################
camp_trade_flow_config = {
    'trade_type_map': {
        '证券卖出': '卖出',
        '证券买入': '买入',
        '基金赎回': '卖出',
        '基金申购': '买入',
        '基金转出': '卖出',
        '基金转入': '买入',
        '理财申购': '买入',
        '理财赎回': '卖出',
        '信托申购': '买入',
        '信托赎回': '卖出',
        '债券卖出': '卖出',
        '债券买入': '买入',
        '分销卖出': '卖出',
        '分销买入': '买入',
        '固定收益卖出': '卖出',
        '固定收益买入': '买入',
        '基金认购': '买入',
        '理财认购': '买入',
        '信托认购': '买入',
    },
    'product_type_map': {
        '场外开放式基金': '公募基金',
        'LOF': '公募基金',
        '理财产品': '私募基金',
        '信托计划': '私募基金',
    },
}

#####################################################################
# 私募产品的额外附加标签信息
# 目前主要为中性产品的细分分析使用
#####################################################################
product_additional_label = {
    '300对冲': {
        'STT372.OF': '世纪前沿松柏量化对冲1号',
        'SST749.OF': '明汯春晓二十七期',
        'SNN022.OF': '世纪前沿300对冲专享2号',
    }
}

#####################################################################
# 私募多头产品的额外附加标签信息
# 目前主要功能为：不需考虑持仓水平相对历史中位数变化的产品，分析时剔除
#####################################################################
ff_product_exclude_label = {
    'SNZ730.OF': '丹羿安心5号',
    'SLW570.OF': '千合昀锦5号',
    'SNA424.OF': '千合资本-积极成长多策略',
    'SQH103.OF': '元葵宏观策略天时3号',
    'SSB112.OF': '庐雍优势成长8号',
    'SNU461.OF': '睿泉成长8号',
    'SNK101.OF': '石锋慎思11号',
    'SLF969.OF': '衍复博裕增强一号',
    'SQF180.OF': '重阳致远8号',
    'SSE495.OF': '钦沐创新动力2号',
    'SJA184.OF': '马拉松20号',
}

############################################################################################################
# 账户监控功能的需要排除在外不进行分析的账户
# 通过关键词进行筛选，目前在监控账户持仓产品是否有业绩跟踪、是否维护成在库已投时，不考虑投顾、万通一号、臻选（臻选使用三级标签筛选）
############################################################################################################
monitor_exclude_account = {
    'key_word': ['投顾', '万通1号']
}

####################################
# 持仓监控功能的需要排除的外部投资经理列表
####################################
monitor_exclude_external_pm_list = ['杜楠', '马婕', '李荣', '代蓓蓓', '周雁', '李栋梁', '马艳', '黄德龙', '程诚', '武国利', '杜伯钊',
                                    '李薇', '马晓飞', '韩笑', '于质冰', '马鲁阳', '贺昀']

#####################################################################
# CTA托管监控代表产品
#####################################################################
cta_monitoring_products_config = {
    'SQR114.OF':'会世元丰CTA9号',
    'SX5355.OF':'千象磐石29号',
    'STG372.OF':'吾执九二号',
    'SQZ294.OF':'宏锡信长量化CTA',
    'SGT306.OF':'宽德致信2号',
    'SVN548.OF':'德贝激享CTA7号',
    'STA716.OF':'思晔趋势11号',
    'SGU025.OF':'洛书瑞盈元延',
    'SSC910.OF':'白鹭鼓浪屿定制信享1号',
    'SXG025.OF':'迈德瑞趋势机会9号',
    'SGU806.OF':'黑翼CTA十三号',
    'SJE357.OF':'黑翼CTA十号',
    'STL382.OF': '涵德成益量化混合27号',
    'SAAD20.OF':'远澜信享银杏6号',
    'SAEK28.OF':'因诺信享CTA1号',
    '90996A.OF': '量子CTA1号',
    '9099FQ.OF': '丰泽量化多策略1号'
}

#####################################################################
# 持仓集中度监控功能所需要剔除的各级产品类型和账户id
# key: 所需剔除的产品标签level, value: 该标签级别下所需剔除的类型
#####################################################################
holding_concentration_monitor_exclude_config = {
    # FIXME 目前直接剔除公募基金不进行集中度检查因为基本为货币基金且公募基金标签体系未确定
    'product_type': ['证券清算款', '债券', '应收利息', '其它资产', '公募基金'],
    'company_short_name': ['中信证券'],
    'portfolio_id': ['704045'],  # 创盈1号，共管大宗户
}

#####################################################################
# 产品当前回撤监控各策略类型的阈值
# 产品当前回撤监控时，对每类策略设置不同的阈值，按照一级标签进行分类
# key: 一级标签, value: 需要监控提示的阈值水平（负数，小于该值时进行提示）
# 对于债券策略，细化至二级标签设置阈值
#####################################################################
product_current_drawdown_monitor_config = {
    'label_level_1': {
        '主观权益': -0.18,
        '指数增强': -0.05,  # 指增考察超额回撤
        '期货策略': {
            '低波动CTA': -0.045,
            '中波动CTA': -0.09,
            '高波动CTA': -0.13,
            '市场中性+CTA': -0.04,
        },
        '量化对冲': {
            'DMA': -0.16,
            '其他': -0.04,
        },
        '套利策略': {
            '可转债套利': -0.04,
            '其他': -0.02,
        },
        '债券策略': {
            '纯债基金': -0.02,
            '二级债基': -0.03,
            '可转债多头': -0.08,
        },
    },
}

########################################################################
# 私募管理人持仓规模上限，仅针对协会规模为'0-5亿元'，'5-10亿元'，'10-20亿元'的管理人
########################################################################
hf_company_total_holding_limit_mapping = {
    '0-5亿元': 3e7,
    '5-10亿元': 9e7,
    '10-20亿元': 2e8
}

#################################################
# 私募估值表持仓风险监控会计科目
#################################################
valuation_sheet_risk_scan_subject_monitor_config = {
    # 会计科目3198 衍生工具-场外期权/会计科目3199 衍生工具-场外收益互换/会计科目3102.91其他衍生工具 收益互换
    '场外衍生品': {'subject_ids': ['3198', '3199', '310291'], 'col_name': '场外衍生品'},
    # 会计科目1108.02 其他交易性金融资产投资 场外私募产品
    '私募嵌套': {'subject_ids': ['110802'], 'col_name': '其他资管产品'},
    # 会计代码1103 交易性债券投资/以公允价值计量且其变动计入当期损益的债券投资
    '债券投资': {'subject_ids': ['1103'], 'col_name': '债券'},
    # 会计科目1102.70 新三板股权
    '新三板投资': {'subject_ids': ['110270'], 'col_name': '新三板'},
    # 投资北交所的产品 会计科目1102.G/F/J... 代码较多 暂使用'1102'+外部使用科目名称含有'北交所'再筛选一次
    '北交所投资': {'subject_ids': ['1102'], 'col_name': '北交所'}
}


#################################################
# FOF私享账户通用基准
#################################################

fof_sx_benchmark = {
    '进取型': '中证800*80%+中信证券境内商品动量指数2.0*20%',
    '积极型': '中证800*60%+中信证券境内商品动量指数2.0*30%+中长期纯债型基金指数*10%',
    '平衡型': '中证800*30%+中信证券境内商品动量指数2.0*25%+中长期纯债型基金指数*45%',
    '稳健型': '中证800*10%+中信证券境内商品动量指数2.0*10%+中长期纯债型基金指数*80%',
    '保守型': '中长期纯债型基金指数*100%',
    '纯债型': '中长期纯债型基金指数*100%',
}

#################################################
# 私募量化产品超额收益拆分汇总表，不同策略对应基准配置
#################################################
excess_analysis_bm_map = {
    '300指增': {
        'return_bm': 'HS300',
        'holding_bm': 'HS300'
    },
    '500指增': {
        'return_bm': 'ZZ500',
        'holding_bm': 'ZZ500'
    },
    '1000指增': {
        'return_bm': 'ZZ1000',
        'holding_bm': 'ZZ1000'
    },
    '300对冲': {
        'return_bm': 'ZERO_BM',
        'holding_bm': 'HS300'
    },
    '500对冲': {
        'return_bm': 'ZERO_BM',
        'holding_bm': 'ZZ500'
    },
}


#############################################################################
# 企业微信机器人发送持仓私募基金收益情况跟踪，给类别产品特殊配置
# 字段说明
#  {'主观多头':                   # 产品标签
#  {'level_1': ['主观权益'],      # 一级产品标签
#   'level_2': None,             # 二级产品标签
#   'benchmark_id': '885001.WI', # 此类别产品对应的基准
#   'excess_return': True,      # 是否计算超额收益
#   'addtional_row': 'BASIS' # 产品收益表额外需要包含的行，目前含 None, BM，BASIS。
#   }}                           # None表示不需要额外增加行，BM表示新增基准指数收益，BASIS代表增加股指期货基差贡献
#############################################################################
hf_return_monitor_config = {
    '主观多头': {
        'level_1': ['主观权益'],
        'level_2': None,
        'benchmark_id': '885001.WI',
        'excess_return': True,
        'addtional_row': 'BM'},
    '量化对冲': {
        'level_1': ['量化对冲'],
        'level_2': None,
        'benchmark_id': None,
        'excess_return': False,
        'addtional_row': 'BASIS'},
    '套利策略': {
        'level_1': ['套利策略'],
        'level_2': None,
        'benchmark_id': None,
        'excess_return': False,
        'addtional_row': None},
    '期货策略': {
        'level_1': ['期货策略'],
        'level_2': None,
        'benchmark_id': 'CAMO2.WI',
        'excess_return': False,
        'addtional_row': 'BM'},
    '债券策略': {
        'level_1': ['债券策略'],
        'level_2': None,
        'benchmark_id': '885008.CUSTOMIZED',
        'excess_return': False,
        'addtional_row': 'BM'},
    '可转债多头': {
        'level_1': ['可转债多头'],
        'level_2': None,
        'benchmark_id': None,
        'excess_return': False,
        'addtional_row': None},
    '300指增': {
        'level_1': None,
        'level_2': ['300指增'],
        'benchmark_id': '000300.SH',
        'excess_return': True,
        'addtional_row': 'BM'},
    '500指增': {
        'level_1': None,
        'level_2': ['500指增'],
        'benchmark_id': '000905.SH',
        'excess_return': True,
        'addtional_row': 'BM'},
    '800指增': {
        'level_1': None,
        'level_2': ['800指增'],
        'benchmark_id': '000906.SH',
        'excess_return': True,
        'addtional_row': 'BM'},
    '1000指增及量化选股': {
        'level_1': None,
        'level_2': ['1000指增', '量化选股'],
        'benchmark_id': '000852.SH',
        'excess_return': True,
        'addtional_row': 'BM'},
}

#######################################################
# 私募管理人深度报告模板 单一量化/多头产品分析默认基准
#######################################################
hf_company_report_product_spec_anls_benchmark_config = {
    '量化': {
        'label_level': 'label_level_2',
        'benchmark': {
            "300指增": {'return_benchmark': 'HS300', 'holding_benchmark': 'HS300', 'return_benchmark_id': '000300.SH', 'holding_benchmark_id': '000300.SH'},
            "500指增": {'return_benchmark': 'ZZ500', 'holding_benchmark': 'ZZ500', 'return_benchmark_id': '000905.SH', 'holding_benchmark_id': '000905.SH'},
            "800指增": {'return_benchmark': 'ZZ800', 'holding_benchmark': 'ZZ800', 'return_benchmark_id': '000906.SH', 'holding_benchmark_id': '000906.SH'},
            "1000指增": {'return_benchmark': 'ZZ1000', 'holding_benchmark': 'ZZ1000', 'return_benchmark_id': '000852.SH', 'holding_benchmark_id': '000852.SH'},
            "量化选股": {'return_benchmark': 'ZZ1000', 'holding_benchmark': 'ZZ1000', 'return_benchmark_id': '000852.SH', 'holding_benchmark_id': '000852.SH'},
            "市场中性": {'return_benchmark': 'ZERO_BM', 'holding_benchmark': 'ZZ500', 'return_benchmark_id': 'ZERO_BM', 'holding_benchmark_id': '000905.SH'},
            "量化多空": {'return_benchmark': 'ZERO_BM', 'holding_benchmark': 'ZERO_BM', 'return_benchmark_id': 'ZERO_BM', 'holding_benchmark_id': 'ZERO_BM'},
            "DMA": {'return_benchmark': 'ZERO_BM', 'holding_benchmark': 'ZERO_BM', 'return_benchmark_id': 'ZERO_BM', 'holding_benchmark_id': 'ZERO_BM'},
            "指数增强+CTA": {'return_benchmark': 'ZZ500', 'holding_benchmark': 'ZZ500', 'return_benchmark_id': '000905.SH', 'holding_benchmark_id': '000905.SH'},
            "市场中性+CTA": {'return_benchmark': 'ZERO_BM', 'holding_benchmark': 'ZZ500', 'return_benchmark_id': 'ZERO_BM', 'holding_benchmark_id': '000905.SH'},
            "人工T0": {'return_benchmark': 'ZERO_BM', 'holding_benchmark': 'ZERO_BM', 'return_benchmark_id': 'ZERO_BM', 'holding_benchmark_id': 'ZERO_BM'},
            "量化T0": {'return_benchmark': 'ZERO_BM', 'holding_benchmark': 'ZERO_BM', 'return_benchmark_id': 'ZERO_BM', 'holding_benchmark_id': 'ZERO_BM'}
        },
    },
    '主观多头': {
        'label_level': 'label_level_1',
        'benchmark': {
            "主观权益": {'return_benchmark': 'ZZ800', 'holding_benchmark': 'ZZ800', 'return_benchmark_id': '000906.SH', 'holding_benchmark_id': '000906.SH'}
        }
    },
    'CTA': {
        'label_level': 'label_level_1',
        'benchmark': {
            "期货策略": {'return_benchmark': 'CAMO2.WI', 'holding_benchmark': 'CAMO2.WI', 'return_benchmark_id': 'CAMO2.WI',
                     'holding_benchmark_id': 'CAMO2.WI'}
        }
    },
}

#############################################################################
# wind基金指数成份缓存任务，所需存入的指数，每月1号执行
#############################################################################
wind_index_component_cache_config = {
    '885000.WI': '万得普通股票型基金指数',
    '885001.WI': '万得偏股混合型基金指数',
    '885005.WI': '万得债券型基金指数',
    '885007.WI': '万得混合债券型二级基金指数',
    '885008.WI': '万得中长期纯债型基金指数',
}

#####################################################################
# FOF组合投委会基准成分: 根据ID获取基准成分的指数名称以及所属的大类资产类别
# 只保留三个大类：权益 CTA 绝对收益
#####################################################################
FOF_investment_commitee_bm_info = {
    '000905.SH': {'bm_name': '中证500', 'allocation_type': '权益', 'bm_mapping_id': '000906.SH'},
    '000906.SH': {'bm_name': '中证800', 'allocation_type': '权益', 'bm_mapping_id': '000906.SH'},
    '885001.WI': {'bm_name': '万得偏股混合型基金指数', 'allocation_type': '权益', 'bm_mapping_id': '000906.SH'},
    '885007.WI': {'bm_name': '万得混合债券型二级指数', 'allocation_type': '绝对收益', 'bm_mapping_id': '885008.WI'},
    '885008.WI': {'bm_name': '万得中长期纯债型基金指数', 'allocation_type': '绝对收益', 'bm_mapping_id': '885008.WI'},
    '885009.WI': {'bm_name': '万得货币市场基金指数', 'allocation_type': '绝对收益', 'bm_mapping_id': '885008.WI'},
    'CAMO2.WI': {'bm_name': '中信证券商品动量2.0', 'allocation_type': 'CTA', 'bm_mapping_id': 'CAMO2.WI'},
    'CBA00103.CS': {'bm_name': '中债-新综合全价(总值)指数', 'allocation_type': '绝对收益', 'bm_mapping_id': '885008.WI'},
    'FIX_RATE': {'bm_name': '固定收益率', 'allocation_type': '绝对收益', 'bm_mapping_id': '885008.WI'},
    'ZYYXCTAB': {'bm_name': '朝阳永续管理期货宽基指数', 'allocation_type': 'CTA', 'bm_mapping_id': 'CAMO2.WI'},
    'ZYYXEMNB': {'bm_name': '朝阳永续股票市场中性宽基指数', 'allocation_type': '绝对收益', 'bm_mapping_id': '885008.WI'},
}

#####################################################################
# 策略对应研究员列表: 根据策略获取对应的研究员列表
#####################################################################
strategy_researcher = {
    '主观权益': ['王锐', '李梦嘉', '杨宁'],
    '300指增': ['陈朔', '王南浩'],
    '500指增': ['陈朔', '王南浩'],
    '1000指增': ['陈朔', '王南浩'],
    '市场中性': ['陈朔', '王南浩'],
    '低波动CTA': ['曾旻睿', '饶嘉懿', '陈紫恒'],
    '中波动CTA': ['曾旻睿', '饶嘉懿', '陈紫恒'],
    '高波动CTA': ['曾旻睿', '饶嘉懿', '陈紫恒'],
    '套利策略': ['饶嘉懿', '陈紫恒']
}

######################
# 策略研究员Email信息
######################
strategy_researcher_email_info = {
    '陈朔': 'chenshuo@citics.com',
    '王南浩': 'wangnanhao@citics.com',
    '曾旻睿': 'zengminrui@citics.com',
    '饶嘉懿': 'raojiayi@citics.com',
    '陈紫恒': 'chenziheng@citics.com',
    '王锐': 'rui_wang@citics.com',
    '李梦嘉': 'limengjia@citics.com',
    '杨宁': 'yangning@citics.com',
    '徐君维': 'xujunwei@citics.com'
}

#################################
# 信盈跟踪误差三级标签及其对应阈值配置
#################################
xinying_tracking_error_level3_label_threshold_map = {
    '纯债型': 0.0,
    '保守型': 0.0,
    '稳健型': 0.0,
    '平衡型': 0.0,
    '积极型': 0.0,
    '进取型': 0.0
}

#############################
# styler常用的cmap配色标准
#############################
# sns.diverging_palette传入参数, (h_neg, h_pos)定义对比色, s-饱和度, l-亮度, n-色阶数
# 定义红绿cmap(数值大->红 数值小->绿)
cmap_kwargs = {'h_neg': 150, 'h_pos': 10, 's': 1000, 'l': 20, 'n': 50, 'as_cmap': True}
# 定义绿红cmap(数值小->红 数值大->绿) 多用于波动率等指标
vol_cmap_kwargs = {'h_neg': 10, 'h_pos': 150, 's': 1000, 'l': 20, 'n': 50, 'as_cmap': True}
# 色域压缩参数, 用于定义df.styler.background_gradient中的high和low两个参数, 数值越大表示压缩程度越大(颜色越浅), 官方推荐取值[0, 1]
cmap_range_adjust_coef = 0.8

#############################
# CTA因子收益率计算截面多空阈值
#############################
CTA_factor_long_short_threshold = {
    'high_threshold': 80,
    'low_threshold': 20,
}


#####################################################################
# 发送给私募管理人的邮件催发估值表、监控材料等信息
#####################################################################
mail_send_to_hf_manager = {
    '磐松': {
        'send_to': ['ivywang@pinestoneasset.com'],
        'subject': '【磐松】中信证券+见正文+amfof@citics.com',
        'carbon_copy_to': ['amfof@citics.com'],
        'text': "您好！\n\n麻烦提供磐松信享沪深300指数增强1号，磐松沪深300指数增强2号，磐松多空对冲5号，磐松多空对冲7号的可提供的最新日期的四级估值表，设置托管邮箱发送至amfof@citics.com。",
    },
    '衍复': {
        'send_to': ['operation@yanfuinvestments.com', 'yanfuhegui@yanfuinvestments.com'],
        'subject': '【衍复中性三号】中信证券+见正文+amfof@citics.com',
        'carbon_copy_to': ['amfof@citics.com'],
        'text': "您好！\n\n麻烦提供由托管盖章的上个月不持有下述资产的说明函，发送至amfof@citics.com。内容如下：\n\n "
                "本产品目前不持有，且在中信证券资产管理有限公司管理的资产管理计划持有本产品份额期间也不会投资除公募基金以外的其他资产管理产品，不会投资商业银行理财产品，"
                "不会投资基础资产为信托受益权及其他被视为一层嵌套的资产支持证券，不会投资资产支持票据和/或标准化票据。不会投资债券(可转换债券除外)和场外衍生品。\n\n",
    },
}

#####################################################################
# 月度私募推荐，推荐策略收益贡献部分，各个策略对应基准信息
#####################################################################
hf_recommended_strategy_benchmark_map = \
{
    '主观权益': '000906.SH',
    '300指增': '000300.SH',
    '500指增': '000905.SH',
    '1000指增': '000852.SH',
    '市场中性': '885008.WI',
    '低波动CTA': 'CAMO2.WI',
    '中波动CTA': 'CAMO2.WI',
    '高波动CTA': 'CAMO2.WI',
    '套利策略': '885008.WI'
}

#####################################################################
# 公募行业主题基准库模拟组合id映射
#####################################################################
mf_mock_port_industry_benchmark_pool_map = {
    '金融地产基准库': 'MP000042',
    '科技基准库': 'MP000044',
    '消费基准库': 'MP000041',
    '新能源基准库': 'MP000040',
    '周期基准库': 'MP000042',
    '医药基准库': 'MP000045',
}
