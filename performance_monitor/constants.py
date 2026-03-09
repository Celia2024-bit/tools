# constants.py

# 默认文件名
DEFAULT_RAW_FILE = "raw_performance.csv"
DEFAULT_TREND_FILE = "trend_performance.csv"

# 监控默认配置
DEFAULT_EXE = "WorkspaceTests.exe"
DEFAULT_INTERVAL = 5
DEFAULT_TREND_LIMIT = 3

# CSV 表头定义
# ctx_vol_per_sec   = voluntary context switches/sec   (线程主动让出，正常)
# ctx_invol_per_sec = involuntary context switches/sec (被强制切走，竞争问题)
RAW_COLUMNS   = ["timestamp", "ctx_vol_per_sec", "ctx_invol_per_sec", "threads", "handles", "memory_mb"]
TREND_COLUMNS = ["timestamp", "avg_ctx_vol", "avg_ctx_invol", "avg_memory", "avg_threads", "avg_handles"]

# 初始加载配置
INITIAL_LOAD_COUNT = 200  # 第一次连接时读取原始数据的行数