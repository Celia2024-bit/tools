import sys
from datetime import datetime


def force_utf8_stdout():
    """
    The log lines carry emoji, and on Windows stdout falls back to the ANSI
    code page (cp1252) whenever it is not a console — a pipe, a `>` redirect,
    a CI runner. print() then dies with UnicodeEncodeError halfway through the
    run, having already written half the files.

    errors="replace" is the belt to the UTF-8 braces: a terminal that cannot
    render a glyph should cost a question mark, never a crash. No-op when
    stdout is already UTF-8, and quietly skipped on the older/odder streams
    that have no reconfigure().
    """

    try:
        sys.stdout.reconfigure(
            encoding="utf-8",
            errors="replace"
        )
    except (AttributeError, OSError, ValueError):
        pass


class Logger:

    def __init__(self):

        force_utf8_stdout()

        timestamp = datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )

        self.log_file = (
            f"trace_injector_{timestamp}.log"
        )

        self.fp = open(
            self.log_file,
            "w",
            encoding="utf-8"
        )

    def log(self, msg=""):

        print(msg)

        self.fp.write(msg)
        self.fp.write("\n")

        self.fp.flush()

    def close(self):

        self.fp.close()
