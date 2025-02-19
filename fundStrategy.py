import pandas as pd
import datetime
from dateutil.relativedelta import relativedelta
import numpy as np
import sqlalchemy
from dateutil.parser import parse
from matplotlib import pyplot as plt
import src.utils.Calculation as Cal
import src.data.wind as wind

# --------------------------------------------
# 筛选股票型，偏股混合型，高仓位灵活配置型(>=50%)基金池
# --------------------------------------------
def fstrat_getEquityFundPool():
    fund_info = wind.wind_getHistoricalProductList(include_pm_info=True)
    fund_info = fund_info[fund_info['type'].isin(['普通股票型基金', '偏股混合型基金', '灵活配置型基金'])]
    return fund_info

if __name__ == '__main__':
    fstrat_getEquityFundPool()


