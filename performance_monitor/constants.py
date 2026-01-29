# constants.py

# 默认文件名
DEFAULT_RAW_FILE = "raw_performance.csv"
DEFAULT_TREND_FILE = "trend_performance.csv"

# 监控默认配置
DEFAULT_EXE = "WorkspaceTests.exe"
DEFAULT_INTERVAL = 5
DEFAULT_TREND_LIMIT = 3

# CSV 表头定义 (严格对齐你的数据格式)
RAW_COLUMNS = ["timestamp", "cpu_percent", "threads", "handles", "memory_mb"]
TREND_COLUMNS = ["timestamp", "avg_memory", "avg_threads", "avg_handles"]


# 初始加载配置
INITIAL_LOAD_COUNT = 200  # 第一次连接时读取原始数据的行数