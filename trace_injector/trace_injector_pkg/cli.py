import argparse
from pathlib import Path

from logger import Logger

from .config import load_config
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
    mode = config.get(
        "mode",
        "inject_trace"
    )
    stats = {
        "files_scanned": 0,
        "files_modified": 0,
        "trace_injected": 0,
        "trace_removed": 0
    }

    logger.log(
        "================================================="
    )

    logger.log(
        "Trace Injector v1.1"
    )

    logger.log(
        "================================================="
    )

    for rule in config.get(
        "rules",
        []
    ):

        process_rule(
            rule,
            mode,
            logger,
            stats
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
        f"Trace Injected : {stats['trace_injected']}"
    )

    logger.log()
    logger.log(
        f"Log written to: {logger.log_file}"
    )

    logger.log(
        f"Trace Removed : "
        f"{stats['trace_removed']}"
    )

    logger.close()
