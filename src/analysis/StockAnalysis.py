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
        stock_ids = None     # stock_ids股票代码，应为list格式，为None时，相当于获取全部股票
):
    df = wind.wind_getAShareHolders(stock_ids)
    # 处理报告期日不是交易日的问题
    rpt_date = df[['date']].drop_duplicates().sort_values('date').reset_index(drop=True)
    rpt_date['trade_date'] = wind.wind_getLastTradeDates(rpt_date['date'].to_list())
    df = pd.merge(df, rpt_date, on='date', how='left')
    # 获取季末的股票价格，如果不选时间，运行时间过长

    stk_price = wind.wind_getAShareStockTradeData(on_dates=rpt_date['trade_date'].to_list())  # stock_ids默认为None, 取全量股票
    stk_price = stk_price[['stock_id', 'stock_name', 'trade_date', 'close']]
    df = pd.merge(df, stk_price, on=['stock_id','trade_date'], how='left')
    df['stk_value'] = df['close'] * df['quantity']
    del df['close'], df['quantity']
    return df
