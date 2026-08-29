#!/usr/bin/env python3
"""
Verify C++ code injection via g++ compilation and execution.
Supports full automatic execution or step-by-step interactive execution.
"""

import argparse
import subprocess
import sys
from pathlib import Path

# Base directories setup
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent           # C:\workspace\Personals\TradeSystem\tools
PROJECT_ROOT = ROOT.parent   # C:\workspace\Personals\TradeSystem

sys.path.insert(0, str(ROOT))

from trace_injector_pkg.cli import main as cli_main
from trace_injector_pkg.libclang import configure as configure_libclang

# Ensure libclang is configured properly
configure_libclang()

def parse_args():
    """Parse command line arguments."""
    epilog_text = """
Examples:
  1. Run all steps automatically (default):
     python3 verify_compile.py

  2. Interactive step-by-step mode (pause after each step to observe changes):
     python3 verify_compile.py -i

  3. Fast syntax-only verification (no linking needed):
     python3 verify_compile.py -s
"""

    parser = argparse.ArgumentParser(
        description="Verify C++ code injection by compiling with g++.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=epilog_text
    )
    
    parser.add_argument(
        "-c", "--config",
        type=Path,
        default=ROOT / "configs_examples" / "config_cfg_compile_all.json",
        help="Path to the JSON configuration file"
    )
    
    parser.add_argument(
        "-d", "--dir",
        type=Path,
        default=ROOT / "test" / "src",
        help="Target C++ source directory to compile"
    )

    parser.add_argument(
        "-s", "--syntax-only",
        action="store_true",
        help="Perform syntax-only check without linking"
    )

    parser.add_argument(
        "-i", "--interactive",
        action="store_true",
        help="Enable interactive step-by-step execution mode"
    )
    
    return parser.parse_args()

def prompt_next_step(step_name, interactive=False):
    """Prompts the user before proceeding to the next step if interactive mode is enabled."""
    if interactive:
        print(f"\n==================================================")
        input(f"👉 Press [Enter] to execute: {step_name}...")
        print(f"==================================================\n")

def run_injection(config_path, interactive=False):
    """Executes code injection using the CLI."""
    prompt_next_step("Step 1: Code Injection", interactive)
    
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
        
    print(f"--> [Step 1] Applying injection config: {config_path.name}")
    sys.argv = ["trace_injector.py", "--config", str(config_path)]
    exit_code = cli_main()
    if exit_code != 0:
        raise RuntimeError(f"Injection failed with exit code: {exit_code}")
    print("    ✨ Injection completed successfully!")
    print("    💡 (Tip: You can check your C++ source files now to see injected code!)\n")

def compile_and_run(source_dir, syntax_only=False, interactive=False, output_bin="test_runner"):
    """Compiles modified C++ files using g++."""
    prompt_next_step("Step 2: G++ Compilation", interactive)

    if not source_dir.exists():
        raise FileNotFoundError(f"Source directory not found: {source_dir}")

    mode_str = "Syntax Validation" if syntax_only else "Full Compilation & Execution"
    print(f"--> [Step 2] {mode_str} in: {source_dir}")

    # Collect .cpp files from target directory
    cpp_files = [str(p) for p in source_dir.rglob("*.cpp")]

    # Include util implementations for linking (excluding standalone test files)
    if not syntax_only:
        util_dir = PROJECT_ROOT / "util"
        if util_dir.exists():
            for p in util_dir.rglob("*.cpp"):
                if "Test" in p.parts or "test" in p.parts:
                    continue
                cpp_files.append(str(p))

    if not cpp_files:
        print("    No .cpp files found. Skipping compilation.")
        return

    out_exec = source_dir / output_bin

    # Build g++ command
    cmd = [
        "g++", "-std=c++17", "-O0", "-g",
        "-I", str(PROJECT_ROOT / "util"),
        "-I", str(PROJECT_ROOT / "util" / "ScopeTrace"),
        "-I", str(PROJECT_ROOT / "util" / "Parameter_Check"),
        "-I", str(PROJECT_ROOT / "util" / "Parameter_Check" / "Types_examples"),
        "-I", str(source_dir)
    ]

    if syntax_only:
        cmd.append("-fsyntax-only")
        cmd.extend(cpp_files)
    else:
        cmd.extend(cpp_files)
        cmd.extend(["-o", str(out_exec)])
        cmd.append("-lws2_32")

    print(f"    Running build command: {' '.join(cmd)}")
    build_res = subprocess.run(cmd, capture_output=True, text=True)

    if build_res.returncode != 0:
        print("    ❌ Compilation failed! Build log:")
        print(build_res.stderr)
        sys.exit(1)
    
    print("    ✨ Compilation successful!\n")

    # Step 3: Run Binary if not syntax-only
    if not syntax_only:
        prompt_next_step("Step 3: Binary Execution", interactive)
        print(f"--> [Step 3] Executing compiled binary ({out_exec.name})...")
        print("=" * 50 + " [ Binary Output ] " + "=" * 50)
        exec_res = subprocess.run([str(out_exec)], capture_output=True, text=True)
        print(exec_res.stdout)
        if exec_res.stderr:
            print("[STDERR]:", exec_res.stderr)
        print("=" * 119)

        if exec_res.returncode == 0:
            print("    ✅ Binary executed successfully with exit code 0!\n")
        else:
            print(f"    ❌ Execution failed with exit code {exec_res.returncode}\n")

def run_cleanup(interactive=False):
    """Restores repository state using git checkout."""
    prompt_next_step("Step 4: Cleanup & Git Restore", interactive)
    print("--> [Step 4] Restoring C++ source state...")
    subprocess.run(["git", "checkout", "--", str(ROOT)], check=False)
    print("    Repository state restored.\n")

def main():
    args = parse_args()

    try:
        # Step 1: Inject
        run_injection(args.config, interactive=args.interactive)
        
        # Step 2 & 3: Compile and Run
        compile_and_run(source_dir=args.dir, syntax_only=args.syntax_only, interactive=args.interactive)
        
        print("🎉 Verification complete: Injected C++ code passed all checks!")
    finally:
        # Step 4: Cleanup
        run_cleanup(interactive=args.interactive)

if __name__ == "__main__":
    main()