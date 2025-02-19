# ------------------------------------------------
# 本文档用于资产配置模型相关画图
# ------------------------------------------------
import pandas as pd
import datetime
import matplotlib.pyplot as plt
import src.analysis.portfolioConstruction as pc
from src.utils.Calculation import *
from src.const import *

plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False
plt.style.use('ggplot')

# ------------------------------------------------------
# 回测滚动持有绩效
# ------------------------------------------------------
def pcPlot_rollingHold(
    asset_return,  # DataFrame，各类资产收益率序列
    asset_weight,  # dictionary of asset weight
    rebalance=26,  # 多长时间做一次rebalance, 单位：周
    discount_asset=['Commodity', 'Arbitrage', 'Hedge'],  # List, 需要提取业绩报酬的资产列表
    fee=0.15,  # 提取业绩报酬
    rolling_hold=1,
    threshold=0,  # 滚动持有胜率
    freq='W',  # 数据频率，可以取'W'或'D'
    local_path=None
):
    assert freq in ['W', 'D'], "Freq must in ['W', 'D']"
    backtest_nav = pc.pc_backTest(asset_return, asset_weight, freq=freq, rebalance=rebalance, discount_asset=discount_asset, fee=fee)[1]
    backtest_ret = (backtest_nav / backtest_nav.shift(1) - 1).dropna()
    roll_wr, roll_ret, roll_vol, roll_mdd = basicCal_getRollingHoldPerformance(backtest_ret, freq=freq,
                                                                               rolling_hold=rolling_hold, threshold=threshold)
    plot_df = pd.concat([roll_ret, roll_vol, roll_mdd], axis=1)
    plot_df.columns = ['滚动持有%s年收益率（年化）分布' % rolling_hold, '滚动持有%s年波动率分布' % rolling_hold, '滚动持有%s年最大回撤分布' % rolling_hold]
    plot_df.hist(bins=30,figsize=(16,5.5),layout=(1,3))
    plt.tight_layout()
    if local_path is None:
        pass
    else:
        picture_name = '滚动持有绩效'  # the name of the picture you want to save
        plt.savefig('%s/%s.png' % (local_path, picture_name))
    return roll_wr