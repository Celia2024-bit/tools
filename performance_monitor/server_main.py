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
from MonitorManager import MonitorManager
from TradingManager import TradingManager

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

# 实例化管理器
manager_manager = MonitorManager()
trading_manager = TradingManager()

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
                    success, text = manager_manager.start()
                    await websocket.send_json({"type": "status_log", "success": success, "message": text})
                    # 重置读取位置，因为文件被删除了
                    last_raw_idx = 0
                    last_trend_idx = 0

                elif m_type == "stop":
                    success, text = manager_manager.stop()
                    await websocket.send_json({"type": "status_log", "success": success, "message": text})
                
                elif m_type == "configure":
                    success, text = manager_manager.configure(m_data)
                    await websocket.send_json({"type": "status_log", "success": success, "message": text})
                                
                elif m_type == "trade_update":
                    success, text = trading_manager.update_and_build()
                    await websocket.send_json({"type": "status_log", "success": success, "message": text})
                    
                elif m_type == "trade_start":
                    success, text = trading_manager.start_processes()
                    await websocket.send_json({"type": "status_log", "success": success, "message": text})

                elif m_type == "trade_stop":
                    success, text = trading_manager.stop_processes()
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