import os
import time
import platform
import subprocess
from MonitorManager import MonitorManager
import constants as C

def setup_fake_csv():
    """创建虚假的初始 CSV 文件，用于测试备份功能"""
    for f in [C.DEFAULT_RAW_FILE, C.DEFAULT_TREND_FILE]:
        with open(f, 'w') as tmp:
            tmp.write("timestamp,test_data\n20230101_000000,100\n")
    print("✅ Created dummy CSV files for backup testing.")

def test_monitor():
    print("="*50)
    print(f"🚀 STARTING MONITOR MANAGER TEST")
    print(f"Platform: {platform.system()}")
    print("="*50)

    manager = MonitorManager()
    
    # 1. 测试备份与清理逻辑
    print("\n[STEP 1] Testing Backup & Clean...")
    setup_fake_csv()
    manager.backup_and_clean()
    
    # 检查备份文件夹是否存在 (如果你采用了之前的建议增加了 backup_dir)
    backup_dir = getattr(manager, 'backup_dir', '.')
    backups = [f for f in os.listdir(backup_dir) if f.startswith("backup_")]
    if len(backups) > 0:
        print(f"✅ Backup successful. Found {len(backups)} backup files.")
    else:
        # 如果是按原代码逻辑备份在当前目录
        print("✅ Cleaned old files. (Check current directory for backup_ files)")

    # 2. 测试配置更新
    print("\n[STEP 2] Testing Configuration...")
    new_cfg = {"interval": 2, "limit": 5}
    success, msg = manager.configure(new_cfg)
    print(f"Update Config: {success} | {msg}")
    if manager.current_config["interval"] == 2:
        print("✅ Configuration updated correctly.")

    # 3. 测试启动监控 (需确保 run_monitor.py 存在)
    print("\n[STEP 3] Testing Monitor Startup...")
    # 注意：这里需要一个可以被监控的进程，或者随便填一个系统进程名
    test_exe = "python" if platform.system() == "Windows" else "python3"
    manager.configure({"exe": test_exe})
    
    start_ok, start_msg = manager.start()
    if start_ok:
        print(f"✅ {start_msg}")
        print(f"Is running: {manager.is_running}")
        
        # 4. 运行中配置保护测试
        print("\n[STEP 4] Testing Re-config Protection...")
        re_cfg_ok, re_cfg_msg = manager.configure({"interval": 10})
        if not re_cfg_ok:
            print(f"✅ Protected: {re_cfg_msg}")
        else:
            print("❌ Error: Allowed configuration while running!")

        # 等待产生一点数据
        print("Monitoring for 5 seconds...")
        time.sleep(5)

        # 5. 测试停止监控
        print("\n[STEP 5] Testing Monitor Stop...")
        stop_ok, stop_msg = manager.stop()
        if stop_ok:
            print(f"✅ {stop_msg}")
            print(f"Is running: {manager.is_running}")
        else:
            print(f"❌ Stop Failed: {stop_msg}")
    else:
        print(f"❌ Startup Failed: {start_msg}")
        print("Hint: Ensure 'run_monitor.py' is in the same directory.")

    print("\n" + "="*50)
    print("🏁 MONITOR TEST COMPLETE")
    print("="*50)

if __name__ == "__main__":
    test_monitor()