import os
import platform
import subprocess
import time
from TradingManager import TradingManager

def run_test():
    print("="*50)
    print(f"🚀 STARTING SYSTEM CROSS-PLATFORM TEST")
    print(f"OS: {platform.system()} | Release: {platform.release()}")
    print("="*50)

    # 1. 初始化 Manager (自动识别路径)
    # 假设测试时处于 tools/performance_monitor 目录，项目根目录在 ../..
    manager = TradingManager(project_root="../..")
    
    print(f"检测到项目根目录: {manager.project_root}")
    print(f"待测执行文件路径: {manager.exe_path}")
    print(f"Python 解释器: {manager.python_exe}")

    # 2. 测试编译环境与路径
    print("\n[STEP 1] Testing Path Accessibility...")
    if os.path.exists(manager.project_root):
        print("✅ Project root exists.")
    else:
        print("❌ Project root NOT FOUND!")
        return

    # 3. 测试 Update & Build (Git + CodeGen + Make)
    print("\n[STEP 2] Testing Update & Build (Make)...")
    success, msg = manager.update_and_build()
    if success:
        print(f"✅ Build Test Passed: {msg}")
    else:
        print(f"❌ Build Test Failed: {msg}")
        # 如果是 Windows 下报错 undefined reference，说明 Makefile 链接顺序有问题
        if "undefined reference" in msg:
            print("💡 TIP: Check if -lws2_32 is at the END of the linking command in Makefile.")

    # 4. 测试进程启动
    print("\n[STEP 3] Testing Process Execution...")
    # 确保 output 目录存在执行文件
    if not os.path.exists(manager.exe_path):
        print(f"❌ Aborting: Executable not found at {manager.exe_path}")
    else:
        start_ok, start_msg = manager.start_processes()
        if start_ok:
            print(f"✅ {start_msg}")
            print("Waiting 3 seconds to verify processes are running...")
            time.sleep(3)
            
            # 5. 测试进程清理
            print("\n[STEP 4] Testing Process Cleanup...")
            stop_ok, stop_msg = manager.stop_processes()
            if stop_ok:
                print(f"✅ {stop_msg}")
            else:
                print(f"❌ Cleanup Failed: {stop_msg}")
        else:
            print(f"❌ Process Start Failed: {start_msg}")

    print("\n" + "="*50)
    print("🏁 TEST COMPLETE")
    print("="*50)

if __name__ == "__main__":
    run_test()