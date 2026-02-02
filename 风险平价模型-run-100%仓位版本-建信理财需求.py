import numpy as np
import pandas as pd
from datetime import datetime

import numpy as np
import pandas as pd
from datetime import datetime

import datetime
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import os
import src.data.wind as wind
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)  # 仅禁用 FutureWarning
from scipy.optimize import minimize, Bounds, NonlinearConstraint

import time


def robust_risk_budget_optimization(cov_matrix, risk_budget=None, max_iter=100000,
                                    precision=1e-12, min_eig_thresh=1e-10,
                                    verbose=True, method='auto'):
    """
    鲁棒的风险预算组合优化
    :param cov_matrix: 协方差矩阵 (numpy数组)
    :param risk_budget: 风险预算列表
    :param max_iter: 最大迭代次数
    :param precision: 优化精度要求
    :param min_eig_thresh: 最小特征值阈值
    :param verbose: 是否显示详细输出
    :param method: 优化方法 ('auto', 'SLSQP', 'trust-constr')
    :return: (最优权重, 优化结果对象)
    """
    # 忽略特定警告
    warnings.filterwarnings("ignore", category=RuntimeWarning, module="scipy.optimize")

    # 确保输入是numpy数组
    cov_matrix = np.asarray(cov_matrix, dtype=np.float64)
    n = cov_matrix.shape[0]

    # 处理风险预算
    if risk_budget is None:
        risk_budget = np.ones(n) / n
    else:
        risk_budget = np.asarray(risk_budget, dtype=np.float64)

    # 1. 识别需要优化的资产
    valid_idx = risk_budget > 1e-10
    zero_idx = ~valid_idx

    if not np.any(valid_idx):
        return np.zeros(n), None

    # 2. 提取有效资产的协方差子矩阵
    valid_cov = cov_matrix[valid_idx][:, valid_idx].copy()
    valid_budget = risk_budget[valid_idx].copy()

    # 确保协方差矩阵高度正定
    eigenvalues = np.linalg.eigvalsh(valid_cov)
    min_eigenvalue = np.min(eigenvalues)
    if min_eigenvalue < min_eig_thresh:
        regularization = (min_eig_thresh - min_eigenvalue) * np.eye(valid_cov.shape[0])
        valid_cov += regularization
        if verbose:
            print(f"应用正则化: 最小特征值={min_eigenvalue:.2e}, 添加正则化项={min_eig_thresh - min_eigenvalue:.2e}")

    # 归一化有效资产的风险预算
    valid_budget /= valid_budget.sum()
    n_valid = valid_cov.shape[0]

    # 3. 定义目标函数
    def objective(w):
        port_var = w.T @ valid_cov @ w
        port_var_reg = port_var + 1e-30  # 极小正则化防止除零
        marginal_risk = valid_cov @ w
        risk_contrib_ratio = (w * marginal_risk) / port_var_reg
        return np.sum((risk_contrib_ratio - valid_budget) ** 2)

    # 4. 设置约束条件
    constraints = []
    bounds = Bounds(0, 1)  # 权重在0到1之间

    # 权重和为1的约束
    constraints.append(
        NonlinearConstraint(
            fun=lambda w: np.sum(w),
            lb=1.0, ub=1.0
        )
    )

    # 5. 初始点 (使用最小方差组合)
    inv_cov = np.linalg.pinv(valid_cov)
    min_var_w = inv_cov.sum(axis=1) / inv_cov.sum()
    w0 = min_var_w

    # 6. 选择优化方法
    if method == 'auto':
        method = 'trust-constr' if n_valid > 5 else 'SLSQP'

    # 7. 优化求解
    start_time = time.time()

    # 通用选项
    options = {
        'maxiter': max_iter,
        'disp': verbose
    }

    # 方法特定选项
    if method == 'SLSQP':
        method_options = {
            'ftol': precision,
            'eps': 1e-10
        }
    elif method == 'trust-constr':
        method_options = {
            'xtol': precision,
            'gtol': precision,
            'barrier_tol': precision,
            'verbose': 1 if verbose else 0
        }
    else:
        raise ValueError(f"未知优化方法: {method}")

    # 合并选项
    options.update(method_options)

    # 执行优化
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = minimize(
            objective,
            w0,
            method=method,
            bounds=bounds,
            constraints=constraints,
            options=options
        )

    elapsed_time = time.time() - start_time
    if verbose:
        status = "成功" if result.success else f"失败: {result.message}"
        print(f"优化方法: {method}, {status}, 耗时: {elapsed_time:.3f}秒, "
              f"迭代: {result.nit}次, 最终目标值: {result.fun:.6e}")

    # 8. 构建完整权重数组
    full_weights = np.zeros(n, dtype=np.float64)
    full_weights[valid_idx] = result.x
    full_weights[zero_idx] = 0

    # 确保权重非负并归一化
    full_weights = np.maximum(full_weights, 0)
    full_weights /= full_weights.sum() + 1e-20

    return full_weights, result


def iterative_refinement(cov_matrix, risk_budget, initial_weights=None,
                         max_cycles=5, tol=1e-12, verbose=True):
    """
    迭代精炼优化过程
    :param cov_matrix: 协方差矩阵
    :param risk_budget: 风险预算
    :param initial_weights: 初始权重
    :param max_cycles: 最大精炼次数
    :param tol: 收敛容差
    :param verbose: 是否显示输出
    :return: 优化后的权重
    """
    best_weights = initial_weights if initial_weights is not None else np.ones(len(risk_budget)) / len(risk_budget)
    best_obj = float('inf')

    for cycle in range(max_cycles):
        # 使用前一次结果作为起点
        if cycle == 0:
            method = 'SLSQP'
        else:
            method = 'trust-constr'
        weights, result = robust_risk_budget_optimization(
            cov_matrix,
            risk_budget,
            max_iter=100000,
            precision=1e-12 / (10 ** cycle),  # 每次迭代提高精度
            verbose=verbose,
            method=method  # 使用最可靠的方法
        )

        # 计算当前目标函数值
        current_obj = result.fun

        if verbose:
            print(f"精炼周期 {cycle + 1}: 目标值={current_obj:.6e}")

        # 检查是否改进
        if current_obj < best_obj:
            best_weights = weights
            best_obj = current_obj

        # 检查收敛
        if current_obj < tol:
            if verbose:
                print(f"在周期 {cycle + 1} 收敛到目标精度 {tol}")
            break

        # 如果目标值不再显著下降，停止
        if cycle > 0 and (best_obj - current_obj) < tol * 10:
            if verbose:
                print(f"在周期 {cycle + 1} 停止，改进不足")
            break

    return best_weights, result.fun


def calculate_objective(cov_matrix, weights, risk_budget):
    """
    计算目标函数值，兼容Pandas DataFrame和NumPy数组
    :param cov_matrix: 协方差矩阵 (DataFrame或numpy数组)
    :param weights: 权重向量
    :param risk_budget: 风险预算
    :return: 目标函数值
    """
    # 转换风险预算为数组
    risk_budget = np.asarray(risk_budget)

    # 识别有效资产
    valid_idx = risk_budget > 1e-10

    # 如果没有有效资产，返回0
    if not np.any(valid_idx):
        return 0.0

    # 提取有效资产的索引
    if hasattr(cov_matrix, 'index'):
        # 处理DataFrame
        valid_assets = cov_matrix.index[valid_idx]
        valid_cov = cov_matrix.loc[valid_assets, valid_assets].values
    else:
        # 处理numpy数组
        valid_cov = cov_matrix[valid_idx][:, valid_idx]

    # 提取有效权重
    valid_weights = weights[valid_idx]

    # 归一化有效风险预算
    valid_budget = risk_budget[valid_idx] / risk_budget[valid_idx].sum()

    # 计算目标函数
    port_var = valid_weights.T @ valid_cov @ valid_weights
    port_var_reg = port_var + 1e-30
    marginal_risk = valid_cov @ valid_weights
    risk_contrib_ratio = (valid_weights * marginal_risk) / port_var_reg
    return np.sum((risk_contrib_ratio - valid_budget) ** 2)


def calculate_momentum_factor(asset, end_date, master_df, factor_type):
    """
    计算指定资产的动量因子值

    :param asset: 资产代码
    :param end_date: 当前调仓日期
    :param master_df: 包含所有资产历史价格的数据框
    :param factor_type: 动量因子类型 ('1m_ret_vol', '12m_ret_vol', '12m_ret', 'price_quantile')
    :return: 动量因子值
    """
    try:
        # 确保end_date在master_df索引中
        if end_date not in master_df.index:
            return np.nan

        # 获取end_date在master_df中的位置
        end_idx = master_df.index.get_loc(end_date)

        if factor_type == '1m_ret_vol':  # 历史一个月绝对涨跌幅/历史一个月波动率
            # 1个月窗口（约21个交易日）
            if end_idx < 21:
                return np.nan
            start_idx = end_idx - 21
            prices = master_df.iloc[start_idx:end_idx + 1][asset]
            abs_ret = (prices.iloc[-1] / prices.iloc[0]) - 1
            daily_rets = prices.pct_change().dropna()
            vol = daily_rets.std() * np.sqrt(252)  # 年化波动率
            return abs_ret / vol if vol != 0 else np.nan

        elif factor_type == '12m_ret_vol':  # 历史12个月绝对涨跌幅/历史12个月波动率
            # 12个月窗口（约252个交易日）
            if end_idx < 252:
                return np.nan
            start_idx = end_idx - 252
            prices = master_df.iloc[start_idx:end_idx + 1][asset]
            abs_ret = (prices.iloc[-1] / prices.iloc[0]) - 1
            daily_rets = prices.pct_change().dropna()
            vol = daily_rets.std() * np.sqrt(252)  # 年化波动率
            return abs_ret / vol if vol != 0 else np.nan

        elif factor_type == '12m_ret':  # 历史12个月绝对涨跌幅
            # 12个月窗口（约252个交易日）
            if end_idx < 252:
                return np.nan
            start_idx = end_idx - 252
            prices = master_df.iloc[start_idx:end_idx + 1][asset]
            return (prices.iloc[-1] / prices.iloc[0]) - 1

        elif factor_type == 'price_quantile':  # 当前价格在过去12个月的分位水平
            # 12个月窗口（约252个交易日）
            if end_idx < 252:
                return np.nan
            start_idx = end_idx - 252
            prices = master_df.iloc[start_idx:end_idx + 1][asset]
            current_price = prices.iloc[-1]
            # 计算分位水平
            return np.mean(prices < current_price)

        else:
            raise ValueError(f"未知的动量因子类型: {factor_type}")

    except Exception as e:
        print(f"计算资产 {asset} 的 {factor_type} 因子时出错: {str(e)}")
        return np.nan


def calculate_composite_momentum(asset, end_date, master_df):
    """
    计算复合动量信号（四个因子等权组合）

    :param asset: 资产代码
    :param end_date: 当前调仓日期
    :param master_df: 包含所有资产历史价格的数据框
    :return: 复合动量值
    """
    factors = [
        # '1m_ret_vol',
        # '12m_ret_vol',
        '12m_ret',
        # 'price_quantile'
    ]

    factor_values = []

    for factor in factors:
        value = calculate_momentum_factor(asset, end_date, master_df, factor)
        if not np.isnan(value):
            factor_values.append(value)

    # 如果所有因子都有效，返回平均值
    if factor_values:
        return np.mean(factor_values)

    return np.nan


def risk_parity_backtest(risk_budgets, start_date, end_date, target_volatility,
                         asset_alternatives=None, output_dir='results',
                         momentum_lookback=12, asset_selection=None, asset_class_mapping=None):
    """
    带波动率控制、替代资产功能和动量选择的风险平价模型回测函数
    新增功能：每月调仓时，在每个大类资产中选择过去T个月收益最好的前N_i个资产进行风险预算平配

    :param risk_budgets: 字典格式，资产代码 -> 风险预算比例
    :param start_date: 回测起始日期 (格式: 'YYYY-MM-DD')
    :param end_date: 回测结束日期 (格式: 'YYYY-MM-DD')
    :param target_volatility: 目标年化波动率 (小数形式，如0.15表示15%)
    :param asset_alternatives: 字典格式，资产代码 -> 替代资产代码
    :param output_dir: 结果输出目录
    :param momentum_lookback: 动量回看期（月数）
    :param asset_selection: 字典格式，大类资产 -> 选择资产数量N_i
    :param asset_class_mapping: 字典格式，资产代码 -> 大类资产（股票/境外股票/债券/商品）
    :return: 包含所有详细数据的元组 (净值曲线, 每日权重, 每月权重)
    """
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)

    # =============================
    # 1. 数据准备 - 确保从start_date开始有数据
    # =============================
    assets = list(risk_budgets.keys())
    all_prices = []
    asset_sources = {}  # 记录每个资产实际使用的数据源

    # 计算数据获取的起始日期（提前一年）
    start_dt = datetime.strptime(start_date, '%Y-%m-%d')
    extended_start_date = (start_dt - timedelta(days=365)).strftime('%Y-%m-%d')
    extended_start_dt = datetime.strptime(extended_start_date, '%Y-%m-%d')
    start_date = wind.wind_getLastTradeDates([start_dt])[0].strftime('%Y-%m-%d')
    extended_start_date = wind.wind_getLastTradeDates([extended_start_dt])[0].strftime('%Y-%m-%d')
    print(f"数据获取范围: {extended_start_date} 至 {end_date}")

    # 生成完整日期范围（工作日）
    all_dates = pd.date_range(start=extended_start_date, end=end_date, freq='B')
    master_df = pd.DataFrame(index=all_dates)

    # # 为每个资产获取价格数据
    # for asset in assets:
    #     # 确定实际使用的资产代码（考虑替代资产）
    #     actual_asset = asset
    #     if asset_alternatives and asset in asset_alternatives:
    #         alternative = asset_alternatives[asset]
    #         print(f"资产 '{asset}' 设置了替代资产: '{alternative}'")
    #     else:
    #         alternative = None
    #
    #     # 尝试获取原始资产数据
    #     try:
    #         # 获取原始资产数据
    #         df = wind.get_asset_price(asset, extended_start_date, end_date)
    #         df = df.rename(columns={'price': asset})
    #         df = df.set_index('trade_date')
    #
    #         # 检查数据是否覆盖了extended_start_date
    #         if df.index[0] > pd.Timestamp(extended_start_date):
    #             print(
    #                 f"警告: 资产 '{asset}' 数据起始日期为 {df.index[0].strftime('%Y-%m-%d')}，早于要求的 {extended_start_date}")
    #             raise Exception(f"资产 '{asset}' 数据不足")
    #
    #         # 检查在start_date是否有数据
    #         if start_date not in df.index:
    #             print(f"警告: 资产 '{asset}' 在 {start_date} 无数据")
    #             raise Exception(f"资产 '{asset}' 在起始日期无数据")
    #
    #         # 记录数据来源
    #         asset_sources[asset] = asset
    #         print(f"资产 '{asset}' 使用原始数据")
    #
    #     except Exception as e:
    #         print(f"资产 '{asset}' 原始数据获取失败: {str(e)}")
    #
    #         # 如果原始资产数据获取失败，尝试使用替代资产
    #         if alternative:
    #             try:
    #                 print(f"尝试替代资产 '{alternative}'")
    #
    #                 # 获取替代资产数据
    #                 alt_df = wind.get_asset_price(alternative, extended_start_date, end_date)
    #                 alt_df = alt_df.rename(columns={'price': asset})  # 使用原始资产名称
    #                 alt_df = alt_df.set_index('trade_date')
    #
    #                 # 检查替代资产数据是否覆盖了extended_start_date
    #                 if alt_df.index[0] > pd.Timestamp(extended_start_date):
    #                     print(
    #                         f"警告: 替代资产 '{alternative}' 数据起始日期为 {alt_df.index[0].strftime('%Y-%m-%d')}，早于要求的 {extended_start_date}")
    #                     raise Exception(f"替代资产 '{alternative}' 数据不足")
    #
    #                 # 检查在start_date是否有数据
    #                 if start_date not in alt_df.index:
    #                     print(f"警告: 替代资产 '{alternative}' 在 {start_date} 无数据")
    #                     raise Exception(f"替代资产 '{alternative}' 在起始日期无数据")
    #
    #                 # 记录数据来源
    #                 asset_sources[asset] = alternative
    #                 print(f"资产 '{asset}' 使用替代资产 '{alternative}' 的数据")
    #                 df = alt_df  # 使用替代资产数据
    #
    #             except Exception as alt_e:
    #                 print(f"错误: 资产 '{asset}' 及其替代资产 '{alternative}' 均无法获取数据: {str(alt_e)}")
    #                 # 如果替代资产也失败，使用随机数据作为最后手段
    #                 np.random.seed(42)
    #                 prices = np.exp(np.cumsum(np.random.randn(len(all_dates)) * 0.01))
    #                 df = pd.DataFrame({asset: prices}, index=all_dates)
    #                 asset_sources[asset] = "随机生成"
    #                 print(f"警告: 资产 '{asset}' 使用随机生成数据")
    #         else:
    #             print(f"错误: 资产 '{asset}' 数据获取失败且无替代资产")
    #             # 如果没有替代资产，使用随机数据作为最后手段
    #             np.random.seed(42)
    #             prices = np.exp(np.cumsum(np.random.randn(len(all_dates)) * 0.01))
    #             df = pd.DataFrame({asset: prices}, index=all_dates)
    #             asset_sources[asset] = "随机生成"
    #             print(f"警告: 资产 '{asset}' 使用随机生成数据")
    #
    #     # 将资产数据添加到主数据框
    #     master_df = master_df.join(df, how='left')

    ### 直接读excel
    master_df = pd.read_excel('prices2014.xlsx')
    ###
    # 确保所有资产都有数据
    master_df = master_df.ffill().bfill()  # 前向填充+后向填充
    master_df.set_index('date', inplace=True)
    master_df = master_df[assets]

    # 检查回测开始日期是否有数据
    if pd.isna(master_df.loc[start_date]).any().any():
        # 找到第一个所有资产都有数据的日期
        valid_start = master_df.dropna().index[0]
        print(f"警告: 起始日期 {start_date} 有资产缺失数据, 调整为 {valid_start.strftime('%Y-%m-%d')}")
        start_date = valid_start.strftime('%Y-%m-%d')
    else:
        print(f"所有资产在 {start_date} 均有数据，回测将从该日期开始")

    # 截取回测期间的数据
    prices = master_df.loc[start_date:end_date]

    # 打印资产数据来源
    print("\n资产数据来源:")
    for asset, source in asset_sources.items():
        print(f"{asset}: {source}")

    # =============================
    # 2. 核心回测逻辑 - 确保从start_date开始
    # =============================
    # 使用完整历史数据计算日收益率
    daily_returns = master_df.pct_change().dropna()

    # 回测期间的日收益率
    backtest_daily_returns = daily_returns.loc[start_date:end_date]

    # 如果回测期间没有数据，使用第一个有效日期
    if backtest_daily_returns.empty:
        first_valid = daily_returns.index[daily_returns.index >= pd.Timestamp(start_date)][0]
        backtest_daily_returns = daily_returns.loc[first_valid:end_date]
        print(f"警告: 使用第一个有效交易日 {first_valid.strftime('%Y-%m-%d')} 开始回测")

    # 初始化回测数据结构
    portfolio_values = pd.Series(1.0, index=backtest_daily_returns.index)  # 初始净值为1
    weights = pd.Series(0, index=assets, dtype=float)  # 当前持仓权重
    cash_weight = 0.0  # 现金权重

    # 数据结构用于记录详细结果
    daily_weights = pd.DataFrame(index=backtest_daily_returns.index, columns=assets + ['Cash'])
    daily_weights.iloc[0] = 0.0  # 初始权重为0
    daily_weights['Cash'].iloc[0] = 1.0  # 初始全部为现金

    monthly_weights = pd.DataFrame(columns=assets + ['Cash'])
    monthly_dates = []  # 用于记录每月末日期

    # 获取所有月末日期（每月最后一个交易日）
    monthly_rebalance_dates = prices.resample('M').last().index
    monthly_rebalance_dates = wind.wind_getLastTradeDates(monthly_rebalance_dates)
    monthly_rebalance_dates_real = wind.wind_getNextTradeDates(monthly_rebalance_dates)
    monthly_rebalance_dates_real = wind.wind_getNextTradeDates(monthly_rebalance_dates_real)

    # 创建完整日期索引映射
    full_date_index = daily_returns.index

    # 遍历每个交易日（仅回测期间）
    for i, date in enumerate(backtest_daily_returns.index):
        end_date = wind.wind_getLastTradeDates([date], include=False)[0]
        end_date = wind.wind_getLastTradeDates([end_date], include=False)[0]
        end_date = pd.Timestamp(end_date)
        full_i = full_date_index.get_loc(end_date)

        # 每月末再平衡
        if date in monthly_rebalance_dates_real:
            monthly_dates.append(date)
            # =============================================
            # 新增：动量选择资产 (仅在每月调仓时执行)
            # =============================================
            new_risk_budgets = risk_budgets.copy()  # 创建风险预算副本

            if asset_class_mapping and asset_selection:
                # 按大类分组资产
                class_assets = {}
                for asset, class_name in asset_class_mapping.items():
                    if asset not in prices.columns:
                        continue
                    if class_name not in class_assets:
                        class_assets[class_name] = []
                    class_assets[class_name].append(asset)

                # 处理每个大类
                for class_name, assets_in_class in class_assets.items():
                    if class_name not in asset_selection:
                        continue

                    N_i = asset_selection[class_name]
                    if N_i <= 0:
                        continue

                    # 计算大类内资产的复合动量值
                    asset_momentum = {}
                    valid_assets = []

                    for asset in assets_in_class:
                        momentum_score = calculate_composite_momentum(asset, end_date, master_df)
                        if not np.isnan(momentum_score):
                            asset_momentum[asset] = momentum_score
                            valid_assets.append(asset)

                    # 选择表现最好的N_i个资产
                    if valid_assets:
                        # 按动量值降序排序
                        sorted_assets = sorted(valid_assets, key=lambda x: asset_momentum[x], reverse=True)
                        selected_assets = sorted_assets[:min(N_i, len(sorted_assets))]

                        # 计算大类总风险预算
                        total_class_budget = sum(risk_budgets.get(a, 0) for a in assets_in_class)

                        # 重新分配风险预算
                        if selected_assets and total_class_budget > 0:
                            # 未被选中的资产预算设为0
                            for asset in assets_in_class:
                                if asset not in selected_assets:
                                    new_risk_budgets[asset] = 0.0

                            # 选中的资产平均分配预算
                            per_asset_budget = total_class_budget / len(selected_assets)
                            for asset in selected_assets:
                                new_risk_budgets[asset] = per_asset_budget
                    # if date == datetime(2022, 5, 6).date():
                    #     print(1)
            # =============================================
            # 后续波动率控制逻辑（使用调整后的风险预算）
            # =============================================
            lookback = 252  # 一年交易日
            start_idx = max(0, full_i - lookback)
            vol_window = daily_returns.iloc[start_idx:full_i]
            cov_matrix = vol_window.cov()*252
            # 直接使用协方差矩阵的索引创建风险预算列表
            risk_budget_list = [new_risk_budgets.get(asset, 0.0) for asset in cov_matrix.index]
            risk_budget_list = np.array(risk_budget_list)
            risk_budget_list /= risk_budget_list.sum()

            print("=== 标准优化 ===")
            new_weights_result = robust_risk_budget_optimization(cov_matrix, risk_budget_list, verbose=True)
            obj_value = new_weights_result[1].fun

            # 计算新权重 (使用动量调整后的风险预算)
            # print("\n=== 迭代精炼优化 ===")
            # new_weights_result = iterative_refinement(cov_matrix, risk_budget_list, verbose=True)
            # obj_value = new_weights_result[1]
            if obj_value <= 0.001:
                new_weights = new_weights_result[0]
                new_weights = pd.Series(new_weights.flatten())
            else:
                annual_vol = vol_window.std() * np.sqrt(252)
                annual_vol = annual_vol.replace(0, 0.15).clip(lower=0.01, upper=0.50)
                new_weights = pd.Series(new_risk_budgets) / annual_vol
                new_weights /= new_weights.sum()  # 归一化
                new_weights = new_weights.fillna(0)
            new_weights.index = assets
            weights_temp = new_weights.values.reshape(-1, 1)
            portfolio_variance = weights_temp.T @ cov_matrix.values @ weights_temp
            portfolio_volatility = np.sqrt(portfolio_variance)[0, 0]
            if target_volatility < portfolio_volatility:
                new_weights = new_weights/(portfolio_volatility/target_volatility)
            # ... [保持不变的波动率控制部分] ...
            print(new_weights)

            # 更新权重
            weights = new_weights

            # 记录每月权重
            monthly_row = new_weights.to_dict()
            monthly_row['Cash'] = cash_weight
            monthly_weights = pd.concat([monthly_weights, pd.DataFrame(monthly_row, index=[date])])


        # 记录每日权重
        daily_weights.loc[date, assets] = weights.values
        daily_weights.loc[date, 'Cash'] = cash_weight

        # 计算当日组合收益
        # 现金部分收益为0
        daily_port_return = (weights * backtest_daily_returns.loc[date]).sum()

        # 更新净值
        if i > 0:
            prev_value = portfolio_values.iloc[i - 1]
            portfolio_values.loc[date] = prev_value * (1 + daily_port_return)
        else:
            portfolio_values.loc[date] = 1.0  # 第一天净值不变

    # 创建净值曲线DataFrame
    net_value_df = pd.DataFrame({'trade_date': portfolio_values.index, 'NetValue': portfolio_values.values})

    # 添加每日权重到净值曲线
    detailed_df = net_value_df.copy()
    for asset in assets + ['Cash']:
        detailed_df[asset] = daily_weights[asset].values

    # 设置每月权重索引
    monthly_weights.index = monthly_dates

    # =============================
    # 3. 结果输出（包含资产来源信息）
    # =============================
    # 输出到Excel
    output_path = os.path.join(output_dir, 'risk_parity_backtest_results.xlsx')
    with pd.ExcelWriter(output_path) as writer:
        # Sheet1: 详细每日数据
        detailed_df.to_excel(writer, sheet_name='每日数据', index=False)

        # Sheet2: 每月资产配置
        monthly_weights.to_excel(writer, sheet_name='每月资产配置')

        # Sheet3: 绩效摘要
        summary_data = {
            '指标': ['起始日期', '结束日期', '初始净值', '最终净值', '总收益率',
                     '年化收益率', '年化波动率', '目标波动率', '夏普比率'],
            '值': [''] * 9
        }

        # 计算绩效指标
        returns = detailed_df['NetValue'].pct_change().dropna()
        total_return = detailed_df['NetValue'].iloc[-1] / detailed_df['NetValue'].iloc[0] - 1
        annual_return = (1 + total_return) ** (252 / len(returns)) - 1
        annual_volatility = returns.std() * np.sqrt(252)
        sharpe_ratio = annual_return / annual_volatility if annual_volatility != 0 else 0

        # 填充绩效数据
        summary_data['值'] = [
            start_date, end_date, 1.0, detailed_df['NetValue'].iloc[-1],
            f"{total_return:.2%}",
            f"{annual_return:.2%}",
            f"{annual_volatility:.2%}",
            f"{target_volatility:.2%}",
            f"{sharpe_ratio:.2f}"
        ]

        pd.DataFrame(summary_data).to_excel(writer, sheet_name='绩效摘要', index=False)

        # Sheet4: 资产数据来源
        source_data = []
        for asset in assets:
            source_data.append({
                '原始资产': asset,
                '实际数据来源': asset_sources.get(asset, asset),
                '替代资产': asset_alternatives.get(asset, '无') if asset_alternatives else '无'
            })
        pd.DataFrame(source_data).to_excel(writer, sheet_name='资产来源', index=False)

    print(f"结果已保存至: {output_path}")

    # =============================
    # 4. 绘制资产配置图
    # =============================
    # 每月大类资产仓位变化图
    plt.figure(figsize=(12, 6))

    # 确保所有数据是数值类型
    monthly_weights = monthly_weights.apply(pd.to_numeric)

    # 动态生成资产颜色映射
    def generate_asset_colors(assets):
        """为资产动态生成颜色映射"""
        # 预设一组颜色
        color_palette = [
            '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
            '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
            '#aec7e8', '#ffbb78', '#98df8a', '#ff9896', '#c5b0d5'
        ]

        # 为每个资产分配颜色
        asset_colors = {}
        for i, asset in enumerate(assets):
            color_idx = i % len(color_palette)  # 循环使用颜色
            asset_colors[asset] = color_palette[color_idx]

        # 添加现金颜色
        asset_colors['Cash'] = '#7f7f7f'
        return asset_colors

    # 基于risk_budgets中的资产生成颜色映射
    assets_in_budget = list(risk_budgets.keys())
    asset_colors = generate_asset_colors(assets_in_budget)

    # 创建堆叠面积图
    bottom = pd.Series(0, index=monthly_weights.index)
    for asset in monthly_weights.columns:
        # 确保数据是数值类型
        asset_weights = pd.to_numeric(monthly_weights[asset])

        # 确保索引是datetime类型
        if not isinstance(monthly_weights.index, pd.DatetimeIndex):
            dates = pd.to_datetime(monthly_weights.index)
        else:
            dates = monthly_weights.index

        # 获取资产颜色，如果未定义则使用默认灰色
        color = asset_colors.get(asset, '#7f7f7f')
        plt.fill_between(dates, bottom, bottom + asset_weights,
                         label=asset, alpha=0.8, color=color)
        bottom += asset_weights

    # 设置图表属性
    plt.title('大类资产仓位比例变化')
    plt.xlabel('日期')
    plt.ylabel('权重比例')
    plt.ylim(0, 1)
    plt.legend(loc='upper center', bbox_to_anchor=(0.5, -0.15), ncol=4)
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    plt.tight_layout()

    # 保存图表
    plot_path = os.path.join(output_dir, 'asset_allocation.png')
    plt.savefig(plot_path, dpi=300, bbox_inches='tight')
    print(f"资产配置图已保存至: {plot_path}")

    return net_value_df, daily_weights, monthly_weights

# =============================
# 5. 参数设置与执行
# =============================
if __name__ == "__main__":
    # 输入参数
    RISK_BUDGETS = {
        'IC.CFE': 0.0625,  # A股
        'IF.CFE': 0.0625,  # A股
        'IM.CFE': 0.0625,  # A股
        '000922.CSI': 0.0625,  # A
        'NDX.GI': 0.0833,  # 美股
        'HSTECH.HI': 0.0833,  # 港股
        'N225.GI': 0.0834,  # 日股
        # 'H11077.SH': 0.125,  # 国债
        # '950175.CSI': 0.125,  # 国债
        'CBA05201.CS': 0.25,
        # 'CBA20901.CS': 0.125,  # 国债
        'AU.SHF': 0.125,  # 黄金
        'M.DCE': 0.125
        # '159980.SZ':0.0834
    }
    # 新增：资产到大类的映射
    ASSET_CLASS_MAPPING = {
        'IC.CFE': '股票',  # A股
        'IF.CFE': '股票',  # A股
        'IM.CFE': '股票',  # A股
        '000922.CSI': '股票',  # A
        'NDX.GI': '境外股票',  # 美股
        'HSTECH.HI': '境外股票',  # 港股
        'N225.GI': '境外股票',  # 日股
        # 'H11077.SH': '债券',  # 国债
        # '950175.CSI': '债券',
        'CBA05201.CS':'债券',
        # 'CBA20901.CS': '债券',  # 国债
        'AU.SHF': '商品',  # 黄金
        'M.DCE': '商品'
        # '159980.SZ': '商品'
    }
    # 新增：每类资产选择数量
    ASSET_SELECTION = {
        '股票': 2,  # 选择表现最好的2个股票资产
        '境外股票': 1,  # 选择表现最好的1个境外股票
        '债券': 1,  # 选择表现最好的1个债券
        '商品': 1  # 选择表现最好的1个商品
    }
    # 替代资产设置
    asset_alternatives = {
        'IC.CFE': '000905.SH',  # A股
        'IF.CFE': '000300.SH',  # H股
        'IM.CFE': '000852.SH',
        # 'NDX.GI': 0.25,  # 美股
        # 'T.CFE': 'CBA05201.CS',  # 国债
        # 'CBA05201.CS': 0.25,  # 国债
        # '000832.CSI': 0.125,  # 转债
        '159980.SZ': 'CU.SHF',  # 黄金
    }
    # 动量回看期（月数）
    MOMENTUM_LOOKBACK = 12

    START_DATE = '2014-1-6'
    END_DATE = '2029-11-30'
    TARGET_VOLATILITY = 0.99  # 目标年化波动率6%
    OUTPUT_DIR = 'risk_parity_results'
    # 设置中文字体支持
    plt.rcParams['font.sans-serif'] = ['SimHei']  # 用来正常显示中文标签
    plt.rcParams['axes.unicode_minus'] = False  # 用来正常显示负号
    # 执行回测（添加动量参数）
    net_value, daily_weights, monthly_weights = risk_parity_backtest(
        RISK_BUDGETS, START_DATE, END_DATE, TARGET_VOLATILITY,
        asset_alternatives, OUTPUT_DIR,
        momentum_lookback=MOMENTUM_LOOKBACK,
        asset_selection=ASSET_SELECTION,
        asset_class_mapping=ASSET_CLASS_MAPPING
    )

    # 打印结果摘要
    print("\n回测完成!")
    print(f"初始净值: 1.00")
    print(f"最终净值: {net_value['NetValue'].iloc[-1]:.4f}")