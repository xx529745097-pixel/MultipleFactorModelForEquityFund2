# ------------------------------------------------
# 本文档用于生成公募基金深度报告
# ------------------------------------------------
import src.analysis.MFAnalysis as MFanls
import src.visualization.MFPlot as MFPlot
import datetime

if __name__ == '__main__':
    # 输入
    product_ids = ['163406.SZ', '163417.SZ'] # 第一个为主分析基金
    benchmark = '885001.WI'
    start_date = datetime.date(2017,1,1)
    end_date = datetime.date(2022,1,22)
    # 输出
    MFPlot.visMF_navHist(start_date, end_date, product_ids, benchmark)
    MFPlot.visMF_Correlation(start_date, end_date, product_ids)
    MFPlot.visMF_navHist(start_date, end_date, [product_ids[0]], benchmark)
    performance = MFanls.anlsMF_retAnalysis(start_date, end_date, product_ids[0], benchmark)
