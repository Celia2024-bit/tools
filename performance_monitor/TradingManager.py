import subprocess
import os
import sys
import psutil

class TradingManager:
    def __init__(self, project_root="../.."):
        self.project_root = os.path.abspath(project_root)
        self.python_exe = sys.executable
        # 确定操作系统对应的可执行文件名
        self.exe_name = "trading_system.exe" if os.name == 'nt' else "trading_system"
        self.exe_path = os.path.join(self.project_root, "output", self.exe_name)
        self.market_script = os.path.join(self.project_root, "src", "MarketFetch.py")

    def update_and_build(self):
        """Execute build steps and return clean English status."""
        try:
            # 1. Git Pull
            res_git = subprocess.run(["git", "pull"], cwd=self.project_root, capture_output=True, text=True)
            if res_git.returncode != 0:
                return False, f"GIT FAILED: {res_git.stderr}"

            # 2. Generate Code
            gen_script = os.path.join("utilLocal", "GenerateStrategy", "generate_code.py")
            res_gen = subprocess.run([self.python_exe, gen_script], cwd=self.project_root, capture_output=True, text=True)
            if res_gen.returncode != 0:
                return False, f"CODE GEN FAILED: {res_gen.stderr}"

            # 3. Make All
            res_make = subprocess.run(["make", "all"], cwd=self.project_root, capture_output=True, text=True)
            if res_make.returncode != 0:
                return False, f"MAKE FAILED: {res_make.stderr}"
            
            # 返回一个简短的成功标志
            return True, "BUILD SUCCESSFUL: System is up to date."
        except Exception as e:
            return False, f"SYSTEM ERROR: {str(e)}"

    def start_processes(self):
        """Start trading and market data processes."""
        try:
            # Start core processes
            p_exe = subprocess.Popen([self.exe_path], cwd=self.project_root)
            p_py = subprocess.Popen([self.python_exe, self.market_script], cwd=self.project_root)
            return True, f"SUCCESS: System started (EXE PID: {p_exe.pid})"
        except Exception as e:
            return False, f"ERROR: Failed to start processes: {str(e)}"

    def stop_processes(self):
        """Clean up all related processes."""
        targets = [self.exe_name, "MarketFetch.py"]
        count = 0
        for proc in psutil.process_iter(['name', 'cmdline']):
            try:
                # Match process name or Python script path
                if any(t in proc.info['name'] for t in targets) or \
                   any(any(t in arg for t in targets) for arg in (proc.info.get('cmdline') or [])):
                    proc.terminate()
                    count += 1
            except: continue
        return True, f"STOPPED: Terminated {count} related processes"