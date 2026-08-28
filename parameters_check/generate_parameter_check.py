#!/usr/bin/env python3
import sys
import re
import os
import shutil
from pathlib import Path
from jinja2 import Template

def check_types_header(types_path: Path) -> bool:
    """
    Statically analyzes Types.h to verify that all custom types meet
    one of the three validity check requirements:
      1) Defines 'bool isValid() const'
      2) Defines 'empty()' (container-like types)
      3) Provides a 'check_traits<T>' specialization
    """
    if not types_path.exists():
        print(f"[Error] Target Types header not found at: {types_path}")
        return False

    content = types_path.read_text(encoding='utf-8')

    struct_matches = re.findall(r'(?:struct|class)\s+([A-Za-z0-9_]+)', content)
    enum_matches = re.findall(r'enum\s+(?:class\s+)?([A-Za-z0-9_]+)', content)
    check_traits_matches = set(re.findall(r'check_traits<\s*([A-Za-z0-9_]+)\s*>', content))

    passed = True

    # 1. Validate Structs/Classes against isValid, empty, or check_traits
    for struct_name in struct_matches:
        if struct_name in ['check_traits', 'std']:
            continue

        struct_pattern = rf'(?:struct|class)\s+{struct_name}\s*\{{(.*?)\}};'
        match = re.search(struct_pattern, content, re.DOTALL)

        body = match.group(1) if match else ""

        has_is_valid = "isValid" in body
        has_empty = "empty" in body
        has_traits = struct_name in check_traits_matches

        if not (has_is_valid or has_empty or has_traits):
            print(f"[Validation Failed] Type '{struct_name}' in {types_path.name} "
                  f"does NOT implement 'isValid()', 'empty()', nor 'check_traits<{struct_name}>'.")
            passed = False

    # 2. Validate Enums against check_traits specialization
    for enum_name in enum_matches:
        if enum_name not in check_traits_matches:
            print(f"[Validation Failed] Enum '{enum_name}' in {types_path.name} "
                  f"lacks 'check_traits<{enum_name}>' specialization.")
            passed = False

    return passed

def generate_and_deploy(types_path: Path, output_dir: Path) -> bool:
    """
    Validates target Types.h, deploys CheckTraits.h to Types.h directory,
    and renders ParameterCheck.h in output_dir. Returns True on success.

    Every read-only check runs before the first write. That ordering is the
    point: this script's first side effect used to be copying CheckTraits.h
    into the target project's include directory, and it happened BEFORE
    Types.h was validated. A rejected run therefore still left a file behind
    in a tree it had just refused to generate for.
    """
    script_dir = Path(__file__).parent
    templates_dir = script_dir / "templates"
    j2_template_path = templates_dir / "ParameterCheck.h.j2"
    check_traits_src = templates_dir / "CheckTraits.h"

    # Step 1: Validate Types.h, before anything is written anywhere
    print(f"--> Validating {types_path}...")

    if not check_types_header(types_path):
        print("\n[Build Stopped] Types validation failed. Generation aborted.")
        print("Nothing was written.")
        return False

    print("--> Types validation passed.")

    # Step 2: Check template availability, still read-only
    if not j2_template_path.exists():
        print(f"[Error] Template not found: {j2_template_path}")
        return False

    if not check_traits_src.exists():
        print(f"[Error] CheckTraits.h not found in templates: {check_traits_src}")
        return False

    # Step 3: Copy CheckTraits.h to the SAME folder as Types.h
    types_dir = types_path.parent
    target_traits_in_types_dir = types_dir / "CheckTraits.h"
    shutil.copy2(check_traits_src, target_traits_in_types_dir)
    print(f"--> Successfully copied CheckTraits.h to Types directory: {target_traits_in_types_dir}")

    # Ensure ParameterCheck.h output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)
    target_parameter_check_path = output_dir / "ParameterCheck.h"

    # Step 4: Calculate relative include paths from output_dir to both headers
    rel_types_path = os.path.relpath(types_path.resolve(), output_dir.resolve())
    rel_traits_path = os.path.relpath(target_traits_in_types_dir.resolve(), output_dir.resolve())

    types_include_str = str(rel_types_path).replace("\\", "/")
    traits_include_str = str(rel_traits_path).replace("\\", "/")

    # Step 5: Render ParameterCheck.h
    template_content = j2_template_path.read_text(encoding='utf-8')
    template = Template(template_content)
    rendered_code = template.render(
        types_header_path=types_include_str,
        check_traits_header_path=traits_include_str
    )

    target_parameter_check_path.write_text(rendered_code, encoding='utf-8')
    print(f"--> Successfully generated: {target_parameter_check_path}")
    print(f"    * Includes Types.h from: '{types_include_str}'")
    print(f"    * Includes CheckTraits.h from: '{traits_include_str}'")

    return True

if __name__ == "__main__":
    # Command CLI parameters:
    #   sys.argv[1]: Path to input Types.h
    #   sys.argv[2]: Target output directory for ParameterCheck.h
    input_types_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("src/Types.h")
    output_destination_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("include")

    #
    # The exit code lives here rather than inside generate_and_deploy, which
    # used to sys.exit() from three places. A caller that imports this module
    # should get a return value, not have its own process killed.
    #
    sys.exit(
        0 if generate_and_deploy(input_types_path, output_destination_dir) else 1
    )
