import json


def load_config(config_file):

    with open(
        config_file,
        "r",
        encoding="utf-8"
    ) as fp:

        return json.load(fp)


def resolve_mode_and_rules(config):
    """
    New config format: top-level "inject" or "remove" key holds the rule
    list (mutually exclusive), plus optional "exclude" and "include_dirs"
    keys.

    Both modes accept the same rule fields — remove targets exactly what the
    matching inject rule would have added.

    Returns (mode, rules, exclude_rules, include_dirs).
    """

    has_inject = "inject" in config
    has_remove = "remove" in config

    if has_inject and has_remove:
        raise ValueError(
            "config.json cannot contain both \"inject\" and \"remove\" "
            "at the same time — pick one."
        )

    if not has_inject and not has_remove:
        raise ValueError(
            "config.json must contain either an \"inject\" or a "
            "\"remove\" key."
        )

    mode = "inject" if has_inject else "remove"
    rules = config.get(mode, [])
    exclude_rules = config.get("exclude", [])
    include_dirs = config.get("include_dirs", [])

    for exclude_rule in exclude_rules:

        if exclude_rule.get("base_class", ""):
            raise ValueError(
                "\"exclude\" entries cannot specify a \"base_class\" — "
                "excluding works at the directory/file/function level "
                f"only. Offending entry: {exclude_rule}"
            )

    return mode, rules, exclude_rules, include_dirs


#
# Deliberately short. A key here is a promise that something reads it, and the
# last version of this tool shipped configs carrying a "headers" key that
# nothing did — which reads as a feature until you rely on it. Unknown keys are
# rejected rather than ignored so a typo, or a key from a newer config, is loud.
#
HEADERS_KEYS = (
    "types_header",
    "generate_into"
)


def resolve_headers(config):
    """
    The optional "headers" block: where the headers the injected code depends on
    come from.

      types_header   the project's Types.h, which ParameterCheck.h is generated
                     against. Required by any rule asking for "validate".
      generate_into  where to write the generated ParameterCheck.h. Defaults to
                     the directory holding Types.h.

    Kept out of resolve_mode_and_rules so that function's return shape does not
    change every time the config grows a key.
    """

    headers = config.get(
        "headers",
        {}
    )

    if not isinstance(headers, dict):
        raise ValueError(
            "\"headers\" must be an object, e.g. "
            "{ \"types_header\": \"src/Types.h\" }"
        )

    unknown = sorted(
        set(headers) - set(HEADERS_KEYS)
    )

    if unknown:
        raise ValueError(
            f"unknown key(s) in \"headers\": {', '.join(unknown)}. "
            f"Accepted: {', '.join(HEADERS_KEYS)}."
        )

    return headers
