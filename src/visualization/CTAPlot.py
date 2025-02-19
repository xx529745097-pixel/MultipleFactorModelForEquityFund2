# ------------------------------------------------
# 本文档用于CTA私募相关分析绘图
# ------------------------------------------------
import pandas as pd
import numpy as np
import altair as alt
import datetime
import matplotlib.pyplot as plt
import src.analysis.CTAanalysis as cta
import src.data.cta as ctaData
import src.analysis.basicAnalysis as basicAnal
import src.data.zyyx_cached as zyyx_cached
import src.data.custHF as custHF
import seaborn as sns
from itertools import chain
from src.const import *
from src.config import *
import src.config as config
import src.utils.fof_calendar as calendar
from dateutil.relativedelta import relativedelta

plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False
plt.style.use('ggplot')

# ------------------------------------------------------
# 期货品种分板块区间表现
# ------------------------------------------------------
def visCTA_FuturesIndexReturnBySection(
    start_date,  # 起始日期，输入格式:datetime.date
    end_date,  # 结束日期，输入格式:datetime.date
    section_dict  # dictionary e.g. {'螺纹钢':'RB.SHF'}
):
    futures_codelist = list(section_dict.values())
    read_bar = ctaData.cta_getFuturesContractDailyData(futures_codelist=futures_codelist,
                                                       start_date=start_date, end_date=end_date)
    settle = read_bar['settle']
    cum_ret = settle.loc[end_date] / settle.loc[start_date] - 1
    cum_ret = cum_ret.sort_values(ascending=False).reset_index()
    cum_ret.rename(columns={0: 'return'}, inplace=True)
    cum_ret['windcode'].replace(dict(zip(section_dict.values(), section_dict.keys())), inplace=True)
    bars = alt.Chart(cum_ret, title='品种周度涨跌幅%s-%s' % (start_date, end_date)).mark_bar().encode(
        alt.X('return', axis=alt.Axis(title='区间涨跌幅', format='.2%')),
        alt.Y('windcode', axis=alt.Axis(title='品种代码'), sort='-x'),
        tooltip=['windcode', 'return']
    )
    text = bars.mark_text(align='right', baseline='middle', dx=3).encode(
        text=alt.Text('return', format='.2%')
    )
    Chart = bars + text
    return Chart.interactive()

# ------------------------------------------------------
# 期货板块指数区间表现展示
# ------------------------------------------------------
def visCTA_FuturesSectionIndexPlot(
    start_date,  # 起始日期，输入格式:datetime.date
    end_date,  # 结束日期，输入格式:datetime.date
    local_path=None,  # the path you would like to save the image
    display_mode='pyplot'  # display mode,可选 pyplot，web，默认为pyplot，web网页调用altair绘图
):
    assert display_mode in ('pyplot','web'),"仅允许两种绘图模式"
    read_index_df = ctaData.cta_getFuturesIndexDailyData(list(const.FUTURES_IND_DICT.values()), start_date, end_date)
    index_df = read_index_df['close']
    std_idx_df = index_df / index_df.iloc[0]
    if display_mode=='pyplot':
        ax = std_idx_df.loc[:, const.FUTURES_IND_DICT.values()].plot(figsize=(12, 6.8),
                                                                     color=['red', 'yellow', 'orchid', 'brown',
                                                                            'green', 'silver', 'coral', 'wheat',
                                                                            'aqua', 'blueviolet', 'pink', 'navy',
                                                                            'gray'])
        ax.legend(const.FUTURES_IND_DICT.keys(), ncol=6, loc='upper left', fontsize=13.5)
        plt.xlabel('日期', fontsize=13)
        plt.xticks(fontsize=13)
        plt.yticks(fontsize=13)
        plt.tight_layout()
        if local_path is None:
            pass
        else:
            picture_name = '期货板块指数跟踪'  # the name of the picture you want to save
            plt.savefig('%s/%s.png' % (local_path, picture_name))
        return
    elif display_mode=='web':
        df = std_idx_df.rename(columns=dict(zip(const.FUTURES_IND_DICT.values(),const.FUTURES_IND_DICT.keys()))).reset_index()
        df=df.melt(id_vars='date',value_name='净值',var_name='板块')
        d_start=df['date'].min()
        d_end = df['date'].max()
        col_name='净值'
        selection = alt.selection_multi(fields=['板块'], bind='legend', name='板块')
        nearest = alt.selection_single(nearest=True, on='mouseover', empty='none')
        title_string = "期货板块指数跟踪" + d_start.strftime('%Y/%m/%d') + "-" + d_end.strftime('%Y/%m/%d')
        base = alt.Chart(df, title=title_string).mark_line().encode(
            x=alt.X('date:T', axis=alt.Axis(format='%Y/%m/%d')),
            y=alt.Y(col_name, scale=alt.Scale(domain=[df[col_name].min(), df[col_name].max()]), title=col_name),
            color=alt.Color('板块'),
            tooltip=['板块', 'date',{'field':col_name,'format':',.4f'}],
            opacity=alt.condition(selection, alt.value(1), alt.value(0.1))
        )
        point = base.mark_point().encode(
            opacity=alt.condition(nearest, alt.value(1), alt.value(0))
        ).add_selection(nearest)
        lines = base.add_selection(selection)
        chart = alt.layer(lines, point).interactive().configure_axisX(labelAngle=0)

        return chart


# ------------------------------------------------------
# 期货品种区间时序波动率展示
# ------------------------------------------------------
def visCTA_FuturesTimeSeriesVolPlot(
    start_date,  # 起始日期，输入格式:datetime.date
    end_date,  # 结束日期，输入格式:datetime.date
    window=20,  # 回看时间窗口，默认20个交易日
    local_path=None,  # the path you would like to save the image
    display_mode = 'pyplot'   # display mode,可选 pyplot，web，默认为pyplot，web网页调用altair绘图
):
    assert display_mode in ('pyplot','web'),"仅允许两种绘图模式"
    assert isinstance(start_date, datetime.date), "start_date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "end_date must be an instance of datetime.date"
    vol_df = cta.ctaAnls_getTimeSeriesVolatility(start_date-datetime.timedelta(days=window*3), end_date, window)
    vol_df=vol_df.loc[(vol_df.index>=start_date)&(vol_df.index<=end_date)]
    if display_mode == 'pyplot':
        ax = vol_df.plot(figsize=(12, 6))
        ax.legend(('时序波动率(等权)', '时序波动率(成交量加权)',), loc='upper left', fontsize=13.5)
        plt.xlabel('日期', fontsize=13)
        plt.xticks(fontsize=13)
        plt.yticks(fontsize=13)
        plt.tight_layout()
        if local_path is None:
            pass
        else:
            picture_name = '时序波动率跟踪'  # the name of the picture you want to save
            plt.savefig('%s\\%s.png' % (local_path, picture_name))
        return
    elif display_mode=='web':
        df = vol_df.rename(columns=dict(zip(['equal weighted', 'amount weighted'],['时序波动率(等权)', '时序波动率(成交量加权)']))).reset_index()
        df=df.melt(id_vars='date',value_name='波动率',var_name='加权方式')
        d_start=df['date'].min()
        d_end = df['date'].max()
        col_value='波动率'
        col_type='加权方式'
        selection = alt.selection_multi(fields=[col_type], bind='legend', name=col_type)
        nearest = alt.selection_single(nearest=True, on='mouseover', empty='none')
        title_string = "时序波动率" + d_start.strftime('%Y/%m/%d') + "-" + d_end.strftime('%Y/%m/%d')
        base = alt.Chart(df, title=title_string).mark_line().encode(
            x=alt.X('date:T', axis=alt.Axis(format='%Y/%m/%d')),
            y=alt.Y(col_value, scale=alt.Scale(domain=[df[col_value].min(), df[col_value].max()]), title=col_value),
            color=alt.Color(col_type),
            tooltip=[col_type, 'date', {'field':col_value,'format':',.4f'}],
            opacity=alt.condition(selection, alt.value(1), alt.value(0.1))
        )

        point = base.mark_point().encode(
            opacity=alt.condition(nearest, alt.value(1), alt.value(0))
        ).add_selection(nearest)
        lines = base.add_selection(selection)
        chart = alt.layer(lines, point).interactive().configure_axisX(labelAngle=0)

        return chart



# ------------------------------------------------------
# 期货品种区间时序波动率展示
# ------------------------------------------------------
def visCTA_FuturesCroSectionVolPlot(
    start_date,  # 起始日期，输入格式:datetime.date
    end_date,  # 结束日期，输入格式:datetime.date
    window=20,  # 回看时间窗口，默认20个交易日
    local_path=None,  # the path you would like to save the image
    display_mode = 'pyplot'   # display mode,可选 pyplot，web，默认为pyplot，web网页调用altair绘图
):
    assert display_mode in ('pyplot', 'web'), "仅允许两种绘图模式"
    assert isinstance(start_date, datetime.date), "start_date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "end_date must be an instance of datetime.date"
    vol_df = cta.ctaAnls_getCrossSectionVolatility(start_date-datetime.timedelta(days=window*3), end_date, window)
    vol_df=vol_df.loc[(vol_df.index>=start_date)&(vol_df.index<=end_date)]
    if display_mode=='pyplot':
        ax = vol_df.plot(figsize=(12,7))
        ax.legend(('全部品种', '黑色建材', '能源化工', '农产品', '油脂油料', '有色金属', '贵金属',),
                  ncol=7, loc='upper left', fontsize=12.5)
        plt.xlabel('日期', fontsize=13)
        plt.xticks(fontsize=13)
        plt.yticks(fontsize=13)
        plt.tight_layout()
        if local_path is None:
            pass
        else:
            picture_name = '截面波动率跟踪'  # the name of the picture you want to save
            plt.savefig('%s\\%s.png' % (local_path, picture_name))
        return
    elif display_mode=='web':
        dict_col_name=dict(zip(['all', 'black', 'chemistry', 'agriculture', 'oil', 'color', 'gold'],['全部品种', '黑色建材', '能源化工', '农产品', '油脂油料', '有色金属', '贵金属']))
        df=vol_df.rename(columns=dict_col_name).reset_index()
        df=df.melt(id_vars='date',value_name='截面波动率',var_name='板块')
        d_start=df['date'].min()
        d_end = df['date'].max()
        col_value='截面波动率'
        col_type='板块'
        selection = alt.selection_multi(fields=[col_type], bind='legend', name=col_type)
        nearest = alt.selection_single(nearest=True, on='mouseover', empty='none')
        title_string = "截面波动率" + d_start.strftime('%Y/%m/%d') + "-" + d_end.strftime('%Y/%m/%d')
        base = alt.Chart(df, title=title_string).mark_line().encode(
            x=alt.X('date:T', axis=alt.Axis(format='%Y/%m/%d')),
            y=alt.Y(col_value, scale=alt.Scale(domain=[df[col_value].min(), df[col_value].max()]), title=col_value),
            color=alt.Color(col_type),
            tooltip=[col_type, 'date',{'field':col_value,'format':',.4f'}],
            opacity=alt.condition(selection, alt.value(1), alt.value(0.1))
        )

        point = base.mark_point().encode(
            opacity=alt.condition(nearest, alt.value(1), alt.value(0))
        ).add_selection(nearest)
        lines = base.add_selection(selection)
        chart = alt.layer(lines, point).interactive().configure_axisX(labelAngle=0)

        return chart



# ------------------------------------------------------
# 期货板块量能分析展示
# ------------------------------------------------------
def visCTA_FuturesAmountPlot(
    start_date,  # 起始日期，输入格式:datetime.date
    end_date,  # 结束日期，输入格式:datetime.date
    window=5,  # 均线窗口，默认20个交易日
    ind_name_list=const.REGROUP_IND_DICT.keys(), # 重分类商品板块名, 输入格式:list
    local_path=None,  # the path you would like to save the image
    display_mode='pyplot'   # display mode,可选 pyplot，web，默认为pyplot，web为网页调用altair绘图
):
    assert display_mode in ('pyplot', 'web'), "仅允许两种绘图模式"
    if display_mode == 'pyplot':
        oi_df = cta.ctaAnls_getOpenInterestChange(start_date, end_date, ind_name_list, window=window)
        oi_df = oi_df.loc[(oi_df.index >= start_date) & (oi_df.index <= end_date)]
        oi_df.loc[:, '全部品种'] = oi_df.mean(axis=1)
        amount_df = cta.ctaAnls_getTransAmtChange(start_date, end_date, ind_name_list, window=window)
        amount_df = amount_df.loc[(amount_df.index >= start_date) & (amount_df.index <= end_date)]
        amount_df.loc[:, '全部品种'] = amount_df.mean(axis=1)
        fig = plt.figure(figsize=(7.6, 9.5))
        ax1 = fig.add_subplot(311)
        amount_df['全部品种'].plot(ax=ax1, ylabel='MA%s日线' % window, linewidth=1, color='red')
        axx = ax1.twinx()
        oi_df['全部品种'].plot(ax=axx, linewidth=1, color='blue')
        ax1.legend([ax1.get_lines()[0], axx.get_lines()[0]], ['成交量', '持仓量'])
        ax1.set_title('量能分析', fontsize=12)
        ax2 = fig.add_subplot(312)
        amount_df.iloc[:, :-1].plot(ax=ax2, ylabel='MA%s日线' % window,
                                    linewidth=1, color=['red', 'yellow', 'orchid', 'brown', 'green',
                                                        'silver', 'coral', 'wheat', 'aqua', 'blueviolet'])
        ax2.set_title('成交量变化(分板块)', fontsize=12)
        ax2.legend()
        ax3 = fig.add_subplot(313)
        oi_df.iloc[:, :-1].plot(ax=ax3, ylabel='MA%s日线' % window,
                                    linewidth=1, color=['red', 'yellow', 'orchid', 'brown', 'green',
                                                        'silver', 'coral', 'wheat', 'aqua', 'blueviolet'])
        ax3.set_title('持仓量变化(分板块)', fontsize=12)
        ax3.legend()
        fig.tight_layout()
        if local_path is None:
            pass
        else:
            picture_name = '量能分析'  # the name of the picture you want to save
            plt.savefig('%s\\%s.png' % (local_path, picture_name))
        return
    elif display_mode=='web':
        oi_df = cta.ctaAnls_getOpenInterestChange(start_date-datetime.timedelta(days=window*3), end_date, ind_name_list, window=window)
        oi_df = oi_df.loc[(oi_df.index >= start_date) & (oi_df.index <= end_date)]
        oi_df.loc[:, '持仓量'] = oi_df.mean(axis=1)
        amount_df = cta.ctaAnls_getTransAmtChange(start_date-datetime.timedelta(days=window*3), end_date, ind_name_list, window=window)
        amount_df = amount_df.loc[(amount_df.index >= start_date) & (amount_df.index <= end_date)]
        amount_df.loc[:, '成交量'] = amount_df.mean(axis=1)

        df=pd.concat([oi_df['持仓量'],amount_df['成交量']],axis=1).reset_index().melt(id_vars='date',value_name='value',var_name='type')
        selection = alt.selection_multi(fields=['type'], bind='legend', name='type')
        df['date']=pd.to_datetime(df['date']).dt.date
        d_start=df['date'].min()
        d_end = df['date'].max()
        title_string = '平均持仓量与平均成交量' + d_start.strftime('%Y/%m/%d') + "-" + d_end.strftime('%Y/%m/%d')
        base1 = alt.Chart(df,title=title_string).mark_line().encode(
            alt.Color('type:N',legend=alt.Legend(title='指标')),
            alt.X('date:T', axis=alt.Axis(format='%Y/%m/%d')),
        )
        line1=base1.transform_filter(alt.datum.type=='持仓量').encode(
            alt.Y('value',scale=alt.Scale(domain=[oi_df['持仓量'].min(), oi_df['持仓量'].max()]),title='持仓量'),
            tooltip=['type', 'date', {'field':'value','format':',.2f'}],
            opacity=alt.condition(selection, alt.value(1), alt.value(0.1))
            )
        line2 = base1.transform_filter(alt.datum.type == '成交量').encode(
            alt.Y('value',scale=alt.Scale(domain=[amount_df['成交量'].min(), amount_df['成交量'].max()]),title='成交量'),
            tooltip=['type', 'date', {'field':'value','format':',.2f'}],
            opacity=alt.condition(selection, alt.value(1), alt.value(0.1))
        )
        chart0=alt.layer(line1,line2).resolve_scale(y='independent')

        chart1=chart0.add_selection(selection).properties(
            width=800,
            height=400,
        ).interactive().configure_axisX(labelAngle=0)

        oi_df=oi_df[list(ind_name_list)].reset_index()
        amount_df=amount_df[list(ind_name_list)].reset_index()

        oi_df=oi_df.melt(id_vars='date',value_name='持仓量',var_name='板块')
        col_value='持仓量'
        col_type='板块'
        selection = alt.selection_multi(fields=[col_type], bind='legend', name=col_type)
        title_string = '持仓量变化(分板块)' + d_start.strftime('%Y/%m/%d') + "-" + d_end.strftime('%Y/%m/%d')
        base2 = alt.Chart(oi_df, title=title_string).mark_line().encode(
            x=alt.X('date:T', axis=alt.Axis(format='%Y/%m/%d')),
            y=alt.Y(col_value, scale=alt.Scale(domain=[oi_df[col_value].min(), oi_df[col_value].max()]), title=col_value),
            color=alt.Color(col_type),
            tooltip=[col_type, 'date', {'field':col_value,'format':',.2f'}],
            opacity=alt.condition(selection, alt.value(1), alt.value(0.1))
        )

        nearest = alt.selection_single(nearest=True, on='mouseover', empty='none')
        point = base2.mark_point().encode(
            opacity=alt.condition(nearest, alt.value(1), alt.value(0))
        ).add_selection(nearest)
        lines = base2.add_selection(selection)
        chart2 = alt.layer(lines, point).interactive().configure_axisX(labelAngle=0)


        amount_df = amount_df.melt(id_vars='date',value_name='成交量',var_name='板块')
        col_value='成交量'
        col_type='板块'
        selection = alt.selection_multi(fields=[col_type], bind='legend', name=col_type)
        title_string = '成交量变化(分板块)' + d_start.strftime('%Y/%m/%d') + "-" + d_end.strftime('%Y/%m/%d')
        base3 = alt.Chart(amount_df, title=title_string).mark_line().encode(
            x=alt.X('date:T', axis=alt.Axis(format='%Y/%m/%d')),
            y=alt.Y(col_value, scale=alt.Scale(domain=[amount_df[col_value].min(), amount_df[col_value].max()]), title=col_value),
            color=alt.Color(col_type),
            tooltip=[col_type, 'date', {'field':col_value,'format':',.2f'}],
            opacity=alt.condition(selection, alt.value(1), alt.value(0.1))
        )

        nearest = alt.selection_single(nearest=True, on='mouseover', empty='none')
        point = base3.mark_point().encode(
            opacity=alt.condition(nearest, alt.value(1), alt.value(0))
        ).add_selection(nearest)
        lines = base3.add_selection(selection)
        chart3 = alt.layer(lines, point).interactive().configure_axisX(labelAngle=0)

        return chart1,chart2,chart3



# ------------------------------------------------------
# 托管截面保证金占用\换手率\持仓周期展示
# ------------------------------------------------------
def visCTA_FundCSInfoBoxplot(
    date,  # 展示仓位日期，输入格式:datetime.date
    start_date,  # 起始日期，输入格式:datetime.date
    type='Margin',  # 'Margin':绘制保证金, 'Turnover':换手率, 'HoldingPeriod':平均持仓周期
    represent=True,  # True:仅展示各策略下代表产品, False:展示所有产品
    local_path=None,  # the path you would like to save the image
):
    assert type in ('Margin', 'Turnover', 'HoldingPeriod'), \
        "type只能输入'Margin', 'Turnover', 'HoldingPeriod' "
    product_info = custHF.custHF_getProductInfo()
    if type=='Margin':
        df = cta.ctaAnls_HFMarginTS(end_date=date, start_date=start_date)
    else:
        df = cta.ctaAnls_HFTurnover(end_date=date, start_date=start_date, type=type)
    title_map = {'Margin': '保证金使用', 'Turnover': '换手率', 'HoldingPeriod': '平均持仓周期'}
    if represent:
        df = df.loc[df['product_id'].isin(cta_monitoring_products_config.keys())]
    col_dict = {'Margin':'margin', 'Turnover':'turnover', 'HoldingPeriod':'holding_period'}
    df = pd.merge(df, product_info[['product_id', 'product_short_name']], left_on='product_id', right_on='product_id', how='left')
    df = pd.pivot_table(df, index='date', columns='product_short_name', values=col_dict[type])
    df2 = df.copy()
    df2.columns = range(1, len(df2.columns)+1)
    df2 = df2.unstack().reset_index(level=0)
    num = df2.T.iloc[0].unique()
    dot = [df2.loc[df2.T.iloc[0] == n].tail(1) for n in num]
    dot = pd.concat(dot, axis=0)
    fig, ax = plt.subplots(figsize=(8, 8 * 0.618))
    df.plot.box(ax=ax)
    plt.xticks(rotation=90)
    plt.scatter(*dot.values.T)
    ax.legend(('%s%s' % (datetime.datetime.strftime(df.index[-1], '%Y%m%d'),
                         title_map[type]),), loc='upper left')
    plt.tight_layout()
    figure = plt.gcf()
    if local_path is None:
        pass
    else:
        picture_name = '%s%s' % (datetime.datetime.strftime(df.index[-1], '%Y%m%d'),
                        title_map[type])  # the name of the picture you want to save
        plt.savefig('%s\\%s.png' % (local_path, picture_name))
    plt.close(fig)
    return figure
# ------------------------------------------------------
# 托管时序保证金占用\换手率\持仓周期展示，平台展示调用
# ------------------------------------------------------
def visCTA_FundTSInfoLinePlot(
    start_date,  # 起始日期，输入格式:datetime.date
    date,  # 展示仓位日期，输入格式:datetime.date
    type='Margin',  # 'Margin':绘制保证金, 'Turnover':换手率, 'HoldingPeriod':平均持仓周期
    product_id=None
):
    assert type in ('Margin', 'Turnover', 'HoldingPeriod', 'HoldingVolume'), \
        "type只能输入'Margin', 'Turnover', 'HoldingPeriod', 'HoldingVolume' "
    if type=='Margin':
        df = cta.ctaAnls_HFMarginTS(end_date=date, start_date=start_date,product_id=product_id)
    else:
        df = cta.ctaAnls_HFTurnover(end_date=date, start_date=start_date, type=type, product_id=product_id)

    title_map = {'Margin': '保证金占用', 'Turnover': '滚动60日双边换手率', 'HoldingPeriod': '滚动60日平均持仓周期', 'HoldingVolume': '持有期货品种数量'}
    d_start=df['date'].min()
    d_end = df['date'].max()
    col_dict = {'Margin':'margin', 'Turnover':'turnover', 'HoldingPeriod':'holding_period', 'HoldingVolume': 'holding_num'}
    format_dict = {'Margin': '.2%', 'Turnover': ',.1f', 'HoldingPeriod': ',.1f', 'HoldingVolume': '.0f'}
    col_name=col_dict[type]
    title_string = title_map[type]+"，统计区间："+d_start.strftime('%Y/%m/%d')+"-"+d_end.strftime('%Y/%m/%d')
    df["date"] = df["date"].apply(pd.Timestamp)
    base = alt.Chart(df,title=title_string).mark_line().encode(
        x=alt.X('date:T', axis=alt.Axis(format='%Y/%m/%d')),
        y=alt.Y(col_name, scale=alt.Scale(domain=[df[col_name].min(), df[col_name].max()]), title=title_map[type], axis=alt.Axis(format=format_dict[type])),
        color=alt.Color('product_name'),
        tooltip=['product_name', 'date', {'field': col_name,'format': format_dict[type]}],
    )

    nearest = alt.selection_single(nearest=True, on='mouseover', empty='none')
    point = base.mark_point().encode(
        opacity=alt.condition(nearest, alt.value(1), alt.value(0))
    ).add_selection(nearest)
    chart = alt.layer(base, point).properties(
        width=800,
        height=400,
    ).interactive().configure_axisX(labelAngle=0)
    return chart

# ------------------------------------------------------
# 托管截面板块保证金比例
# ------------------------------------------------------
def visCTA_FundSectionMargin(
    date,  # 展示仓位日期，输入格式:datetime.date
    represent=True,  # True:仅展示各策略下代表产品, False:展示所有产品
    section_num=5,  # 显示前N大板块保证金
):
    margin_df = cta.ctaAnls_HFSectionMarginCS(date=date, section_num=section_num)
    margin_df.replace({'section': const.FUTURES_IND_NAME_CN_TO_EN}, inplace=True)
    if represent:
        margin_df = margin_df.loc[margin_df['product_id'].isin(cta_monitoring_products_config.keys())].reset_index(drop=True)
    ind_col = ['第%s大板块' % i for i in list(range(1, section_num + 1))]
    weight_col = ['第%s大占总保证金比' % i for i in list(range(1, section_num+1))]
    join_col = list(chain.from_iterable(zip(ind_col, weight_col)))
    margin_df['section_rank'] = pd.DataFrame(ind_col * len(margin_df['product_name'].unique()))
    margin_df['weight_rank'] = pd.DataFrame(weight_col * len(margin_df['product_name'].unique()))
    result_section = pd.pivot_table(margin_df, index='product_name', values='section', columns='section_rank', aggfunc='first')
    result_weight = pd.pivot_table(margin_df, index='product_name', values='margin', columns='weight_rank')
    result = result_section.join(result_weight)
    result['数据日期'] = date
    result = result[['数据日期'] + join_col]
    col_dict = dict(zip(weight_col, ['{:.2%}']*section_num))
    result = result.style.format(col_dict).background_gradient(subset=weight_col, cmap='Reds', low=0, high=config.cmap_range_adjust_coef)
    return result

# ------------------------------------------------------
# 托管截面板块保证金比例
# ------------------------------------------------------
def visCTA_FundSectionInfoBarPlot(
    date,  # 展示仓位日期，输入格式:datetime.date
    section,
    represent=True,  # True:仅展示各策略下代表产品, False:展示所有产品
    data_type='val'  # 保证金口径数据margin, 市值口径数据val
):
    assert data_type in ('margin', 'val'), "输入数据类型需为margin 或 val"
    assert section in list(const.FUTURES_IND_NAME_CN_TO_EN.values()), "输入section需要为煤焦钢矿, 有色, 能源, 油脂油料, 贵金属, 化工, 软商品, 农副产品, 非金属建材, 谷物, 股指期货, 国债期货, 商品期货"
    product_info = custHF.custHF_getProductInfo()
    if data_type == 'margin':
        margin_df = ctaData.cta_getFundPositionsInfo(start_date=date, end_date=date, sheet_tag='MARGIN', product_id=None)
        margin_df.rename(columns=const.FUTURES_IND_NAME_CN_TO_EN, inplace=True)
        if represent:
            margin_df = margin_df.loc[margin_df['product_id'].isin(cta_monitoring_products_config.keys())].reset_index(drop=True)
        margin_df = pd.merge(margin_df, product_info[['product_id', 'product_short_name']], left_on='product_id', right_on='product_id', how='left')
        margin_df.sort_values(by='product_short_name', inplace=True, ascending=True)
        fig, ax = plt.subplots(figsize=(8, 8 * 0.618))
        margin_df.plot.bar(x='product_short_name', y=section, color='navy', ax=ax)
        ax.set_title(section + '板块保证金占用：' + date.strftime('%Y-%m-%d'), fontsize=18)
        plt.xticks(fontsize=12)
        plt.tight_layout()
        figure = plt.gcf()
        plt.close(fig)
    elif data_type == 'val':
        val_df = ctaData.cta_getFundPositionsInfo(start_date=date, end_date=date, sheet_tag='VAL', product_id=None)
        cost_df = ctaData.cta_getFundPositionsInfo(start_date=date, end_date=date, sheet_tag='VALSUM', product_id=None)
        val_df['type'] = 'val'
        cost_df['type'] = 'valsum'
        val_cost_df = pd.concat([val_df, cost_df], axis=0)
        val_cost_df.rename(columns=const.FUTURES_IND_NAME_CN_TO_EN, inplace=True)
        val_cost_df = val_cost_df.pivot_table(index=['date', 'product_id', 'product_name'], columns='type', values=section).reset_index()
        val_cost_df['多头'] = (val_cost_df['val'] + val_cost_df['valsum']) / 2
        val_cost_df['空头'] = -(val_cost_df['valsum'] - val_cost_df['val']) / 2
        val_cost_df = pd.merge(val_cost_df, product_info[['product_id', 'product_short_name']], on='product_id', how='left')
        val_cost_df.sort_values(by='product_short_name', inplace=True, ascending=True)
        fig, ax = plt.subplots(figsize=(8, 8 * 0.618))
        val_cost_df.plot.bar(x='product_short_name', y='空头',  label='空头市值', color='g', ax=ax)
        val_cost_df.plot.bar(x='product_short_name', y='多头', label='多头市值', color='r', ax=ax)
        val_cost_df.plot.bar(x='product_short_name', y='val', label='净敞口', color='gray', ax=ax)
        ax.set_title(section + '板块多空市值及敞口：' + date.strftime('%Y-%m-%d'), fontsize=18)
        ax.legend(loc='upper left')
        plt.xticks(rotation=90)
        plt.tight_layout()
        figure = plt.gcf()
        plt.close(fig)
    return figure
# ------------------------------------------------------
# 托管时序板块保证金比例,平台展示调用
# ------------------------------------------------------
def visCTA_FundTSSectionMargin(
    start_date, # 输入格式:datetime.date
    end_date,  # 输入格式:datetime.date
    product_id=None,  # 单产品代码 e.g. ['SGW851.OF'], 默认None为全量读取
):
    df = cta.ctaAnls_HFSectionMarginTS(start_date=start_date,end_date=end_date,product_id=product_id)
    df.replace({'section': const.FUTURES_IND_NAME_CN_TO_EN}, inplace=True)
    d_start=df['date'].min()
    d_end = df['date'].max()

    value_name='margin'
    title_string = "时序板块保证金占用" + "，统计区间：" + d_start.strftime('%Y/%m/%d') + "-" + d_end.strftime('%Y/%m/%d')
    selection = alt.selection_multi(fields=['section'], bind='legend', name='板块')
    df["date"] = df["date"].apply(pd.Timestamp)
    base = alt.Chart(df,title=title_string).mark_line().encode(
        x=alt.X('date:T', axis=alt.Axis(format='%Y/%m/%d')),
        y=alt.Y(value_name, scale=alt.Scale(domain=[df[value_name].min(), df[value_name].max()]), title='保证金占用',  axis=alt.Axis(format='%')),
        color=alt.Color('section'),
        tooltip=['section', 'date',{'field':value_name,'format':'.2%'}],
        opacity=alt.condition(selection, alt.value(1), alt.value(0.1))
    )
    nearest = alt.selection_single(nearest=True, on='mouseover', empty='none')
    point = base.mark_point().encode(
        opacity=alt.condition(nearest, alt.value(1), alt.value(0))
    ).add_selection(nearest)
    lines = base.add_selection(selection)
    chart = alt.layer(lines, point).properties(
        width=800,
        height=400,
    ).interactive().configure_axisX(labelAngle=0)
    return chart

# ------------------------------------------------------
# 托管区间板块损益
# ------------------------------------------------------
def visCTA_FundSectionPNL(
    start_date,  # 开始日期，输入格式:datetime.date
    end_date,  # 结束日期，输入格式:datetime.date，日期代表当周
    product_id=None,  # 单产品代码 e.g. 'SGW851.OF', 默认None为全量读取
    represent=True,  # True:仅展示各策略下代表产品, False:展示所有产品
    local_path=None  # the path you would like to save the image
):
    pnl_df = cta.ctaAnls_HFSectionPNL(start_date, end_date, product_id)
    if product_id is None:
        if represent:
            pnl_df = pnl_df.loc[pnl_df['product_id'].isin(cta_monitoring_products_config.keys())].reset_index(drop=True)
    pnl_df.rename(columns=const.FUTURES_IND_NAME_CN_TO_EN, inplace=True)
    col_keep=list(const.FUTURES_IND_NAME_CN_TO_EN.values())
    col_keep.remove('商品期货')
    for id in pnl_df.index:
        fig, ax = plt.subplots()
        data = pnl_df.loc[id, col_keep]
        bottom = 0
        x_idx = np.arange(len(data), dtype=np.float64)
        labels = data.index.tolist()
        x_loc = np.arange(len(labels))
        for i, pnl in enumerate(data):
            x = x_idx[i]
            y = data.iloc[i]
            if pnl > 0:
                label1 = '盈'
                profit = plt.bar(x, y, align='center', bottom=bottom, label=label1, color='red')
            else:
                label2 = '亏'
                loss = plt.bar(x, y, align='center', bottom=bottom, label=label2, color='green')
            bottom += y
            x += 0.8
        plt.legend(handles=[profit, loss])
        plt.title('%s %s-%s板块累计损益' % (pnl_df.loc[id, 'product_name'], datetime.datetime.strftime(start_date, '%Y%m%d'),
                                           datetime.datetime.strftime(end_date, '%Y%m%d')))
        plt.xticks(x_loc)
        ax.set_xticklabels(labels)
        plt.setp(ax.get_xticklabels(), rotation=45, ha='right', rotation_mode='anchor')
        ax.yaxis.grid(True, linestyle='--', color='grey', alpha=0.25)
        plt.tight_layout()
        if local_path is None:
            plt.show()
        else:
            # the name of the picture you want to save
            picture_name = '%s板块累计损益' % id
            plt.savefig('%s\\%s.png' % (local_path, picture_name))
        plt.close()
# ------------------------------------------------------
# 托管时序板块损益，平台展示调用
# ------------------------------------------------------
def visCTA_FundTSSectionPNL(
    start_date,  # 开始日期，输入格式:datetime.date
    end_date,  # 结束日期，输入格式:datetime.date，日期代表当周
    product_id=None,  # 单产品代码 e.g. 'SGW851.OF', 默认None为全量读取
):
    pnl_df = cta.ctaAnls_HFSectionPNLTS(start_date, end_date, product_id)
    pnl_df.rename(columns=const.FUTURES_IND_NAME_CN_TO_EN, inplace=True)
    pnl_df['date'] = pd.to_datetime(pnl_df['date']).dt.date

    nameset=set(pnl_df.columns)-set(['date','product_id', 'product_name'])
    col_keep=list(nameset)
    df_melt=pd.melt(pnl_df, id_vars=['date','product_id', 'product_name'],
                     value_vars=col_keep).rename(
                     columns={'variable': 'section', 'value': 'pnl'})
    d_start=df_melt['date'].min()
    d_end=df_melt['date'].max()
    value_name='pnl'
    title_string = "时序板块损益" + "，统计区间：" + d_start.strftime('%Y/%m/%d') + "-" + d_end.strftime('%Y/%m/%d')
    selection = alt.selection_multi(fields=['section'], bind='legend', name='板块')
    df_melt["date"] = df_melt["date"].apply(pd.Timestamp)
    base = alt.Chart(df_melt,title=title_string).mark_line().encode(
        x=alt.X('date:T', axis=alt.Axis(format='%Y/%m/%d')),
        y=alt.Y(value_name, scale=alt.Scale(domain=[df_melt[value_name].min(), df_melt[value_name].max()]), title=value_name),
        color=alt.Color('section'),
        tooltip=['section', 'date', {'field': value_name, 'format': ',.2f'}],
        opacity=alt.condition(selection, alt.value(1), alt.value(0.1))
    )
    nearest = alt.selection_single(nearest=True, on='mouseover', empty='none')
    point = base.mark_point().encode(
        opacity=alt.condition(nearest, alt.value(1), alt.value(0))
    ).add_selection(nearest)
    lines = base.add_selection(selection)
    chart = alt.layer(lines, point).properties(
        width=800,
        height=400,
    ).interactive().configure_axisX(labelAngle=0)
    return chart
# ------------------------------------------------------
# 托管截面板块市值敞口比例和变化
# ------------------------------------------------------
def visCTA_FundSectionExposureInfo(
    end_date,  # 结束日期，输入格式:datetime.date
    start_date,  # 起始日期，输入格式:datetime.date
    pos_change=True,  # True:仓位变动，False:绝对仓位，若为False，end_date须和start_date一致
    direction=True,  # 仓位变动方向，True为加仓/多头，False为减仓/空头
    represent=True,  # True:仅展示各策略下代表产品, False:展示所有产品
    section_num=3  # 显示前N大板块保证金
):
    if pos_change:
        df = cta.ctaAnls_HFSectionExposureChg(end_date=end_date, start_date=start_date, direction=direction, section_num=section_num)
        tag = '多头增仓' if direction == True else '空头增仓'
    else:
        assert start_date == end_date, "如果选择pos_change=False绝对仓位，start_date必须等于end_date"
        df = cta.ctaAnls_HFSectionExposureCS(date=end_date, direction=direction, section_num=section_num)
        tag = '多头' if direction == True else '空头'
    if represent:
        df = df.loc[df['product_id'].isin(cta_monitoring_products_config.keys())].reset_index(drop=True)
    df.replace({'section': const.FUTURES_IND_NAME_CN_TO_EN}, inplace=True)
    ind_col = ['第%s大%s板块' % (i, tag) for i in list(range(1, section_num + 1))]
    weight_col = ['第%s大%s市值占净值比' % (i, tag) for i in list(range(1, section_num + 1))]
    join_col = list(chain.from_iterable(zip(ind_col, weight_col)))
    df['section_rank'] = pd.DataFrame(ind_col * len(df['product_id'].unique()))
    df['weight_rank'] = pd.DataFrame(weight_col * len(df['product_id'].unique()))
    result_section = pd.pivot_table(df, index='product_name', values='section', columns='section_rank', aggfunc='first')
    result_weight = pd.pivot_table(df, index='product_name', values='exposure_change' if pos_change else 'value_exposure',
                                   columns='weight_rank')
    result = result_section.join(result_weight)
    result['起始日期'] = start_date
    result['结束日期'] = end_date
    result = result[['起始日期', '结束日期'] + join_col]
    col_dict = dict(zip(weight_col, ['{:.2%}']*section_num))
    result = result.style.format(col_dict).background_gradient(subset=weight_col, cmap='Reds', low=0, high=config.cmap_range_adjust_coef).highlight_null('white')
    return result

# ------------------------------------------------------
# 托管截面板块市值敞敞口、区间变化，平台展示调用
# ------------------------------------------------------
def visCTA_FundSectionExposureChg(
    end_date,  # 结束日期，输入格式:datetime.date
    start_date,  # 起始日期，输入格式:datetime.date
    product_id=None
):

    df = cta.ctaAnls_SingleFundSectionExposureChg(end_date=end_date, start_date=start_date, product_id=product_id)

    df.replace({'section': const.FUTURES_IND_NAME_CN_TO_EN}, inplace=True)
    name_dict={'product_name':'产品','section':'板块','exposure_start':'期初市值','exposure_end':'期末市值','exposure_change':'市值变动'}
    df.rename(columns=name_dict,inplace=True)

    result = df[['开始日期', '结束日期', '产品','板块','市值变动','期初市值','期末市值']]
    col_dict = dict(zip(['期初市值','期末市值','市值变动'], ['{:.2%}']*3))
    cmap_df = sns.diverging_palette(**config.cmap_kwargs)
    result = result.style.format(col_dict).background_gradient(subset=['期初市值','期末市值','市值变动'], cmap=cmap_df).highlight_null('white')
    return result
# ------------------------------------------------------
# 托管时序板块市值敞口,平台展示调用
# ------------------------------------------------------
def visCTA_FundTSSectionExposureInfo(
    start_date,  # 起始日期，输入格式:datetime.date
    end_date,  # 结束日期，输入格式:datetime.date
    product_id=None # 单产品代码 e.g. ['SGW851.OF'], 默认None为全量读取
):
    df = cta.ctaAnls_HFSectionExposureTS(start_date=start_date,end_date=end_date, product_id=product_id)
    df.replace({'section': const.FUTURES_IND_NAME_CN_TO_EN}, inplace=True)
    d_start=df['date'].min()
    d_end = df['date'].max()

    title_string = "时序板块合约市值净暴露"+"，统计区间：" + d_start.strftime('%Y/%m/%d') + "-" + d_end.strftime('%Y/%m/%d')
    selection = alt.selection_multi(fields=['section'], bind='legend', name='板块')
    df["date"] = df["date"].apply(pd.Timestamp)
    base = alt.Chart(df,title=title_string).mark_line().encode(
        x=alt.X('date:T', axis=alt.Axis(format='%Y/%m/%d')),
        y=alt.Y('value_exposure', scale=alt.Scale(domain=[df['value_exposure'].min(), df['value_exposure'].max()]), title='合约市值净暴露', axis=alt.Axis(format='%')),
        color=alt.Color('section'),
        tooltip=['section', 'date', {'field': 'value_exposure', 'format': ',.4f'}],
        opacity=alt.condition(selection, alt.value(1), alt.value(0.1))
    )
    nearest = alt.selection_single(nearest=True, on='mouseover', empty='none')
    point = base.mark_point().encode(
        opacity=alt.condition(nearest, alt.value(1), alt.value(0))
    ).add_selection(nearest)
    lines = base.add_selection(selection)
    chart = alt.layer(lines, point).properties(
        width=800,
        height=400,
    ).interactive().configure_axisX(labelAngle=0)
    return chart

# ------------------------------------------------------
# 已投产品区间相对基准表现
# ------------------------------------------------------
def visCTA_HFWeeklyReturn(
    ids,
    start_date,  # 起始日期，输入格式:datetime.date
    end_date,  # 结束日期，输入格式:datetime.date
    data_level='Strategy'  # 需输入Product或Strategy
):
    performance_data = basicAnal.basicAnal_calPerformanceStats(ids, start_date, end_date, freq='W', fund_type='HF', benchmark_id=None,
                                                               data_level=data_level, strategy_category=None)
    if data_level == 'Strategy':
        level_info = custHF.custHF_getStrategyInfo()
        id_to_name = level_info.set_index('strategy_id')['strategy_name'].to_dict()
    else:
        level_info = custHF.custHF_getProductInfo()
        id_to_name = level_info.set_index('product_id')['product_short_name'].to_dict()
    performance_data['level_name'] = performance_data['id'].apply(lambda x: id_to_name[x])
    performance_data.sort_values(by='period_return', ascending=False, inplace=True)
    bench_data = zyyx_cached.zyyxCached_getCachedUnivDistribution(start_date, end_date, categories=['中波动管理期货'],
                                                                  stats=['week_return'], percent_array=[0.5])
    bench_data = (bench_data['0.5'] + 1).prod(axis=0) - 1
    performance_data['bench_return'] = bench_data
    performance_data.rename(columns={
        'period_return': '区间收益率',
        'annualized_period_return': '年化区间收益率',
        'max_drawdown': '最大回撤',
        'sharpe_ratio': '夏普',
        'calmar': '卡玛比',
        'annualized_volatility': '年化波动率',
        'level_name': '名称',
        'start_date': '开始日期',
        'end_date': '截止日期',
        'year_return_rank': '今年以来收益率排名',
        'bench_return':'区间基准收益'
    }, inplace=True)

    formatter = {
        '区间收益率': lambda x: "{:.2%}".format(x),
        '年化区间收益率': lambda x: "{:.2%}".format(x),
        '年化波动率': lambda x: "{:.2%}".format(x) if not isinstance(x, str) else x,
        '最大回撤': lambda x: "{:.2%}".format(x),
        '夏普': lambda x: "{:.2f}".format(x) if not isinstance(x, str) else x,
        '卡玛比': lambda x: "{:.2f}".format(x),
        '年化区间超额收益': lambda x: "{:.2%}".format(x),
        '开始日期': lambda x: x.strftime("%Y-%m-%d"),
        '截止日期': lambda x: x.strftime("%Y-%m-%d"),
        '名称': lambda x: str(x),
        '今年以来收益率排名': lambda x: "{:.2%}".format(x),
        '区间基准收益': lambda x: "{:.2%}".format(x)
    }
    performance_data = performance_data[['名称', '开始日期', '截止日期', '区间收益率', '区间基准收益']]
    new_cmap = sns.diverging_palette(**config.cmap_kwargs)
    d1 = dict(selector="th", props=[('text-align', 'center')])
    d2 = dict(selector='caption', props=[('text-align', 'center'), ('font-weight', 'bold'), ('color', 'black'), ('font-size', '125%')])
    df = performance_data.reset_index(drop=True).style.format(formatter, na_rep="")\
        .set_properties(**{'width': '100', 'text-align': 'center'})\
        .set_table_styles([d1])\
        .set_table_styles([d2], overwrite=False)\
        .background_gradient(subset='区间收益率', cmap=new_cmap, low=config.cmap_range_adjust_coef, high=config.cmap_range_adjust_coef, axis=0,
                             vmin=(-performance_data['区间收益率'].abs().max(axis=0).min()) + bench_data,
                             vmax=performance_data['区间收益率'].abs().max(axis=0).min() + bench_data)
    df = df.highlight_null('white')
    return df

# -----------------------------------------------------------------------
# CTA因子区间收益指标表格
# -----------------------------------------------------------------------
def visCTA_calCTAFactorPerfStats(
    style_factor_list,  # list
    period,  # 统计区间
    date,
    start_date=None,  # This parameter ONLY works for period equal to Customized
):
    start_date = start_date if period == 'Customized' else None
    start_date, end_date = calendar.calender_getStartEndDate(period, date, start_date)
    performance_data = cta.ctaAnls_calCTAFactorPerfStats(start_date, end_date, style_factor_list)
    formatter = {
        'CTA因子': lambda x: str(x),
        '区间收益率': lambda x: "{:.2%}".format(x),
        '年化区间收益率': lambda x: "{:.2%}".format(x),
        '年化波动率': lambda x: "{:.2%}".format(x) if not isinstance(x, str) else x,
        '最大回撤': lambda x: "{:.2%}".format(x),
        '夏普': lambda x: "{:.2f}".format(x) if not isinstance(x, str) else x,
        '卡玛比': lambda x: "{:.2f}".format(x),
        '开始日期': lambda x: x.strftime("%Y-%m-%d"),
        '截止日期': lambda x: x.strftime("%Y-%m-%d"),
    }
    rename_map = {
        'cta_factor': 'CTA因子',
        'period_return': '区间收益率',
        'annualized_period_return': '年化区间收益率',
        'annualized_volatility': '年化波动率',
        'max_drawdown': '最大回撤',
        'sharpe_ratio': '夏普',
        'calmar': '卡玛比',
        'start_date': '开始日期',
        'end_date': '截止日期',
    }
    performance_data.rename(columns=rename_map, inplace=True)
    perf_prefix_cols = ['CTA因子', '开始日期', '截止日期', '区间收益率']
    if period != 'Today':
        performance_data = performance_data[perf_prefix_cols + performance_data.columns.drop(perf_prefix_cols).to_list()]
    else:
        performance_data = performance_data[perf_prefix_cols]
    _df_caption = 'Performance Stats, ' + 'period: ' + period + ', data frequency: D'
    new_cmap = sns.diverging_palette(**config.cmap_kwargs)
    d1 = dict(selector="th", props=[('text-align', 'center')])
    d2 = dict(selector='caption',  props=[('text-align', 'center'), ('font-weight', 'bold'), ('color', 'black'), ('font-size', '125%')])
    df = performance_data.reset_index(drop=True).style.format(formatter, na_rep="") \
        .set_properties(**{'width': '100', 'text-align': 'center'}) \
        .set_caption(_df_caption) \
        .set_table_styles([d1]) \
        .set_table_styles([d2], overwrite=False)
    for col in performance_data.columns.drop(['CTA因子', '开始日期', '截止日期']):
        if col == '年化波动率':
            df = df.background_gradient(subset=col, cmap=sns.diverging_palette(**config.vol_cmap_kwargs), low=config.cmap_range_adjust_coef, high=config.cmap_range_adjust_coef, axis=0)
        elif col == '最大回撤':
            df = df.background_gradient(subset=col, cmap=new_cmap, low=config.cmap_range_adjust_coef, high=config.cmap_range_adjust_coef, axis=0)
        else:
            df = df.background_gradient(subset=col, cmap=new_cmap, low=config.cmap_range_adjust_coef, high=config.cmap_range_adjust_coef, axis=0,
                                        vmin=(-performance_data[col].abs().max(axis=0)), vmax=performance_data[col].abs().max(axis=0))
    df = df.highlight_null('white')
    return df

# -----------------------------------------------------------------------
# CTA因子净值曲线画图
# -----------------------------------------------------------------------
def visCTA_plotFactorNav(
    style_factor_list,  # list
    period,  # 统计区间
    date,
    start_date=None,  # This parameter ONLY works for period equal to Customized
):
    start_date = start_date if period == 'Customized' else None
    start_date, end_date = calendar.calender_getStartEndDate(period, date, start_date)
    style_factor_nav = cta.ctaAnls_calCtaFactorNav(start_date, end_date, style_factor_list)
    # 逆透视, 方便后续使用altair绘图
    result = pd.melt(style_factor_nav, id_vars='date', var_name='cta_factor', value_name='nav')
    nearest = alt.selection_single(nearest=True, on='mouseover', empty='none')
    selection = alt.selection_multi(fields=['cta_factor'], bind='legend', name='CTA因子')
    title_string = "CTA因子净值曲线, 统计区间: " + str(period) + ", 数据频率: D"
    base = alt.Chart(result, title=title_string).mark_line().encode(
        x=alt.X('date:T', title='日期', axis=alt.Axis(format='%Y/%m/%d')),
        y=alt.Y('nav', title='区间Nav', scale=alt.Scale(domain=[0.99*result['nav'].min(), 1.01*result['nav'].max()])),
        color=alt.Color('cta_factor'),
        tooltip=['cta_factor', 'date', {'field': 'nav', 'format': ',.4f'}],
        opacity=alt.condition(selection, alt.value(1), alt.value(0.1))
    )
    point = base.mark_point().encode(
        opacity=alt.condition(nearest, alt.value(1), alt.value(0))
    ).add_selection(nearest)
    lines = base.add_selection(selection)
    c = alt.layer(lines, point).interactive().configure_axisX(labelAngle=0).properties(
            width=600,  # 设置图表宽度
            height=500  # 设置图表高度
    )
    return c, style_factor_nav

# -----------------------------------------------------------------------
# 画CTA factor weekly/monthly performance, 表格形式
# -----------------------------------------------------------------------
def visCTA_calCTAFactorMonthlyReturn(
    end_date,  # 结束日期
    num_trailing_month,  # 展示过去几个月的收益
    factor_list=None  # python list
):
    assert isinstance(num_trailing_month, int), "num_trailing_month should be an int instance"
    start_date = end_date - relativedelta(months=num_trailing_month)
    result = cta.ctaAnls_calCTAFactorMonthlyReturn(start_date, end_date, factor_list)
    result = result.iloc[:num_trailing_month, :]
    result.reset_index(inplace=True)
    result['index'] = result['year'].astype(str) + '-' + result['month'].astype(str)
    result.drop(['year', 'month'], axis=1, inplace=True)
    result.set_index('index', inplace=True)
    result = result.T
    formatter = dict(zip(list(result.columns), [lambda x: "{:.2%}".format(x)] * len(result.columns)))
    new_cmap = sns.diverging_palette(**config.cmap_kwargs)
    d1 = dict(selector="th", props=[('text-align', 'center')])
    d2 = dict(selector='caption', props=[('text-align', 'center'), ('font-weight', 'bold'), ('color', 'black'), ('font-size', '125%')])
    _df_caption = 'Barra factor return: last ' + str(num_trailing_month) + ' Months'
    df = result.style.format(formatter, na_rep="").background_gradient(cmap=new_cmap, low=config.cmap_range_adjust_coef, high=config.cmap_range_adjust_coef, axis=0).highlight_null('white').set_properties(
        **{'width': '100', 'text-align': 'center'}).set_caption(_df_caption).set_table_styles([d1]).set_table_styles([d2], overwrite=False)
    return df

# -----------------------------------------------------------------------
# 画CTA factor 的regression结果
# -----------------------------------------------------------------------
def visCTA_ctaRegressionAnalysis(
    id,
    start_date,  # DateTime.date instance, eg: datetime.date(2021, 1, 1)
    end_date,  # DateTime.date instance, eg: datetime.date(2021, 10, 1)
    data_level='Product',
    freq='W'
):
    assert isinstance(start_date, datetime.date), "date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "date must be an instance of datetime.date"
    assert freq in ("D", "W"), "freq需为D或者W"
    assert data_level in ('Strategy', 'Product'), "数据层级为Strategy 或 Product"
    df_data = cta.ctaAnls_ctaRegressionAnalysis(
            [id],
            start_date,  # DateTime.date instance, eg: datetime.date(2021, 1, 1)
            end_date,  # DateTime.date instance, eg: datetime.date(2021, 10, 1)
            data_level=data_level,
            factor_list=list(const.CTA_FACTOR_NAME_DICT.values()),
            freq=freq
    )
    id = list(df_data.keys())[0]
    df_nav = df_data[id]['nav_decompose'].reset_index()
    df_reg_params = df_data[id]['reg_params']
    # 逆透视, 方便后续使用altair绘图
    result = pd.melt(df_nav, id_vars='date', var_name='nav_name', value_name='nav')
    nearest = alt.selection_single(nearest=True, on='mouseover', empty='none')
    selection = alt.selection_multi(fields=['nav_name'], bind='legend', name='CTA因子')
    title_string = "收益拆解, 统计区间: " + start_date.strftime("%Y-%m-%d") + "到" + end_date.strftime("%Y-%m-%d")+", 数据频率: " + freq
    base = alt.Chart(result, title=title_string).mark_line().encode(
        x=alt.X('date:T', title='日期', axis=alt.Axis(format='%Y/%m/%d')),
        y=alt.Y('nav', title='区间Nav', scale=alt.Scale(domain=[0.99*result['nav'].min(), 1.01*result['nav'].max()])),
        color=alt.Color('nav_name', title='曲线'),
        tooltip=['nav_name', 'date', {'field': 'nav', 'format': ',.4f'}],
        opacity=alt.condition(selection, alt.value(1), alt.value(0.1))
    )
    point = base.mark_point().encode(
        opacity=alt.condition(nearest, alt.value(1), alt.value(0))
    ).add_selection(nearest)
    lines = base.add_selection(selection)
    chart = alt.layer(lines, point)
    return chart, df_reg_params

# -----------------------------------------------------------------------
# 画CTA factor 的收益分析结果，结果包含表格，条形图，曲线图
# -----------------------------------------------------------------------
def visCTA_ctaFactorReturnAnalysis(
    factor,
    start_date,  # DateTime.date instance, eg: datetime.date(2021, 1, 1)
    end_date,  # DateTime.date instance, eg: datetime.date(2021, 10, 1)
    data_level='section',  # 归因层级，section板块，future品种
    long_short=False  # 归因是否区分多头、空头
):
    assert isinstance(start_date, datetime.date), "date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "date must be an instance of datetime.date"
    assert data_level in ('section', 'future'), "仅支持板块层面和品种层面"
    df_attribution_line, df_attribution_return = cta.ctaAnls_ctaFactorReturnAnalysis(
            factor,
            start_date,
            end_date,
            data_level=data_level,
            long_short=long_short
    )
    rename_dict = {
        'future_section': '期货板块',
        'future_id': '品种',
        'direction': '方向',
        'start_date': '开始日期',
        'end_date': '截止日期',
        'return': '收益',
        'accumulate_return': '累计收益',
        'level_direction': '品种_方向',
        'date': '日期',
    }
    df_attribution_return.rename(columns=rename_dict, inplace=True)
    df_attribution_line.rename(columns=rename_dict, inplace=True)
    category_column = '期货板块' if data_level == 'section' else '品种'
    table_result = df_attribution_return[['品种_方向', '开始日期', '截止日期', '收益']]

    formatter = {'收益': '{:.4%}'}
    new_cmap = sns.diverging_palette(**config.cmap_kwargs)
    table_result = table_result.style.format(formatter).set_properties(**{'text-align': 'center'}).\
        background_gradient(subset=['收益'], cmap=new_cmap, low=config.cmap_range_adjust_coef,
                             high=config.cmap_range_adjust_coef, axis=0, vmin=-df_attribution_return['收益'].abs().max(axis=0),
                             vmax=df_attribution_return['收益'].abs().max(axis=0)).hide_index()
    title_string = '因子收益归因 - ' + category_column + ' - ' + str(df_attribution_return['开始日期'].iloc[0]) \
                   + ' - ' + str(df_attribution_return['截止日期'].iloc[0])
    if long_short:
        level_col = '方向'
        selection = alt.selection_multi(nearest=True, fields=[level_col], bind='legend', name='名称')
        base = alt.Chart(df_attribution_return,title=title_string).mark_bar().encode(
                x=alt.X(category_column, sort=None),
                y=alt.Y('收益', axis=alt.Axis(format='%')),
                color=alt.Color(level_col),
                tooltip=[category_column, level_col, {'field': '收益', 'format': '.4%'}],
                opacity=alt.condition(selection, alt.value(1), alt.value(0.1))
                ).properties(width=150).configure_header(titleFontSize=14, labelFontSize=14)
        chart_result = base.add_selection(selection)
    else:
        max_ytick = df_attribution_return['收益'].abs().max() * 1.01
        min_ytick = -max_ytick
        chart_result = alt.Chart(df_attribution_return, title=title_string).mark_bar().encode(
            x=alt.X('收益', scale=alt.Scale(domain=[min_ytick, max_ytick]), title='收益', axis=alt.Axis(format='%')),
            y=alt.Y(category_column + ':N', sort='-x'),
            color=alt.condition(alt.datum.收益 > 0, alt.value("red"), alt.value("green")),
            tooltip=[category_column, {'field': '收益', 'format': '.4%'}],
            text=category_column,
        )

    nearest = alt.selection_single(nearest=True, on='mouseover', empty='none')
    selection = alt.selection_multi(fields=['品种_方向'], bind='legend', name='板块方向')
    base = alt.Chart(df_attribution_line, title=title_string).mark_line().encode(
        x=alt.X('日期:T', title='日期', axis=alt.Axis(format='%Y/%m/%d')),
        y=alt.Y('累计收益', title='累计收益', scale=alt.Scale(domain=[0.99*df_attribution_line['累计收益'].min(), 1.01*df_attribution_line['累计收益'].max()])),
        color=alt.Color('品种_方向'),
        tooltip=['品种_方向', '日期', {'field': '累计收益', 'format': '.4%'}],
        opacity=alt.condition(selection, alt.value(1), alt.value(0.1))
    )
    point = base.mark_point().encode(
        opacity=alt.condition(nearest, alt.value(1), alt.value(0))
    ).add_selection(nearest)
    lines = base.add_selection(selection)
    line_result = alt.layer(lines, point).interactive().configure_axisX(labelAngle=0).properties(
            width=600,
            height=500
    )
    return table_result, chart_result, line_result

# -----------------------------------------------------------------------
# CTA因子与选定策略的相关系数矩阵
# -----------------------------------------------------------------------
def visCTA_plotFactorCorrelation(
    ids_dict,           # dict, id with fund type, e.g. {'MF': ['000711.OF'], 'HF': ['S0000045', 'S0000053']}，可以只有MF或者HF
    period,             # 统计区间， YTD, YTLDLM, 2022, 2021, 2020, 2019, SI (since　inception）,Custom
    freq='W',  # 数据频率，D或者W
    date=datetime.datetime.today().date(),
    data_level='Strategy',  # Strategy or Product
    start_date=None,        # This parameter ONLY works for period equal to Customized
    factor_list=None
):
    assert isinstance(ids_dict, dict), "ids_dict需为dict，例：{'HF': ['SJA330.OF']}"
    assert type(date) == datetime.date, '日期输入格式需为datetime.date'
    assert freq in ("D", "W"), "freq需为D或者W"
    assert data_level in ('Strategy', 'Product'), "数据层级为Strategy 或 Product"
    start_date, end_date = calendar.calender_getStartEndDate(period, date, start_date)
    corr_df = cta.ctaAnls_calFactorCorrelation(ids_dict, start_date, end_date, freq, factor_list=factor_list)
    print(corr_df)
    corr_long = corr_df.reset_index().melt(id_vars='index')
    corr_long.columns = ['横轴', '纵轴', '相关性']
    variable_order = list(corr_df.columns)
    # 绘制相关性热力图
    if period != 'SI':
        start_date_text = start_date.strftime("%Y-%m-%d")
    else:
        start_date_text = '成立以来'
    title_string = "相关系数：" + start_date_text + "到" + end_date.strftime("%Y-%m-%d")
    heatmap = alt.Chart(corr_long, title=title_string).mark_rect().encode(
        x=alt.X('纵轴:O', sort=variable_order, title=''),
        y=alt.Y('横轴:O', sort=variable_order, title=''),
        color=alt.Color('相关性:Q', scale=alt.Scale(range=['#2ecc71', '#f7f7f7', '#e74c3c'], domain=[-1, 0, 1])),
        tooltip=['横轴', '纵轴', {'field': '相关性', 'format': '.2f'}],
    )
    # 添加文本标签
    text = heatmap.mark_text(baseline='middle').encode(
        text=alt.Text('相关性:Q', format='.2f'),
        color=alt.value('black'),
    )
    # 组合图表
    final_chart = heatmap + text

    return final_chart

# -----------------------------------------------------------------------
# CTA因子不同周期收益柱状图
# -----------------------------------------------------------------------
def visCTA_plotFactorPeriodReturn(
    end_date  # DateTime.date instance, eg: datetime.date(2021, 1, 1)
):
    assert isinstance(end_date, datetime.date), "date must be an instance of datetime.date"
    factor_period_return = cta.ctaAnls_calCTAFactorPeriodReturn(end_date-datetime.timedelta(days=90), end_date)
    result = factor_period_return.melt(id_vars=['因子', '因子分类'], value_vars=['近一周收益率', '近一月收益率', '近三月收益率'], var_name='收益周期', value_name='收益率')
    title_string = "因子收益柱状图-截止日期-" + end_date.strftime("%Y-%m-%d")
    selection = alt.selection_multi(nearest=True, fields=['收益周期'], bind='legend', name='名称')
    base = alt.Chart(result, title=title_string).mark_bar().encode(
        x=alt.X('收益周期:O', title=None),
        y=alt.Y('收益率:Q', title='区间收益', axis=alt.Axis(format='0.2%')),
        color=alt.Color('收益周期:N'),
        column=alt.Column('因子:N', title='因子', sort=list(const.CTA_FACTOR_NAME_DICT.values())),
        tooltip=['因子分类', '因子', '收益周期', {'field': '收益率', 'format': '.2%'}],
        opacity=alt.condition(selection, alt.value(1), alt.value(0.1))
    )
    chart = base.add_selection(selection)
    return chart