from datetime import datetime


class Logger:

    def __init__(self, file_name=None):

        if file_name is None:

            timestamp = datetime.now().strftime(
                "%Y%m%d_%H%M%S"
            )

            file_name = (
                f"interface_sync_{timestamp}.log"
            )

        self.file_name = file_name

        self.fp = open(
            file_name,
            "w",
            encoding="utf-8"
        )

    def log(self, msg=""):

        print(msg)

        self.fp.write(msg)
        self.fp.write("\n")

        self.fp.flush()

    def close(self):

        if self.fp:
            self.fp.close()