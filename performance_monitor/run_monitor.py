# run_monitor.py
import argparse
from monitor_module import start_performance_monitor
import constants as C

def main():
    # 1. 创建参数解析器
    parser = argparse.ArgumentParser(description="Performance Monitor Tool")

    # 2. 定义参数 (设置了默认值，如果你不输入，就用默认的)
    parser.add_argument("--exe", type=str, default=C.DEFAULT_EXE)
    parser.add_argument("--interval", type=int, default=C.DEFAULT_INTERVAL)
    parser.add_argument("--limit", type=int, default=C.DEFAULT_TREND_LIMIT)
    parser.add_argument("--raw", type=str, default=C.DEFAULT_RAW_FILE)
    parser.add_argument("--trend", type=str, default=C.DEFAULT_TREND_FILE)

    # 3. 解析参数
    args = parser.parse_args()

    print("--- Monitor Configuration ---")
    print(f"Target EXE: {args.exe}")
    print(f"Interval  : {args.interval}s")
    print(f"Trend Limit: {args.limit} points")
    print(f"Output    : {args.raw}, {args.trend}")
    print("----------------------------")

    # 4. 启动监控
    start_performance_monitor(
        exe_name=args.exe, 
        raw_csv=args.raw, 
        trend_csv=args.trend, 
        interval_sec=args.interval, 
        trend_limit=args.limit
    )

if __name__ == "__main__":
    main()