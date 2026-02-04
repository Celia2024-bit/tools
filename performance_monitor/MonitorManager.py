import os
import shutil
import subprocess
from datetime import datetime
import constants as C

class MonitorManager:
    def __init__(self):
        self.process = None
        self.is_running = False
        self.current_config = {
            "exe": C.DEFAULT_EXE,
            "interval": C.DEFAULT_INTERVAL,
            "limit": C.DEFAULT_TREND_LIMIT
        }

    def backup_and_clean(self):
        """在启动前备份并删除旧的 CSV 文件"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        for file in [C.DEFAULT_RAW_FILE, C.DEFAULT_TREND_FILE]:
            if os.path.exists(file):
                backup_name = f"backup_{timestamp}_{file}"
                try:
                    shutil.copy(file, backup_name)
                    os.remove(file)
                    print(f"DEBUG: Backed up {file} to {backup_name}")
                except Exception as e:
                    print(f"DEBUG: Backup error: {e}")

    def start(self):
        """启动监控子进程"""
        if self.is_running:
            return False, "Monitor is already running."
        
        self.backup_and_clean()
        
        cmd = [
            "python", "run_monitor.py",
            "--exe", self.current_config["exe"],
            "--interval", str(self.current_config["interval"]),
            "--limit", str(self.current_config["limit"]),
            "--raw", C.DEFAULT_RAW_FILE,
            "--trend", C.DEFAULT_TREND_FILE
        ]
        
        try:
            self.process = subprocess.Popen(
                cmd, 
                creationflags=subprocess.CREATE_NEW_CONSOLE  # 仅限 Windows
            )
            self.is_running = True
            return True, f"Monitor started (PID: {self.process.pid})"
        except Exception as e:
            return False, f"Failed to launch monitor: {str(e)}"

    def stop(self):
        """停止监控进程"""
        if not self.is_running or not self.process:
            return False, "Monitor is not running."
        
        try:
            # 强制杀死进程树
            subprocess.run(['taskkill', '/F', '/T', '/PID', str(self.process.pid)], capture_output=True)
            self.process = None
            self.is_running = False
            return True, "Monitor stopped."
        except Exception as e:
            return False, f"Error while stopping: {str(e)}"

    def configure(self, new_config):
        """更新配置"""
        if self.is_running:
            return False, "Cannot reconfigure while running!"
        self.current_config.update(new_config)
        return True, f"Config updated: {self.current_config['exe']}"