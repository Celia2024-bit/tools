import subprocess
import os
import sys
import psutil

class TradingManager:
    def __init__(self, project_root="../.."):
        if os.name == 'nt':
            self.project_root = os.path.abspath(project_root)
            self.python_exe = sys.executable
            # 确定操作系统对应的可执行文件名
            self.exe_name = "trading_system.exe"
        else:
            self.project_root = "/app/TradeSystem"
            self.python_exe = "python3"
            # 确定操作系统对应的可执行文件名
            self.exe_name = "trading_system"
        self.exe_path = os.path.join(self.project_root, "output", self.exe_name)
        self.market_script = os.path.join(self.project_root, "src", "MarketFetch.py")

    def update_and_build(self):
        """通用构建函数：支持 Windows 路径注入和 Linux 标准环境"""
        try:
            # 1. 获取当前环境变量副本
            my_env = os.environ.copy()
            
            # --- 关键：仅在 Windows (nt) 下注入 MinGW 路径 ---
            if os.name == 'nt': 
                # 这里填入你电脑上真实的 MinGW bin 目录
                mingw_path = r"C:\ProgramData\mingw64\mingw64\bin" 
                if mingw_path not in my_env["PATH"]:
                    my_env["PATH"] = mingw_path + os.pathsep + my_env["PATH"]
            # ----------------------------------------------

            # 2. Git Pull (带上环境变量)
            subprocess.run(["git", "checkout", "--", "."], cwd=self.project_root, env=my_env)
            # 2. 清理子模块 (foreach 对每个子模块运行 checkout)
            subprocess.run(["git", "submodule", "foreach", "--recursive", "git", "checkout", "--", "."], 
                           cwd=self.project_root, env=my_env)
            # 3. 同步子模块状态
            subprocess.run(["git", "submodule", "update", "--init", "--recursive"], 
                           cwd=self.project_root, env=my_env)
                           
            res_git = subprocess.run(["git", "pull"], cwd=self.project_root, 
                                     capture_output=True, text=True, env=my_env)
            if res_git.returncode != 0:
                return False, f"GIT FAILED: {res_git.stderr}"
                
            res_git = subprocess.run(["git", "submodule", "update"], cwd=self.project_root, 
                                     capture_output=True, text=True, env=my_env)
            if res_git.returncode != 0:
                return False, f"GIT FAILED: {res_git.stderr}"

            # 3. Generate Code
            gen_script = os.path.join("utilLocal", "GenerateStrategy", "generate_code.py")
            res_gen = subprocess.run([self.python_exe, gen_script], cwd=self.project_root, 
                                     capture_output=True, text=True, env=my_env)
            if res_gen.returncode != 0:
                return False, f"CODE GEN FAILED: {res_gen.stderr}"

            # 4. Make All
            # 在 Windows 下建议先 clean，防止旧的 .o 文件干扰链接 [cite: 8, 9]
            subprocess.run(["make", "clean"], cwd=self.project_root, env=my_env)
            
            res_make = subprocess.run(["make", "all"], cwd=self.project_root, 
                                      capture_output=True, text=True, env=my_env)
            if res_make.returncode != 0:
                return False, f"MAKE FAILED: {res_make.stderr}"
            
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