import json


def load_config(config_file):

    with open(
        config_file,
        "r",
        encoding="utf-8"
    ) as fp:

        return json.load(fp)


#
# Deliberately short. A key here is a promise that something reads it, and this
# tool shipped a "headers" block that nothing read for a while — which looks
# like a feature until you rely on it. So an unrecognised key is an error rather
# than something quietly ignored, and a config left over from the version that
# generated ParameterCheck.h says so instead of silently generating nothing.
#
TOP_LEVEL_KEYS = (
    "inject",
    "remove",
    "exclude",
    "include_dirs"
)


def resolve_mode_and_rules(config):
    """
    Top-level "inject" or "remove" key holds the rule list (mutually
    exclusive), plus optional "exclude" and "include_dirs" keys.

    Both modes accept the same rule fields — remove targets exactly what the
    matching inject rule would have added.

    Returns (mode, rules, exclude_rules, include_dirs).
    """

    unknown = sorted(
        set(config) - set(TOP_LEVEL_KEYS)
    )

    if unknown:
        raise ValueError(
            f"unknown top-level key(s): {', '.join(unknown)}. "
            f"Accepted: {', '.join(TOP_LEVEL_KEYS)}."
        )

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
