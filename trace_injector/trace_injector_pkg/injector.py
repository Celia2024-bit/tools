from .constants import SCOPE_TRACE
from .line_utils import (
    find_legacy_trace_line,
    has_include,
    include_insert_point,
    injected_span,
    is_one_line_body,
    marker_of,
    markers_in_span
)
from .payloads import (
    BUILT_IN_PAYLOADS,
    build_context,
    include_directives,
    include_text,
    render,
    render_include,
    skip_reason
)
from .targets import (
    body_open_brace,
    iter_target_functions,
    log_parse_problems,
    parse_translation_unit
)


def inject_trace_into_file(
    cpp_file,
    target_function,
    logger,
    stats,
    excluded_functions=None,
    target_base_class="",
    include_dirs=None,
    payload_names=None,
    payload_table=None
):

    if excluded_functions is None:
        excluded_functions = set()

    if payload_table is None:
        payload_table = BUILT_IN_PAYLOADS

    if payload_names is None:
        payload_names = [SCOPE_TRACE]

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

    rewrites = []

    #
    # Headers wanted by the payloads that actually went in, gathered across
    # every function in the file: one include serves the lot.
    #
    headers = []

    for node, label in iter_target_functions(
        tu,
        target_function,
        target_base_class,
        excluded_functions,
        logger
    ):

        brace_idx = body_open_brace(
            node,
            lines
        )

        #
        # No body in this file: a declaration, or a template nothing has
        # defined. Nothing to say about it — the definition will be found
        # wherever it lives.
        #
        if brace_idx is None:
            continue

        #
        # A body written on one line cannot take a payload without its closing
        # brace moving, and moving it is a reformat, not an injection. Said
        # rather than done quietly, since the function did match the rule.
        #
        if is_one_line_body(lines, brace_idx):

            logger.log(
                f"   ⚠️  {label}() skipped: body is on one line"
            )
            continue

        #
        # The legacy check keeps a rerun over a tree injected by an older
        # version from stacking a second trace on top of the first.
        #
        legacy_present = find_legacy_trace_line(
            lines,
            brace_idx
        ) is not None

        wanted = []

        for name in payload_names:

            if name not in payload_table:
                continue

            if name == SCOPE_TRACE and legacy_present:
                continue

            reason, warn = skip_reason(
                payload_table[name],
                node
            )

            if reason:

                if warn:

                    logger.log(
                        f"   ⚠️  {name} skipped: {label}() {reason}"
                    )
                continue

            wanted.append(name)

            for header in include_directives(payload_table[name]):

                if (name, header) not in headers:
                    headers.append((name, header))

        begin, end = injected_span(
            lines,
            brace_idx
        )

        present = markers_in_span(
            lines,
            begin,
            end
        )

        context = build_context(
            node,
            label,
            lines,
            brace_idx
        )

        #
        # The whole injected region is rebuilt rather than patched, which is
        # what makes editing a payload template take effect on a rerun. The
        # payloads already there keep their positions; the ones this rule does
        # not own are copied through untouched.
        #
        desired = []

        for name in present + [
            name
            for name in wanted
            if name not in present
        ]:

            if name in wanted:

                desired.extend(
                    render(
                        name,
                        payload_table[name],
                        context
                    )
                )

            else:

                desired.extend(
                    lines[i]
                    for i in range(begin, end)
                    if marker_of(lines[i]) == name
                )

        #
        # One blank line between the region and the code, unless the author
        # already left one there.
        #
        if desired and not (
            end < len(lines)
            and
            lines[end].strip() == ""
        ):
            desired.append("\n")

        if lines[begin:end] == desired:

            #
            # Both empty means every payload was skipped, which the skip
            # itself has already accounted for — saying "already injected"
            # about a function that has nothing in it would be a lie.
            #
            if desired:

                logger.log(
                    f"   ✅ Already injected: {label}()"
                )
            continue

        added = [
            name
            for name in wanted
            if name not in present
        ]

        rewrites.append(
            (
                begin,
                end,
                desired,
                label,
                bool(added)
            )
        )

    #
    # Presence is decided here, before the bodies move, because no body
    # rewrite can add or remove an #include. Where the line goes has to wait
    # until afterwards, when the indices have settled.
    #
    missing = [
        render_include(name, header)
        for name, header in headers
        if not has_include(
            lines,
            f"#include {include_text(header)}"
        )
    ]

    if not rewrites and not missing:

        logger.log(
            "   ✅ No changes required."
        )
        return

    #
    # apply bottom-up so earlier indices stay valid
    #
    rewrites.sort(
        key=lambda item: item[0],
        reverse=True
    )

    for begin, end, desired, label, added in rewrites:

        lines[begin:end] = desired

        if added:

            logger.log(
                f"   ✨ Injected: {label}()"
            )

            stats["trace_injected"] += 1

        else:

            logger.log(
                f"   ✨ Updated: {label}()"
            )

            stats["trace_updated"] += 1

    if missing:

        at = include_insert_point(lines)

        lines[at:at] = missing

        for line in missing:

            logger.log(
                f"   ➕ Include: {line.strip()}"
            )

            stats["includes_added"] += 1

    cpp_file.write_text(
        "".join(lines),
        encoding="utf-8"
    )

    stats["files_modified"] += 1
