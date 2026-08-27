"""
What gets written into a function body, and how a rule chooses it.

A payload is a name plus a list of line templates. The injector renders the
templates against facts about the function and appends the marker; the remover
only ever looks at the marker, so nothing here has to be understood twice.
"""

from .class_hierarchy import owning_class, qualified_name
from .constants import MARKER_PREFIX, SCOPE_TRACE
from .targets import parameters_of

#
# One space more than the brace's own indentation. Four, because that is what
# every fixture and every project this tool was written for uses; a payload
# that wants something else can write its own leading whitespace and ignore
# {indent}.
#
BODY_INDENT = "    "

#
# The built-in payload. A config's "payloads" table overrides entries by name
# and adds new ones. Leave the table out and this is what inject writes.
#
# The name goes in as a string literal rather than __FUNCTION__ because
# __FUNCTION__ is bare on gcc — `Run`, with no word about which class — and
# fully qualified with its parameter list on MSVC. The injector already knows
# the qualified name, so it writes it and the log reads the same either way.
#
BUILT_IN_PAYLOADS = {
    SCOPE_TRACE: {
        "lines": [
            "{indent}ScopeTrace trace(__FILE__, __LINE__, \"{qualified_name}\");"
        ],
        "include": "ScopeTrace.h"
    }
}


#
# Placeholders that need the parameters to be nameable. A template using none
# of them does not care whether they are, which is why the check is per
# payload rather than per function.
#
PARAMETER_PLACEHOLDERS = (
    "param_names",
    "param_name_list",
    "param_count"
)


def include_directives(spec):
    """
    The headers one payload needs, as a list. One name is the common case, so
    "include" accepts a bare string as well as a list.
    """

    included = spec.get("include") or []

    if isinstance(included, str):
        return [included]

    return list(included)


def include_text(header):
    """
    The header as it is written after #include. Angle brackets and quotes are
    passed through, so a payload can ask for <vector>; anything else is a
    project header and gets quoted.
    """

    header = header.strip()

    if header.startswith("<") or header.startswith("\""):
        return header

    return f"\"{header}\""


def resolve_payloads(config):
    """
    The payload table for this config: the built-in entries, overridden and
    extended by the config's own "payloads" object.
    """

    table = dict(BUILT_IN_PAYLOADS)

    declared = config.get("payloads") or {}

    if not isinstance(declared, dict):
        raise ValueError(
            "\"payloads\" must be an object mapping a payload name to its "
            "definition."
        )

    for name, spec in declared.items():

        if MARKER_PREFIX.strip() in name or not name.strip():
            raise ValueError(
                f"invalid payload name {name!r} — it ends up inside the "
                "marker comment, so keep it to a plain identifier."
            )

        if not isinstance(spec, dict) or not spec.get("lines"):
            raise ValueError(
                f"payload {name!r} must be an object with a non-empty "
                "\"lines\" list."
            )

        for template in spec["lines"]:

            if not isinstance(template, str):
                raise ValueError(
                    f"payload {name!r}: every entry in \"lines\" must be a "
                    f"string, got {template!r}."
                )

        if not isinstance(
            spec.get("requires_parameters", False),
            bool
        ):
            raise ValueError(
                f"payload {name!r}: \"requires_parameters\" must be true or "
                "false."
            )

        included = spec.get("include", "")

        if not isinstance(included, (str, list)):
            raise ValueError(
                f"payload {name!r}: \"include\" must be a header name or a "
                "list of them."
            )

        for header in include_directives(spec):

            if not isinstance(header, str) or not header.strip():
                raise ValueError(
                    f"payload {name!r}: every entry in \"include\" must be a "
                    f"non-empty header name, got {header!r}."
                )

        table[name] = spec

    return table


def validate_rule_payloads(rules, table):
    """
    A rule naming a payload that does not exist is a typo, and a silent one:
    inject would write nothing and report no changes required.
    """

    for rule in rules:

        for name in rule.get("payloads") or []:

            if name not in table:
                raise ValueError(
                    f"rule names an unknown payload {name!r}. Defined: "
                    f"{', '.join(sorted(table))}."
                )


def payloads_for_rule(rule, mode, table):
    """
    Which payloads a rule acts on, in the order they are written.

    inject defaults to the built-in one, so a config written before payloads
    existed keeps injecting what it always did. remove defaults to None,
    meaning every marker it finds — cleaning up is the one job where
    forgetting to list something should not leave it behind, and it is the
    only way to reach a payload whose definition has since left the config.
    """

    listed = rule.get("payloads")

    if listed:
        return list(listed)

    if mode == "remove":
        return None

    return [SCOPE_TRACE]


def body_indent(lines, brace_idx):
    """Indentation for a line inside the body whose brace sits on `brace_idx`."""

    line = lines[brace_idx]

    leading = line[:len(line) - len(line.lstrip())]

    return leading.replace("\n", "").replace("\r", "") + BODY_INDENT


def parameter_facts(node):
    """
    The parameter placeholders for this function, or (None, reason) when its
    parameters cannot be written out.

    Both refusals are about naming, not about types. A parameter with no name
    cannot be passed along, and a variadic tail cannot be enumerated at all —
    a payload that expands to check_all(..., a, b) would silently ignore
    everything after b, which is worse than not injecting.
    """

    if node.type is not None and node.type.is_function_variadic():
        return None, "is variadic"

    names = []

    for argument in parameters_of(node):

        if not argument.spelling:
            return None, "has an unnamed parameter"

        names.append(argument.spelling)

    quoted = ", ".join(
        f"\"{name}\""
        for name in names
    )

    return {
        "param_names": ", ".join(names),
        "param_name_list": "{" + quoted + "}",
        "param_count": str(len(names))
    }, None


def build_context(node, label, lines, brace_idx):
    """
    The facts a template may refer to. The parameter placeholders are absent
    when they cannot be produced — skip_reason keeps any payload that would
    have referred to them from being rendered at all.
    """

    parent = owning_class(node)

    context = {
        "indent": body_indent(lines, brace_idx),
        "qualified_name": label,
        "function": node.spelling,
        "class": qualified_name(parent) if parent is not None else ""
    }

    facts, _ = parameter_facts(node)

    if facts is not None:
        context.update(facts)

    return context


def uses_parameters(spec):

    return any(
        "{" + placeholder + "}" in template
        for template in spec["lines"]
        for placeholder in PARAMETER_PLACEHOLDERS
    )


def skip_reason(spec, node):
    """
    Why this payload cannot go into this function, as (reason, warn), or
    (None, False) when it can.

    `warn` separates the two kinds. "requires_parameters and there are none"
    is the config getting what it asked for and says nothing. A parameter that
    cannot be named is a surprise: a check was asked for and will not be
    there, so it goes in the log.
    """

    if spec.get("requires_parameters") and not parameters_of(node):
        return "takes no parameters", False

    if uses_parameters(spec):

        facts, reason = parameter_facts(node)

        if facts is None:
            return reason, True

    return None, False


def render_include(name, header):
    """
    The #include line for one header, marked like any other injected line so
    removal finds it the same way.
    """

    return f"#include {include_text(header)}  {MARKER_PREFIX}{name}\n"


def render(name, spec, context):
    """The lines to insert for one payload, marker already appended."""

    rendered = []

    for template in spec["lines"]:

        try:
            text = template.format(**context)

        except KeyError as error:
            raise ValueError(
                f"payload {name!r}: unknown placeholder {error}. Available: "
                f"{', '.join(sorted(context))}."
            ) from error

        except (IndexError, ValueError) as error:
            raise ValueError(
                f"payload {name!r}: {error}. A literal brace in a template "
                "has to be doubled — \"{{\" and \"}}\"."
            ) from error

        rendered.append(
            f"{text.rstrip()}  {MARKER_PREFIX}{name}\n"
        )

    return rendered
