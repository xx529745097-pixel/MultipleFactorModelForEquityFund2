import numpy as np
import pandas as pd
import datetime
import math
import streamlit as st
import src.data.wind as wind
import src.data.amdata as amdata
import src.data.irm as irm
import src.utils.fof_calendar as calendar
import src.utils.Calculation as cal
import src.data.custHF as custHF
import src.data.custFOF as custFOF
import src.data.custMF as custMF
import src.data.wind as wd
import src.data.zyyx as zyyx
import src.data.wind_cached as wind_cached
import src.data.zyyx_cached as zyyx_cached
import src.analysis.basicAnalysis as basicAnalysis
import src.analysis.MFAnalysis as MFAnal
import src.analysis.fundamentalFundAnalysis as FFAnal
import src.analysis.quantFundAnalysis as QFAnal
import src.config as config
import src.const as const
from dateutil.relativedelta import relativedelta
import calendar as util_calendar
import copy
import traceback
from tqdm import tqdm
# ------------------------------------------------------
# 输入产品数据和持仓数据，按照portfolio_oa_id合并持仓数据
# ------------------------------------------------------
def _merge_portfolio_ref_and_holding(
    ref_data,       # 产品数据
    holding_data    # 产品持仓数据
):
    del holding_data['portfolio_name'], holding_data['inception_date'], holding_data['portfolio_id']
    combined_data = ref_data.merge(holding_data, on='portfolio_oa_id')
    return combined_data
# ------------------------------------------------------
# 从一级标签到配置层面的映射
# ------------------------------------------------------
def _allocation_type_mapping(level_1):
    if level_1 in ['主观权益', '指数增强', '行业主题', 'ETF']:
        return '权益'
    elif level_1 == '期货策略':
        return 'CTA'
    elif level_1 in ['债券策略', '套利策略', '量化对冲']:
        return '绝对收益'
    elif level_1 in ['复合策略', '宏观策略']:
        return '复合策略'
    elif level_1 in ['货币基金']:
        return '货币基金'
    elif level_1 in ['Reits']:
        return 'Reits'
    else:
        return '其他'

# ------------------------------------------------------
# 给FOF组合底层资产贴上标签类信息
# ------------------------------------------------------
def _append_product_label_info(
    holding_data,
    include_company_strategy_info=False,    # 输出的表格是否需要加上策略和公司的名称信息列
    mf_wind_allocation_type=False,          # 是否需要结合wind标签信息，给公募产品打上权益类的大类资产标签，默认不使用
):
    hf_ref_data = custHF.custHF_getProductInfo().rename(columns={'company_short_name': 'company_name'})
    mf_ref_data = custMF.custMF_getMFProductInfo().rename(columns={'company_legal_name': 'company_name'})
    hf_ref_data['hf_mf_type'] = '私募'
    mf_ref_data['hf_mf_type'] = '公募'
    col = ['product_id', 'label_level_1', 'label_level_2', 'hf_mf_type'] + (['company_id', 'company_name', 'strategy_id', 'strategy_name'] if include_company_strategy_info else [])
    ref_data = hf_ref_data[col].append(mf_ref_data[col])
    # 批量导入的公募数据来自于wind, wind的产品id会有不完备的情况，例如货基可场内交易但无场内代码，导致与持仓数据中的id后缀不匹配。
    # 目前解决方式是按照代码前六位(.OF之前的ID)来merge，已验证无重复
    ref_data['aux_product_id'] = ref_data['product_id'].str.split('.', expand=True)[0]
    del ref_data['product_id']
    holding_data['aux_product_id'] = holding_data.apply(lambda x: x['product_id'].split('.')[0] if ('基金' in str(x['product_type']) or '信托' in str(x['product_type'])) else x['product_id'], axis=1) if not holding_data.empty else ''
    result = holding_data.merge(ref_data, on='aux_product_id', how='left')
    result['hf_mf_type'].fillna(value='其他', inplace=True)
    result['label_level_1'].fillna(value='其他', inplace=True)
    result['label_level_2'].fillna(value='其他', inplace=True)
    if include_company_strategy_info:
        result['company_name'].fillna(value='其他', inplace=True)
        result['strategy_name'].fillna(value='其他', inplace=True)
    result['allocation_type'] = result['label_level_1'].apply(lambda x: _allocation_type_mapping(x))
    if mf_wind_allocation_type:
        mf_wind_info = wd.wind_getCurrentProductList(only_a_share=False)[['product_id', 'type']].rename(columns={'type': 'wind_type'})
        mf_wind_info['aux_product_id'] = mf_wind_info['product_id'].str.split('.', expand=True)[0]
        result = pd.merge(result, mf_wind_info[['aux_product_id', 'wind_type']], on='aux_product_id', how='left')
        result['allocation_type'] = result.apply(lambda x: '权益' if (x['allocation_type'] == '其他' and x['wind_type'] in const.const.EQUITY_MF_WIND_SECTOR_CODE_MAP.values()) else x['allocation_type'], axis=1)
        del result['wind_type']
    del result['aux_product_id']
    return result

# ------------------------------------------------------
# 获取各层级最新持有规模信息，数据来源取T至T-45各账户最新持仓数据
# ------------------------------------------------------
def anlsFOF_getCurrentHoldingInfo(
    date,   # 获取持仓日期
    data_level='Product'  # 数据层级, 可选择'Product', 'Strategy', 'Company'
):
    assert data_level in ('Product', 'Strategy', 'Company'), "'data_level'需为'Product', 'Strategy'或'Company'"
    # 取出各账户最新持仓数据, 使用ref_data筛选当前未清算账户(非投顾账户仅保留'正常运作'类型)
    ref_data = custFOF.custFOF_getFOFReferenceData(include_advisory_account=True, include_portfolio_oa_id=True)
    holding_data = custFOF.custFOF_getFOFHoldingData(date-datetime.timedelta(days=45), date, include_portfolio_oa_id=True).sort_values(['portfolio_oa_id', 'date'], ascending=True)
    holding_data = holding_data[holding_data['portfolio_oa_id'].isin(ref_data['portfolio_oa_id'].to_list())]
    holding_data = pd.merge(holding_data, holding_data.groupby(['portfolio_oa_id'], as_index=False).agg({'date': 'last'}).rename(columns={'date': 'latest_holding_date'}), on='portfolio_oa_id', how='left')
    holding_data = holding_data[holding_data['date'] == holding_data['latest_holding_date']]
    holding_data = _append_product_label_info(holding_data, include_company_strategy_info=True).sort_values(['company_id', 'strategy_id', 'product_id', 'latest_holding_date'])
    level_mapping = {
        'Product': {'groupby_col': ['product_id'], 'info_col': ['product_name', 'product_type', 'label_level_1', 'label_level_2', 'hf_mf_type', 'company_id', 'company_name', 'strategy_id', 'strategy_name', 'allocation_type']},
        'Strategy': {'groupby_col': ['strategy_id'], 'info_col': ['strategy_name', 'label_level_1', 'label_level_2', 'hf_mf_type', 'company_id', 'company_name', 'allocation_type']},
        'Company': {'groupby_col': ['company_id'], 'info_col': ['company_name', 'hf_mf_type']}
    }
    groupby_cols = level_mapping[data_level]['groupby_col']
    result = holding_data.groupby(groupby_cols, as_index=False).agg({'product_NAV': 'sum', 'latest_holding_date': 'last'}).rename(columns={'product_NAV': 'total_NAV'})
    result['date'] = date
    result = result[['date']+groupby_cols+['total_NAV', 'latest_holding_date']]
    info_cols = level_mapping[data_level]['info_col']
    result = pd.merge(result, holding_data[groupby_cols+info_cols].groupby(groupby_cols, as_index=False).first(), on=groupby_cols, how='left')
    return result

# -----------------------------------------------------------------------------------
# 获取投资组合带有负债项、并且各产品收益(包括交易涉及的费用、业绩报酬、应去除的浮盈浮亏、客户申赎带来的影响)已配平的持仓表
# 配平是指各项收益率每日合并后为账户净值的真实收益率，作为Mirabelli模型的基础数据输入
# -----------------------------------------------------------------------------------
def anlsFOF_restoreFOFHoldingValuationSheet(
    start_date,
    end_date,
    portfolio_id,   # 投资组合的ID, str
):
    holding_data = custFOF.custFOF_getFOFHoldingData(start_date, end_date, [portfolio_id], include_portfolio_oa_id=True)

    # STEP 1 处理正负清算款合并的问题
    # 如果沪深证券清算款存在一正一负的情况（常见于公募户），会计准则上应将正的记为资产，负的记为负债；但IT的持仓数据无法细化至这一步，只能够将清算款合并为一项，
    # 故需要将这种情况的持仓数据加入一个补充项，使得表中除负债端的数据之外所体现的为资产端且求和为资产总值
    clearance_supplement = holding_data.groupby('date', as_index=False).agg({'portfolio_oa_id': 'last', 'portfolio_name': 'last',
                            'portfolio_id': 'last', 'inception_date': 'last', 'NAV': 'last', 'total_NAV': 'last', 'total_share': 'last', 'VAL': 'sum'})
    clearance_supplement = clearance_supplement[clearance_supplement['total_NAV'] - clearance_supplement['VAL'] >= const.const.EPSILON]
    if not clearance_supplement.empty:
        clearance_supplement['product_id'] = 'CLEARANCE_AMT_SUPPLE'
        clearance_supplement['product_name'] = '证券清算款补充项'
        clearance_supplement['product_type'] = '证券清算款补充项'
        clearance_supplement['VAL'] = clearance_supplement['total_NAV'] - clearance_supplement['VAL']
        clearance_supplement['COST'] = clearance_supplement['VAL']
        holding_data = pd.concat([holding_data, clearance_supplement]).sort_values('date').reset_index(drop=True).fillna(0)  # 只会对这一新增的行进行fill，所fill的数据均是需要置0的损益类数据列

    # STEP 2 将负债端的条目加入持仓数据
    # 基于净资产的视角去计算负债端以及其变化，负债数值为负，变化值为负代表负债增加，对净资产的影响为负
    # 计算完成后append到holding_data下方
    asset_liability_data = holding_data.groupby('date', as_index=False)[['portfolio_oa_id', 'portfolio_name', 'portfolio_id', 'inception_date', 'NAV', 'total_NAV', 'total_share']].last()
    asset_liability_data['product_id'] = 'LIABILITY'
    asset_liability_data['product_name'] = '账户负债类合计'
    asset_liability_data['product_type'] = '负债端'
    asset_liability_data['VAL'] = asset_liability_data['NAV'] - asset_liability_data['total_NAV']
    asset_liability_data['product_daily_ret'] = asset_liability_data['VAL'].diff()
    holding_balance = pd.concat([holding_data, asset_liability_data]).sort_values('date').reset_index(drop=True)

    # 初步得到具有负债项的持仓表，并检查每日持仓规模求和是否等于每日净资产
    holding_balance_NAV_sum_check = holding_balance.groupby('date', as_index=False).agg({'NAV': 'last', 'VAL': 'sum'})
    holding_balance_NAV_sum_check['NAV_diff'] = holding_balance_NAV_sum_check['NAV'] - holding_balance_NAV_sum_check['VAL']
    assert holding_balance_NAV_sum_check['NAV_diff'].sum() < const.const.EPSILON, "需检查持仓数据负债端的计算误差"

    # STEP 3 处理收益数据
    # 得到带有负债的持仓表后，应检查每日净资产的变化是否与各持仓标的product_daily_ret求和结果一致
    # 如果不一致则需检查是否发生如下情况：
    # 1. 账户一般季度性扣除两费，负债会周期跳跃式减少，但现金项的变化未体现出来；需要对两费扣除当天的现金项作处理，体现现金product_daily_ret的变化
    # 2. 持仓产品全部赎回时，按照T日申请交易的价格结算，但T+1日未确认时仍有估值变化(浮盈浮亏)，T+2确认交易后所得证券清算款会反向进行增减以将最后实际发生的赎回金额置为T日价格所对应的金额且不体现在product_daily_ret中，
    # 此情况应对将T日之后的浮盈浮亏移至现金项，再将确认日(T+2日)所产生的重置变化也体现在现金项中，以保证对赎回产品归因的准确性
    # 全部赎回如果产生费用、业绩报酬，目前只体现在了现金的变化中，（因全部赎回的确认日当天估值表中已没有这一产品），需额外在持仓数据中加入一项持仓为0但有收益贡献金额的产品数据，去体现费用和业绩报酬的变化。
    # 2.1 持仓私募产品发生部分赎回时，与上述过程类似，申请和确认日期之间赎回部分会产生浮盈浮亏；将T日之后的浮盈浮亏（直接按照比例计算）移至现金项
    # 产生的费用和业绩报酬数据（TOT_EXPENSE，如有）也已计入该产品项的product_daily_ret当日损益，相当于在确认日(T+2日)计入当日的贡献，无需再做额外处理
    # 2.2 公募ETF发生全部赎回（场内交易）时，T+0确认，T日估值表上该产品也会消失，会导致当日交易的损益无法归因到该产品上，需额外在持仓数据中加入一项持仓为0但有收益贡献金额的产品数据，去体现交易当天的损益
    # 2.3 公募发生场外全部赎回，且交易存在费用、业绩报酬时，同样需要将其体现至产品层面
    # 上述情况2中提到的在确认日将浮盈浮亏重置过程体现在现金项变化（product_daily_ret）的动作是最后统一进行的
    # 3. 账户可能发生了追加投资或者部分赎回，这种情况在后续计算收益率贡献的部分进行放缩处理
    # 4. 对于其他情况assert出来报错

    # STEP 3-1 对私募、公募产品赎回的情况进行处理
    # 先对情况2进行预处理，对于全部赎回的私募产品，在交易申请之后确认之前的浮盈浮亏放置到现金项里，保证对赎回产品归因的准确性；
    trade_data = custFOF.custFOF_getActualTradeHistoricalFlowFromCAMP(start_date, end_date, [portfolio_id])

    # 私募的赎回的数据
    hf_trade_data = trade_data[(trade_data['trade_type'] == '卖出') & (trade_data['product_type'] == '私募基金')]
    for index, row in hf_trade_data.iterrows():
        # 全部赎回的私募产品
        if len(holding_balance[(holding_balance['product_id'] == row['product_id']) & (holding_balance['date'] == row['trade_date'])]) \
            and row['trade_volume'] == holding_balance[(holding_balance['product_id'] == row['product_id']) & (holding_balance['date'] == row['trade_date'])]['product_volume'].iloc[0]:
            # 将申请日（不含）至确认日（不含）之间的浮盈浮亏移至现金项
            for i in range(1, (row['trade_confirm_date'] - row['trade_date']).days):
                today = row['trade_date'] + datetime.timedelta(i)
                holding_balance_today = holding_balance[(holding_balance['date'] == today) & (holding_balance['product_id'] == row['product_id'])]
                if holding_balance_today.empty:
                    continue
                float_return = holding_balance_today['product_daily_ret'].iloc[0]
                holding_balance.loc[(holding_balance['date'] == today) & (holding_balance['product_id'] == row['product_id']), 'product_daily_ret'] = 0
                holding_balance.loc[(holding_balance['date'] == today) & (holding_balance['product_type'] == '活期存款'), 'product_daily_ret'] += float_return
            # 如果全部赎回的交易存在费用、业绩报酬，需要将其体现至产品层面（判断逻辑：成交金额不等于申请日的产品持仓金额）
            if row['trade_amount'] != holding_balance[(holding_balance['product_id'] == row['product_id']) & (holding_balance['date'] == row['trade_date'])]['VAL'].iloc[0]:
                today = row['trade_date']
                # 该笔全部赎回交易的费用、业绩报酬（负值）
                fee = row['trade_amount'] - holding_balance[(holding_balance['product_id'] == row['product_id']) & (holding_balance['date'] == row['trade_date'])]['VAL'].iloc[0]
                holding_balance.loc[(holding_balance['date'] == today) & (holding_balance['product_id'] == row['product_id']), 'product_daily_ret'] += fee
        # 部分赎回的私募产品
        if len(holding_balance[(holding_balance['product_id'] == row['product_id']) & (holding_balance['date'] == row['trade_date'])]) \
            and row['trade_volume'] < holding_balance[(holding_balance['product_id'] == row['product_id']) & (holding_balance['date'] == row['trade_date'])]['product_volume'].iloc[0]:
            # 将申请日（不含）至确认日（不含）之间的浮盈浮亏(按份额比例进行计算)移至现金项
            for i in range(1, (row['trade_confirm_date'] - row['trade_date']).days):
                today = row['trade_date'] + datetime.timedelta(i)
                holding_balance_today = holding_balance[(holding_balance['date'] == today) & (holding_balance['product_id'] == row['product_id'])]
                if holding_balance_today.empty:
                    continue
                # float_return是赎回的份额所产生的浮盈浮亏金额
                float_return = holding_balance_today['product_daily_ret'].iloc[0] * row['trade_volume'] / holding_balance_today['product_volume'].iloc[0]
                holding_balance.loc[(holding_balance['date'] == today) & (holding_balance['product_id'] == row['product_id']), 'product_daily_ret'] -= float_return
                holding_balance.loc[(holding_balance['date'] == today) & (holding_balance['product_type'] == '活期存款'), 'product_daily_ret'] += float_return

    # 公募的场内的赎回数据（使用申请日==确认日去判断）
    mf_exchange_trade_data = trade_data[(trade_data['trade_type'] == '卖出') & (trade_data['product_type'] == '公募基金') & (trade_data['trade_date'] == trade_data['trade_confirm_date'])]
    # 分多笔交易形成的全部赎回无法直接判断出来，故对交易进行加总处理，再进行判断
    mf_exchange_trade_data = mf_exchange_trade_data.groupby(['trade_date'], as_index=False).agg({'product_id': 'last', 'trade_volume': 'sum', 'trade_amount': 'sum'})
    for index, row in mf_exchange_trade_data.iterrows():
        # 全部赎回的公募ETF
        if len(holding_balance[(holding_balance['product_id'] == row['product_id']) & (holding_balance['date'] == row['trade_date'] - datetime.timedelta(1))]) \
            and row['trade_volume'] == holding_balance[(holding_balance['product_id'] == row['product_id']) & (holding_balance['date'] == row['trade_date'] - datetime.timedelta(1))]['product_volume'].iloc[0]:
            today = row['trade_date']
            holding_balance_today = holding_balance[(holding_balance['date'] == today)]
            holding_balance_yesterday = holding_balance[(holding_balance['date'] == today - datetime.timedelta(1)) & (holding_balance['product_id'] == row['product_id'])]
            if holding_balance_yesterday.empty:
                continue
            float_return = row['trade_amount'] - holding_balance_yesterday['VAL'].iloc[0]
            holding_balance = holding_balance.append({
                'NAV': holding_balance_today['NAV'].iloc[0],
                'total_NAV': holding_balance_today['total_NAV'].iloc[0],
                'total_share': holding_balance_today['total_share'].iloc[0],
                'date': today,
                'product_id': holding_balance_yesterday['product_id'].iloc[0],
                'product_name': holding_balance_yesterday['product_name'].iloc[0],
                'product_type': holding_balance_yesterday['product_type'].iloc[0],
                'product_daily_ret': float_return,
            }, ignore_index=True)
            holding_balance.loc[(holding_balance['date'] == today) & (holding_balance['product_type'] == '活期存款'), 'product_daily_ret'] -= float_return
    holding_balance[['portfolio_oa_id', 'portfolio_name', 'portfolio_id', 'inception_date']] = holding_balance[['portfolio_oa_id', 'portfolio_name', 'portfolio_id', 'inception_date']].fillna(method='ffill')
    holding_balance = holding_balance.sort_values('date').reset_index(drop=True).fillna(0)  # 只会对补充上的行进行fill，所fill的数据均是需要置0的损益类数据列

    # 公募的场外的赎回数据（使用申请日!=确认日去判断）
    mf_otc_trade_data = trade_data[(trade_data['trade_type'] == '卖出') & (trade_data['product_type'] == '公募基金') & (trade_data['trade_date'] != trade_data['trade_confirm_date'])]
    # 分多笔交易形成的全部赎回无法直接判断出来，故对交易进行加总处理，再进行判断
    mf_otc_trade_data = mf_otc_trade_data.groupby(['trade_date'], as_index=False).agg({'product_id': 'last', 'trade_volume': 'sum', 'trade_amount': 'sum'})
    for index, row in mf_otc_trade_data.iterrows():
        # 全部赎回的公募产品，且交易存在费用、业绩报酬，需要将其体现至产品层面（判断逻辑：成交金额不等于申请日的产品持仓金额）
        if len(holding_balance[(holding_balance['product_id'] == row['product_id']) & (holding_balance['date'] == row['trade_date'])]['product_volume']) \
            and row['trade_volume'] == holding_balance[(holding_balance['product_id'] == row['product_id']) & (holding_balance['date'] == row['trade_date'])]['product_volume'].iloc[0]\
            and row['trade_amount'] != holding_balance[(holding_balance['product_id'] == row['product_id']) & (holding_balance['date'] == row['trade_date'])]['VAL'].iloc[0]:
            today = row['trade_date']
            # 该笔全部赎回交易的费用、业绩报酬（负值）
            fee = row['trade_amount'] - holding_balance[(holding_balance['product_id'] == row['product_id']) & (holding_balance['date'] == row['trade_date'])]['VAL'].iloc[0]
            holding_balance.loc[(holding_balance['date'] == today) & (holding_balance['product_id'] == row['product_id']), 'product_daily_ret'] += fee

    # STEP 3-2 检查收益数据，对私募、公募产品赎回的情况中未配平的现金项统一补齐
    holding_balance_return_check = holding_balance.groupby('date', as_index=False).agg({'NAV': 'last', 'total_share': 'last','product_daily_ret': 'sum'})
    holding_balance_return_check['NAV_change'] = holding_balance_return_check['NAV'].diff()
    holding_balance_return_check['total_share_change'] = holding_balance_return_check['total_share'].diff()  # 实收资本的变化，用来判断账户自身是否发生了追加或赎回
    holding_balance_return_check['product_daily_ret_diff'] = holding_balance_return_check['NAV_change'] - holding_balance_return_check['product_daily_ret']
    holding_balance_return_check = holding_balance_return_check[(holding_balance_return_check['product_daily_ret_diff'].abs() > const.const.EPSILON) | (holding_balance_return_check['total_share_change'].abs() > const.const.EPSILON)]

    # 对除了情况3（账户客户存在追加投资或赎回）之外的情况，统一将现金项的损益配平，以实现该部分的每日收益金额和每日的资产净值变化所匹配
    for index, row in holding_balance_return_check.iterrows():
        if abs(row['total_share_change']) == 0:
            # 该情况属于情况1、2，在现金项进行补偿；统一处理，同样效果
            # （否则该情况是账户存在追加投资或赎回，属于情况3，需要在下面的步骤将收益率贡献进行处理，细化拆分 产品实际贡献和申赎影响对于账户净值的收益贡献）
            holding_balance.loc[(holding_balance['date'] == row['date']) & (holding_balance['product_type'] == '活期存款'), 'product_daily_ret'] += row['product_daily_ret_diff']

    # STEP 3-3 处理账户客户存在追加投资或赎回的情况
    # 到这一步情况1、2的数据都已处理完毕，下面对情况3的当天收益贡献进行细化处理
    portfolio_ret = holding_balance.groupby('date')[['NAV', 'total_share']].last()
    portfolio_ret['valuation_unit_NAV'] = portfolio_ret['NAV'] / portfolio_ret['total_share']  # 这里直接使用 资产净值/实收资本份额 的方式计算单位净值，不保留四位小数，为原始数据，统一标准
    portfolio_ret['portfolio_return'] = portfolio_ret['valuation_unit_NAV'].pct_change(1)
    portfolio_ret = portfolio_ret.reset_index()
    holding_balance_with_ret = pd.merge(holding_balance, portfolio_ret[['date', 'portfolio_return']], on=['date'], how='left')
    T_1_NAV = pd.DataFrame(holding_balance_with_ret.groupby('date')[['NAV', 'total_share']].last().shift(1)).reset_index().rename(columns={'NAV': 'T-1_NAV', 'total_share': 'T-1_total_share'})
    holding_balance_with_ret = pd.merge(holding_balance_with_ret, T_1_NAV, on='date', how='left')
    # 产品当日的收益贡献
    holding_balance_with_ret['product_return_attribution'] = holding_balance_with_ret['product_daily_ret']/holding_balance_with_ret['T-1_NAV']
    holding_balance_with_ret['product_return_attribution_sum'] = holding_balance_with_ret.groupby('date')['product_return_attribution'].transform('sum')

    for index, row in holding_balance_return_check.iterrows():
        if abs(row['total_share_change']) > 0:
            # 该情况是账户存在追加投资或赎回，属于情况3，需要将收益率贡献进行处理，细化拆分 产品实际贡献和申赎影响对于账户净值的收益贡献
            # 持有产品的收益贡献：
            today_holding_balance_with_ret = holding_balance_with_ret.loc[(holding_balance_with_ret['date'] == row['date'])]
            holding_balance_with_ret.loc[(holding_balance_with_ret['date'] == row['date']), 'product_return_attribution'] *= \
                holding_balance_with_ret.loc[(holding_balance_with_ret['date'] == row['date']), 'T-1_total_share'] / holding_balance_with_ret.loc[(holding_balance_with_ret['date'] == row['date']), 'total_share']
            # 剩下的部分是申赎资金带来的影响
            holding_balance_with_ret = holding_balance_with_ret.append({
                'NAV': today_holding_balance_with_ret['NAV'].iloc[0],
                'total_NAV': today_holding_balance_with_ret['total_NAV'].iloc[0],
                'total_share': today_holding_balance_with_ret['total_share'].iloc[0],
                'T-1_NAV': today_holding_balance_with_ret['T-1_NAV'].iloc[0],
                'T-1_total_share': today_holding_balance_with_ret['T-1_total_share'].iloc[0],
                'portfolio_return': today_holding_balance_with_ret['portfolio_return'].iloc[0],
                'date': row['date'],
                'product_id': 'SUBSCRIPTION_REDEEM',
                'product_name': '客户申赎影响',
                'product_type': '客户申赎影响',
                'product_return_attribution': holding_balance_with_ret.loc[(holding_balance_with_ret['date'] == row['date']), 'portfolio_return'].iloc[0] - holding_balance_with_ret.loc[(holding_balance_with_ret['date'] == row['date']), 'product_return_attribution'].sum(),
            }, ignore_index=True)
            holding_balance_with_ret[['portfolio_oa_id', 'portfolio_name', 'portfolio_id', 'inception_date']] = holding_balance_with_ret[['portfolio_oa_id', 'portfolio_name', 'portfolio_id', 'inception_date']].fillna(method='ffill')
            holding_balance_with_ret = holding_balance_with_ret.sort_values('date').reset_index(drop=True).fillna(0)  # 只会对补充上的行进行fill，所fill的数据均是需要置0的损益类数据列

    # STEP 4 至此已完成对持仓数据的处理，得到资产和收益都配平的、且包含每个产品每日收益贡献的持仓表，最后进行检查
    holding_balance_with_ret['product_return_attribution_sum'] = holding_balance_with_ret.groupby('date')['product_return_attribution'].transform('sum')
    holding_balance_return_attribution_check = holding_balance_with_ret.groupby('date').agg({'portfolio_return': 'last', 'product_return_attribution_sum': 'last'})
    holding_balance_return_attribution_check['return_attibution_diff'] = holding_balance_return_attribution_check['product_return_attribution_sum'] - holding_balance_return_attribution_check['portfolio_return']
    holding_balance_return_attribution_check = holding_balance_return_attribution_check[holding_balance_return_attribution_check['return_attibution_diff'].abs() > const.const.EPSILON]
    assert len(holding_balance_return_attribution_check) == 0, "需检查收益贡献数据的计算误差"

    return holding_balance_with_ret

# ---------------------------------------------------------------------
# 获取FOF账户在指定区间内的Mirabelli收益率归因的基础数据(逐日逐产品最细的结果)
# 基础数据是指具体到每一持仓的收益贡献数据，后续可根据各类别和区间进行合并计算
# 注意：该函数输出的Mirabelli结果与起始日期是相关的，不可取中间部分区间进行合并计算（求和不会等于中间区间的总收益）
# 注意：为了与网站选择日期（基于收益率数据）的逻辑相一致，使用时需要将网站所选起始日期往前推一个交易日
# ---------------------------------------------------------------------
@st.cache_data(ttl=86400, show_spinner=False)
def anlsFOF_getFOFMirabelliAttributionDetails(
    start_date,
    end_date,
    portfolio_id,  # 投资组合的ID, str
):
    holding_balance_with_ret = anlsFOF_restoreFOFHoldingValuationSheet(start_date, end_date, portfolio_id)
    if holding_balance_with_ret.empty:
        return holding_balance_with_ret
    holding_balance_with_cumprod_ret = holding_balance_with_ret.groupby('date').agg({'portfolio_return': 'last', 'product_return_attribution_sum': 'last'})
    holding_balance_with_cumprod_ret = ((holding_balance_with_cumprod_ret+1).cumprod() - 1).rename(columns={'product_return_attribution_sum': 'portfolio_cumprod_ret'})
    holding_balance_with_cumprod_ret['portfolio_cumprod_ret_shift_1'] = holding_balance_with_cumprod_ret['portfolio_cumprod_ret'].shift(1)
    holding_balance_with_cumprod_ret = holding_balance_with_cumprod_ret[['portfolio_cumprod_ret', 'portfolio_cumprod_ret_shift_1']].reset_index()
    holding_balance_with_ret = pd.merge(holding_balance_with_ret, holding_balance_with_cumprod_ret, on='date', how='left')
    holding_balance_with_ret['product_mirabelli_attribution'] = holding_balance_with_ret['product_return_attribution'] * (1 + holding_balance_with_ret['portfolio_cumprod_ret_shift_1'])
    mirabelli_attribution_result = _append_product_label_info(holding_balance_with_ret, include_company_strategy_info=True)
    # 此处手动处理一下，将负债端、活期存款、证券清算款（含补充项）、客户申赎影响 等这些项目在各资产层级的类别置为同一项："费用及杂项"
    if len(mirabelli_attribution_result):
        sector_label_col = ['product_type', 'label_level_1', 'label_level_2', 'allocation_type', 'company_name', 'strategy_name', 'product_name']
        mirabelli_attribution_result[sector_label_col] = mirabelli_attribution_result.apply(lambda x: tuple(['费用及杂项']*7) if x['product_type'] in
                                                        ['负债端', '活期存款', '证券清算款', '证券清算款补充项', '客户申赎影响', '应收利息', '应收红利', '备付金', '存出保证金', '增值税', '其它资产']
                                                        else tuple(x[col] for col in sector_label_col), axis=1, result_type='expand')
    return mirabelli_attribution_result

# ---------------------------------------------------------------------
# 获取FOF账户在指定区间内的Mirabelli收益率归因按照选择分类层级的汇总数据
# ---------------------------------------------------------------------
def anlsFOF_getFOFMirabelliAttributionbySector(
    portfolio_id,  # 投资组合的ID, str
    date,
    period,
    start_date=None,
    level='product_type',  # Other options: 'label_level_1', 'label_level_2', 'allocation_type', 'company_name', 'strategy_name', 'product_name'
):
    assert period in ('YTD', 'YTLDLM', '2024', '2023', '2022', '2021', '2020', '2019', 'SI', 'Customized', 'Today'), \
        "统计区间，只能为YTD, 2022, 2021, 2020, 2019, Today 以及SI（均为字符串格式）"
    assert level in ('product_type', 'label_level_1', 'label_level_2', 'allocation_type', 'company_name', 'strategy_name', 'product_name'), "所选汇总类别不支持"
    start_date, end_date = calendar.calender_getStartEndDate(period, date, start_date)
    # 取start_date之前的上一个交易日
    wind_calender = wd.wind_getSSECalendar()
    wind_calender_history = wind_calender.loc[(wind_calender['date'] < start_date), 'date']
    start_date = wind_calender_history.iloc[-1]
    assert end_date > start_date, "起始日期晚于结束日期"

    level_col_map = {
        'groupby': {
            'allocation_type': ['allocation_type'],
            'product_type': ['product_type'],
            'label_level_1': ['allocation_type', 'label_level_1'],
            'label_level_2': ['allocation_type', 'label_level_1', 'label_level_2'],
            'company_name': ['company_name'],
            'strategy_name': ['label_level_1', 'strategy_name'],
            'product_name': ['label_level_1', 'strategy_name', 'product_name'],
        },
        'sort': {
            'allocation_type': ['product_mirabelli_attribution'],
            'product_type': ['product_mirabelli_attribution'],
            'label_level_1': ['allocation_type', 'product_mirabelli_attribution'],
            'label_level_2': ['allocation_type', 'label_level_1', 'product_mirabelli_attribution'],
            'company_name': ['product_mirabelli_attribution'],
            'strategy_name': ['label_level_1', 'product_mirabelli_attribution'],
            'product_name': ['label_level_1', 'strategy_name', 'product_mirabelli_attribution'],
        },
    }
    mirabelli_attribution_result = anlsFOF_getFOFMirabelliAttributionDetails(start_date, end_date, portfolio_id)
    if mirabelli_attribution_result.empty:
        return mirabelli_attribution_result
    mirabelli_attribution_by_sector = mirabelli_attribution_result.groupby(['portfolio_name'] + level_col_map['groupby'][level], as_index=False)['product_mirabelli_attribution'].sum().\
                                        sort_values(level_col_map['sort'][level], ascending=False)
    mirabelli_attribution_by_sector = mirabelli_attribution_by_sector.append({'portfolio_name': mirabelli_attribution_by_sector['portfolio_name'].iloc[0], level: '总计',
                                                                              'product_mirabelli_attribution': mirabelli_attribution_by_sector['product_mirabelli_attribution'].sum()}, ignore_index=True)
    mirabelli_attribution_by_sector['start_date'] = mirabelli_attribution_result['date'].unique()[1].strftime('%Y-%m-%d')
    mirabelli_attribution_by_sector['end_date'] = mirabelli_attribution_result['date'].unique()[-1].strftime('%Y-%m-%d')
    return mirabelli_attribution_by_sector

# ---------------------------------------------------------------------
# 获取FOF账户在指定区间内的Mirabelli收益率归因时序图
# 时序图是各level按照时序累加的曲线，每一个截面上的收益率归因求和都等于截至当前时间点的收益率
# ---------------------------------------------------------------------
def anlsFOF_getFOFMirabelliAttributionCumSeries(
    portfolio_id,  # 投资组合的ID, str
    date,
    period,
    start_date=None,
    level='product_type',  # Other options: 'label_level_1', 'label_level_2', 'allocation_type', 'company_name', 'strategy_name', 'product_name'
):
    assert period in ('YTD', 'YTLDLM', '2024', '2023', '2022', '2021', '2020', '2019', 'SI', 'Customized','Today'), \
        "统计区间，只能为YTD, 2022, 2021, 2020, 2019, Today 以及SI（均为字符串格式）"
    assert level in ('product_type', 'label_level_1', 'label_level_2', 'allocation_type', 'company_name', 'strategy_name', 'product_name'), "所选汇总类别不支持"
    start_date, end_date = calendar.calender_getStartEndDate(period, date, start_date)
    # 取start_date之前的上一个交易日
    wind_calender = wd.wind_getSSECalendar()
    wind_calender_history = wind_calender.loc[(wind_calender['date'] < start_date), 'date']
    start_date = wind_calender_history.iloc[-1]
    assert end_date > start_date, "起始日期晚于结束日期"

    mirabelli_attribution_result = anlsFOF_getFOFMirabelliAttributionDetails(start_date, end_date, portfolio_id)
    mirabelli_attribution_series = mirabelli_attribution_result.groupby(['date', level], as_index=False)['product_mirabelli_attribution'].sum()
    port_ret_series = mirabelli_attribution_result.groupby(['date'], as_index=False)['product_mirabelli_attribution'].sum()
    port_ret_series[level] = '组合收益'

    mirabelli_attribution_series = pd.concat([mirabelli_attribution_series, port_ret_series]).sort_values('date').set_index('date')
    mirabelli_attribution_series['product_mirabelli_attribution_cumsum'] = mirabelli_attribution_series.groupby(level, as_index=False)['product_mirabelli_attribution'].cumsum()
    mirabelli_attribution_series.reset_index(inplace=True)
    mirabelli_attribution_series['portfolio_name'] = mirabelli_attribution_result['portfolio_name'].iloc[0]

    return mirabelli_attribution_series

# ---------------------------------------------------------------------
# 获取FOF账户在指定区间内 每个月收益率归因
# 按照每个自然月，对各level的收益贡献进行汇总
# ---------------------------------------------------------------------
def anlsFOF_getFOFMirabelliMonthlyAttribution(
    portfolio_id,  # 投资组合的ID, str
    date,
    num_trailing_month=6,  # 展示过去几个月的收益,默认6个月
    level='product_type',  # Other options: 'label_level_1', 'label_level_2', 'allocation_type', 'company_name', 'strategy_name', 'product_name'
):

    assert level in ('product_type', 'label_level_1', 'label_level_2', 'allocation_type', 'company_name', 'strategy_name', 'product_name'), "所选汇总类别不支持"

    month_start_date = datetime.date(date.year, date.month, 1)
    month_start_date_list = [month_start_date - relativedelta(months=i) for i in range(num_trailing_month)]
    month_date_list = [[date_i, datetime.date(date_i.year, date_i.month, util_calendar.monthrange(date_i.year, date_i.month)[1])] for date_i in month_start_date_list]
    month_date_list.reverse()
    month_date_list[-1][1] = date

    mirabelli_attribution_result = []
    for date_i in month_date_list:
        result = anlsFOF_getFOFMirabelliAttributionbySector(portfolio_id, date_i[1], 'Customized', date_i[0], level)
        if result.empty:
            continue
        result['start_date'] = date_i[0]
        result['end_date'] = date_i[1]
        mirabelli_attribution_result.append(result)
    mirabelli_monthly_attribution = pd.concat(mirabelli_attribution_result, ignore_index=True)
    mirabelli_monthly_attribution[level] = mirabelli_monthly_attribution[level].apply(lambda x: '组合收益' if x == '总计' else x)
    mirabelli_monthly_attribution['data_type'] = mirabelli_monthly_attribution[level].apply(lambda x: '组合收益' if x == '组合收益' else '归因')
    mirabelli_monthly_attribution['year'] = mirabelli_monthly_attribution['start_date'].apply(lambda x: x.year)
    mirabelli_monthly_attribution['month'] = mirabelli_monthly_attribution['start_date'].apply(lambda x: x.month)
    mirabelli_monthly_attribution['date'] = mirabelli_monthly_attribution.apply(lambda x: str(x['year']) + '-' + str(x['month']), axis=1)

    return mirabelli_monthly_attribution

# ------------------------------------------------------
# 获取投资组合底层各类策略及其对应比较基准的return
# ------------------------------------------------------
def anlsFOF_getFOFSubCategoryAndBMReturn(
    date,
    period,
    portfolio_id,
    sub_category,
    start_date=None,        # This parameter ONLY works for period list contains Customized
    mode='COMMON_ACCOUNT',  # 目前获取子策略收益序列支持两种模式：1. COMMON_ACCOUNT：非投顾账户，利用归因模型结果，对T日子策略贡献按照T-1权重进行放缩还原，形成收益率序列;
                            # 2.ADVISORY_ACCOUNT：投顾账户，直接利用子策略持仓权重，和可得的产品收益率进行计算
    customized_bm=None,     # 支持自定义选择对比基准，默认为None则使用默认config；如果选择则需给定{'benchmark_source': 'wind', 'benchmark': 'CAMO2.WI', 'name': '中信证券商品动量2.0'}结构的字典
):
    assert mode in ('COMMON_ACCOUNT', 'ADVISORY_ACCOUNT'), "子策略收益计算支持'COMMON_ACCOUNT', 'ADVISORY_ACCOUNT'两种模式，适用于非投顾账户和投顾账户"

    port_label_mapping = copy.deepcopy(config.port_label_mapping)
    # 支持对sub cate自定义比较基准
    # 为空或者CTA策略选择朝阳永续中位数，都属于默认选项不需要对config进行更新
    if customized_bm is not None and customized_bm['name'] != '朝阳永续中位数':
        port_label_mapping[sub_category]['benchmark_source'] = customized_bm['benchmark_source']
        port_label_mapping[sub_category]['benchmark'] = customized_bm['benchmark']
        port_label_mapping[sub_category]['name'] = customized_bm['name']

    start_date, end_date = calendar.calender_getStartEndDate(period, date, start_date)
    # 为了让首个周五的sub category portfolio的收益率是完整的，将其取数port_start_date提前15个自然日
    port_start_date = start_date - datetime.timedelta(15)
    holding_data = custFOF.custFOF_getFOFHoldingData(port_start_date, end_date, [portfolio_id])

    if mode == 'ADVISORY_ACCOUNT':
        if holding_data.empty:
            return holding_data
        holding_data = _append_product_label_info(holding_data)
        holding_data = holding_data[holding_data[port_label_mapping[sub_category]['label_level']].isin(port_label_mapping[sub_category]['label_key'])]
        # 获取Sub Category的底层产品return信息以及统一后的freq
        all_product_ret = basicAnalysis.basicAnal_adjustFreqOfMFAndHFReturn(port_start_date, end_date,
                                list(set(holding_data[holding_data['hf_mf_type'] == '公募']['product_id'].to_list())),
                                list(set(holding_data[holding_data['hf_mf_type'] == '私募']['product_id'].to_list())))
        if all_product_ret.empty:
            return all_product_ret
        holding_weight_sum = holding_data.groupby(['date'], as_index=False)['product_weight'].sum().rename(columns={'product_weight': 'weight_sum'})
        holding_data = pd.merge(holding_data, holding_weight_sum, on=['date'], how='left')
        holding_data['adj_weight'] = holding_data['product_weight'] / holding_data['weight_sum']
        holding_data = holding_data.merge(all_product_ret, on=['date', 'product_id'], how='left').dropna(axis=0, subset=['adj_return_rate', 'freq'])  # drop掉因为非交易日或因为频率不同导致的nan值
        # sub category return 加权求和
        sub_cate_ret = holding_data.groupby(['date'], as_index=False).agg({'adj_return_rate': lambda x: np.average(x, weights=holding_data.loc[x.index, 'adj_weight'])})
        sub_cate_ret['id'] = portfolio_id
    else:
        mirabelli_attribution = anlsFOF_getFOFMirabelliAttributionDetails(port_start_date, end_date, portfolio_id)
        if mirabelli_attribution.empty:
            return mirabelli_attribution
        sub_cate_mirabelli_attribution = mirabelli_attribution[mirabelli_attribution[port_label_mapping[sub_category]['label_level']].isin(port_label_mapping[sub_category]['label_key'])]
        sub_cate_mirabelli_attribution = sub_cate_mirabelli_attribution.groupby('date', as_index=False).agg({'product_weight': 'sum', 'product_return_attribution': 'sum'}).\
                                        rename(columns={'product_weight': 'sub_cate_weight', 'product_return_attribution': 'sub_cate_attribution'})
        sub_cate_mirabelli_attribution['sub_cate_weight_shift1'] = sub_cate_mirabelli_attribution['sub_cate_weight'].shift(1)
        sub_cate_mirabelli_attribution['adj_return_rate'] = sub_cate_mirabelli_attribution['sub_cate_attribution'] / sub_cate_mirabelli_attribution['sub_cate_weight_shift1']
        sub_cate_mirabelli_attribution['id'] = portfolio_id
        sub_cate_ret = sub_cate_mirabelli_attribution[['date', 'adj_return_rate', 'id']]
    sub_cate_freq = all_product_ret['freq'].iloc[0] if mode == 'ADVISORY_ACCOUNT' else 'D'

    # sub category 的收益率至此已取得，下面merge对应bm的收益率
    if port_label_mapping[sub_category]['benchmark_source'] == 'zyyx_cached':
        # benchmark zyyx week_return 是周频数据，故需要降频
        sub_cate_ret_w = calendar.calender_convertDailyReturnToWeekly(sub_cate_ret, 'date', 'adj_return_rate', 'id')
        benchmark_ret = zyyx_cached.zyyxCached_getCachedUnivDistribution(start_date, end_date, [port_label_mapping[sub_category]['benchmark']], ['week_return']).\
                        rename(columns={'0.5': 'bm_return_rate'})
        # inner join时由于benchmark_ret的日期是符合以start_date作为日期起点，sub_cate_ret_w前面用port_start_date多取的数字会被去除
        all_ret = pd.merge(sub_cate_ret_w[['date', 'adj_return_rate']], benchmark_ret[['date', 'bm_return_rate']]).dropna()
        all_ret['freq'] = 'W'
    elif port_label_mapping[sub_category]['benchmark_source'] == 'wind_cached':
        # 定制化benchmark
        benchmark_ret = wind_cached.windCached_getCustomizedIndexReturn(port_label_mapping[sub_category]['benchmark'], port_start_date, end_date, sub_cate_freq)
        benchmark_ret.rename(columns={'index_return': 'bm_return_rate'}, inplace=True)
        all_ret = pd.merge(sub_cate_ret[['date', 'adj_return_rate']], benchmark_ret[['date', 'bm_return_rate']])[1:]  # SI区间，首日收益率为nan，无意义，影响最大回撤计算
        all_ret = all_ret[(all_ret['date'] >= start_date) & (all_ret['date'] <= end_date)]
        all_ret['freq'] = sub_cate_freq
    else:
        # benchmark为wind指数，取数时根据freq调整
        benchmark_ret = wd.wind_getIndexData(port_label_mapping[sub_category]['benchmark'], port_start_date, end_date, sub_cate_freq, method='last')
        benchmark_ret['bm_return_rate'] = benchmark_ret['close_price'].pct_change()
        all_ret = pd.merge(sub_cate_ret[['date', 'adj_return_rate']], benchmark_ret[['date', 'bm_return_rate']]).dropna()
        all_ret = all_ret[(all_ret['date'] >= start_date) & (all_ret['date'] <= end_date)]
        all_ret['freq'] = sub_cate_freq
    all_ret['portfolio_id'] = portfolio_id
    all_ret['portfolio_name'] = holding_data['portfolio_name'].iloc[0]
    all_ret['sub_category'] = sub_category

    return all_ret

# ------------------------------------------------------
# 获取投资组合的重点持仓信息
# ------------------------------------------------------
def anlsFOF_getFOFTopHolding(
    date,
    pm_name=None,
    type=None,
    client_region=None,
    product_type=None,
    level='产品',
    rank_num=None # number
):
    if product_type not in ['私募基金','公募基金']:
        assert level == '产品', '只有当"产品类型"为"私募基金"或"公募基金"时,才可运行"策略"层级和"公司"层级的分析'
    holding_data = custFOF.custFOF_getFOFHoldingData(date, date, include_portfolio_oa_id=True)
    if product_type is not None:
        holding_data = holding_data[holding_data['product_type']==product_type]
    ref_data = custFOF.custFOF_getFOFReferenceData(pm_name, type, client_region, include_advisory_account=True, include_portfolio_oa_id=True)
    combined_data = _merge_portfolio_ref_and_holding(ref_data, holding_data)
    agg_data = combined_data.groupby(['product_id', 'product_name'], as_index=False)['product_NAV'].sum()
    total_aum = agg_data['product_NAV'].sum()
    agg_data['product_weight'] = agg_data['product_NAV']/total_aum
    if product_type == '公募基金':
        product_info = custMF.custMF_getMFProductInfo()
        product_info.rename(columns={'company_legal_name': 'company_short_name'}, inplace=True)
    elif product_type == '私募基金':
        product_info = custHF.custHF_getProductInfo()

    if level == '策略':
        agg_data = agg_data.merge(product_info[['product_id', 'strategy_id', 'strategy_name']], on='product_id', how='left')
        agg_data = agg_data.groupby(['strategy_id', 'strategy_name'], as_index=False).sum()
        agg_data.rename(columns={'strategy_id': 'ID', 'strategy_name': 'Name', 'product_NAV': 'NAV', 'product_weight': 'Weight'}, inplace=True)
    elif level == '公司':
        agg_data = agg_data.merge(product_info[['product_id', 'company_id', 'company_short_name']], on='product_id', how='left')
        agg_data = agg_data.groupby(['company_id', 'company_short_name'], as_index=False).sum()
        agg_data.rename(columns={'company_id': 'ID', 'company_short_name': 'Name', 'product_NAV': 'NAV', 'product_weight': 'Weight'}, inplace=True)
    else:
        agg_data.rename(columns={'product_id': 'ID', 'product_name': 'Name', 'product_NAV': 'NAV', 'product_weight': 'Weight'}, inplace=True)
    agg_data.sort_values(by='Weight', ascending=False, inplace=True)
    if rank_num is not None:
        agg_data = agg_data.iloc[:rank_num, ]
    agg_data.reset_index(drop=True, inplace=True)
    top_sum = agg_data.sum()
    agg_data = agg_data.append({'ID': '合计', 'Name': '合计', 'Weight': top_sum['Weight'], 'NAV': top_sum['NAV']}, ignore_index=True)
    return agg_data

# ------------------------------------------------------
# 获取投资组合的持仓类别信息
# 通过data_mode可选择获取截面还是时序数据，默认获取截面数据
# ------------------------------------------------------
def anlsFOF_getFOFSectorInfo(
    date,
    pm_name=None,
    type=None,
    client_region=None,
    level='product_type', # Other options: label_level_1, label_level_2, allocation_type
    portfolio_id=None,  # Default is all portfolios
    data_mode='CS',     # CS截面数据 TS时序数据
    start_date=None,    # 如果获取时序数据，需指定起始日期
    mf_wind_allocation_type=False,  # 是否需要结合wind标签信息，给公募产品打上权益类的大类资产标签，默认不使用
):
    assert level in ['product_type', 'label_level_1', 'label_level_2', 'allocation_type'], '输入的level有误，请重新输入'
    if data_mode == 'CS':
        assert start_date is None, "获取截面数据时请勿输入start_date"
    else:
        assert isinstance(start_date, datetime.date), "获取时序数据时请输入start_date"

    level_col_map = {
        'groupby': {
            'allocation_type': ['allocation_type'],
            'product_type': ['product_type'],
            'label_level_1': ['allocation_type', 'label_level_1'],
            'label_level_2': ['allocation_type', 'label_level_1', 'label_level_2'],
        },
        'sort': {
            'allocation_type': ['product_NAV'],
            'product_type': ['product_NAV'],
            'label_level_1': ['allocation_type', 'product_NAV'],
            'label_level_2': ['allocation_type', 'label_level_1', 'product_NAV'],
        },
    }
    holding_data = custFOF.custFOF_getFOFHoldingData(date if data_mode=='CS' else start_date, date, [portfolio_id] if portfolio_id else None, include_portfolio_oa_id=True)
    if portfolio_id is not None and {portfolio_id} <= set(const.const.STANDARD_PORT_ID_LIST):
        combined_data = holding_data
    else:
        ref_data = custFOF.custFOF_getFOFReferenceData(pm_name, type, client_region, include_advisory_account=True, include_portfolio_oa_id=True)
        combined_data = _merge_portfolio_ref_and_holding(ref_data, holding_data)
    if level in ['label_level_1', 'label_level_2', 'allocation_type']:
        combined_data = _append_product_label_info(combined_data, mf_wind_allocation_type=mf_wind_allocation_type)
    agg_data = combined_data.groupby(([] if data_mode=='CS' else ['date']) + level_col_map['groupby'][level], as_index=False)['product_NAV'].sum()
    agg_data = agg_data.sort_values(by=([] if data_mode=='CS' else ['date']) + level_col_map['sort'][level], ascending=False if data_mode=='CS' else True).reset_index(drop=True)
    agg_data.rename(columns={'product_NAV': 'sector_NAV'}, inplace=True)
    if data_mode == 'CS':
        agg_data['sector_weight'] = agg_data['sector_NAV'] / agg_data['sector_NAV'].sum()
    else:
        sector_nav_sum = agg_data.groupby(['date'])['sector_NAV'].sum().to_dict()
        agg_data['sector_weight'] = agg_data.apply(lambda x: x['sector_NAV']/sector_nav_sum[x['date']], axis=1)
    return agg_data

# ------------------------------------------------------
# 获取投资组合在两个日期间的持仓类别变动
# ------------------------------------------------------
def anlsFOF_getFOFSectorChange(
    start_date,     # 比较区间的起始日期
    end_date,       # 比较区间的结束日期
    portfolio_id,   # 单一的组合id, string形式
    level='product_type', # Other options: label_level_1, label_level_2, allocation_type
):
    level_col_map = {
        'merge': {
            'allocation_type': ['allocation_type'],
            'product_type': ['product_type'],
            'label_level_1': ['allocation_type', 'label_level_1'],
            'label_level_2': ['allocation_type', 'label_level_1', 'label_level_2'],
        },
        'sort': {
            'allocation_type': ['end_sector_weight'],
            'product_type': ['end_sector_weight'],
            'label_level_1': ['allocation_type', 'end_sector_weight'],
            'label_level_2': ['allocation_type', 'label_level_1', 'end_sector_weight'],
        },
    }
    start_sector = anlsFOF_getFOFSectorInfo(date=start_date, level=level, portfolio_id=portfolio_id).rename(columns={'sector_weight': 'start_sector_weight'})
    end_sector = anlsFOF_getFOFSectorInfo(date=end_date, level=level, portfolio_id=portfolio_id).rename(columns={'sector_weight': 'end_sector_weight'})
    sector_compare = pd.merge(start_sector[level_col_map['merge'][level] + ['start_sector_weight']], end_sector[level_col_map['merge'][level] + ['end_sector_weight']], how='outer', on=level_col_map['merge'][level]).fillna(0)
    sector_compare['change'] = sector_compare['end_sector_weight'] - sector_compare['start_sector_weight']
    sector_compare['portfolio_id'] = portfolio_id
    sector_compare = sector_compare.sort_values(by=level_col_map['sort'][level], ascending=False).reset_index(drop=True)
    return sector_compare

# ------------------------------------------------------
# 获取投资组合AUM分布
# ------------------------------------------------------
def anlsFOF_getFOFAUMDistribution(
    date,
    pm_name=None,
    port_type=None,
    client_region=None,
    chart_dimension='level_1_type',  # 绘图时数据展开的维度，选择范围：'level_1_type','level_2_type','level_3_type','management_type',
):
    assert chart_dimension in const.const.FOF_PRODUCT_TYPE.values(), '柱状图数据维度选项必须为level_1_type,level_2_type,level_3_type,management_type之一'

    holding_data = custFOF.custFOF_getFOFHoldingData(date, date, include_portfolio_oa_id=True)
    ref_data = custFOF.custFOF_getFOFReferenceData(pm_name, port_type, client_region, include_advisory_account=True, include_additional_info=True, include_portfolio_oa_id=True, include_all_portfolio_status=True)
    combined_data = _merge_portfolio_ref_and_holding(ref_data, holding_data)
    for fof_prod_type in const.const.FOF_PRODUCT_TYPE.values():
        combined_data.loc[combined_data['advisory_or_not'], fof_prod_type] = '投顾账户'  # 将投顾账户的各级分类填充成'投顾账户'
        combined_data[fof_prod_type] = combined_data[fof_prod_type].apply(lambda x: x if x else '空值')
    agg_nav_data = combined_data.groupby(chart_dimension, as_index=False)['product_NAV'].sum()
    agg_nav_data.rename(columns={'product_NAV': 'portfolio_NAV'}, inplace=True)
    agg_nav_data.sort_values(by='portfolio_NAV', ascending=False, inplace=True)
    nav_total_sum = agg_nav_data.sum()['portfolio_NAV']
    agg_nav_data = agg_nav_data.append({chart_dimension: '合计', 'portfolio_NAV': nav_total_sum}, ignore_index=True)
    agg_account_data = combined_data.groupby(chart_dimension, as_index=False)['portfolio_oa_id'].nunique()
    agg_account_data.rename(columns={'portfolio_oa_id': 'portfolio_count'}, inplace=True)
    agg_account_data.sort_values(by='portfolio_count', ascending=False, inplace=True)
    account_total_sum = agg_account_data.sum()['portfolio_count']
    agg_account_data = agg_account_data.append({chart_dimension: '合计', 'portfolio_count': account_total_sum}, ignore_index=True)
    return agg_nav_data, agg_account_data

# ----------------------------------------------------------------
# FOF组合投资的底层资产（产品或策略或公司）超过某一比例阈值的规模和比例数据计算
# ----------------------------------------------------------------
def anlsFOF_getFOFListByAsset(
    date,
    level_ids,      # 产品或策略或公司ids, 与level选项对应
    product_type,   # 目前支持 私募基金, 公募基金, 活期存款
    level,          # 资产层级 目前支持 产品 策略 公司
    pm_name=None,
    port_type=None,
    client_region=None,
    percent_threshold=0.01,
    detail_mode=False,  # 明细表mode，打开后，在资产层级选择策略、公司时，展示底层产品的持仓情况
):
    assert product_type in ['私募基金', '公募基金', '活期存款'], "产品类别选项仅支持'私募基金', '公募基金', '活期存款'"
    assert level in ['产品', '策略', '公司'], "资产层级选项仅支持'产品', '策略', '公司'"

    level_cols_mapping = {
        '产品': {'id': 'product_id', 'name': 'product_name', 'NAV': 'product_NAV', 'weight': 'product_weight'},
        '策略': {'id': 'strategy_id', 'name': 'strategy_name', 'NAV': 'strategy_NAV', 'weight': 'strategy_weight'},
        '公司': {'id': 'company_id', 'name': 'company_name', 'NAV': 'company_NAV', 'weight': 'company_weight'},
    }
    port_list = custFOF.custFOF_getFOFReferenceData(pm_name, port_type, client_region, include_advisory_account=True, user_permission_setting=True)[['portfolio_id', 'pm_name', 'client_region', 'level_3_type']]
    FOF_holding = custFOF.custFOF_getFOFHoldingData(date, date)
    FOF_holding = pd.merge(FOF_holding, port_list[['portfolio_id']], how='inner', on='portfolio_id')
    FOF_holding = _append_product_label_info(FOF_holding, include_company_strategy_info=True)
    if product_type in ['公募基金', '私募基金']:
        grouped_holding = FOF_holding.groupby(['portfolio_id', 'portfolio_name', level_cols_mapping[level]['id'], level_cols_mapping[level]['name']], as_index=False).sum().\
                        rename(columns={'product_NAV':  level_cols_mapping[level]['NAV'], 'product_weight':  level_cols_mapping[level]['weight']})
        ret = grouped_holding[(grouped_holding[level_cols_mapping[level]['id']].str.split('.', expand=True)[0].isin([level_id.split('.')[0] for level_id in level_ids])) & (grouped_holding[level_cols_mapping[level]['weight']] > percent_threshold)]
    else:
        ret = FOF_holding[(FOF_holding['product_type'] == '活期存款') & (FOF_holding['product_weight'] > percent_threshold)]
    ret = pd.merge(ret, port_list, on='portfolio_id')
    if detail_mode:  # detail_mode打开时，展示策略或公司汇总数据与产品级数据的汇总表
        assert level in ['策略', '公司'], "明细表mode仅支持策略、公司两个资产层级选项"
        ret = ret[['portfolio_id', 'level_3_type', level_cols_mapping[level]['id'], 'portfolio_name', level_cols_mapping[level]['name'], level_cols_mapping[level]['NAV'], level_cols_mapping[level]['weight'], 'pm_name', 'client_region']]
        ret = pd.merge(ret, FOF_holding[['portfolio_id', level_cols_mapping[level]['id'], 'product_name', 'product_NAV', 'product_weight', 'product_volume']],
                       on=['portfolio_id', level_cols_mapping[level]['id']], how='left')
        ret = ret[['portfolio_name', 'level_3_type', level_cols_mapping[level]['name'], level_cols_mapping[level]['NAV'], level_cols_mapping[level]['weight'], 'product_name', 'product_volume', 'product_NAV', 'product_weight', 'pm_name', 'client_region']]
        ret.sort_values(by=[level_cols_mapping[level]['name'], 'pm_name', level_cols_mapping[level]['weight'], 'product_weight'], ascending=False, inplace=True)
        ret = ret.append({'portfolio_name': '合计', level_cols_mapping[level]['name']: '', 'level_3_type': '', level_cols_mapping[level]['NAV']: np.nan,
                          level_cols_mapping[level]['weight']: np.nan,'product_name': '', 'product_volume': ret['product_volume'].sum(), 'product_NAV': ret['product_NAV'].sum(), 'product_weight': np.nan, 'pm_name': '', 'client_region': ''}, ignore_index=True)
    else:
        if level != '产品':
            ret = ret[['portfolio_name', 'level_3_type', level_cols_mapping[level]['name'], level_cols_mapping[level]['NAV'], level_cols_mapping[level]['weight'], 'pm_name', 'client_region']]
            ret.sort_values(by=[level_cols_mapping[level]['name'], 'pm_name', level_cols_mapping[level]['weight']], ascending=False, inplace=True)
            ret = ret.append({'portfolio_name': '合计', level_cols_mapping[level]['name']: '', 'level_3_type': '', level_cols_mapping[level]['NAV']: ret[level_cols_mapping[level]['NAV']].sum(), level_cols_mapping[level]['weight']: np.nan, 'pm_name': '', 'client_region': ''}, ignore_index=True)
        else:  # level==产品时需展示product_volume
            ret = ret[['portfolio_name', 'level_3_type', level_cols_mapping[level]['name'], 'product_volume', level_cols_mapping[level]['NAV'], level_cols_mapping[level]['weight'], 'pm_name', 'client_region']]
            ret.sort_values(by=[level_cols_mapping[level]['name'], 'pm_name', level_cols_mapping[level]['weight']], ascending=False, inplace=True)
            ret = ret.append({'portfolio_name': '合计', level_cols_mapping[level]['name']: '', 'level_3_type': '', 'product_volume': ret['product_volume'].sum(), level_cols_mapping[level]['NAV']: ret[level_cols_mapping[level]['NAV']].sum(), level_cols_mapping[level]['weight']: np.nan, 'pm_name': '', 'client_region': ''}, ignore_index=True)
    ret.reset_index(drop=True, inplace=True)
    return ret

# ------------------------------------------------------
# 计算账户基础风险收益指标
# ------------------------------------------------------
def anlsFOF_calFOFPerfStats(
    date,
    portfolio_ids,  # list, 账户A6_ID
    period,  # 统计区间， YTD, Recent_1M, Recent_3M, Today, 2021, 2020, 2019, SI (since　inception）, Customized
    freq='D',  # 数据频率，D或者W
    start_date=None,
    benchmark=False,  # 是否计算超额指标,为False时计算绝对perf，为True时计算超额perf
    summary_mode=False,  # summary_mode 打开后会同时计算账户+基准+超额的表现数据并汇总
    stats=const.const.COMMON_PERF_STATS,  # 函数所需计算的stats list, 默认stats为'period_return', 'annualized_period_return', 'annualized_volatility', 'max_drawdown', 'sharpe_ratio', 'calmar'
    acc_nav=False  # 是否采用累计净值计算，部分FOF账户存在分红，单位净值计算有误的情况下使用
):
    assert period in ('YTD', 'Recent_1M', 'Recent_3M', 'Today', '2024', '2023', '2022', '2021', '2020', '2019', 'SI', 'Customized'), \
        "统计区间，只能为YTD, Recent_1M, Recent_3M, Today, 2022, 2021, 2020, 2019以及SI（均为字符串格式）"
    assert freq in ("D", "W"), "freq需为D或者W"
    assert isinstance(portfolio_ids, list), "ids需为list"
    assert set(stats) <= (set(const.const.COMMON_PERF_STATS) | set(const.const.EXTEND_PERF_STATS)), \
            "stats选项目前支持'period_return','annualized_period_return','annualized_volatility','max_drawdown','sharpe_ratio','calmar','current_drawdown'"
    if summary_mode:
        assert period != 'Today', "summary_mode不支持period选择Today"

    start_date, end_date = calendar.calender_getStartEndDate(period, date, start_date)
    if end_date < start_date:
        pass
    else:
        account_nav = custFOF.custFOF_getFOFNetValueAndReturn(start_date, end_date, portfolio_ids, freq=freq, include_benchmark=benchmark, acc_nav=acc_nav)
        if len(account_nav) == 0:
            return pd.DataFrame()
        if period != 'Today':
            ret_df = pd.pivot_table(account_nav, index='date', columns='portfolio_id', values='return')
            if summary_mode:
                bm_ret_df = pd.pivot_table(account_nav, index='date', columns='portfolio_id', values='bm_return').add_suffix('_benchmark')
                result = pd.concat([pd.DataFrame.from_dict(cal.basicCal_calPerformanceStats(ret_df[name].dropna(), freq=freq, stats=stats),
                                            columns=[name], orient='index') for name in ret_df.columns], axis=1)
                benchmark_result = pd.concat([pd.DataFrame.from_dict(cal.basicCal_calPerformanceStats(bm_ret_df[name].dropna(), freq=freq, stats=stats),
                                            columns=[name], orient='index') for name in bm_ret_df.columns], axis=1).add_suffix('_result')  # benchmark后缀前面已加，最后效果就是_benchmark_result
                excess_result = pd.concat([pd.DataFrame.from_dict(cal.basicCal_calPerformanceStats(ret_df[name].dropna(), freq=freq,
                    benchmark_ret_series=bm_ret_df[name+'_benchmark'].dropna(), stats=stats), columns=[name], orient='index') for name in ret_df.columns], axis=1).add_suffix('_excess_result')
                result = pd.concat([result, benchmark_result, excess_result], axis=1)
            elif benchmark:
                bm_ret_df = pd.pivot_table(account_nav, index='date', columns='portfolio_id', values='bm_return').add_suffix('_benchmark')
                result = pd.concat([pd.DataFrame.from_dict(cal.basicCal_calPerformanceStats(ret_df[name].dropna(), freq=freq,
                    benchmark_ret_series=bm_ret_df[name+'_benchmark'].dropna(), stats=stats), columns=[name], orient='index') for name in ret_df.columns], axis=1)
            else:
                result = pd.concat([pd.DataFrame.from_dict(cal.basicCal_calPerformanceStats(ret_df[name].dropna(), freq=freq, stats=stats),
                    columns=[name], orient='index') for name in ret_df.columns], axis=1)
            result = result.T.reset_index()
            #下面两列尽量保证输出跟 basicAnal_calPerformanceStats() 一致
            result.rename(columns={'index': 'portfolio_id'}, inplace=True)
        else:
            if benchmark:
                result = account_nav[['date', 'portfolio_id', 'return', 'bm_return']]
                result['excess_return'] = result['return'] - result['bm_return']
                result = result[['date', 'portfolio_id', 'excess_return']]
                result.rename(columns={'date': 'start_date', 'excess_return': 'period_return'}, inplace=True)
            else:
                result = account_nav[['date', 'portfolio_id', 'return']]
                result.rename(columns={'date':'start_date', 'return': 'period_return'}, inplace=True)
            result['end_date'] = end_date

        return result

# ------------------------------------------------------
# FOF组合账户风险收益持仓分布以及红黄绿灯情况的总览
# ------------------------------------------------------
def anlsFOF_platformOverview(
    date,
    period,
    portfolio_types,
    sector_type,
    pm_name,                                # None表示全部投资经理
    start_date=None,
    summary_mode=False,                     # 是否打开summary_mode, 将BM和超额的数据展示, 默认关闭
    include_flag=False,                     # 是否纳入红黄绿灯情况, 默认不纳入展示
    stats=const.const.COMMON_PERF_STATS+const.const.EXTEND_PERF_STATS,    # perf stats list, 默认stats为'period_return', 'annualized_period_return', 'annualized_volatility', 'max_drawdown', 'sharpe_ratio', 'calmar', 'current_drawdown'
    client_region=None,                     # 筛选客户区域
):
    assert set(stats) <= (set(const.const.COMMON_PERF_STATS) | set(const.const.EXTEND_PERF_STATS)), \
            "stats选项目前支持'period_return','annualized_period_return','annualized_volatility','max_drawdown','sharpe_ratio','calmar','current_drawdown'"
    if period == '2024':
        date = datetime.date(2024, 12, 31)  # 最后一个交易日
    if period == '2023':
        date = datetime.date(2023, 12, 29)  # 最后一个交易日
    if period == '2022':
        date = datetime.date(2022, 12, 30)  # 最后一个交易日
    if period == '2021':
        date = datetime.date(2021, 12, 31)
    if period == '2020':
        date = datetime.date(2020, 12, 31)
    # 获取持仓数据
    holding = custFOF.custFOF_getFOFHoldingData(date, date)
    # 仅当考察日期为周五时考虑投顾账户 避免数据缺失
    portfolio_info = custFOF.custFOF_getFOFReferenceData(pm_name, portfolio_types, client_region, include_advisory_account=True if date.weekday() == 4 else False, include_additional_info=True, user_permission_setting=True)
    portfolio_info = portfolio_info[(portfolio_info['inception_date'] < date) | (~portfolio_info['portfolio_id'].isna())]
    holding = holding.merge(portfolio_info[['portfolio_id', 'client_region', 'portfolio_type', 'pm_name']], on='portfolio_id', how='inner')  # inner join筛去非周五日期的投顾持仓
    # 因数据频率不同，对投顾账户拆分处理
    subsidiary_portfolio_ids = portfolio_info[~portfolio_info['advisory_or_not']]['portfolio_id'].unique().tolist()
    advisory_portfolio_ids = portfolio_info[portfolio_info['advisory_or_not']]['portfolio_id'].unique().tolist()
    holding = _append_product_label_info(holding)
    sector = holding.groupby(by=['date', 'portfolio_id'] + [sector_type], as_index=False)['product_NAV'].sum()
    aum = holding.groupby(by=['date', 'portfolio_id'], as_index=False)['product_NAV'].sum()
    aum.rename(columns={'product_NAV': 'AUM'}, inplace=True)
    sector = sector.merge(aum, on=['date', 'portfolio_id'], how='left')
    sector['sector_ratio'] = sector['product_NAV']/sector['AUM']
    sector = sector.pivot_table(index=['date', 'portfolio_id'], columns=sector_type, values='sector_ratio', fill_value=0)
    sector = sector.reset_index()

    # 获取T0可用资金数据
    t0_available_cash = custFOF.custFOF_getT0AvailableCash()
    portfolio_info = portfolio_info.merge(t0_available_cash, on=['portfolio_id'], how='left')

    # 获取收益数据 当date为周五时，对投顾账户取周频净值收益数据，需判断传入id是否为空防止报错
    subsidiary_account_return_info = custFOF.custFOF_getFOFNetValueAndReturn(date, date, subsidiary_portfolio_ids, freq='D', include_flag=include_flag) if len(subsidiary_portfolio_ids) else pd.DataFrame()
    advisory_account_return_info = custFOF.custFOF_getFOFNetValueAndReturn(date, date, advisory_portfolio_ids, freq='W', include_flag=include_flag) if len(advisory_portfolio_ids) else pd.DataFrame()
    return_info = pd.concat([subsidiary_account_return_info, advisory_account_return_info], axis=0)
    del return_info['portfolio_name']  # 组合名称后续从portfolio_info中带出
    if summary_mode:
        # FIXME 因投顾账户未提供bm_return，summary_mode下投顾账户会报错(平台暂无打开summary mode的用法)
        subsidiary_account_period_perf = anlsFOF_calFOFPerfStats(date, subsidiary_portfolio_ids, period, start_date=start_date, benchmark=True, summary_mode=summary_mode, stats=stats) if len(subsidiary_portfolio_ids) else pd.DataFrame()
        advisory_account_period_perf = anlsFOF_calFOFPerfStats(date, advisory_portfolio_ids, period, freq='W', start_date=start_date, benchmark=True, summary_mode=summary_mode, stats=stats) if len(advisory_portfolio_ids) else pd.DataFrame()
        period_perf = pd.concat([subsidiary_account_period_perf, advisory_account_period_perf], axis=0)
        period_perf[['portfolio_id', 'perf_type']] = period_perf.apply(lambda x: tuple(x['portfolio_id'].split('_')[:2])
                    if len(x['portfolio_id'].split('_')) > 1 else (x['portfolio_id'].split('_')[0], 'port'), axis=1, result_type='expand')
        period_perf['date'] = date
        period_perf['period'] = period
    else:
        subsidiary_account_period_perf = anlsFOF_getFOFPerfStats(date, period, portfolio_ids=subsidiary_portfolio_ids, start_date=start_date, stats=stats) if len(subsidiary_portfolio_ids) else pd.DataFrame()
        # 投顾账户暂未缓存绩效 需要实时计算周度绩效
        advisory_account_period_perf = anlsFOF_calFOFPerfStats(date, portfolio_ids=advisory_portfolio_ids, period=period, freq='W', start_date=start_date, summary_mode=summary_mode, stats=stats).rename(columns={'end_date': 'date'}) if len(advisory_portfolio_ids) else pd.DataFrame()
        # 调整col以便与缓存数据header保持一致
        if len(advisory_account_period_perf):
            advisory_account_period_perf['period'] = period
            del advisory_account_period_perf['start_date']
        period_perf = pd.concat([subsidiary_account_period_perf, advisory_account_period_perf], axis=0)
        del period_perf['portfolio_name']
        # FIX 2020 2021 2022 CACHE
        if period in ['2020', '2021', '2022', '2023', '2024']:
            period_perf['date'] = date
    # 整合数据 以portfolio_info中有持仓的账户为准
    result = pd.merge(portfolio_info[portfolio_info['portfolio_id'].isin(holding['portfolio_id'])][['portfolio_id', 'portfolio_name', 'level_3_type', 'portfolio_type', 'inception_date', 't0_available_cash', 'advisory_or_not']], return_info, on=['portfolio_id'], how='left')
    result = pd.merge(result[['date', 'portfolio_id', 'portfolio_name', 'level_3_type', 'portfolio_type', 'inception_date', 't0_available_cash', 'AUM', 'NAV', 'advisory_or_not'] +
                    (['YTD_flag', 'SI_flag'] if include_flag else [])], period_perf, on=['date', 'portfolio_id'], how='left')
    result = pd.merge(result, sector, on=['date', 'portfolio_id'], how='left')
    return result

# ------------------------------------------------------
# 私享账户分类型业绩统计
# ------------------------------------------------------
def anlsFOF_getSXAccountPerfStatsSummary(
    date,
    pm_name=None,
    account_aum=0,
    inception_before=datetime.date.today() - datetime.timedelta(days=90),
    output_type='平均数',   # '平均数', '加权平均数', '中位数'
    period='YTD',
    account_type=None,
    account_area=None,
    start_date=None,  #该参数只对period为Customized有效
    include_account_type_convert=True,  # 是否纳入发生私享臻选转换的账户，默认为纳入
    include_pm_convert=True,  # 是否纳入投资经理转换的账户，默认为纳入
    convert_account_as_whole=True,  # 是否将转换账户前后绩效视为一体(对私享臻选的转换和投资经理的转换同时生效)，默认视为一体
    include_client_special_need=True,  # 是否将具有客户特殊需求的账户纳入，默认为纳入
):
    if period == 'Customized':
        assert start_date != None, 'Customized区间，start_date不能为空值'
    sx_account = custFOF.custFOF_getSXAccountList(date, pm_name, account_aum, inception_before, account_type, account_area,
                                                  include_account_type_convert=include_account_type_convert,
                                                  include_pm_convert=include_pm_convert,
                                                  convert_account_as_whole=convert_account_as_whole,
                                                  include_client_special_need=include_client_special_need
                                                  )
    period_perf = anlsFOF_getFOFPerfStats(date, period=period, portfolio_ids=sx_account.portfolio_id.tolist(), start_date=start_date)
    assert not period_perf.empty, "No Perfstats Data Data"
    period_perf = pd.merge(period_perf, sx_account.loc[:, ['portfolio_name', 'level_3_type']],
                           left_on='portfolio_name', right_on='portfolio_name')
    output = []
    for ptf_type in period_perf.level_3_type.unique():
        result = dict()
        target_account = period_perf[period_perf['level_3_type'] == ptf_type]
        num = int(target_account.shape[0])
        max_ret = target_account['period_return'].max()
        min_ret = target_account['period_return'].min()
        if output_type == '平均数':
            period_ret = target_account['period_return'].mean()
            ann_ret = target_account['annualized_period_return'].mean()
            ann_vol = target_account['annualized_volatility'].mean()
            mdd = target_account['max_drawdown'].mean()
        elif output_type == '中位数':
            period_ret = target_account['period_return'].median()
            ann_ret = target_account['annualized_period_return'].median()
            ann_vol = target_account['annualized_volatility'].median()
            mdd = target_account['max_drawdown'].median()
        elif output_type == '加权平均数':
            weight = sx_account.set_index('portfolio_name').loc[target_account['portfolio_name'], 'AUM']
            weight = weight / weight.sum()
            period_ret = target_account.set_index('portfolio_name')['period_return'].multiply(weight).sum()
            ann_ret = target_account.set_index('portfolio_name')['annualized_period_return'].multiply(weight).sum()
            ann_vol = target_account.set_index('portfolio_name')['annualized_volatility'].multiply(weight).sum()
            mdd = target_account.set_index('portfolio_name')['max_drawdown'].multiply(weight).sum()
        result['level_3_type'] = ptf_type
        result['account_num'] = num
        result['period_return'] = period_ret
        result['annualized_period_return'] = ann_ret
        result['annualized_volatility'] = ann_vol
        result['max_drawdown'] = mdd
        result['max_period_return'] = max_ret
        result['min_period_return'] = min_ret
        output.append(pd.DataFrame.from_dict(result, orient='index'))
    output = pd.concat(output, axis=1)
    output = output.T.reset_index(drop=True)

    # 获取各账户当前基准的生效区间，取max(账户inception日期，基准effect_from日期)作为当前基准生效日期
    current_bm_info = custFOF.custFOF_getFOFBMComponent(date=date, portfolio_id=sx_account['portfolio_id'].unique().tolist()).sort_values(['portfolio_id', 'bm_id'])  # 保证字符串拼接时bm_id顺序一致
    current_bm_info['sub_bm_str'] = current_bm_info['bm_id'] + '*' + current_bm_info['bm_weight'].apply(lambda x: '%.2f' % x)
    current_bm_str_info = current_bm_info.groupby(['portfolio_id'], as_index=False).agg({'sub_bm_str': lambda x: '+'.join(x.to_list()), 'effect_from': 'max', 'effect_to': 'min'}).rename(columns={'sub_bm_str': 'bm_str'})
    sx_account = pd.merge(sx_account, current_bm_str_info, on='portfolio_id', how='left')
    sx_account['bm_start_date'] = sx_account[['inception_date', 'effect_from']].apply(lambda col: pd.to_datetime(col)).max(axis=1).apply(lambda x: x.date())
    # 获取基准绩效
    # 找到代表基准，首先在正常运作且基准类型是通用基准的账户中，按level_3_type分类计算每类账户的基准众数，排除臻选产品以及基准不典型的产品
    # 找到代表产品，以level_3_type进行分类，取每个类别中当前基准生效日期最早的产品
    account_bm_represent = sx_account[((sx_account['portfolio_status'].isin(['正常运作'])) & (sx_account['level_3_type'].isin(config.fof_sx_benchmark.keys())))].groupby('level_3_type', as_index=False).agg({'bm_str': lambda x: x.mode().iloc[0]})  # 取benchmark众数
    account_represent = pd.merge(sx_account, account_bm_represent, on=['level_3_type', 'bm_str'], how='right')
    account_represent = account_represent[account_represent['level_3_type'].isin(config.fof_sx_benchmark.keys())].sort_values(by='bm_start_date', ascending=True).groupby('level_3_type',as_index=False).first()
    # 调用函数计算基准收益
    account_perf = anlsFOF_calFOFPerfStats(date, account_represent['portfolio_id'].to_list(), period, start_date=start_date, benchmark=True, summary_mode=True)
    account_perf[['portfolio_id', 'perf_type']]=account_perf.apply(lambda x: tuple(x['portfolio_id'].split('_')[:2])
                    if len(x['portfolio_id'].split('_')) > 1 else (x['portfolio_id'].split('_')[0], 'port'), axis=1, result_type='expand')
    account_perf = account_perf.loc[account_perf['perf_type']=='benchmark', ]
    benchmark_perf = account_represent[['level_3_type', 'portfolio_id']].merge(account_perf, how='right', on='portfolio_id')
    benchmark_perf.rename(columns={'period_return': 'bm_period_return', 'annualized_period_return': 'bm_annualized_period_return', 'max_drawdown': 'bm_max_drawdown', 'annualized_volatility': 'bm_annualized_volatility'}, inplace=True)
    output = output.merge(benchmark_perf[['bm_period_return', 'bm_annualized_period_return', 'bm_max_drawdown', 'bm_annualized_volatility', 'level_3_type']], how='left', on='level_3_type')
    output['excess_period_return'] = output['period_return'] - output['bm_period_return']
    output = output.sort_values('period_return', ascending=False).reset_index(drop=True)
    return output

# ------------------------------------------------------
# 获取单一FOF账户的持仓明细
# ------------------------------------------------------
def anlsFOF_getSingleFOFHoldingData(
    date,
    portfolio_id,
    include_cost_info=False  # 是否包含买入成本价格、当前价格，默认不包含
):
    result = custFOF.custFOF_getFOFHoldingData(date, date, [portfolio_id])
    result = _append_product_label_info(result)
    if include_cost_info:
        result['unit_cost'] = np.nan
        result['unit_val'] = np.nan
        result['product_appreciation'] = np.nan
        result.loc[result['product_volume'] > 0, 'unit_cost'] = result['COST']/result['product_volume']
        result.loc[result['product_volume'] > 0, 'unit_val'] = result['VAL'] / result['product_volume']
        result.loc[result['product_volume'] > 0, 'product_appreciation'] = result['VAL'] - result['COST']
    return result

# ------------------------------------------------------
# 获取单一FOF账户的区间底层私募表现，可展示实际持有的首尾时间确定绩效计算区间
# ------------------------------------------------------
def anlsFOF_getSingleFOFHoldingPerformanceStats(
    portfolio_id,  # FOF组合代码
    period,  # 统计区间
    end_date,  # 统计截止日期
    freq,  # 数据频率，D或者W
    start_date=None,  # 统计开始日期
    fund_type='HF',  # 基金类型，仅支持'HF'或'MF'
    stats=const.const.COMMON_PERF_STATS,  # 函数所需计算的stats list, 默认stats为'period_return', 'annualized_period_return', 'annualized_volatility', 'max_drawdown', 'sharpe_ratio', 'calmar'
    include_holding_amount=False,
    include_history_holding=False,
    on_exact_holding_period=False  # 是否按实际持有的首尾时间展示
):
    assert fund_type in ('HF', 'MF'), "基金类型fund_type仅支持'HF'和'MF'"
    start_date, end_date = calendar.calender_getStartEndDate(period, end_date, start_date)
    if on_exact_holding_period:
        holding = custFOF.custFOF_getFOFHoldingData(start_date, end_date, [portfolio_id])
        df = pd.concat([holding.groupby(['product_id']).date.min(), holding.groupby(['product_id']).date.max()], axis=1)
        df.columns = ['holding_start_date', 'holding_end_date']
        if include_history_holding is False:
            df = df.loc[df['holding_end_date'] == holding.date.max()]
        ids_config = {index: (row['holding_start_date'], row['holding_end_date']) for index, row in df.iterrows()}
        performance_data_list = []
        for id in ids_config:
            performance_data_single = basicAnalysis.basicAnal_calPerformanceStats([id], ids_config[id][0], ids_config[id][1], freq, fund_type, data_level='Product', stats=stats)
            if len(performance_data_single)>0:
                performance_data_list.append(performance_data_single)
        performance_data = pd.concat(performance_data_list, axis=0)
    else:
        holding = custFOF.custFOF_getFOFHoldingData(end_date - datetime.timedelta(14), end_date, [portfolio_id])
        holding = holding[holding.date == holding.date.max()]
        performance_data = basicAnalysis.basicAnal_calPerformanceStats(holding['product_id'].unique().tolist(), start_date, end_date, freq, fund_type, data_level='Product', stats=stats)

    if include_holding_amount:
        holding_latest = holding.loc[holding['date'] == holding['date'].max(),]
        performance_data = performance_data.merge(holding_latest[['product_id', 'product_NAV', 'product_weight']].rename(columns={'product_id':'id'}), how='left',on='id')
    return performance_data





# ------------------------------------------------------
# 获取投资组合底层各类策略的绩效表现汇总表
# ------------------------------------------------------
def anlsFOF_getFOFSubCategoryPerfTable(
    date,
    period,
    portfolio_id,
    sub_category,
    start_date=None,  # This parameter ONLY works for period list contains Customized
    mode='COMMON_ACCOUNT',  # 目前获取子策略收益序列支持两种模式：1. COMMON_ACCOUNT：非投顾账户，利用归因模型结果，对T日子策略贡献按照T-1权重进行放缩还原，形成收益率序列;
                            # 2.ADVISORY_ACCOUNT：投顾账户，直接利用子策略持仓权重，和可得的产品收益率进行计算
    customized_bm=None,     # 支持自定义选择对比基准，默认为None则使用默认config；如果选择则需给定{'benchmark_source': 'wind', 'benchmark': 'CAMO2.WI', 'name': '中信证券商品动量2.0'}结构的字典
):
    assert period in ('YTD', 'Recent_1M', 'Recent_3M', '2024', '2023', '2022', '2021', '2020', '2019', 'SI', 'Customized'), \
        "统计区间，只能为YTD, Recent_1M, Recent_3M, 2024, 2023, 2022, 2021, 2020, 2019, Customized以及SI（均为字符串格式）"
    assert sub_category in ('股票多头', '主观权益', '纯债基金', '二级债基', '300指增', '500指增', '1000指增', '市场中性', 'CTA', '低波动CTA', '中波动CTA', '高波动CTA', '宏观策略', '套利策略', '量化对冲', '稳健类策略'), \
        "FOF组合底层策略类别，目前支持股票多头,主观权益,纯债基金,二级债基,300指增,500指增,1000指增,市场中性,CTA,低波动CTA,中波动CTA,高波动CTA,宏观策略,套利策略,量化对冲,稳健类策略"

    all_ret = anlsFOF_getFOFSubCategoryAndBMReturn(date, period, portfolio_id, sub_category, start_date, mode, customized_bm)
    if all_ret.empty:
        return all_ret
    all_ret.set_index(['date'], inplace=True)
    result = dict()
    result[all_ret['portfolio_name'].iloc[0] + '-' +sub_category] = cal.basicCal_calPerformanceStats(all_ret['adj_return_rate'], all_ret['freq'].iloc[0])
    result[config.port_label_mapping[sub_category]['name'] if (customized_bm is None or customized_bm['name'] == '朝阳永续中位数') else customized_bm['name']] = cal.basicCal_calPerformanceStats(all_ret['bm_return_rate'], all_ret['freq'].iloc[0])
    result['excess_return'] = cal.basicCal_calPerformanceStats(all_ret['adj_return_rate'], all_ret['freq'].iloc[0], all_ret['bm_return_rate'])
    result = pd.DataFrame.from_dict(result).T.reset_index().rename(columns={'index': 'level_name'})
    result['period'] = period
    result['freq'] = all_ret['freq'].iloc[0]
    return result

# ------------------------------------------------------
# 获取投资组合底层各类策略的净值曲线图
# ------------------------------------------------------
def anlsFOF_getFOFSubCategoryPerfChart(
    date,
    period,
    portfolio_id,
    sub_category,
    start_date=None,        # This parameter ONLY works for period list contains Customized
    mode='COMMON_ACCOUNT',  # 目前获取子策略收益序列支持两种模式：1. COMMON_ACCOUNT：非投顾账户，利用归因模型结果，对T日子策略贡献按照T-1权重进行放缩还原，形成收益率序列;
                            # 2.ADVISORY_ACCOUNT：投顾账户，直接利用子策略持仓权重，和可得的产品收益率进行计算
    customized_bm=None,     # 支持自定义选择对比基准，默认为None则使用默认config；如果选择则需给定{'benchmark_source': 'wind', 'benchmark': 'CAMO2.WI', 'name': '中信证券商品动量2.0'}结构的字典
):
    assert period in ('YTD', 'Recent_1M', 'Recent_3M', '2024', '2023', '2022', '2021', '2020', '2019', 'SI', 'Customized'), \
        "统计区间，只能为YTD, Recent_1M, Recent_3M, 2024, 2023, 2022, 2021, 2020, 2019, Customized以及SI（均为字符串格式）"
    assert sub_category in ('股票多头', '主观权益', '纯债基金', '二级债基', '300指增', '500指增', '1000指增', '市场中性', 'CTA', '低波动CTA', '中波动CTA', '高波动CTA', '宏观策略', '套利策略', '量化对冲', '稳健类策略'), \
        "FOF组合底层策略类别，目前支持股票多头,主观权益,纯债基金,二级债基,300指增,500指增,1000指增,市场中性,CTA,低波动CTA,中波动CTA,高波动CTA,宏观策略,套利策略,量化对冲,稳健类策略"

    all_ret = anlsFOF_getFOFSubCategoryAndBMReturn(date, period, portfolio_id, sub_category, start_date, mode, customized_bm)
    if all_ret.empty:
        return all_ret
    all_ret.set_index(['date'], inplace=True)
    all_ret['excess_return_rate'] = all_ret['adj_return_rate'] - all_ret['bm_return_rate']
    nav_series = (all_ret[['adj_return_rate', 'bm_return_rate', 'excess_return_rate']] + 1).cumprod()
    nav_series.loc[all_ret.index[0] - datetime.timedelta(days=const.const.FREQ_INTERVAL[all_ret['freq'].iloc[0]])] = 1
    nav_series = nav_series.sort_index().reset_index()
    all_nav_result = nav_series.melt(id_vars='date', var_name='return_type', value_name='nav')
    return_type_map = {
        'adj_return_rate': {'id': all_ret['portfolio_name'].iloc[0] + '-' + sub_category, 'nav_type': 'category'},
        'bm_return_rate': {'id': config.port_label_mapping[sub_category]['name'] if (customized_bm is None or customized_bm['name'] == '朝阳永续中位数') else customized_bm['name'], 'nav_type': 'bm'},
        'excess_return_rate': {'id': all_ret['portfolio_name'].iloc[0] + '-' + sub_category + '-超额', 'nav_type': 'excess'},
    }
    all_nav_result['id'] = all_nav_result['return_type'].apply(lambda x: return_type_map[x]['id'])
    all_nav_result['nav_type'] = all_nav_result['return_type'].apply(lambda x: return_type_map[x]['nav_type'])
    all_nav_result['freq'] = all_ret['freq'].iloc[0]
    del all_nav_result['return_type']
    return all_nav_result

# ------------------------------------------------------
# 获取投资组合底层各类策略的月度收益
# ------------------------------------------------------
def anlsFOF_getFOFSubCategoryMonthlyReturn(
    date,
    period,
    portfolio_id,
    sub_category,
    mode='COMMON_ACCOUNT',  # 目前获取子策略收益序列支持两种模式：1. COMMON_ACCOUNT：非投顾账户，利用归因模型结果，对T日子策略贡献按照T-1权重进行放缩还原，形成收益率序列;
    # 2.ADVISORY_ACCOUNT：投顾账户，直接利用子策略持仓权重，和可得的产品收益率进行计算
):
    assert period in ('YTD', 'Recent_1M', 'Recent_3M', '2024', '2023', '2022', '2021', 'SI'), \
        "统计区间，只能为YTD, Recent_1M, Recent_3M, 2024, 2023, 2022, 2021以及SI（均为字符串格式）"
    assert sub_category in (
    '股票多头', '主观权益', '纯债基金', '二级债基', '300指增', '500指增', '1000指增', '市场中性', 'CTA', '低波动CTA', '中波动CTA', '高波动CTA', '宏观策略', '套利策略', '量化对冲', '稳健类策略'), \
        "FOF组合底层策略类别，目前支持股票多头,主观权益,纯债基金,二级债基,300指增,500指增,1000指增,市场中性,CTA,低波动CTA,中波动CTA,高波动CTA,宏观策略,套利策略,量化对冲,量化对冲,稳健类策略"

    all_ret = anlsFOF_getFOFSubCategoryAndBMReturn(date, period, portfolio_id, sub_category, mode=mode).set_index('date')
    if all_ret.empty:
        return all_ret
    port_monthly_return = cal.basicCal_getCalendarPeriodReturn(all_ret['adj_return_rate'], 'M').to_frame('port_monthly_return')
    bm_monthly_return = cal.basicCal_getCalendarPeriodReturn(all_ret['bm_return_rate'], 'M').to_frame('bm_monthly_return')
    monthly_return = pd.merge(port_monthly_return, bm_monthly_return, left_index=True, right_index=True, how='left')
    monthly_return['excess_monthly_return'] = monthly_return['port_monthly_return'] - monthly_return['bm_monthly_return']
    monthly_return['portfolio_id'] = portfolio_id
    monthly_return['portfolio_name'] = all_ret['portfolio_name'].iloc[0]
    monthly_return['sub_category'] = sub_category
    monthly_return['freq'] = all_ret['freq'].iloc[0]
    monthly_return.sort_index(ascending=False, inplace=True)
    return monthly_return

# ---------------------------------------------------------
# 获取投资组合多头行业穿透
# 私募公募整合时仅支持申万一级分布，只看公募可以对行业分类以及报告期进行选择
# ---------------------------------------------------------
def anlsFOF_getFOFIndustryLookThrough(
    date,                   # 持仓数据日期，输入格式:datetime.date
    portfolio_id,
    company='SW',           # 行业分类标准，输入格式:str，'SW' or 'CITICS'
    level=1,                # 行业分类级别，输入格式:int
    top_num=10,             # 前N大行业
    mask_h_shares=True,     # 是否将港股的行业全部置为“港股”，默认为是
    report_date=None,       # 报告日期控制，默认为空，以date之前前最新报告为准；报告日期输入格式:datetime.date
):
    assert company in ['SW', 'CITICS'], "行业分类目前支持申万和中信"
    assert level in [1, 2, 3], "行业分类级别支持1、2、3级"

    # 未特殊设置报告期，则以date前最新报告为准
    if not report_date:
        report_date = date

    # 持仓信息
    holding_result = anlsFOF_getSingleFOFHoldingData(date, portfolio_id)

    # 对持仓中后端产品预处理，穿透到产品一级后合并至原持仓df，将权重更新好
    back_end_holding_result = holding_result[holding_result['product_id'].isin(config.back_end_product_info.keys())]
    if not back_end_holding_result.empty:
        back_end_all_holding = []
        for product_id in back_end_holding_result['product_id'].to_list():
            back_end_product_holding = anlsFOF_getSingleFOFHoldingData(date, config.back_end_product_info[product_id]['portfolio_id'])
            back_end_product_holding[['COST', 'VAL', 'product_weight', 'product_NAV']] = back_end_product_holding[['COST', 'VAL', 'product_weight', 'product_NAV']] * back_end_holding_result[back_end_holding_result['product_id'] == product_id]['product_weight'].iloc[0]
            back_end_all_holding.append(back_end_product_holding)
        # 后端主观的底层产品并入holding_result
        back_end_all_holding = pd.concat(back_end_all_holding)
        back_end_all_holding[['portfolio_name', 'portfolio_id', 'inception_date', 'NAV', 'date']] = holding_result[['portfolio_name', 'portfolio_id', 'inception_date', 'NAV', 'date']].loc[0].to_list()
        holding_result = holding_result.drop(holding_result[holding_result['product_id'].isin(config.back_end_product_info.keys())].index)
        holding_result = holding_result.append(back_end_all_holding).reset_index(drop=True)

    # 按持仓类型获取行业比重数据
    # 公募 主观多头 公募不筛类型直接输入 有数字即返回 包含了主观权益 指数增强 二级债基
    # 对于未录入的产品 holding_result['hf_mf_type'] == '公募' 也无法筛出 故直接将所有id输入 返回时只会包含有权益持仓的公募
    mf_list = holding_result['product_id'].to_list()
    mf_industry = MFAnal.anlsMF_getListedMFIndustryWeightDetails(report_date, mf_list, company, level, mask_h_shares=mask_h_shares) if mf_list else pd.DataFrame()
    # 私募 主观权益
    ff_list = holding_result[(holding_result['hf_mf_type'] == '私募') & (holding_result['label_level_1'] == '主观权益')]['product_id'].to_list()
    if ff_list:
        assert (company == 'SW' and level == 1), "您的账户有私募多头持仓，目前行业穿透仅支持申万一级"
    ff_industry = FFAnal.ffa_getListedFundaFundIndustryWeightDetails(report_date, ff_list, mask_h_shares=mask_h_shares) if ff_list else pd.DataFrame()
    # 私募 指数增强&量化对冲
    qf_list = holding_result[(holding_result['hf_mf_type'] == '私募') & (holding_result['label_level_1'].isin(['指数增强', '量化对冲']))]['product_id'].to_list()
    # FIXME 标准组合中，使用500股指期货主连，穿透时相当于满仓运行的指增，进行行业穿透时，使用500的行业分布进行代替
    if 'IC.CFE' in holding_result['product_id'].to_list():
        qf_list += ['IC.CFE']
    if qf_list:
        assert (company == 'SW' and level == 1), "您的账户有私募量化持仓，目前行业穿透仅支持申万一级"
    qf_industry = QFAnal.qfa_getListedQuantFundIndustryWeightDetails(report_date, qf_list) if qf_list else pd.DataFrame()
    # 数据汇总
    fund_industry = pd.concat([mf_industry, ff_industry, qf_industry], axis=0)
    if fund_industry.empty:
        # 与下方返回格式保持一致
        return {'industry': fund_industry, 'market': None, 'product': None}
    combine_result = pd.merge(fund_industry, holding_result[['product_id', 'product_name', 'product_type', 'product_weight', 'label_level_1',
                                             'label_level_2', 'allocation_type']], on='product_id')
    combine_result['industry_weight_in_port'] = combine_result['industry_weight'] * combine_result['product_weight']
    # 计算行业
    result = combine_result.groupby(by=['industry', 'industry_level'], as_index=False)['industry_weight_in_port'].sum()
    result['equity_total_weight'] = result['industry_weight_in_port'].sum()
    result['industry_weight'] = result['industry_weight_in_port'] / result['equity_total_weight']
    # 报告期信息
    if mf_industry.empty:
        report_date = combine_result['report_date'].min()  # 报告期
    else:
        # 公募私募都有持仓时，展示公募的报告期（靠前的那个）
        # 如果公募正处于报告披露的过程中，存在数据日期不同的情况，则同时展示所用的两个日期以提示用户
        earliest_report_date_list = combine_result['earliest_report_date']
        earliest_report_date = earliest_report_date_list[~earliest_report_date_list.isnull()].max()
        report_date = combine_result['report_date'].min() if combine_result['report_date'].min() == earliest_report_date \
                        else str([str(earliest_report_date), str(combine_result['report_date'].min())])
    result[['portfolio_id', 'portfolio_name', 'date', 'NAV', 'report_date']] = \
        [portfolio_id, holding_result['portfolio_name'].iloc[0], holding_result['date'].iloc[0], holding_result['NAV'].iloc[0], report_date]
    result['industry_NAV'] = result['NAV'] * result['industry_weight_in_port']
    result = result.sort_values(by='industry_weight', ascending=False).reset_index(drop=True)
    # 拆分top_num并将bottom部分求和作为其他项
    top_result = result.iloc[:top_num, :]
    bottom_result = result.iloc[top_num:, :]
    if not bottom_result.empty:
        top_result = top_result.append({'industry_level': company + '_' + str(level), 'industry': '其他', 'industry_weight_in_port': bottom_result['industry_weight_in_port'].sum(),
                                        'industry_weight': bottom_result['industry_weight'].sum(), 'industry_NAV': bottom_result['industry_NAV'].sum()},ignore_index=True)
    top_result = top_result.append({'industry_level': company + '_' + str(level), 'industry': '合计', 'industry_weight_in_port': top_result['industry_weight_in_port'].sum(),
                                    'industry_weight': top_result['industry_weight'].sum(), 'industry_NAV': top_result['industry_NAV'].sum()}, ignore_index=True)
    col_to_fillna = ['equity_total_weight', 'portfolio_id', 'portfolio_name', 'date', 'NAV', 'report_date']  # 组合级别的信息通过fillna补全（该级别信息对于全表来说都是一致的）
    top_result[col_to_fillna] = top_result[col_to_fillna].fillna(method='ffill')  # 新加行的其他基础信息依照已有数据fill

    # 市场穿透
    lookthrough_market_result = result.copy(deep=True)
    lookthrough_market_result['market'] = lookthrough_market_result['industry'].apply(lambda x: '美股' if '美股' in x else ('港股' if '港股' in x else 'A股'))
    lookthrough_market_result = lookthrough_market_result.groupby(['market'], as_index=False).agg({'industry_NAV': 'sum', 'industry_weight_in_port': 'sum', 'industry_weight': 'sum'})
    lookthrough_market_result.rename(columns={'industry_NAV': 'market_NAV', 'industry_weight_in_port': 'market_weight_in_port', 'industry_weight': 'market_weight'}, inplace=True)
    lookthrough_market_result = lookthrough_market_result.sort_values(by='market_weight', ascending=False).reset_index(drop=True)
    lookthrough_market_result = lookthrough_market_result.append({'market': '合计',
                                                                  'market_NAV': lookthrough_market_result['market_NAV'].sum(),
                                                                  'market_weight_in_port': lookthrough_market_result['market_weight_in_port'].sum(),
                                                                  'market_weight': lookthrough_market_result['market_weight'].sum()}, ignore_index=True)
    lookthrough_market_result[['portfolio_name', 'NAV', 'date']] = [result['portfolio_name'].iloc[0], result['NAV'].iloc[0], result['date'].iloc[0]]
    lookthrough_market_result = lookthrough_market_result[['portfolio_name', 'NAV', 'date', 'market', 'market_NAV', 'market_weight_in_port', 'market_weight']]

    # 参与穿透的产品
    lookthrough_holding_products = combine_result['product_id'].unique().tolist()
    lookthrough_holding_result = holding_result[holding_result['product_id'].isin(lookthrough_holding_products)].sort_values(['allocation_type', 'label_level_1', 'label_level_2', 'product_type', 'product_weight'], ascending=False).reset_index(drop=True)
    lookthrough_holding_result = lookthrough_holding_result[['portfolio_name', 'NAV', 'date', 'product_id', 'product_name', 'product_NAV', 'product_weight',
                                                             'product_type', 'label_level_1', 'label_level_2', 'allocation_type']]
    return {'industry': top_result, 'market': lookthrough_market_result, 'product': lookthrough_holding_result}

# ------------------------------------------------------
# 私享账户分类账户收益回撤
# ------------------------------------------------------
def anlsFOF_getSXAccountReturnDrawdownBubbleMap(
    date,
    xaxis,  # 横轴绘制最大回撤、当前回撤或是波动
    pm_name=None,
    account_aum=0,
    inception_before=datetime.date.today() - datetime.timedelta(days=90),
    period='YTD',
    account_type=None,
    account_area=None,
    start_date=None,
    include_account_type_convert=True,  # 是否纳入发生私享臻选转换的账户，默认为纳入
    include_pm_convert=True,  # 是否纳入投资经理转换的账户，默认为纳入
    convert_account_as_whole=True,  # 是否将转换账户前后绩效视为一体(对私享臻选的转换和投资经理的转换同时生效)，默认视为一体
    include_client_special_need=True,  # 是否将具有客户特殊需求的账户纳入，默认为纳入
):
    assert xaxis in ['最大回撤', '当前回撤', '波动'], "xaxis请选择'最大回撤'、'当前回撤' 或'波动'"
    xaxis_stat_mapping = {
        '最大回撤': 'max_drawdown',
        '当前回撤': 'current_drawdown',
        '波动': 'annualized_volatility'
    }
    sx_account = custFOF.custFOF_getSXAccountList(date, pm_name, account_aum, inception_before, account_type, account_area,
                                                  include_account_type_convert=include_account_type_convert,
                                                  include_pm_convert=include_pm_convert,
                                                  convert_account_as_whole=convert_account_as_whole,
                                                  include_client_special_need=include_client_special_need
                                                  )
    period_perf = anlsFOF_getFOFPerfStats(date, period=period, portfolio_ids=sx_account.portfolio_id.tolist(), start_date=start_date, stats=['period_return', xaxis_stat_mapping[xaxis]])
    assert not period_perf.empty, "No Perfstats Data Read from Database"
    period_perf = pd.merge(period_perf, sx_account[['portfolio_name', 'level_3_type', 'AUM', 'pm_name']],
                           left_on='portfolio_name', right_on='portfolio_name')
    if xaxis == '最大回撤':
        period_perf = period_perf[['portfolio_name','period_return', 'max_drawdown', 'level_3_type', 'AUM', 'pm_name']]
        period_perf.max_drawdown = -period_perf.max_drawdown
    elif xaxis == '当前回撤':
        period_perf = period_perf[['portfolio_name','period_return', 'current_drawdown', 'level_3_type', 'AUM', 'pm_name']]
        period_perf.current_drawdown = -period_perf.current_drawdown
    elif xaxis == '波动':
        period_perf = period_perf[['portfolio_name', 'period_return', 'annualized_volatility', 'level_3_type', 'AUM', 'pm_name']]

    return period_perf

# ------------------------------------------------------
# 私享账户分类型时序收益
# ------------------------------------------------------
def anlsFOF_getSXAccountAvgNav(
    date,
    pm_name=None,
    account_aum=0,
    inception_before=datetime.date.today(),
    output_type='平均数',   # '平均数', '加权平均数', '中位数'
    period='YTD',
    account_type=None,
    account_area=None,
    freq='D',
    start_date=None,
    include_account_type_convert=True,  # 是否纳入发生私享臻选转换的账户，默认为纳入
    include_pm_convert=True,  # 是否纳入投资经理转换的账户，默认为纳入
    convert_account_as_whole=True,  # 是否将转换账户前后绩效视为一体(对私享臻选的转换和投资经理的转换同时生效)，默认视为一体
    include_client_special_need=True,  # 是否将具有客户特殊需求的账户纳入，默认为纳入
):
    assert freq in ("D", "W"), "freq需为D或者W"
    sx_account = custFOF.custFOF_getSXAccountList(date, pm_name, account_aum, inception_before, account_type, account_area,
                                                  include_account_type_convert=include_account_type_convert,
                                                  include_pm_convert=include_pm_convert,
                                                  convert_account_as_whole=convert_account_as_whole,
                                                  include_client_special_need=include_client_special_need
                                                  )
    start_date, end_date = calendar.calender_getStartEndDate(period, date, start_date=start_date)
    account_nav = custFOF.custFOF_getFOFNetValueAndReturn(start_date, end_date, portfolio_ids=sx_account.portfolio_id.tolist())
    ret_df = pd.pivot_table(account_nav, index='date', columns='portfolio_name', values='return')
    account_group = sx_account.groupby('level_3_type')
    result = dict()
    for ptf_type, group in account_group:
        ret_group = ret_df.loc[:, ret_df.columns.isin(group.portfolio_name.tolist())]
        if output_type == '平均数':
            nav_series = (ret_group.mean(axis=1) + 1).cumprod()
        elif output_type == '中位数':
            nav_series = (ret_group.median(axis=1) + 1).cumprod()
        elif output_type == '加权平均数':
            weight = sx_account.set_index('portfolio_name').loc[group.portfolio_name.tolist(), 'AUM']
            weight = weight / weight.sum()
            nav_series = (ret_group.multiply(weight).sum(axis=1) + 1).cumprod()
        nav_series.loc[start_date - datetime.timedelta(days=1)] = 1
        result[ptf_type] = nav_series
    return result

# ------------------------------------------------------
# 单账户时序收益
# ------------------------------------------------------
def anlsFOF_getAccountNav(
    date,
    portfolio_id,  # 账户名称
    period,  # 统计区间， YTD, YTLDLM, 2022, 2021, 2020, 2019, SI (since　inception）, Customized
    freq='D',  # 数据频率，D或者W
    start_date=None,
    include_benchmark=False,  # 是否返回benchmark的收益
    include_excess=False,  # 是否返回超额收益
    acc_nav=False  # 是否采用累计净值计算，部分FOF账户存在分红，单位净值计算有误的情况下使用
):
    assert period in ('YTD', 'YTLDLM', '2024', '2023', '2022', '2021', '2020', '2019', 'SI', 'Customized'), \
        "统计区间，只能为YTD, 2024, 2023, 2022, 2021, 2020, 2019以及SI（均为字符串格式）"
    assert freq in ("D", "W"), "freq需为D或者W"
    start_date, end_date = calendar.calender_getStartEndDate(period, date, start_date)
    assert end_date > start_date, "起始日期晚于结束日期"
    account_nav = custFOF.custFOF_getFOFNetValueAndReturn(start_date, end_date, portfolio_ids=[portfolio_id], freq=freq, include_benchmark=include_benchmark, acc_nav=acc_nav)
    ret_df = pd.pivot_table(account_nav, index='date', values=['return', 'bm_return'] if include_benchmark else ['return'])
    if include_excess == True:
        ret_df['excess_nav']=ret_df['return']-ret_df['bm_return']
    nav_series = (ret_df + 1).cumprod()
    nav_series.loc[ret_df.index[0] - datetime.timedelta(days=const.const.FREQ_INTERVAL[freq])] = 1
    nav_series = nav_series.sort_index()
    result = nav_series.reset_index()
    result.rename(columns={'return': 'nav', 'bm_return': 'bm_nav'}, inplace=True)
    name_list = custFOF.custFOF_getFOFProductList().set_index('portfolio_id')
    result['id'] = name_list.loc[portfolio_id][0]
    return result

# ------------------------------------------------------
# 获取FOF账户绩效表现的Wrapper，包括缓存或者Customized区间
# ------------------------------------------------------
def anlsFOF_getFOFPerfStats(
    date,
    period,  # YTD, Today, 2022, 2021, 2020, 'Customized'
    portfolio_ids=None,
    start_date=None,    # 该参数只对Customzied有用
    stats=const.const.COMMON_PERF_STATS,  # perf stats list, 默认stats为'period_return', 'annualized_period_return', 'annualized_volatility', 'max_drawdown', 'sharpe_ratio', 'calmar'
):
    assert set(stats) <= (set(const.const.COMMON_PERF_STATS) | set(const.const.EXTEND_PERF_STATS)), \
            "stats选项目前支持'period_return','annualized_period_return','annualized_volatility','max_drawdown','sharpe_ratio','calmar','current_drawdown'"
    if period in ['YTD', '2024', '2023', '2022', '2021', '2020']:
        stats_result = custFOF.custFOF_getFOFCachedPerfStats(date, period, portfolio_ids, stats=stats)
    elif period in [ 'Today', 'Customized']:
        stats_result = anlsFOF_calAndCacheFOFPerfStats(date, period=period, portfolio_ids=portfolio_ids, start_date=start_date, stats=stats)
        stats_result.rename(columns={'dt': 'date'}, inplace=True)
    return stats_result

# ------------------------------------------------------------------------------
# PM投资情况 红黄绿灯情况汇总
# 返回：flag_count_weight: 红黄绿灯按账户数量、规模汇总的比重数据表格;
# 返回：group_result: 不同产品系列的规模、绩效、超额绩效、红绿灯统计的汇总表格
# ------------------------------------------------------------------------------
def anlsFOF_pmFlagOverview(
    date,
    period,
    pm_name,                    # None表示全部投资经理
    start_date=None,
):
    # 汇总数据大表
    flag_result = anlsFOF_platformOverview(date, period, portfolio_types=None, sector_type='allocation_type', pm_name=pm_name,
                                           start_date=start_date, summary_mode=True, include_flag=True, stats=['period_return'])
    port_result = flag_result[flag_result['perf_type'] == 'port']
    excess_result = flag_result[flag_result['perf_type'] == 'excess'].rename(columns={'period_return': 'excess_period_return'})
    port_result = port_result.merge(excess_result[['portfolio_id', 'excess_period_return']], on=['portfolio_id'])
    port_result[['period_return', 'excess_period_return']] = port_result[['period_return', 'excess_period_return']].astype(float)

    # 总体权重计算
    flag_count_weight = port_result.groupby(['YTD_flag'], as_index=False).agg({'portfolio_id': 'count', 'AUM': 'sum'})
    flag_count_weight['count_weight'] = flag_count_weight['portfolio_id'] / flag_count_weight['portfolio_id'].sum()
    flag_count_weight['AUM_weight'] = flag_count_weight['AUM'] / flag_count_weight['AUM'].sum()
    # 红黄绿灯情况可能不是都有，当前行数不一，为了展示的规整性，通过merge补全行数
    flag_count_weight = pd.merge(pd.DataFrame({'YTD_flag': ['绿', '黄', '红']}), flag_count_weight, on=['YTD_flag'], how='left').fillna(0)
    flag_count_weight = flag_count_weight.append({'YTD_flag': '合计', 'portfolio_id': flag_count_weight['portfolio_id'].sum(),
                                                  'AUM': flag_count_weight['AUM'].sum()}, ignore_index=True)
    flag_count_weight.rename(columns={'portfolio_id': 'portfolio_count'}, inplace=True)
    flag_count_weight = flag_count_weight.astype({'portfolio_count': int})

    # 每一产品线的数据计算  如果PM不在投委会报告范围内或PM选项为None(全选)则使用portfolio_type分类，否则依照投委会报告的产品线config分类
    if pm_name is not None and pm_name in config.invest_commitee_key_accounts_config.keys():
        port_result['product_line'] = np.nan
        for key_word, full_name in config.invest_commitee_key_accounts_config[pm_name]['account_groups'].items():
            port_result['product_line'] = port_result.apply(lambda x: full_name if key_word in x['portfolio_name'] else x['product_line'], axis=1)
        port_result.dropna(inplace=True)  # 不显示config产品线之外的账户
        port_result['portfolio_type'] = port_result['product_line']  # 将产品线替换至portfolio_type规整数据，方便后续展示
        del port_result['product_line']
    flag_group_result = port_result.groupby(['portfolio_type', 'YTD_flag'], as_index=False)['portfolio_id'].count().\
                        pivot(index='portfolio_type', columns='YTD_flag', values='portfolio_id').reset_index()
    # 红黄绿灯情况可能不是都有，当前df列数不一，为了展示的规整性补全列数
    for col in ['红', '黄', '绿']:
        if col not in flag_group_result.columns:
            flag_group_result[col] = np.nan
    flag_group_result = flag_group_result[['portfolio_type', '红', '黄', '绿']]

    perf_group_result = port_result.groupby(['portfolio_type'], as_index=False).\
                        agg({'portfolio_id': 'count', 'AUM': 'sum', 'period_return': 'mean', 'excess_period_return': 'mean'})
    group_result = pd.merge(perf_group_result, flag_group_result, on=['portfolio_type'])
    group_result = group_result.append({'portfolio_type': '合计', 'portfolio_id': group_result['portfolio_id'].sum(),
                                        'AUM': group_result['AUM'].sum(), '红': group_result['红'].sum(),
                                        '黄': group_result['黄'].sum(), '绿': group_result['绿'].sum()}, ignore_index=True)
    group_result.rename(columns={'portfolio_id': 'portfolio_count'}, inplace=True)
    group_result[['红', '黄', '绿']] = group_result[['红', '黄', '绿']].fillna(0).astype({'红': int, '黄': int, '绿': int})

    return flag_count_weight, group_result

# ------------------------------------------------------------------------------
# 账户区间绩效即基准超额收益汇总，每个账户一行
# 目前用于投委会报告前三页 - 集合产品A类账户的代表账户绩效汇总
# 返回代表账户绩效、对应基准绩效、红绿灯情况
# ------------------------------------------------------------------------------
def anlsFOF_keyAccountPerfSummary(
    port_ids,   # 输入账户id list
    date,
    period,
    start_date=None
):
    assert period in ('YTD', 'Recent_1M', 'Recent_3M', '2024', '2023', '2022', '2021', '2020', '2019', 'SI', 'Customized'), \
        "统计区间，只能为YTD, Recent_1M, Recent_3M, Today, 2022, 2021, 2020, 2019以及SI（均为字符串格式）"

    portfolio_info = custFOF.custFOF_getFOFReferenceData(include_advisory_account=True, user_permission_setting=True)
    portfolio_info = portfolio_info[portfolio_info['portfolio_id'].isin(port_ids)]

    # 获取收益数据
    return_info = custFOF.custFOF_getFOFNetValueAndReturn(date, date, port_ids, include_flag=True)
    period_perf = anlsFOF_calFOFPerfStats(date, port_ids, period, start_date=start_date, benchmark=True, summary_mode=True)
    period_perf[['portfolio_id', 'perf_type']] = period_perf.apply(lambda x: tuple(x['portfolio_id'].split('_')[:2])
                if len(x['portfolio_id'].split('_')) > 1 else (x['portfolio_id'].split('_')[0], 'port'), axis=1, result_type='expand')
    period_perf['date'] = date
    period_perf['period'] = period

    # 整理表格格式，每个账户一行
    port_result = period_perf[period_perf['perf_type'] == 'port']
    bm_result = period_perf[period_perf['perf_type'] == 'benchmark'].rename(columns={'period_return': 'bm_period_return'})
    excess_result = period_perf[period_perf['perf_type'] == 'excess'].rename(columns={'period_return': 'excess_period_return'})
    result = port_result.merge(bm_result[['portfolio_id', 'bm_period_return']], on=['portfolio_id'])
    result = result.merge(excess_result[['portfolio_id', 'excess_period_return']], on=['portfolio_id'])
    result[['period_return', 'bm_period_return', 'excess_period_return']] = result[['period_return', 'bm_period_return', 'excess_period_return']].astype(float)

    # 整合红绿灯数据
    result = result.merge(return_info[['portfolio_id', 'AUM', 'YTD_flag', 'SI_flag']], on=['portfolio_id'], how='left')
    result = result.merge(portfolio_info[['portfolio_id', 'portfolio_name', 'level_3_type', 'pm_name', 'inception_date']], on=['portfolio_id'], how='left')
    result = result[['portfolio_id',  'portfolio_name', 'pm_name', 'level_3_type', 'AUM', 'period', 'start_date', 'end_date',  'period_return', 'annualized_period_return',
                     'annualized_volatility', 'max_drawdown','bm_period_return', 'excess_period_return', 'YTD_flag', 'SI_flag']]
    result.sort_values(['AUM', 'level_3_type', 'pm_name'], ascending=[False, False, False], inplace=True)

    # 对于config中的集合产品A类账户的代表账户，进行进一步的加工，展示账户策略类型（单策略/多策略）
    if set(port_ids) <= set(config.invest_commitee_pooled_key_accounts_config.keys()):
        result['port_strategy_type'] = result['portfolio_id'].apply(lambda x: config.invest_commitee_pooled_key_accounts_config.get(x, {'port_strategy_type': ''})['port_strategy_type'])
        result.sort_values(['AUM', 'pm_name'], ascending=[False, False], inplace=True)
        result = result[['portfolio_id', 'portfolio_name', 'pm_name', 'port_strategy_type', 'AUM', 'period', 'start_date', 'end_date', 'period_return', 'annualized_period_return',
                        'annualized_volatility', 'max_drawdown', 'bm_period_return', 'excess_period_return', 'YTD_flag', 'SI_flag']]
    result['AUM'] = result['AUM'] / 1e4
    result.reset_index(drop=True, inplace=True)
    return result

# ------------------------------------------------------
# FOF投资经理持仓分布统计
# ------------------------------------------------------
def anlsFOF_getFOFPMSectorDistribution(
    date,                # 考察日期
    sector_type,         # 持仓分类
    portfolio_ids=None,  # 账户ID, list
    include_summary_row=False  # 是否包含账户总体的统计行
):
    assert sector_type in ['allocation_type', 'label_level_1', 'label_level_2'], "sector_type仅支持'allocation_type', 'label_level_1', 'label_level_2'"
    holding_data = custFOF.custFOF_getFOFHoldingData(date, date, include_portfolio_oa_id=True)
    ref_data = custFOF.custFOF_getFOFReferenceData(include_advisory_account=True, include_portfolio_oa_id=True)
    holding_data = pd.merge(holding_data, ref_data[['portfolio_oa_id', 'pm_name']], on='portfolio_oa_id', how='left')
    if portfolio_ids:  # port_id筛选
        assert isinstance(portfolio_ids, list), "portfolio_ids需为list类型"
        holding_data = holding_data[holding_data['portfolio_id'].isin(portfolio_ids)]
    holding_data = _append_product_label_info(holding_data)  # 加入sector标签
    holding_data['allocation_type_category'] = pd.Categorical(holding_data['allocation_type'], categories=const.const.ALLOCATION_TYPE_LIST, ordered=True)
    holding_data.sort_values(['allocation_type_category', 'label_level_1', 'label_level_2'], ascending=True, inplace=True)
    sorted_type_labels = holding_data[sector_type].unique().tolist()  # 按层级依次排序，保证当前层级的排序也遵循上一层级的排序顺序
    # 对于多投资经理的账户进行拆分复制，分别计入各自持仓
    pm_splitted_holding = holding_data.copy(deep=True)
    pm_splitted_holding['pm_name'] = pm_splitted_holding['pm_name'].str.split(',')
    pm_splitted_holding = pm_splitted_holding.explode('pm_name')
    sector_distribution = pm_splitted_holding.groupby(['pm_name', sector_type], as_index=False).agg({'product_NAV': 'sum'})
    sector_distribution = pd.pivot_table(sector_distribution, values='product_NAV', index='pm_name', columns=sector_type)
    if include_summary_row:  # 统计账户总体持仓分布时，需使用原始的holding_data，避免拆分带来的影响
        overall_sector_distribution = holding_data.groupby([sector_type], as_index=False).agg({'product_NAV': 'sum'})
        overall_sector_distribution['pm_name'] = '账户总体'
        overall_sector_distribution = pd.pivot_table(overall_sector_distribution, values='product_NAV', index='pm_name', columns=sector_type)
        sector_distribution = pd.concat([sector_distribution, overall_sector_distribution[sector_distribution.columns]], axis=0)
    # 计算分布比例
    sector_distribution = sector_distribution[sorted_type_labels].div(sector_distribution[sorted_type_labels].sum(axis=1), axis=0).fillna(0).reset_index()  # 无持仓填充为0
    sector_distribution['date'] = date
    sector_distribution = sector_distribution[['pm_name'] + sorted_type_labels + ['date']]
    return sector_distribution

# ------------------------------------------------------
# FOF账户区间超额收益-跟踪误差(超额波动率)气泡图
# 仅统计需要考核基准的信盈类账户，不包括非信盈类和定制业务
# ------------------------------------------------------
def anlsFOF_getFOFExcessReturnTrackingErrorBubbleMap(
    date,           # 考察日期
    pm_name='全部',  # 投资经理
    period='YTD',   # 统计区间， YTD, 2023, 2022, ...
    account_type=None,  # FOF产品线类型，传入None或者dict. 传入None时不加筛选取所有FOF产品信息
    sector_type='allocation_type',  # 投资经理持仓分布分类标准
    start_date=None,
    inception_before=datetime.date.today() - datetime.timedelta(days=90),
    tracking_error_threshold=0,  # 跟踪误差阈值
):
    assert sector_type in ('allocation_type', 'label_level_1', 'label_level_2'), "sector_type需为'allocation_type', 'label_level_1'或'label_level_2'"
    account_list = custFOF.custFOF_getFOFReferenceData(pm_name=pm_name, portfolio_type=account_type, include_advisory_account=True,
                                                       include_portfolio_oa_id=True, include_additional_info=True, user_permission_setting=True)
    account_list = account_list[account_list['inception_date'] < inception_before]
    account_list = account_list[account_list['kpi_type'] == '信盈类']
    # 筛选在考察日期有基准的账户，避免下方超额计算报错，无基准的账户也会在merge时通过account_list保留
    account_bm_info = custFOF.custFOF_getFOFBMComponent(date)
    account_list = account_list[account_list['portfolio_oa_id'].isin(account_bm_info['portfolio_oa_id'].unique().tolist())]
    # 因投顾账户为周频净值，拆分投顾账户和非投顾账户分别计算
    non_advisory_account_list = account_list[~account_list['advisory_or_not']]['portfolio_id'].to_list()
    advisory_account_list = account_list[account_list['advisory_or_not']]['portfolio_id'].to_list()
    period_perf = pd.DataFrame()
    account_nav = pd.DataFrame()
    if len(non_advisory_account_list) > 0:
        non_advisory_period_perf = anlsFOF_calFOFPerfStats(date, portfolio_ids=non_advisory_account_list, period=period, start_date=start_date,
                                          freq='D', benchmark=True, stats=['period_return', 'annualized_volatility'])
        non_advisory_account_nav = custFOF.custFOF_getFOFNetValueAndReturn(non_advisory_period_perf['end_date'].min(), non_advisory_period_perf['end_date'].max(),
                                                                           non_advisory_account_list, freq='D')
        period_perf = pd.concat([period_perf, non_advisory_period_perf], axis=0)
        account_nav = pd.concat([account_nav, non_advisory_account_nav], axis=0)
    if len(advisory_account_list) > 0:
        advisory_period_perf = anlsFOF_calFOFPerfStats(date, portfolio_ids=advisory_account_list, period=period, start_date=start_date,
                                        freq='W', benchmark=True, stats=['period_return', 'annualized_volatility'])
        advisory_account_nav = custFOF.custFOF_getFOFNetValueAndReturn(advisory_period_perf['end_date'].min(), advisory_period_perf['end_date'].max(),
                                                                       advisory_account_list, freq='W')
        period_perf = pd.concat([period_perf, advisory_period_perf], axis=0)
        account_nav = pd.concat([account_nav, advisory_account_nav], axis=0)
    assert not period_perf.empty, "无数据"
    # 加入AUM数据
    period_perf = pd.merge(period_perf, account_nav[['date', 'portfolio_id', 'AUM']].rename(columns={'date': 'end_date'}), on=['end_date', 'portfolio_id'], how='left')
    period_perf = pd.merge(account_list[['portfolio_id', 'portfolio_name', 'level_3_type', 'kpi_type', 'pm_name', 'benchmark']], period_perf, on='portfolio_id', how='left')
    period_perf = period_perf[['start_date', 'end_date', 'portfolio_id', 'portfolio_name', 'level_3_type', 'kpi_type', 'period_return',
                               'annualized_volatility', 'AUM', 'pm_name', 'benchmark']].sort_values(['level_3_type', 'kpi_type', 'annualized_volatility'], ascending=[True, True, False])
    period_perf['tracking_error_threshold'] = tracking_error_threshold
    period_perf['over_threshold_flag'] = (period_perf['annualized_volatility'] <= tracking_error_threshold).apply(lambda x: '达标' if x else '未达标')
    return period_perf

# ------------------------------------------------------
# 汇总、分类分析FOF账户的历史交易数据
# ------------------------------------------------------
def anlsFOF_summarizeTradesHistoricalFlow(
    start_date,
    end_date,
    pm_name=None,
    portfolio_type=None,  # FOF产品线类型，传入None或者dict. 传入None时不加筛选取所有FOF产品信息
    summary_level=None,
    client_region=None,
):
    assert summary_level in ['产品类型(公募/私募)', '产品一级标签', '产品二级标签', '大类配置类型', '具体产品', '具体策略', '具体公司'], "历史交易流汇总分析目前支持的维度包括：产品类型、一级标签、二级标签、大类配置类型、产品、策略、公司"

    ref_data = custFOF.custFOF_getFOFReferenceData(pm_name, portfolio_type, client_region=client_region, include_advisory_account=True, user_permission_setting=True)
    history_trades = anlsFOF_getTradeHistoricalFlow(start_date, end_date, ref_data['portfolio_id'].dropna().to_list())  # 部分投顾账户未取到portfolio_id，通过dropna筛去
    if summary_level == '产品类型(公募/私募)':
        group_result = history_trades.groupby(['product_type', 'trade_type'], as_index=False)['trade_amount'].sum()
        group_result = group_result.pivot_table(index='product_type', columns='trade_type', values='trade_amount').fillna(0).reset_index()
    else:
        # 对于其他summary_level 首先筛选出公募私募出来并 merge好标签
        history_trades = history_trades[history_trades['product_type'].isin(['公募基金', '私募基金'])]
        mf_product_info = custMF.custMF_getMFProductInfo()[['product_id', 'strategy_id', 'company_id', 'strategy_name', 'company_legal_name', 'label_level_1', 'label_level_2']].rename(columns={'company_legal_name': 'company_name'})
        hf_product_info = custHF.custHF_getProductInfo()[['product_id', 'strategy_id', 'company_id', 'strategy_name', 'company_short_name', 'label_level_1', 'label_level_2']].rename(columns={'company_short_name': 'company_name'})
        product_info = pd.concat([mf_product_info, hf_product_info])
        history_trades = pd.merge(history_trades, product_info, on=['product_id'], how='left')
        history_trades['label_level_1'] = history_trades.apply(lambda x: x['label_level_1'] if 'ETF' not in x['product_name'] else '主观权益', axis=1)
        history_trades['label_level_2'] = history_trades.apply(lambda x: x['label_level_2'] if 'ETF' not in x['product_name'] else 'ETF', axis=1)
        history_trades['allocation_type'] = history_trades['label_level_1'].apply(lambda x: _allocation_type_mapping(x))
        history_trades[['strategy_name', 'company_name', 'label_level_1', 'label_level_2', 'allocation_type']] = history_trades[['strategy_name', 'company_name', 'label_level_1', 'label_level_2', 'allocation_type']].fillna('其他')
        # group处理
        summary_level_map = {'产品一级标签': 'label_level_1', '产品二级标签': 'label_level_2', '大类配置类型': 'allocation_type', '具体产品': 'product_name', '具体策略': 'strategy_name', '具体公司': 'company_name'}
        group_result = history_trades.groupby(['product_type', summary_level_map[summary_level], 'trade_type'], as_index=False)['trade_amount'].sum()
        group_result = group_result.pivot_table(index=['product_type', summary_level_map[summary_level]], columns='trade_type', values='trade_amount').fillna(0).reset_index()
    if '买入' not in group_result.columns:
        group_result['买入'] = 0
    if '卖出' not in group_result.columns:
        group_result['卖出'] = 0
    group_result['净买入'] = group_result['买入'] - group_result['卖出']
    origin_group_result_col = group_result.columns.tolist()
    group_result['start_date'] = history_trades['trade_date'].min()
    group_result['end_date'] = history_trades['trade_date'].max()
    group_result = group_result[['start_date', 'end_date']+origin_group_result_col]

    return group_result

# ------------------------------------------------------
# 获取FOF账户的历史交易数据
# ------------------------------------------------------
def anlsFOF_getTradeHistoricalFlow(
    start_date,
    end_date,
    portfolio_ids=None,     # list, 账户A6_ID, 为None时查询所有结果
    trade_type=None,        # 用于对交易类型筛选
    product_ids=None        # list, 用于筛选持仓产品, 为None时查询全部port的结果
):
    assert trade_type in [None, '买入', '卖出'], "对于交易类型的筛选目前只支持 买入 卖出 或不筛选"
    ref_data = custFOF.custFOF_getFOFReferenceData(include_advisory_account=True)
    result = custFOF.custFOF_getActualTradeHistoricalFlowFromCAMP(start_date, end_date, portfolio_ids)
    result = pd.merge(result, ref_data[['portfolio_id', 'portfolio_name', 'pm_name']], on=['portfolio_id'], how='left')
    result.sort_values(['pm_name', 'portfolio_id', 'trade_date'], inplace=True)
    if trade_type:
        result = result[result['trade_type'].isin([trade_type])]
    if product_ids:
        assert isinstance(product_ids, list), "筛选产品product_ids的输入格式需为list"
        result = result[result['product_id'].isin(product_ids)]
    return result

# -------------------------------------------------------------
# 获取FOF账户的在途交易指令数据
# 在途指令的交易类型包括：理财认购、首次申购、理财申购、全部赎回、理财赎回
# -------------------------------------------------------------
def anlsFOF_getTradeFutureFlow(
    start_date,
    end_date,
    portfolio_ids=None,     # list, 账户A6_ID, 为None时查询所有结果
):
    result = custFOF.custFOF_getTradeFutureFlow(start_date, end_date, portfolio_ids)
    result.sort_values(['pm_name', 'portfolio_id', 'trade_execute_date'], inplace=True)
    return result

# -------------------------------------------------------------------------------------------
# 获取FOF账户未来某时间点的估算持仓情况
# 目前仅从camp获得私募的在途交易指令数据，进行拼接估算
# 在途指令的交易类型包括：理财认购、首次申购、理财申购、全部赎回、理财赎回、理财转入、理财转出，根据交易类型特征去估算未来的持仓情况
# -------------------------------------------------------------------------------------------
def anlsFOF_estimateFutureHoldingData(
    scheduled_date,                     # 指定的未来日期，早于该日期的在途交易都会按照已成交估算
    portfolio_ids,                      # list, 账户A6_ID
    include_initial_trade_date=False    # 是否加入首次申购日期, 默认为False
):
    assert scheduled_date >= datetime.date.today(), "指定的未来日期应晚于或等于今天"
    assert len(portfolio_ids) == 1, "目前估算未来持仓时限制单账户计算"

    base_date = datetime.date.today()    # 当前持仓的基准日期设置为今天，寻找今天前最新的持仓信息
    current_holding = custFOF.custFOF_getFOFHoldingData(base_date - datetime.timedelta(30), base_date, portfolio_ids)
    current_holding = current_holding[current_holding['date'] == current_holding.date.max()]
    # 计算产品估值价格和估值增值
    current_holding['unit_val'] = np.nan
    current_holding['product_appreciation'] = np.nan
    current_holding.loc[current_holding['product_volume'] > 0, 'unit_val'] = current_holding['VAL'] / current_holding['product_volume']
    current_holding.loc[current_holding['product_volume'] > 0, 'product_appreciation'] = current_holding['VAL'] - current_holding['COST']
    # 此处scheduled_trade的start_date前移是因为有一些未走完清算流程的交易还在在途表中，且账户持仓中未体现其变化，其日期已经早于今天，但仍需被纳入
    scheduled_trade = custFOF.custFOF_getTradeFutureFlow(base_date - datetime.timedelta(30), scheduled_date, portfolio_ids=portfolio_ids)
    # 此处需纳入已确认但还未体现在目前最新的持仓的历史交易数据，并入scheduled_trade统一处理
    # 使用来自估值表的交易数据，判断交易是否已确认进估值表
    valuation_confirmed_trade = custFOF.custFOF_getTradeHistoricalFlowFromValuation(base_date - datetime.timedelta(30), base_date, portfolio_ids=portfolio_ids)
    valuation_confirmed_trade = valuation_confirmed_trade[(valuation_confirmed_trade['trade_date'] > current_holding.date.max()) & (valuation_confirmed_trade['trade_type'].isin(['买入', '卖出']))]

    for index, row in valuation_confirmed_trade.iterrows():
        scheduled_trade = scheduled_trade.append({'portfolio_id': row['portfolio_id'],
                                                  'portfolio_name': row['portfolio_name'],
                                                  'trade_entry_date': row['trade_date'],
                                                  'trade_execute_date': row['trade_date'],
                                                  'product_id': row['product_id'],
                                                  'product_name': row['product_name'],
                                                  'trade_type': row['trade_type'],      # 对于持仓未体现的历史交易数据，直接记录买入卖出方向，方便区别进行处理
                                                  'trade_volume': row['trade_amount'] if row['trade_type'] == '买入' else row['trade_volume'],  # 对于持仓未体现的历史交易数据，买入方向记录交易金额，卖出方向记录交易量
                                                  'trade_channel': row['trade_market'],
                                                  'confirm_status': '已确认, 但尚未体现在最新持仓信息中',
                                                  'trade_product_type': row['product_type'],
                                                  }, ignore_index=True)
    if scheduled_trade.empty:
        scheduled_holding = current_holding
        scheduled_holding[['trade_execute_date', 'trade_type', 'confirm_status']] = '', '', ''
    else:
        scheduled_trade.rename(columns={'product_name': 'trade_product_name'}, inplace=True)
        del scheduled_trade['portfolio_name']

        # 当前持仓与在途交易的表格合并
        scheduled_holding = pd.merge(current_holding, scheduled_trade, how='outer', on=['portfolio_id', 'product_id'])
        product_nav_data = custHF.custHF_getHFReturn(scheduled_holding.product_id.to_list(), base_date - datetime.timedelta(30), base_date, 'W', 'Product', include_nav=True)\
                            .rename(columns={'level_id': 'product_id', '单位净值': 'present_unit_nav'})
        present_product_nav = product_nav_data.groupby(['product_id'], as_index=False).apply(lambda x: x[x['date'] == x['date'].max()])
        scheduled_holding = pd.merge(scheduled_holding, present_product_nav[['product_id', 'present_unit_nav']], on='product_id', how='left')

        # 预处理指令,计算申购、赎回涉及金额,之后需与现金项比较
        scheduled_holding['partly_redemption_amount'] = scheduled_holding.apply(lambda x: x['present_unit_nav']*x['trade_volume'] if x['trade_type'] == '理财赎回' else 0, axis=1)
        partly_redemption_amount = scheduled_holding['partly_redemption_amount'].sum()
        fully_redemption_amount = scheduled_holding[scheduled_holding['trade_type'] == '全部赎回']['product_NAV'].sum()
        confirmed_sold_amount = valuation_confirmed_trade[valuation_confirmed_trade['trade_type'] == '卖出']['trade_amount'].sum()  # 对于持仓未体现的历史交易数据，使用交易金额计算
        sum_redemption_amount = fully_redemption_amount + partly_redemption_amount + confirmed_sold_amount
        sum_purchase_amount = scheduled_holding[scheduled_holding['trade_type'].isin(['理财认购', '首次申购', '理财申购', '买入'])]['trade_volume'].sum()
        cash_change = sum_redemption_amount - sum_purchase_amount  # 此项代表所有申赎完成后，剩余现金的数量

        # 预处理指令,计算转入转出涉及金额,因在途交易只包含份额数据,需按照product_unit_nav估算金额,估算时默认理财转换不收取费用
        scheduled_holding['transfer_amount'] = scheduled_holding.apply(lambda x: x['present_unit_nav'] * x['trade_volume'] if x['trade_type'] == '理财转出' else 0, axis=1)
        scheduled_holding['transfer_amount'] = scheduled_holding.apply(lambda x: scheduled_holding[(scheduled_holding['pm_name']==x['pm_name'])&(scheduled_holding['trade_entry_date']==x['trade_entry_date'])&
                                                (scheduled_holding['trade_execute_date']==x['trade_execute_date'])&(scheduled_holding['trade_volume']==x['trade_volume'])]['transfer_amount'].iloc[0] \
                                                if x['trade_type'] == '理财转入' else x['transfer_amount'], axis=1)
        scheduled_holding['COST'] = scheduled_holding.apply(lambda x: 0 if x['trade_type'] == '理财转入' and np.isnan(x['COST']) else x['COST'], axis=1)
        scheduled_holding['VAL'] = scheduled_holding.apply(lambda x: 0 if x['trade_type'] == '理财转入' and np.isnan(x['VAL']) else x['VAL'], axis=1)
        scheduled_holding['product_NAV'] = scheduled_holding.apply(lambda x: 0 if x['trade_type'] == '理财转入' and np.isnan(x['product_NAV']) else x['product_NAV'], axis=1)
        scheduled_holding['product_type'] = scheduled_holding.apply(lambda x: '私募基金' if x['trade_type'] == '理财转入' and np.isnan(x['product_type']) else x['product_type'], axis=1)
        scheduled_holding['product_name'] = scheduled_holding.apply(lambda x: x['trade_product_name'] if pd.isnull(x['product_name']) else x['product_name'], axis=1)
        # 统一处理所有交易指令
        def _calScheduledDateHolding(x):
            if x['trade_type'] == '理财认购':
                x['product_name'], x['COST'], x['VAL'], x['product_NAV'], x['product_type'] = x['trade_product_name'], x['trade_volume'], x['trade_volume'], x['trade_volume'], '私募基金'
            elif x['trade_type'] == '首次申购':
                x['product_name'], x['COST'], x['VAL'], x['product_NAV'], x['product_type'] = x['trade_product_name'], x['trade_volume'], x['trade_volume'], x['trade_volume'], '私募基金'
            elif x['trade_type'] == '理财申购':
                x['COST'], x['VAL'], x['product_NAV'] = x['COST'] + x['trade_volume'], x['VAL'] + x['trade_volume'], x['product_NAV'] + x['trade_volume']
            elif x['trade_type'] == '理财转入':
                x['product_name'], x['COST'], x['VAL'], x['product_NAV'] = x['trade_product_name'], x['COST'] + x['transfer_amount'], x['VAL'] + x['transfer_amount'], x['product_NAV'] + x['transfer_amount']
            elif x['trade_type'] == '买入':
                if pd.isna(x['portfolio_name']):  # 对于首次买入情形
                    x['product_name'], x['COST'], x['VAL'], x['product_NAV'], x['product_type'] = x['trade_product_name'], x['trade_volume'], x['trade_volume'], x['trade_volume'], x['trade_product_type']
                else:  # 对于增持情形
                    x['COST'], x['VAL'], x['product_NAV'] = x['COST'] + x['trade_volume'], x['VAL'] + x['trade_volume'], x['product_NAV'] + x['trade_volume']
            elif x['trade_type'] == '全部赎回':
                x['COST'], x['VAL'], x['product_NAV'] = 0, 0, 0
            elif x['trade_type'] in ['理财赎回', '理财转出', '卖出']:
                residual_ratio = (x['product_volume']-x['trade_volume'])/x['product_volume']  # 对于部分赎回、理财转出和未体现的历史数据，计算卖出的比例，对持仓进行处理
                x['COST'], x['VAL'], x['product_NAV'] = x['COST']*residual_ratio, x['VAL']*residual_ratio, x['product_NAV']*residual_ratio
            # 处理现金项的变化，若为负也保留并继续输出，说明当前的交易未配平
            if x['product_type'] == '活期存款':
                x['COST'], x['VAL'], x['product_NAV'] = x['COST'] + cash_change, x['VAL'] + cash_change, x['product_NAV'] + cash_change
            return x
        scheduled_holding = scheduled_holding.apply(_calScheduledDateHolding, axis=1)

        # 如果持仓中没有活期存款项，现金变化无法体现，则新增"虚拟活期存款"项 作为一行
        if '活期存款' not in scheduled_holding['product_type'].to_list():
            scheduled_holding = scheduled_holding.append({'COST': cash_change, 'VAL': cash_change, 'product_NAV': cash_change,
                                                          'product_name': '虚拟活期存款', 'product_type': '虚拟活期存款'}, ignore_index=True)

        # 整理表格 重算权重值
        del scheduled_holding['pm_name'], scheduled_holding['trade_entry_date'], scheduled_holding['trade_product_name'], \
            scheduled_holding['trade_volume'], scheduled_holding['trade_channel'], scheduled_holding['present_unit_nav'], scheduled_holding['partly_redemption_amount']
        scheduled_holding[['portfolio_name', 'portfolio_id', 'inception_date', 'NAV', 'date']] = scheduled_holding[['portfolio_name',  'portfolio_id', 'inception_date', 'NAV', 'date']].fillna(method='ffill')
        scheduled_holding['product_weight'] = scheduled_holding['product_NAV']/scheduled_holding['NAV']
        scheduled_holding.sort_values(by=['product_weight'], ascending=False, inplace=True)

    scheduled_holding = _append_product_label_info(scheduled_holding)
    # 加入未来持仓产品的首次申购时间，此处使用下单日期
    if include_initial_trade_date:
        actual_historical_trade = custFOF.custFOF_getActualTradeHistoricalFlowFromCAMP(const.const.SI_START_DATE, base_date, portfolio_ids)
        product_initial_trades = actual_historical_trade.sort_values(['product_id', 'trade_date']).groupby(['product_id'], as_index=False).first().rename(columns={'trade_date': 'initial_trade_date'})
        scheduled_holding = pd.merge(scheduled_holding, product_initial_trades[['product_id', 'initial_trade_date']], how='left', on='product_id')
    return scheduled_holding

# -------------------------------------------------------------------------------------------
# 获取单一FOF账户未来某时间点的估算持仓并计算持仓类别汇总数据，绘制饼图
# 目前仅从camp获得私募的在途交易指令数据，进行拼接估算
# -------------------------------------------------------------------------------------------
def anlsFOF_estimateFutureHoldingSectorInfo(
    scheduled_date,                     # 指定的未来日期，早于该日期的在途交易都会按照已成交估算
    portfolio_ids,                      # list, 账户A6_ID
    level='product_type',               # 持仓类别汇总维度 Other options: label_level_1, label_level_2, allocation_type
):
    assert level in ['product_type', 'label_level_1', 'label_level_2', 'allocation_type'], '输入的level有误，请重新输入'
    level_col_map = {
        'groupby': {
            'allocation_type': ['allocation_type'],
            'product_type': ['product_type'],
            'label_level_1': ['allocation_type', 'label_level_1'],
            'label_level_2': ['allocation_type', 'label_level_1', 'label_level_2'],
        },
        'sort': {
            'allocation_type': ['product_NAV'],
            'product_type': ['product_NAV'],
            'label_level_1': ['allocation_type', 'product_NAV'],
            'label_level_2': ['allocation_type', 'label_level_1', 'product_NAV'],
        },
    }
    estimate_holding = anlsFOF_estimateFutureHoldingData(scheduled_date, portfolio_ids)
    agg_data = estimate_holding.groupby(level_col_map['groupby'][level], as_index=False)['product_NAV'].sum()
    agg_data = agg_data.sort_values(by=level_col_map['sort'][level], ascending=False).reset_index(drop=True)
    agg_data.rename(columns={'product_NAV': 'sector_NAV'}, inplace=True)
    agg_data['sector_weight'] = agg_data['sector_NAV']/agg_data['sector_NAV'].sum()
    return agg_data

# ----------------------------------------------------------------
# FOF组合投资的底层资产（产品或策略或公司）反查历史交易记录的汇总
# ----------------------------------------------------------------
def anlsFOF_getTradeHistoricalFlowSummaryByAsset(
    start_date,
    end_date,
    level_ids,      # 产品或策略或公司ids, 与level选项对应
    product_type,   # 目前支持 私募产品, 公募产品
    level,          # 资产层级 目前支持 产品 策略 公司
    pm_name=None,
    port_type=None,
    client_region=None,
    detail_mode=False,  # 展示详细交易记录
):
    assert product_type in ['私募基金', '公募基金'], "产品类别选项仅支持'私募基金', '公募基金'"
    assert level in ['产品', '策略', '公司'], "资产层级选项仅支持'产品', '策略', '公司'"

    level_cols_mapping = {
        '产品': {'id': 'product_id', 'name': 'product_name'},
        '策略': {'id': 'strategy_id', 'name': 'strategy_name'},
        '公司': {'id': 'company_id', 'name': 'company_name'},
    }
    ref_data = custFOF.custFOF_getFOFReferenceData(pm_name, port_type, client_region=client_region, include_advisory_account=True, user_permission_setting=True)
    history_trades = anlsFOF_getTradeHistoricalFlow(start_date, end_date, ref_data['portfolio_id'].dropna().to_list())  # 部分投顾账户未取到portfolio_id，通过dropna筛去
    # 将为空的pm_name信息设为“空”，防止groupby的时候数据消失
    history_trades['pm_name'] = history_trades['pm_name'].fillna('NA')
    history_trades = _append_product_label_info(history_trades, include_company_strategy_info=True)
    history_trades = history_trades[history_trades[level_cols_mapping[level]['id']].str.split('.', expand=True)[0].isin([level_id.split('.')[0] for level_id in level_ids])]
    if history_trades.empty:
        return history_trades
    if detail_mode:
        history_trades = history_trades.sort_values(by=['pm_name', 'company_name', 'strategy_name', 'product_name', 'trade_date'], ascending=False).reset_index()
        ret = history_trades[['portfolio_name', 'pm_name', 'company_name', 'strategy_name', 'product_name', 'product_id', 'trade_date',
                              'trade_type', 'trade_price', 'trade_volume', 'trade_amount']]
    else:
        group_result = history_trades.groupby(['portfolio_id', 'portfolio_name', 'pm_name', level_cols_mapping[level]['id'], level_cols_mapping[level]['name'], 'trade_type'], as_index=False)['trade_amount'].sum()
        group_result = group_result.pivot_table(index=['portfolio_name', 'pm_name', level_cols_mapping[level]['id'], level_cols_mapping[level]['name']], columns='trade_type', values='trade_amount').fillna(0).reset_index()
        if '买入' not in group_result.columns:
            group_result['买入'] = 0
        if '卖出' not in group_result.columns:
            group_result['卖出'] = 0
        group_result['净买入'] = group_result['买入'] - group_result['卖出']
        group_result.sort_values(by=[level_cols_mapping[level]['name'], 'pm_name', '净买入'], ascending=False, inplace=True)
        group_result = group_result.append({'portfolio_name': '合计', level_cols_mapping[level]['name']: '', level_cols_mapping[level]['id']: '', '买入': group_result['买入'].sum(),
                                            '卖出': group_result['卖出'].sum(), '净买入': group_result['净买入'].sum(), 'pm_name': ''}, ignore_index=True)
        ret = group_result[['portfolio_name', 'pm_name', level_cols_mapping[level]['name'], level_cols_mapping[level]['id'], '买入', '卖出', '净买入']]
    return ret

# ----------------------------------------------------------------
# FOF组合投资的底层资产（产品或策略或公司）反查未来交易记录的汇总
# ----------------------------------------------------------------
def anlsFOF_getTradeFutureFlowSummaryByAsset(
    start_date,
    end_date,
    level_ids,      # 产品或策略或公司ids, 与level选项对应
    product_type,   # 目前支持 私募产品
    level,          # 资产层级 目前支持 产品 策略 公司
    pm_name=None,   # 会按照账户投资经理和交易录单人取并集去筛选
    port_type=None,
    client_region=None,
):
    assert product_type in ['私募基金'], "产品类别选项仅支持'私募基金'"
    assert level in ['产品', '策略', '公司'], "资产层级选项仅支持'产品', '策略', '公司'"

    level_cols_mapping = {
        '产品': {'id': 'product_id', 'name': 'product_name'},
        '策略': {'id': 'strategy_id', 'name': 'strategy_name'},
        '公司': {'id': 'company_id', 'name': 'company_name'},
    }
    # pm_name先进行全选，后面按照账户投资经理和具体下单同事取并集去筛选
    ref_data = custFOF.custFOF_getFOFReferenceData(pm_name=None, portfolio_type=port_type, client_region=client_region, include_advisory_account=True, user_permission_setting=True)
    future_trades = anlsFOF_getTradeFutureFlow(start_date, end_date, ref_data['portfolio_id'].dropna().to_list()).rename(columns={'pm_name': 'execute_pm_name'})  # 部分投顾账户未取到portfolio_id，通过dropna筛去
    future_trades = pd.merge(future_trades, ref_data[['portfolio_id', 'pm_name']], on='portfolio_id', how='left')
    # pm_name筛选
    if pm_name is not None:
        future_trades = future_trades[(future_trades['pm_name'].str.contains(pm_name, na=False)) | (future_trades['execute_pm_name'].str.contains(pm_name, na=False))]
    hf_info = custHF.custHF_getProductInfo()[['product_id', 'strategy_id', 'strategy_name', 'company_id', 'company_short_name']].rename(columns={'company_short_name': 'company_name'})
    future_trades = pd.merge(future_trades, hf_info, how='left', on='product_id')  # 将策略、公司级信息拼接上
    if level_ids is not None:
        future_trades = future_trades[future_trades[level_cols_mapping[level]['id']].isin(level_ids)]
    if future_trades.empty:
        return future_trades
    future_trades = future_trades.sort_values(['pm_name', 'portfolio_id', 'trade_execute_date', 'company_name', 'strategy_name']).reset_index()
    return future_trades

# -------------------------------------------------------------------------------------------
# 获取FOF账户从今日至未来某日期的T0可用资金的估算情况
# 目前利用从camp获得私募的在途交易指令数据，叠加平台前端用户输入/缓存的交易试算指令进行计算
# 输出包括T0可用金额变化的时序表，以及在途交易和录入试算指令合并后的明细表
# -------------------------------------------------------------------------------------------
def anlsFOF_estimateFutureT0AvailableCashSerie(
    portfolio_ids,      # list, 账户A6_ID
    scheduled_date,     # 指定的未来日期，早于该日期的在途交易和试算指令都会按照已成交估算
):
    assert scheduled_date > datetime.date.today(), "指定的未来日期应晚于今天"
    assert len(portfolio_ids) == 1, "目前估算未来持仓时限制单账户计算"

    wind_calendar = wind.wind_getSSECalendar()

    # 1. 合并在途交易和用户缓存的交易指令
    base_date = wind_calendar[wind_calendar['date'] <= datetime.date.today()]['date'].iloc[-1]
    # 模型认为当日的交易已经点击下单，T0可用资金的变化已经体现当天的交易，故数据从T+1的试算交易数据开始取
    # 由于还需要考虑已下单的赎回交易指令带来的可用金额变化，在途交易数据需再向前取3交易日
    scheduled_trade = custFOF.custFOF_getTradeFutureFlow(wind_calendar[wind_calendar['date'] <= base_date]['date'].iloc[-4], scheduled_date, portfolio_ids=portfolio_ids)
    scheduled_trade = scheduled_trade[scheduled_trade['trade_volume'] < 1e9]  # 筛去作为占位使用的交易指令
    history_trade = custFOF.custFOF_getActualTradeHistoricalFlowFromCAMP(wind_calendar[wind_calendar['date'] <= base_date]['date'].iloc[-10], base_date, portfolio_ids=portfolio_ids)
    trial_trade = custFOF.custFOF_getTrialTradeOrder(base_date, scheduled_date, portfolio_ids=portfolio_ids)
    # 由于会存在先录入trial_trade后，又实际在camp进行预约交易的情况，上述两组数可能会有重复的条目，目前认为产品+日期+金额完全一致的就是重复项，会剔除重复
    for index, row in scheduled_trade.iterrows():
        trial_trade = trial_trade[~((trial_trade['product_id'] == row['product_id']) & (trial_trade['trade_date'] == row['trade_execute_date']) & ((trial_trade['trade_amount'] == row['trade_volume']) | (trial_trade['trade_volume'] == row['trade_volume'])))]  # 注意科目上的对齐
        # 对于全部赎回的指令,再进行一次判断,因为金证所计算的全部赎回份额可以实时考虑当日是否有分红(报酬),可能会导致金证(CAMP)指令的赎回份额与持仓份额不一致
        trial_trade = trial_trade[~((trial_trade['product_id'] == row['product_id']) & (trial_trade['trade_date'] == row['trade_execute_date']) & (trial_trade['trade_type'] == '全部赎回') & (row['trade_type'] == '全部赎回'))]  # 注意科目上的对齐
    for index, row in history_trade.iterrows():
        scheduled_trade = scheduled_trade[~((scheduled_trade['product_id'] == row['product_id']) & (scheduled_trade['trade_execute_date'] == row['trade_date']) & ((scheduled_trade['trade_volume'] == row['trade_volume']) | (scheduled_trade['trade_volume'] == row['trade_amount'])))]
    receivable_history_trade = history_trade[(history_trade['trade_date'] > wind_calendar[wind_calendar['date'] <= base_date]['date'].iloc[-4]) & (history_trade['trade_type'].str.contains('卖出'))]
    scheduled_trade['trade_amount'] = scheduled_trade.apply(lambda x: x['trade_volume'] if (('申购' in str(x['trade_type'])) | ('认购' in str(x['trade_type']))) else None, axis=1) if not scheduled_trade.empty else None
    trial_trade = trial_trade.rename(columns={'trade_date': 'trade_execute_date'})
    receivable_history_trade = receivable_history_trade.rename(columns={'trade_date': 'trade_execute_date'})
    scheduled_trade['scheduled_trade_type'] = 'CAMP已录入'
    trial_trade['scheduled_trade_type'] = '模拟试算'
    receivable_history_trade['scheduled_trade_type'] = '交易已确认,但赎回款可能未到账'
    combined_scheduled_trade = pd.concat([scheduled_trade,
                                          trial_trade[['portfolio_id', 'portfolio_name', 'trade_execute_date', 'product_id', 'product_name', 'trade_type', 'trade_volume', 'trade_amount', 'scheduled_trade_type', 'redemption_interval']],
                                          receivable_history_trade[['portfolio_id', 'trade_execute_date', 'product_id', 'product_name', 'trade_type', 'trade_volume', 'trade_amount', 'scheduled_trade_type']]])
    assert len(combined_scheduled_trade) > 0, "未检测到区间内的在途交易指令 或者 赎回款未到账的情况, 暂停试算."
    # 计算每笔交易的赎回款到账T0可用的预计时间
    combined_scheduled_trade['settlement_payment_date'] = combined_scheduled_trade.\
            apply(lambda x: (wind_calendar[wind_calendar['date'] >= x['trade_execute_date']]['date'].iloc[2 if x['product_id'][:2] == '90' else 3]) if ('赎回' in str(x['trade_type']) or '卖出' in str(x['trade_type'])) else None, axis=1)
    # 更新自定义的预期赎回款到账时间
    combined_scheduled_trade['settlement_payment_date'] = combined_scheduled_trade.\
            apply(lambda x: (wind_calendar[wind_calendar['date'] >= x['trade_execute_date']]['date'].iloc[int(x['redemption_interval'])] if pd.notna(x['redemption_interval']) else x['settlement_payment_date']) if ('赎回' in str(x['trade_type']) or '卖出' in str(x['trade_type'])) else None, axis=1)

    # 2. 逐日计算T0可用
    holding_data = custFOF.custFOF_getFOFHoldingData(base_date-datetime.timedelta(10), base_date, portfolio_ids)
    holding_data = holding_data.merge(custFOF.custFOF_getT0AvailableCash(), on=['portfolio_id'], how='left')
    holding_data['trade_date'] = holding_data['date']
    t0_available_cash = holding_data['t0_available_cash'].iloc[-1]

    result = []
    # 首日情况
    result.append(pd.DataFrame({
        'trade_date': [base_date],
        'today_t0_available': [t0_available_cash],
    }))
    # 未来情况的估算
    for step in range((scheduled_date - base_date).days):
        observe_date = base_date + datetime.timedelta(step+1)
        today_scheduled_trade = combined_scheduled_trade[(combined_scheduled_trade['trade_execute_date'] == observe_date) & (combined_scheduled_trade['trade_type'].str.contains('申购') | combined_scheduled_trade['trade_type'].str.contains('认购'))]
        today_scheduled_trade['trade_date'] = observe_date
        t0_available_cash -= today_scheduled_trade['trade_amount'].sum()
        today_scheduled_trade['trade_volume'] = None

        today_t0_available_add = combined_scheduled_trade[(combined_scheduled_trade['settlement_payment_date'] == observe_date) & (combined_scheduled_trade['trade_type'].str.contains('赎回') | combined_scheduled_trade['trade_type'].str.contains('卖出'))]
        today_t0_available_add = pd.merge(today_t0_available_add, holding_data[['trade_date', 'product_id', 'product_volume', 'product_NAV']], on=['trade_date', 'product_id'], how='left') if observe_date <= holding_data['date'].max() else pd.merge(today_t0_available_add, holding_data[holding_data['date'] == holding_data['date'].max()][['product_id', 'product_volume', 'product_NAV']], on=['product_id'], how='left')
        today_t0_available_add['trade_date'] = observe_date
        if not today_t0_available_add.empty:
            today_t0_available_add['redemption_amount'] = today_t0_available_add.apply(lambda x: x['product_NAV'] * x['trade_volume'] / x['product_volume'] if not np.isnan(x['product_volume']) else x['trade_volume'], axis=1)
            t0_available_cash += today_t0_available_add['redemption_amount'].sum()
            today_t0_available_add['trade_amount'] = today_t0_available_add['redemption_amount']
            del today_t0_available_add['redemption_amount'], today_t0_available_add['product_volume'], today_t0_available_add['product_NAV']
        today_result = pd.concat([today_scheduled_trade, today_t0_available_add])
        if today_result.empty:
            result.append(pd.DataFrame({
                'trade_date': [observe_date],
                'today_t0_available': [t0_available_cash],
            }))
        else:
            today_result['today_t0_available'] = t0_available_cash
            result.append(today_result)

    t0_available_details = pd.concat(result)

    # 对于有在途交易指令但是并不对未来T0可用产生影响的场景，assert不再试算。比如在途里面仅有今日的申购，且试算指令为空的情况。
    assert set(t0_available_details.columns) > {'trade_date', 'today_t0_available'}, "未检测到区间内(自明日起)的在途交易指令 或者 赎回款未到账的情况, 暂停试算."
    # 补充基础信息，对数据无影响
    t0_available_details[['portfolio_id', 'portfolio_name', 'pm_name']] = t0_available_details[['portfolio_id', 'portfolio_name', 'pm_name']].fillna(method='ffill')
    t0_available_details[['portfolio_id', 'portfolio_name', 'pm_name']] = t0_available_details[['portfolio_id', 'portfolio_name', 'pm_name']].fillna(method='bfill')
    t0_available_details.reset_index(drop=True, inplace=True)

    return {'t0_available_details': t0_available_details, 'combined_scheduled_trade': combined_scheduled_trade}


# ----------------------------------------------------------------
# FOF组合投委会基准的信息展示
# 能够展示全量的时序上的投委会基准成分情况
# ----------------------------------------------------------------
def anlsFOF_getFOFInvestCommiteeBMDetail(
    date=None,          # 数据日期(观察日期)，默认取该账户在所有区间的投委会基准情况，用于判断是否发生过变更以及进行时序分析
    portfolio_id=None,  # 默认取全量数据，指定账户请输入账户ID的list
):
    port_bm_data = custFOF.custFOF_getFOFBMComponent(date, portfolio_id)
    port_bm_data = port_bm_data[['portfolio_oa_id', 'portfolio_id', 'portfolio_name', 'effect_from', 'effect_to', 'bm_id', 'bm_name', 'bm_weight', 'coefficient', 'bm_allocation_type', 'bm_allocation_type_order']]
    return port_bm_data

# ----------------------------------------------------------------
# FOF组合相对投委会基准的择时分析
# 基准成分的收益率（800 CAMO2 885008）运行mock组合，并与基准进行对比
# 对组合的模拟回测会按照交易日期，取在三个大类上的delta权重变化进行调仓，对基准的模拟是每半年度进行再平衡(回到中枢)，中枢变化时也再平衡
# 模拟组合仓位都是100%，非权益、CTA的仓位均由885008补全
# 输出：投资组合和投委会基准的mock组合的净值和收益率数据
# ----------------------------------------------------------------
def anlsFOF_FOFPositionTimingAnalysis(
    portfolio_id,       # 投资组合的ID, str
    date,
    period,
    start_date=None,
    single_asset=None,  # 是否只考虑单资产的择时效果，默认考虑账户整体，输入None；目前支持输入“EQUITY”、“CTA”选项，单独进行分析
):
    assert period in ('YTD', 'YTLDLM', '2024', '2023', '2022', '2021', '2020', '2019', 'SI', 'Customized', 'Today'), \
        "统计区间，只能为YTD, 2022, 2021, 2020, 2019, Today 以及SI（均为字符串格式）"
    assert single_asset in (None, 'EQUITY', 'CTA'), "单资产择时效果的模式目前支持权益和CTA"

    start_date, end_date = calendar.calender_getStartEndDate(period, date, start_date)
    # 取start_date之前的上一个交易日
    wind_calender = wd.wind_getSSECalendar()
    wind_calender_history = wind_calender.loc[(wind_calender['date'] < start_date), 'date']
    start_date = wind_calender_history.iloc[-1]
    assert end_date > start_date, "起始日期晚于结束日期"
    single_asset_map = {'EQUITY': '权益', 'CTA': 'CTA'}

    # STEP1: 对日历的处理，得到交易日历和再平衡的日期
    holding_data = anlsFOF_getFOFSectorInfo(portfolio_id=portfolio_id, start_date=start_date, date=end_date, level='allocation_type', data_mode='TS', mf_wind_allocation_type=True)
    holding_data['allocation_type'] = holding_data['allocation_type'].apply(lambda x: '权益' if x == '复合策略' else x)
    start_date = max(start_date, holding_data['date'].min())
    end_date = min(end_date, holding_data['date'].max())
    bm_data = anlsFOF_getFOFInvestCommiteeBMDetail(portfolio_id=[portfolio_id])
    bm_data = bm_data[(bm_data['effect_from'] <= end_date) & (bm_data['effect_to'] > start_date)]
    trade_calendar = wind_calender.copy(deep=True)
    trade_calendar = trade_calendar[(trade_calendar['date'] >= start_date) & (trade_calendar['date'] <= end_date)]
    trade_data = anlsFOF_getTradeHistoricalFlow(start_date, end_date, [portfolio_id])
    # 投资组合的mock使用交易情况进行调仓
    trade_date_list = list(trade_data['trade_date'].unique())
    # 基准的mock每半年再平衡一次
    rebalance_date_list = trade_calendar.iloc[::int(const.const.ANNUAL_SCALE/2)]['date'].tolist()
    # 投委会基准切换的日期，也需进行再平衡
    rebalance_date_list += list(bm_data[bm_data['effect_from'] > datetime.date(2000,1,1)]['effect_from'].unique())
    rebalance_date_list.sort()

    # STEP2: 取出基准成分中的指数的收益率，以及再平衡日期所需配置的权重，准备好回测的输入
    # 取所需基准的收益率并整合
    bm_data['bm_mapping_id'] = bm_data['bm_id'].apply(lambda x: config.FOF_investment_commitee_bm_info[x]['bm_mapping_id'])
    bm_ret = []
    for _, row in bm_data[['bm_allocation_type', 'bm_mapping_id']].drop_duplicates().iterrows():
        single_bm_ret = wd.wind_getIndexReturn(row['bm_mapping_id'], start_date, end_date, 'D').reset_index().rename(columns={row['bm_mapping_id']: 'index_return_rate'})
        single_bm_ret['index_id'] = row['bm_mapping_id']
        single_bm_ret['allocation_type'] = row['bm_allocation_type']
        single_bm_ret = single_bm_ret[['date', 'index_id', 'allocation_type', 'index_return_rate']]
        bm_ret.append(single_bm_ret)
    # 如果投委会基准中没有绝对收益的部分，需要再额外取一下，保证后续回测数据齐全
    if '绝对收益' not in bm_data['bm_allocation_type'].unique().tolist():
        single_bm_ret = wd.wind_getIndexReturn('885008.WI', start_date, end_date, 'D').reset_index().rename(columns={'885008.WI': 'index_return_rate'})
        single_bm_ret['index_id'] = '885008.WI'
        single_bm_ret['allocation_type'] = '绝对收益'
        single_bm_ret = single_bm_ret[['date', 'index_id', 'allocation_type', 'index_return_rate']]
        bm_ret.append(single_bm_ret)
    bm_ret = pd.concat(bm_ret)
    # 按照大类资产和日期，对收益率进行整理
    bm_ret_pivot = bm_ret.pivot(index='date', values='index_return_rate', columns='allocation_type')

    # STEP3: 按照大类资产和日期，对再平衡日期上的各项权重进行整理，得到可输入回测的调仓/再平衡具体数据表
    bm_mock_position = pd.DataFrame(columns=['date']+list(bm_ret_pivot.columns))
    bm_mock_position['date'] = pd.Series(rebalance_date_list)
    port_mock_trade_record = pd.DataFrame(columns=['date']+list(bm_ret_pivot.columns))
    port_mock_trade_record['date'] = pd.Series(trade_date_list)
    trade_data = _append_product_label_info(trade_data, mf_wind_allocation_type=True)
    trade_data['allocation_type'] = trade_data['allocation_type'].apply(lambda x: '绝对收益' if x not in ['权益', 'CTA'] else x)
    trade_data['trade_amount'] = trade_data.apply(lambda x: -1 * x['trade_amount'] if x['trade_type'] == '卖出' else x['trade_amount'], axis=1)
    for col in bm_ret_pivot.columns:
        bm_mock_position[col] = bm_mock_position.apply(lambda x: bm_data[(bm_data['effect_from'] <= x['date']) & (bm_data['effect_to'] > x['date']) & (bm_data['bm_allocation_type'] == col)]['bm_weight'].sum(), axis=1)
        port_mock_trade_record[col] = port_mock_trade_record.apply(lambda x: trade_data[(trade_data['trade_date'] == x['date']) & (trade_data['allocation_type'] == col)]['trade_amount'].sum()
                                                                     / holding_data[holding_data['date'] == x['date']]['sector_NAV'].sum(), axis=1)
    port_mock_position = bm_mock_position.copy(deep=True)
    port_mock_position = port_mock_position[:1]
    # 如果账户份额发生大幅变化(客户申赎造成现金项的增减)，会影响影响各资产权重，对此现象也认为是一种交易(单日内对资产权重的影响)，添加到交易的记录中
    port_total_share = custFOF.custFOF_getFOFHoldingData(start_date, end_date, [portfolio_id], include_portfolio_oa_id=True).\
                        groupby(['portfolio_id', 'portfolio_name', 'date'], as_index=False)['total_share', 'total_NAV'].last()
    port_total_share['date_shift_1'] = port_total_share['date'].shift(1)
    port_total_share['total_share_shift_1'] = port_total_share['total_share'].shift(1)
    port_total_share['total_NAV_shift_1'] = port_total_share['total_NAV'].shift(1)
    port_total_share['total_share_change_pct'] = port_total_share['total_share'].pct_change()
    port_total_share = port_total_share[port_total_share['total_share_change_pct'].abs() >= 0.01]  # 认为份额变化1%以上会产生不可忽略的影响
    # 对每类资产计算客户申赎带来的影响，并且将结果并入交易记录
    if not port_total_share.empty:
        for col in bm_ret_pivot.columns:
            port_total_share[col] = port_total_share.apply(lambda x: holding_data[(holding_data['date'] == x['date_shift_1']) & (holding_data['allocation_type'] == col)]['sector_weight'].sum() * (-x['total_share_change_pct']/(1+x['total_share_change_pct'])), axis=1)
        port_mock_trade_record = pd.concat([port_mock_trade_record, port_total_share[['date']+list(bm_ret_pivot.columns)]])
        port_mock_trade_record.sort_values('date', inplace=True)
        port_mock_trade_record = port_mock_trade_record.groupby('date', as_index=False).sum()
    # mock时均按照满仓配置
    # 考察组合整体时:权益、CTA之外的仓位都归至绝对收益; 不管原始状态有没有“绝对收益”，都加上这一列，保证权重和是100%
    if not single_asset:
        bm_mock_position['绝对收益'] = bm_mock_position.apply(lambda x: 1 - x[list(set(bm_ret_pivot.columns) - {'绝对收益', 'date'})].sum(), axis=1)
        port_mock_position['绝对收益'] = port_mock_position.apply(lambda x: 1 - x[list(set(bm_ret_pivot.columns) - {'绝对收益', 'date'})].sum(), axis=1)
    # 考察单一资产时:只保留该资产的仓位情况
    else:
        assert single_asset_map[single_asset] in list(bm_ret_pivot.columns), "账户基准中无该类资产类别，不适配"
        bm_mock_position[bm_mock_position.columns.drop(['date', single_asset_map[single_asset]])] = 0
        port_mock_position[port_mock_position.columns.drop(['date', single_asset_map[single_asset]])] = 0
        port_mock_trade_record[port_mock_trade_record.columns.drop(['date', single_asset_map[single_asset]])] = 0

    # STEP4: 回测，得到两个组合的模拟净值数据并计算收益率数据
    port_mock_nav = _position_timing_mock_backtest(port_mock_position.set_index('date'), bm_ret_pivot, port_mock_trade_record.set_index('date'), trade_record_mode=True, single_asset=single_asset)
    bm_mock_nav = _position_timing_mock_backtest(bm_mock_position.set_index('date'), bm_ret_pivot, single_asset=single_asset)

    # 整理
    level_info = custFOF.custFOF_getFOFReferenceData()
    port_name = level_info[level_info['portfolio_id'] == portfolio_id]['portfolio_name'].iloc[0]
    port_mock_nav['id'] = port_name + '(' + ((single_asset_map[single_asset] + '部分') if single_asset else '') + '模拟)'
    bm_mock_nav['id'] = port_name + '-比较基准(' + ((single_asset_map[single_asset] + '部分') if single_asset else '') + '模拟)'
    # 把port_mock中客户申赎的日期点和bm_mock的再平衡和调整的点标记出来
    port_mock_nav['highlight_trade_date'] = port_mock_nav.apply(lambda x: 'SUBSCRIPTION_REDEEM' if x['date'] in port_total_share['date'].tolist() else None, axis=1)
    bm_mock_nav['highlight_trade_date'] = port_mock_nav.apply(lambda x: 'REBALANCE' if x['date'] in rebalance_date_list[1:] else None, axis=1)

    # STEP4: 计算绩效数据
    perf_table = _position_timing_mock_perf_stats(port_mock_nav[['date', 'id', 'return']], bm_mock_nav[['date', 'id', 'return']], [period], start_date if period == 'Customized' else None)

    return port_mock_nav, bm_mock_nav, perf_table

# ----------------------------------------------------------------
# FOF组合相对投委会基准的择时分析 - 模拟组合回测的私有函数
# 输入：1.目标仓位，时序数据，index是date，认为当期盘后调整为新仓位权重()；2.各资产收益表，默认index(date数据)是顺序的，已按照所需频率维护完善的，将直接按照此表日历进行遍历
# 以上两个输入列名一致，所输入的目标仓位会根据资产收益表的频率及区间实现自适应
# 输出：模拟组合回测所得的净值曲线数据以及组合收益率数据
# ----------------------------------------------------------------
def _position_timing_mock_backtest(
    target_position,
    asset_return,
    trade_record=None,
    trade_record_mode=False,    # 打开后则使用交易记录输入模式，trade_record存放的是权重的变化（代表交易记录）, target_position只需存储首日的配置比例
    single_asset=None,          # 是否只考虑单资产的择时效果，默认考虑账户整体，输入None；目前支持输入“EQUITY”、“CTA”选项，单独进行分析
):
    assert set(list(target_position.columns)) == set(list(asset_return.columns)), "请检查回测输入，保证所对应的列是一致的"
    target_position = target_position[~target_position.index.duplicated()]
    if trade_record_mode:
        assert trade_record is not None
        trade_record = trade_record[~trade_record.index.duplicated()]
    else:
        assert trade_record is None

    asset_list = list(asset_return.columns)
    mock_nav = asset_return.copy(deep=True)
    mock_nav[asset_list] = 0
    mock_nav['exception'] = 0  # 空仓部分 始终收益率为0
    mock_nav['nav'] = 1
    # 对首日的资产情况进行初始化
    mock_nav.loc[asset_return.index.min()] = [target_position.loc[target_position.index.min(), asset_col] for asset_col in asset_list] +\
                                             [1 - target_position.loc[target_position.index.min(), asset_list].sum(), 1]
    mock_nav.sort_index(inplace=True)
    mock_nav['date_shift1'] = mock_nav.index
    mock_nav['date_shift1'] = mock_nav['date_shift1'].shift(1)
    asset_return = asset_return.join(mock_nav['date_shift1'], how='left').fillna(0)  # 该dataframe内均为收益率数据，需fillna0否则影响计算准确性
    for index, row in asset_return.iterrows():
        # 首日已处理，跳过
        if index == asset_return.index.min():
            continue
        # 收益计算
        for asset_col in asset_list:
            mock_nav.loc[index, asset_col] = mock_nav.loc[row['date_shift1'], asset_col] * (1 + row[asset_col])
        mock_nav.loc[index, 'exception'] = mock_nav.loc[row['date_shift1'], 'exception']
        mock_nav.loc[index, 'nav'] = mock_nav.loc[index, asset_list+['exception']].sum()
        # 交易或者再平衡的判断和计算
        if trade_record_mode:
            today_trade_record = trade_record[(trade_record.index > row['date_shift1']) & (trade_record.index <= index)]
            if len(today_trade_record):
                today_trade_record = today_trade_record[today_trade_record.index == today_trade_record.index.max()]
                if single_asset:
                    for asset_col in asset_list:
                        mock_nav.loc[index, asset_col] = max(mock_nav.loc[index, asset_col] + mock_nav.loc[index, 'nav'] * today_trade_record.iloc[0][asset_col], 0)  # 不允许出现负仓位,允许有杠杆(为了准确反映仓位增减的值)
                    mock_nav.loc[index, 'exception'] = mock_nav.loc[index, 'nav'] - mock_nav.loc[index, asset_list].sum()
                else:
                    for asset_col in list(set(asset_list) - {'绝对收益'}):
                        mock_nav.loc[index, asset_col] = max(mock_nav.loc[index, asset_col] + mock_nav.loc[index, 'nav'] * today_trade_record.iloc[0][asset_col], 0)  # 不允许出现负仓位,允许有杠杆(为了准确反映仓位增减的值)
                    mock_nav.loc[index, '绝对收益'] = mock_nav.loc[index, 'nav'] - mock_nav.loc[index, list(set(asset_list) - {'绝对收益'})].sum()
        else:
            today_target_position = target_position[(target_position.index > row['date_shift1']) & (target_position.index <= index)]
            if len(today_target_position):
                # 本期需进行再平衡
                today_target_position = today_target_position[today_target_position.index == today_target_position.index.max()]
                for asset_col in asset_list:
                    mock_nav.loc[index, asset_col] = mock_nav.loc[index, 'nav'] * today_target_position.iloc[0][asset_col]
                if single_asset:
                    mock_nav.loc[index, 'exception'] = mock_nav.loc[index, 'nav'] - mock_nav.loc[index, asset_list].sum()

    # 返回净值表（包括各类资产情况明细和模拟组合的收益率）
    mock_nav['return'] = mock_nav['nav'].pct_change()
    mock_nav.reset_index(inplace=True)
    return mock_nav

# ----------------------------------------------------------------
# FOF组合相对投委会基准的择时分析 - 模拟组合回测的私有函数
# 输入：1.目标仓位，时序数据，index是date，认为当期盘后调整为新仓位权重()；2.各资产收益表，默认index(date数据)是顺序的，已按照所需频率维护完善的，将直接按照此表日历进行遍历
# 以上两个输入列名一致，所输入的目标仓位会根据资产收益表的频率及区间实现自适应
# 输出：模拟组合回测所得的净值曲线数据以及组合收益率数据
# ----------------------------------------------------------------
def _position_timing_mock_perf_stats(
    port_mock_ret,
    bm_mock_ret,
    periods=['YTD', 'SI', '2024', '2023', '2022'],
    start_date=None
):
    assert set(periods) <= {'YTD', 'Recent_1M', 'Recent_3M', '2024', '2023', '2022', '2021', '2020', '2019', 'SI', 'Customized'}, \
        "统计区间，只能属于YTD, Recent_1M, Recent_3M, '2024', '2023', 2022, 2021, 2020, 2019, Customized以及SI（均为字符串格式）"
    if port_mock_ret.empty or bm_mock_ret.empty:
        return pd.DataFrame()
    port_mock_ret = port_mock_ret.set_index(['date'])[1:]  # 对于模拟回测的数据 首日的收益率一定是nan，为了不影响最大回撤等地方的计算，去除第一个起始点的数据
    bm_mock_ret = bm_mock_ret.set_index(['date']).rename(columns={'return': 'bm_return'})[1:]

    result = []
    for period in periods:
        start_date, end_date = calendar.calender_getStartEndDate(period, port_mock_ret.index.max(), start_date)
        period_port_mock_ret = port_mock_ret[(port_mock_ret.index >= start_date) & (port_mock_ret.index <= end_date)]
        period_bm_mock_ret = bm_mock_ret[(bm_mock_ret.index >= start_date) & (bm_mock_ret.index <= end_date)]
        if len(period_port_mock_ret) == 0 or len(period_bm_mock_ret) == 0:
            continue
        period_result = dict()
        period_result[port_mock_ret['id'].iloc[0]] = cal.basicCal_calPerformanceStats(period_port_mock_ret['return'], 'D')
        period_result[bm_mock_ret['id'].iloc[0]] = cal.basicCal_calPerformanceStats(period_bm_mock_ret['bm_return'], 'D')
        period_result['择时效果'] = cal.basicCal_calPerformanceStats(period_port_mock_ret['return'], 'D', period_bm_mock_ret['bm_return'])
        period_result = pd.DataFrame.from_dict(period_result).T.reset_index().rename(columns={'index': 'mock_name'})
        period_result['period'] = period
        period_result['freq'] = 'D'
        if len(period_result) != 0:
            result.append(period_result)
    if not result:
        return pd.DataFrame()
    result = pd.concat(result)
    result = result.reset_index()

    return result

####################################################################
# WRITE API
####################################################################

# ------------------------------------------------------
# 更新全部私享臻选账户日度绩效指标到缓存数据库
# ------------------------------------------------------
def anlsFOF_calAndCacheFOFPerfStats(
    date,
    period='YTD',           # 需要缓存的有YTD, 2022, 2021, 2020, 对于'Customized'不缓存
    cache_start_date=None,  # 该参数对非Customzied区间有效，是一次性缓存一个区间内，每一个date对period的stats
    portfolio_ids=None,     # 只有当period为Customized的时候，该参数不为None
    start_date=None,        # 该参数只对period为Customized有效，是customized区间的stats的那个start date
    stats=['period_return', 'annualized_period_return', 'annualized_volatility', 'max_drawdown', 'sharpe_ratio', 'calmar', 'current_drawdown'],
                            # 对于cache函数，stats默认值选择为目前的全量stats，请注意：数据库结构修改后再修改该默认参数
    insert=False,
):
    assert period in ['YTD', 'Today', '2024', '2023', '2022', '2021', '2020', 'Customized'], "统计区间暂时不支持"
    assert set(stats) <= {'period_return', 'annualized_period_return', 'annualized_volatility', 'max_drawdown', 'sharpe_ratio', 'calmar', 'current_drawdown'}, \
            "stats选项目前支持'period_return','annualized_period_return','annualized_volatility','max_drawdown','sharpe_ratio','calmar','current_drawdown'"
    all_accounts = custFOF.custFOF_getFOFReferenceData()

    if period == 'Customized':
        assert start_date != None, 'Customized情况下，start date不能为空'
    if period in ['Today', 'Customized']:
        assert insert == False, 'Today或者Customized数据不要存入缓存库'
        all_accounts = all_accounts[all_accounts['portfolio_id'].isin(portfolio_ids)]
    if period in ['YTD', '2024', '2023', '2022', '2021', '2020']:
        assert portfolio_ids == None, '对于非Customized，不需要这个参数'
        assert start_date == None, '对于非Customized, 不需要这个参数'
    if period == '2020':
        assert date == datetime.date(2021,1,1), 'date日期请输入%s' % datetime.date(2021,1,1)
        tradingCalendar = [datetime.date(2021,1,1)]
    if period == '2021':
        assert date == datetime.date(2022,1,1), 'date日期请输入%s' % datetime.date(2022,1,1)
        tradingCalendar = [datetime.date(2022, 1, 1)]
    if period == '2022':
        assert date == datetime.date(2023,1,1), 'date日期请输入%s' % datetime.date(2023,1,1)
        tradingCalendar = [datetime.date(2023, 1, 1)]
    if period == '2023':
        assert date == datetime.date(2024,1,1), 'date日期请输入%s' % datetime.date(2024,1,1)
        tradingCalendar = [datetime.date(2024, 1, 1)]
    if period == '2024':
        assert date == datetime.date(2025,1,1), 'date日期请输入%s' % datetime.date(2025,1,1)
        tradingCalendar = [datetime.date(2025, 1, 1)]
    # if period == 'YTLDLM':
    #     assert date == datetime.date(date.year, date.month, 1), 'date日期请输入%s' % datetime.date(date.year, date.month, 1)
    #     assert date.month != 1, '1月无YTLDLM数据'
    #     tradingCalendar = [datetime.date(date.year, date.month, 1)]
    if period == 'YTD':
        assert cache_start_date is not None, "请输入cache_start_date缓存区间起始日期"
        tradingCalendar = wind.wind_getSSECalendar()
        tradingCalendar.index = tradingCalendar['date']
        tradingCalendar = tradingCalendar[cache_start_date:date]
        tradingCalendar = tradingCalendar['date']

    if period in ['YTD', '2024', '2023', '2022', '2021', '2020']:
        account_perf = pd.concat([anlsFOF_calFOFPerfStats(date=date, portfolio_ids=all_accounts.portfolio_id.tolist(),
                                                      period=period, freq='D', stats=stats) for date in tradingCalendar], axis=0)
    elif period in [ 'Customized', 'Today']:
        account_perf = anlsFOF_calFOFPerfStats(date=date, portfolio_ids=all_accounts.portfolio_id.tolist(), period=period, freq='D', start_date=start_date,
                                               stats=stats)

    account_perf = account_perf.replace(np.nan, -9999)
    account_perf['period'] = period
    if period in ['2020', '2021', '2022', '2023', '2024']:
        account_perf['end_date'] = date
    account_perf.rename(columns={'end_date': 'dt'}, inplace=True)

    # 缓存任务在遇到假期时，可能会出现重复日期的数据（FOF账户在最新交易日的数据还未落导致），需进行去重
    account_perf = account_perf.drop_duplicates(['dt', 'portfolio_id'])

    account_perf = pd.merge(account_perf, all_accounts[['portfolio_name', 'portfolio_id']], on='portfolio_id')
    if period == 'Today':
        stats = ['period_return']

    account_perf = account_perf.loc[:, ['dt', 'portfolio_id', 'portfolio_name', 'period'] + stats]
    if insert:
        # amdata数据库
        # Delete existing key if exists
        conn = amdata.amdata_connectAmdataDb()
        sql = "DELETE FROM AMFOF.SRC_FOF_PORTFOLIO_STATS WHERE DT in ({0}) and PERIOD = '{1}'"
        sql = sql.format(','.join(["DATE'%s'" % x.strftime('%Y-%m-%d') for x in account_perf['dt'].unique()]), period)
        cur = conn.cursor()
        cur.execute(sql)
        conn.commit()

        # Write into database
        amdata.amdata_insertAMData(account_perf, 'AMFOF.SRC_FOF_PORTFOLIO_STATS')

        # IRM数据库
        # Delete existing key if exists
        conn = irm.irm_connectIRMDB()
        sql = "DELETE FROM irm.AMFOF_SRC_FOF_PORTFOLIO_STATS WHERE DT in ({0}) and PERIOD = '{1}'"
        sql = sql.format(','.join(["DATE'%s'" % x.strftime('%Y-%m-%d') for x in account_perf['dt'].unique()]), period)
        cur = conn.cursor()
        cur.execute(sql)
        conn.commit()

        # Write into database
        irm.irm_insertIRMData(account_perf, 'irm.AMFOF_SRC_FOF_PORTFOLIO_STATS')
    return account_perf

# ------------------------------------------------------
# 获取持仓产品列表，范围为：T-1和T-8之间持仓数据的并集
# ------------------------------------------------------
def anlsFOF_holdingProductList(
    date,   # 获取持仓日期
    insert=False  # 是否写入数据库，默认不写入
):
    # 输入交易日为T，获取T-1,T-8的日期
    wind_calender = wind.wind_getSSECalendar()
    wind_calender_history = wind_calender.loc[(wind_calender['date'] < date), 'date']
    start_date = wind_calender_history.iloc[-8]
    end_date = wind_calender_history.iloc[-1]
    holding_data = custFOF.custFOF_getFOFHoldingData(start_date, end_date)
    holding_product = holding_data[['product_id', 'product_name']].drop_duplicates()
    holding_product['date'] = date

    if insert:
        # 如果重复日期数据
        conn = irm.irm_connectIRMDB()
        sql = "DELETE FROM irm.AMFOF_HOLDING_PRODUCT_LIST WHERE date = DATE'{0}'"
        sql = sql.format(date.strftime('%Y-%m-%d'))
        cur = conn.cursor()
        cur.execute(sql)
        conn.commit()
        # 写入数据库
        irm.irm_insertIRMData(holding_product, 'irm.AMFOF_HOLDING_PRODUCT_LIST')
    return holding_product

# ------------------------------------------------------
# 缓存策略层级最新持有规模信息，数据来源取T至T-45各账户最新持仓数据
# ------------------------------------------------------
def anlsFOF_cacheCurrentStrategyHoldingInfo(
    date,   # 获取持仓日期
    insert=False  # 默认不写入
):
    res = anlsFOF_getCurrentHoldingInfo(date=date, data_level='Strategy')[['strategy_id', 'strategy_name', 'total_NAV', 'latest_holding_date', 'date']]  # 数据库中不写入标签信息
    res.rename(columns={'date': 'update_date', 'total_NAV': 'strategy_NAV_scaled'}, inplace=True)
    res['strategy_NAV_scaled'] = res['strategy_NAV_scaled'].apply(lambda x: "{:.2f}".format(x/1e4))  # 以万为单位 保留2位小数
    if insert:
        # 如果重复日期数据
        conn = irm.irm_connectIRMDB()
        sql = "DELETE FROM irm.AMFOF_CURRENT_HOLDING_STRATEGY_INFO WHERE update_date = DATE'{0}'"
        sql = sql.format(date.strftime('%Y-%m-%d'))
        cur = conn.cursor()
        cur.execute(sql)
        conn.commit()
        # 写入数据库
        irm.irm_insertIRMData(res, 'irm.AMFOF_CURRENT_HOLDING_STRATEGY_INFO')
    return res

# ------------------------------------------------------
# 私享慧享账户、安享账户，按照PM维度分别统计管理账户的红黄绿灯情况汇总
# ------------------------------------------------------
def anlsFOF_accountFlagSummary(
        date,   # 统计日期
        account_type='sixiang_huixiang' # 账户类型，私享慧享，安享账户
):
    assert account_type in ('sixiang_huixiang', 'anxiang'), '分类为私享慧享账户，安享账户'

    flag_info = anlsFOF_platformOverview(date, 'YTD', portfolio_types=None, sector_type='allocation_type', pm_name=None,
                                           start_date=None, summary_mode=False, include_flag=True, stats=['period_return'])
    if account_type == 'sixiang_huixiang':
        sx_account = custFOF.custFOF_getSXAccountList(date, account_type=config.specific_FOF_product_line['sixiang+huixiang'])
        sx_account = sx_account[sx_account['pm_name'].isin(const.const.SIXIANG_PM_LIST)]
        result = sx_account.merge(flag_info[['portfolio_id', 'YTD_flag', 'SI_flag']], on=['portfolio_id'], how='left')
        flag_count = result.groupby(['pm_name', 'YTD_flag'], as_index=False).agg({'portfolio_id': 'count'})
        flag_count = flag_count.pivot_table(index='pm_name', columns='YTD_flag', values='portfolio_id', fill_value=0)
        flag_weight = pd.DataFrame(0, index=flag_count.index, columns=['账户数', '绿', '黄', '红'])
        flag_weight['账户数'] = flag_count.sum(axis=1)
        flag_weight.loc[:, flag_count.columns] = flag_count.div(flag_weight['账户数'], axis=0)
        result = flag_weight.reset_index()
    else:
        sx_account = custFOF.custFOF_getSXAccountList(date, account_type=config.specific_FOF_product_line['anxiang'])
        sx_account = sx_account[sx_account['pm_name'].isin(const.const.SIXIANG_PM_LIST + ['张泂'])]
        result = sx_account.merge(flag_info[['portfolio_id', 'YTD_flag', 'SI_flag']], on=['portfolio_id'], how='left')
        flag_count = result.groupby(['YTD_flag'], as_index=False).agg({'portfolio_id': 'count'})
        flag_count = flag_count.pivot_table(columns='YTD_flag', values='portfolio_id', fill_value=0)
        flag_weight = pd.DataFrame(0, index=flag_count.index, columns=['账户数', '绿', '黄', '红'])
        flag_weight['账户数'] = flag_count.sum(axis=1)
        flag_weight.loc[:, flag_count.columns] = flag_count.div(flag_weight['账户数'], axis=0)
        result = flag_weight.reset_index(drop=True)
    result = result.sort_values(by='账户数', ascending=False)
    return result

# ------------------------------------------------------
# 某单一产品对于账户贡献的损益汇总
# ------------------------------------------------------
def anlsFOF_getFOFProductAttributionSummary(
    ids,                        # id 列表
    start_date,                 # 开始日期
    end_date,                   # 结束日期
    data_level='Strategy',      # 数据层级，策略层面/产品层面
    fund_type='HF',             # 基金类型，'HF'/'MF'
    benchmark=None              # 基准代码
):
    assert fund_type in ('HF', 'MF'), "fund_type需为'HF'或'MF'"
    assert benchmark in list(const.const.WEB_BENCHMARK_LIST.values()) + list(config.mf_mock_port_industry_benchmark_pool_map.values()), \
        "benchmark仅支持const.WEB_BENCHMARK_LIST和公募模拟组合基准库中的基准"
    if fund_type == 'HF':
        assert data_level in ('Strategy', 'Product'), "私募数据只支持策略和产品层面"
        product_info = custHF.custHF_getProductInfo()
    else:
        assert data_level == 'Product', "公募数据暂仅支持产品层面"
        product_info = custMF.custMF_getMFProductInfo()

    if data_level == 'Strategy':
        product_info = product_info[product_info['strategy_id'].isin(ids)]
        product_ids = product_info['product_id'].to_list()
    else:
        product_info = product_info[product_info['product_id'].isin(ids)]
        product_ids = ids  # 因公募存在多个份额的情况，产品信息可能未全量覆盖，保留原始传入的ids，防止因产品信息未维护导致的缺漏
    data_all = custFOF.custFOF_getFOFCachedHoldingValuationSheet(start_date - datetime.timedelta(14), end_date, product_id=product_ids)
    data = data_all[data_all['date'] >= start_date]
    df_result = data.groupby(['portfolio_id', 'product_id'], as_index=False).agg({'portfolio_name': 'first', 'product_daily_nav_change': 'sum', 'product_name': 'first', 'VAL': ['first', 'last'], 'date': ['first', 'last']})
    name_dict = {('portfolio_id', ''): 'portfolio_id', ('product_id', ''): 'product_id', ('portfolio_name', 'first'): 'portfolio_name',
                 ('product_daily_nav_change', 'sum'): 'profit_sum', ('product_name', 'first'): 'product_name', ('VAL', 'first'): 'val_start',
                 ('VAL', 'last'): 'val_end', ('date', 'first'): 'date_start', ('date', 'last'): 'date_end'}
    df_result.columns = df_result.columns.to_flat_index()
    df_result.rename(columns=name_dict, inplace=True)

    history_trades = anlsFOF_getTradeHistoricalFlow(start_date, end_date, product_ids=product_ids)
    trade_sum = history_trades.groupby(['portfolio_id', 'trade_type', 'product_id'], as_index=False).agg({'product_name': 'first', 'trade_volume': 'sum', 'trade_amount': 'sum'})
    df_result = df_result.merge(trade_sum.loc[trade_sum['trade_type'] == '买入', ['product_id', 'portfolio_id', 'trade_volume', 'trade_amount']],
                  on=['portfolio_id', 'product_id'], how='outer')
    df_result.rename(columns={'trade_volume': 'buy_vol', 'trade_amount': 'buy_val'}, inplace=True)
    df_result = df_result.merge(trade_sum.loc[trade_sum['trade_type'] == '卖出', ['product_id', 'portfolio_id', 'trade_volume', 'trade_amount']],
                  on=['portfolio_id', 'product_id'], how='outer')
    data_details = df_result.rename(columns={'trade_volume': 'sell_vol', 'trade_amount': 'sell_val'})
    data_details = data_details.merge(product_info[['product_id', 'strategy_id', 'strategy_name']], on='product_id', how='left')
    data_details.loc[data_details['date_start'] > start_date, 'val_start'] = 0
    data_details.loc[data_details['date_end'] < end_date, 'val_end'] = 0
    group_level = ['strategy_id', 'strategy_name'] if data_level == 'Strategy' else ['product_id', 'product_name']
    result_data = data_details.groupby(group_level, as_index=False).agg({'profit_sum': 'sum',
        'val_start': 'sum', 'val_end': 'sum', 'buy_vol': 'sum', 'buy_val': 'sum', 'sell_vol': 'sum', 'sell_val': 'sum'})
    if result_data.empty:
        result_data['benchmark_profit'] = None
    else:
        if benchmark is not None:
            data_all = pd.merge(data_all, product_info[['product_id', 'strategy_id', 'strategy_name']], on='product_id', how='left')
            daily_holding_val = data_all.groupby(group_level + ['date'], as_index=False)['product_NAV'].sum()
            daily_holding_val['product_NAV_shift_1'] = daily_holding_val.groupby(group_level, as_index=False)['product_NAV'].shift(1)
            daily_holding_val = daily_holding_val[daily_holding_val['date'] >= start_date]
            if benchmark in config.mf_mock_port_industry_benchmark_pool_map.values():  # 取基准库组合的收益作为基准
                benchmark_ret = custMF.custMF_getMockPortNetValueAndReturn(start_date=start_date - datetime.timedelta(days=14), end_date=end_date + datetime.timedelta(days=14), mock_port_ids=[benchmark], freq='D')
                benchmark_ret = pd.pivot_table(benchmark_ret, values='return', index='date', columns='portfolio_id').reset_index()
            else:
                benchmark_ret = wd.wind_getIndexReturn(benchmark, start_date - datetime.timedelta(days=14), end_date + datetime.timedelta(days=14), freq='D').reset_index()
            df = pd.merge(benchmark_ret, daily_holding_val, on='date', how='inner')
            df['benchmark_profit'] = df[benchmark] * df['product_NAV_shift_1']
            result_data = pd.merge(result_data, df.groupby(group_level, as_index=False).agg({'benchmark_profit': 'sum'}), on=group_level, how='left')
        else:
            result_data['benchmark_profit'] = 0
    result_data['excess_profit'] = result_data['profit_sum'] - result_data['benchmark_profit']
    return data_details, result_data

# ------------------------------------------------------
# 缓存全量anlsFOF_restoreFOFHoldingValuationSheet函数的运行结果，内容为调整后的持仓数据
# regular_update True情况下，返回插入数据以及错误信息，因数据量较大建议开始日期与结束日期间间隔不超过一年
# regular_update False情况下因数据量过大不返回插入数据，返回空列表以及错误信息
# ------------------------------------------------------
def anlsFOF_cacheFOFHoldingValuationSheet(
    start_date,     # 开始日期
    end_date,       # 截止日期
    regular_update=True,  # 更新模式，True会缓存更新区间的数据，False为全部更新模式，全量缓存每个账户成立以来到截止时间的数据，开始日期变量不生效
    insert=False  # 是否插入数据库
):
    data_start_date = start_date -datetime.timedelta(days=14)
    portfolio_data = custFOF.custFOF_getFOFReferenceData(include_portfolio_oa_id=True, include_all_portfolio_status=True)
    data_result = []
    error_dict = {}
    rename_dict = {'T-1_NAV': 'preday_nav', 'T-1_total_share': 'preday_total_share', 'product_weight': 'product_weight_to_nav',
                   'total_product_weight': 'product_weight_to_total_nav', 'product_daily_ret': 'product_daily_nav_change',
                   'product_daily_float_ret': 'product_daily_float_nav_change',
                   'product_daily_realized_ret': 'product_daily_realized_nav_change'}
    def _insert_to_database(start_date, end_date, data, id=None):
        # 如果重复日期数据
        conn = irm.irm_connectIRMDB()
        if id is None:
            sql = "DELETE FROM irm.fof_holding_valuation_sheet_adjusted WHERE date >= DATE'{0}' and date <= DATE'{1}'"
            sql = sql.format(start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
        else:
            sql = "DELETE FROM irm.fof_holding_valuation_sheet_adjusted WHERE date >= DATE'{0}' and date <= DATE'{1}' and portfolio_id = '{2}'"
            sql = sql.format(inception_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'), id)
        cur = conn.cursor()
        cur.execute(sql)
        conn.commit()
        # 写入数据库
        irm.irm_insertIRMData(data, 'irm.fof_holding_valuation_sheet_adjusted')
    if regular_update:
        for index, row in tqdm(portfolio_data.iterrows()):
            id = row['portfolio_id']
            print(id + row['portfolio_name']+'-'+row['portfolio_status'])
            try:
                port_data = anlsFOF_restoreFOFHoldingValuationSheet(data_start_date, end_date, portfolio_id=id)
                port_data = port_data.loc[port_data['date'] >= start_date, ]
                port_data = port_data.loc[port_data['total_share'] >0, ]
                port_data.rename(columns=rename_dict, inplace=True)
                # 已清算、正在清算账户最后一天可能导致收益率计算出现nan、无穷值，对已清算、清算中账户单独判断
                if row['portfolio_status'] in ['已清算', '清算中'] and not port_data.empty:
                    # 取到数据的最大日期小于区间截止日期，去掉受清算影响的最后一日数据
                    if port_data['date'].max()<end_date:
                        port_data=port_data[port_data['date']<port_data['date'].max()]
                    # 取到数据的最大日期不小于区间截止日期，进一步判断最后一日是否包含nan、无穷等异常值，如包含去掉最后一日
                    elif port_data[port_data['date']==end_date].isin([np.nan, np.inf, -np.inf]).any(axis=1).sum()>0:
                        port_data=port_data[port_data['date']<port_data['date'].max()]
                if not port_data.empty:
                    # 防止T-1 数据出现nan,仅对最小日期进行fillna(0)
                    port_data.loc[port_data['date'] == port_data['date'].min(), :] = \
                        port_data.loc[port_data['date'] == port_data['date'].min(), :].fillna(0)
                    data_result.append(port_data)
            except Exception as error:
                exception_info = traceback.format_exc()
                error_dict[id] = [row, exception_info]
                print(error_dict[id])
        data_result = pd.concat(data_result, axis=0)
        if insert:
            _insert_to_database(start_date, end_date, data_result)
    else:
        for index, row in tqdm(portfolio_data.iterrows()):
            id = row['portfolio_id']
            inception_date = row['inception_date']
            print(id + row['portfolio_name']+'-'+row['portfolio_status'])
            try:
                port_data = anlsFOF_restoreFOFHoldingValuationSheet(inception_date, end_date, portfolio_id=id)
                port_data.rename(columns=rename_dict, inplace=True)
                port_data = port_data.loc[port_data['total_share'] >0, ]
                # 已清算、正在清算账户最后一天可能导致收益率计算出现nan、无穷值，对已清算、清算中账户单独判断
                if row['portfolio_status'] in ['已清算', '清算中'] and not port_data.empty:
                    # 取到数据的最大日期小于区间截止日期，去掉受清算影响的最后一日数据
                    if port_data['date'].max()<end_date:
                        port_data=port_data[port_data['date']<port_data['date'].max()]
                    # 取到数据的最大日期不小于区间截止日期，进一步判断最后一日是否包含nan、无穷等异常值，如包含去掉最后一日
                    elif port_data[port_data['date']==end_date].isin([np.nan, np.inf, -np.inf]).any(axis=1).sum()>0:
                        port_data=port_data[port_data['date']<port_data['date'].max()]
                if not port_data.empty and insert:
                    # 防止T-1 数据出现nan,仅对最小日期进行fillna(0)
                    port_data.loc[port_data['date'] == port_data['date'].min(), :] = \
                        port_data.loc[port_data['date'] == port_data['date'].min(), :].fillna(0)
                    _insert_to_database(inception_date, end_date, port_data, id=id)
            except Exception as error:
                exception_info = traceback.format_exc()
                error_dict[id] = [row, exception_info]
                print(error_dict[id])
    return data_result, error_dict

# --------------------------------------------------------------------------------------
# 录入交易试算指令列表
# 覆盖机制，同一账户的指令会不断被覆盖，这与前端交互组件的逻辑有关，始终用前端得到的df去覆盖
# --------------------------------------------------------------------------------------
def anlsFOF_cacheTrialTradeOrder(
    portfolio_id,
    trial_order_data,  # DataFrame格式的试算指令作为输入，需传入整理好的英文表头
    del_start_date=None,  # 当用户在前端对df开始修改, 必须指明需对应删除的数据区间，保证缓存数据为用户所需
    del_end_date=None,  # 当用户在前端对df开始修改, 必须指明需对应删除的数据区间，保证缓存数据为用户所需
    insert=False,  # 数据库插入的函数，默认不进行插入
):
    portfolio_ids = [portfolio_id]
    if insert:
        # 按照账户覆盖式写入
        conn = irm.irm_connectIRMDB()
        cur = conn.cursor()
        if del_start_date and del_end_date:
            sql = "DELETE FROM irm.amfof_trade_order_precalculation WHERE portfolio_id in ({0}) and trade_date >= DATE'{1}' and trade_date <= DATE'{2}'"
            cur.execute(sql.format(','.join(["'%s'" % x for x in portfolio_ids]), del_start_date, del_end_date))
            conn.commit()
        if not trial_order_data.empty:
            # 写入数据库
            irm.irm_insertIRMData(trial_order_data, 'irm.amfof_trade_order_precalculation')

    return trial_order_data


# --------------------------------------------------------------------------------------
# 整理并检查需录入的交易试算指令列表
# 覆盖机制，同一账户的指令会不断被覆盖，这与前端交互组件的逻辑有关，始终用前端得到的df去覆盖
# --------------------------------------------------------------------------------------
def anlsFOF_checkAndCacheTrialTradeOrder(
    portfolio_id,
    portfolio_name,
    trial_order_data,       # DataFrame格式的试算指令作为输入，需传入整理好的英文表头
    del_start_date=None,    # 当用户在前端对df开始修改, 必须指明需对应删除的数据区间，保证缓存数据为用户所需
    del_end_date=None,      # 当用户在前端对df开始修改, 必须指明需对应删除的数据区间，保证缓存数据为用户所需
    insert=False,           # 数据库插入的函数，默认不进行插入
):
    assert len(trial_order_data[trial_order_data['trade_date'].isna()]) == 0, "缓存试算交易数据时需完整录入各条指令的交易日期"
    trial_order_data['trade_date'] = pd.to_datetime(trial_order_data['trade_date']).dt.date
    trial_order_data['trade_amount'] = trial_order_data['trade_amount'].apply(lambda x: float(str(x).replace(',', '')) if x is not None else x)
    trial_order_data['trade_volume'] = trial_order_data['trade_volume'].apply(lambda x: float(str(x).replace(',', '')) if x is not None else x)
    hf_product_info = custHF.custHF_getProductInfo(include_filing_product=True)
    trial_order_data = trial_order_data[['trade_date', 'product_name', 'trade_type', 'trade_amount', 'trade_volume', 'redemption_interval']]
    trial_order_data = pd.merge(trial_order_data, hf_product_info[['product_short_name', 'product_id']], left_on='product_name', right_on='product_short_name', how='left')
    del trial_order_data['product_short_name']
    holding_data = custFOF.custFOF_getFOFHoldingData(datetime.date.today()-datetime.timedelta(10), datetime.date.today(), [portfolio_id])
    holding_data = holding_data[holding_data['date'] == holding_data['date'].max()]
    redemption_trial_order_data = trial_order_data[trial_order_data['trade_type'].str.contains('赎回')]
    assert len(holding_data[holding_data['product_id'].isin(redemption_trial_order_data['product_id'].tolist())]) == len(redemption_trial_order_data[['product_id']].drop_duplicates()), "赎回产品并不在目前持仓中"
    trial_order_data['trade_amount'] = trial_order_data.apply(lambda x: holding_data[holding_data['product_id'] == x['product_id']]['product_NAV'].iloc[0] if x['trade_type'] == '全部赎回' else x['trade_amount'], axis=1)
    trial_order_data['trade_volume'] = trial_order_data.apply(lambda x: holding_data[holding_data['product_id'] == x['product_id']]['product_volume'].iloc[0] if x['trade_type'] == '全部赎回' else x['trade_volume'], axis=1)
    trial_order_data['portfolio_id'] = portfolio_id
    trial_order_data['portfolio_name'] = portfolio_name
    trial_order_data['update_time'] = datetime.datetime.now()
    trial_order_data['update_person'] = str(st.experimental_user['email'])
    # nan无法存入数据库，存数前进行处理
    trial_order_data = trial_order_data.fillna(value='None')
    anlsFOF_cacheTrialTradeOrder(portfolio_id, trial_order_data, del_start_date, del_end_date, insert=insert)

    return trial_order_data

# -------------------------------------------------------------------------------------------
# 单一账户的交易试算指令下载接口
# 能够按照CAMP导入模板生成EXCEL方便导入
# -------------------------------------------------------------------------------------------
def anlsFOF_checkAndDownloadTrialTradeOrder(
    portfolio_id,
    portfolio_name,
    trial_order_data,  # DataFrame格式的试算指令作为输入，需传入整理好的英文表头
):
    assert len(trial_order_data), "未录入有效的试算指令，故暂不提供试算指令下载"
    assert len(trial_order_data[trial_order_data['trade_date'].isna()]) == 0, "缓存试算交易数据时需完整录入各条指令的交易日期"

    trial_order_data['trade_date'] = pd.to_datetime(trial_order_data['trade_date']).dt.date
    trial_order_data['trade_amount'] = trial_order_data['trade_amount'].apply(lambda x: float(str(x).replace(',', '')) if x is not None else x)
    trial_order_data['trade_volume'] = trial_order_data['trade_volume'].apply(lambda x: float(str(x).replace(',', '')) if x is not None else x)

    scheduled_trade = custFOF.custFOF_getTradeFutureFlow(datetime.date.today(), trial_order_data['trade_date'].max(), portfolio_ids=[portfolio_id])
    scheduled_trade = scheduled_trade[scheduled_trade['trade_volume'] < 1e9]  # 筛去作为占位使用的交易指令
    # 由于会存在先录入trial_trade后，又实际在camp进行预约交易的情况，上述两组数可能会有重复的条目，目前认为产品+日期+金额完全一致的就是重复项，会剔除重复
    for index, row in scheduled_trade.iterrows():
        trial_order_data = trial_order_data[~((trial_order_data['product_id'] == row['product_id']) & (trial_order_data['trade_date'] == row['trade_execute_date']) & ((trial_order_data['trade_amount'] == row['trade_volume']) | (trial_order_data['trade_volume'] == row['trade_volume'])))]  # 注意科目上的对齐
        # 对于全部赎回的指令,再进行一次判断,因为金证所计算的全部赎回份额可以实时考虑当日是否有分红(报酬),可能会导致金证(CAMP)指令的赎回份额与持仓份额不一致
        trial_order_data = trial_order_data[~((trial_order_data['product_id'] == row['product_id']) & (trial_order_data['trade_date'] == row['trade_execute_date']) & (trial_order_data['trade_type'] == '全部赎回') & (row['trade_type'] == '全部赎回'))]  # 注意科目上的对齐

    # FIXME 当前已存在同一产品具有两种可投份额的情况，目前全量展示在模板里并在网页端提示需要手动检查
    camp_product_id_mapping = custHF.custHF_getProductCAMPIDWithShareType()
    trial_order_data = pd.merge(trial_order_data, camp_product_id_mapping, on='product_id', how='left')
    duplicated_camp_product = camp_product_id_mapping[camp_product_id_mapping['product_id'].duplicated(keep=False)]
    if len(duplicated_camp_product) and len(trial_order_data[trial_order_data['product_id'].isin(duplicated_camp_product['product_id'].tolist())]):
        warning_trial_order_data = trial_order_data[trial_order_data['product_id'].isin(duplicated_camp_product['product_id'].tolist())]
        warning_trial_order_data = warning_trial_order_data[['product_id', 'product_name']].drop_duplicates()
        waring_strings = ' \n'.join(warning_trial_order_data.apply(lambda row: ''.join(row.astype(str)), axis=1))
        st.warning(':warning: 请注意！以下产品存在多种份额可投, 请在Excel文件中具体选择份额： \r\n' + waring_strings)

    trial_order_data['交易日'] = trial_order_data['trade_date']
    trial_order_data['产品名称'] = portfolio_id
    trial_order_data['辅助列-1'] = portfolio_name
    trial_order_data['基金名称'] = trial_order_data['product_id'] if trial_order_data.empty else trial_order_data.apply(lambda x: x['product_id'] if pd.isna(x['product_camp_id_with_share_type']) else x['product_camp_id_with_share_type'], axis=1)
    trial_order_data['辅助列-2'] = trial_order_data['product_name']
    trial_order_data['转入基金名称'] = ''
    trial_order_data['交易类型'] = trial_order_data['trade_type'].apply(lambda x: '赎回' if '赎回' in x else x)
    trial_order_data['需求金额/数量'] = trial_order_data.apply(lambda x: '全部份额' if str(x['trade_type']) == '全部赎回' else (x['trade_volume'] if '赎回' in str(x['trade_type']) else x['trade_amount']), axis=1) if not trial_order_data.empty else None
    trial_order_data[['渠道', '分红方式/巨额赎回', '备注']] = ''
    camp_template_result = trial_order_data.copy(deep=True)
    camp_template_result = camp_template_result[['交易日', '产品名称', '辅助列-1', '基金名称', '辅助列-2', '转入基金名称', '交易类型', '需求金额/数量', '渠道', '分红方式/巨额赎回', '备注']]
    camp_template_result = camp_template_result.set_index('交易日')

    return camp_template_result

# -------------------------------------------------------------------------------------------
# 获取用户交易试算指令录入情况
# 基于账户一级的信息进行展示，方便用户进行选择，导出所需的试算指令
# 下载选项的默认项是今天录入的所有指令
# -------------------------------------------------------------------------------------------
def anlsFOF_getTrialTradeOrderPortInfo(
    pm_email    # 用户邮箱，识别用户的唯一标识
):
    current_trial_order = custFOF.custFOF_getTrialTradeOrder(datetime.date.today(), datetime.date(2099, 12, 31))
    current_trial_order = current_trial_order[current_trial_order['update_person'] == pm_email]
    current_trial_order = current_trial_order[current_trial_order['update_time'] > datetime.datetime.now() - datetime.timedelta(days=2)]
    current_trial_order.sort_values('update_time', inplace=True)
    current_trial_order_port_info = current_trial_order.groupby(['portfolio_id', 'portfolio_name'], as_index=False)['update_time'].last()
    today_midnight = datetime.datetime(datetime.datetime.now().year, datetime.datetime.now().month, datetime.datetime.now().day)
    current_trial_order_port_info.sort_values('update_time', ascending=False, inplace=True)
    current_trial_order_port_info = current_trial_order_port_info.reset_index(drop=True)
    current_trial_order_port_info['是否下载'] = current_trial_order_port_info['update_time'] >= today_midnight
    current_trial_order_port_info.rename(columns={'portfolio_id': '账户ID', 'portfolio_name': '账户名', 'update_time': '最后编辑时间'}, inplace=True)
    return current_trial_order_port_info

# -------------------------------------------------------------------------------------------
# 交易试算指令批量下载接口
# 能够按照CAMP导入模板生成一个EXCEL，更加方便地导入
# -------------------------------------------------------------------------------------------
def anlsFOF_batchDownloadTrialTradeOrder(
    portfolio_ids   # 账户列表，传入list
):
    wind_calendar = wind.wind_getSSECalendar()
    # 当天录入的指令也会下载，所以需要包含当日数据；CAMP支持筛去重复指令，所以不会对曾经录入的在今天执行的交易造成影响
    base_date = wind_calendar[wind_calendar['date'] >= datetime.date.today()]['date'].iloc[0]
    # 模型认为当日的交易已经点击下单，T0可用资金的变化已经体现当天的交易，故数据从T+1的试算交易数据开始取
    trial_order_data = custFOF.custFOF_getTrialTradeOrder(base_date, base_date + datetime.timedelta(365), portfolio_ids=portfolio_ids)
    if (not len(portfolio_ids)) or trial_order_data.empty:
        return pd.DataFrame()
    else:
        trial_order_data['trade_date'] = pd.to_datetime(trial_order_data['trade_date']).dt.date
        trial_order_data['trade_amount'] = trial_order_data['trade_amount'].apply(lambda x: float(str(x).replace(',', '')) if x is not None else x)
        trial_order_data['trade_volume'] = trial_order_data['trade_volume'].apply(lambda x: float(str(x).replace(',', '')) if x is not None else x)

        scheduled_trade = custFOF.custFOF_getTradeFutureFlow(datetime.date.today(), trial_order_data['trade_date'].max(), portfolio_ids)
        scheduled_trade = scheduled_trade[scheduled_trade['trade_volume'] < 1e9]  # 筛去作为占位使用的交易指令
        # 由于会存在先录入trial_trade后，又实际在camp进行预约交易的情况，上述两组数可能会有重复的条目，目前认为产品+日期+金额完全一致的就是重复项，会剔除重复
        for index, row in scheduled_trade.iterrows():
            trial_order_data = trial_order_data[~((trial_order_data['product_id'] == row['product_id']) & (trial_order_data['trade_date'] == row['trade_execute_date']) & ((trial_order_data['trade_amount'] == row['trade_volume']) | (trial_order_data['trade_volume'] == row['trade_volume'])))]  # 注意科目上的对齐
            # 对于全部赎回的指令,再进行一次判断,因为金证所计算的全部赎回份额可以实时考虑当日是否有分红(报酬),可能会导致金证(CAMP)指令的赎回份额与持仓份额不一致
            trial_order_data = trial_order_data[~((trial_order_data['product_id'] == row['product_id']) & (trial_order_data['trade_date'] == row['trade_execute_date']) & (trial_order_data['trade_type'] == '全部赎回') & (row['trade_type'] == '全部赎回'))]  # 注意科目上的对齐

        # FIXME 当前已存在同一产品具有两种可投份额的情况，目前全量展示在模板里并在网页端提示需要手动检查
        camp_product_id_mapping = custHF.custHF_getProductCAMPIDWithShareType()
        trial_order_data = pd.merge(trial_order_data, camp_product_id_mapping, on='product_id', how='left')
        duplicated_camp_product = camp_product_id_mapping[camp_product_id_mapping['product_id'].duplicated(keep=False)]
        if len(duplicated_camp_product) and len(trial_order_data[trial_order_data['product_id'].isin(duplicated_camp_product['product_id'].tolist())]):
            warning_trial_order_data = trial_order_data[trial_order_data['product_id'].isin(duplicated_camp_product['product_id'].tolist())]
            warning_trial_order_data = warning_trial_order_data[['product_id', 'product_name']].drop_duplicates()
            waring_strings = ' \n'.join(warning_trial_order_data.apply(lambda row: ''.join(row.astype(str)), axis=1))
            st.warning(':warning: 请注意！以下产品存在多种份额可投, 请在Excel文件中具体选择份额： \r\n' + waring_strings)

        trial_order_data['产品名称'] = trial_order_data['portfolio_id']
        trial_order_data['辅助列-1'] = trial_order_data['portfolio_name']
        trial_order_data['交易日'] = trial_order_data['trade_date']
        trial_order_data['基金名称'] = trial_order_data['product_id'] if trial_order_data.empty else trial_order_data.apply(lambda x: x['product_id'] if pd.isna(x['product_camp_id_with_share_type']) else x['product_camp_id_with_share_type'], axis=1)
        trial_order_data['辅助列-2'] = trial_order_data['product_name']
        trial_order_data['转入基金名称'] = ''
        trial_order_data['交易类型'] = trial_order_data['trade_type'].apply(lambda x: '赎回' if '赎回' in x else x)
        trial_order_data['需求金额/数量'] = trial_order_data.apply(lambda x: '全部份额' if str(x['trade_type']) == '全部赎回' else (x['trade_volume'] if '赎回' in str(x['trade_type']) else x['trade_amount']), axis=1) if not trial_order_data.empty else None
        trial_order_data[['渠道', '分红方式/巨额赎回', '备注']] = ''
        camp_template_result = trial_order_data.copy(deep=True)
        camp_template_result = camp_template_result[['交易日', '产品名称', '辅助列-1', '基金名称', '辅助列-2', '转入基金名称', '交易类型', '需求金额/数量', '渠道', '分红方式/巨额赎回', '备注']]
        camp_template_result = camp_template_result.set_index('交易日')

        return camp_template_result

# ------------------------------------------------------
# 获取具有标签信息的FOF账户的持仓数据
# 目前应用于邮件服务
# ------------------------------------------------------
def anlsFOF_getFOFHoldingDataWithProductLabel(
    date,
    portfolio_ids=None,
):
    result = custFOF.custFOF_getFOFHoldingData(date, date, portfolio_ids)
    result = _append_product_label_info(result)
    result['unit_cost'] = np.nan
    result['unit_val'] = np.nan
    result['product_appreciation'] = np.nan
    result.loc[result['product_volume'] > 0, 'unit_cost'] = result['COST'] / result['product_volume']
    result.loc[result['product_volume'] > 0, 'unit_val'] = result['VAL'] / result['product_volume']
    result.loc[result['product_volume'] > 0, 'product_appreciation'] = result['VAL'] - result['COST']

    return result