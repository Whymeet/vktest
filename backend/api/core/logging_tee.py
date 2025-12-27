"""
Logging utilities - TeeOutput for stdout/stderr duplication
"""
import os
import sys
from pathlib import Path


class TeeOutput:
    """Дублирует stdout/stderr в файл и консоль"""

    def __init__(self, log_file_path: Path, original_stream):
        self.log_file_path = log_file_path
        self.original = original_stream
        self.log_file = None
        self._open_file()

    def _open_file(self):
        try:
            self.log_file_path.parent.mkdir(parents=True, exist_ok=True)
            self.log_file = open(self.log_file_path, "a", encoding="utf-8")
        except Exception:
            self.log_file = None

    def write(self, message):
        self.original.write(message)
        if self.log_file:
            try:
                self.log_file.write(message)
                self.log_file.flush()
            except Exception:
                pass

    def flush(self):
        self.original.flush()
        if self.log_file:
            try:
                self.log_file.flush()
            except Exception:
                pass


def setup_tee_logging():
    """Setup stdout/stderr redirection to log file"""
    from api.core.config import IN_DOCKER

    if IN_DOCKER:
        logs_dir = Path("/app/logs")
    else:
        logs_dir = Path(__file__).parent.parent.parent / "logs"

    logs_dir.mkdir(parents=True, exist_ok=True)
    backend_log_file = logs_dir / "backend_all.log"

    sys.stdout = TeeOutput(backend_log_file, sys.__stdout__)
    sys.stderr = TeeOutput(backend_log_file, sys.__stderr__)
