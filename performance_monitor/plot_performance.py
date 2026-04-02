# -*- coding: utf-8 -*-
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import argparse
import os
import sys
import numpy as np


def draw_raw_subplots(csv_file, output_name, title_prefix):
    """Raw 数据绘图：内存、句柄、上下文切换（3张子图）"""
    if not os.path.exists(csv_file):
        print(f"❌ Error: Required file not found: {csv_file}")
        sys.exit(1)

    try:
        df = pd.read_csv(csv_file)
        if df.empty:
            print(f"⚠️ Warning: {csv_file} is empty. Skipping.")
            return

        mem_col   = 'memory_mb'
        hnd_col   = 'handles'
        vol_col   = 'ctx_vol_per_sec'
        invol_col = 'ctx_invol_per_sec'

        df['timestamp'] = pd.to_datetime(df['timestamp'])

        numeric_cols = [mem_col, hnd_col, vol_col, invol_col]
        for col in numeric_cols:
            if col in df.columns:
                neg_count = (df[col] < 0).sum()
                if neg_count > 0:
                    print(f"ℹ️  Filtered {neg_count} negative values in {col} ({csv_file})")
                df.loc[df[col] < 0, col] = np.nan

        fig, (ax_mem, ax_hnd, ax_ctx) = plt.subplots(
            3, 1, figsize=(11, 11), sharex=True, layout='constrained'
        )

        ax_mem.plot(df['timestamp'], df[mem_col], color='#1f77b4', linewidth=1.5, marker='.', markersize=4)
        ax_mem.set_ylabel('Memory (MB)')
        ax_mem.set_title(f'{title_prefix} Performance Metrics', fontsize=14)
        ax_mem.grid(True, alpha=0.3)

        ax_hnd.plot(df['timestamp'], df[hnd_col], color='#d62728', linewidth=1.5, marker='.', markersize=4)
        ax_hnd.set_ylabel('Handles Count')
        ax_hnd.grid(True, alpha=0.3)

        if vol_col in df.columns and invol_col in df.columns:
            ax_ctx.plot(df['timestamp'], df[vol_col],   color='#2ca02c', label='Voluntary',   linewidth=1.2)
            ax_ctx.plot(df['timestamp'], df[invol_col], color='#ff7f0e', label='Involuntary', linewidth=1.2)
            ax_ctx.set_ylabel('Ctx Switches /s')
            ax_ctx.legend(loc='upper right', fontsize='small')
        else:
            ax_ctx.text(0.5, 0.5, "Ctx Columns Not Found", ha='center', va='center', transform=ax_ctx.transAxes)

        ax_ctx.set_xlabel('Time')
        ax_ctx.grid(True, alpha=0.3)
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


def draw_trend_subplots(csv_file, output_name, title_prefix):
    """
    Trend 数据绘图：
      子图1 — 内存 & 句柄（avg）
      子图2 — 平均上下文切换（avg_ctx_vol / avg_ctx_invol）
      子图3 — 峰值上下文切换（max_peak_vol / max_peak_invol）  ← 新增
      子图4 — Spike 次数（vol_spikes / invol_spikes）           ← 新增
    """
    if not os.path.exists(csv_file):
        print(f"❌ Error: Required file not found: {csv_file}")
        sys.exit(1)

    try:
        df = pd.read_csv(csv_file)
        if df.empty:
            print(f"⚠️ Warning: {csv_file} is empty. Skipping.")
            return

        df['timestamp'] = pd.to_datetime(df['timestamp'])

        # --- 负数过滤 ---
        numeric_cols = [
            'avg_mem', 'avg_handles',
            'avg_ctx_vol', 'avg_ctx_invol',
            'max_peak_vol', 'max_peak_invol',
            'vol_spikes', 'invol_spikes',
        ]
        for col in numeric_cols:
            if col in df.columns and pd.api.types.is_numeric_dtype(df[col]):
                neg_count = (df[col] < 0).sum()
                if neg_count > 0:
                    print(f"ℹ️  Filtered {neg_count} negative values in {col} ({csv_file})")
                df.loc[df[col] < 0, col] = np.nan

        has_peak   = 'max_peak_vol'  in df.columns and 'max_peak_invol' in df.columns
        has_spikes = 'vol_spikes'    in df.columns and 'invol_spikes'   in df.columns

        # 动态决定行数
        n_rows = 2 + int(has_peak) + int(has_spikes)
        fig, axes = plt.subplots(
            n_rows, 1,
            figsize=(11, 3.5 * n_rows),
            sharex=True,
            layout='constrained'
        )
        if n_rows == 1:
            axes = [axes]

        ax_idx = 0

        # ── 子图1：内存 & 句柄 ──────────────────────────────────────
        ax1 = axes[ax_idx]; ax_idx += 1
        color_mem = '#1f77b4'
        color_hnd = '#d62728'

        ax1.set_title(f'{title_prefix} Performance Metrics', fontsize=14)
        ax1.grid(True, alpha=0.3)

        if 'avg_mem' in df.columns:
            ax1.plot(df['timestamp'], df['avg_mem'],
                     color=color_mem, linewidth=1.5, marker='.', markersize=4, label='Avg Memory (MB)')
            ax1.set_ylabel('Memory (MB)', color=color_mem)
            ax1.tick_params(axis='y', labelcolor=color_mem)

        if 'avg_handles' in df.columns:
            ax1b = ax1.twinx()
            ax1b.plot(df['timestamp'], df['avg_handles'],
                      color=color_hnd, linewidth=1.5, marker='.', markersize=4, label='Avg Handles')
            ax1b.set_ylabel('Handles Count', color=color_hnd)
            ax1b.tick_params(axis='y', labelcolor=color_hnd)
            # 合并图例
            lines1, labels1 = ax1.get_legend_handles_labels()
            lines2, labels2 = ax1b.get_legend_handles_labels()
            ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper right', fontsize='small')

        # ── 子图2：平均上下文切换 ───────────────────────────────────
        ax2 = axes[ax_idx]; ax_idx += 1
        ax2.grid(True, alpha=0.3)
        ax2.set_ylabel('Avg Ctx Switches /s')

        if 'avg_ctx_vol' in df.columns:
            ax2.plot(df['timestamp'], df['avg_ctx_vol'],
                     color='#2ca02c', linewidth=1.2, marker='.', markersize=3, label='Avg Voluntary')
        if 'avg_ctx_invol' in df.columns:
            ax2.plot(df['timestamp'], df['avg_ctx_invol'],
                     color='#ff7f0e', linewidth=1.2, marker='.', markersize=3, label='Avg Involuntary')
        ax2.legend(loc='upper right', fontsize='small')

        # ── 子图3（新增）：峰值上下文切换 ──────────────────────────
        if has_peak:
            ax3 = axes[ax_idx]; ax_idx += 1
            ax3.grid(True, alpha=0.3)
            ax3.set_ylabel('Peak Ctx Switches /s')

            ax3.plot(df['timestamp'], df['max_peak_vol'],
                     color='#17becf', linewidth=1.3, marker='^', markersize=5,
                     label='Peak Voluntary (max_peak_vol)')
            ax3.plot(df['timestamp'], df['max_peak_invol'],
                     color='#9467bd', linewidth=1.3, marker='v', markersize=5,
                     label='Peak Involuntary (max_peak_invol)')

            # 标注自愿切换最高点
            peak_vol_idx = df['max_peak_vol'].idxmax()
            if not pd.isna(df.loc[peak_vol_idx, 'max_peak_vol']):
                ax3.annotate(
                    f"  {df.loc[peak_vol_idx, 'max_peak_vol']:.0f}/s",
                    xy=(df.loc[peak_vol_idx, 'timestamp'], df.loc[peak_vol_idx, 'max_peak_vol']),
                    fontsize=8, color='#17becf',
                    arrowprops=dict(arrowstyle='->', color='#17becf', lw=0.8),
                    xytext=(10, 10), textcoords='offset points'
                )

            ax3.legend(loc='upper right', fontsize='small')

        # ── 子图4（新增）：Spike 次数 ───────────────────────────────
        if has_spikes:
            ax4 = axes[ax_idx]; ax_idx += 1
            ax4.grid(True, alpha=0.3)
            ax4.set_ylabel('Spike Count')

            # Add labels here so the legend can find them
            ax4.plot(df['timestamp'], df['vol_spikes'],
                     color='#2ca02c', linewidth=1.2, marker='o', markersize=4, 
                     label='Vol Spikes') # Added label

            ax4.plot(df['timestamp'], df['invol_spikes'],
                     color='#ff7f0e', linewidth=1.2, marker='s', markersize=4, 
                     label='Invol Spikes') # Added label

            ax4.yaxis.get_major_locator().set_params(integer=True)
            ax4.legend(loc='upper right', fontsize='small')

        # ── X 轴格式 ────────────────────────────────────────────────
        axes[-1].set_xlabel('Time')
        axes[-1].xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
        plt.setp(axes[-1].get_xticklabels(), rotation=45, ha='right')

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
    parser.add_argument("--raw_csv",   type=str, required=True)
    parser.add_argument("--trend_csv", type=str, required=True)
    parser.add_argument("--raw_out",   type=str, default="report_raw_detail.png")
    parser.add_argument("--trend_out", type=str, default="report_trend_summary.png")

    args = parser.parse_args()
    draw_raw_subplots(args.raw_csv,   args.raw_out,   "Raw (Detailed)")
    draw_trend_subplots(args.trend_csv, args.trend_out, "Trend (Aggregated)")


if __name__ == "__main__":
    main()