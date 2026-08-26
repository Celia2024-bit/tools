from clang import cindex

from .class_hierarchy import is_or_derives_from, owning_class, qualified_name
from .constants import TRACE_LINES
from .file_discovery import match_function
from .line_utils import already_injected, find_open_brace_line

MAX_REPORTED_DIAGNOSTICS = 3


def _build_clang_args(include_dirs):

    args = [
        "-x",
        "c++",
        "-std=c++17"
    ]

    for include_dir in include_dirs or []:
        args.append(
            f"-I{include_dir}"
        )

    return args


def _log_parse_problems(tu, logger):
    """
    Only called when a base_class filter is active: an unresolved #include
    means the hierarchy cannot be walked, and the rule would then silently
    match nothing. A silent miss is worse than a noisy warning.
    """

    reported = 0

    for diagnostic in tu.diagnostics:

        if diagnostic.severity < cindex.Diagnostic.Error:
            continue

        if reported >= MAX_REPORTED_DIAGNOSTICS:

            logger.log(
                "   ⚠️  ... more parse errors suppressed"
            )
            break

        logger.log(
            f"   ⚠️  Parse error: {diagnostic.spelling}"
        )

        reported += 1

    if reported:

        logger.log(
            "   ⚠️  Base-class matching may be incomplete — check "
            "\"include_dirs\" in the config."
        )


def inject_trace_into_file(
    cpp_file,
    target_function,
    logger,
    stats,
    excluded_functions=None,
    target_base_class="",
    include_dirs=None
):

    if excluded_functions is None:
        excluded_functions = set()

    index = cindex.Index.create()

    tu = index.parse(
        str(cpp_file),
        args=_build_clang_args(include_dirs)
    )

    if target_base_class:

        _log_parse_problems(
            tu,
            logger
        )

    lines = cpp_file.read_text(
        encoding="utf-8"
    ).splitlines(True)

    insertions = []

    for node in tu.cursor.walk_preorder():

        if node.kind not in (
            cindex.CursorKind.CXX_METHOD,
            cindex.CursorKind.FUNCTION_DECL
        ):
            continue

        if not node.is_definition():
            continue

        if not match_function(
            node.spelling,
            target_function
        ):
            continue

        if target_base_class and not is_or_derives_from(
            owning_class(node),
            target_base_class
        ):
            continue

        #
        # Always qualified: "StrategyEngine::Run" reads better than a bare
        # "Run" repeated once per override.
        #
        label = qualified_name(node)

        if node.spelling in excluded_functions:

            logger.log(
                f"   🚫 Excluded: {label}()"
            )
            continue

        brace_idx = find_open_brace_line(
            lines,
            node.extent.start.line,
            node.extent.end.line
        )

        if brace_idx is None:
            continue

        if already_injected(
            lines,
            brace_idx
        ):
            logger.log(
                f"   ✅ Already injected: {label}()"
            )
            continue

        insertions.append(
            (
                brace_idx + 1,
                label
            )
        )

    if not insertions:

        logger.log(
            "   ✅ No changes required."
        )
        return

    #
    # apply bottom-up
    #
    insertions.sort(
        key=lambda x: x[0],
        reverse=True
    )

    for insert_idx, func_name in insertions:

        for entry in reversed(
            TRACE_LINES
        ):
            lines.insert(
                insert_idx,
                entry
            )

        logger.log(
            f"   ✨ Injected: {func_name}()"
        )

        stats["trace_injected"] += 1

    cpp_file.write_text(
        "".join(lines),
        encoding="utf-8"
    )

    stats["files_modified"] += 1
