import yaml
import re
import os

def load_config(yaml_path):
    """Load YAML configuration file."""
    with open(yaml_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def parse_signature(sig):
    """
    Parse function signature string to extract:
    - class name
    - function name
    - parameter names (without types)
    Example input: 'bool TradeExecutor::ExecuteBuyOrder(price, amount)'
    """
    m = re.match(r'.*\b(\w+)::(\w+)\s*\((.*)\)', sig)
    if not m:
        return None, None, []
    class_name = m.group(1)
    func_name = m.group(2)
    params = m.group(3)
    # Split parameters by comma and strip whitespace
    param_names = [p.strip() for p in params.split(',') if p.strip()]
    return class_name, func_name, param_names

def has_check_all(lines, start_idx):
    """
    Check if 'check_all' call exists within the next few lines after the opening brace.
    This avoids duplicate insertion. We'll look specifically after the brace.
    """
    # Look for check_all within a reasonable range after the insertion point
    for i in range(start_idx, min(start_idx + 5, len(lines))):
        if 'check_all' in lines[i]:
            return True
    return False

def generate_check_all_call(func_name, param_names):
    """
    Generate the check_all call string.
    If no parameters, return empty string (no call).
    Format: check_all("FunctionName", param1, param2, ...);
    """
    if not param_names:
        return ''
    return '    check_all("{}", {});\n'.format(func_name, ", ".join(param_names))

def process_file(filepath, func_sigs):
    """
    Process a C++ source file:
    - For each configured function signature, find the corresponding definition
    - Detect opening brace on a separate line
    - Insert check_all call if missing immediately after brace
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    output = []
    i = 0
    while i < len(lines):
        line = lines[i]
        inserted = False
        for sig_full in func_sigs:
            class_name, func_name, param_names = parse_signature(sig_full)
            if class_name is None:
                continue

            # const|noexcept|override:  it is extensible
            pattern = rf'\s*[\w\s\*&:<>,]*\b{class_name}::{func_name}\s*\([^)]*\)\s*(?:\b(?:const|noexcept|override)\b\s*)*(?:\{{)?$'
            if re.match(pattern, line.strip()):
                # Found the function signature on its own line
                output.append(line)
                i += 1  # Advance to the next line, where the brace is expected

                if i < len(lines) and '{' in lines[i]:
                    brace_line = lines[i]
                    output.append(brace_line)

                    if not has_check_all(lines, i + 1):
                        output.append(generate_check_all_call(func_name, param_names))

                    i += 1  # Continue processing after brace
                    inserted = True
                    break
                else:
                    # Brace not found where expected, still add next line
                    if i < len(lines):
                        output.append(lines[i])
                        i += 1
                    inserted = True
                    break

        if not inserted:
            output.append(line)
            i += 1

    backup_path = filepath + ".bak"
    os.rename(filepath, backup_path)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(output)
    print(f"Processed {filepath}, backup saved as {backup_path}")


def main():
    """
    Main entry point:
    - Load YAML config
    - For each cpp file, process according to configured functions
    """
    # Ensure Config.yaml exists for testing
    if not os.path.exists('Config.yaml'):
        with open('Config.yaml', 'w') as f:
            f.write("TradeExecutor.cpp:\n")
            f.write("  - bool TradeExecutor::ExecuteBuyOrder(price, amount)\n")
            f.write("  - bool TradeExecutor::HandleActionSignal(action, price, amount)\n")

    # Ensure TradeExecutor.cpp exists for testing
    if not os.path.exists('TradeExecutor.cpp'):
        with open('TradeExecutor.cpp', 'w') as f:
            f.write("class TradeExecutor {\n")
            f.write("public:\n")
            f.write("bool TradeExecutor::ExecuteBuyOrder(double price, double amount)\n")
            f.write("{\n")
            f.write("    // Some existing code\n")
            f.write("    return true;\n")
            f.write("}\n")
            f.write("\n")
            f.write("bool TradeExecutor::HandleActionSignal(int action, double price, double amount) {\n")
            f.write("    // Another function\n")
            f.write("    return false;\n")
            f.write("}\n")
            f.write("};\n")

    config = load_config('Config.yaml')
    for cpp_file, func_sigs in config.items():
        if not os.path.exists(cpp_file):
            print(f"{cpp_file} not found, skipping.")
            continue
        process_file(cpp_file, func_sigs)

if __name__ == "__main__":
    main()