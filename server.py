# tools/server.py
import os
import difflib
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

# 只有这些后缀会被当成文本读给前端，其余（.exe/.o/...）一律跳过
TEXT_SUFFIXES = {
    ".h", ".hpp", ".hh", ".inl", ".c", ".cc", ".cxx", ".cpp",
    ".json", ".mmd", ".md", ".html", ".txt", ".j2", ".py", ".log",
}
# 单个文件内容上限，避免一次返回超大 JSON
MAX_FILE_BYTES = 256 * 1024
# 忽略的目录名
SKIP_DIRS = {"__pycache__", ".git", "node_modules"}

# 工具执行完成后要展示的“生成产物”目录
ARTIFACT_DIRS = {
    "sm": ["state_machine/out", "state_machine/output"],
}
# 工具会就地改写的源码目录：执行前后各拍一次快照，用于生成 diff
WATCH_DIRS = {
    "aspect": ["aspect_injector/test"],
    "interface": ["sync_interface/test"],
}


def _resolve_dirs(names):
    """把相对目录名解析为实际存在的绝对路径。"""
    dirs = []
    for name in names:
        path = (TOOLS_DIR / name).resolve()
        if path.is_dir():
            dirs.append(path)
    return dirs


def _iter_text_files(dirs):
    for base in dirs:
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            if any(part in SKIP_DIRS for part in path.relative_to(base).parts):
                continue
            if path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            yield path


def _rel(path):
    try:
        return path.relative_to(TOOLS_DIR).as_posix()
    except ValueError:
        return path.as_posix()


def _read_text(path):
    """读取文本文件，返回 (内容, 是否被截断)；不可读时返回 (None, False)。"""
    try:
        raw = path.read_bytes()
    except OSError:
        return None, False
    truncated = len(raw) > MAX_FILE_BYTES
    if truncated:
        raw = raw[:MAX_FILE_BYTES]
    try:
        return raw.decode("utf-8", errors="replace"), truncated
    except Exception:
        return None, False


def _snapshot(dirs):
    """记录目录下所有文本文件的内容，key 为相对 tools/ 的路径。"""
    snap = {}
    for path in _iter_text_files(dirs):
        content, _ = _read_text(path)
        if content is not None:
            snap[_rel(path)] = content
    return snap


def _unified(rel_path, before, after):
    diff = difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=f"a/{rel_path}",
        tofile=f"b/{rel_path}",
        n=3,
    )
    return "".join(diff)


def _build_diffs(before, after):
    """对比两次快照，生成 git diff 风格的结果。"""
    diffs = []
    for rel_path in sorted(set(before) | set(after)):
        old = before.get(rel_path)
        new = after.get(rel_path)
        if old == new:
            continue

        if old is None:
            status = "added"
            old = ""
        elif new is None:
            status = "deleted"
            new = ""
        else:
            status = "modified"

        text = _unified(rel_path, old, new)
        additions = sum(
            1 for line in text.splitlines()
            if line.startswith("+") and not line.startswith("+++")
        )
        deletions = sum(
            1 for line in text.splitlines()
            if line.startswith("-") and not line.startswith("---")
        )
        diffs.append({
            "path": rel_path,
            "name": rel_path.rsplit("/", 1)[-1],
            "status": status,
            "additions": additions,
            "deletions": deletions,
            "diff": text,
        })
    # 改动大的文件排前面
    diffs.sort(key=lambda d: -(d["additions"] + d["deletions"]))
    return diffs


def _collect_artifacts(dirs):
    """收集生成的文件内容，供前端折叠展示。"""
    artifacts = []
    for path in _iter_text_files(dirs):
        content, truncated = _read_text(path)
        if content is None:
            continue
        artifacts.append({
            "path": _rel(path),
            "name": path.name,
            "ext": path.suffix.lower().lstrip("."),
            "size": path.stat().st_size,
            "lines": content.count("\n") + 1,
            "truncated": truncated,
            "content": content,
        })
    artifacts.sort(key=lambda a: a["path"])
    return artifacts


def _tools_for(tool):
    """把 all 展开成具体工具列表。"""
    if tool == "all":
        return ["sm", "aspect", "interface"]
    return [tool]


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

        selected = _tools_for(tool)

        # 执行前快照（只针对会就地改写源码的工具）
        watch_dirs = _resolve_dirs(
            [d for name in selected for d in WATCH_DIRS.get(name, [])]
        )
        before = _snapshot(watch_dirs)

        cmd = ["python3", "test_runner.py", "--tool", tool]
        if file_path:
            cmd.extend(["--file", file_path])
        if src_file:
            cmd.extend(["--src", src_file])

        # 强制子进程用 UTF-8 输出，否则工具日志里的 emoji 在非 UTF-8 环境下会直接崩掉
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        res = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding="utf-8", errors="replace", env=env, cwd=TOOLS_DIR,
        )

        response_data = {
            "status": "success" if res.returncode == 0 else "error",
            "tool": tool,
            "returncode": res.returncode,
            "command": " ".join(cmd),
            "logs": res.stdout + "\n" + res.stderr,
        }

        # 执行后快照 -> git diff 风格的改动列表
        after = _snapshot(watch_dirs)
        diffs = _build_diffs(before, after)
        response_data["diffs"] = diffs
        response_data["diff_summary"] = {
            "files": len(diffs),
            "additions": sum(d["additions"] for d in diffs),
            "deletions": sum(d["deletions"] for d in diffs),
        }

        # 生成产物（状态机的 json/mmd/html/code 等），前端折叠后按需展开
        artifact_dirs = _resolve_dirs(
            [d for name in selected for d in ARTIFACT_DIRS.get(name, [])]
        )
        response_data["artifacts"] = _collect_artifacts(artifact_dirs)

        # 如果是状态机，直接把生成的 Mermaid 图解析返给前端
        mmd_file = TOOLS_DIR / "state_machine" / "out" / "state_machine.mmd"
        if tool in ["sm", "async", "all"] and mmd_file.exists():
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
