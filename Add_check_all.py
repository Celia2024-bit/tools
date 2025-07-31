import yaml
import re
import os
import sys

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

def has_safety_wrapper(lines, start_idx):
    keywords = ['check_all', 'try', 'catch']
    for i in range(start_idx, min(start_idx + 10, len(lines))):
        line = lines[i]
        if any(kw in line for kw in keywords):
            return True
    return False

def get_fallback_value(return_type):
    fallback_map = {
        'bool': 'false',
        'int': '0',
        'double': '0.0',
        'float': '0.0f',
        'std::string': '""',
        'ActionType': 'ActionType::HOLD',
        'void': ''
    }
    return fallback_map.get(return_type.strip(), '/* TODO: fallback */')

def extract_return_type(line, class_name, func_name):
    m = re.search(r'([\w:<>]+)\s+' + re.escape(class_name) + r'::' + re.escape(func_name) + r'\s*\(', line)
    return m.group(1) if m else 'void'

def insert_errorlogger_include(lines):
    if any('ErrorLogger.h' in line for line in lines):
        return lines  # already included
    for i, line in enumerate(lines):
        if line.strip().startswith('#include'):
            lines.insert(i, '#include "../util/ErrorLogger.h"\n')
            lines.insert(i, '#include "../util/ParameterCheck.h"\n')
            break
    return lines

def transform_function_body(lines, start_idx, class_name, func_name, param_names, return_type):
    open_braces = 0
    body_lines = []
    i = start_idx
    while i < len(lines):
        line = lines[i]
        open_braces += line.count('{')
        open_braces -= line.count('}')
        body_lines.append(line)
        if open_braces == 0:
            break
        i += 1

    indent = '    '
    content = body_lines[1:-1]
    fallback = get_fallback_value(return_type)

    if not param_names or has_safety_wrapper(content, 0):
        return body_lines, i + 1

    for raw_line in content:
        if raw_line.strip():
            base_indent = re.match(r'^(\s*)', raw_line).group(1)
            break
    else:
        base_indent = indent

    new_body = [body_lines[0]]

    # check_all block
    if return_type != 'void':
        new_body.append(indent + f'if (!check_all("{class_name}::{func_name}", {", ".join(param_names)}))\n')
        new_body.append(indent + '{\n')
        new_body.append(indent*2 + f'std::cerr << "Invalid parameters in {class_name}::{func_name} !  See parameter_check.log for details" << std::endl;\n')
        new_body.append(indent*2 + f'return {fallback};\n')
        new_body.append(indent + '}\n')
    else:
        new_body.append(indent + f'if (!check_all("{class_name}::{func_name}", {", ".join(param_names)}))\n')
        new_body.append(indent + '{\n')
        new_body.append(indent*2 + 'std::cerr << "Invalid parameters!" << std::endl;\n')
        new_body.append(indent*2 + 'return;\n')
        new_body.append(indent + '}\n')

    # try-catch block
    new_body.append(indent + 'try\n')
    new_body.append(indent + '{\n')
    for line in content:
        new_body.append(indent + line if line.strip() else '\n')
    new_body.append(indent + '}\n')
    new_body.append(indent + 'catch (const std::exception& e)\n')
    new_body.append(indent + '{\n')
    new_body.append(indent*2 + f'ErrorLogger::LogError("{class_name}", "{func_name}", "std::exception", e.what());\n')
    new_body.append(indent*2 + f'std::cerr << "Exception in {class_name}::{func_name}! See error.log for details." << std::endl;\n')
    if fallback:
        new_body.append(indent*2 + f'return {fallback};\n')
    new_body.append(indent + '}\n')
    new_body.append(indent + 'catch (...)\n')
    new_body.append(indent + '{\n')
    new_body.append(indent*2 + f'ErrorLogger::LogError("{class_name}", "{func_name}", "Unknown", "Unspecified error");\n')
    new_body.append(indent*2 + f'std::cerr << "Unknown exception in {class_name}::{func_name}! See error.log for details." << std::endl;\n')
    if fallback:
        new_body.append(indent*2 + f'return {fallback};\n')
    new_body.append(indent + '}\n')

    new_body.append(body_lines[-1])
    return new_body, i + 1

def process_file(filepath, func_sigs):
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    lines = insert_errorlogger_include(lines)

    output = []
    i = 0
    while i < len(lines):
        line = lines[i]
        inserted = False
        for sig_full in func_sigs:
            class_name, func_name, param_names = parse_signature(sig_full)
            if class_name is None:
                continue
            if f'{class_name}::{func_name}' in line and '(' in line:
                output.append(line)
                return_type = extract_return_type(line, class_name, func_name)
                i += 1
                if i < len(lines) and '{' in lines[i]:
                    transformed_body, next_idx = transform_function_body(
                        lines, i, class_name, func_name, param_names, return_type
                    )
                    output.extend(transformed_body)
                    i = next_idx
                else:
                    output.append(lines[i])
                    i += 1
                inserted = True
                break
        if not inserted:
            output.append(line)
            i += 1

    original_content = ''.join(lines)
    updated_content = ''.join(output)

    if original_content != updated_content:
        backup_path = filepath + ".bak"
        os.rename(filepath, backup_path)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(updated_content)
        print(f"Processed {filepath}, backup saved as {backup_path}")
    else:
        print(f"No changes made to {filepath}. Skipped backup.")

def main():
    """
    Main entry point:
    - Load YAML config
    - For each cpp file, process according to configured functions
    """
    if len(sys.argv) < 2:
        print("Usage: python script.py <directory-containing-cpp-files>")
        return

    search_folder = os.path.abspath(sys.argv[1])
    config_path = os.path.join("config", "functionEnhanced.yaml")

    if not os.path.exists(config_path):
        print(f"Config.yaml not found in: {search_folder}")
        return

    config = load_config(config_path)
    if not config:
        print("Config.yaml is empty or malformed. Nothing to do.")
        return

    any_file_processed = False

    for rel_path, func_sigs in config.items():
        abs_path = os.path.join(search_folder, rel_path)
        if not os.path.exists(abs_path):
            print(f"Skipping missing file: {abs_path}")
            continue
        process_file(abs_path, func_sigs)
        any_file_processed = True

    if not any_file_processed:
        print("No valid source files found. Exiting.")

if __name__ == "__main__":
    main()
