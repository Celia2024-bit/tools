import argparse
from pathlib import Path

from .logger import Logger

from .config import load_config, resolve_mode_and_rules
from .libclang import configure as configure_libclang
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
    Returns the process exit code: 0 for a run that did what it was asked. A
    config this tool will not accept raises out of here rather than returning,
    so a build step sees a non-zero exit either way.
    """

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--config",
        default="config.json"
    )

    args = parser.parse_args()

    #
    # Before the logger, so a run that cannot parse anything at all fails with
    # its message on stderr and no half-written log file to explain.
    #
    libclang = configure_libclang()

    cleanup_logs()

    logger = Logger()

    config = load_config(
        args.config
    )

    mode, rules, exclude_rules, include_dirs = resolve_mode_and_rules(config)

    stats = {
        "files_scanned": 0,
        "files_modified": 0,
        "files_excluded": 0,
        "trace_injected": 0,
        "trace_removed": 0,
        "includes_added": 0,
        "includes_removed": 0
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

    #
    # Only when it had to be searched for. Which libclang answered is the first
    # thing worth knowing when a base_class rule matches nothing, and the log is
    # the only place that survives the run.
    #
    if libclang:

        logger.log(
            f"libclang: {libclang}"
        )

    logger.log(
        "================================================="
    )

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

    logger.log(
        f"Includes Added : {stats['includes_added']}"
    )

    logger.log(
        f"Includes Gone  : {stats['includes_removed']}"
    )

    logger.log()
    logger.log(
        f"Log written to: {logger.log_file}"
    )

    logger.close()

    return 0
