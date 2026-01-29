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
   
    """
    print(f"Starting monitor ")
    data_buffer = []
    
    # Ensure CSV has headers if it's a new file
    if not os.path.exists(raw_csv):
        with open(raw_csv, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(C.RAW_COLUMNS)

    process = None
    data_buffer = []

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

            # 1. CPU Usage 
            # interval=None means it calculates since the last call (non-blocking)
            cpu = process.cpu_percent(interval=None)

            # 2. Memory Usage (Private Bytes)
            mem_info = process.memory_info()
            mem_mb = mem_info.private / (1024 * 1024)

            # 3. Thread Count
            threads = process.num_threads()

            # 4. Handle Count (Windows Specific)
            if platform.system() == "Windows":
                handles = process.num_handles()
            else:
                handles = process.num_fds()

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Data Record
            record = [timestamp, cpu, threads, handles, round(mem_mb, 2)]

            # Write to CSV
            with open(raw_csv, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(record)
                f.flush() # Ensure data is written to disk

            #print(f"Logged: {record}")
            data_buffer.append({
                'mem': mem_mb,
                'threads': threads,
                'handles': handles
            })
            
            if len(data_buffer) >= trend_limit:
                avg_mem = sum(d['mem'] for d in data_buffer) / len(data_buffer)
                avg_thr = sum(d['threads'] for d in data_buffer) / len(data_buffer)
                avg_hnd = sum(d['handles'] for d in data_buffer) / len(data_buffer)
                
                f_tr_ex = os.path.exists(trend_csv)
                with open(trend_csv, 'a', newline='') as f:
                    writer = csv.writer(f)
                    if not f_tr_ex:
                        writer.writerow(C.TREND_COLUMNS)
                    writer.writerow([timestamp, round(avg_mem, 2), int(avg_thr), int(avg_hnd)])
                
               # print(f"Trend Logged: {len(data_buffer)} pts aggregated.")
                data_buffer = [] # 清空缓冲区
            
            # This interval determines our Real-time resolution
            time.sleep(interval_sec)

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            print("Process lost or access denied. Searching again...")
            process = None
            time.sleep(2)
        except Exception as e:
            print(f"Unexpected error: {e}")
            time.sleep(5)

# Example Usage:
# if __name__ == "__main__":
#     start_performance_monitor("your_product.exe", "raw_performance.csv", 60)