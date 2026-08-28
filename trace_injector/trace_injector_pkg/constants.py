"""
What the injector writes, and therefore what the remover must be able to take
back out again.

Every injection kind declares all three halves in one place: `build` produces
the lines, `header` is the include those lines need, and the kind's name is what
the marker comment carries. Adding a kind means adding one entry to
INJECTION_KINDS — inject and remove both read from it, so the two cannot drift
apart. Remove is deliberately kind-blind: it strips every marker it finds,
whatever "inject_type" put it there.

Injected lines are found again by their marker comment, not by the C++ they
contain. Matching on the code was the old way and it could not tell an injected
`ScopeTrace trace(...)` from a hand-written one, so remove deleted both. The
marker is the tool's signature: no marker, not ours, left alone.
"""

DEFAULT_INJECT_TYPES = ["trace"]

#
# Appended to every line the injector writes. Kept in one piece so a search for
# it in a source tree finds every trace of this tool at once.
#
INJECT_MARKER = "// inject automatically"


def block_marker(kind):
    """The marker carried by each line of an injected block."""

    return f"{INJECT_MARKER}: {kind}"


def include_marker(kind):
    """
    The marker carried by an #include the injector added.

    Distinct from block_marker on purpose: an include is file-scoped and a
    block is function-scoped, so the two are added, counted and removed under
    different rules and must never be mistaken for each other.
    """

    return f"{INJECT_MARKER}: include for {kind}"


def mark_lines(lines, kind):
    """
    Append the kind's marker to every non-blank line of a block.

    Every line, not just the first: the ScopeTrace block spans five lines, and
    a marker on only one of them would leave the remover to work out where the
    block ends by counting brackets. Marked line by line, removal is a filter.
    """

    marker = block_marker(kind)

    return [
        f"{line.rstrip()}  {marker}\n"
        if line.strip()
        else line
        for line in lines
    ]


def get_scope_trace_lines(func_name):
    """The ScopeTrace guard placed at the top of a function body."""

    return [
        "    ScopeTrace trace(\n",
        "        __FILE__,\n",
        "        __LINE__,\n",
        f'        "{func_name}"\n',
        "    );\n",
        "\n"
    ]


def get_validate_params_lines(func_name, param_names):
    """
    The parameter check, plus the name table it reads.

    Empty for a function that takes no parameters: there is nothing to check,
    and `const char* __param_names[] = {}` does not compile.
    """

    if not param_names:
        return []

    names = ", ".join(
        f'"{name}"'
        for name in param_names
    )

    args = ", ".join(param_names)

    return [
        f"    static const char* __param_names[] = {{ {names} }};\n",
        f'    validate_params("{func_name}", __param_names, {args});\n',
        "\n"
    ]


#
# Order matters twice over: it is the order blocks are written in, so the log
# and the file read the same way, and remove walks the run of blocks in file
# order regardless.
#
# The headers are named, not located. Where they are found is the project's
# `-I`, exactly as for every other header the sources include; ScopeTrace.h and
# ParameterCheck.h live in the util library and are maintained there.
#
INJECTION_KINDS = (
    (
        "trace",
        lambda func_name, param_names: get_scope_trace_lines(func_name),
        "ScopeTrace.h"
    ),
    (
        "validate",
        get_validate_params_lines,
        "ParameterCheck.h"
    )
)


def injected_headers():
    """Every header this tool includes on the sources' behalf."""

    return tuple(
        header
        for _, _, header in INJECTION_KINDS
    )


def normalize_inject_types(inject_types):
    """
    A rule may say "trace", ["trace", "validate"], or nothing at all. Callers
    should not each re-handle that.
    """

    if inject_types is None:
        return list(DEFAULT_INJECT_TYPES)

    if isinstance(inject_types, str):
        return [inject_types]

    return list(inject_types)


def build_injected_blocks(
    func_name,
    param_names,
    inject_types=None
):
    """
    The (kind, lines) pairs to insert for one function, in INJECTION_KINDS
    order.

    A kind that produced nothing is left out rather than reported as an empty
    block, which is what makes "so which includes does this file need" a
    question about what was written instead of about what the rule asked for.
    """

    wanted = normalize_inject_types(inject_types)

    blocks = []

    for kind, build, _ in INJECTION_KINDS:

        if kind not in wanted:
            continue

        lines = build(
            func_name,
            param_names
        )

        if lines:
            blocks.append(
                (
                    kind,
                    mark_lines(
                        lines,
                        kind
                    )
                )
            )

    return blocks


def kind_of_line(line):
    """Which injection kind wrote this line, or None if nothing did."""

    for kind, _, _ in INJECTION_KINDS:

        if line.rstrip().endswith(
            block_marker(kind)
        ):
            return kind

    return None
