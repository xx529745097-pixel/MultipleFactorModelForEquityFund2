import os.path
import time

import pandas as pd
import datetime
from dateutil.relativedelta import relativedelta
import numpy as np
import sqlalchemy
from dateutil.parser import parse
from matplotlib import pyplot as plt

import src.const
import src.utils.Calculation as Cal
import src.data.wind as wind
import src.analysis.MFAnalysis as MFanls
import src.utils.backtest as bt
import fstrat_config
import warnings
warnings.filterwarnings('ignore')
import pulp

date = datetime.date(2026,3,31)


# 根据基准类型生成行业权重
# 通过 WDS 获取基准指数的行业权重
dbconn = wind.wind_connectWindDB()
sql_equity_fund = """
    SELECT DISTINCT a.F_INFO_WINDCODE 
    FROM ChinaMutualFundSector a
    JOIN ChinaMutualFundStockPortfolio b ON a.F_INFO_WINDCODE = b.S_INFO_WINDCODE
    WHERE a.S_INFO_SECTORENTRYDT <= '{0}' 
      AND (a.S_INFO_SECTOREXITDT >= '{1}' OR a.S_INFO_SECTOREXITDT IS NULL)
      -- 过滤股票市值占比 >= 60%
      AND b.F_PRT_STKVALUETONAV >= 0.60
      -- ⚠️ 补充建议：限制投资组合表的报告期，防止拉取历史全部季度导致数据爆炸！
      -- AND b.F_PRT_ENDDATE <= '{0}' 
      -- 将原 Pandas 中的行业代码过滤前置到 SQL 的 WHERE 子句
      AND SUBSTR(a.S_INFO_SECTOR, 1, 10) IN ('2001010101', '2001010201', '2001010204')
"""
date_temp = date.strftime("%Y%m%d")
equity_fund_df = pd.read_sql_query(sql_equity_fund.format(date_temp, date_temp), dbconn)
# equity_fund_df = equity_fund_df[
#     equity_fund_df['s_info_sector'].str[:10].isin(['2001010101', '2001010201', '2001010204'])]

equity_fund_list = equity_fund_df['f_info_windcode'].unique().tolist()
# equity_fund_list = pd.read_excel('C:/Users/041685/Desktop/Python代码/基金分类-场内代码清洗/List2_clean.xlsx')
# equity_fund_list = equity_fund_list['product_id'].tolist()
df_industry2 = MFanls.anlsMF_getMFSimHoldingIndustryExposure(date, equity_fund_list, 'SW', level=2)
df_industry2_clean = df_industry2[['product_id', 'industry', 'industry_weight', 'report_date']].copy()
df_industry2_clean.rename(columns={'report_date': 'date'}, inplace=True)
df_industry2_clean['date'] = pd.to_datetime(df_industry2_clean['date'])
df_industry = df_industry2_clean.pivot_table(
    index=['date', 'product_id'],  # 行：日期+产品ID
    columns='industry',  # 列：行业名称
    values='industry_weight',  # 值：行业权重
    fill_value=0,  # 缺失值填0
    aggfunc='sum'  # 聚合方式（重复行求和，无重复则等价于直接取值）
).reset_index()
# result_industry_sum = pd.pivot_table(df_industry2, columns='industry', index=['report_date', 'product_id'],
#                                      values='industry_weight', aggfunc='first').fillna(0).reset_index()
df_industry.to_excel('885001行业比例_{}.xlsx'.format(date.strftime("%Y%m%d")))

non_numeric_cols = ['date', 'product_id']  # 不需要归一化的列
numeric_cols = df_industry.columns.drop(non_numeric_cols)  # 需要归一化的数值列

# 4. 按行归一化（每行求和为1）
# 计算每行的总和
row_sums = df_industry[numeric_cols].sum(axis=1)
# 处理总和为0的情况（避免除以0）
row_sums = row_sums.replace(0, 1)  # 总和为0时，保持原值（除以1不改变）
# 归一化：每个数值 / 该行总和
df_normalized = df_industry.copy()
df_normalized[numeric_cols] = df_industry[numeric_cols].div(row_sums, axis=0)
# 2. 定义不计算平均值的列（可根据你的需求修改）
exclude_cols = ['date', 'product_id']
# 3. 筛选需要计算平均值的列，并计算每列均值
calc_cols = [col for col in df_normalized.columns if col not in exclude_cols]
col_means = df_normalized[calc_cols].mean()  # 计算指定列的平均值
# 4. 构造平均值行（非计算列填充标识，如"平均值"）
mean_row = {}
for col in df_normalized.columns:
    if col in exclude_cols:
        mean_row[col] = '平均值'  # 非数值列填充说明文字
    else:
        mean_row[col] = round(col_means[col], 4)  # 数值列填充平均值（保留2位小数）
# 5. 将平均值行转换为DataFrame，并插入到第一行
mean_df = pd.DataFrame([mean_row])  # 转为DataFrame
df_with_mean = pd.concat([mean_df, df_normalized], ignore_index=True)  # 合并并重置索引
df_with_mean = df_with_mean.reset_index(drop= True)
industry_holdings = df_with_mean.iloc[0]  # 提取第一行数据
industry_holdings = industry_holdings.reset_index()  # 重置索引
industry_holdings.columns = ['申万二级行业', '持仓比例']  # 重命名列
# 步骤2：匹配六大板块（无映射的标为“其他”）
industry_holdings['六大板块'] = industry_holdings['申万二级行业'].map(src.const.const.INDUSTRYTOSECTOR_SW2FOF2026).fillna('其他')
industry_holdings = industry_holdings[industry_holdings['持仓比例'] != '平均值']
# 步骤3：按板块分组计算持仓比例总和
plate_holdings = industry_holdings.groupby('六大板块')['持仓比例'].sum()
# 保留4位小数（符合金融数据精度要求）
# plate_holdings = plate_holdings.round(4)

plate_holdings.to_excel('885001板块比例_{}.xlsx'.format(date.strftime("%Y%m%d")))