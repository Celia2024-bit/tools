# -*- coding: utf-8 -*-
"""
check_regression.py
-------------------
Called at the end of CI/CD pipeline.
Reads trend CSV and checks two things per metric:
  1. Threshold breach  — any value exceeds absolute limit
  2. Upward trend      — slope across all trend points is positive

Metrics checked:
  - ctx_invol  involuntary context switches/sec  (thread contention)
  - memory     MB
  - threads    count
  - handles    count

  NOTE: voluntary ctx switches are NOT checked for upward trend —
  a thread voluntarily yielding (waiting on I/O) is normal behaviour.
  Only involuntary (forced preemption) indicates scheduling pressure.

Exit 0 = PASS, Exit 1 = FAIL (blocks merge in CI/CD)

Usage:
  python3 check_regression.py --trend_csv build_result/trend_performance.csv

  # with custom thresholds:
  python3 check_regression.py --trend_csv build_result/trend_performance.csv \
      --ctx_invol_limit 500  \
      --mem_limit 200        \
      --thread_limit 60      \
      --handle_limit 500     \
      --slope_threshold 0.05
"""

import argparse
import csv
import sys
import os

# ── Default thresholds ───────────────────────────────────────────────────────
DEFAULT_CTX_INVOL_LIMIT  = 500    # involuntary ctx switches/sec absolute ceiling
DEFAULT_MEM_LIMIT        = 200.0  # MB
DEFAULT_THREAD_LIMIT     = 60
DEFAULT_HANDLE_LIMIT     = 500
DEFAULT_SLOPE_THRESHOLD  = 0.05   # per trend-point; lower = stricter


def load_trend_csv(path):
    rows = []
    with open(path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                rows.append({
                    'timestamp':   row.get('timestamp', ''),
                    'ctx_vol':     float(row.get('avg_ctx_vol',   0)),
                    'ctx_invol':   float(row.get('avg_ctx_invol', 0)),
                    'avg_memory':  float(row.get('avg_memory',    0)),
                    'avg_threads': float(row.get('avg_threads',   0)),
                    'avg_handles': float(row.get('avg_handles',   0)),
                })
            except ValueError:
                continue
    return rows


def linear_slope(values):
    """Least-squares slope. Positive = upward trend."""
    n = len(values)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2.0
    y_mean = sum(values) / n
    num = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    den = sum((i - x_mean) ** 2 for i in range(n))
    return num / den if den != 0 else 0.0


def check(rows, ctx_invol_limit, mem_limit, thread_limit, handle_limit, slope_threshold):
    failures = []
    info     = []

    ctx_invol_vals = [r['ctx_invol']   for r in rows]
    mem_vals       = [r['avg_memory']  for r in rows]
    thread_vals    = [r['avg_threads'] for r in rows]
    handle_vals    = [r['avg_handles'] for r in rows]

    # ── 1. Absolute threshold ────────────────────────────────────────────────
    checks = [
        ("ctx_invol/s", ctx_invol_vals, ctx_invol_limit, ".0f", "ctx switches/sec"),
        ("memory",      mem_vals,       mem_limit,        ".1f", "MB"),
        ("threads",     thread_vals,    thread_limit,     "d",   ""),
        ("handles",     handle_vals,    handle_limit,     "d",   ""),
    ]

    for name, vals, limit, fmt, unit in checks:
        peak = max(vals)
        peak_str  = format(int(peak) if fmt == 'd' else peak, fmt if fmt != 'd' else '.0f')
        limit_str = format(int(limit) if fmt == 'd' else limit, fmt if fmt != 'd' else '.0f')
        if peak > limit:
            failures.append(
                f"  ❌ THRESHOLD BREACH  {name:<14} peak={peak_str}{unit}  limit={limit_str}{unit}"
            )
        else:
            info.append(
                f"  ✅ {name:<14}  peak={peak_str}{unit}  (limit={limit_str}{unit})"
            )

    # ── 2. Upward trend (slope) ──────────────────────────────────────────────
    # voluntary ctx switches intentionally skipped (see module docstring)
    slope_checks = [
        ("ctx_invol/s", ctx_invol_vals, "ctx switches/sec"),
        ("memory",      mem_vals,       "MB/pt"),
        ("threads",     thread_vals,    "/pt"),
        ("handles",     handle_vals,    "/pt"),
    ]

    for name, vals, unit in slope_checks:
        slope = linear_slope(vals)
        if slope > slope_threshold:
            failures.append(
                f"  ❌ UPWARD TREND      {name:<14} slope={slope:.4f}{unit}  threshold={slope_threshold}"
            )
        else:
            info.append(
                f"  ✅ {name:<14}  slope={slope:.4f}  (stable)"
            )

    return (len(failures) == 0), info, failures


def main():
    parser = argparse.ArgumentParser(description="CI/CD Performance Regression Checker")
    parser.add_argument("--trend_csv",        type=str,   required=True)
    parser.add_argument("--ctx_invol_limit",  type=float, default=DEFAULT_CTX_INVOL_LIMIT)
    parser.add_argument("--mem_limit",        type=float, default=DEFAULT_MEM_LIMIT)
    parser.add_argument("--thread_limit",     type=int,   default=DEFAULT_THREAD_LIMIT)
    parser.add_argument("--handle_limit",     type=int,   default=DEFAULT_HANDLE_LIMIT)
    parser.add_argument("--slope_threshold",  type=float, default=DEFAULT_SLOPE_THRESHOLD)
    args = parser.parse_args()

    print("=" * 60)
    print("  Performance Regression Check")
    print("=" * 60)

    if not os.path.exists(args.trend_csv):
        print(f"❌ FATAL: trend CSV not found: {args.trend_csv}")
        sys.exit(1)

    rows = load_trend_csv(args.trend_csv)
    if len(rows) < 2:
        print(f"❌ FATAL: not enough data points ({len(rows)}) — need at least 2")
        sys.exit(1)

    print(f"  Data points   : {len(rows)}")
    print(f"  Thresholds    : ctx_invol={args.ctx_invol_limit}/s  "
          f"mem={args.mem_limit}MB  threads={args.thread_limit}  handles={args.handle_limit}")
    print(f"  Slope limit   : {args.slope_threshold} per trend-point")
    print(f"  Note          : voluntary ctx switches monitored but not slope-checked")
    print("-" * 60)

    passed, info, failures = check(
        rows,
        ctx_invol_limit = args.ctx_invol_limit,
        mem_limit       = args.mem_limit,
        thread_limit    = args.thread_limit,
        handle_limit    = args.handle_limit,
        slope_threshold = args.slope_threshold,
    )

    for line in info:     print(line)
    for line in failures: print(line)

    print("=" * 60)
    if passed:
        print("  RESULT: ✅ PASS — no regression detected")
        print("=" * 60)
        sys.exit(0)
    else:
        print(f"  RESULT: ❌ FAIL — {len(failures)} issue(s) found")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()