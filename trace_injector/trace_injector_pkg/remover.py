"""
Remove is kind-blind on purpose.

A remove rule says *where* to clean, never *what* to clean: whatever the
injector put at the top of a matched function comes out, trace and validate
alike, and the function is left byte-identical to how it started. Being
selective was the old bug — remove understood only ScopeTrace, so a
trace+validate injection lost its trace and kept its validate, and the next
inject wrote a second copy of the block that was still sitting there.
"""

from .line_utils import (
    find_injected_line,
    find_open_brace_line,
    injected_kinds,
    injected_region_end,
    is_injected_line
)
#
# The targeted path logs `Removed: Class::Method()` and nothing else — the
# function name is the useful part there, and the format is asserted on. The
# whole-file path has no name to give, so it names the kinds instead.
#
from .targets import (
    iter_target_functions,
    log_parse_problems,
    parse_translation_unit
)


def remove_trace_from_file(
    cpp_file,
    logger,
    stats,
    target_function="",
    target_base_class="",
    excluded_functions=None,
    include_dirs=None
):
    """
    With no function/base_class filter and nothing excluded, strip every
    injected block in the file — the cheap line scan, which also catches blocks
    the injector did not place. Any filter at all switches to the AST pass,
    which cleans exactly the functions the matching inject rule would have
    touched.
    """

    if excluded_functions is None:
        excluded_functions = set()

    targeted = bool(
        target_function
        or
        target_base_class
        or
        excluded_functions
    )

    if targeted:

        return _remove_targeted(
            cpp_file,
            logger,
            stats,
            target_function,
            target_base_class,
            excluded_functions,
            include_dirs
        )

    return _remove_all(
        cpp_file,
        logger,
        stats
    )


def _write_back(
    cpp_file,
    lines,
    logger,
    stats
):

    cpp_file.write_text(
        "".join(lines),
        encoding="utf-8"
    )

    stats["files_modified"] += 1


def _remove_targeted(
    cpp_file,
    logger,
    stats,
    target_function,
    target_base_class,
    excluded_functions,
    include_dirs
):

    tu = parse_translation_unit(
        cpp_file,
        include_dirs
    )

    if target_base_class:

        log_parse_problems(
            tu,
            logger
        )

    lines = cpp_file.read_text(
        encoding="utf-8"
    ).splitlines(True)

    deletions = []

    for node, label in iter_target_functions(
        tu,
        target_function,
        target_base_class,
        excluded_functions,
        logger
    ):

        brace_idx = find_open_brace_line(
            lines,
            node.extent.start.line,
            node.extent.end.line
        )

        if brace_idx is None:
            continue

        begin = find_injected_line(
            lines,
            brace_idx
        )

        if begin is None:
            continue

        deletions.append(
            (
                begin,
                injected_region_end(
                    lines,
                    begin
                ),
                label
            )
        )

    if not deletions:

        logger.log(
            "   ✅ No changes required."
        )
        return

    #
    # apply bottom-up so earlier indices stay valid
    #
    deletions.sort(
        key=lambda item: item[0],
        reverse=True
    )

    for begin, end, label in deletions:

        del lines[begin:end]

        logger.log(
            f"   ✨ Removed: {label}()"
        )

        stats["trace_removed"] += 1

    _write_back(
        cpp_file,
        lines,
        logger,
        stats
    )


def _remove_all(
    cpp_file,
    logger,
    stats
):
    """
    One pass over the file, deleting each run of injected blocks whole.

    Counted per run rather than per block, so a function carrying trace and
    validate reports as the one function it is.
    """

    lines = cpp_file.read_text(
        encoding="utf-8"
    ).splitlines(True)

    result = []

    removed = 0

    i = 0

    while i < len(lines):

        if not is_injected_line(lines[i]):

            result.append(
                lines[i]
            )

            i += 1
            continue

        end = injected_region_end(
            lines,
            i
        )

        kinds = injected_kinds(
            lines,
            i,
            end
        )

        logger.log(
            f"   ✨ Removed injection [{', '.join(kinds)}]"
        )

        stats["trace_removed"] += 1
        removed += 1

        i = end

    if not removed:

        logger.log(
            "   ✅ No changes required."
        )
        return

    _write_back(
        cpp_file,
        result,
        logger,
        stats
    )
