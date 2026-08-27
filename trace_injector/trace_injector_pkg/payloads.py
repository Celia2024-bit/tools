"""
What gets written into a function body, and how a rule chooses it.

A payload is a name plus a list of line templates. The injector renders the
templates against facts about the function and appends the marker; the remover
only ever looks at the marker, so nothing here has to be understood twice.
"""

from .class_hierarchy import owning_class, qualified_name
from .constants import MARKER_PREFIX, SCOPE_TRACE

#
# One space more than the brace's own indentation. Four, because that is what
# every fixture and every project this tool was written for uses; a payload
# that wants something else can write its own leading whitespace and ignore
# {indent}.
#
BODY_INDENT = "    "

#
# The built-in payload. A config's "payloads" table overrides entries by name
# and adds new ones. Leave the table out and this is what inject writes —
# exactly what it wrote before payloads were configurable.
#
BUILT_IN_PAYLOADS = {
    SCOPE_TRACE: {
        "lines": [
            "{indent}ScopeTrace trace(__FILE__, __LINE__, __FUNCTION__);"
        ]
    }
}


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


def build_context(node, label, lines, brace_idx):
    """The facts a template may refer to."""

    parent = owning_class(node)

    return {
        "indent": body_indent(lines, brace_idx),
        "qualified_name": label,
        "function": node.spelling,
        "class": qualified_name(parent) if parent is not None else ""
    }


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
