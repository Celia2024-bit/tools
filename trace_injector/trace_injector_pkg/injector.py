from .constants import build_injected_blocks, normalize_inject_types
from .includes import add_includes
from .line_utils import (
    already_injected,
    find_close_brace_line,
    find_open_brace_line
)
from .targets import (
    get_function_param_names,
    iter_target_functions,
    log_parse_problems,
    parse_translation_unit,
)

#
# Which half of a function an insertion goes into. Ordered, and the order is
# what decides the tie when both land on the same line — see the sort below.
#
ABOVE_BODY = 0
BELOW_BODY = 1


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

        if not blocks:
            continue

        above = [
            line
            for _, top, _ in blocks
            for line in top
        ]

        #
        # Reversed: the kinds nest, so the one whose `try` opens last is the one
        # whose `catch` has to close first. Only "guard" writes down here today,
        # but a second wrapping kind would be silently mis-nested otherwise.
        #
        below = [
            line
            for _, _, tail in reversed(blocks)
            for line in tail
        ]

        kinds = [
            kind
            for kind, _, _ in blocks
        ]

        close_idx = None

        if below:

            close_idx = find_close_brace_line(
                lines,
                brace_idx,
                node.extent.end.line
            )

            #
            # A body written entirely on its opening line has nowhere to put the
            # closing half, and guessing would mean writing a `}` into the
            # middle of a statement. Skipped whole rather than half-injected.
            #
            if close_idx is None:

                logger.log(
                    f"   ⏭️  Skipped: {label}() — body shares its line with "
                    "the braces"
                )
                continue

        insertions.append(
            (brace_idx + 1, ABOVE_BODY, above, label, kinds)
        )

        if below:

            #
            # No label: one function is one log line and one count, however many
            # places the blocks had to be written into.
            #
            insertions.append(
                (close_idx, BELOW_BODY, below, None, kinds)
            )

        kinds_written.update(kinds)

    if not insertions:
        logger.log("   ✅ No changes required.")
        return

    #
    # Apply bottom-up so earlier indices stay valid. The tie-break matters: an
    # empty body puts the closing half on the same line as the opening one, and
    # inserting the opening first would leave the catch arms sitting above the
    # `try` they belong to.
    #
    insertions.sort(
        key=lambda item: (item[0], item[1]),
        reverse=True
    )

    for insert_idx, _, lines_to_inject, label, kinds in insertions:
        for entry in reversed(lines_to_inject):
            lines.insert(insert_idx, entry)

        if label is None:
            continue

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
