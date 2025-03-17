# ------------------------------------------------
# 本文档用于对收益率序列做指标计算
# ------------------------------------------------
import datetime
import pandas as pd
import numpy as np
import src.data.wind as wind
from src.data.wind import *
from sklearn.linear_model import LinearRegression


# ----------------------------------------
# 组合回测函数
# 根据资产收益和调仓生效日权重计算组合回测收益序列
# 非调仓日期权重会根据资产波动而自动调整归一
# ----------------------------------------
def backtest_calPortfolioReturnSeries(
    ret_df,    # 底层资产收益
    weight_df  # 调仓生效日权重
):
    assert set(ret_df.columns) == set(weight_df.columns), "回测时ret_df和weight_df的columns需要完全一致"
    weight_df = weight_df[ret_df.columns]  # 保证ret_df和weight_df资产排序一致
    weight_df = weight_df.add_suffix('_weight')
    # 合并数据，整合日期index，从第一个调仓权重生效日开始回测
    backtest_df = ret_df.join(weight_df, how='left').loc[weight_df.index.min():, :]  # 默认从第一个调仓生效日期开始回测
    if backtest_df.empty:
        return pd.Series()
    # 填充缺失的资产收益为0，可能存在不同资产交易日不完全对齐的情况
    backtest_df[ret_df.columns] = backtest_df[ret_df.columns].fillna(0)
    # 根据资产收益计算每日权重
    for row_num, (index, row) in enumerate(backtest_df.iterrows()):
        if index in weight_df.index:  # 跳过调仓日期
            continue
        backtest_df.loc[index, weight_df.columns] = backtest_df.iloc[row_num-1][weight_df.columns].to_numpy() * (1 + backtest_df.iloc[row_num-1][ret_df.columns].to_numpy())  # 对应元素相乘
    # 权重之和调整为100%
    backtest_df[weight_df.columns] = backtest_df[weight_df.columns].div(backtest_df[weight_df.columns].sum(axis=1), axis=0)
    port_ret_series = backtest_df.apply(lambda x: (x[weight_df.columns].to_numpy() * x[ret_df.columns].to_numpy()).sum(), axis=1)
    return port_ret_series



# if __name__ == '__main__':
#     ret_df = pd.DataFrame.from_dict({'date': pd.date_range(datetime.date(2024, 1, 1), datetime.date(2024, 2, 1))})
#     ret_df['date'] = ret_df['date'].dt.date
#     back_df = pd.DataFrame.from_dict({'date': [datetime.date(2024, 1, 10), datetime.date(2024, 1, 27)]})
#     back_df['asset_a'] = [0.3, 0.7]
#     back_df['asset_b'] = [0.5, 0.5]
#     ret_df['asset_a'] = np.random.randn(len(ret_df)) / 100
#     ret_df['asset_b'] = np.random.randn(len(ret_df)) / 100
#     ret_df = ret_df.set_index('date')
#     back_df = back_df.set_index('date')
#     backtest_calPortfolioReturnSeries(ret_df, back_df)