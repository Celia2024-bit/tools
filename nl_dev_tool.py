import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from google.genai import errors
import time

# 确保脚本所在目录及各子工具目录优先在 Python 搜索路径中
TOOLS_DIR = Path(__file__).resolve().parent
STATE_MACHINE_DIR = TOOLS_DIR / "state_machine"
SYNC_INTERFACE_DIR = TOOLS_DIR / "sync_interface"
ASPECT_INJECTOR_DIR = TOOLS_DIR / "aspect_injector"

for path in [TOOLS_DIR, STATE_MACHINE_DIR, SYNC_INTERFACE_DIR, ASPECT_INJECTOR_DIR]:
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from google import genai
from google.genai import types

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

ROUTER_SYSTEM_PROMPT = """You are an intent router for C++ automation tools.
Analyze the user's natural language request and determine which tool to use.

Tools available:
1. "state_machine": User wants to create or update a state machine.
2. "interface_sync": User wants to modify an existing C++ interface header and sync derived classes.
3. "aspect_injector": User wants to inject or remove aspects.

Rules:
- Output JSON ONLY in this format:
{
  "tool": "state_machine" | "interface_sync" | "aspect_injector",
  "old_header": "<path to old header if mentioned in description, else null>",
  "src_dir": "<source directory for derived classes if mentioned, else null>"
}
- Do not wrap in markdown code fences.
"""


def route_intent(description: str) -> dict:
    """Use Gemini to quickly determine which sub-tool to invoke, with auto-retry for 429 quota errors."""
    max_retries = 3
    retry_delay = 5  # 秒

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model="gemini-3.6-flash",
                contents=description,
                config=types.GenerateContentConfig(
                    system_instruction=ROUTER_SYSTEM_PROMPT,
                    max_output_tokens=200,
                    thinking_config=types.ThinkingConfig(
                        thinking_level=types.ThinkingLevel.MINIMAL
                    ),
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                ),
            )
            text = response.text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            return json.loads(text.strip())

        except errors.ClientError as e:
            if e.code == 429 and attempt < max_retries - 1:
                print(f"⚠️ Gemini API rate limit hit (429). Retrying in {retry_delay} seconds... (Attempt {attempt + 1}/{max_retries})")
                time.sleep(retry_delay)
                retry_delay *= 2  # 退避时间翻倍
            else:
                raise e


def resolve_path(path_str: str, default_path: Path = None) -> Path:
    """
    通用路径解析工具：无论输入是相对路径还是绝对路径，均解析为物理绝对路径。
    python nl_dev_tool.py "Add trace and validate logging to every function under aspect_injector/test/src/hot, but skip AlphaEngine.cpp"
    """
    if not path_str:
        return default_path.resolve() if default_path else None

    p = Path(path_str)
    # 如果是相对路径，基于当前终端执行目录（Path.cwd()）转换为绝对路径
    if not p.is_absolute():
        p = (Path.cwd() / p).resolve()
    else:
        p = p.resolve()

    # 如果解析后的路径不存在，且有默认路径，则降级使用默认路径
    if not p.exists() and default_path and default_path.exists():
        return default_path.resolve()

    return p


def handle_state_machine(description: str, output: str, should_run: bool):
    """处理状态机生成与编译运行流程
    python  nl_dev_tool.py "An order processing system that starts in Pending, moves to Paid on PaymentReceived, and then moves to Completed on OrderDelivered."
    """
    from nl_to_state_machine import nl_to_state_machine_md, run_pipeline

    default_out = STATE_MACHINE_DIR / "test" / "state_machine.md"
    out_path = resolve_path(output, default_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    md_content = nl_to_state_machine_md(description)
    out_path.write_text(md_content, encoding="utf-8")
    print(f"📄 State machine spec written to: {out_path}")

    if should_run:
        run_pipeline(out_path, cwd=STATE_MACHINE_DIR)


def handle_interface_sync(description: str, intent: dict, args, should_run: bool):
    """处理接口变更与派生类同步流程
    python nl_dev_tool.py "Update interface sync_interface/test/include/IObserver_old.h: remove OnConnected ,add OnError(int err_code) ,change Ondate(int id, double timestamp). Sync all derived classes under sync_interface/test/src""""
    from nl_to_new_interface import generate_new_header

    # 1. 提取路径字符串（优先取 AI 提取，其次取 CLI 参数）
    raw_old = intent.get("old_header") or args.old
    raw_src = intent.get("src_dir") or args.src

    # 2. 转换为绝对路径（兼容绝对路径与基于终端位置的相对路径）
    default_src = SYNC_INTERFACE_DIR / "test" / "src"
    src_dir = resolve_path(raw_src, default_src)

    if not raw_old:
        print("❌ Error: Interface sync requires old header path. Mention it in description or use `--old <path>`.", file=sys.stderr)
        sys.exit(1)

    old_path = resolve_path(raw_old)
    if not old_path or not old_path.is_file():
        print(f"❌ Error: Old header file not found at: {old_path}", file=sys.stderr)
        sys.exit(1)

    # 3. 生成新头文件
    old_text = old_path.read_text(encoding="utf-8")
    new_text = generate_new_header(old_text, description)

    if args.output:
        new_path = resolve_path(args.output)
    else:
        stem = old_path.stem
        new_stem = stem[:-4] if stem.endswith("_old") else f"{stem}_new"
        new_path = old_path.with_name(f"{new_stem}{old_path.suffix}")

    new_path.write_text(new_text, encoding="utf-8")
    print(f"📄 Updated header written to: {new_path}")

    # 4. 执行底层同步脚本（全部使用绝对路径传参）
    if should_run:
        abs_old = str(old_path)
        abs_new = str(new_path)
        abs_src = str(src_dir)

        print(f"\nRunning interface_sync.py --old {abs_old} --new {abs_new} --src {abs_src}...\n")
        subprocess.run([
            sys.executable, str(SYNC_INTERFACE_DIR / "interface_sync.py"),
            "--old", abs_old,
            "--new", abs_new,
            "--src", abs_src
        ], check=True, cwd=SYNC_INTERFACE_DIR)


def handle_aspect_injector(description: str, output: str, should_run: bool):
    """处理切面配置生成与注入流程"""
    from nl_to_aspect_config import nl_to_config_json

    default_out = ASPECT_INJECTOR_DIR / "config.json"
    out_path = resolve_path(output, default_out)

    config_str = nl_to_config_json(description)
    
    # 解析并修正 config 中的 directory 路径
    try:
        config_data = json.loads(config_str)
        
        # 递归清洗/修整目录路径
        def clean_dir(target_list):
            for item in target_list:
                d = item.get("directory", "")
                if d:
                    # 如果包含了 aspect_injector/ 前缀，自动剥离掉
                    p = Path(d)
                    parts = p.parts
                    if len(parts) > 0 and parts[0] == "aspect_injector":
                        d = str(Path(*parts[1:]))
                    
                    # 转换为针对 ASPECT_INJECTOR_DIR 的绝对路径，彻底避免 cwd 错位
                    abs_dir = (ASPECT_INJECTOR_DIR / d).resolve()
                    if abs_dir.exists():
                        item["directory"] = str(abs_dir)
                    else:
                        item["directory"] = d

        if "inject" in config_data:
            clean_dir(config_data["inject"])
        if "exclude" in config_data:
            clean_dir(config_data["exclude"])

        config_str = json.dumps(config_data, indent=2)
    except Exception as e:
        print(f"⚠️ Warning: Config path normalization failed: {e}")

    out_path.write_text(config_str, encoding="utf-8")
    print(f"📄 Aspect config written to: {out_path}")

    if should_run:
        print(f"\nRunning aspect_injector.py --config {out_path}...\n")
        subprocess.run([
            sys.executable, str(ASPECT_INJECTOR_DIR / "aspect_injector.py"),
            "--config", str(out_path)
        ], check=True, cwd=ASPECT_INJECTOR_DIR)


def main():
    parser = argparse.ArgumentParser(
        description="Single natural-language interface for all C++ automation tools."
    )
    parser.add_argument("description", help="Plain-English description of what you want to do")
    parser.add_argument("--old", default=None, help="Path to old interface header (for interface_sync)")
    parser.add_argument("--src", default=None, help="Source directory for derived classes")
    parser.add_argument("-o", "--output", default=None, help="Output path (optional)")
    parser.add_argument("--no-run", action="store_true", help="Only generate files, do not execute pipeline")
    args = parser.parse_args()

    should_run = not args.no_run

    print("🧠 Analyzing intent with Gemini...")
    intent = route_intent(args.description)
    tool = intent.get("tool")
    print(f"🎯 Detected tool target: [{tool}]\n")

    if tool == "state_machine":
        handle_state_machine(args.description, args.output, should_run)
    elif tool == "interface_sync":
        handle_interface_sync(args.description, intent, args, should_run)
    elif tool == "aspect_injector":
        handle_aspect_injector(args.description, args.output, should_run)
    else:
        print(f"❌ Unknown intent: {tool}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()