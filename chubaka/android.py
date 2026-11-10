import logging
import os
import sys

from lysyk.engine import _native
from chubaka.app import main


class LogStream:
    def __init__(self, level):
        self.level = level
        self.buffer = ""

    def write(self, text):
        self.buffer += text
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            if line.strip():
                _native.log_line(self.level, line)
        return len(text)

    def flush(self):
        if self.buffer.strip():
            _native.log_line(self.level, self.buffer)
        self.buffer = ""


def run():
    os.makedirs(os.path.join(os.environ.get("XDG_DATA_HOME", "."), "ChubakaSOD"), exist_ok=True)
    sys.stdout = LogStream(0)
    sys.stderr = LogStream(1)
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    main(["--fullscreen"])
