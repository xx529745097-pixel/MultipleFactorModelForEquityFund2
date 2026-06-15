# ------------------------------------------------
# 本文档用于对calendar的处理
# ------------------------------------------------
import pandas as pd
import datetime
import src.data.wind as wind
import src.data.custFOF as custFOF
import src.const as const
from dateutil.relativedelta import relativedelta

# ------------------------------------------------
# 返回最后一个交易日，每年/每季度/每月
# ------------------------------------------------
def calendar_getLastDay(
        freq    # 'Y' year, 'Q' quarter, 'M' month
):
    calendar = wind.wind_getSSECalendar()
    calendar = calendar.sort_values(by='date').reset_index(drop=True)
    calendar['date'] = pd.to_datetime(calendar['date'])
    calendar['year'] = calendar['date'].dt.year
    calendar['quarter'] = calendar['date'].dt.quarter
    calendar['month'] = calendar['date'].dt.month
    freq_dict = {
        "Y": ["year"],
        "Q": ["year", "quarter"],
        "M": ["year", "month"]
    }

    calendar = calendar.drop_duplicates(subset=freq_dict[freq], keep='last').reset_index(drop=True)
    calendar['date'] = pd.to_datetime(calendar['date']).dt.date
    calendar = calendar[['date']]
    return calendar

# ------------------------------------------------
# 返回给定日期的上一个周周几
# 如果date本身就是目标星期几，则返回当天
# ------------------------------------------------
def calendar_getLastTargetDay(
    date,  # datetime.date instance
    target_day  # 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'
):
    assert target_day in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'], "weekday需为Monday这种形式（首字母大写）"
    assert isinstance(date, datetime.date), "date must be an instance of datetime.date"
    date_to_idx_map = {
        'Monday': 0,
        'Tuesday': 1,
        'Wednesday': 2,
        'Thursday': 3,
        'Friday': 4,
        'Saturday': 5,
        'Sunday': 6
    }
    day_num = date.weekday()
    day_num_target = date_to_idx_map[target_day]
    days_ago = (7 + day_num - day_num_target) % 7
    target_date = date - datetime.timedelta(days=days_ago)
    return target_date

# ------------------------------------------------
# 返回给定区间内的每周五，返回list
# ------------------------------------------------
def calendar_getFridays(
    startdate,  # datetime.date
    enddate     # datetime.date
):
    TradeCalendar = wind.wind_getSSECalendar()
    TradeCalendar = TradeCalendar[TradeCalendar['date'] >= startdate]
    TradeCalendar = TradeCalendar[TradeCalendar['date'] <= enddate]
    TradeCalendar['date'] = pd.to_datetime(TradeCalendar['date'])
    Fridays = TradeCalendar.resample('W-Fri', on = 'date').last().dropna(axis=0, how='all')
    Fridays['date'] = Fridays['date'].apply(lambda x: x.to_pydatetime().date())
    Fridays = Fridays.reset_index(drop = True)
    return Fridays

# ------------------------------------------------
# 返回给定日期的N个交易日前的日期(T-N)
# ------------------------------------------------
def calendar_getDateNTradeDaysAgo(
    date,  # datetime.date instance
    delta  # N: integer > 0
):
    assert isinstance(date, datetime.date), "date must be an instance of datetime.date"
    TradeCalendar = wind.wind_getSSECalendar()
    TradeCalendar = TradeCalendar[TradeCalendar['date'] <= date]
    return TradeCalendar['date'][len(TradeCalendar)-1-delta]

# ------------------------------------------------------
# 关于date的helper函数
# ------------------------------------------------------
def calender_getStartEndDate(
    period,             # 统计区间
    date=datetime.datetime.today().date(),
    start_date=None,    # This parameter ONLY works for period equal to Customized
):
    assert period in const.const.PERF_STATS_PERIOD, "统计区间暂时不支持"
    if period in ('Today', 'Recent_1W', 'Recent_1M', 'Recent_3M', 'Recent_1Y', 'YTD', 'YTLDLM', '2024', '2023', '2022', '2021', '2020', '2019', '2018', '2017', 'SI'):
        assert start_date is None, "Custom区间需要输入start_date，选定区间请勿输入start_date"

    # 对于Recent_1M(Recent_3M)，date输入为月末时，单独判断，取本月月初(上上月月初)作为start_date
    period_dict = {
        'Today': (date, date),
        'Recent_1W': (date - relativedelta(days=6), date),
        'Recent_1M': (datetime.date(date.year, date.month, 1), date) if (date + relativedelta(days=1)).month != date.month else (date - relativedelta(months=1) + relativedelta(days=1), date),
        'Recent_3M': (datetime.date(date.year, date.month, 1) - relativedelta(months=2), date) if (date + relativedelta(days=1)).month != date.month else (date - relativedelta(months=3) + relativedelta(days=1), date),
        'Recent_1Y': (datetime.date(date.year, date.month, 1) - relativedelta(years=1), date),
        'YTD': (datetime.date(date.year, 1, 1), date),
        # year to last date of last month
        'YTLDLM': (datetime.date(date.year, 1, 1), datetime.date(date.year, date.month, 1) - datetime.timedelta(1)) if date.month != 1 else (datetime.date(date.year - 1, 1, 1), datetime.date(date.year, date.month, 1) - datetime.timedelta(1)),
        '2024': (datetime.date(2024, 1, 1), datetime.date(2024, 12, 31)),
        '2023': (datetime.date(2023, 1, 1), datetime.date(2023, 12, 31)),
        '2022': (datetime.date(2022, 1, 1), datetime.date(2022, 12, 31)),
        '2021': (datetime.date(2021, 1, 1), datetime.date(2021, 12, 31)),
        '2020': (datetime.date(2020, 1, 1), datetime.date(2020, 12, 31)),
        '2019': (datetime.date(2019, 1, 1), datetime.date(2019, 12, 31)),
        '2018': (datetime.date(2018, 1, 1), datetime.date(2018, 12, 31)),
        '2017': (datetime.date(2017, 1, 1), datetime.date(2017, 12, 31)),
        'SI': (const.const.SI_START_DATE, date)
    }
    if period == 'Customized':
        assert start_date is not None, '请输入start date'
        assert start_date <= date, '起始日期请小于截止日期'
        end_date = date
    else:
        assert start_date is None, '请移除start date'
        start_date, end_date = period_dict[period]
    return start_date, end_date

# ------------------------------------------------------
# 日频数据降周频&周频不稳定数据处理的helper函数
# 返回 return降频后的dataframe, columns_to_exclude的列不会输出, 防止降频后生成错误数据
# ------------------------------------------------------
def calender_convertDailyReturnToWeekly(
    ret_df,                 # 收益率dataframe
    date_column_name,       # 日期列名
    return_column_name,     # 收益率列名
    id_column_name,         # ID列名
    columns_to_exclude=[],  # 为防止dataframe中包含不止一列return数据而导致返回数据错误, 可用此参数将不需降频和返回的数据列去除
):
    ret_df = ret_df.drop(columns=columns_to_exclude)
    ret_df[date_column_name] = pd.to_datetime(ret_df[date_column_name])
    # 获取最终日期用于截取降频造成的日期超出部分
    end_date = ret_df[date_column_name].max()
    ret_copy = ret_df.copy()
    if len(ret_copy):
        ret_df[return_column_name] = ret_df[return_column_name] + 1
        ret_df = ret_df.set_index(date_column_name).groupby(id_column_name).resample('W-Fri').agg({return_column_name: 'prod'}).reset_index()
        ret_df[return_column_name] = ret_df[return_column_name] - 1
        ret_copy = ret_copy.set_index(date_column_name).groupby(id_column_name).resample('W-Fri').last()
        del ret_copy[id_column_name], ret_copy[return_column_name]
        ret_copy = ret_copy.reset_index()
    else:
        del ret_copy[return_column_name]
    #########################################################
    # FIXME dropna将除去周频数据的缺失点,将无法通过报错发现数据源异常
    #########################################################
    result = ret_copy.merge(ret_df[[date_column_name, id_column_name, return_column_name]], on=[date_column_name, id_column_name], how='left').dropna()
    # 截取降频造成的日期超出部分
    result = result[result[date_column_name] <= end_date]
    result[date_column_name] = pd.to_datetime(result[date_column_name]).dt.date
    return result

# ---------------------------------------------------------------------------------------------
# 获取投顾账户最近持仓数据日期的helper函数
# 投顾账户持仓数据日频周频不定，只有交易日有数据，在取持仓、计算持仓change的时候需要针对性计算日期，否则取不到数
# 返回 最近的持仓数据日期 datetime格式
# ---------------------------------------------------------------------------------------------
def calender_getAdvisoryAccountHoldingDate(
    date,               # 基准日期，函数寻找该日期前投顾账户具有持仓数据的最近日期
    portfolio_id,       # 投顾账户port_id
):
    holding_date = custFOF.custFOF_getFOFHoldingData(date - datetime.timedelta(22), date, [portfolio_id])['date'].max()
    return holding_date

# ------------------------------------------------------
# 获取定时缓存任务的执行日期、获取缓存数据相关网页展示的日期默认值
# ------------------------------------------------------
def calender_getFOFProperDate(
        mode='web',     # web: 获取网页的日期默认值  cache: 获取定时任务的执行日期
        delta_date=3    # 工作日T-X的计算逻辑，当前支持T-1和T-3
):
    weekday_mapping_cache_1 = {
        # mode=cache delta_date=1
        # key: 周一至周日(0-6) 下同
        0: None,
        1: 1,
        2: 1,
        3: 1,
        4: 1,
        5: 1,
        6: None
    }

    weekday_mapping_cache_3 = {
        # mode=cache delta_date=3
        0: None,
        1: 5,
        2: 5,
        3: 3,
        4: 3,
        5: 3,
        6: None
    }

    weekday_mapping_web_3 = {
        # mode=web delta_date=3
        0: 5,
        1: 5,
        2: 5,
        3: 3,
        4: 3,
        5: 3,
        6: 4,
    }

    web_mapping = {3: weekday_mapping_web_3}
    cache_mapping = {1: weekday_mapping_cache_1, 3: weekday_mapping_cache_3}
    all_mapping = {'web': web_mapping, 'cache': cache_mapping}
    today = datetime.date.today()
    delta_days = all_mapping[mode][delta_date][datetime.date.weekday(today)]
    if delta_days:
        return today - datetime.timedelta(delta_days)
    else:
        return None

# -------------------------------------------------------------------------
# 将给定日期区间拆成分段年度统计区间，返回值为(start_date,end_date)元组的list，日期从近到远
# 对于绩效分析部分，通常搭配'Customized'模式使用
# -------------------------------------------------------------------------
def calender_splitAsAnnualPeriod(
    start_date,     # 起始日期
    end_date        # 截止日期
):
    assert isinstance(start_date, datetime.date), "start_date类型需为datetime.date"
    assert isinstance(end_date, datetime.date), "end_date类型需为datetime.date"
    annual_period_list = []
    for year in range(start_date.year, end_date.year + 1):
        sub_interval_start_date = max(start_date, datetime.date(year, 1, 1))
        sub_interval_end_date = min(end_date, datetime.date(year, 12, 31))
        annual_period_list.append((sub_interval_start_date, sub_interval_end_date))
    return annual_period_list[::-1]
