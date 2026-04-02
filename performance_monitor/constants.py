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
TREND_COLUMNS = [
    "timestamp", 
    "avg_ctx_vol", 
    "avg_ctx_invol", 
    "avg_mem", 
    "avg_threads", 
    "avg_handles",
    # --- 自愿切换监测 (针对锁竞争/阻塞) ---
    "max_peak_vol",      # 捕获类似 13k/s 的极端自愿切换
    "vol_peak_time",     # 自愿切换达峰时刻
    "vol_spikes",        # 这一周期内发生高频锁竞争的次数
    # --- 非自愿切换监测 (针对内核抢占) ---
    "max_peak_invol",    # 针对实时性破坏的瞬时峰值
    "invol_peak_time",   # 非自愿切换达峰时刻
    "invol_spikes"       # 这一周期内发生内核强行打断的次数
]

# 初始加载配置
INITIAL_LOAD_COUNT = 200  # 第一次连接时读取原始数据的行数
VOL_THRESHOLD = 5000   # 每秒超过 5000 次自愿切换算作一次抖动
INVOL_THRESHOLD = 50   # 每秒超过 50 次非自愿切换算作一次抖动