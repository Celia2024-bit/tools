"""
What has to be true before a single .cpp is touched.

A rule asking for "validate" writes calls to validate_params(), and those only
exist if ParameterCheck.h has been generated against *this* project's Types.h.
So generating it is the first action of the run rather than a step the caller is
trusted to have remembered, and a Types.h the generator rejects aborts the run
before anything is modified.

The generator lives in the sibling parameters_check tool and is used as a
library: generate_and_deploy() returns False instead of exiting, and it writes
nothing at all when validation fails. Paired with aborting here, a rejected run
leaves both trees exactly as it found them.
"""

import contextlib
import importlib.util
import io

from pathlib import Path

from .constants import normalize_inject_types

VALIDATE_KIND = "validate"

MODULE_NAME = "parameters_check_generator"

#
# tools/trace_injector/trace_injector_pkg/preflight.py -> tools/
#
GENERATOR_PATH = (
    Path(__file__).resolve().parents[2]
    / "parameters_check"
    / "generate_parameter_check.py"
)


def rules_want_validate(rules):
    """Whether any rule in this run asks for a validate block."""

    for rule in rules:

        wanted = normalize_inject_types(
            rule.get("inject_type")
        )

        if VALIDATE_KIND in wanted:
            return True

    return False


def _log_block(logger, text):
    """Replay captured generator output into the log, so it is in both places."""

    for line in text.splitlines():
        logger.log(f"   {line}")


def _load_generator(logger):

    if not GENERATOR_PATH.exists():

        logger.log(
            "   ❌ ParameterCheck generator not found at: "
            f"{GENERATOR_PATH}"
        )

        logger.log(
            "   ❌ It ships in the parameters_check tool next to this one."
        )

        return None

    spec = importlib.util.spec_from_file_location(
        MODULE_NAME,
        GENERATOR_PATH
    )

    module = importlib.util.module_from_spec(spec)

    try:
        spec.loader.exec_module(module)

    except Exception as exc:
        #
        # Almost always a missing jinja2, which the generator imports at module
        # level. Worth naming: it is the one dependency this tool does not have
        # until a rule asks for "validate".
        #
        logger.log(
            f"   ❌ ParameterCheck generator could not be loaded: {exc}"
        )

        logger.log(
            "   ❌ It needs jinja2 — pip install jinja2"
        )

        return None

    return module


def prepare_parameter_check(
    mode,
    rules,
    headers,
    logger
):
    """
    Generate ParameterCheck.h if this run needs it. Returns False to abort.

    Nothing to do unless we are injecting and at least one rule asks for
    "validate" — a trace-only run has no reason to require a Types.h, and a
    remove run needs no headers at all to take code back out.
    """

    if mode != "inject":
        return True

    if not rules_want_validate(rules):
        return True

    types_header = headers.get(
        "types_header",
        ""
    )

    if not types_header:

        logger.log(
            "   ❌ A rule asks for \"validate\", which calls validate_params()"
        )

        logger.log(
            "   ❌ from a generated ParameterCheck.h. Point "
            "\"headers\": { \"types_header\": ... }"
        )

        logger.log(
            "   ❌ at the project's Types.h so it can be generated."
        )

        return False

    types_path = Path(types_header)

    generate_into = Path(
        headers.get("generate_into")
        or
        types_path.parent
    )

    module = _load_generator(logger)

    if module is None:
        return False

    logger.log()
    logger.log(
        f"⚙️ Generating ParameterCheck.h from: {types_path}"
    )

    #
    # The generator prints; this tool logs. Capturing keeps the two halves of a
    # rejected run in one place, which matters because the reason for the abort
    # is in the generator's output, not in ours.
    #
    captured = io.StringIO()

    with contextlib.redirect_stdout(captured):

        generated = module.generate_and_deploy(
            types_path,
            generate_into
        )

    _log_block(
        logger,
        captured.getvalue()
    )

    if not generated:

        logger.log(
            "   ❌ Types.h was rejected, so validate_params() would not "
            "compile against it."
        )

        logger.log(
            "   ❌ Nothing was injected. Fix the types, or drop \"validate\" "
            "from the rule."
        )

    return generated
