# -----------------------------------------------------------------------
# 主观多头私募相关数据提取
# -----------------------------------------------------------------------
import pandas as pd
from src.data.amdata import *
import src.data.irm as irm
import datetime
import src.const as const
from src.const import *

# ------------------------------------------------------------------------
# 读取来自托管的主观多头私募拆分数据
# ------------------------------------------------------------------------
def ffd_getFundamentalFundsExposure(
    start_date,         # DateTime.date instance
    end_date,           # DateTime.date instance
    product_ids = None  # list
):
    conn = irm.irm_connectIRMDB()
    assert isinstance(start_date, datetime.date), "date must be an instance of datetime.date"
    assert isinstance(end_date, datetime.date), "date must be an instance of datetime.date"
    assert start_date <= end_date, "start_date must be smaller or equal to end_date"

    if product_ids == None: # 空的时候读取全部基金
        sql = "SELECT * FROM irm.amdata_src_fund_daily_iservice_stock_new WHERE D_DT >= DATE'{}' AND D_DT <= DATE'{}'"
        df = pd.read_sql_query(sql.format(start_date, end_date), conn).rename(columns=str.lower)
    else:
        sql = "SELECT * FROM irm.amdata_src_fund_daily_iservice_stock_new WHERE D_DT >= DATE'{}' AND D_DT <= DATE'{}' and c_secu_id in ({})"
        df = pd.read_sql_query(sql.format(start_date, end_date, ','.join(["'%s'" % x for x in product_ids])), conn).rename(columns=str.lower)

    df['d_dt'] = pd.to_datetime(df['d_dt']).dt.date  # convert timestamp to datetime.date
    # 统一量纲为1,fixed_columns_list 为不需要改变的列
    fixed_columns_list = ['d_dt', 'c_secu_id', 'product_name', 'n_turnover_this_year', 'n_turnover_near_one_month',
                        'n_turnover_near_one_year',  'n_market', 'n_btop', 'n_earnyild', 'n_sizenl', 'n_size',
                        'n_momentum', 'n_leverage', 'n_beta', 'n_resvol', 'n_liquidty', 'n_growth', 'n_accu_unit_val',
                        'n_net_asset_val', 'd_update_dt']
    adjusted_columns_list = list(set(df.columns)-set(fixed_columns_list))
    df[adjusted_columns_list] = df[adjusted_columns_list]/100
    rename_dict = dict(zip([x for x in df.columns if x.startswith('n_')], [x[2:] for x in df.columns if x.startswith('n_')]))
    rename_dict['d_dt'] = 'date'
    rename_dict['c_secu_id'] = 'product_id'
    df.rename(columns=rename_dict, inplace=True)
    hk_industry = pd.DataFrame({'chinese': const.HK_INDUSTRY_NAME_CN_TO_EN.keys(),
                                'english': const.HK_INDUSTRY_NAME_CN_TO_EN.values()})
    sw_industry = pd.DataFrame({'chinese': const.SW_INDUSTRY_NAME_CN_TO_EN.keys(),
                                'english': const.SW_INDUSTRY_NAME_CN_TO_EN.values()})
    df[hk_industry['english']] = df[hk_industry['english']].fillna(0)
    df[sw_industry['english']] = df[sw_industry['english']].fillna(0)
    df['stock'] = df['stock'].fillna(0)
    # 对大类资产分项进行合并
    df['future'] = df.filter(like='futures_').sum(axis=1)
    df['cash'] = df.filter(like='cash_').sum(axis=1)
    df['bond'] = df.filter(like='bond_').sum(axis=1)
    df['repo'] = df.filter(like='repo_').sum(axis=1)
    df['option'] = df.filter(like='option_').sum(axis=1)
    df['hf'] = df.filter(like='hf_').sum(axis=1)
    df['mf'] = df.filter(like='mf_').sum(axis=1)
    df['other_derivatives'] = df.filter(like='other_derivatives_').sum(axis=1)
    df['net_stock'] = df['stock'] + df['future'] # 股票净仓位，考虑是否加上option和derivative
    del df['product_name']
    conn.close()
    return df

