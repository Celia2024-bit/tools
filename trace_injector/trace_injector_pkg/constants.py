"""
What the injector writes, and therefore what the remover must be able to take
back out again.

Every injection kind declares both halves in one place: `build` produces the
lines, `markers` recognises them on the way out. Adding a kind means adding one
entry to INJECTION_KINDS — inject and remove both read from it, so the two
cannot drift apart. Remove is deliberately kind-blind: it strips every marker
it finds, whatever "inject_type" put it there.
"""

DEFAULT_INJECT_TYPES = ["trace"]


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
INJECTION_KINDS = (
    (
        "trace",
        lambda func_name, param_names: get_scope_trace_lines(func_name),
        (
            "ScopeTrace trace(",
        )
    ),
    (
        "validate",
        get_validate_params_lines,
        (
            "static const char* __param_names[]",
            "validate_params("
        )
    )
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


def build_injected_lines(
    func_name,
    param_names,
    inject_types=None
):
    """The lines to insert for one function, in INJECTION_KINDS order."""

    wanted = normalize_inject_types(inject_types)

    lines = []

    for kind, build, _ in INJECTION_KINDS:

        if kind in wanted:
            lines.extend(
                build(
                    func_name,
                    param_names
                )
            )

    return lines


def kind_of_line(line):
    """Which injection kind wrote this line, or None if nothing did."""

    for kind, _, markers in INJECTION_KINDS:

        for marker in markers:

            if marker in line:
                return kind

    return None
