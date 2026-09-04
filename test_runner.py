#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import os
import argparse
from pathlib import Path

# 获取 tools 目录的绝对路径
TOOLS_DIR = Path(__file__).resolve().parent

# 将各工具目录加入 Python 模块搜索路径
STATE_MACHINE_DIR = TOOLS_DIR / "state_machine"
ASPECT_INJECTOR_DIR = TOOLS_DIR / "aspect_injector"
SYNC_INTERFACE_DIR = TOOLS_DIR / "sync_interface"

sys.path.extend([
    str(STATE_MACHINE_DIR),
    str(ASPECT_INJECTOR_DIR),
    str(SYNC_INTERFACE_DIR)
])

def test_state_machine(md_path=None):
    """测试 状态机 生成 Pipeline
    python test_runner.py --tool sm -f state_machine/test/state_machine.md
    """
    from nl_to_state_machine import run_pipeline
    
    if not md_path:
        md_path = STATE_MACHINE_DIR / "test" / "state_machine.md"
    else:
        md_path = Path(md_path).resolve()

    if not md_path.exists():
        print(f"❌ 错误: 找不到状态机 Markdown 规范文件: {md_path}")
        return

    print(f"\n==========================================")
    print(f"🚀 运行 State Machine Pipeline")
    print(f"📄 Spec: {md_path}")
    print(f"==========================================\n")
    
    run_pipeline(md_path, cwd=STATE_MACHINE_DIR)

def test_aspect_injector(config_path=None):
    """测试 切面注入器 Pipeline:
    python test_runner.py --tool    
    """
    
    import subprocess
    
    if not config_path:
        config_path = ASPECT_INJECTOR_DIR / "config.json"
    else:
        config_path = Path(config_path).resolve()

    if not config_path.exists():
        print(f"❌ 错误: 找不到 Aspect Injector 配置文件: {config_path}")
        return

    print(f"\n==========================================")
    print(f"🚀 运行 Aspect Injector")
    print(f"📄 Config: {config_path}")
    print(f"==========================================\n")

    subprocess.run([
        sys.executable, str(ASPECT_INJECTOR_DIR / "aspect_injector.py"),
        "--config", str(config_path)
    ], check=True, cwd=ASPECT_INJECTOR_DIR)

def main():
    parser = argparse.ArgumentParser(description="Tools 本地离线测试运行器 (零 Token 消耗)")
    parser.add_argument("--tool", "-t", choices=["sm", "aspect", "all"], default="sm", 
                        help="选择测试工具: sm (state_machine), aspect (aspect_injector), all (全部)")
    parser.add_argument("--file", "-f", type=str, help="显式指定配置文件路径 (.md 或 .json)")

    args = parser.parse_args()

    if args.tool in ["sm", "all"]:
        test_state_machine(args.file if args.tool == "sm" else None)
        
    if args.tool in ["aspect", "all"]:
        test_aspect_injector(args.file if args.tool == "aspect" else None)

if __name__ == "__main__":
    main()