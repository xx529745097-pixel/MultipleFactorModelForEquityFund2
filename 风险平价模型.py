import numpy as np
import pandas as pd
from datetime import datetime
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import os
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)
from scipy.optimize import minimize, Bounds, NonlinearConstraint
import time


def robust_risk_budget_optimization(cov_matrix, risk_budget=None, max_iter=100000,
                                    precision=1e-12, min_eig_thresh=1e-10,
                                    verbose=True, method='auto'):
    warnings.filterwarnings("ignore", category=RuntimeWarning, module="scipy.optimize")
    cov_matrix = np.asarray(cov_matrix, dtype=np.float64)
    n = cov_matrix.shape[0]

    if risk_budget is None:
        risk_budget = np.ones(n) / n
    else:
        risk_budget = np.asarray(risk_budget, dtype=np.float64)

    valid_idx = risk_budget > 1e-10
    zero_idx = ~valid_idx
    if not np.any(valid_idx):
        return np.zeros(n), None

    valid_cov = cov_matrix[valid_idx][:, valid_idx].copy()
    valid_budget = risk_budget[valid_idx].copy()

    eigenvalues = np.linalg.eigvalsh(valid_cov)
    min_eigenvalue = np.min(eigenvalues)
    if min_eigenvalue < min_eig_thresh:
        regularization = (min_eig_thresh - min_eigenvalue) * np.eye(valid_cov.shape[0])
        valid_cov += regularization

    valid_budget /= valid_budget.sum()
    n_valid = valid_cov.shape[0]

    def objective(w):
        port_var = w.T @ valid_cov @ w
        port_var_reg = port_var + 1e-30
        marginal_risk = valid_cov @ w
        risk_contrib_ratio = (w * marginal_risk) / port_var_reg
        return np.sum((risk_contrib_ratio - valid_budget) ** 2)

    constraints = []
    bounds = Bounds(0, np.inf)
    inv_cov = np.linalg.pinv(valid_cov)
    min_var_w = inv_cov.sum(axis=1) / inv_cov.sum()
    w0 = min_var_w

    if method == 'auto':
        method = 'trust-constr' if n_valid > 5 else 'SLSQP'

    start_time = time.time()
    options = {'maxiter': max_iter, 'disp': verbose}

    if method == 'SLSQP':
        method_options = {'ftol': precision, 'eps': 1e-10}
    elif method == 'trust-constr':
        method_options = {'xtol': precision, 'gtol': precision, 'barrier_tol': precision, 'verbose': 1 if verbose else 0}
    else:
        raise ValueError(f"未知优化方法: {method}")

    options.update(method_options)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = minimize(objective, w0, method=method, bounds=bounds, constraints=constraints, options=options)

    full_weights = np.zeros(n, dtype=np.float64)
    full_weights[valid_idx] = result.x
    full_weights[zero_idx] = 0
    full_weights = np.maximum(full_weights, 0)
    full_weights /= full_weights.sum() + 1e-20

    return full_weights, result


def calculate_momentum_factor(asset, end_date, master_df, factor_type):
    try:
        if end_date not in master_df.index:
            return np.nan
        end_idx = master_df.index.get_loc(end_date)

        if factor_type == '1m_ret_vol':
            if end_idx < 21: return np.nan
            start_idx = end_idx - 21
            prices = master_df.iloc[start_idx:end_idx + 1][asset]
            abs_ret = (prices.iloc[-1] / prices.iloc[0]) - 1
            daily_rets = prices.pct_change().dropna()
            vol = daily_rets.std() * np.sqrt(252)
            return abs_ret / vol if vol != 0 else np.nan

        elif factor_type == '12m_ret_vol':
            if end_idx < 252: return np.nan
            start_idx = end_idx - 252
            prices = master_df.iloc[start_idx:end_idx + 1][asset]
            abs_ret = (prices.iloc[-1] / prices.iloc[0]) - 1
            daily_rets = prices.pct_change().dropna()
            vol = daily_rets.std() * np.sqrt(252)
            return abs_ret / vol if vol != 0 else np.nan

        elif factor_type == '12m_ret':
            if end_idx < 252: return np.nan
            start_idx = end_idx - 252
            prices = master_df.iloc[start_idx:end_idx + 1][asset]
            return (prices.iloc[-1] / prices.iloc[0]) - 1

        elif factor_type == 'price_quantile':
            if end_idx < 252: return np.nan
            start_idx = end_idx - 252
            prices = master_df.iloc[start_idx:end_idx + 1][asset]
            current_price = prices.iloc[-1]
            return np.mean(prices < current_price)

        else:
            raise ValueError(f"未知的动量因子类型: {factor_type}")

    except Exception as e:
        return np.nan


def calculate_composite_momentum(asset, end_date, master_df):
    factors = ['1m_ret_vol', '12m_ret_vol', '12m_ret', 'price_quantile']
    factor_values = []
    for factor in factors:
        value = calculate_momentum_factor(asset, end_date, master_df, factor)
        if not np.isnan(value):
            factor_values.append(value)
    return np.mean(factor_values) if factor_values else np.nan


def calculate_performance_analysis(net_values):
    df = net_values.copy()
    df.columns = ['date', 'nav']
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)
    df['daily_return'] = df['nav'].pct_change()
    df['year'] = df['date'].dt.year.astype(int)

    year_end_nav = df.groupby('year')['nav'].last().reset_index()
    year_full_data = {y: g for y, g in df.groupby('year')}
    MIN_TRADING_DAYS = 5
    annual_results = []

    for i in range(len(year_end_nav)):
        curr_year = year_end_nav.iloc[i]['year']
        curr_data = year_full_data.get(curr_year, pd.DataFrame())
        n = len(curr_data)
        ann_ret = mdd = vol = np.nan

        if n >= MIN_TRADING_DAYS:
            curr_nav = year_end_nav.iloc[i]['nav']
            if i == 0:
                start_nav = curr_data['nav'].iloc[0]
                ann_ret = (curr_nav / start_nav) - 1
            else:
                prev_nav = year_end_nav.iloc[i-1]['nav']
                ann_ret = (curr_nav / prev_nav) - 1

            cum_max = curr_data['nav'].cummax()
            dd = (curr_data['nav'] - cum_max) / cum_max
            mdd = dd.min()
            daily_ret = curr_data['daily_return'].dropna()
            if len(daily_ret) > 1:
                vol = daily_ret.std() * np.sqrt(252)

        annual_results.append({
            '年份': int(curr_year),
            '年度收益(%)': ann_ret * 100 if not np.isnan(ann_ret) else np.nan,
            '最大回撤(%)': mdd * 100 if not np.isnan(mdd) else np.nan,
            '波动率(%)': vol * 100 if not np.isnan(vol) else np.nan
        })

    total_ret = (df['nav'].iloc[-1] / df['nav'].iloc[0]) - 1
    years = (df['date'].iloc[-1] - df['date'].iloc[0]).days / 365.25
    ann_return = (1 + total_ret) ** (1 / years) - 1
    cum_max_all = df['nav'].cummax()
    mdd_all = ((df['nav'] - cum_max_all) / cum_max_all).min()
    dr_all = df['daily_return'].dropna()
    vol_all = dr_all.std() * np.sqrt(252) if len(dr_all) > 1 else np.nan

    overall = {'年份': '全时段', '年度收益(%)': ann_return * 100, '最大回撤(%)': mdd_all * 100, '波动率(%)': vol_all * 100}
    perf_df = pd.concat([pd.DataFrame(annual_results), pd.DataFrame([overall])], ignore_index=True)
    return perf_df


def risk_parity_backtest(risk_budgets, start_date, end_date, target_volatility,
                         asset_alternatives=None, output_dir='results',
                         asset_selection=None, asset_class_mapping=None):
    os.makedirs(output_dir, exist_ok=True)
    assets = list(risk_budgets.keys())

    master_df = pd.read_excel('prices.xlsx')
    master_df['date'] = pd.to_datetime(master_df['date'])
    master_df = master_df.set_index('date').sort_index().ffill().bfill()

    if 'Cash' not in master_df.columns:
        raise Exception("Excel必须包含Cash列（货币基金）")

    cash_series = master_df['Cash']
    master_df = master_df[assets]
    daily_returns = master_df.pct_change().dropna()
    cash_daily_returns = cash_series.pct_change().dropna()

    backtest_indices = master_df.loc[start_date:end_date].index
    backtest_daily_returns = daily_returns.loc[backtest_indices[0]:end_date]
    backtest_cash_returns = cash_daily_returns.loc[backtest_indices[0]:end_date]

    portfolio_values = pd.Series(1.0, index=backtest_daily_returns.index)
    weights = pd.Series(0.0, index=assets)
    cash_weight = 1.0
    daily_weights = pd.DataFrame(index=backtest_daily_returns.index, columns=assets + ['Cash'], dtype=float)
    daily_weights.iloc[0] = 0.0
    daily_weights['Cash'].iloc[0] = 1.0
    monthly_weights = pd.DataFrame(columns=assets + ['Cash'])
    monthly_dates = []

    all_months = backtest_daily_returns.index.to_period('M').unique()
    compute_dates = []
    effective_dates = []

    for m in all_months:
        m_days = backtest_daily_returns.index[backtest_daily_returns.index.to_period('M') == m]
        if len(m_days) >= 2:
            compute_dates.append(m_days[0])
            effective_dates.append(m_days[1])

    # ---------------------
    # 关键修复：获取每月最后一个交易日（Timestamp类型）
    # ---------------------
    month_end_dict = {}
    for m in all_months:
        m_days = backtest_daily_returns.index[backtest_daily_returns.index.to_period('M') == m]
        if len(m_days) > 0:
            month_end_dict[m] = m_days[-1]

    for i, date in enumerate(backtest_daily_returns.index):
        if date in compute_dates:
            # 修复：获取当前计算日期之前的、主数据表中的上个月最后一个交易日
            # 确保计算基准日是固定的历史时间点
            last_month_end = master_df.index[master_df.index < date][-1]
            month_end_date = last_month_end

            selected_assets = []
            if asset_class_mapping and asset_selection:
                class_assets = {}
                for a, c in asset_class_mapping.items():
                    if a not in assets: continue
                    if c not in class_assets: class_assets[c] = []
                    class_assets[c].append(a)

                for cls_name, cls_assets in class_assets.items():
                    if cls_name not in asset_selection: continue
                    N = asset_selection[cls_name]
                    if N <= 0: continue

                    mom_dict = {}
                    valid_list = []
                    for a in cls_assets:
                        ms = calculate_composite_momentum(a, month_end_date, master_df)
                        if not np.isnan(ms):
                            mom_dict[a] = ms
                            valid_list.append(a)

                    if valid_list:
                        sorted_assets = sorted(valid_list, key=lambda x: mom_dict[x], reverse=True)
                        selected = sorted_assets[:min(N, len(sorted_assets))]
                        selected_assets.extend(selected)

            new_risk_budgets = pd.Series(0.0, index=assets)
            for cls_name in asset_class_mapping.values():
                cls_all = [a for a in assets if asset_class_mapping[a] == cls_name]
                total_cls_risk = sum([risk_budgets[a] for a in cls_all])
                cls_selected = [a for a in selected_assets if asset_class_mapping[a] == cls_name]
                if len(cls_selected) > 0:
                    per = total_cls_risk / len(cls_selected)
                    for a in cls_selected:
                        new_risk_budgets[a] = per

            # ---------------------
            # 关键修复：日期运算正常
            # ---------------------
            lookback_start = month_end_date - pd.DateOffset(years=1)
            vol_window = daily_returns.loc[lookback_start:month_end_date].dropna()
            if len(vol_window) < 30:
                continue
            cov_matrix = vol_window.cov() * 252

            rb_list = [new_risk_budgets[a] for a in cov_matrix.index]
            rb_list = np.array(rb_list)
            rb_list /= (rb_list.sum() + 1e-20) if rb_list.sum() != 0 else 1
            w, _ = robust_risk_budget_optimization(cov_matrix, rb_list, verbose=False)
            new_weights = pd.Series(w, index=cov_matrix.index)

            w_ = new_weights.values.reshape(-1, 1)
            port_var = w_.T @ cov_matrix.values @ w_
            port_vol = np.sqrt(port_var)[0, 0]
            if port_vol > 1e-6:
                new_weights = new_weights * (target_volatility / port_vol)

            sum_risky = new_weights.sum()
            cash_w = max(0.0, 1.0 - sum_risky)
            new_weights /= (sum_risky + cash_w + 1e-10)

            next_weights = new_weights.copy()
            next_cash = cash_w

        if date in effective_dates:
            weights = next_weights.copy()
            cash_weight = next_cash
            row = weights.to_dict()
            row['Cash'] = cash_weight
            monthly_weights = pd.concat([monthly_weights, pd.DataFrame([row], index=[date])])

        daily_weights.loc[date, assets] = weights.values
        daily_weights.loc[date, 'Cash'] = cash_weight
        risky_ret = (weights * backtest_daily_returns.loc[date]).sum()
        cash_ret = cash_weight * backtest_cash_returns.loc[date]
        total_ret = risky_ret + cash_ret

        if i > 0:
            portfolio_values.loc[date] = portfolio_values.iloc[i-1] * (1 + total_ret)
        else:
            portfolio_values.loc[date] = 1.0

    net_value_df = pd.DataFrame({'date': portfolio_values.index, 'NetValue': portfolio_values.values})
    perf_df = calculate_performance_analysis(net_value_df)
    output_path = os.path.join(output_dir, 'risk_parity_backtest_results.xlsx')

    with pd.ExcelWriter(output_path) as writer:
        net_value_df.join(daily_weights).to_excel(writer, sheet_name='每日数据', index=False)
        monthly_weights.to_excel(writer, sheet_name='每月资产配置')
        perf_df.to_excel(writer, sheet_name='绩效分析')

    print(f"回测完成 | 最终净值: {portfolio_values.iloc[-1]:.4f}")
    return net_value_df, daily_weights, monthly_weights


if __name__ == "__main__":
    plt.rcParams['font.sans-serif'] = ['SimHei']
    plt.rcParams['axes.unicode_minus'] = False

    RISK_BUDGETS = {
        'IC.CFE': 0.0833,
        'IF.CFE': 0.0833,
        'IM.CFE': 0.0834,
        'NDX.GI': 0.0833,
        'HSTECH.HI': 0.0833,
        'N225.GI': 0.0834,
        'CBA05201.CS': 0.25,
        'AU.SHF': 0.0833,
        'M.DCE': 0.0833,
        '159980.SZ': 0.0834
    }

    ASSET_CLASS_MAPPING = {
        'IC.CFE': '股票', 'IF.CFE': '股票', 'IM.CFE': '股票',
        'NDX.GI': '境外股票', 'HSTECH.HI': '境外股票', 'N225.GI': '境外股票',
        'CBA05201.CS': '债券',
        'AU.SHF': '商品', 'M.DCE': '商品', '159980.SZ': '商品'
    }

    ASSET_SELECTION = {'股票': 2, '境外股票': 1, '债券': 1, '商品': 1}

    net_value, daily_weights, monthly_weights = risk_parity_backtest(
        RISK_BUDGETS,
        start_date='2020-12-30',
        end_date='2026-05-07',
        target_volatility=0.03,
        asset_alternatives=None,
        output_dir='risk_parity_results',
        asset_selection=ASSET_SELECTION,
        asset_class_mapping=ASSET_CLASS_MAPPING
    )