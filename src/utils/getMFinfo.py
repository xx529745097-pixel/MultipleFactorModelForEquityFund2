# ------------------------------------------------
# 本文档用于新发基金数据处理
# ------------------------------------------------
import src.data.wind as wind
import datetime

# ------------------------------------------------------
# 获取即将发行的基金信息
# ------------------------------------------------------
def MFInfo_getIssuingNewMF():
    today = datetime.date.today()
    MFIssure_new = wind.wind_getMFIssueinfo(today, issue=True) # 未来发行的基金
    return MFIssure_new

# ------------------------------------------------------
# 获取最近成立的基金信息
# ------------------------------------------------------
def MFInfo_getIssuedNewMF(days): # days，统计过去多少个自然日成立的基金
    assert (type(days) == int), '天数的输入格式应为int'
    today = datetime.date.today()
    before = today - datetime.timedelta(days)
    MFIssure_before = wind.wind_getMFIssueinfo(before, issue=False) # 过去days成立的基金
    return MFIssure_before

