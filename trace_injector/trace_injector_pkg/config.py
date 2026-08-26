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
    list (mutually exclusive), plus an optional "exclude" key.

    Returns (mode, rules, exclude_rules).
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

    return mode, rules, exclude_rules
