import pandas as pd
import datetime

class _const:
    class ConstError(TypeError):
        pass
    class ConstCaseError(ConstError):
        pass
    def __init__(self):
        pass
    def __setattr__(self, key, value):
        if key in self.__dict__:
            raise self.ConstError("Can't change const.%s" % key)
        if not key.isupper():
            raise self.ConstCaseError("const name %s is not all uppercase" % key)
        self.__dict__[key] = value
const = _const()

# Define a constant as follows:
const.PI = 3.14
# 检查数据误差的阈值
const.EPSILON = 0.0001
const.SCRIPT_TIME_EPSILON = 1  # 脚本进程的创建时间误差阈值，单位(秒)

const.ANNUAL_SCALE = 250
const.WEEK_SCALE = 52
const.FREQ_INTERVAL = {
    'D': 1,
    'W': 7,
}

# 全局设置 组合、策略使用的 SI起始日期
const.SI_START_DATE = datetime.date(2000, 1, 1)
# 全局设置 市场观察-基准指数使用的 SI起始日期
const.BM_SI_START_DATE = datetime.date(2019, 1, 1)
# 全局设置 市场观察-COMMINGLE序列和标准组合使用的 SI起始日期
const.COMMINGLE_SI_START_DATE = datetime.date(2023, 1, 1)

# ------------------------------------------------------
# wind相关常数
# ------------------------------------------------------
const.INDUSTRYTOSECTOR_CITICSFOF = {
        '石油石化'              : '周期产业',
        '煤炭'                 : '周期产业',
        '有色金属'              : '周期产业',
        '钢铁'                 : '周期产业',
        '基础化工'              : '周期产业',
        '机械'                 : '制造产业',
        '电力设备及新能源'        : '制造产业',
        '电力设备与新能源'        : '制造产业',
        '国防军工'              : '制造产业',
        '汽车'                  : '制造产业',
        '家电'                  : '制造产业',
        '医药'                  : '医疗健康产业',
        '轻工制造'               : '消费产业',
        '商贸零售'               : '消费产业',
        '消费者服务'             : '消费产业',
        '纺织服装'              : '消费产业',
        '食品饮料'              : '消费产业',
        '农林牧渔'              : '消费产业',
        '美股'                  : '美股',
        '电子'                  : '科技产业',
        '通信'                  : '科技产业',
        '计算机'                : '科技产业',
        '传媒'                  : '科技产业',
        '银行'                  : '金融产业',
        '非银行金融'             : '金融产业',
        '综合金融'               : '金融产业',
        '电力及公用事业'          : '基础设施与地产产业',
        '建筑'                  : '基础设施与地产产业',
        '建材'                  : '基础设施与地产产业',
        '房地产'                 : '基础设施与地产产业',
        '交通运输'               : '基础设施与地产产业',
        '港股'                  : '港股',
        '综合'                  : '综合'
}

const.EQUITY_MF_WIND_SECTOR_CODE_MAP = {
    '2001010101000000': '普通股票型基金',
    '2001010102000000': '被动指数型基金',
    '2001010103000000': '增强指数型基金',
    '2001010201000000': '偏股混合型基金',
    '2001010202000000': '平衡混合型基金',
    '2001010204000000': '灵活配置型基金',
    '2001010801010000': '国际(QDII)普通股票型基金',
    '2001010801020000': '国际(QDII)被动指数型股票基金',
    '2001010801030000': '国际(QDII)增强指数型股票基金',
    '2001010802010000': '国际(QDII)偏股混合型基金',
    '2001010802020000': '国际(QDII)平衡混合型基金',
    '2001010802040000': '国际(QDII)灵活配置型基金',
    '2001010901000000': '股票型FOF基金',
    '2001010902010000': '偏股混合型FOF基金',
    '2001010902020000': '平衡混合型FOF基金',
}

const.WIND_SECTOR_CODE_MAP = {
    '2001010101000000': '普通股票型基金',
    '2001010102000000': '被动指数型基金',
    '2001010103000000': '增强指数型基金',
    '2001010201000000': '偏股混合型基金',
    '2001010202000000': '平衡混合型基金',
    '2001010203000000': '偏债混合型基金',
    '2001010204000000': '灵活配置型基金',
    '2001010301000000': '中长期纯债型基金',
    '2001010302000000': '短期纯债型基金',
    '2001010303000000': '混合债券型一级基金',
    '2001010304000000': '混合债券型二级基金',
    '2001010305000000': '被动指数型债券基金',
    '2001010306000000': '增强指数型债券基金',
    '2001010400000000': '货币市场型基金',
    '2001010601000000': '股票多空',
    '2001010605000000': 'REITs',
    '2001010607000000': '商品型基金',
    '2001010700000000': 'REITs基金',
    '2001010801010000': '国际(QDII)普通股票型基金',
    '2001010801020000': '国际(QDII)被动指数型股票基金',
    '2001010801030000': '国际(QDII)增强指数型股票基金',
    '2001010802010000': '国际(QDII)偏股混合型基金',
    '2001010802020000': '国际(QDII)平衡混合型基金',
    '2001010802030000': '国际(QDII)偏债混合型基金',
    '2001010802040000': '国际(QDII)灵活配置型基金',
    '2001010803010000': '国际(QDII)普通债券型基金',
    '2001010804010000': '国际(QDII)股票多空',
    '2001010804030000': '国际(QDII)宏观策略',
    '2001010804050000': '国际(QDII)REITs',
    '2001010804060000': '国际(QDII)其他另类投资基金',
    '2001010901000000': '股票型FOF基金',
    '2001010902010000': '偏股混合型FOF基金',
    '2001010902020000': '平衡混合型FOF基金',
    '2001010902030000': '偏债混合型FOF基金',
    '2001010902040000': '目标日期型FOF基金',
    '2001010903000000': '债券型FOF基金',
}
# --------------------------------------
# Wind ETF投资范围分类(ChinaETFInvestClass)
# --------------------------------------
const.WIND_ETF_INVEST_TYPE_LEVEL_1_SECTOR_CODE_MAP = {
    '1000032560000000': '货币型ETF',
    '1000009717000000': '跨境ETF',
    '1000010087000000': '商品型ETF',
    '1000009166000000': '债券型ETF',
    '1000009165000000': '股票型ETF',
}

const.WIND_ETF_INVEST_TYPE_LEVEL_2_SECTOR_CODE_MAP = {
    '1000032560000000': '货币型ETF',
    '1000009717000000': '跨境ETF',
    '1000010087000000': '商品型ETF',
    '1000009166000000': '债券型ETF',
    '1000009713000000': '行业指数ETF',
    '1000009715000000': '风格指数ETF',
    '1000009714000000': '策略指数ETF',
    '1000009716000000': '主题指数ETF',
    '1000009712000000': '规模指数ETF',
}

const.WIND_STATS_MAP = {
    # trailing return
    'f_avgreturn_day': '当天收益率',
    'f_avgreturn_thisweek': '本周收益率', 'f_avgreturn_thismonth': '本月收益率', 'f_avgreturn_thisquarter': '本季收益率',
    'f_avgreturn_week': '一周收益率',     'f_avgreturn_month': '一个月收益率',    'f_avgreturn_quarter': '一个季度收益率',
    'f_avgreturn_halfyear': '半年收益率', 'f_avgreturn_thisyear': '今年收益率',
    'f_avgreturn_year': '一年收益率',     'f_avgreturn_twoyea': '两年收益率',     'f_avgreturn_threeyear': '三年收益率',
    'f_avgreturn_fouryear': '四年收益率',  'f_avgreturn_fiveyear': '五年收益率',  'f_avgreturn_sixyear': '六年收益率',
    'f_avgreturn_sincefound': '成立以来收益率',
    # peer return and product ranking
    'f_sfreturn_recentweek': '最近一周同类基金收益率',     'f_sfreturn_recentmonth': '最近一月同类基金收益率',
    'f_sfrank_recentweek': '最近一周同类排名',            'f_sfrank_recentmonth': '最近一月同类排名',
    'f_sfreturn_thisyear': '今年以来同类基金收益率',       'f_sfreturn_recentquarter': '最近三个月同类基金收益率',
    'f_sfrank_thisyear': '今年以来同类排名',              'f_sfrank_recentquarter': '最近三月同类排名',
    'f_sfreturn_recenthalfyear': '最近半年同类基金收益率', 'f_sfreturn_recentyear': '最近一年同类基金收益率',
    'f_sfrank_recenthalfyear': '最近半年同类排名',        'f_sfrank_recentyear': '最近一年同类排名',
    'f_sfreturn_recenttwoyear': '最近两年同类基金收益率',  'f_sfreturn_recentthreeyear': '最近三年同类基金收益率',
    'f_sfrank_recenttwoyear': '最近两年同类排名',         'f_sfrank_recentthreeyear': '最近三年同类排名',
    'f_sfreturn_recentfiveyear': '最近五年同类基金收益率', 'f_sfreturn_sincefound': '成立以来同类基金收益率',
    'f_sfrank_recentfiveyear': '最近五年同类排名',        'f_sfrank_sincefound': '成立以来同类排名',
    # Std
    'f_stdarddev_halfyear': '半年标准差',    'f_stdarddev_year': '一年标准差',    'f_stdarddev_twoyear': '两年标准差',
    'f_stdarddev_threeyear': '三年标准差',   'f_stdarddev_fiveyear': '五年标准差', 'f_stdarddev_sincefound': '成立以来标准差',
    'f_stdarddev_onemonth': '一个月标准差',   'f_stdarddev_recentquartert': '一个季度标准差', 'f_stdarddev_thisyear': '今年以来标准差',
    # Sharp Ratio
    'f_sharpratio_halfyear': '半年夏普',    'f_sharpratio_year': '一年夏普',
    'f_sharpratio_twoyear': '两年夏普',     'f_sharpratio_threeyear': '三年夏普',
    'f_sharpratio_sincefound': '成立以来夏普', 'f_sharpratio_onemonth': '一个月夏普',
    'f_sharpratio_recentquartert': '一个季度夏普', 'f_sharpratio_thisyear': '今年以来夏普',
    # beta
    'f_beta_6m': '半年beta',  'f_beta_1y': '一年beta',  'f_beta_2y': '两年beta',  'f_beta_3y': '三年beta',
    'beta_onemonth': '一个月beta', 'beta_recentquartert': '一个季度beta', 'beta_thisyear': '今年以来beta', 'beta_sincefound':'成立以来beta',
    # alpha
    'f_alpha_6m': '半年alpha', 'f_alpha_1y': '一年alpha', 'f_alpha_2y': '两年alpha', 'f_alpha_3y': '三年alpha',
    'alpha_onemonth': '一个月alpha', 'alpha_recentquartert': '一个季度alpha', 'alpha_thisyear': '今年以来alpha', 'alpha_sincefound': '成立以来alpha',
    # max drawdown
    'f_maxdownside_quarter': '一个季度最大回撤',    'f_maxdownside_halfyear': '半年最大回撤',     'f_maxdownside_year': '一年最大回撤',
    'f_maxdownside_twoyear': '两年最大回撤',       'f_maxdownside_threeyear': '三年最大回撤',    'f_maxdownside_thisyeart': '今年以来最大回撤',
    'f_maxdownside_sincefound': '成立以来最大回撤', 'f_maxdownside_thisweek': '近一周最大回撤',    'f_maxdownside_thismonth': '近一月最大回撤',
    # information ratio
    'f_inforatio_thisweek': '近一周信息比率', 'f_inforatio_thismonth': '近一月信息比率', 'f_inforatio_quarter': '近一季度信息比率',
    'f_inforatio_halfyear': '近半年信息比率', 'f_inforatio_year': '近一年信息比率',   'f_inforatio_twoyear': '近两年信息比率',
    'f_inforatio_threeyear': '近三年信息比率', 'f_inforatio_fiveyear': '近五年信息比率', 'f_inforatio_thisyeart': '今年以来信息比率',
    'f_inforatio_sincefound': '成立以来信息比率',
}

# --------------------------------------------------------
# WIND公募基金收益统计通用指标，对应wind ChinaMFPerformance的字段
# --------------------------------------------------------
const.WIND_MF_PERF_COMMON_STATS = ['f_avgreturn_day', 'f_sfrank_dayt', 'f_avgreturn_week', 'f_sfrank_recentweekt', 'f_avgreturn_month',
                                   'f_sfrank_recentmontht', 'f_avgreturn_quarter', 'f_sfrank_recentquartert', 'f_avgreturn_year',
                                   'f_sfrank_recentyeart', 'f_avgreturn_thisyear', 'f_sfrank_thisyeart']

# ------------------------------------------------------
# 朝阳永续相关常数
# ------------------------------------------------------
const.ZYYX_STATS_MAP = {
    #short term
    'week_return' : '本周收益',       'month_return' : '本月收益',           'quarter_return' : '本季收益',       'year_return' : '今年收益',
    'month_stdev_a':'本月年化波动率',  'quarter_stdev_a' : '本季年化波动率',    'year_stdev_a' : '今年年化波动率',    'total_stdev_a': '成立以来年化波动率',
    'month_sharp' : '本月夏普值',    'quarter_sharp' : '本季夏普值',          'year_sharp' : '今年夏普值',          'total_sharp': '成立以来夏普值',
    'month_max_retracement' : '本月最大回撤',    'quarter_max_retracement' : '本季度最大回撤',    'year_max_retracement' : '今年以来最大回撤', 'total_max_retracement': '成立以来最大回撤',
    'month_jensen' : '本月詹森指数',             'quarter_jensen' : '本季詹森指数',               'year_jensen' : '今年以来詹森指数',
    'month_sor' : '本月索提诺比率',               'quarter_sor' : '本季索提诺比率',                'year_sor' : '今年以来索提诺比率',
    'month_tre' : '本月特雷诺比率',               'quarter_tre' : '本季特雷诺比率',                'year_tre' : '今年以来特雷诺比率',
    'month_info_ratio' : '本月信息比率',         'quarter_info_ratio' : '本季信息比率',           'year_info_ratio' : '今年以来信息比率',
    #long term
    'y1_return_a' : '近1年年化收益',            'y2_return_a': '近2年年化收益',             'y3_return_a':'近3年年化收益',           'y5_return_a' :'近5年年化收益',
    'y1_max_retracement' : '近1年最大回撤',     'y2_max_retracement' : '近2年最大回撤',     'y3_max_retracement' :'近3年最大回撤',   'y5_max_retracement' : '近5年最大回撤',
    'y1_sharp' : '近1年夏普值',                 'y2_sharp' : '近2年夏普值',                 'y3_sharp' : '近3年夏普值',             'y5_sharp' : '近5年夏普值',
    'y1_calmar' : '近1年卡玛比率',              'y2_calmar' : '近2年卡玛比率',              'y3_calmar' : '近3年卡玛比率',          'y5_calmar' : '近5年卡玛比率',
    'y1_jensen' : '近1年詹森指数',              'y2_jensen' : '近2年詹森指数',              'y3_jensen' : '近3年詹森指数',          'y5_jensen' : '近5年詹森指数',
    'y1_sor' : '近1年索提诺比率',                'y2_sor' : '近2年索提诺比率',               'y3_sor' : '近3年索提诺比率',           'y5_sor' : '近5年索提诺比率',
    'y1_tre' : '近1年特雷诺比率',                'y2_tre' : '近2年特雷诺比率',               'y3_tre' : '近3年特雷诺比率',           'y5_tre' : '近5年特雷诺比率',
    'y1_info_ratio' : '近1年信息比率',          'y2_info_ratio' :'近2年信息比率',           'y3_info_ratio' : '近3年信息比率',       'y5_info_ratio' : '近5年信息比率',
    'y1_stdev_a': '近一年年化波动率',            'y2_stdev_a': '近两年年化波动率',            'y3_stdev_a': '近三年年化波动率',         'm6_stdev_a': '近六月年化波动率'
}

const.ZYYX_AUM_RNAGE_MAP = {
    '6.0' : '0-5亿', '7.0' : '5-10亿', '2.0' : '10-20亿',
    '3.0' : '20-50亿','4.0' : '50-100亿', '5.0' : '100亿以上'
}
const.ZYYX_CUSTOMIZED_STATS_MAP={
    'period_return': '区间收益',
     'annualized_period_return': '区间年化收益',
     'annualized_volatility': '区间年化波动率',
     'max_drawdown': '区间最大回撤',
     'sharpe_ratio': '区间夏普率',
     'calmar': '区间卡玛率'
}
# ------------------------------------------------------
# Universe相关分析
# ------------------------------------------------------
const.ZYYX_UNIV_PERF_DISTRIBUTION = [0.1, 0.25, 0.33, 0.4, 0.5, 0.6, 0.67, 0.75, 0.9]
const.ZYYX_UNIV_ROLLING_PLOT = [0.1, 0.25, 0.5, 0.75, 0.9]
const.WIND_UNIV_PERF_DISTRIBUTION = [0, 0.25, 0.33, 0.4, 0.5, 0.6, 0.67, 0.75, 1]
const.WIND_UNIV_ROLLING_PLOT = [0, 0.25, 0.5, 0.75, 1]

# ------------------------------------------------------
# CTA相关分析
# ------------------------------------------------------
# WIND商品大类板块指数
const.FUTURES_IND_DICT = {'商品指数': 'CCFI.WI', '贵金属': 'NMFI.WI', '有色金属': 'NFFI.WI', '煤焦钢矿': 'JJRI.WI',
                          '能源': 'ENFI.WI', '化工': 'CIFI.WI', '谷物': 'CRFI.WI', '油脂油料': 'OOFI.WI',
                          '软商品': 'SOFI.WI', '农副产品': 'APFI.WI', '非金属建材': 'NMBM.WI'}
# WIND商品品种指数-手动剔除低流动性品种，新上市品种根据成交量可在此添加
const.FUTURES_DICT = {'沪银指数':'AGFI.WI', '沪铝指数':'ALFI.WI', '苹果指数':'APLFI.WI', '沪金指数':'AUFI.WI',
                      '沥青指数':'BUFI.WI', '郑棉指数':'CFFI.WI', '玉米指数':'CFI.WI', '甲醇指数':'MAFI.WI',
                      '淀粉指数':'CSFI.WI', '沪铜指数':'CUFI.WI', '玻璃指数':'FGFI.WI', '纸浆指数':'SPFI.WI',
                      '燃油指数':'FUFI.WI', '热卷指数':'HCFI.WI', '铁矿指数':'IFI.WI', '塑料指数':'LFI.WI',
                      '豆粕指数':'MFI.WI', '沪镍指数':'NIFI.WI', '菜油指数':'OIFI.WI', '棕榈指数':'PFI.WI',
                      'PP指数':'PPFI.WI', '螺纹指数':'RBFI.WI', '乙二醇指数':'EGFI.WI', '菜粕指数':'RMFI.WI',
                      '沪胶指数':'RUFI.WI', '原油指数':'SCFI.WI', '硅铁指数':'SFFI.WI', '沪锡指数':'SNFI.WI',
                      '郑糖指数':'SRFI.WI', 'TA指数':'TAFI.WI', 'PVC指数':'VFI.WI', '豆油指数':'YFI.WI',
                      '沪锌指数':'ZNFI.WI', '不锈钢指数':'SSFI.WI', '尿素指数':'URFI.WI', '纯碱指数':'SAFI.WI'}
# 主观划分商品板块
const.BLACK_IND_DICT = {'螺纹钢':'RB.SHF', '铁矿石':'I.DCE', '热轧卷板':'HC.SHF',
                        '硅铁':'SF.CZC', '玻璃':'FG.CZC', '纯碱':'SA.CZC', '不锈钢':'SS.SHF'}
const.CHEMISTRY_IND_DICT = {'原油':'SC.INE', '天然沥青':'BU.SHF', '纸浆':'SP.SHF', '甲醇':'MA.CZC', 'PTA':'TA.CZC',
                            '塑料':'L.DCE', 'PVC':'V.DCE', '聚丙烯':'PP.DCE', 'MEG':'EG.DCE', '橡胶':'RU.SHF',
                            '尿素':'UR.CZC', '燃料油':'FU.SHF'}
const.AGRICULTURE_IND_DICT = {'玉米':'C.DCE', '淀粉':'CS.DCE', '棉花':'CF.CZC', '白糖':'SR.CZC', '苹果':'AP.CZC'}
const.AGRIOIL_IND_DICT = {'豆粕':'M.DCE', '豆油':'Y.DCE', '棕榈油':'P.DCE', '菜油':'OI.CZC', '菜粕':'RM.CZC'}
const.COLOR_IND_DICT = {'铜':'CU.SHF', '铝':'AL.SHF', '锌':'ZN.SHF', '镍':'NI.SHF', '锡':'SN.SHF'}
const.GOLD_IND_DICT = {'黄金':'AU.SHF', '白银':'AG.SHF'}
const.REGROUP_IND_DICT = {'黑色建材':const.BLACK_IND_DICT, '能源化工':const.CHEMISTRY_IND_DICT,
                          '农产品':const.AGRICULTURE_IND_DICT, '油脂油料':const.AGRIOIL_IND_DICT,
                          '有色金属':const.COLOR_IND_DICT, '贵金属':const.GOLD_IND_DICT}
# 托管商品板块中英文对照
const.FUTURES_IND_NAME_CN_TO_EN = {
    'n_mtgk'            :'煤焦钢矿',
    'n_ys'              :'有色',
    'n_ny'              :'能源',
    'n_yzyl'            :'油脂油料',
    'n_gjs'             :'贵金属',
    'n_hg'              :'化工',
    'n_rsp'             :'软商品',
    'n_nfcp'            :'农副产品',
    'n_fjsjc'           :'非金属建材',
    'n_gw'              :'谷物',
    'n_stock_future'    :'股指期货',
    'n_bond_future'     :'国债期货',
    'n_commodity_future':'商品期货'
}

# ------------------------------------------------------
# barra 因子分类
# ------------------------------------------------------
const.BARRA_STYLE_FACTOR = ['BETA', 'BTOP', 'EARNYILD', 'GROWTH', 'LEVERAGE', 'LIQUIDTY', 'MOMENTUM', 'RESVOL', 'SIZE', 'SIZENL']
const.BARRA_INDUSTRY_FACTOR = ["ENERGY", "CHEM", "CONMAT", "MTLMIN", "MATERIAL", "AERODEF", "BLDPROD", "CNSTENG", "ELECEQP",
                               "INDCONG", "MACH", "TRDDIST", "COMSERV", "AIRLINE", "MARINE", "RDRLTRAN", "AUTO", "HOUSEDUR",
                               "LEISLUX", "CONSSERV", "MEDIA", "RETAIL", "PERSPRD", "BEV", "FOODPROD", "HEALTH", "BANKS", "DVFININS",
                               "REALEST", "SOFTWARE", "HDWRSEMI", "UTILITIE"]
const.BARRA_COUNTRY_FACTOR = ["COUNTRY"]
const.BARRA_STYLE_FUNDAMENTAL_FACTOR = ['SIZE', 'EARNYILD', 'GROWTH', 'BTOP', 'LEVERAGE', 'SIZENL']
const.BARRA_STYLE_TECHNICAL_FACTOR = ['BETA', 'MOMENTUM', 'RESVOL', 'LIQUIDTY']

# ------------------------------------------------------
# 恒生一级行业代码
# ------------------------------------------------------
const.HSHK_INDUSTRY_CODE_LEVEL_1 = {
    'HSCIUT.HI': '公用事业_港股',
    'HSCICO.HI': '综合企业_港股',
    'HSCITC.HI': '电讯业_港股',
    'HSCIFN.HI': '金融业_港股',
    'HSCIPC.HI': '地产建筑业_港股',
    'HSCICD.HI': '非必需性消费_港股',
    'HSCIH.HI': '医疗保健业_港股',
    'HSCIMT.HI': '原材料业_港股',
    'HSCIIT.HI': '资讯科技业_港股',
    'HSCIEN.HI': '能源业_港股',
    'HSCIIN.HI': '工业_港股',
    'HSCICS.HI': '必需性消费_港股'
}
# ------------------------------------------------------
# 中信一级行业代码
# ------------------------------------------------------
const.CITICS_INDUSTRY_CODE_LEVEL_1 = {
    'CI005001.WI':'石油石化',
    'CI005002.WI':'煤炭',
    'CI005003.WI':'有色金属',
    'CI005004.WI':'电力及公用事业',
    'CI005005.WI':'钢铁',
    'CI005006.WI':'基础化工',
    'CI005007.WI':'建筑',
    'CI005008.WI':'建材',
    'CI005009.WI':'轻工制造',
    'CI005010.WI':'机械',
    'CI005011.WI':'电力设备及新能源',
    'CI005012.WI':'国防军工',
    'CI005013.WI':'汽车',
    'CI005014.WI':'商贸零售',
    'CI005015.WI':'消费者服务',
    'CI005016.WI':'家电',
    'CI005017.WI':'纺织服装',
    'CI005018.WI':'医药',
    'CI005019.WI':'食品饮料',
    'CI005020.WI':'农林牧渔',
    'CI005021.WI':'银行',
    'CI005022.WI':'非银行金融',
    'CI005023.WI':'房地产',
    'CI005024.WI':'交通运输',
    'CI005025.WI':'电子',
    'CI005026.WI':'通信',
    'CI005027.WI':'计算机',
    'CI005028.WI':'传媒',
    'CI005029.WI':'综合',
    'CI005030.WI':'综合金融'
}

# ------------------------------------------------------
# 申万一级行业代码
# ------------------------------------------------------
const.SW_INDUSTRY_CODE_LEVEL_1 = {
    '801010.SI':'农林牧渔',
    '801030.SI':'基础化工',
    '801040.SI':'钢铁',
    '801050.SI':'有色金属',
    '801080.SI':'电子',
    '801110.SI':'家用电器',
    '801120.SI':'食品饮料',
    '801130.SI':'纺织服饰',
    '801140.SI':'轻工制造',
    '801150.SI':'医药生物',
    '801160.SI':'公用事业',
    '801170.SI':'交通运输',
    '801180.SI':'房地产',
    '801200.SI':'商贸零售',
    '801210.SI':'社会服务',
    '801230.SI':'综合',
    '801710.SI':'建筑材料',
    '801720.SI':'建筑装饰',
    '801730.SI':'电力设备',
    '801740.SI':'国防军工',
    '801750.SI':'计算机',
    '801760.SI':'传媒',
    '801770.SI':'通信',
    '801780.SI':'银行',
    '801790.SI':'非银金融',
    '801880.SI':'汽车',
    '801890.SI':'机械设备',
    '801950.SI':'煤炭',
    '801960.SI':'石油石化',
    '801970.SI':'环保',
    '801980.SI':'美容护理'
}

# ------------------------------------------------------
# 申万一级行业中英文对照
# ------------------------------------------------------
const.SW_INDUSTRY_NAME_CN_TO_EN = {
    '钢铁': 'steel',
    '煤炭': 'coal',
    '有色金属': 'nonferrousmetals',
    '石油石化': 'petroleumpetrochemical',
    '基础化工': 'basicchemicals',
    '建筑材料': 'buildingmaterials',
    '交通运输': 'transportation',
    '建筑装饰': 'constructiondecoration',
    '电力设备': 'electricalequipment',
    '机械设备': 'capitalequipment',
    '国防军工': 'defence',
    '环保': 'environmentalprotection',
    '公用事业': 'utilities',
    '农林牧渔': 'agriculture',
    '食品饮料': 'foodbeverage',
    '医药生物': 'pharmaceuticalsbiotech',
    '商贸零售': 'commerceretailng',
    '社会服务': 'socialservices',
    '汽车': 'automobiles',
    '家用电器': 'homeappliances',
    '纺织服饰': 'textilesapparel',
    '轻工制造': 'lightindustry',
    '美容护理': 'beautycare',
    '电子': 'electronics',
    '计算机': 'computer',
    '传媒': 'media',
    '通信': 'communications',
    '房地产': 'realestate',
    '银行': 'banks',
    '非银金融': 'nonbankingfinancials',
    '综合': 'conglomerates'
}

# ------------------------------------------------------
# 港股行业中英文对照
# ------------------------------------------------------
const.HK_INDUSTRY_NAME_CN_TO_EN = {
    '公用事业_港股': 'ggsy',
    '综合企业_港股': 'zhqy',
    '电讯业_港股': 'dxy',
    '消费服务业_港股': 'xffw',
    '金融业_港股': 'jry',
    '地产建筑业_港股': 'dcjzy',
    '非必需性消费_港股': 'fbyxf',
    '医疗保健业_港股': 'ylbj',
    '原材料业_港股': 'ycly',
    '资讯科技业_港股': 'zxkj',
    '能源业_港股': 'nyy',
    '消费品制造业_港股': 'xfpzzy',
    '其他_港股': 'other_hk',
    '工业_港股': 'gy',
    '必需性消费_港股': 'bxxxf'
}

# ------------------------------------------------------
# 大小盘价值成长风格中英文对照
# ------------------------------------------------------
const.STYLE_NAME_CN_TO_EN = {
    '大盘成长': 'dpcz',
    '大盘价值': 'dpjz',
    '大盘平衡': 'dpph',
    '中盘成长': 'zpcz',
    '中盘价值': 'zpjz',
    '中盘平衡': 'zpph',
    '小盘成长': 'xpcz',
    '小盘价值': 'jpjz',
    '小盘平衡': 'xpph',
    '其他风格': 'qtqt'
}

# ------------------------------------------------------
# 申万一级行业代码对应风格分类，数据来源：申万研究所
# ------------------------------------------------------
const.SW_INDUSTRY_CODE_LEVEL_1_STYLE = {
    '801010.SI':'消费',
    '801030.SI':'周期',
    '801040.SI':'周期',
    '801050.SI':'周期',
    '801080.SI':'TMT',
    '801110.SI':'消费',
    '801120.SI':'消费',
    '801130.SI':'消费',
    '801140.SI':'周期',
    '801150.SI':'消费',
    '801160.SI':'稳定',
    '801170.SI':'周期',
    '801180.SI':'金融',
    '801200.SI':'消费',
    '801210.SI':'消费',
    '801230.SI':'综合',
    '801710.SI':'周期',
    '801720.SI':'周期',
    '801730.SI':'中游制造',
    '801740.SI':'中游制造',
    '801750.SI':'TMT',
    '801760.SI':'TMT',
    '801770.SI':'TMT',
    '801780.SI':'金融',
    '801790.SI':'金融',
    '801880.SI':'消费',
    '801890.SI':'中游制造',
    '801950.SI':'周期',
    '801960.SI':'周期',
    '801970.SI':'稳定',
    '801980.SI':'消费'
}

# ------------------------------------------------------
# 大类资产分类
# ------------------------------------------------------
const.ASSET_DICT={'Equity':['偏股公募'], 'Commodity':['管理期货'], 'Macro':['宏观策略'],
                  'Bond':['纯债基金'], 'Arbitrage': ['套利策略'], 'Hedge':['股票市场中性']}


# ------------------------------------------------------
# 申万二级行业代码及中文
# ------------------------------------------------------
const.SW_INDUSTRY_CODE_LEVEL_2 = {
    '801011.SI': '林业Ⅱ(申万)',
    '801012.SI': '农产品加工(申万)',
    '801014.SI': '饲料(申万)',
    '801015.SI': '渔业(申万)',
    '801016.SI': '种植业(申万)',
    '801017.SI': '养殖业(申万)',
    '801018.SI': '动物保健Ⅱ(申万)',
    '801032.SI': '化学纤维(申万)',
    '801033.SI': '化学原料(申万)',
    '801034.SI': '化学制品(申万)',
    '801036.SI': '塑料(申万)',
    '801037.SI': '橡胶(申万)',
    '801038.SI': '农化制品(申万)',
    '801039.SI': '非金属材料Ⅱ(申万)',
    '801043.SI': '冶钢原料(申万)',
    '801044.SI': '普钢(申万)',
    '801045.SI': '特钢Ⅱ(申万)',
    '801051.SI': '金属新材料(申万)',
    '801053.SI': '贵金属(申万)',
    '801054.SI': '小金属(申万)',
    '801055.SI': '工业金属(申万)',
    '801056.SI': '能源金属(申万)',
    '801072.SI': '通用设备(申万)',
    '801074.SI': '专用设备(申万)',
    '801076.SI': '轨交设备Ⅱ(申万)',
    '801077.SI': '工程机械(申万)',
    '801078.SI': '自动化设备(申万)',
    '801081.SI': '半导体(申万)',
    '801082.SI': '其他电子Ⅱ(申万)',
    '801083.SI': '元件(申万)',
    '801084.SI': '光学光电子(申万)',
    '801085.SI': '消费电子(申万)',
    '801086.SI': '电子化学品Ⅱ(申万)',
    '801092.SI': '汽车服务(申万)',
    '801093.SI': '汽车零部件(申万)',
    '801095.SI': '乘用车(申万)',
    '801096.SI': '商用车(申万)',
    '801101.SI': '计算机设备(申万)',
    '801102.SI': '通信设备(申万)',
    '801103.SI': 'IT服务Ⅱ(申万)',
    '801104.SI': '软件开发(申万)',
    '801111.SI': '白色家电(申万)',
    '801112.SI': '黑色家电(申万)',
    '801113.SI': '小家电(申万)',
    '801114.SI': '厨卫电器(申万)',
    '801115.SI': '照明设备Ⅱ(申万)',
    '801116.SI': '家电零部件Ⅱ(申万)',
    '801124.SI': '食品加工(申万)',
    '801125.SI': '白酒Ⅱ(申万)',
    '801126.SI': '非白酒(申万)',
    '801127.SI': '饮料乳品(申万)',
    '801128.SI': '休闲食品(申万)',
    '801129.SI': '调味发酵品Ⅱ(申万)',
    '801131.SI': '纺织制造(申万)',
    '801132.SI': '服装家纺(申万)',
    '801133.SI': '饰品(申万)',
    '801141.SI': '包装印刷(申万)',
    '801142.SI': '家居用品(申万)',
    '801143.SI': '造纸(申万)',
    '801145.SI': '文娱用品(申万)',
    '801151.SI': '化学制药(申万)',
    '801152.SI': '生物制品(申万)',
    '801153.SI': '医疗器械(申万)',
    '801154.SI': '医药商业(申万)',
    '801155.SI': '中药Ⅱ(申万)',
    '801156.SI': '医疗服务(申万)',
    '801161.SI': '电力(申万)',
    '801163.SI': '燃气Ⅱ(申万)',
    '801178.SI': '物流(申万)',
    '801179.SI': '铁路公路(申万)',
    '801181.SI': '房地产开发(申万)',
    '801183.SI': '房地产服务(申万)',
    '801191.SI': '多元金融(申万)',
    '801193.SI': '证券Ⅱ(申万)',
    '801194.SI': '保险Ⅱ(申万)',
    '801202.SI': '贸易Ⅱ(申万)',
    '801203.SI': '一般零售(申万)',
    '801204.SI': '专业连锁Ⅱ(申万)',
    '801206.SI': '互联网电商(申万)',
    '801218.SI': '专业服务(申万)',
    '801219.SI': '酒店餐饮(申万)',
    '801223.SI': '通信服务(申万)',
    '801231.SI': '综合Ⅱ(申万)',
    '801711.SI': '水泥(申万)',
    '801712.SI': '玻璃玻纤(申万)',
    '801713.SI': '装修建材(申万)',
    '801721.SI': '房屋建设Ⅱ(申万)',
    '801722.SI': '装修装饰Ⅱ(申万)',
    '801723.SI': '基础建设(申万)',
    '801724.SI': '专业工程(申万)',
    '801726.SI': '工程咨询服务Ⅱ(申万)',
    '801731.SI': '电机Ⅱ(申万)',
    '801733.SI': '其他电源设备Ⅱ(申万)',
    '801735.SI': '光伏设备(申万)',
    '801736.SI': '风电设备(申万)',
    '801737.SI': '电池(申万)',
    '801738.SI': '电网设备(申万)',
    '801741.SI': '航天装备Ⅱ(申万)',
    '801742.SI': '航空装备Ⅱ(申万)',
    '801743.SI': '地面兵装Ⅱ(申万)',
    '801744.SI': '航海装备Ⅱ(申万)',
    '801745.SI': '军工电子Ⅱ(申万)',
    '801764.SI': '游戏Ⅱ(申万)',
    '801765.SI': '广告营销(申万)',
    '801766.SI': '影视院线(申万)',
    '801767.SI': '数字媒体(申万)',
    '801769.SI': '出版(申万)',
    '801782.SI': '国有大型银行Ⅱ(申万)',
    '801783.SI': '股份制银行Ⅱ(申万)',
    '801784.SI': '城商行Ⅱ(申万)',
    '801785.SI': '农商行Ⅱ(申万)',
    '801881.SI': '摩托车及其他(申万)',
    '801951.SI': '煤炭开采(申万)',
    '801952.SI': '焦炭Ⅱ(申万)',
    '801962.SI': '油服工程(申万)',
    '801963.SI': '炼化及贸易(申万)',
    '801971.SI': '环境治理(申万)',
    '801972.SI': '环保设备Ⅱ(申万)',
    '801981.SI': '个护用品(申万)',
    '801982.SI': '化妆品(申万)',
    '801991.SI': '航空机场(申万)',
    '801992.SI': '航运港口(申万)',
    '801993.SI': '旅游及景区(申万)',
    '801994.SI': '教育(申万)',
    '801995.SI': '电视广播Ⅱ(申万)'
}

const.ZXZQ_EQUITY_FOF = ['ZXA009.OF']
const.ZXZQ_FI_FOF = ['J909944.OF', 'J90995S.OF', 'J90997A.OF', 'J90997Z.OF']
const.HF_STATUS = ['在库已投', '在库未投', '跟踪', '其他', '出库']
const.AMDATA_DB_TO_THIRD_PARTY_DB_MAP = {
    '主观权益': '股票多头',
    '500指增': '500指数增强',
    '300指增': '300指数增强',
    '1000指增': '1000指数增强',
    '市场中性': '股票市场中性',
    '低波动CTA': '低波动管理期货',
    '中波动CTA': '中波动管理期货',
    '高波动CTA': '高波动管理期货',
    '股票多头': '股票多头',
    '套利策略': '套利策略',
    '价值': '股票多头',
    '平衡': '股票多头',
    '轮动': '股票多头'
}
const.INDEX_NAME_TO_CODE_MAP = {
    'ZZ500'  : '000905.SH',
    'HS300'  : '000300.SH',
    'ZZ1000' : '000852.SH',
    'ZZ800'  : '000906.SH'
}

# ------------------------------------------------------
# 基本分析相关数据
# ------------------------------------------------------
const.PERF_STATS_PERIOD = ['YTD', 'Recent_1W', 'Recent_1M', 'Recent_3M', 'Recent_1Y', 'YTLDLM', 'Today', '2024', '2023', '2022', '2021', '2020', '2019', '2018', '2017', 'SI', 'Customized']


# ------------------------------------------------------
# 网页版相关数据
# ------------------------------------------------------
const.WEB_SECTOR_TYPE_LIST = {
    '大类配置类型': 'allocation_type',
    '一级标签': 'label_level_1',
    '二级标签': 'label_level_2',
    '产品类型': 'product_type',
}

# ------------------------------------------------------
# 大类资产列表 - 自建体系
# ------------------------------------------------------
const.ALLOCATION_TYPE_LIST = ['权益', 'CTA', '绝对收益', '复合策略', '货币基金', 'Reits', '其他']

# ------------------------------------------------------
# 比较基准与指数
# ------------------------------------------------------
const.WEB_BENCHMARK_LIST = {
    'None': None,
    '沪深300': '000300.SH',
    '沪深300全收益': 'h00300.CSI',
    '中证500': '000905.SH',
    '中证500全收益': 'h00905.CSI',
    '中证800': '000906.SH',
    '中证800全收益': 'h00906.CSI',
    '中证1000': '000852.SH',
    '中证1000全收益': 'h00852.SH',
    '中证A500': '000510.SH',
    '中证A500全收益': '000510CNY010.CSI',
    '偏股混基金指数': '885001.WI',
    '混合债券二级基金指数': '885007.WI',
    '中长期纯债基金指数': '885008.WI',
    '中证商品期货指数': '100001.CCI',
    '中信证券商品动量2.0': 'CAMO2.WI',
    '万得小市值指数': '8841425.WI',
    '万得微盘股指数': '8841431.WI',
}

const.CUSTOMIZED_BENCHMARK_LIST = {
    '定制-中长期纯债型基金指数': '885008.CUSTOMIZED',
    '定制-CTA管理人指数': 'CTA_MANAGER_INDEX_01.CUSTOMIZED'
}

# ---------------------------------------------------------------------------
# 自定义比较基准的权重配置，以DataFrame的形式储存各成份的权重
# 用于 FOF市场观察 比较基准分析 回测分析等
# [配置序列的中文名，成份ID，成份权重，成份数据源]
# ---------------------------------------------------------------------------
const.COMMINGLE_COMPONENT_CONFIG = pd.DataFrame([

    ['信盈稳健基准', '000906.SH', 0.1, 'wind'],
    ['信盈稳健基准', 'CAMO2.WI', 0.05, 'wind'],
    ['信盈稳健基准', '885008.WI', 0.85, 'wind'],

    ['信盈平衡基准', '000906.SH', 0.3, 'wind'],
    ['信盈平衡基准', 'CAMO2.WI', 0.2, 'wind'],
    ['信盈平衡基准', '885008.WI', 0.5, 'wind'],

    ['信盈积极基准', '000906.SH', 0.6, 'wind'],
    ['信盈积极基准', 'CAMO2.WI', 0.3, 'wind'],
    ['信盈积极基准', '885008.WI', 0.1, 'wind'],

], columns=['series_name', 'component_id', 'component_weight', 'component_data_source'])

# ---------------------------------------------------------------------------
# 标准组合名称列表
# 目前支持4个标准组合
# ---------------------------------------------------------------------------
const.STANDARD_PORT_NAME_LIST = ['稳健型-标准组合', '平衡型-标准组合', '积极型-标准组合', '进取型-标准组合']

# ---------------------------------------------------------------------------
# 标准组合ID列表
# 目前支持4个标准组合
# ---------------------------------------------------------------------------
const.STANDARD_PORT_ID_LIST = ['STANDARD_PORT_WENJIAN_1', 'STANDARD_PORT_PINGHENG_1', 'STANDARD_PORT_JIJI_1', 'STANDARD_PORT_JINQU_1']

# ---------------------------------------------------------------------------
# 标准组合所对应基准的字典
# 目前支持4个标准组合
# ---------------------------------------------------------------------------
const.STANDARD_PORT_BM_NAME_DICT = {
    '稳健型-标准组合': '中证800*10%+中信证券境内商品动量指数2.0*10%+中长期纯债型基金指数*80%',
    '平衡型-标准组合': '中证800*30%+中信证券境内商品动量指数2.0*25%+中长期纯债型基金指数*45%',
    '积极型-标准组合': '中证800*60%+中信证券境内商品动量指数2.0*30%+中长期纯债型基金指数*10%',
    '进取型-标准组合': '中证800*80%+中信证券境内商品动量指数2.0*20%',
}

# ---------------------------------------------------------------------------
# 标准组合的权重配置，以DataFrame的形式储存各成份的权重
# 展示于 FOF组合持仓分析和收益分析，作为参考
# [标准组合ID，标准组合的中文名，成份ID，成份产品名，成份权重，成份数据源，成分back_up_index，成分back_up_index数据源，对应bm_index，对应bm数据源]
# 上述backup是指补足产品历史缺失数据所用的指数，bm是指该产品所属大类对应到bm所用的指数，这两个指数可能会不同
# ---------------------------------------------------------------------------
const.STANDARD_PORT_COMPONENT_CONFIG = pd.DataFrame([

    ['STANDARD_PORT_WENJIAN_1', '稳健型-标准组合', '稳健型-标准组合', '9099G7.OF', '中信丰泽300指数增强1号', 0.07, 'amdata', '000300.SH', 'wind', '000906.SH', 'wind'],
    ['STANDARD_PORT_WENJIAN_1', '稳健型-标准组合', '稳健型-标准组合', 'IC.CFE', '中证500股指期货主连', 0.03, 'wind', '000905.SH', 'wind', '000906.SH', 'wind'],
    ['STANDARD_PORT_WENJIAN_1', '稳健型-标准组合', '稳健型-标准组合', '90993X.OF', '中信证券丰收信益2号', 0.20, 'amdata', '885008.WI', 'wind', '885008.WI', 'wind'],
    ['STANDARD_PORT_WENJIAN_1', '稳健型-标准组合', '稳健型-标准组合', '9099K1.OF', '中信证券星云126号', 0.20, 'amdata', '885008.WI', 'wind', '885008.WI', 'wind'],
    ['STANDARD_PORT_WENJIAN_1', '稳健型-标准组合', '稳健型-标准组合', '909433.OF', '中信证券贵宾丰元18号', 0.20, 'amdata', '885008.WI', 'wind', '885008.WI', 'wind'],
    ['STANDARD_PORT_WENJIAN_1', '稳健型-标准组合', '稳健型-标准组合', '909827.OF', '中信证券贵宾丰元56号', 0.20, 'amdata', '885008.WI', 'wind', '885008.WI', 'wind'],
    ['STANDARD_PORT_WENJIAN_1', '稳健型-标准组合', '稳健型-标准组合', '9099FQ.OF', '中信证券丰泽量化多策略1号', 0.10, 'amdata', 'CAMO2.WI', 'wind', 'CAMO2.WI', 'wind'],

    ['STANDARD_PORT_PINGHENG_1', '平衡型-标准组合', '平衡型-标准组合', '9099G7.OF', '中信丰泽300指数增强1号', 0.20, 'amdata', '000300.SH', 'wind', '000906.SH', 'wind'],
    ['STANDARD_PORT_PINGHENG_1', '平衡型-标准组合', '平衡型-标准组合', 'IC.CFE', '中证500股指期货主连', 0.10, 'wind', '000905.SH', 'wind', '000906.SH', 'wind'],
    ['STANDARD_PORT_PINGHENG_1', '平衡型-标准组合', '平衡型-标准组合', '90993X.OF', '中信证券丰收信益2号', 0.15, 'amdata', '885008.WI', 'wind', '885008.WI', 'wind'],
    ['STANDARD_PORT_PINGHENG_1', '平衡型-标准组合', '平衡型-标准组合', '9099K1.OF', '中信证券星云126号', 0.15, 'amdata', '885008.WI', 'wind', '885008.WI', 'wind'],
    ['STANDARD_PORT_PINGHENG_1', '平衡型-标准组合', '平衡型-标准组合', '909433.OF', '中信证券贵宾丰元18号', 0.15, 'amdata', '885008.WI', 'wind', '885008.WI', 'wind'],
    ['STANDARD_PORT_PINGHENG_1', '平衡型-标准组合', '平衡型-标准组合', '9099FQ.OF', '中信证券丰泽量化多策略1号', 0.25, 'amdata', 'CAMO2.WI', 'wind', 'CAMO2.WI', 'wind'],

    ['STANDARD_PORT_JIJI_1', '积极型-标准组合', '积极型-标准组合', '9099G7.OF', '中信丰泽300指数增强1号', 0.40, 'amdata', '000300.SH', 'wind', '000906.SH', 'wind'],
    ['STANDARD_PORT_JIJI_1', '积极型-标准组合', '积极型-标准组合', 'IC.CFE', '中证500股指期货主连', 0.20, 'wind', '000905.SH', 'wind', '000906.SH', 'wind'],
    ['STANDARD_PORT_JIJI_1', '积极型-标准组合', '积极型-标准组合', '90993X.OF', '中信证券丰收信益2号', 0.10, 'amdata', '885008.WI', 'wind', '885008.WI', 'wind'],
    ['STANDARD_PORT_JIJI_1', '积极型-标准组合', '积极型-标准组合', '9099FQ.OF', '中信证券丰泽量化多策略1号', 0.30, 'amdata', 'CAMO2.WI', 'wind', 'CAMO2.WI', 'wind'],

    ['STANDARD_PORT_JINQU_1', '进取型-标准组合', '进取型-标准组合', '9099G7.OF', '中信丰泽300指数增强1号', 0.55, 'amdata', '000300.SH', 'wind', '000906.SH', 'wind'],
    ['STANDARD_PORT_JINQU_1', '进取型-标准组合', '进取型-标准组合', 'IC.CFE', '中证500股指期货主连', 0.25, 'wind', '000905.SH', 'wind', '000906.SH', 'wind'],
    ['STANDARD_PORT_JINQU_1', '进取型-标准组合', '进取型-标准组合', '9099FQ.OF', '中信证券丰泽量化多策略1号', 0.20, 'amdata', 'CAMO2.WI', 'wind', 'CAMO2.WI', 'wind'],

], columns=['standard_port_id', 'standard_port_name', 'series_name', 'component_id', 'component_name', 'component_weight', 'component_data_source',
            'back_up_index_id', 'back_up_index_data_source', 'bm_index_id', 'bm_index_data_source'])

# ------------------------------------------------------
# 私享投资经理名单
# ------------------------------------------------------
const.SIXIANG_PM_LIST = ['曾旻睿', '陈朔', '汪崇阳', '闫若凡', '杨宁', '王南浩', '饶嘉懿']

# ------------------------------------------------------
# FOF投资经理名单
# ------------------------------------------------------
const.FOF_PM_LIST = ['曾旻睿', '陈朔', '汪崇阳', '闫若凡', '杨宁', '王南浩', '饶嘉懿', '张泂', '王锐', '许智华', '徐鹏', '魏星']

# ------------------------------------------------------
# FOF产品线的四级分类标签中英文对照
# ------------------------------------------------------
const.FOF_PRODUCT_TYPE = {
    '一级分类': 'level_1_type',
    '二级分类': 'level_2_type',
    '三级分类': 'level_3_type',
    '管理类型': 'management_type',
}

# ------------------------------------------------------
# 常规的Performance指标选项
# ------------------------------------------------------
const.COMMON_PERF_STATS = ['period_return', 'annualized_period_return', 'annualized_volatility', 'max_drawdown', 'sharpe_ratio', 'calmar']

# ------------------------------------------------------
# 拓展的Performance指标选项
# ------------------------------------------------------
const.EXTEND_PERF_STATS = ['current_drawdown']

# ------------------------------------------------------
# 股指期货连续合约，主力合约代码
# ------------------------------------------------------
const.STOCK_INDEX_FUTURES_CODE = [
    "IH.CFE",
    "IH_S.CFE",
    "IH00.CFE",
    "IH01.CFE",
    "IH02.CFE",
    "IH03.CFE",
    "IC.CFE",
    "IC_S.CFE",
    "IC00.CFE",
    "IC01.CFE",
    "IC02.CFE",
    "IC03.CFE",
    "IF.CFE",
    "IF_S.CFE",
    "IF00.CFE",
    "IF01.CFE",
    "IF02.CFE",
    "IF03.CFE",
    "IM.CFE",
    "IM_S.CFE",
    "IM00.CFE",
    "IM01.CFE",
    "IM02.CFE",
    "IM03.CFE"
]

# ------------------------------------------------------
# 股指期货合约对应指数代码/名称
# ------------------------------------------------------
const.STOCK_INDEX_FUTURES_BM_MAP = {
    'IH': {'index_id': '000016.SH', 'index_name': '上证50'},
    'IF': {'index_id': '000300.SH', 'index_name': '沪深300'},
    'IC': {'index_id': '000905.SH', 'index_name': '中证500'},
    'IM': {'index_id': '000852.SH', 'index_name': '中证1000'},
}

#####################################################################
# CTA因子计算配置
# 选中进行因子计算与因子收益计算的品种
#####################################################################
const.SELECTED_FUTURES_LIST = ['JM', 'I', 'V', 'PP', 'CS',
                      'P', 'Y', 'OI', 'A', 'B', 'C',
                      'M', 'SF', 'SM', 'MA', 'TA',
                      'FG', 'CF', 'SR', 'RM', 'SC',
                      'LU', 'NR', 'HC', 'RB', 'BU',
                      'RU', 'FU', 'AL', 'CU', 'NI',
                      'ZN', 'SN', 'AG', 'AU']
#####################################################################
# CTA因子计算配置
# 合约类型代码映射
#####################################################################
const.CONTRACT_TYPE = {'主力': '', '次主力': '_S', '连续': '00', '连一': '01', '连二': '02', '连三': '03'}

#####################################################################
# CTA因子计算配置
# 品种对应wind板块映射
#####################################################################
const.FUTURES_SECTOR_DICT = {
    "AL": "有色金属", "CU": "有色金属", "NI": "有色金属", "ZN": "有色金属",
    "SN": "有色金属", "PB": "有色金属", "AO": "有色金属", "P": "油脂油料",
    "Y": "油脂油料", "OI": "油脂油料", "A": "油脂油料", "B": "油脂油料",
    "M": "油脂油料", "RM": "油脂油料", "CF": "软商品", "SR": "软商品",
    "CS": "农副产品", "SC": "能源", "LU": "能源", "FU": "能源",
    "PG": "能源", "JM": "煤焦钢材", "I": "煤焦钢材", "SF": "煤焦钢材",
    "SM": "煤焦钢材", "HC": "煤焦钢材", "RB": "煤焦钢材", "SS": "煤焦钢材",
    "PP": "化工", "MA": "化工", "TA": "化工", "NR": "化工",
    "BU": "化工", "RU": "化工", "L": "化工", "SP": "化工",
    "SA": "化工", "BR": "化工", "EB": "化工", "EG": "化工",
    "PF": "化工", "AG": "贵金属", "AU": "贵金属", "C": "谷物",
    "V": "非金属建材", "FG": "非金属建材"
}
#####################################################################
# 商品期货品种代码对应名称映射
#####################################################################
const.FUTURES_NAME_DICT = {
    "AL": "SHFE铝", "CU": "SHFE铜", "NI": "SHFE镍", "ZN": "SHFE锌",
    "SN": "SHFE锡", "P": "DCE棕榈油", "Y": "DCE豆油", "OI": "CZCE菜油",
    "A": "DCE豆一", "B": "DCE豆二", "M": "DCE豆粕", "RM": "CZCE菜粕",
    "CF": "CZCE棉花", "SR": "CZCE白糖", "CS": "DCE玉米淀粉", "SC": "INE原油",
    "LU": "INE低硫燃料油", "FU": "SHFE燃油", "JM": "DCE焦煤", "I": "DCE铁矿石",
    "SF": "CZCE硅铁", "SM": "CZCE锰硅", "HC": "SHFE热轧卷板", "RB": "SHFE螺纹钢",
    "V": "DCE PVC", "PP": "DCE聚丙烯", "MA": "CZCE甲醇", "TA": "CZCE PTA",
    "NR": "INE20号胶", "BU": "SHFE沥青", "RU": "SHFE橡胶", "AG": "SHFE白银",
    "AU": "SHFE黄金", "C": "DCE玉米", "FG": "CZCE玻璃", "L": "DCE塑料",
    "SP": "SHFE纸浆", "SA": "CZCE纯碱", "BR": "SHFE丁二烯橡胶", "EB": "DCE苯乙烯",
    "PB": "SHFE铅", "PG": "DCE LPG", "SS": "SHFE不锈钢", "EG": "DCE乙二醇",
    "PF": "CZCE短纤", "AO": "SHFE氧化铝"
}

# ------------------------------------------------------
# CTA 因子字典
# ------------------------------------------------------
const.CTA_FACTOR_NAME_DICT = \
{
'momentum_5_series': '5日时序动量',
'momentum_22_series': '22日时序动量',
'momentum_66_series': '66日时序动量',
'momentum_5_cross': '5日截面动量',
'momentum_22_cross': '22日截面动量',
'momentum_66_cross': '66日截面动量',
'basis_momentum_5_cross': '5日基差动量',
'basis_momentum_22_cross': '22日基差动量',
'term_structure_cross': '期限结构',
'warehouse_cross': '库存',
'skew_256_cross': '偏度',
'wave_5_cross': '5日波动率',
'wave_22_cross': '22日波动率',
'fluidity_255_cross': '流动性',
}

# ------------------------------------------------------
# CTA 因子分类字典
# ------------------------------------------------------
const.CTA_FACTOR_TYPE_DICT = {
    'momentum_5_series': '时序动量',
    'momentum_22_series': '时序动量',
    'momentum_66_series': '时序动量',
    'momentum_5_cross': '截面动量',
    'momentum_22_cross': '截面动量',
    'momentum_66_cross': '截面动量',
    'basis_momentum_5_cross': '基差动量',
    'basis_momentum_22_cross': '基差动量',
    'term_structure_cross': '期限结构和基本面',
    'warehouse_cross': '期限结构和基本面',
    'skew_256_cross': '量价',
    'wave_5_cross': '量价',
    'wave_22_cross': '量价',
    'fluidity_255_cross': '量价'
}

#############################
# CTA规模以上指数，年度成分
#############################
const.CTA_MANAGER_INDEX_COMPONENT = pd.DataFrame([
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2018, 'S0000066', 'equal', '英仕曼CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2018, 'S0000113', 'equal', '元盛CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2019, 'S0000066', 'equal', '英仕曼CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2019, 'S0000110', 'equal', '黑翼CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2019, 'S0000113', 'equal', '元盛CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2019, 'S0000093', 'equal', '洛书CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2019, 'S0000097', 'equal', '涵德CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2019, 'S0000242', 'equal', '博普CTA_高杠杆'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2019, 'S0000109', 'equal', '千象CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2019, 'S0001339', 'equal', '远澜_中杠杆CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2020, 'S0000110', 'equal', '黑翼CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2020, 'S0000113', 'equal', '元盛CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2020, 'S0000093', 'equal', '洛书CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2020, 'S0000097', 'equal', '涵德CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2020, 'S0000242', 'equal', '博普CTA_高杠杆'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2020, 'S0000109', 'equal', '千象CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2020, 'S0001339', 'equal', '远澜_中杠杆CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2020, 'S0000064', 'equal', '象限CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2020, 'S0000223', 'equal', '宏锡CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2020, 'S0001099', 'equal', '白鹭CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2020, 'S0000071', 'equal', '呈瑞CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2021, 'S0000110', 'equal', '黑翼CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2021, 'S0000113', 'equal', '元盛CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2021, 'S0000093', 'equal', '洛书CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2021, 'S0000097', 'equal', '涵德CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2021, 'S0000242', 'equal', '博普CTA_高杠杆'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2021, 'S0000109', 'equal', '千象CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2021, 'S0001339', 'equal', '远澜_中杠杆CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2021, 'S0000064', 'equal', '象限CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2021, 'S0000223', 'equal', '宏锡CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2021, 'S0001099', 'equal', '白鹭CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2021, 'S0001528', 'equal', '芷瀚CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2021, 'S0000071', 'equal', '呈瑞CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2022, 'S0000066', 'equal', '英仕曼CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2022, 'S0000110', 'equal', '黑翼CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2022, 'S0000113', 'equal', '元盛CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2022, 'S0000093', 'equal', '洛书CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2022, 'S0000097', 'equal', '涵德CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2022, 'S0000242', 'equal', '博普CTA_高杠杆'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2022, 'S0000109', 'equal', '千象CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2022, 'S0001339', 'equal', '远澜_中杠杆CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2022, 'S0000064', 'equal', '象限CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2022, 'S0000223', 'equal', '宏锡CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2022, 'S0001375', 'equal', '均成CTA_中杠杆'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2022, 'S0001099', 'equal', '白鹭CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2022, 'S0000094', 'equal', '盛冠达CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2022, 'S0001528', 'equal', '芷瀚CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2022, 'S0000065', 'equal', '会世CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2022, 'S0000071', 'equal', '呈瑞CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2023, 'S0000066', 'equal', '英仕曼CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2023, 'S0000110', 'equal', '黑翼CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2023, 'S0000113', 'equal', '元盛CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2023, 'S0000093', 'equal', '洛书CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2023, 'S0000097', 'equal', '涵德CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2023, 'S0000242', 'equal', '博普CTA_高杠杆'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2023, 'S0000109', 'equal', '千象CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2023, 'S0001339', 'equal', '远澜_中杠杆CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2023, 'S0000064', 'equal', '象限CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2023, 'S0000223', 'equal', '宏锡CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2023, 'S0001375', 'equal', '均成CTA_中杠杆'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2023, 'S0001099', 'equal', '白鹭CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2023, 'S0000094', 'equal', '盛冠达CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2023, 'S0001528', 'equal', '芷瀚CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2023, 'S0000065', 'equal', '会世CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2024, 'S0000066', 'equal', '英仕曼CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2024, 'S0000110', 'equal', '黑翼CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2024, 'S0000113', 'equal', '元盛CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2024, 'S0000093', 'equal', '洛书CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2024, 'S0000097', 'equal', '涵德CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2024, 'S0000242', 'equal', '博普CTA_高杠杆'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2024, 'S0000109', 'equal', '千象CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2024, 'S0001339', 'equal', '远澜_中杠杆CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2024, 'S0000064', 'equal', '象限CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2024, 'S0000223', 'equal', '宏锡CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2024, 'S0001375', 'equal', '均成CTA_中杠杆'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2024, 'S0001099', 'equal', '白鹭CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2024, 'S0000094', 'equal', '盛冠达CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2024, 'S0001528', 'equal', '芷瀚CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2024, 'S0000065', 'equal', '会世CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2024, 'S0001705', 'equal', '因诺CTA_低杠杆'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2024, 'S0000930', 'equal', '众壹量化CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2025, 'S0000066', 'equal', '英仕曼CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2025, 'S0000110', 'equal', '黑翼CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2025, 'S0000113', 'equal', '元盛CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2025, 'S0000093', 'equal', '洛书CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2025, 'S0000097', 'equal', '涵德CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2025, 'S0000242', 'equal', '博普CTA_高杠杆'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2025, 'S0000109', 'equal', '千象CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2025, 'S0001339', 'equal', '远澜_中杠杆CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2025, 'S0000064', 'equal', '象限CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2025, 'S0000223', 'equal', '宏锡CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2025, 'S0001375', 'equal', '均成CTA_中杠杆'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2025, 'S0001099', 'equal', '白鹭CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2025, 'S0000094', 'equal', '盛冠达CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2025, 'S0001528', 'equal', '芷瀚CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2025, 'S0000065', 'equal', '会世CTA'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2025, 'S0001705', 'equal', '因诺CTA_低杠杆'],
     ['CTA_MANAGER_INDEX_01.CUSTOMIZED', 2025, 'S0000930', 'equal', '众壹量化CTA']
], columns=['customized_index_id', 'year', 'strategy_id', 'weight_type', 'strategy_name'])