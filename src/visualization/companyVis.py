# ------------------------------------------------
# 本文档用于基金公司数据的画图
# ------------------------------------------------
import seaborn as sn
import pandas as pd
import numpy as np
import datetime
import dataframe_image as dfi
import matplotlib.pyplot as plt
import src.analysis.CompanyAnalysis as Comp
import src.data.wind as wind
plt.style.use('ggplot') # 使用ggplot样式
plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False

# ------------------------------------------------------
# 基金公司财务数据画图
# ------------------------------------------------------
def visCompany_compFinData(
        company                  # 基金公司简称（如易方达基金，东证资管，中信证券），格式为str
):
    df = Comp.anlsCompany_compFinData([company])
    df.index=df['date']
    # 基金公司管理规模及收入
    plt.rcParams['figure.figsize'] = (7, 4)
    fig, ax1 = plt.subplots()
    ax2 = ax1.twinx()
    x = df['date']
    y_1 = df['net_asset']
    y_2 = df['management_exp']
    ax1.plot(x, y_1, color='r')
    ax2.plot(x, y_2, color='k')
    ax1.grid(axis='y', linestyle='--')
    ax1.set_ylabel('亿元')
    ax2.set_ylabel('亿元')
    fig.legend(['管理规模（左轴）', '管理费收入（右轴）'], loc='upper left')
    plt.title(company+' 非货管理规模及管理费收入')
    plt.show()
    # 基金公司收益来源拆分
    plt.rcParams['figure.figsize'] = (7, 4)
    df.loc[:, ['stock_pnl', 'bond_pnl', 'fund_pnl']].plot.bar(stacked=True)
    plt.xticks(rotation=45)
    plt.ylabel('收入(亿元)')
    plt.xlabel('报告期')
    plt.title(company + ' 投资收益拆分')
    plt.legend(['股票收益','债券收益','基金收益'])
    plt.show()
    # 基金公司股票收益拆分
    plt.rcParams['figure.figsize'] = (7, 4)
    df.loc[:, ['stock_inv_inc', 'dvd_inc', 'stock_fv_chg']].plot.bar(stacked=True)
    plt.xticks(rotation=45)
    plt.ylabel('收入(亿元)')
    plt.xlabel('报告期')
    plt.title(company + ' 股票收益拆分')
    plt.legend(['股票差价收入', '股息收入', '股票公允价值变动'])
    plt.show()
    # 基金公司债券收益拆分
    plt.rcParams['figure.figsize'] = (7, 4)
    df.loc[:, ['bond_inv_inc', 'bond_int_inc', 'bond_fv_chg']].plot.bar(stacked=True)
    plt.xticks(rotation=45)
    plt.ylabel('收入(亿元)')
    plt.xlabel('报告期')
    plt.title(company + ' 债券收益拆分')
    plt.legend(['债券差价收入', '票息收入', '债券公允价值变动'])
    plt.show()
    # 基金公司基金收益拆分
    plt.rcParams['figure.figsize'] = (7, 4)
    df.loc[:, ['fund_inv_inc', 'fund_fv_chg']].plot.bar(stacked=True)
    plt.xticks(rotation=45)
    plt.ylabel('收入(亿元)')
    plt.xlabel('报告期')
    plt.title(company + ' 基金收益拆分')
    plt.legend(['基金差价收入', '基金公允价值变动'])
    plt.show()

# ------------------------------------------------------
# 基金公司财务数据分位数画图
# ------------------------------------------------------
def visCompany_compFinDataRanking(
        company                 # 基金公司简称（如易方达基金，东证资管，中信证券），格式为str
):
    df = Comp.anlsCompany_compFinDataRanking([company])
    df.index = df['date']
    # 基金公司管理规模及收入排名
    plt.rcParams['figure.figsize'] = (7, 4)
    fig, ax1 = plt.subplots()
    ax2 = ax1.twinx()
    x = df['date']
    y_1 = df['net_asset']
    y_2 = df['management_exp']
    ax1.plot(x, y_1, color='r')
    ax2.plot(x, y_2, color='k')
    ax1.grid(axis='y', linestyle='--')
    fig.legend(['管理规模（左轴）', '管理费收入（右轴）'], loc='upper left')
    plt.title(company+' 管理规模及收入排名分位数')
    plt.show()
    # 基金公司股票投资收益排名
    plt.rcParams['figure.figsize'] = (7, 4)
    df['stock_pnl'].plot()
    plt.xticks(rotation=45)
    plt.xlabel('报告期')
    plt.title(company + ' 股票投资收益排名')
    plt.show()
    # 基金公司债券投资收益排名
    plt.rcParams['figure.figsize'] = (7, 4)
    df['bond_pnl'].plot()
    plt.xticks(rotation=45)
    plt.xlabel('报告期')
    plt.title(company + ' 债券投资收益排名')
    plt.show()
    # 基金公司基金投资收益排名
    plt.rcParams['figure.figsize'] = (7, 4)
    df['fund_pnl'].plot()
    plt.xticks(rotation=45)
    plt.xlabel('报告期')
    plt.title(company + ' 基金投资收益排名')
    plt.show()

# ------------------------------------------------------
# 基金公司持有股票的财务数据画图
# ------------------------------------------------------
def visCompany_stockHoldingsFinData(
        company                  # 基金公司简称（如易方达基金，东证资管，中信证券），格式为str
):
    df = Comp.anlsCompany_stockHoldingsFinData([company])
    today = pd.to_datetime('today').date()
    date_latest = df.loc[df.shape[0] - 1, 'date']
    if (today - date_latest) < datetime.timedelta(days=90):
        df.drop((df.shape[0] - 1), inplace=True)  # 如果没到上市公司年报和半年报披露日，删掉最后一行
    df.index = df['date']
    # 集中度
    plt.rcParams['figure.figsize'] = (7, 4)
    df[['Top10_stock', 'Top3_industry']].plot()
    plt.xticks(rotation=45)
    plt.xlabel('报告期')
    plt.legend(['前十大股票比例','前三大行业比例'])
    plt.title(company + ' 持仓集中度')
    plt.show()
    # 盈利性
    plt.rcParams['figure.figsize'] = (7, 4)
    df[['eps_quarter', 'net_profit_yoy']].plot()
    plt.xticks(rotation=45)
    plt.xlabel('报告期')
    plt.legend(['单季度EPS','净利润同比增长率'])
    plt.title(company + ' 持仓盈利性')
    plt.show()
    # 估值
    plt.rcParams['figure.figsize'] = (7, 4)
    fig, ax1 = plt.subplots()
    ax2 = ax1.twinx()
    x = df['date']
    y_1 = df['pe_ttm']
    y_2 = df['pb']
    ax1.plot(x, y_1, color='r')
    ax2.plot(x, y_2, color='k')
    ax1.grid(axis='y', linestyle='--')
    fig.legend(['市盈率（左轴）', '市净率（右轴）'])
    plt.title(company + ' 持仓估值')
    plt.show()
    # 市值
    plt.rcParams['figure.figsize'] = (7, 4)
    df[['total_mv', 'floating_mv']].plot()
    plt.xticks(rotation=45)
    plt.xlabel('报告期')
    plt.legend(['总市值','流通市值'])
    plt.title(company + ' 持仓市值')
    plt.show()

# ------------------------------------------------------
# 基金公司持有股票的财务数据分位数画图
# ------------------------------------------------------
def visCompany_stockHoldingsFinDataRanking(
        company                  # 基金公司简称（如易方达基金，东证资管，中信证券），格式为str
):
    df = Comp.anlsCompany_stockHoldingsFinDataRanking([company])
    today = pd.to_datetime('today').date()
    date_latest = df.loc[df.shape[0]-1, 'date']
    if (today - date_latest) < datetime.timedelta(days=90):
        df.drop((df.shape[0]-1), inplace=True) # 如果没到上市公司年报和半年报披露日，删掉最后一行
    df.index = df['date']
    # 最新一期截面情况
    df_latest = df.tail(1)
    plt.style.use('ggplot')
    feature = list(df_latest.columns[2:])
    values = df_latest[feature].values[0].tolist()
    feature = ['单季度EPS', '净利润同比增长率', '总市值', '流通市值', '市盈率', '市净率', '前十大股票比例', '前三大行业比例'] #重命名
    N = len(values)
    angles = np.linspace(0, 2 * np.pi, N, endpoint=False)# 设置雷达图的角度，用于平分切开一个平面
    values = np.concatenate((values, [values[0]]))# 使雷达图封闭起来
    angles = np.concatenate((angles, [angles[0]]))
    fig = plt.figure()# 绘图
    ax = fig.add_subplot(111, polar=True)# 设置为极坐标格式
    ax.plot(angles, values, 'o-', linewidth=2, label='活动前')# 绘制折线图
    ax.fill(angles, values, 'r', alpha=0.5)
    ax.set_thetagrids(angles[:8] * 180 / np.pi, feature)# 添加每个特质的标签
    ax.set_ylim(0, 1)# 设置极轴范围
    ax.grid(True)# 增加网格纸
    plt.title(df_latest.index.values[0].strftime('%Y-%m-%d')+'基金公司所处分位数')
    plt.show()
    # 集中度
    plt.rcParams['figure.figsize'] = (7, 4)
    df[['Top10_stock', 'Top3_industry']].plot()
    plt.xticks(rotation=45)
    plt.xlabel('报告期')
    plt.legend(['前十大股票比例', '前三大行业比例'])
    plt.title(company + ' 持仓集中度分位数')
    plt.show()
    # 盈利性
    plt.rcParams['figure.figsize'] = (7, 4)
    df[['eps_quarter', 'net_profit_yoy']].plot()
    plt.xticks(rotation=45)
    plt.xlabel('报告期')
    plt.legend(['单季度EPS', '净利润同比增长率'])
    plt.title(company + ' 持仓盈利性分位数')
    plt.show()
    # 估值
    plt.rcParams['figure.figsize'] = (7, 4)
    df[['pe_ttm', 'pb']].plot()
    plt.xticks(rotation=45)
    plt.xlabel('报告期')
    plt.legend(['市盈率', '市净率'])
    plt.title(company + ' 持仓估值分位数')
    plt.show()
    # 市值
    plt.rcParams['figure.figsize'] = (7, 4)
    df[['total_mv', 'floating_mv']].plot()
    plt.xticks(rotation=45)
    plt.xlabel('报告期')
    plt.legend(['总市值', '流通市值'])
    plt.title(company + ' 持仓市值分位数')
    plt.show()
    
# ------------------------------------------------------
# 基金公司分类型管理规模画图
# ------------------------------------------------------
def visCompany_compAUM(
        company,                  # 基金公司简称（如易方达基金，东证资管，中信证券），格式为str
        type_level = 1            # 基金类型分类，只有1和2两个选项
):
    df = Comp.anlsCompany_compAUM([company], type_level)
    df_rank = Comp.anlsCompany_compAUMRanking([company], type_level)
    if type_level == 1:
        df = pd.pivot_table(data=df, values='net_asset', index='date', columns='type_name_lv1')
        rank = pd.pivot_table(data=df_rank, values='rank', index='date', columns='type_name_lv1')
        num = pd.pivot_table(data=df_rank, values='num', index='date', columns='type_name_lv1')
    else:
        df = pd.pivot_table(data=df, values='net_asset', index='date', columns='type_name_lv2')
        rank = pd.pivot_table(data=df_rank, values='rank', index='date', columns='type_name_lv2')
        num = pd.pivot_table(data=df_rank, values='num', index='date', columns='type_name_lv2')
    plt.rcParams['figure.figsize'] = (7, 4)
    df.plot.bar(stacked=True)
    plt.xticks(rotation=45)
    plt.ylabel('管理规模(亿元)')
    plt.xlabel('报告期')
    plt.title(company + ' 各类型基金管理规模')
    plt.show()

    df_now = df.tail(1).T
    df_now.columns = ['aum']
    rank_now = rank.tail(1).T
    rank_now.columns = ['aum_rank']
    num_now = num.tail(1).T
    num_now.columns = ['aum_num']
    aum_now = pd.merge(df_now, rank_now, how='outer', left_index=True, right_index=True).round(2)
    aum_now = pd.merge(aum_now, num_now, how='outer', left_index=True, right_index=True).round(2)
    return aum_now

# ------------------------------------------------------
# 基金公司最新的股东列表及对应的持股比例
# ------------------------------------------------------
def visCompany_holderInfo(
        fundCompany,  # 基金公司
        chrome_path=None,           # the chrome.exe path
        local_path=None,            # the path you would like to save the image
        picture_name=None          # the name of the picture you want to save
):
    df = Comp.anlsCompany_getMFCurrentStakeHolder(fundCompany)
    if chrome_path is not None and local_path is not None and picture_name is not None:
        local_path = local_path + '/' + picture_name + '.png'
        dfi.export(df, local_path, chrome_path=chrome_path)
        return
    else:
        return df

# ------------------------------------------------------
# 基金公司管理规模测算，基于IPO询价数据
# ------------------------------------------------------
def visCompany_latestCompanyAUMLBfromIPOStats(
        fundCompany,                # 基金公司 ['衍复','诚奇']，输入的公司名字最好有唯一性，不然可能影响结果
        end_date = datetime.date.today(), # 月末数据可信度更高
        chrome_path=None,           # the chrome.exe path
        local_path=None,            # the path you would like to save the image
        picture_name=None          # the name of the picture you want to save
):
    start_date = datetime.date(end_date.year, end_date.month, 1)
    df = Comp.anlsCompany_getCompanyAUMLBfromIPOStats(fundCompany, start_date, end_date)
    date_latest = df['date'].max()
    result_latest = df.loc[df['date'] == date_latest].reset_index(drop=True)
    result_latest = result_latest.sort_values(['aum'], ascending=False).reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(15, 15 * 0.618))
    ax.bar(result_latest['company_name'], result_latest['aum'], label='规模(亿元)')
    ax.legend(loc='upper left')
    ax1 = ax.twinx()
    ax1.scatter(ax.get_xticks(), result_latest['confidence'], marker='^', color='black', label='Confidence', s=300)
    plt.title('量化私募规模预估' + date_latest.strftime("%Y%m%d"))
    ax1.legend(loc='upper right')
    plt.xticks(rotation=45)
    plt.show()
    if chrome_path is not None and local_path is not None and picture_name is not None:
        local_path = local_path + '/' + picture_name + '.png'
        dfi.export(result_latest, local_path, chrome_path=chrome_path)
        return
    else:
        return result_latest
