import os
import shutil
import subprocess
from datetime import datetime
import constants as C

class MonitorManager:
    def __init__(self):
        self.process = None
        self.is_running = False
        self.backup_dir = "backups"  # Folder to store old logs
        self.max_backups = 5         # Keep only the last 5 sets of logs
        self.current_config = {
            "exe": C.DEFAULT_EXE,
            "interval": C.DEFAULT_INTERVAL,
            "limit": C.DEFAULT_TREND_LIMIT
        }

    def backup_and_clean(self):
        """Backs up old CSV files to a subfolder and keeps only the most recent ones."""
        if not os.path.exists(self.backup_dir):
            os.makedirs(self.backup_dir)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 1. Move current files to backup folder
        for file in [C.DEFAULT_RAW_FILE, C.DEFAULT_TREND_FILE]:
            if os.path.exists(file):
                backup_name = os.path.join(self.backup_dir, f"backup_{timestamp}_{file}")
                try:
                    shutil.move(file, backup_name) # Move instead of copy+remove
                    print(f"DEBUG: Moved {file} to {backup_name}")
                except Exception as e:
                    print(f"DEBUG: Backup error: {e}")

        # 2. Cleanup old backups (Keep only the latest N)
        try:
            # List all files in backup dir sorted by creation time
            all_backups = sorted(
                [os.path.join(self.backup_dir, f) for f in os.listdir(self.backup_dir)],
                key=os.path.getctime
            )
            
            # If we have more than (max_backups * 2 files), delete the oldest ones
            while len(all_backups) > (self.max_backups * 2):
                oldest_file = all_backups.pop(0)
                os.remove(oldest_file)
                print(f"DEBUG: Deleted old backup: {oldest_file}")
        except Exception as e:
            print(f"DEBUG: Cleanup error: {e}")

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