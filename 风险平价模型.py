import numpy as np
import pandas as pd
from datetime import datetime


def risk_parity_backtest(risk_budgets, start_date, end_date):
    """
    风险平价模型回测函数
    :param risk_budgets: 字典格式，资产代码 -> 风险预算比例 (e.g. {'IC.CFE': 0.125, ...})
    :param start_date: 回测起始日期 (格式: 'YYYY-MM-DD')
    :param end_date: 回测结束日期 (格式: 'YYYY-MM-DD')
    :return: 净值曲线DataFrame，包含日期和组合净值
    """
    # =============================
    # 1. 数据准备 (此处需替换为实际数据接口)
    # =============================
    # 示例：生成模拟价格数据（实际使用时应从数据库/API获取）
    assets = list(risk_budgets.keys())
    dates = pd.date_range(start=start_date, end=end_date)
    np.random.seed(42)

    # 生成模拟价格数据 (7个资产)
    prices = pd.DataFrame(
        np.exp(np.cumsum(np.random.randn(len(dates), len(assets)) * 0.01, axis=0)),
        index=dates, columns=assets
    )

    # =============================
    # 2. 核心回测逻辑
    # =============================
    # 初始化
    daily_returns = prices.pct_change().dropna()
    portfolio_values = pd.Series(1.0, index=daily_returns.index)  # 初始净值为1
    weights = pd.Series(0, index=assets, dtype=float)  # 当前持仓权重

    # 获取所有月末日期
    monthly_dates = prices.resample('M').last().index

    # 遍历每个交易日
    for i, date in enumerate(daily_returns.index):
        # 每月末再平衡
        if date in monthly_dates:
            # 计算近一年波动率 (年化)
            lookback = 252  # 一年交易日
            start_idx = max(0, i - lookback)
            vol_window = daily_returns.iloc[start_idx:i]

            # 处理数据不足的情况
            if len(vol_window) < 20:
                annual_vol = pd.Series(0.15, index=assets)  # 默认波动率15%
            else:
                annual_vol = vol_window.std() * np.sqrt(252)

            # 计算新权重 (风险预算/波动率)
            new_weights = pd.Series(risk_budgets) / annual_vol
            new_weights /= new_weights.sum()  # 归一化

            # 更新权重
            weights = new_weights

        # 计算当日组合收益
        daily_port_return = (weights * daily_returns.loc[date]).sum()

        # 更新净值
        if i > 0:
            prev_value = portfolio_values.iloc[i - 1]
            portfolio_values.loc[date] = prev_value * (1 + daily_port_return)

    # 返回净值曲线
    return pd.DataFrame({'NetValue': portfolio_values})


# =============================
# 3. 参数设置与执行
# =============================
if __name__ == "__main__":
    # 输入参数
    RISK_BUDGETS = {
        'IC.CFE': 0.125,  # A股
        'HSTECH.HI': 0.125,  # H股
        'NDX.GI': 0.25,  # 美股
        'T.CFE': 0.125,  # 国债
        '000832.CSI': 0.125,  # 转债
        'AU.SHF': 0.125,  # 黄金
        'AG.SHF': 0.125  # 白银
    }
    START_DATE = '2015-01-01'
    END_DATE = '2025-8-15'

    # 执行回测
    result = risk_parity_backtest(RISK_BUDGETS, START_DATE, END_DATE)

    # 打印结果
    print("回测净值曲线:")
    print(result.tail())

    # 可选: 绘制净值曲线
    # result.plot(title='Risk Parity Portfolio Performance')



