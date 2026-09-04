# tools/server.py
import os
import traceback
from pathlib import Path
import subprocess
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # 允许前端跨域直接请求

TOOLS_DIR = Path(__file__).resolve().parent

# 保底 API Key（如果环境变量中没有设置）
if not os.environ.get("GEMINI_API_KEY"):
    os.environ["GEMINI_API_KEY"] = "你的真实_GEMINI_API_KEY"

@app.route('/exec', methods=['GET', 'POST'])
def exec_tool():
    if request.method == 'GET':
        return jsonify({
            "status": "online",
            "message": "C++ Tools Service API is running. Send a POST request to execute tools."
        })

    try:
        payload = request.json or {}
        tool = payload.get('tool', 'sm')
        file_path = payload.get('file')
        src_file = payload.get('src')
        
        cmd = ["python3", "test_runner.py", "--tool", tool]
        if file_path:
            cmd.extend(["--file", file_path])
        if src_file:
            cmd.extend(["--src", src_file])
        
        res = subprocess.run(cmd, capture_output=True, text=True, cwd=TOOLS_DIR)
        
        response_data = {
            "status": "success" if res.returncode == 0 else "error",
            "logs": res.stdout + "\n" + res.stderr
        }
        
        # 如果是状态机，直接把生成的 Mermaid 图解析返给前端
        mmd_file = TOOLS_DIR / "state_machine" / "out" / "state_machine.mmd"
        if tool in ["sm", "async"] and mmd_file.exists():
            with open(mmd_file, "r", encoding="utf-8") as f:
                response_data["mermaid"] = f.read()

        return jsonify(response_data)

    except Exception as e:
        err_msg = traceback.format_exc()
        print(f"Error executing tool:\n{err_msg}")
        return jsonify({
            "status": "error",
            "message": str(e),
            "traceback": err_msg
        }), 500

if __name__ == '__main__':
    # 绑定 0.0.0.0 以便容器外部接入
    app.run(host='0.0.0.0', port=8000)