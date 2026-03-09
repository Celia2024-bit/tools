import psutil
import time
import csv
import os
from datetime import datetime
import constants as C
import platform

def get_process_by_name(process_name):
    """Find a running process by its executable name."""
    for proc in psutil.process_iter(['name']):
        try:
            if proc.info['name'].lower() == process_name.lower():
                return proc
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return None

def start_performance_monitor(exe_name, raw_csv, trend_csv, interval_sec=1, trend_limit=20, target_pid=None):
    """
    Monitors a specific process and logs metrics to a CSV file.
    Tracks: context switches (voluntary + involuntary), memory, threads, handles.

    Context switch rate (per second) is more meaningful than CPU% for
    diagnosing thread scheduling pressure and contention.
    """
    print(f"Starting monitor")
    
    # Ensure CSV has headers if it's a new file
    if not os.path.exists(raw_csv):
        with open(raw_csv, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(C.RAW_COLUMNS)

    process = None
    data_buffer = []

    # Track previous ctx switch counts to compute per-second delta
    prev_ctx_vol  = None
    prev_ctx_invol = None
    prev_time     = None

    if target_pid:
        try:
            process = psutil.Process(target_pid)
        except psutil.NoSuchProcess:
            print(f"❌ PID {target_pid} not found.")
            return

    while True:
        try:
            # Re-check for process if it wasn't found or was closed
            if process is None or not process.is_running():
                if target_pid:
                    print("Target process finished. Stopping monitor.")
                    break
                process = get_process_by_name(exe_name)
                if process is None:
                    print(f"Waiting for {exe_name} to start...")
                    time.sleep(5)
                    continue
                else:
                    print(f"Process {exe_name} found (PID: {process.pid})")
                    # Reset ctx baseline when process is (re)found
                    prev_ctx_vol   = None
                    prev_ctx_invol = None
                    prev_time      = None

            # ── 1. Context Switches (delta per second) ───────────────────────
            ctx        = process.num_ctx_switches()
            now        = time.time()

            if prev_ctx_vol is None:
                # First sample — just capture baseline, record 0
                ctx_vol_rate   = 0
                ctx_invol_rate = 0
            else:
                elapsed        = now - prev_time if (now - prev_time) > 0 else 1
                ctx_vol_rate   = (ctx.voluntary   - prev_ctx_vol)   / elapsed
                ctx_invol_rate = (ctx.involuntary  - prev_ctx_invol) / elapsed

            prev_ctx_vol   = ctx.voluntary
            prev_ctx_invol = ctx.involuntary
            prev_time      = now

            # ── 2. Memory (RSS) ───────────────────────────────────────────────
            mem_mb = process.memory_info().rss / (1024 * 1024)

            # ── 3. Thread Count ───────────────────────────────────────────────
            threads = process.num_threads()

            # ── 4. Handle / FD Count ──────────────────────────────────────────
            if platform.system() == "Windows":
                handles = process.num_handles()
            else:
                handles = process.num_fds()

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # RAW record: timestamp, ctx_vol/s, ctx_invol/s, threads, handles, memory_mb
            record = [
                timestamp,
                round(ctx_vol_rate,   1),
                round(ctx_invol_rate, 1),
                threads,
                handles,
                round(mem_mb, 2)
            ]

            # Write raw CSV
            with open(raw_csv, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(record)
                f.flush()

            data_buffer.append({
                'ctx_vol':   ctx_vol_rate,
                'ctx_invol': ctx_invol_rate,
                'mem':       mem_mb,
                'threads':   threads,
                'handles':   handles,
            })

            # ── Aggregate into trend point ────────────────────────────────────
            if len(data_buffer) >= trend_limit:
                avg_ctx_vol   = sum(d['ctx_vol']   for d in data_buffer) / len(data_buffer)
                avg_ctx_invol = sum(d['ctx_invol'] for d in data_buffer) / len(data_buffer)
                avg_mem       = sum(d['mem']        for d in data_buffer) / len(data_buffer)
                avg_thr       = sum(d['threads']    for d in data_buffer) / len(data_buffer)
                avg_hnd       = sum(d['handles']    for d in data_buffer) / len(data_buffer)

                f_tr_ex = os.path.exists(trend_csv)
                with open(trend_csv, 'a', newline='') as f:
                    writer = csv.writer(f)
                    if not f_tr_ex:
                        writer.writerow(C.TREND_COLUMNS)
                    writer.writerow([
                        timestamp,
                        round(avg_ctx_vol,   1),
                        round(avg_ctx_invol, 1),
                        round(avg_mem,       2),
                        int(avg_thr),
                        int(avg_hnd)
                    ])

                data_buffer = []

            time.sleep(interval_sec)

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            print("Process lost or access denied. Searching again...")
            process        = None
            prev_ctx_vol   = None
            prev_ctx_invol = None
            prev_time      = None
            time.sleep(2)
        except Exception as e:
            print(f"Unexpected error: {e}")
            time.sleep(5)