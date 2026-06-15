# -----------------------------------------------------------------------
# 主观多头私募分析可视化
# -----------------------------------------------------------------------

import pandas as pd
import numpy as np
import datetime
from matplotlib import pyplot as plt
from src.data.fundamentalFundData import *
from src.analysis.fundamentalFundAnalysis import *
from src.analysis.basicAnalysis import *
import altair as alt
from src.const import *
import src.config as config
from matplotlib .ticker import FuncFormatter
import seaborn as sns
alt.renderers.enable('notebook')

# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# 0. 主观多头核心库总览
# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# 1. 单一产品分析函数
# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------

# ------------------------------------------------------
# 某一产品的A股港股比例及产品nav时序图
# TS time series
# ------------------------------------------------------
def ffv_fundaAHShareAllocationTS(
    product_id,              # e.g. 'SQV392.OF'
    start_date,              # datetime.date
    end_date,
    AH = 'AH',               # str格式，'AH' A+H净仓位，'A' 只看A股仓位，'H' 只看港股仓位
    benchmark = '885001.WI'  # 基准指数 '000300.SH'等
):
    assert AH in ('AH', 'A', 'H'), "目前只支持'AH, 'A', 'H'"
    level_info = custHF.custHF_getProductInfo()
    id_to_name = level_info.set_index('product_id')['product_short_name'].to_dict()
    df = ffd_getFundamentalFundsExposure(start_date, end_date, [product_id])
    nav = basicAnal_returnToNav({'HF': [product_id]}, start_date, end_date, 'D', benchmark, 'Product')
    AH_dict = {
        'AH': ['date', 'net_stock'],
        'A':  ['date', 'a_stock'],
        'H':  ['date', 'hk_stock']
    }
    df = df[AH_dict[AH]]
    df = pd.merge(df, nav, on=['date'], how='left').sort_values(by='date').reset_index(drop=True)
    df[[product_id, benchmark]] /= df.loc[0, [product_id, benchmark]]
    df['date'] = pd.to_datetime(df['date'])
    melted = pd.melt(df[['date', product_id, benchmark]], id_vars='date', value_vars=[product_id, benchmark])
    base1 = alt.Chart(df, title=id_to_name[product_id] + ' 仓位及业绩表现').encode(
        alt.X('date', axis=alt.Axis(title=None, format='%Y/%m/%d'))
    )
    bar = base1.mark_bar(opacity=0.3, color='#57A44C').encode(
        alt.Y(AH_dict[AH][1], axis=alt.Axis(title=AH_dict[AH][1], titleColor='#57A44C', format='.0%')),
        tooltip=['date', {'field': AH_dict[AH][1], 'format': '.4f'}]
    )
    base2 = alt.Chart(melted).encode(
        alt.X('date', axis=alt.Axis(title=None, format='%Y/%m/%d'))
    )
    line = base2.mark_line( interpolate='monotone',clip=True).encode(
        alt.Y('value',axis=alt.Axis(title='Nav', titleColor='#5276A7'), scale=alt.Scale(domain=[melted['value'].min()*0.98, melted['value'].max()*1.02])),
        color = 'variable',
        tooltip=['date', {'field': 'value', 'format': '.4f'}]
    )
    Chart = alt.layer(bar, line).resolve_scale(
        y='independent'
    )
    return Chart.interactive()

# ------------------------------------------------------
# 某一产品的换手率-资产规模时序图
# TS time series
# ------------------------------------------------------
def ffv_fundaFundTurnOverTS(
    product_id,          # e.g. 'SQV392.OF'
    start_date,          # datetime.date
    end_date
):
    level_info = custHF.custHF_getProductInfo()
    id_to_name = level_info.set_index('product_id')['product_short_name'].to_dict()
    df = ffd_getFundamentalFundsExposure(start_date, end_date, [product_id])
    df = df[['date','turnover_near_one_month', 'turnover_near_one_year','net_asset_val']]
    df['turnover_near_one_month'] *= 12
    df['net_asset_val'] /= 1e8
    df['date'] = pd.to_datetime(df['date'])
    melted = pd.melt(df[['date', 'turnover_near_one_month', 'turnover_near_one_year']], id_vars='date', value_vars=['turnover_near_one_month', 'turnover_near_one_year'])
    base1 = alt.Chart(df, title=id_to_name[product_id] + ' 换手率及资产规模').encode(
        alt.X('date', axis=alt.Axis(title=None, format='%Y/%m/%d'))
    )
    bar = base1.mark_bar(opacity=0.3, color='#57A44C').encode(
        alt.Y('net_asset_val', axis=alt.Axis(title='net_asset_val', titleColor='#57A44C', format='.0%')),
        tooltip=['date', {'field': 'net_asset_val', 'format': '.4f'}]
    )
    base2 = alt.Chart(melted).encode(
        alt.X('date', axis=alt.Axis(title=None, format='%Y/%m/%d'))
    )
    line = base2.mark_line(interpolate='monotone').encode(
        alt.Y('value', axis=alt.Axis(title='Nav', titleColor='#5276A7')),
        color='variable',
        tooltip=['date', {'field': 'value', 'format': '.4f'}]
    )
    Chart = alt.layer(bar, line).resolve_scale(
        y='independent'
    )
    return Chart.interactive()

# ------------------------------------------------------
# 某一产品的前N大行业集中度时序图
# ------------------------------------------------------
def ffv_fundaFundTopNIndustryCRTS(
    product_id,          # e.g. 'SQV392.OF'
    start_date,          # datetime.date
    end_date,
    N = 3,               # 前三大行业
    AH = 'AH'            # 'AH'代表A股港股合并在一起看，'A'代表只看A股行业，'H’代表只看港股行业
):
    assert AH in ('AH', 'A', 'H'), "目前只支持'AH, 'A', 'H'"
    level_info = custHF.custHF_getProductInfo()
    id_to_name = level_info.set_index('product_id')['product_short_name'].to_dict()
    df = ffa_fundaFundTopNIndustryCRTS(product_id, start_date, end_date, N, AH)
    df['date'] = pd.to_datetime(df['date'])
    base = alt.Chart(df, title=id_to_name[product_id] + ' 前'+str(N)+'大'+AH+'行业占资产净值比').encode(
        alt.X('date', axis=alt.Axis(title=None, format='%Y/%m/%d'))
    )
    line = base.mark_line(color='#57A44C').encode(
        alt.Y('weight', axis=alt.Axis(title='占资产净值比例', titleColor='#57A44C', format='.0%')),
        tooltip=['date', 'weight']
    )
    Chart = line
    return Chart.interactive()

# ------------------------------------------------------
# 某一产品的风格时序图
# ------------------------------------------------------
def ffv_fundaFundStyleTS(
    product_id,          # e.g. 'SQV392.OF'
    start_date,          # datetime.date
    end_date
):
    level_info = custHF.custHF_getProductInfo()
    id_to_name = level_info.set_index('product_id')['product_short_name'].to_dict()
    df = ffd_getFundamentalFundsExposure(start_date, end_date, [product_id])
    style = pd.DataFrame({'chinese': const.STYLE_NAME_CN_TO_EN.keys(),
                                'english': const.STYLE_NAME_CN_TO_EN.values()})
    dic_style = dict(zip(style['english'], style['chinese']))
    df = df[['date'] + list(style['english'])].rename(columns=dic_style)
    melted = pd.melt(df, id_vars='date',
                     value_vars=list(style['chinese'])).rename(
        columns={'variable': 'style', 'value': 'weight'})
    melted['date'] = pd.to_datetime(melted['date'])
    Chart = alt.Chart(melted, title=id_to_name[product_id] + ' 风格分布').mark_area().encode(
        x = 'date',
        y = alt.Y('weight', stack='normalize'),
        color = 'style',
        tooltip=['date', 'style', {'field': 'weight', 'format': '.4f'}]
    )
    return Chart.interactive()

# ------------------------------------------------------
# 某一产品的前N大行业截面图
# ------------------------------------------------------
def ffa_fundaTopNIndustryCS(
    product_id,          # e.g. 'SQV392.OF'
    date,                # datetime.date
    N = 5,               # 前N大行业
    AH = 'AH'            # 'AH'代表A股港股合并在一起看，'A'代表只看A股行业，'H’代表只看港股行业
):
    assert AH in ('AH', 'A', 'H'), "目前只支持'AH, 'A', 'H'"
    level_info = custHF.custHF_getProductInfo()
    id_to_name = level_info.set_index('product_id')['product_short_name'].to_dict()
    df = ffa_fundaTopNIndustryTS(product_id, date, date, N, AH)
    dict_industry = _industryDictionary()
    df.replace({'industry': dict_industry}, inplace=True)
    del df['date']
    Chart = alt.Chart(df, title=id_to_name[product_id] + ' 前'+str(N)+'大'+AH+'行业 ' + date.strftime('%Y%m%d')).mark_bar().encode(
        x='sum(weight)',
        y=alt.Y('industry', sort='-x'),
        tooltip = ['industry', 'weight']
    )

    return Chart.interactive()

# ------------------------------------------------------
# 某一产品的AH仓位/行业变化截面图
# threshhold用于行业，变动大于这个阈值的行业才会显示
# ------------------------------------------------------
def ffv_fundaFundPositionIndustryChg(
    product_id,          # e.g. 'SQV392.OF'
    date1,               # datetime.date 开始时点
    date2,               # 结束时点
    AH = 'AH',           # 'AH' 看A+H行业，'A' 只看A股行业，'H' 只看港股行业
    industry = True,     # True 看行业，False看仓位
    threshhold = 0.05    # 阈值
):
    assert AH in ('AH', 'A', 'H'), "目前只支持'AH, 'A', 'H'"
    level_info = custHF.custHF_getProductInfo()
    id_to_name = level_info.set_index('product_id')['product_short_name'].to_dict()
    df = ffa_fundaFundPositionIndustryChg(product_id, date1, date2, AH, industry, threshhold)
    dict_industry = _industryDictionary()
    df.replace({'industry': dict_industry}, inplace=True)
    if industry:
        melted = pd.melt(df, id_vars='industry',
                         value_vars=['weight_start', 'weight_end' ,'weight_change']).rename(
            columns={'variable': 'class', 'value': 'weight'})
        Chart = alt.Chart(melted, title=id_to_name[product_id] + ' ' + AH + ' 行业变动情况 ' + date1.strftime('%Y%m%d') + '-' + date2.strftime('%Y%m%d')).mark_bar().encode(
            x='class',
            y='weight',
            column = 'industry',
            color = 'class',
            tooltip = ['industry', 'weight', 'class']
        )
    else:
        melted = pd.melt(df,
                         value_vars=['net_stock_start', 'net_stock_end' ,'net_stock_chg']).rename(
            columns={'variable': 'class', 'value': 'weight'})
        Chart = alt.Chart(melted, title=id_to_name[product_id] + ' 股票净仓位变动情况 ' + date1.strftime('%Y%m%d') + '-' + date2.strftime('%Y%m%d')).mark_bar().encode(
            x='class',
            y='weight',
            color='class',
            tooltip = ['class', 'weight']
        )

    return Chart.interactive()

# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# 2. 全部多头产品合并分析
# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------

# ------------------------------------------------------
# 全部多头产品仓位变化
# ------------------------------------------------------
def ffv_fundaFundAllProductsPositionChgCount(
    date1,           # datetime.date
    date2,
    threshhold=0.05  # 阈值，评判是否加减仓的值
):
    df_AH = ffa_fundaFundAllProductsPositionChgCount(date1, date2, 'AH', threshhold)
    df_A = ffa_fundaFundAllProductsPositionChgCount(date1, date2, 'A', threshhold)
    df_H = ffa_fundaFundAllProductsPositionChgCount(date1, date2, 'H', threshhold)
    df = df_AH.append(df_A).append(df_H).reset_index(drop=True)
    df.rename(columns={'chg':'仓位变化方向','product_count':'产品数量','avg_change':'平均变动','start_date':'开始日期','end_date':'结束日期','position':'市场'}, inplace=True)
    df = df.style.format({'平均变动': '{:.2%}'})
    return df

# ------------------------------------------------------
# 全部多头产品仓位变化
# ------------------------------------------------------
def ffv_fundaFundAllProductsPositionChgStats(
    date1,              # datetime.date
    date2
):
    df_AH = ffa_fundaFundAllProductsPositionChgStats(date1, date2, 'AH')
    df_A = ffa_fundaFundAllProductsPositionChgStats(date1, date2, 'A')
    df_H = ffa_fundaFundAllProductsPositionChgStats(date1, date2, 'H')
    df = df_AH.append(df_A).append(df_H).reset_index(drop=True)
    df1 = df.iloc[[0, 2, 4], :].reset_index(drop=True).drop('position',axis=1).rename(columns={'mean':'期初均值','median':'期初中位数','max':'期初最大值','min':'期初最小值','date':'期初日期'})
    df2 = df.iloc[[1, 3, 5], :].reset_index(drop=True).rename(columns={'mean':'期末均值','median':'期末中位数','max':'期末最大值','min':'期末最小值','date':'期末日期','position':'市场'})
    chg = pd.DataFrame(columns=['均值变化','中位数变化'])
    chg['均值变化'] = df2['期末均值']-df1['期初均值']
    chg['中位数变化'] = df2['期末中位数'] - df1['期初中位数']
    result = pd.concat([chg, df1, df2], axis=1)
    result = result.style.format({'均值变化': '{:.2%}', '中位数变化': '{:.2%}', '期初均值': '{:.2%}', '期初中位数': '{:.2%}', '期初最大值': '{:.2%}', '期初最小值': '{:.2%}','期末均值': '{:.2%}', '期末中位数': '{:.2%}', '期末最大值': '{:.2%}', '期末最小值': '{:.2%}'})
    return result

# ------------------------------------------------------
# 全部多头产品仓位detail
# ------------------------------------------------------
def ffv_fundaFundAllProductsPositionDetails(
    date                # datetime.date
):
    df = ffa_fundaFundAllProductsPositionWRank(date)
    df.rename(columns={'product_name':'产品名称','net_stock':'净仓位','net_stock_rank':'净仓位排名'
        ,'a_stock':'A股仓位','a_stock_rank':'A股仓位排名','hk_stock':'港股仓位','hk_stock_rank':'港股仓位排名'}, inplace=True)
    df = df.style.format({'净仓位': '{:.2%}', 'A股仓位': '{:.2%}', '港股仓位': '{:.2%}','净仓位排名': '{:.0f}', 'A股仓位排名': '{:.0f}', '港股仓位排名': '{:.0f}'}).background_gradient(subset=['净仓位','A股仓位','港股仓位'], cmap='Reds', low=0, high=config.cmap_range_adjust_coef)
    return df

# ------------------------------------------------------
# 全部多头产品仓位变化
# ------------------------------------------------------
def ffv_fundaFundAllProductsPositionChgDetails(
    date1,              # datetime.date
    date2
):
    df = ffa_fundaFundAllProductsPositionChgDetails(date1, date2)
    df.rename(columns={'product_name': '产品名称', 'net_stock_chg': '净仓位变动', 'net_stock_chg_rank': '净仓位变动排名'
        , 'a_stock_chg': 'A股仓位变动', 'a_stock_chg_rank': 'A股仓位变动排名', 'hk_stock_chg': '港股仓位变动', 'hk_stock_chg_rank': '港股仓位变动排名'}, inplace=True)
    df = df.style.format({'净仓位变动': '{:.2%}', 'A股仓位变动': '{:.2%}', '港股仓位变动': '{:.2%}','净仓位变动排名': '{:.0f}', 'A股仓位变动排名': '{:.0f}', '港股仓位变动排名': '{:.0f}'}).background_gradient(subset=['净仓位变动','A股仓位变动','港股仓位变动'], cmap='Reds', low=0, high=config.cmap_range_adjust_coef)
    return df

# ------------------------------------------------------
# 全部多头产品仓位相对于历史中枢仓位的变化情况
# ------------------------------------------------------
def ffv_fundaFundAllProductsPositionChgVSHistoryMedian(
    date,               # datetime.date，最新数据日期
    AH='AH',            # 'AH'代表全部仓位, 'A'代表A股仓位, 'H'代表港股仓位
    look_back_weeks=4   # 回看周数，默认回看4周

):
    df = ffa_fundaFundAllProductsPositionChgVSHistoryMedian(date, AH, look_back_weeks)
    df = df.sort_values(by='history_median', ascending=False).reset_index(drop=True)
    df.rename(columns={'date': '数据截止日期', 'product_id': '产品ID', 'product_name': '产品名称', 'AH': '仓位数据类型', 'history_median': '历史仓位中位数'}, inplace=True)
    def _update_col_name(x):
        if 'position' in x:
            if 'diff' in x:
                return x.split('_')[0]+'仓位偏离'
            else:
                return x.split('_')[0]+'仓位'
        else:
            return x
    col_list = [_update_col_name(col) for col in df.columns]
    num_col_list = col_list[4:]
    position_num_col_list = [col for col in num_col_list if '偏离' not in col]
    diff_num_col_list = [col for col in num_col_list if '偏离' in col]
    df.columns = col_list
    new_cmap = sns.diverging_palette(**config.cmap_kwargs)
    df = df.style.format({num_col: '{:.2%}' for num_col in num_col_list}).background_gradient(subset=position_num_col_list, cmap='Reds', low=0, high=config.cmap_range_adjust_coef).\
        background_gradient(subset=diff_num_col_list, cmap=new_cmap, axis=0, vmin=-0.5, vmax=0.5).highlight_null('white')
    return df

# ------------------------------------------------------
# 全部多头产品前N大行业或前N大变化行业的detail
# 可以看加仓的，也可以看减仓的
# ------------------------------------------------------
def ffv_fundaFundAllProductsTopIndustryDetails(
    date1,           # datetime.date
    date2,           # if abs_pos=True, date1=date2
    abs_pos = True,  # True 绝对仓位， False 变化
    add_pos = True,  # True是加仓，False是减仓
    AH = 'AH',       # 'AH' A股港股行业合并计算，'A' 只看A股行业，'H'只看港股行业
    N = 3            # 前N大行业
):
    assert AH in ('AH', 'A', 'H'), "目前只支持'AH, 'A', 'H'"
    dict_industry = _industryDictionary()
    dict_weight = {
        True: 'weight',
        False: 'weight_change'
    }
    if abs_pos:
        assert date1 == date2, "如果选择abs_pos 绝对仓位，date1必须等于date2"
        df = ffa_fundaFundAllProductsTopIndustryDetails(date1, AH, N)
    else:
        df = ffa_fundaFundAllProductsTopIndustryChgDetails(date1, date2, AH, N, add_pos)
    df.replace({'industry': dict_industry}, inplace=True)
    # pivot table 用于展示
    df['industry_rank'] = pd.DataFrame(['第一大行业','第二大行业','第三大行业'] * len(df['product_name'].unique()))
    df['weight_rank'] = pd.DataFrame(['第一大行业权重', '第二大行业权重', '第三大行业权重'] * len(df['product_name'].unique()))
    result_industry = pd.pivot_table(df, index='product_name', values='industry',columns='industry_rank', aggfunc='first')
    result_weight = pd.pivot_table(df, index='product_name', values=dict_weight[abs_pos], columns='weight_rank')
    result = result_industry.join(result_weight)
    result = result[['第一大行业','第一大行业权重','第二大行业','第二大行业权重','第三大行业','第三大行业权重']]
    result = result.style.format({'第一大行业权重': '{:.2%}','第二大行业权重': '{:.2%}','第三大行业权重': '{:.2%}'}).background_gradient(subset=['第一大行业权重', '第二大行业权重', '第三大行业权重'], cmap='Reds', low=0, high=config.cmap_range_adjust_coef)
    return result

# ------------------------------------------------------
# 全部多头产品行业变化汇总
# ------------------------------------------------------
def ffv_fundaFundAllProductsIndustryChgbyManager(
    date1,     # datetime.date
    date2,
    AH = 'AH',  # 'AH' A股港股行业合并计算，'A' 只看A股行业，'H'只看港股行业
    global_mode=False,  # 全局模式，默认关闭，只对比持有该行业产品的仓位均值变化；打开全局模式后，取所有跟踪产品的整体均值进行对比
):
    assert AH in ('AH', 'A', 'H'), "目前只支持'AH, 'A', 'H'"
    df = ffa_fundaFundAllProductsIndustryChgbyManager(date1, date2, AH, global_mode)
    if global_mode:
        df = df[['industry', 'mean_change', 'mean_end', 'mean_start', 'count_end', 'count_start']]
    else:
        df = df[['industry', 'mean_change', 'mean_end', 'mean_start', 'count_change', 'count_end', 'count_start']]
    dict_industry = _industryDictionary()
    df.replace({'industry': dict_industry}, inplace=True)
    df.rename(columns={'industry':'行业','mean_change':'平均变动','mean_end':'期末均值','mean_start':'期初均值',
                       'count_change':'管理人变动数量','count_end':'期末管理人数','count_start':'期初管理人数'}, inplace=True)
    df = df.style.format({'期初均值': '{:.2%}', '期末均值': '{:.2%}', '平均变动': '{:.2%}',
                          '期初管理人数': '{:.0f}', '期末管理人数': '{:.0f}', '管理人变动数量': '{:.0f}'}).background_gradient(cmap='Reds', low=0, high=config.cmap_range_adjust_coef)
    return df

# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# 3. 基于多头产品绩效数据、持仓数据绘制图表的工具函数
# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------------
# 基于多头产品绩效数据的绘图工具函数
# 输出包括 区间收益率-年化波动率散点图 最大回撤-年化波动率散点图 最大回撤-年化波动率-区间收益率气泡图
# -----------------------------------------------------------------------------------
def ffv_fundaFundPerformanceScatter(
    data        # 绩效表格数据，来自basicVis_PerformanceStats
):
    fig1 = plt.figure(figsize=(10, 5))
    fig1.set_dpi(100)
    ax1 = fig1.add_subplot(111)
    ax1.scatter(data['年化波动率'], data['区间收益率'], marker='o', color='blue')
    plt.xlabel("年化波动率")
    plt.ylabel("区间收益率")
    ax1.set_title('区间收益率-年化波动率')
    for i, label in enumerate(data['名称']):
        plt.annotate(label, (data['年化波动率'][i], data['区间收益率'][i]))
    # 数轴tick百分数展示
    plt.gca().xaxis.set_major_formatter(FuncFormatter(lambda x, y: '%1.0f' % (x*100) + '%'))
    plt.gca().yaxis.set_major_formatter(FuncFormatter(lambda x, y: '%1.0f' % (x*100) + '%'))
    fig1

    fig2 = plt.figure(figsize=(10, 5))
    fig2.set_dpi(100)
    ax2 = fig2.add_subplot(111)
    ax2.scatter(data['年化波动率'], data['最大回撤'], marker='o', color='blue')
    plt.xlabel("年化波动率")
    plt.ylabel("最大回撤")
    ax2.set_title('最大回撤-年化波动率')
    for i, label in enumerate(data['名称']):
        plt.annotate(label, (data['年化波动率'][i], data['最大回撤'][i]))
    # 数轴tick百分数展示
    plt.gca().xaxis.set_major_formatter(FuncFormatter(lambda x, y: '%1.0f' % (x*100) + '%'))
    plt.gca().yaxis.set_major_formatter(FuncFormatter(lambda x, y: '%1.0f' % (x*100) + '%'))
    fig2

    fig3 = plt.figure(figsize=(10, 5))
    fig3.set_dpi(100)
    ax3 = fig3.add_subplot(111)
    data['区间收益率'] = data['区间收益率'].astype(float)
    # 正收益
    ax3.scatter(data[data['区间收益率'] >= 0]['年化波动率'], data[data['区间收益率'] >= 0]['最大回撤'], s=data[data['区间收益率'] >= 0]['区间收益率']*10000, marker='o', color='blue', alpha=0.3)
    # 负收益
    ax3.scatter(data[data['区间收益率'] < 0]['年化波动率'], data[data['区间收益率'] < 0]['最大回撤'], s=data[data['区间收益率'] < 0]['区间收益率']*(-10000), marker='o', color='grey', alpha=0.5)
    plt.xlabel("年化波动率")
    plt.ylabel("最大回撤")
    ax3.set_title('最大回撤-年化波动率-区间收益率')
    plt.ylim([data['最大回撤'].astype(float).min()*1.1, 0])
    for i, label in enumerate(data['名称']):
        plt.annotate(label, (data['年化波动率'][i], data['最大回撤'][i]))
    # 数轴tick百分数展示
    plt.gca().xaxis.set_major_formatter(FuncFormatter(lambda x, y: '%1.0f' % (x*100) + '%'))
    plt.gca().yaxis.set_major_formatter(FuncFormatter(lambda x, y: '%1.0f' % (x*100) + '%'))
    fig3


# -----------------------------------------------------------------------------------
# 基于多头产品绩效排名数据的绘图制表工具函数
# 输出包括 分位数表现统计表，降序分位数面积图
# -----------------------------------------------------------------------------------
def ffv_fundaFundRankPerformanceChart(
    data        # 绩效表格数据，来自basicVis_PerformanceStats with strategy_category 排名
):
    data['收益率排名'] = data['收益率排名'].astype(float)
    quantile_map={
        '前10%': [0.9, 1],
        '前25%': [0.75, 1],
        '前50%': [0.5, 1],
        '后25%': [0, 0.25],
        '后10%': [0, 0.1]
    }
    fig1 = plt.figure(figsize=(10, 5))
    fig1.set_dpi(100)
    ax1 = fig1.add_subplot(111)
    ax1.fill_between(data['名称'], data['收益率排名'], color='pink', alpha=0.5)
    ax1.plot(data['名称'], (data.index.max() - np.array(data.index.to_list()))/data.index.max(), color="blue")
    plt.xlabel("产品", )
    plt.ylabel("全市场排名分位数")
    plt.xticks(rotation=60)
    ax1.set_title('全市场业绩排名分位数')
    # 数轴tick百分数展示
    plt.gca().yaxis.set_major_formatter(FuncFormatter(lambda x, y: '%1.0f' % (x*100) + '%'))
    fig1

    result = pd.DataFrame(columns=['分位数', '数量', '占比'])
    for key, value in quantile_map.items():
        key_num = len(data[(data['收益率排名'] >= value[0]) & (data['收益率排名'] <= value[1])])
        result = result.append({'分位数': key, '数量': key_num, '占比': key_num / len(data)}, ignore_index=True)
    result = result.append({'分位数': '合计', '数量': len(data), '占比': np.nan}, ignore_index=True)
    result['占比'] = result['占比'].astype(float)
    formatter = {'占比': "{:.2%}"}
    result = result.style.format(formatter).highlight_null('white').hide_index()

    return result


# -----------------------------------------------------------------------------------
# 基于多头产品行业持仓数据的散点图函数
# 输出包括  行业期末总仓位-行业期末管理人数散点图  行业平均变动-管理人变动数量散点图
# -----------------------------------------------------------------------------------
def ffv_fundaFundIndustryScatter(
    data        # 行业月度变化数据，来自ffv_fundaFundAllProductsIndustryChgbyManager
):
    data[['平均变动', '期末均值', '期末管理人数']] = data[['平均变动', '期末均值', '期末管理人数']].astype(float)
    data['期末总仓位'] = data['期末均值'] * data['期末管理人数']
    fig1 = plt.figure(figsize=(10, 5))
    fig1.set_dpi(100)
    ax1 = fig1.add_subplot(111)
    ax1.scatter(data['期末总仓位'], data['期末管理人数'], marker='o', color='blue', alpha=0.8)
    plt.xlabel("期末总仓位")
    plt.ylabel("期末管理人数")
    ax1.set_title('行业总权重')
    for i, label in enumerate(data['行业']):
        plt.annotate(label, (data['期末总仓位'][i], data['期末管理人数'][i]))
    # 数轴tick百分数展示
    plt.gca().xaxis.set_major_formatter(FuncFormatter(lambda x, y: '%1.0f' % (x*100) + '%'))
    fig1

    fig2 = plt.figure(figsize=(10, 5))
    fig2.set_dpi(100)
    ax2 = fig2.add_subplot(111)
    ax2.scatter(data['平均变动'], data['管理人变动数量'], marker='o', color='blue', alpha=0.8)
    plt.xlabel("平均变动")
    plt.ylabel("管理人变动数量")
    ax2.set_title('行业平均变动')
    for i, label in enumerate(data['行业']):
        plt.annotate(label, (data['平均变动'][i], data['管理人变动数量'][i]))
    # 数轴tick百分数展示
    plt.gca().xaxis.set_major_formatter(FuncFormatter(lambda x, y: '%1.0f' % (x*100) + '%'))
    fig2

# -----------------------------------------------------------------------------------
# 基于多头产品AH持仓数据的散点图函数
# 输出  A股仓位-净仓位散点图 港股仓位-净仓位散点图
# -----------------------------------------------------------------------------------
def ffv_fundaFundAHPositionScatter(
    data        # 产品AH持仓数据，来自ffv_fundaFundAllProductsPositionDetails
):
    fig1 = plt.figure(figsize=(10, 5))
    fig1.set_dpi(100)
    ax1 = fig1.add_subplot(111)
    ax1.scatter(data['A股仓位'], data['净仓位'], marker='o', color='blue', alpha=0.8)
    plt.xlabel("A股仓位")
    plt.ylabel("净仓位")
    ax1.set_title('产品净仓位情况')
    plt.xlim([-0.1, data['A股仓位'].astype(float).max()*1.1])
    plt.ylim([-0.1, data['净仓位'].astype(float).max()*1.1])
    for i, label in enumerate(data['产品名称']):
        plt.annotate(label, (data['A股仓位'][i], data['净仓位'][i]))
    # 数轴tick百分数展示
    plt.gca().xaxis.set_major_formatter(FuncFormatter(lambda x, y: '%1.0f' % (x*100) + '%'))
    plt.gca().yaxis.set_major_formatter(FuncFormatter(lambda x, y: '%1.0f' % (x*100) + '%'))
    fig1

    fig2 = plt.figure(figsize=(10, 5))
    fig2.set_dpi(100)
    ax2 = fig2.add_subplot(111)
    ax2.scatter(data['港股仓位'], data['净仓位'], marker='o', color='blue', alpha=0.8)
    plt.xlabel("港股仓位")
    plt.ylabel("净仓位")
    ax2.set_title('产品净仓位情况')
    plt.xlim([-0.1, data['港股仓位'].astype(float).max()*1.1])
    plt.ylim([-0.1, data['净仓位'].astype(float).max()*1.1])
    for i, label in enumerate(data['产品名称']):
        plt.annotate(label, (data['港股仓位'][i], data['净仓位'][i]))
    # 数轴tick百分数展示
    plt.gca().xaxis.set_major_formatter(FuncFormatter(lambda x, y: '%1.0f' % (x*100) + '%'))
    plt.gca().yaxis.set_major_formatter(FuncFormatter(lambda x, y: '%1.0f' % (x*100) + '%'))
    fig2

# -----------------------------------------------------------------------------------
# 基于多头产品AH仓位变动的气泡图函数
# 输出  A股仓位变动-净仓位变动散点图 港股仓位变动-净仓位变动散点图
# -----------------------------------------------------------------------------------
def ffv_fundaFundAHPositionChgScatter(
    data        # 产品AH仓位变动数据，来自ffv_fundaFundAllProductsPositionChgDetails
):
    fig1 = plt.figure(figsize=(10, 5))
    fig1.set_dpi(100)
    ax1 = fig1.add_subplot(111)
    # 正变动
    ax1.scatter(data['A股仓位变动'], data['净仓位变动'], marker='o', color='blue', alpha=0.8)
    plt.xlabel("A股仓位变动")
    plt.ylabel("净仓位变动")
    ax1.set_title('净仓位变动情况')
    plt.xlim([data['A股仓位变动'].astype(float).min()*1.1, data['A股仓位变动'].astype(float).max()*1.1])
    plt.ylim([data['净仓位变动'].astype(float).min()*1.1, data['净仓位变动'].astype(float).max()*1.1])
    for i, label in enumerate(data['产品名称']):
        plt.annotate(label, (data['A股仓位变动'][i], data['净仓位变动'][i]))
    # 数轴tick百分数展示
    plt.gca().xaxis.set_major_formatter(FuncFormatter(lambda x, y: '%1.0f' % (x*100) + '%'))
    plt.gca().yaxis.set_major_formatter(FuncFormatter(lambda x, y: '%1.0f' % (x*100) + '%'))
    fig1

    fig2 = plt.figure(figsize=(10, 5))
    fig2.set_dpi(100)
    ax2 = fig2.add_subplot(111)
    # 正变动
    ax2.scatter(data['港股仓位变动'], data['净仓位变动'], marker='o', color='blue', alpha=0.8)
    plt.xlabel("港股仓位变动")
    plt.ylabel("净仓位变动")
    ax2.set_title('净仓位变动情况')
    plt.xlim([data['港股仓位变动'].astype(float).min()*1.1, data['港股仓位变动'].astype(float).max()*1.1])
    plt.ylim([data['净仓位变动'].astype(float).min()*1.1, data['净仓位变动'].astype(float).max()*1.1])
    for i, label in enumerate(data['产品名称']):
        plt.annotate(label, (data['港股仓位变动'][i], data['净仓位变动'][i]))
    # 数轴tick百分数展示
    plt.gca().xaxis.set_major_formatter(FuncFormatter(lambda x, y: '%1.0f' % (x*100) + '%'))
    plt.gca().yaxis.set_major_formatter(FuncFormatter(lambda x, y: '%1.0f' % (x*100) + '%'))
    fig2


# -----------------------------------------------------------------------------------
# 多头产品各二级分类策略绩效气泡图函数
# 输出  区间收益率-最大回撤-年化波动率气泡图
# -----------------------------------------------------------------------------------
def ffv_fundaFundLevelTwoStrategyPerformanceBubble(
    data        # 各二级分类策略绩效表格，来自basicVis_PerformanceStats
):
    data['年化波动率'] = data['年化波动率'].astype(float)
    fig1 = plt.figure(figsize=(10, 5))
    fig1.set_dpi(100)
    ax1 = fig1.add_subplot(111)
    ax1.scatter(data['区间收益率'], data['最大回撤'], s=data['年化波动率']*10000, marker='o', color='blue', alpha=0.3)
    plt.xlabel("区间收益率")
    plt.ylabel("最大回撤")
    ax1.set_title('区间收益率-最大回撤-年化波动率')
    for i, label in enumerate(data['名称']):
        plt.annotate(label, (data['区间收益率'][i], data['最大回撤'][i]))
    plt.ylim([data['最大回撤'].astype(float).min()*1.1, 0])
    # 数轴tick百分数展示
    plt.gca().xaxis.set_major_formatter(FuncFormatter(lambda x, y: '%1.0f' % (x*100) + '%'))
    plt.gca().yaxis.set_major_formatter(FuncFormatter(lambda x, y: '%1.0f' % (x*100) + '%'))
    fig1


# -----------------------------------------------------------------------------------
# 多头产品各二级分类策略月度收益箱线图函数
# 输出  月度收益箱线图
# -----------------------------------------------------------------------------------
def ffv_fundaFundLevelTwoStrategyMReturnBoxplot(
    data        # 各二级分类策略月度收益表格，来自basicVis_HFMonthlyReturn
):
    data = data.T.astype(float).fillna(0)  # 数据不完整时存在nan值导致箱线图不显示，故将nan赋为0
    fig1 = plt.figure(figsize=(10, 5))
    fig1.set_dpi(100)
    ax1 = fig1.add_subplot(111)
    ax1.boxplot(data, showmeans=True, showcaps=True, showbox=True, showfliers=True, patch_artist=True, boxprops={'color': 'lightgrey', 'facecolor': 'lightgrey'})
    ax1.set_title('月收益分布')
    plt.xticks([i for i in range(1, 1+len(data.columns))], data.columns.to_list(), rotation=45)
    # 数轴tick百分数展示
    plt.gca().yaxis.set_major_formatter(FuncFormatter(lambda x, y: '%1.0f' % (x*100) + '%'))
    fig1


# ------------------------------------------------------
# 全部多头产品仓位平均数变化时序图
# ------------------------------------------------------
def ffv_fundaFundAllProductsAvgPositionTS(
    start_date,              # datetime.date
    end_date,
    AH = 'AH'          # 'AH'代表全部仓位, 'A'代表A股仓位, 'H'代表港股仓位
):
    df = ffd_getFundamentalFundsExposure(start_date, end_date)[['date','product_id','a_stock','hk_stock','net_stock']]
    if AH == 'AH':
        # FIXME 加入数据过滤逻辑，筛去net_stock>150%的产品，主要剔除国债期货异动的影响
        df = df[df['net_stock'] < 1.5]
    AH_dict = {
        'AH': 'net_stock',
        'A': 'a_stock',
        'H': 'hk_stock'
    }
    df = df[['date','product_id',AH_dict[AH]]]
    df = df.groupby('date', as_index=False)[AH_dict[AH]].mean()
    df['date'] = pd.to_datetime(df['date'])
    base = alt.Chart(df, title='全部产品'+AH+'仓位平均变化').encode(
        alt.X('date', axis=alt.Axis(title=None, format='%Y/%m/%d'))
    )
    line = base.mark_line(color='#57A44C').encode(
        alt.Y(AH_dict[AH], axis=alt.Axis(title='占资产净值比例', titleColor='#57A44C', format='.0%')),
        tooltip=['date', AH_dict[AH]]
    )
    Chart = line
    return Chart.interactive()

# ------------------------------------------------------
# 全部多头产品仓位分位数变化时序图
# ------------------------------------------------------
def ffv_fundaFundAllProductsQuantilePositionTS(
    start_date,              # datetime.date
    end_date,
    AH = 'AH'          # 'AH'代表全部仓位, 'A'代表A股仓位, 'H'代表港股仓位
):
    df = ffd_getFundamentalFundsExposure(start_date, end_date)[['date', 'product_id', 'a_stock', 'hk_stock', 'net_stock']]
    if AH == 'AH':
        # FIXME 加入数据过滤逻辑，筛去net_stock>150%的产品，主要剔除国债期货异动的影响
        df = df[df['net_stock'] < 1.5]
    AH_dict = {
        'AH': 'net_stock',
        'A': 'a_stock',
        'H': 'hk_stock'
    }
    df = df[['date', 'product_id', AH_dict[AH]]]
    df['date'] = pd.to_datetime(df['date'])
    quantile_res = []
    for q in [0.1, 0.25, 0.5, 0.75, 0.9]:
        quantile_res.append(df.groupby(['date'])[AH_dict[AH]].quantile(q).rename('{:.0%}分位'.format(q)))
    melted = pd.melt(pd.concat(quantile_res, axis=1).reset_index(), id_vars=['date']).rename(columns={'variable': 'quantile_level', 'value': 'position'})
    c = alt.Chart(melted, title='全部产品'+AH+'仓位分位数变化').mark_line().encode(
        x=alt.X('date:T', title=None, axis=alt.Axis(format='%Y/%m/%d')),
        y=alt.Y('position', title='占资产净值比例', axis=alt.Axis(format='.0%'), scale=alt.Scale(domain=[0.98*melted['position'].abs().min(), 1.02*melted['position'].abs().max()])),
        color=alt.Color('quantile_level', title=None, sort='descending'),
        tooltip=['date', 'quantile_level', 'position']
    )
    return c.interactive()


# -------------------------------------- 私有函数 ----------------------------------------------------------- #

# ------------------------------------------------------
# 内部函数，生成AH行业中英文对照表
# ------------------------------------------------------
def _industryDictionary():
    sw_industry = pd.DataFrame({'chinese': const.SW_INDUSTRY_NAME_CN_TO_EN.keys(),
                                'english': const.SW_INDUSTRY_NAME_CN_TO_EN.values()})
    hk_industry = pd.DataFrame({'chinese': const.HK_INDUSTRY_NAME_CN_TO_EN.keys(),
                                'english': const.HK_INDUSTRY_NAME_CN_TO_EN.values()})
    dict_industry = dict(zip(sw_industry['english'].append(hk_industry['english']), sw_industry['chinese'].append(hk_industry['chinese'])))
    return dict_industry