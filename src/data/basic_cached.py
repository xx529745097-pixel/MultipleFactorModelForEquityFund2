# ------------------------------------------------------
# 本文档用于从AMFOF数据库存取缓存的基础数据
# ------------------------------------------------------

import pandas as pd
import datetime
import src.data.amdata as am
import src.data.irm as irm
import src.data.custHF as custHF
import src.data.custMF as custMF


# ------------------------------------------------------
# 缓存每日公募私募策略评级信息snapshot
# ------------------------------------------------------
def basicCached_cacheStrategyRatingSnapshot(
    date=datetime.date.today(),  # 数据日期时间戳
    insert=False
):
    hf_info = custHF.custHF_getStrategyInfo()[['strategy_name', 'strategy_id', 'strategy_rating', 'strategy_catetory']]
    mf_info = custMF.custMF_getMFStrategyInfo()[['strategy_name', 'strategy_id', 'strategy_rating', 'strategy_catetory']]
    result_df = hf_info.append(mf_info)
    result_df['dt'] = date
    result_df['create_time'] = datetime.date.today()

    if insert:
        # AMDATA数据库
        # Delete existing key if exists
        conn = am.amdata_connectAmdataDb()
        sql = "DELETE FROM AMFOF.FUND_DAILY_SNAPSHOT WHERE DT=TO_DATE('{}', 'yyyy-mm-dd')"
        sql = sql.format(date)
        cur = conn.cursor()
        cur.execute(sql)
        conn.commit()

        # Write into database
        am.amdata_insertAMData(result_df, 'AMFOF.FUND_DAILY_SNAPSHOT')

        # IRM数据库
        # Delete existing key if exists
        conn = irm.irm_connectIRMDB()
        sql = "DELETE FROM irm.AMFOF_FUND_DAILY_SNAPSHOT WHERE DT=DATE'{}'"
        sql = sql.format(date)
        cur = conn.cursor()
        cur.execute(sql)
        conn.commit()

        # Write into database
        irm.irm_insertIRMData(result_df, 'irm.AMFOF_FUND_DAILY_SNAPSHOT')

    return result_df
