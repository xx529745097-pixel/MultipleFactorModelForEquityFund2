# ------------------------------------------------
# 本文档用于风险预算模型需要调用的函数
# ------------------------------------------------
import numpy as np
from scipy.optimize import minimize

# ------------------------------------------------------
# 计算组合风险
# ------------------------------------------------------
def riskBgt_calPortfolioVar(
    w,  # 权重参数
    V  # DataFrame or Matrix, covariance
):
    w = np.matrix(w)
    V = np.matrix(V)
    return (w * V * w.T)[0,0]

# ------------------------------------------------------
# 计算单个资产对组合风险贡献度
# ------------------------------------------------------
def riskBgt_calRiskContribution(
    w,  # 权重参数
    V  # DataFrame or Matrix, covariance
):
    sigma = np.sqrt(riskBgt_calPortfolioVar(w, V))
    # 边际风险贡献
    MRC = V.dot(w.T) / sigma
    # 风险贡献
    RC = np.multiply(MRC, w.T)
    return RC

# ------------------------------------------------------
# 风险预算优化目标
# ------------------------------------------------------
def riskBgt_riskBudgetObjective(
    x,  # 优化目标
    pars  # list, pars[0]协方差, pras[1]组合中资产预期风险贡献度的目标向量
):
    V = pars[0]  # 协方差矩阵
    x_t = pars[1]  # 组合中资产预期风险贡献度的目标向量
    sig_p = np.sqrt(riskBgt_calPortfolioVar(x, V))  # portfolio sigma
    risk_target = np.asmatrix(np.multiply(sig_p, x_t))
    asset_RC = riskBgt_calRiskContribution(x, V)
    J = np.sum(np.square(asset_RC * 100 - risk_target * 100))  # sum of squared error
    return J

# ------------------------------------------------------
# 限制条件1: sum equals 1
# ------------------------------------------------------
def riskBgt_totalWeightConstraint(x):
    return np.sum(x) - 1.0

# ------------------------------------------------------
# 限制条件2: long only
# ------------------------------------------------------
def riskBgt_longOnlyConstraint(x):
    return x

# ------------------------------------------------------
# 根据资产预期目标风险贡献度来计算各资产的权重
# ------------------------------------------------------
def riskBgt_calWeight(x, w0, V):
    x_t = x
    cons = ({'type': 'eq', 'fun': riskBgt_totalWeightConstraint},
            {'type': 'ineq', 'fun': riskBgt_longOnlyConstraint})
    res = minimize(riskBgt_riskBudgetObjective, w0, args=[V, x_t], method='SLSQP',
                   constraints=cons, options={'disp': True})
    w_rb = np.asmatrix(res.x)
    return w_rb

# ------------------------------------------------------
# 权重优化限制条件1: risk contribution <= risk budget * (1 + tolerance)
# ------------------------------------------------------
def riskBgt_fRiskToleranceUpper(
    V,  # covariance matrix
    w0,  # original weight for given risk budget
    TB  # tolerated bias
):
    def val(x):
        rc = riskBgt_calRiskContribution(w0, V)
        return np.asarray(rc * (1 + TB) - riskBgt_calRiskContribution(x, V))[0]
    return val

# ------------------------------------------------------
# 权重优化限制条件2: risk contribution >= risk budget * (1 - tolerance)
# ------------------------------------------------------
def riskBgt_fRiskToleranceLower(
    V,  # covariance matrix
    w0,  # original weight for given risk budget
    TB  # tolerated bias
):
    def val(x):
        rc = riskBgt_calRiskContribution(w0, V)
        return np.asarray(riskBgt_calRiskContribution(x, V) - rc * (1 - TB))[0]
    return val

# ------------------------------------------------------
# 改进权重优化目标
# ------------------------------------------------------
def riskBgt_adjustedWeightObjective(
    x,  # 优化目标
    pars  # list, pars[0]各类资产年化收益率 pars[1]协方差矩阵
):
    ret = pars[0]  # 各类资产年化收益率
    V = pars[1]  # 协方差矩阵
    J = (x * ret).sum() / np.sqrt(riskBgt_calPortfolioVar(x, V))
    return -J

# ------------------------------------------------------
# 计算改进配置权重
# ------------------------------------------------------
def riskBgt_calAdjustedWeight(ret, V, w0, TB):
    cons = ({'type': 'eq', 'fun': riskBgt_totalWeightConstraint},
            {'type': 'ineq', 'fun': riskBgt_fRiskToleranceUpper(V, w0, TB)},
            {'type': 'ineq', 'fun': riskBgt_fRiskToleranceLower(V, w0, TB)})
    res = minimize(riskBgt_adjustedWeightObjective, w0, args=[ret, V], method='SLSQP',
                   constraints=cons, options={'disp': True, 'maxiter': 10})
    adj_w = np.asmatrix(res.x)
    return adj_w
