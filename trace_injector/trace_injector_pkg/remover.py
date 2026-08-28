"""
Remove is kind-blind on purpose.

A remove rule says *where* to clean, never *what* to clean: whatever the
injector put into a matched function comes out — trace, validate and both halves
of a guard alike — and the function is left byte-identical to how it started.
Being selective was the old bug: remove understood only ScopeTrace, so a
trace+validate injection lost its trace and kept its validate, and the next
inject wrote a second copy of the block that was still sitting there.

"Into", not "at the top of". A guard wraps the body, so its closing half sits
just above the function's own brace and the search has to cover the whole
extent.

Kind-blind is not code-blind. What comes out is what carries the injector's
marker comment, so a hand-written ScopeTrace guard, or an #include somebody
added themselves, survives a remove that walks right past it.
"""

from .constants import is_block_end_line
from .includes import drop_orphan_includes
from .line_utils import (
    find_open_brace_line,
    injected_kinds,
    injected_region_end,
    injected_runs,
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
    """
    The one place a removal is written, and therefore the one place the includes
    are reconsidered: whichever path deleted the blocks, the include goes if and
    only if nothing is left that needs it.
    """

    lines, dropped = drop_orphan_includes(lines)

    for header in dropped:

        logger.log(
            f"   ✨ Removed include: {header}"
        )

        stats["includes_removed"] += 1

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

    removed_labels = []

    #
    # Runs already claimed, keyed by where they start. walk_preorder hands out
    # nested definitions too — a lambda's operator() sits inside the extent of
    # the function that declares it — so the same run can be offered twice, and
    # deleting it twice would take a chunk of the file with it.
    #
    claimed = set()

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

        #
        # The whole body, not just the top of it. A guard writes its catch arms
        # above the closing brace, and a window at the top of the function
        # cannot see them.
        #
        found = False

        for begin, end in injected_runs(
            lines,
            brace_idx + 1,
            node.extent.end.line
        ):

            if begin in claimed:
                continue

            claimed.add(begin)

            deletions.append(
                (begin, end)
            )

            found = True

        if found:
            removed_labels.append(label)

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

    for begin, end in deletions:

        del lines[begin:end]

    #
    # Per function, not per run: a function carrying a trace, a validate and the
    # two halves of a guard is still the one function the reader asked about.
    #
    for label in removed_labels:

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
    validate reports as the one function it is — and the closing half of a guard
    is not counted at all. A line scan has no way to pair a run of catch arms
    with the `try` it belongs to, and counting it would report one injection as
    two, disagreeing with both the inject that wrote it and the targeted remove
    that takes it out.
    """

    lines = cpp_file.read_text(
        encoding="utf-8"
    ).splitlines(True)

    result = []

    #
    # Deleted, not counted: those are two different numbers now, and it is the
    # first that decides whether the file has to be written back.
    #
    deleted = 0

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

        deleted += 1

        if not is_block_end_line(lines[i]):

            kinds = injected_kinds(
                lines,
                i,
                end
            )

            logger.log(
                f"   ✨ Removed injection [{', '.join(kinds)}]"
            )

            stats["trace_removed"] += 1

        i = end

    if not deleted:

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
