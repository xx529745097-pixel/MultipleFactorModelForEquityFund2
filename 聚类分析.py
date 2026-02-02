import datetime

import pandas as pd
import numpy as np
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
import matplotlib.pyplot as plt
import src.data.wind as wind

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import AgglomerativeClustering
from scipy.cluster.hierarchy import dendrogram, linkage
from sklearn.metrics import silhouette_score

def cluster_funds(returns_df, n_clusters=None):
    """
    对基金历史收益序列进行聚类

    参数:
    returns_df (pd.DataFrame): 基金历史收益数据框
        - 每行代表一个基金
        - 每列代表一个时间点的收益
    n_clusters (int, optional): 聚类数量，如果未指定则自动确定

    返回:
    pd.DataFrame: 包含原始数据和聚类标签的数据框
    """
    # 检查输入有效性
    if not isinstance(returns_df, pd.DataFrame):
        raise TypeError("输入必须是Pandas DataFrame")

    # 数据标准化
    scaler = StandardScaler()
    scaled_data = scaler.fit_transform(returns_df)

    # 自动确定聚类数量（肘部法则）
    if n_clusters is None:
        print("未指定聚类数量，使用肘部法则自动确定...")
        sse = []
        max_clusters = min(10, len(returns_df) - 1)  # 最大尝试聚类数
        k_range = range(1, max_clusters + 1)

        for k in k_range:
            kmeans = KMeans(n_clusters=k, init='k-means++', n_init=10, random_state=42)
            kmeans.fit(scaled_data)
            sse.append(kmeans.inertia_)  # 保存SSE（簇内平方和）

        # 计算SSE变化的百分比
        sse_diff = np.diff(sse)
        sse_diff_perc = sse_diff[:-1] / sse_diff[1:]

        # 找到"肘点" - SSE下降明显变缓的点
        elbow_point = np.argmax(sse_diff_perc) + 2  # +2 因为从k=2开始计算变化率

        # 确保肘点有效
        n_clusters = max(2, min(elbow_point, max_clusters))
        print(f"自动确定的最佳聚类数量: {n_clusters}")

        # 可选：绘制肘部法则图
        plt.figure(figsize=(10, 6))
        plt.plot(k_range, sse, 'bo-')
        plt.xlabel('聚类数量')
        plt.ylabel('簇内平方和 (SSE)')
        plt.title('肘部法则')
        plt.axvline(x=n_clusters, color='r', linestyle='--')
        plt.show()

    # 检查聚类数量有效性
    if n_clusters <= 0:
        raise ValueError("聚类数量必须为正整数")
    if len(returns_df) < n_clusters:
        raise ValueError("聚类数量不能超过样本数量")

    # 执行K-Means聚类
    kmeans = KMeans(
        n_clusters=n_clusters,
        init='k-means++',
        n_init=10,
        random_state=42
    )
    clusters = kmeans.fit_predict(scaled_data)

    # 添加聚类标签到原始数据框
    clustered_df = returns_df.copy()
    clustered_df['Cluster'] = clusters

    return clustered_df

def cluster_funds_complete(returns_df, n_clusters=None):
    """
    使用 Complete Linkage 层次聚类对基金历史收益序列进行聚类

    参数:
    returns_df (pd.DataFrame): 基金历史收益数据框
        - 每行代表一个基金
        - 每列代表一个时间点的收益
    n_clusters (int, optional): 聚类数量，如果未指定则自动确定

    返回:
    pd.DataFrame: 包含原始数据和聚类标签的数据框
    """
    # 检查输入有效性
    if not isinstance(returns_df, pd.DataFrame):
        raise TypeError("输入必须是Pandas DataFrame")

    # 数据标准化
    scaler = StandardScaler()
    scaled_data = scaler.fit_transform(returns_df)

    # 自动确定聚类数量（使用轮廓系数）
    if n_clusters is None:
        print("未指定聚类数量，使用轮廓系数自动确定...")
        best_score = -1
        best_n = 2
        max_clusters = min(10, len(returns_df) - 1)

        for k in range(2, max_clusters + 1):
            clustering = AgglomerativeClustering(
                n_clusters=k,
                linkage='complete'
            )
            clusters = clustering.fit_predict(scaled_data)
            score = silhouette_score(scaled_data, clusters)

            if score > best_score:
                best_score = score
                best_n = k

        n_clusters = best_n
        print(f"自动确定的最佳聚类数量: {n_clusters} (轮廓系数: {best_score:.4f})")

    # 检查聚类数量有效性
    if n_clusters <= 0:
        raise ValueError("聚类数量必须为正整数")
    if len(returns_df) < n_clusters:
        raise ValueError("聚类数量不能超过样本数量")

    # 执行 Complete Linkage 层次聚类
    clustering = AgglomerativeClustering(
        n_clusters=n_clusters,
        linkage='complete'
    )
    clusters = clustering.fit_predict(scaled_data)

    # 添加聚类标签到原始数据框
    clustered_df = returns_df.copy()
    clustered_df['Cluster'] = clusters

    # 可视化树状图
    plt.figure(figsize=(12, 8))
    linkage_matrix = linkage(scaled_data, method='complete')
    dendrogram(linkage_matrix, labels=returns_df.index.tolist())
    plt.title('Complete Linkage Hierarchical Clustering Dendrogram')
    plt.xlabel('Fund ID')
    plt.ylabel('Distance')
    plt.axhline(y=linkage_matrix[-n_clusters + 1, 2], color='r', linestyle='--')
    plt.show()

    return clustered_df


# 示例用法
if __name__ == "__main__":
    # path = 'C:/Users/041685/Desktop/基金研究/公募基金研究/公募月度研究会/投委会、月度会材料/投委会专题/'
    # df = pd.read_excel(path+'行业轮动基金筛选.xlsx', sheet_name='并集')
    # enddate = df['date'][0].date()
    # startdate = enddate - datetime.timedelta(730)
    # fcode = df['product_id'].tolist()
    # ret_df = wind.wind_getMFStats(
    #     fcode,  # wind基金代码，输入格式：List 如 ['000001.OF', '000002.OF']
    #     startdate,  # 起始日期，输入格式:datetime.date
    #     enddate,  # 结束日期，输入格式:datetime.date
    #     stats=['f_avgreturn_day'],  # 通过ChinaMFPerformance表格来查可以输入的stats,所有字母用小写。
    #     MF=True  # 如果MF为False，则对应的是的券商理财产品的stats
    # )
    # tradedate = wind.wind_getSSECalendar()
    # tradedate = tradedate[tradedate['date']>= startdate]
    # tradedate = tradedate[tradedate['date']<= enddate]
    # pivot_df = ret_df.pivot(index='date', columns='product_id', values='f_avgreturn_day')
    # filtered_df = pivot_df.loc[pivot_df.index.isin(tradedate['date'].tolist())]
    # filtered_df = filtered_df.dropna(axis = 1)
    # results = cluster_funds_complete(filtered_df.T, 4)
    # cluster1 = results[results['Cluster']==0].drop('Cluster', axis = 1).T
    # cluster2 = results[results['Cluster']==1].drop('Cluster', axis = 1).T
    # cluster3 = results[results['Cluster']==2].drop('Cluster', axis = 1).T
    # cluster4 = results[results['Cluster']==3].drop('Cluster', axis = 1).T
    # cluster5 = results[results['Cluster']==4].drop('Cluster', axis = 1).T
    # # cluster6 = results[results['Cluster']==5].drop('Cluster', axis = 1).T
    # # cluster7 = results[results['Cluster']==6].drop('Cluster', axis = 1).T
    # cluster1['avg_return'] = cluster1.mean(axis = 1)
    # cluster2['avg_return'] = cluster2.mean(axis = 1)
    # cluster3['avg_return'] = cluster3.mean(axis = 1)
    # cluster4['avg_return'] = cluster4.mean(axis = 1)
    # cluster5['avg_return'] = cluster5.mean(axis = 1)
    # # cluster6['avg_return'] = cluster6.mean(axis = 1)
    # # cluster7['avg_return'] = cluster7.mean(axis = 1)
    # results = results.T
    # results['Cluster1'] = cluster1['avg_return']
    # results['Cluster2'] = cluster2['avg_return']
    # results['Cluster3'] = cluster3['avg_return']
    # results['Cluster4'] = cluster4['avg_return']
    # results['Cluster5'] = cluster5['avg_return']
    # # results['Cluster6'] = cluster6['avg_return']
    # # results['Cluster7'] = cluster7['avg_return']
    # results.to_excel(path+'聚类结果_20240905_分4类_2年.xlsx')

    ###### 固收+基金池
    df = pd.read_excel('债基-输出结果/固收+基金池_20251031.xlsx')
    enddate = df['date'][0].date()
    startdate = enddate - datetime.timedelta(365)
    fcode = df['product_id'].tolist()
    ret_df = wind.wind_getMFStats(
        fcode,  # wind基金代码，输入格式：List 如 ['000001.OF', '000002.OF']
        startdate,  # 起始日期，输入格式:datetime.date
        enddate,  # 结束日期，输入格式:datetime.date
        stats=['f_avgreturn_day'],  # 通过ChinaMFPerformance表格来查可以输入的stats,所有字母用小写。
        MF=True  # 如果MF为False，则对应的是的券商理财产品的stats
    )
    tradedate = wind.wind_getSSECalendar()
    tradedate = tradedate[tradedate['date']>= startdate]
    tradedate = tradedate[tradedate['date']<= enddate]
    pivot_df = ret_df.pivot(index='date', columns='product_id', values='f_avgreturn_day')
    filtered_df = pivot_df.loc[pivot_df.index.isin(tradedate['date'].tolist())]
    filtered_df = filtered_df.dropna(axis = 1)
    results = cluster_funds(filtered_df.T, 3)
    cluster1 = results[results['Cluster']==0].drop('Cluster', axis = 1).T
    cluster2 = results[results['Cluster']==1].drop('Cluster', axis = 1).T
    cluster3 = results[results['Cluster']==2].drop('Cluster', axis = 1).T
    # cluster4 = results[results['Cluster']==3].drop('Cluster', axis = 1).T
    cluster1['avg_return'] = cluster1.mean(axis = 1)
    cluster2['avg_return'] = cluster2.mean(axis = 1)
    cluster3['avg_return'] = cluster3.mean(axis = 1)
    # cluster4['avg_return'] = cluster4.mean(axis = 1)
    results = results.T
    results['Cluster1'] = cluster1['avg_return']
    results['Cluster2'] = cluster2['avg_return']
    results['Cluster3'] = cluster3['avg_return']
    # results['Cluster4'] = cluster4['avg_return']
    results.to_excel('债基-输出结果/固收+聚类结果_20251031.xlsx')
    #######

    ####### 行业轮动基金