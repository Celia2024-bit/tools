from .constants import build_injected_lines, normalize_inject_types
from .line_utils import already_injected, find_open_brace_line
from .targets import (
    get_function_param_names,
    iter_target_functions,
    log_parse_problems,
    parse_translation_unit,
)


def inject_trace_into_file(
    cpp_file,
    target_function,
    logger,
    stats,
    excluded_functions=None,
    target_base_class="",
    include_dirs=None,
    inject_types=None
):
    if excluded_functions is None:
        excluded_functions = set()

    inject_types = normalize_inject_types(inject_types)

    tu = parse_translation_unit(cpp_file, include_dirs)

    if target_base_class:
        log_parse_problems(tu, logger)

    lines = cpp_file.read_text(encoding="utf-8").splitlines(True)
    insertions = []

    for node, label in iter_target_functions(
        tu, target_function, target_base_class, excluded_functions, logger
    ):
        brace_idx = find_open_brace_line(
            lines, node.extent.start.line, node.extent.end.line
        )

        if brace_idx is None:
            continue

        if already_injected(lines, brace_idx):
            logger.log(f"   ✅ Already injected: {label}()")
            continue

        param_names = get_function_param_names(node)

        lines_to_inject = build_injected_lines(
            func_name=label,
            param_names=param_names,
            inject_types=inject_types
        )

        if lines_to_inject:
            insertions.append((brace_idx + 1, lines_to_inject, label))

    if not insertions:
        logger.log("   ✅ No changes required.")
        return

    #
    # apply bottom-up so earlier indices stay valid
    #
    insertions.sort(key=lambda x: x[0], reverse=True)

    for insert_idx, lines_to_inject, label in insertions:
        for entry in reversed(lines_to_inject):
            lines.insert(insert_idx, entry)

        logger.log(f"   ✨ Injected: {label}()")
        stats["trace_injected"] += 1

    cpp_file.write_text("".join(lines), encoding="utf-8")
    stats["files_modified"] += 1
