"""
Natural-language front end for Celia's State Machine pipeline.

Instead of hand-writing state_machine.md, describe the state machine in
plain English. Gemini generates a Markdown file in EXACTLY the format
table_to_json.py already expects.
"""

import argparse
import os
import subprocess
from pathlib import Path
import sys
from google import genai
import time
from google.genai import errors, types
from google import genai

# 初始化 Google GenAI Client
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

SYSTEM_PROMPT = """You convert a plain-English description of a state machine
into a Markdown file in EXACTLY this format (this is parsed by an existing
tool, so the structure must match precisely):

# <Title> State Machine Definition

## Config

- **prefix**: <PascalCase prefix for generated class names, e.g. Order>

## Context Definition Table

| **context_name** | **field_type** | **field_name** | **description** |
| ----------------- | --------------- | --------------- | ----------------- |
| <ContextName>      | <C++ type>      | <fieldName>     | <description>      |

## State Definition Table

| **id** | **name** | **type** | **description** |
| ------ | -------- | -------- | ---------------- |
| S000   | <Name>   | initial  | <description>     |

## State Transition Table

| **id** | **from_state** | **event** | **guard** | **to_state** | **action** | **description** |
| ------ | -------------- | --------- | --------- | ------------ | ---------- | ---------------- |
| T001   | <From>         | <Event>   |           | <To>         | <Action>   | <description>     |

Rules:
- Exactly one state must have type "initial". Terminal states get type "final".
  All other states get type "normal".
- State ids are S000, S001, S002, ... in order of first appearance.
- Transition ids are T001, T002, T003, ... in order.
- "guard" is only filled in when the description implies a condition
  (e.g. "if the amount is over 100"). Leave it empty otherwise.
- "action" is only filled in when the description implies a side effect
  (e.g. "send a notification"). Use PascalCase, e.g. SendPaymentNotification.
- Infer 2-4 sensible context fields (order id, amount, etc.) if the domain
  implies them; otherwise you may leave the Context table with just the header.
- Output ONLY the Markdown file content. No commentary, no code fences.
"""


def nl_to_state_machine_md(description: str) -> str:
    """Turn a natural-language description into a state_machine.md your pipeline can parse."""
    response = client.models.generate_content(
        model='gemini-3.6-flash',
        contents=description,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            max_output_tokens=2000,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
        ),
    )
    return response.text.strip()

def run_pipeline(md_path, cwd=None):
    """
    Run the existing table_to_json.py -> json_to_mermaid.py -> json_to_cpp.py
    pipeline against an already-generated state_machine.md, then compile and
    run the C++ test.

    `cwd` lets a caller outside this tool's own directory (like
    dev_assistant.py) point the subprocess calls at the right place, without
    duplicating this logic. Left as None, subprocess uses the current
    process's own working directory — the original standalone behaviour.
    """
    md_path = Path(md_path)
    posix_md_path = md_path.as_posix()
    filename = md_path.stem
    json_path = f"./out/{filename}.json"

    print(f"\nRunning Python pipeline on {posix_md_path}...\n")

    # 1. Markdown -> JSON
    subprocess.run([sys.executable, "table_to_json.py", posix_md_path], check=True, cwd=cwd)
    # 2. JSON -> Mermaid
    subprocess.run([sys.executable, "json_to_mermaid.py", json_path], check=True, cwd=cwd)
    # 3. JSON -> C++ (包含 main.cpp 生成)
    subprocess.run([sys.executable, "json_to_cpp.py", json_path, "-p", "Order"], check=True, cwd=cwd)

    # 4. 编译并运行 C++ 测试
    print("\n🔨 Compiling and Running C++ test...")
    code_dir = Path("./out/code")
    executable = code_dir / "test_sm.exe" if sys.platform == "win32" else code_dir / "test_sm"

    compile_cmd = [
        "g++", "-std=c++17",
        str(code_dir / "main.cpp"),
        str(code_dir / "OrderStateMachine.cpp"),
        str(code_dir / "OrderHandler.cpp"),
        "-o", str(executable)
    ]
    subprocess.run(compile_cmd, check=True, cwd=cwd)
    subprocess.run([str(executable)], check=True, cwd=cwd)

    print("\n✨ All operations completed successfully!")


def main():
    parser = argparse.ArgumentParser(description="Generate state_machine.md from a natural-language description.")
    parser.add_argument("description", help="Plain-English description of the state machine")
    parser.add_argument("-o", "--output", default="./test/state_machine.md",
                         help="Where to write the generated Markdown (default: ./test/state_machine.md)")
    parser.add_argument("--run", action="store_true",
                         help="After generating, immediately run pipeline")
    args = parser.parse_args()

    print("Generating state_machine.md from description...\n")
    markdown = nl_to_state_machine_md(args.description)

    out_path = Path(args.output).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(markdown, encoding="utf-8")

    print(markdown)
    print(f"\nWritten to {out_path}")

    if args.run:
        run_pipeline(out_path)

if __name__ == "__main__":
    main()