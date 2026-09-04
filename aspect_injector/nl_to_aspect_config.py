"""
Natural-language front end for the Aspect Injector.

Instead of hand-writing config.json, describe what you want injected (or
removed) in plain English. Gemini generates a config.json in EXACTLY the
schema config.py already validates, so aspect_injector.py runs completely
unchanged.

Setup:
    pip install google-genai
    set GEMINI_API_KEY=your_key_here   (PowerShell: $env:GEMINI_API_KEY="...")

Run:
    python nl_to_aspect_config.py "inject trace and validate into every function under test/src/hot, but skip AlphaEngine.cpp" -o config.json --run
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

from google import genai
from google.genai import types

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

# Mirrors config.py's TOP_LEVEL_KEYS and resolve_mode_and_rules exactly.
# Keep this in sync if config.py's schema ever changes.
SYSTEM_PROMPT = """You convert a plain-English description of a C++ aspect-injection
task into a config.json file for an existing tool. The JSON must validate against
these exact rules (this is parsed by existing Python code, so be precise):

Top-level keys allowed: "inject", "remove", "exclude", "include_dirs".
- Exactly one of "inject" or "remove" must be present — never both, never neither.
- "exclude" and "include_dirs" are optional.

Each entry in "inject" or "remove" is an object with these optional fields:
- "directory": string, path to scan (required in practice — e.g. "test/src/hot")
- "file": string, exact filename to restrict to (e.g. "RiskChecker.cpp"), or "" for all files
- "function": string, exact function name to restrict to, or "" for all functions
- "base_class": string, only match methods on classes deriving from this base
  (unqualified like "IStrategy" or qualified like "trading::IStrategy"), or ""
- "inject_type": a list of one or more of "trace", "validate", "guard"
    - "trace": adds a ScopeTrace entry/exit log
    - "validate": adds parameter validation (skipped automatically if the
      function has no parameters)
    - "guard": wraps the body in try/catch with error logging
    - Only meaningful for "inject" entries; omit for "remove" entries.

Each entry in "exclude" has:
- "directory", "file" (optional), "function" (optional)
- Never include "base_class" here — exclusions never filter by base class,
  only by directory/file/function.

"include_dirs" is a flat list of extra "-I" style include paths, only needed
when "base_class" filters are used and the base class lives in a header
outside the scanned directory.

Rules:
- Infer directory/file/function/base_class scoping strictly from what the
  description actually says. Do not invent restrictions the user didn't ask for.
- Default inject_type to ["trace"] if the description doesn't say what to inject.
- Output ONLY the JSON. No commentary, no code fences, no trailing comments.
"""


def nl_to_config_json(description: str) -> str:
    """Turn a natural-language description into a config.json string."""
    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=description,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            max_output_tokens=2000,
            thinking_config=types.ThinkingConfig(
            thinking_level=types.ThinkingLevel.MINIMAL 
        ),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        ),
    )
    if not response.text:
        raise RuntimeError(f"Gemini returned an empty response. Full response:\n{response}")
    text = response.text.strip()
    # Strip accidental code fences just in case.
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return text.strip()


def main():
    parser = argparse.ArgumentParser(description="Generate config.json for the Aspect Injector from a natural-language description.")
    parser.add_argument("description", help="Plain-English description of what to inject or remove")
    parser.add_argument("-o", "--output", default="config.json",
                         help="Where to write the generated config (default: config.json)")
    parser.add_argument("--run", action="store_true",
                         help="After generating, immediately run aspect_injector.py --config <output>")
    args = parser.parse_args()

    print("Generating config.json from description...\n")
    config_text = nl_to_config_json(args.description)

    out_path = Path(args.output).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(config_text, encoding="utf-8")

    print(config_text)
    print(f"\nWritten to {out_path}")

    if args.run:
        print(f"\nRunning aspect_injector.py --config {out_path}...\n")
        subprocess.run([sys.executable, "aspect_injector.py", "--config", str(out_path)], check=True)


if __name__ == "__main__":
    main()