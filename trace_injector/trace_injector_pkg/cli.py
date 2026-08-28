import argparse
from pathlib import Path

from .logger import Logger

from .config import load_config, resolve_headers, resolve_mode_and_rules
from .preflight import prepare_parameter_check
from .processor import process_rule


def cleanup_logs():

    for file in Path.cwd().glob(
        "trace_injector_*.log"
    ):
        try:
            file.unlink()
        except Exception:
            pass


def main():
    """
    Returns the process exit code: 0 for a run that did what it was asked,
    non-zero for one that refused. A build step invoking this needs to be able
    to tell those apart without reading the log.
    """

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--config",
        default="config.json"
    )

    args = parser.parse_args()

    cleanup_logs()

    logger = Logger()

    config = load_config(
        args.config
    )

    mode, rules, exclude_rules, include_dirs = resolve_mode_and_rules(config)

    headers = resolve_headers(config)

    stats = {
        "files_scanned": 0,
        "files_modified": 0,
        "files_excluded": 0,
        "trace_injected": 0,
        "trace_removed": 0
    }

    logger.log(
        "================================================="
    )

    logger.log(
        "Trace Injector v1.2"
    )

    logger.log(
        f"Mode: {mode}"
    )

    logger.log(
        "================================================="
    )

    #
    # Before the first file, not after: an injection that cannot compile is
    # worse than no injection, and undoing one costs a second run.
    #
    if not prepare_parameter_check(
        mode,
        rules,
        headers,
        logger
    ):

        logger.log()
        logger.log(
            f"Log written to: {logger.log_file}"
        )

        logger.close()

        return 1

    for rule in rules:

        process_rule(
            rule,
            mode,
            exclude_rules,
            logger,
            stats,
            include_dirs=include_dirs
        )

    logger.log()
    logger.log(
        "================================================="
    )

    logger.log(
        "Summary"
    )

    logger.log(
        "================================================="
    )

    logger.log(
        f"Files Scanned  : {stats['files_scanned']}"
    )

    logger.log(
        f"Files Modified : {stats['files_modified']}"
    )

    logger.log(
        f"Files Excluded : {stats['files_excluded']}"
    )

    logger.log(
        f"Trace Injected : {stats['trace_injected']}"
    )

    logger.log(
        f"Trace Removed  : {stats['trace_removed']}"
    )

    logger.log()
    logger.log(
        f"Log written to: {logger.log_file}"
    )

    logger.close()

    return 0
