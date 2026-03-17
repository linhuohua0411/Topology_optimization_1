"""
邻接矩阵与边列表互转、CSV 读写、清洗。与 plan 6.2 数据格式约定一致。
约定：nodes.csv（节点ID、角色、客户端等），edges_tk.csv（时间戳 tk 时的边列表）。
"""


def edges_to_adjacency(edges, n_nodes):
    """边列表 -> 邻接矩阵 A。"""
    raise NotImplementedError


def adjacency_to_edges(A):
    """邻接矩阵 A -> 边列表。"""
    raise NotImplementedError


def load_edges_csv(path):
    """加载 edges_tk.csv，返回边列表及可选时间戳。"""
    raise NotImplementedError


def save_edges_csv(edges, path, timestamp=None):
    """保存边列表为 edges_tk.csv。"""
    raise NotImplementedError
