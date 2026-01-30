import asyncio
import os
import json
import subprocess
import shutil
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import psutil

# 导入你定义的常量
import constants as C

app = FastAPI()

# 添加以下 CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境建议指定 ["http://localhost:7070"]
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有请求方法 (GET, POST 等)
    allow_headers=["*"],  # 允许所有请求头
)

# --- 监控管理器：负责控制 run_monitor.py ---
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
        if self.is_running:
            return False, "Monitor is already running. Please stop it first."
        
        # 1. 备份并清理旧文件，确保新运行数据纯净
        self.backup_and_clean()
        
        # 2. 构造命令行参数
        cmd = [
            "python", "run_monitor.py",
            "--exe", self.current_config["exe"],
            "--interval", str(self.current_config["interval"]),
            "--limit", str(self.current_config["limit"]),
            "--raw", C.DEFAULT_RAW_FILE,
            "--trend", C.DEFAULT_TREND_FILE
        ]
        
        # 3. 启动子进程 (在 Windows 下弹出新窗口显示监控日志)
        try:
            self.process = subprocess.Popen(
                cmd, 
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )
            self.is_running = True
            return True, f"Monitor started for {self.current_config['exe']} (PID: {self.process.pid})"
        except Exception as e:
            return False, f"Failed to launch monitor: {str(e)}"

    def stop(self):
        if not self.is_running or not self.process:
            return False, "Monitor is not currently running."
        
        try:
            # 强制杀死进程树 (/T)
            subprocess.run(['taskkill', '/F', '/T', '/PID', str(self.process.pid)], capture_output=True)
            self.process = None
            self.is_running = False
            return True, "Monitor stopped. Process killed and data saved."
        except Exception as e:
            return False, f"Error while stopping: {str(e)}"

    def configure(self, new_config):
        if self.is_running:
            return False, "Cannot reconfigure while running! Please stop the monitor first."
        
        # 更新配置字典
        self.current_config.update(new_config)
        return True, f"Configuration updated: {self.current_config['exe']} @ {self.current_config['interval']}s"

# 实例化管理器
manager = MonitorManager()

@app.get("/processes")
async def get_processes():
    # Get all unique running .exe names, sorted alphabetically
    processes = sorted(list(set([p.info['name'] for p in psutil.process_iter(['name']) if p.info['name']])))
    return {"processes": processes}

# --- WebSocket 逻辑 ---
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("WebSocket client connected.")
    
    # 记录每个连接的文件读取位置，防止重复发送
    last_raw_idx = 0
    last_trend_idx = 0

    try:
        while True:
            # 1. 处理前端指令 (使用 wait_for 防止阻塞)
            try:
                raw_msg = await asyncio.wait_for(websocket.receive_text(), timeout=0.1)
                msg = json.loads(raw_msg)
                m_type = msg.get("type")
                m_data = msg.get("data", {})

                if m_type == "start":
                    success, text = manager.start()
                    await websocket.send_json({"type": "status_log", "success": success, "message": text})
                    # 重置读取位置，因为文件被删除了
                    last_raw_idx = 0
                    last_trend_idx = 0

                elif m_type == "stop":
                    success, text = manager.stop()
                    await websocket.send_json({"type": "status_log", "success": success, "message": text})

                elif m_type == "configure":
                    success, text = manager.configure(m_data)
                    await websocket.send_json({"type": "status_log", "success": success, "message": text})

            except asyncio.TimeoutError:
                pass # 正常超时，继续往下跑文件读取逻辑

            # 2. 增量读取 RAW CSV 并推送
            if os.path.exists(C.DEFAULT_RAW_FILE):
                with open(C.DEFAULT_RAW_FILE, 'r', encoding='utf-8', errors='ignore') as f:
                    all_lines = f.readlines()
                    if len(all_lines) > last_raw_idx:
                        for line in all_lines[last_raw_idx:]:
                            if not line.strip() or "timestamp" in line: continue
                            vals = line.strip().split(',')
                            if len(vals) >= 5:
                                await websocket.send_json({
                                    "type": "realtime",
                                    "data": dict(zip(C.RAW_COLUMNS, vals))
                                })
                        last_raw_idx = len(all_lines)

            # 3. 增量读取 TREND CSV 并推送
            if os.path.exists(C.DEFAULT_TREND_FILE):
                with open(C.DEFAULT_TREND_FILE, 'r', encoding='utf-8', errors='ignore') as f:
                    all_lines = f.readlines()
                    if len(all_lines) > last_trend_idx:
                        for line in all_lines[last_trend_idx:]:
                            if not line.strip() or "timestamp" in line: continue
                            vals = line.strip().split(',')
                            if len(vals) >= 4:
                                await websocket.send_json({
                                    "type": "trend_push",
                                    "data": dict(zip(C.TREND_COLUMNS, vals))
                                })
                        last_trend_idx = len(all_lines)

            await asyncio.sleep(0.5)

    except WebSocketDisconnect:
        print("Client disconnected.")
    except Exception as e:
        print(f"Server Internal Error: {e}")

if __name__ == "__main__":
    # 启动时确保旧进程清理干净 (可选)
    uvicorn.run(app, host="127.0.0.1", port=8080)