from datetime import datetime


class Logger:

    def __init__(self):

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