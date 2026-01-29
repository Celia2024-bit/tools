# -*- coding: utf-8 -*-
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import argparse
import os
import sys

def draw_perf_subplots(csv_file, output_name, title_prefix):
    """通用绘图逻辑"""
    # 严格校验：如果文件不存在，直接报错并退出
    if not os.path.exists(csv_file):
        print(f"❌ Error: Required file not found: {csv_file}")
        sys.exit(1) 

    try:
        df = pd.read_csv(csv_file)
        if df.empty:
            print(f"⚠️ Warning: {csv_file} is empty. Skipping.")
            return

        # 智能识别表头 (Raw: memory_mb, Trend: avg_memory)
        mem_col = 'memory_mb' if 'memory_mb' in df.columns else 'avg_memory'
        hnd_col = 'handles' if 'handles' in df.columns else 'avg_handles'
        
        df['timestamp'] = pd.to_datetime(df['timestamp'])

        fig, (ax_mem, ax_hnd) = plt.subplots(2, 1, figsize=(11, 8), sharex=True)

        # 内存趋势
        ax_mem.plot(df['timestamp'], df[mem_col], color='#1f77b4', linewidth=1.5, marker='.', markersize=4)
        ax_mem.set_ylabel('Memory (MB)')
        ax_mem.set_title(f'{title_prefix} Performance Metrics', fontsize=14)
        ax_mem.grid(True, alpha=0.3)

        # 句柄趋势
        ax_hnd.plot(df['timestamp'], df[hnd_col], color='#d62728', linewidth=1.5, marker='.', markersize=4)
        ax_hnd.set_ylabel('Handles Count')
        ax_hnd.set_xlabel('Time')
        ax_hnd.grid(True, alpha=0.3)

        ax_hnd.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
        plt.xticks(rotation=45)
        plt.tight_layout()

        plt.savefig(output_name, dpi=300)
        plt.close()
        print(f"✅ Successfully generated: {output_name}")
        
    except Exception as e:
        print(f"❌ Failed to process {csv_file}: {e}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Professional Performance Plotter")
    
    # 强制要求传入文件名，不设默认值，或者默认值设为 None
    parser.add_argument("--raw_csv", type=str, required=True, help="Path to the raw CSV file")
    parser.add_argument("--trend_csv", type=str, required=True, help="Path to the trend CSV file")
    
    # 输出文件名可以设默认值
    parser.add_argument("--raw_out", type=str, default="report_raw_detail.png")
    parser.add_argument("--trend_out", type=str, default="report_trend_summary.png")

    args = parser.parse_args()

    # 执行绘图
    draw_perf_subplots(args.raw_csv, args.raw_out, "Raw (Detailed)")
    draw_perf_subplots(args.trend_csv, args.trend_out, "Trend (Aggregated)")

if __name__ == "__main__":
    main()