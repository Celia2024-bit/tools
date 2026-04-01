# -*- coding: utf-8 -*-
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import argparse
import os
import sys
import numpy as np

def draw_perf_subplots(csv_file, output_name, title_prefix):
    """通用绘图逻辑：绘制内存、句柄和上下文切换"""
    if not os.path.exists(csv_file):
        print(f"❌ Error: Required file not found: {csv_file}")
        sys.exit(1) 

    try:
        df = pd.read_csv(csv_file)
        if df.empty:
            print(f"⚠️ Warning: {csv_file} is empty. Skipping.")
            return

        # 智能识别表头
        mem_col = 'memory_mb' if 'memory_mb' in df.columns else 'avg_memory'
        hnd_col = 'handles' if 'handles' in df.columns else 'avg_handles'
        vol_col = 'ctx_vol_per_sec' if 'ctx_vol_per_sec' in df.columns else 'avg_ctx_vol'
        invol_col = 'ctx_invol_per_sec' if 'ctx_invol_per_sec' in df.columns else 'avg_ctx_invol'
        
        # --- 数据清洗逻辑 ---
        # 1. 转换时间
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # 2. 负数过滤器：遍历所有数值列，将小于 0 的值设为 NaN
        # 这样绘图时这些异常点会被直接忽略（断开连接），而不是显示错误的负值
        numeric_cols = [mem_col, hnd_col, vol_col, invol_col]
        for col in numeric_cols:
            if col in df.columns:
                # 统计一下有多少负数（可选，用于调试）
                neg_count = (df[col] < 0).sum()
                if neg_count > 0:
                    print(f"ℹ️  Filtered {neg_count} negative values in {col} ({csv_file})")
                
                # 将负数置为空
                df.loc[df[col] < 0, col] = np.nan

        # 使用 layout='constrained' 适配布局
        fig, (ax_mem, ax_hnd, ax_ctx) = plt.subplots(3, 1, figsize=(11, 11), sharex=True, layout='constrained')

        # 内存趋势
        ax_mem.plot(df['timestamp'], df[mem_col], color='#1f77b4', linewidth=1.5, marker='.', markersize=4)
        ax_mem.set_ylabel('Memory (MB)')
        ax_mem.set_title(f'{title_prefix} Performance Metrics', fontsize=14)
        ax_mem.grid(True, alpha=0.3)

        # 句柄趋势
        ax_hnd.plot(df['timestamp'], df[hnd_col], color='#d62728', linewidth=1.5, marker='.', markersize=4)
        ax_hnd.set_ylabel('Handles Count')
        ax_hnd.grid(True, alpha=0.3)

        # 上下文切换趋势
        if vol_col in df.columns and invol_col in df.columns:
            # 使用 plot 绘图，由于负数变成了 NaN，折线会自动在异常点处断开
            ax_ctx.plot(df['timestamp'], df[vol_col], color='#2ca02c', label='Voluntary', linewidth=1.2)
            ax_ctx.plot(df['timestamp'], df[invol_col], color='#ff7f0e', label='Involuntary', linewidth=1.2)
            ax_ctx.set_ylabel('Ctx Switches')
            ax_ctx.legend(loc='upper right', fontsize='small')
        else:
            ax_ctx.text(0.5, 0.5, "Ctx Columns Not Found", ha='center', va='center', transform=ax_ctx.transAxes)
        
        ax_ctx.set_xlabel('Time')
        ax_ctx.grid(True, alpha=0.3)

        # 格式化 X 轴
        ax_ctx.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
        plt.setp(ax_ctx.get_xticklabels(), rotation=45, ha='right')

        plt.savefig(output_name, dpi=300)
        plt.close(fig)
        print(f"✅ Successfully generated: {output_name}")
        
    except Exception as e:
        print(f"❌ Failed to process {csv_file}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Professional Performance Plotter")
    parser.add_argument("--raw_csv", type=str, required=True, help="Path to the raw CSV file")
    parser.add_argument("--trend_csv", type=str, required=True, help="Path to the trend CSV file")
    parser.add_argument("--raw_out", type=str, default="report_raw_detail.png")
    parser.add_argument("--trend_out", type=str, default="report_trend_summary.png")

    args = parser.parse_args()
    draw_perf_subplots(args.raw_csv, args.raw_out, "Raw (Detailed)")
    draw_perf_subplots(args.trend_csv, args.trend_out, "Trend (Aggregated)")

if __name__ == "__main__":
    main()