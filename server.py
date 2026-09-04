# tools/server.py
import os
import re
import sys
import difflib
import traceback
from pathlib import Path
import subprocess
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # let the frontend call this API cross-origin

TOOLS_DIR = Path(__file__).resolve().parent

# Fallback API key (used only when the environment does not provide one)
if not os.environ.get("GEMINI_API_KEY"):
    os.environ["GEMINI_API_KEY"] = "your_real_GEMINI_API_KEY"

# Only these suffixes are read back as text for the frontend; anything else
# (.exe, .o, ...) is skipped.
TEXT_SUFFIXES = {
    ".h", ".hpp", ".hh", ".inl", ".c", ".cc", ".cxx", ".cpp",
    ".json", ".mmd", ".md", ".html", ".txt", ".j2", ".py", ".log",
}
# Per-file cap, so one big file cannot blow up the JSON response
MAX_FILE_BYTES = 256 * 1024
# Directory names never worth reporting
SKIP_DIRS = {"__pycache__", ".git", "node_modules"}

# The AI router picks the sub-tool inside the child process, so we snapshot every
# directory the tools may rewrite and diff whatever actually changed.
WATCH_DIRS = ["aspect_injector/test", "sync_interface/test"]

# Extra generated output to show, keyed by the tool name the router reports.
ARTIFACT_DIRS = {
    "state_machine": ["state_machine/out", "state_machine/output"],
}

# Presets used when a caller asks for a tool by name instead of sending a prompt.
DEFAULT_PROMPTS = {
    "sm": (
        "An order processing system that starts in Pending, moves to Paid on "
        "PaymentReceived, and then moves to Completed on OrderDelivered."
    ),
    "aspect": (
        "Add trace and validate logging to every function under "
        "aspect_injector/test/src, but skip AlphaEngine.cpp"
    ),
    "interface": (
        "Update interface sync_interface/test/include/IObserver_old.h: remove "
        "OnConnected, add OnError(int err_code), change OnData(int id, double "
        "timestamp). Sync all derived classes under sync_interface/test/src"
    ),
}

# Markers printed by nl_dev_tool.py (see its "progress reporting" section)
TOOL_MARKER = re.compile(r"AI selected tool:\s*([a-z_]+)")
ARTIFACT_MARKER = re.compile(r"artifact \[[^\]]*\]:\s*(.+?)\s*$", re.MULTILINE)


def _resolve_dirs(names):
    """Turn relative directory names into existing absolute paths."""
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
    """Read a text file and return (content, truncated); (None, False) if unreadable."""
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
    """Record the content of every text file below dirs, keyed by tools-relative path."""
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
    """Compare two snapshots and produce git-diff style entries."""
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
    # Biggest changes first
    diffs.sort(key=lambda d: -(d["additions"] + d["deletions"]))
    return diffs


def _artifact_entry(path):
    """Describe one generated file for the frontend, or None if it is not readable text."""
    if path.suffix.lower() not in TEXT_SUFFIXES or not path.is_file():
        return None
    content, truncated = _read_text(path)
    if content is None:
        return None
    return {
        "path": _rel(path),
        "name": path.name,
        "ext": path.suffix.lower().lstrip("."),
        "size": path.stat().st_size,
        "lines": content.count("\n") + 1,
        "truncated": truncated,
        "content": content,
    }


def _collect_artifacts(dirs, extra_files=()):
    """Collect generated file contents so the frontend can show them collapsed."""
    paths = list(_iter_text_files(dirs))
    paths.extend(extra_files)

    artifacts = []
    seen = set()
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        entry = _artifact_entry(resolved)
        if entry:
            artifacts.append(entry)

    artifacts.sort(key=lambda a: a["path"])
    return artifacts


def _artifact_paths_from_logs(logs):
    """Pull the paths nl_dev_tool.py reported as artifacts out of its stdout."""
    paths = []
    for raw in ARTIFACT_MARKER.findall(logs):
        path = (TOOLS_DIR / raw).resolve() if not Path(raw).is_absolute() else Path(raw).resolve()
        if path.is_file():
            paths.append(path)
    return paths


@app.route('/exec', methods=['GET', 'POST'])
def exec_tool():
    if request.method == 'GET':
        return jsonify({
            "status": "online",
            "message": "C++ Tools Service API is running. Send a POST request to execute tools."
        })

    try:
        payload = request.json or {}
        # The natural-language request drives everything; `tool` only selects a preset.
        prompt = (payload.get('prompt') or payload.get('description') or '').strip()
        tool = payload.get('tool')
        if not prompt:
            prompt = DEFAULT_PROMPTS.get(tool, '').strip()
        if not prompt:
            return jsonify({
                "status": "error",
                "message": "Send a natural-language 'prompt', or a 'tool' in "
                           f"{sorted(DEFAULT_PROMPTS)} to use its preset prompt.",
            }), 400

        # Snapshot before the run, so we can diff whatever the tools rewrite in place
        watch_dirs = _resolve_dirs(WATCH_DIRS)
        before = _snapshot(watch_dirs)

        # Run with the same interpreter as this server, not a bare "python3" that
        # could resolve to a different install
        cmd = [sys.executable, "nl_dev_tool.py", prompt]
        if payload.get('old'):
            cmd.extend(["--old", payload['old']])
        if payload.get('src'):
            cmd.extend(["--src", payload['src']])
        if payload.get('output'):
            cmd.extend(["-o", payload['output']])
        if payload.get('no_run'):
            cmd.append("--no-run")

        # Force UTF-8 in the child, otherwise non-UTF-8 consoles kill the whole run
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        res = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding="utf-8", errors="replace", env=env, cwd=TOOLS_DIR,
        )
        logs = res.stdout + "\n" + res.stderr

        # Which tool did the AI router pick?
        match = TOOL_MARKER.search(logs)
        tool_detected = match.group(1) if match else None

        response_data = {
            "status": "success" if res.returncode == 0 else "error",
            "prompt": prompt,
            "tool": tool,
            "tool_detected": tool_detected,
            "returncode": res.returncode,
            "command": " ".join([Path(cmd[0]).name] + cmd[1:]),
            "logs": logs,
        }

        # Snapshot after the run -> git-diff style change list
        after = _snapshot(watch_dirs)
        diffs = _build_diffs(before, after)
        response_data["diffs"] = diffs
        response_data["diff_summary"] = {
            "files": len(diffs),
            "additions": sum(d["additions"] for d in diffs),
            "deletions": sum(d["deletions"] for d in diffs),
        }

        # Generated output, collapsed in the frontend until the user expands it
        artifact_dirs = _resolve_dirs(ARTIFACT_DIRS.get(tool_detected, []))
        reported = _artifact_paths_from_logs(logs)
        response_data["artifacts"] = _collect_artifacts(artifact_dirs, reported)

        # For state machines, hand the generated Mermaid diagram straight to the
        # frontend. The pipeline names it after the spec, so resolve it from the spec
        # this run reported - the out/ directory can still hold older diagrams.
        if tool_detected == "state_machine":
            out_dir = TOOLS_DIR / "state_machine" / "out"
            candidates = [out_dir / f"{p.stem}.mmd" for p in reported
                          if p.suffix.lower() == ".md"]
            candidates.append(out_dir / "state_machine.mmd")
            for mmd_file in candidates:
                if mmd_file.exists():
                    response_data["mermaid"] = mmd_file.read_text(encoding="utf-8")
                    break

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
    # Bind 0.0.0.0 so the container port mapping works
    app.run(host='0.0.0.0', port=8000)
