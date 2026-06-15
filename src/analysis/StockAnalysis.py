# ------------------------------------------------
# 本文档用于股票数据分析
# ------------------------------------------------
import src.data.wind as wind
import src.utils.Calculation as Cal
import pandas as pd
import datetime
import numpy as np

# ------------------------------------------------------
# 计算A股的股东持股市值
# ------------------------------------------------------
def anlsStk_getAShareHolders(
    start_date,         # datetime.date 起始日期
    end_date,           # datetime.date 截止日期
    stock_ids=None,     # stock_ids股票代码，应为list格式，为None时，相当于获取全部股票
    float_holders=False   # 前十大股东/前十大流通股东，默认为前十大股东
):
    assert isinstance(start_date, datetime.date), "start_date需为datetime.date类型"
    assert isinstance(end_date, datetime.date), "end_date需为datetime.date类型"
    float_holders = wind.wind_getAShareHolders(report_period_start_date=start_date, report_period_end_date=end_date, stock_ids=stock_ids, float_holders=float_holders)
    # 处理报告期日不是交易日的问题
    rpt_dates = float_holders['date'].sort_values().unique().tolist()
    last_trade_dates = wind.wind_getLastTradeDates(rpt_dates)
    last_trade_date_mapping = {k: v for k, v in zip(rpt_dates, last_trade_dates)}
    float_holders['trade_date'] = float_holders['date'].map(last_trade_date_mapping)
    # 获取报告日期前最后一个交易日的股票收盘价格信息
    stk_price = wind.wind_getAShareStockTradeData(on_dates=float_holders['trade_date'].unique().tolist())  # stock_ids默认为None, 取全量股票
    float_holders = pd.merge(float_holders, stk_price[['stock_id', 'stock_name', 'trade_date', 'close']], on=['stock_id', 'trade_date'], how='inner')
    float_holders['stk_value'] = float_holders['close'] * float_holders['quantity']
    del float_holders['close'], float_holders['quantity']
    return float_holders
