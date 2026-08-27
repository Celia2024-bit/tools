import json

from .payloads import resolve_payloads, validate_rule_payloads


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
    list (mutually exclusive), plus optional "exclude", "include_dirs" and
    "payloads" keys.

    Both modes accept the same rule fields — remove targets exactly what the
    matching inject rule would have added.

    Returns (mode, rules, exclude_rules, include_dirs, payload_table).
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

    payload_table = resolve_payloads(config)

    validate_rule_payloads(
        rules,
        payload_table
    )

    return mode, rules, exclude_rules, include_dirs, payload_table
