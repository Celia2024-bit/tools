"""
Natural-language front end for Interface Sync.

You already have the OLD interface header (a real file). Instead of
hand-editing a copy to make the NEW version, describe the change in plain
English. Gemini reads the old header and writes the new one; your existing
interface_sync.py then does the real work of diffing the two and updating
every derived class header, exactly as before.

Setup:
    pip install google-genai
    set GEMINI_API_KEY=your_key_here   (PowerShell: $env:GEMINI_API_KEY="...")

Run:
    python nl_to_new_interface.py \
        --old test/include/IObserver_old.h \
        --describe "remove OnConnected, add a double timestamp parameter to OnData, and add a new OnError(int err_code) method" \
        --src test/src \
        --run
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

from google import genai
from google.genai import types

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

SYSTEM_PROMPT = """You are given the full contents of an existing C++ interface
header file, followed by a plain-English description of how the interface
should change. Produce the COMPLETE new version of the header file.

Rules:
- Preserve the file's existing style exactly: include guards/pragma, brace
  style, indentation, the virtual destructor, and any methods NOT mentioned
  in the description.
- Every interface method stays a pure virtual method (trailing "= 0;").
  Never add "override" here — this is the base interface, not a derived class.
- Apply only the changes described: remove methods that should be removed,
  modify signatures that should change, add methods that should be added.
  Do not invent unrelated changes.
- Keep the class name identical to the input.
- Output ONLY the complete C++ header file content. No commentary, no
  markdown code fences, no explanation.
"""


def generate_new_header(old_header_text: str, description: str) -> str:
    prompt = (
        f"Existing header:\n\n{old_header_text}\n\n"
        f"Requested change:\n\n{description}"
    )
    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            max_output_tokens=2000,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        ),
    )
    text = response.text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("cpp") or text.startswith("c++") or text.startswith("h"):
            text = text.split("\n", 1)[1] if "\n" in text else text
    return text.strip() + "\n"


def main():
    parser = argparse.ArgumentParser(description="Generate a new interface header from a plain-English description, then run Interface Sync.")
    parser.add_argument("--old", required=True, help="Path to the existing (old) interface header")
    parser.add_argument("--describe", required=True, help="Plain-English description of how the interface should change")
    parser.add_argument("--src", required=True, help="Root directory containing derived class headers")
    parser.add_argument("-o", "--output", default=None,
                         help="Where to write the generated new header (default: same directory as --old, "
                              "same filename without '_old')")
    parser.add_argument("--run", action="store_true",
                         help="After generating, immediately run interface_sync.py --old <old> --new <output> --src <src>")
    args = parser.parse_args()

    old_path = Path(args.old).resolve()
    if not old_path.is_file():
        print(f"Old header not found: {old_path}", file=sys.stderr)
        sys.exit(1)

    if args.output:
        new_path = Path(args.output).resolve()
    else:
        # IObserver_old.h -> IObserver.h, falling back to IObserver_new.h
        stem = old_path.stem
        new_stem = stem[:-4] if stem.endswith("_old") else f"{stem}_new"
        new_path = old_path.with_name(f"{new_stem}{old_path.suffix}")

    print(f"Reading old header: {old_path}")
    old_text = old_path.read_text(encoding="utf-8")

    print("Generating new header from description...\n")
    new_text = generate_new_header(old_text, args.describe)

    new_path.parent.mkdir(parents=True, exist_ok=True)
    new_path.write_text(new_text, encoding="utf-8")

    print(new_text)
    print(f"Written to {new_path}")

    if args.run:
        print(f"\nRunning interface_sync.py --old {old_path} --new {new_path} --src {args.src}...\n")
        subprocess.run(
            [sys.executable, "interface_sync.py",
             "--old", str(old_path),
             "--new", str(new_path),
             "--src", args.src],
            check=True,
        )


if __name__ == "__main__":
    main()
