"""Console + session file tee logging utilities."""

import logging
import threading

from .ui_utils import _ANSI_ESCAPE_RE


class TeeLogger:
    def __init__(self, filename, original_stdout):
        self.terminal = original_stdout
        self.log = open(filename, "a", encoding="utf-8")
        self.lock = threading.Lock()
        self._at_line_start = True

    def write(self, message):
        with self.lock:
            try:
                self.terminal.write(message)
            except Exception:
                pass
            try:
                clean = _ANSI_ESCAPE_RE.sub("", message)
                if clean:
                    self.log.write(clean)
                    self.log.flush()
                    self._at_line_start = clean.endswith("\n")
            except Exception:
                pass

    def write_log_line(self, formatted_line):
        with self.lock:
            try:
                if not self.log.closed:
                    if not self._at_line_start:
                        self.log.write("\n")
                    self.log.write(formatted_line + "\n")
                    self.log.flush()
                    self._at_line_start = True
            except Exception:
                pass

    def flush(self):
        with self.lock:
            try:
                self.terminal.flush()
            except Exception:
                pass
            try:
                if not self.log.closed:
                    self.log.flush()
            except Exception:
                pass

    def close(self):
        with self.lock:
            try:
                if not self.log.closed:
                    self.log.flush()
                    self.log.close()
            except Exception:
                pass


class _TeeLogHandler(logging.Handler):
    def __init__(self, tee_logger):
        super().__init__()
        self.tee_logger = tee_logger

    def emit(self, record):
        try:
            msg = self.format(record)
            self.tee_logger.write_log_line(msg)
        except Exception:
            pass
