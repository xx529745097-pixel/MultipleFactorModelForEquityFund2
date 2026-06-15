############################################
# 管理人/策略持仓上限监控 补充监控项 以公司层级维护
# 同时支持公募和私募管理人
############################################
holding_limit_monitor_result_supplements = {'MC000131': '淳厚基金'}

##############################
# 公募核心库收益监控
##############################
# --------------------------------
# 公募核心库收益监控 - 核心库类型config
# --------------------------------
mf_core_pool_config = {
    '权益核心库': {
        'mock_port_id_map': {
            '核心中核心': {'平衡': 'MP000049', '轮动': 'MP000048', '价值': 'MP000047'},
            '行业主题基金': {'金融地产': 'MP000052', '科技': 'MP000055', '消费': 'MP000056', '新能源': 'MP000054', '周期': 'MP000053', '医药': 'MP000050'},
            '智选30推荐': {'CC30': 'MP000069'},
        },
        'benchmark': {'000906.SH': '中证800', '885001.WI': '偏股混合型基金指数', },
        'represent_mock_port': {'核心中核心': 'MP000046', '智选30推荐': 'MP000069', '金融地产': 'MP000052', '科技': 'MP000055', '消费': 'MP000056', '新能源': 'MP000054', '周期': 'MP000053', '医药': 'MP000050'}
    },
    '债券核心库': {
        'mock_port_id_map': {
            '纯债基金': {'纯债': 'MP000059'},
            '固收+基金': {'固收+': 'MP000060'},
        },
        'benchmark': {'885008.WI': '中长期纯债基金指数', '885062.WI': '短期纯债基金指数', '885006.WI': '混合债券型一级基金指数', '885007.WI': '混合债券型二级基金指数'},
        'represent_mock_port': {'纯债基金推荐组合': 'MP000059', '二级债基推荐组合': 'MP000060'}
    },
}

# ------------------------------------------------
# 公募核心库收益监控 - 收益排名指标对应wind收益统计字段和回看天数
# period用于手动计算指数和模拟组合的区间收益指标
# ------------------------------------------------
mf_core_pool_ret_rank_perf_stats = {
    '1D': {'wind_perf_col': 'f_avgreturn_day', 'period': 'Today'},
    'rank_1D': {'wind_perf_col': 'f_sfrank_dayt', 'period': 'Today'},
    '1W': {'wind_perf_col': 'f_avgreturn_week', 'period': 'Recent_1W'},
    'rank_1W': {'wind_perf_col': 'f_sfrank_recentweekt', 'period': 'Recent_1W'},
    '1M': {'wind_perf_col': 'f_avgreturn_month', 'period': 'Recent_1M'},
    'rank_1M': {'wind_perf_col': 'f_sfrank_recentmontht', 'period': 'Recent_1M'},
    '3M': {'wind_perf_col': 'f_avgreturn_quarter', 'period': 'Recent_3M'},
    'rank_3M': {'wind_perf_col': 'f_sfrank_recentquartert', 'period': 'Recent_3M'},
    '1Y': {'wind_perf_col': 'f_avgreturn_year', 'period': 'Recent_1Y'},
    'rank_1Y': {'wind_perf_col': 'f_sfrank_recentyeart', 'period': 'Recent_1Y'},
    'YTD': {'wind_perf_col': 'f_avgreturn_thisyear', 'period': 'YTD'},
    'rank_YTD': {'wind_perf_col': 'f_sfrank_thisyeart', 'period': 'YTD'},
}
