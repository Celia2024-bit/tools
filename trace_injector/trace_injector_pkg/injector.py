from .constants import build_injected_blocks, normalize_inject_types
from .includes import add_includes
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

    #
    # What was actually written, which is not the same as what the rule asked
    # for: "validate" produces nothing for a function with no parameters. The
    # includes follow this set, so a file that got no validate block does not
    # end up including ParameterCheck.h — and with it Types.h — for nothing.
    #
    kinds_written = set()

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

        blocks = build_injected_blocks(
            func_name=label,
            param_names=param_names,
            inject_types=inject_types
        )

        if blocks:

            lines_to_inject = [
                line
                for _, block in blocks
                for line in block
            ]

            kinds = [
                kind
                for kind, _ in blocks
            ]

            insertions.append((brace_idx + 1, lines_to_inject, label, kinds))

            kinds_written.update(kinds)

    if not insertions:
        logger.log("   ✅ No changes required.")
        return

    #
    # apply bottom-up so earlier indices stay valid
    #
    insertions.sort(key=lambda x: x[0], reverse=True)

    for insert_idx, lines_to_inject, label, kinds in insertions:
        for entry in reversed(lines_to_inject):
            lines.insert(insert_idx, entry)

        #
        # The kinds, not just the name. A rule asking for validate writes no
        # validate block into a function with no parameters, and that is most
        # functions in most code — so a log that only names the function reads
        # as "validate did nothing at all" when it did exactly what it should.
        #
        logger.log(
            f"   ✨ Injected: {label}() [{', '.join(kinds)}]"
        )

        stats["trace_injected"] += 1

    #
    # Last, so the indices above stay the ones the AST reported. The include
    # lands at the top of the file, ahead of every body this run touched.
    #
    lines, added = add_includes(lines, kinds_written)

    for header in added:
        logger.log(f"   ✨ Added include: {header}")
        stats["includes_added"] += 1

    cpp_file.write_text("".join(lines), encoding="utf-8")
    stats["files_modified"] += 1
