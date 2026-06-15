# ------------------------------------------------------
# 股指期货分析的相关画图函数
# ------------------------------------------------------
import datetime
import matplotlib.pyplot as plt
import pandas as pd
import src.data.wind as wind
import src.visualization.monitorVis as mntrVis
from src.analysis.indexFutureAnalysis import *

plt.style.use('seaborn-whitegrid')
plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False

# ------------------------------------------------------
# 画简单做多某个股指期货合约策略的净值图
# ------------------------------------------------------
def visIdxFutureAnls_LongSinlgeIndexFutureStrategyNavPlot(
    futures_id,  # string, must be "IF", "IC" OR "IH"
    start_date,  # 起始日期，输入格式:datetime.date
    end_date,  # 结束日期，输入格式:datetime.date
    save_path=None  # 图片存储地址
):
    continuous_contract_data = idxFutureAnls_stockIndexFutureBasisAnalysis(futures_id, start_date, end_date)

    fig = plt.figure(figsize=(14, 7))
    fig.set_dpi(100)
    ax1 = fig.add_subplot(111)
    ax1.plot(continuous_contract_data['date'], continuous_contract_data['nav'], color='blue', label='净值', linewidth=1)
    ax1.scatter(continuous_contract_data[continuous_contract_data['shift_flag'] == 1]['date'], continuous_contract_data[continuous_contract_data['shift_flag'] == 1]['nav'], marker='o',
                color='red', label='合约切换时点')
    ax1.legend()
    ax1.set_title(futures_id + '合约移仓策略（做多）净值')

    if save_path:
        plt.savefig(save_path + "/" + futures_id + "合约移仓策略（做多）净值" + start_date.strftime("%Y%m%d") + "_" + end_date.strftime("%Y%m%d") + ".png")
    plt.show()
    return
# ------------------------------------------------------
# 画近x周的某个股指期货的年化基差水平
# ------------------------------------------------------
def visIdxFutureAnls_WeeklyIndexFutureAnnualizedBasisPlot(
    futures_id,  # string, must be "IF", "IC" OR "IH"
    start_date,  # 起始日期，输入格式:datetime.date
    end_date,  # 结束日期，输入格式:datetime.date
    num_past_weeks,  # 观察过去几周， 输入格式：int
    save_path=None  # 图片存储地址
):
    continuous_contract_data = idxFutureAnls_stockIndexFutureBasisAnalysis(futures_id, start_date, end_date)

    fig = plt.figure(figsize=(14, 7))
    fig.set_dpi(100)
    ax1 = fig.add_subplot(111)
    continuous_contract_data.index = pd.to_datetime(continuous_contract_data['date'])
    continuous_contract_data['annualized_discount_premium_rate'].resample('W-Fri').last()[-num_past_weeks:].plot.bar(rot=0, ax=ax1)
    ax1.set_title(futures_id + "近" + str(num_past_weeks) + "周周末年化基差水平")
    ax1.yaxis.set_major_formatter(ticker.PercentFormatter(xmax=1, decimals=2))


    if save_path:
        plt.savefig(save_path + "/" + futures_id + "近" + str(num_past_weeks) + "周周末年化基差水平" + end_date.strftime("%Y%m%d") + ".png")

    plt.show()
    return
# ------------------------------------------------------
# 画某个股指合约的绝对基差水平
# ------------------------------------------------------
def visIdxFutureAnls_IndexFutureBasisPlot(
    futures_id,  # string, must be "IF", "IC" OR "IH"
    start_date,  # 起始日期，输入格式:datetime.date
    end_date,  # 结束日期，输入格式:datetime.date
    save_path=None  # 图片存储地址
):
    continuous_contract_data = idxFutureAnls_stockIndexFutureBasisAnalysis(futures_id, start_date, end_date)

    fig = plt.figure(figsize=(14, 7))
    fig.set_dpi(100)
    ax1 = fig.add_subplot(111)
    ax1.plot(continuous_contract_data['date'], continuous_contract_data['basis'], color='blue', label='基差水平', linewidth=1)
    p_value_25 = np.percentile(continuous_contract_data['basis'].values, 25)
    p_value_50 = np.percentile(continuous_contract_data['basis'].values, 50)
    p_value_75 = np.percentile(continuous_contract_data['basis'].values, 75)
    ax1.axhline(y=p_value_25, color='red', label='25分位', linestyle='--')
    ax1.axhline(y=p_value_50, color='green', label='50分位', linestyle='--')
    ax1.axhline(y=p_value_75, color='yellow', label='75分位', linestyle='--')
    ax1.spines['top'].set_visible(False)
    ax1.spines['right'].set_visible(False)
    ax1.spines['bottom'].set_color('black')
    ax1.spines['left'].set_color('black')
    ax1.legend()
    ax1.set_title(futures_id + '绝对基差水平')
    plt.tight_layout()

    if save_path:
        plt.savefig(save_path + "/" + futures_id + "绝对基差水平" + start_date.strftime("%Y%m%d") + "_" + end_date.strftime("%Y%m%d") + ".png")
    plt.show()
    return

# ------------------------------------------------------
# 基差监控：画近N日各股指期货的年化基差水平
# ------------------------------------------------------
def visIdxFutureAnls_StockIndexFuturesBasisMonitorPlot(
    date,            # 监控的数据日期
    tracked_days=10  # 回看天数
):
    wind_calendar = wind.wind_getSSECalendar()
    start_date = wind_calendar[wind_calendar['date'] <= date]['date'].iloc[-tracked_days]
    end_date = wind_calendar[wind_calendar['date'] <= date]['date'].iloc[-1]
    result_fig = mntrVis.mntrVis_PlotStockIndexFuturesBasisLevel(start_date, end_date)
    plt.show()
    return
