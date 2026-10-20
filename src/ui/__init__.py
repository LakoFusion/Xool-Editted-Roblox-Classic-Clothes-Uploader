import atexit
import ctypes
import os
import re
import shutil
import signal
import sys
import threading
import time
from collections import deque

BOLD_WHITE = "\033[1;97m"
CYAN = "\033[1;96m"
GREEN = "\033[1;92m"
YELLOW = "\033[1;93m"
RED = "\033[1;91m"
DIM_GRAY = "\033[90m"
RESET = "\033[0m"

HIDE_CURSOR = "\033[?25l"
SHOW_CURSOR = "\033[?25h"
HOME = "\033[H"
CLEAR_BELOW = "\033[J"
ERASE_LINE = "\033[K"

ANSI_PATTERN = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
BOX_TRANSLATION = {
    0x256D: "-", 0x256E: "-", 0x2570: "-", 0x256F: "-",
    0x2502: "|", 0x250C: "-", 0x2510: "-", 0x2514: "-", 0x2518: "-",
    0x251C: "-", 0x2524: "-", 0x252C: "-", 0x2534: "-", 0x253C: "-",
    0x2500: "-", 0x2501: "-", 0x2503: "|", 0x2554: "-", 0x2557: "-",
    0x255A: "-", 0x255D: "-", 0x2551: "|", 0x2550: "-",
}


def enable_windows_ansi():
    if os.name != "nt":
        return
    try:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass


class LogStream:
    def __init__(self, ui, fallback):
        self.ui = ui
        self.fallback = fallback
        self.buffer = ""
        self.lock = threading.Lock()

    def write(self, text):
        try:
            if not text:
                return 0
            if not self.ui.active:
                self.fallback.write(text)
                return len(text)
            with self.lock:
                self.buffer += text
                while "\n" in self.buffer:
                    line, self.buffer = self.buffer.split("\n", 1)
                    if line.strip():
                        self.ui.log(line)
            return len(text)
        except Exception:
            return len(text or "")

    def flush(self):
        try:
            with self.lock:
                if self.buffer.strip():
                    self.ui.log(self.buffer)
                self.buffer = ""
            self.fallback.flush()
        except Exception:
            pass

    def isatty(self):
        try:
            return bool(getattr(self.fallback, "isatty", lambda: False)())
        except Exception:
            return False

    def __getattr__(self, name):
        return getattr(self.fallback, name)


class ConsoleUI:
    def __init__(self, tool_name="Clothes Uploader Roblox", version="1.0", refresh_interval=0.5):
        self.tool_name = tool_name
        self.version = version
        self.refresh_interval = max(0.2, float(refresh_interval))
        self.lock = threading.RLock()
        self.write_lock = threading.Lock()
        self.state = {
            "status": "Starting",
            "account": "N/A",
            "target": "N/A",
            "mode": "N/A",
            "uploaded": 0,
            "remaining": 0,
            "skipped": 0,
            "failed": 0,
            "pending": 0,
            "round": 0,
            "candidates": 0,
        }
        self.logs = deque(maxlen=5)
        self.started_at = None
        self.stop_event = threading.Event()
        self.thread = None
        self.active = False
        self.color = os.environ.get("NO_COLOR") is None
        self.original_stdout = None
        self.stream = None
        self.previous_sigint = None
        self.started = False
        self.render_failed = False
        self.atexit_callback = self.stop

    def start(self):
        if self.active:
            return True
        if not self.color:
            return False
        try:
            if not sys.stdout.isatty():
                return False
            enable_windows_ansi()
            self.original_stdout = sys.stdout
            self.stream = LogStream(self, self.original_stdout)
            self.stop_event = threading.Event()
            self.started_at = time.time()
            self.active = True
            self.started = True
            self.set_status("Running")
            sys.stdout = self.stream
            self.install_signals()
            atexit.register(self.atexit_callback)
            self.write(HIDE_CURSOR)
            self.thread = threading.Thread(target=self.loop, name="console-ui", daemon=True)
            self.thread.start()
            return True
        except Exception:
            self.active = False
            self.started = False
            if self.original_stdout is not None:
                sys.stdout = self.original_stdout
            return False

    def stop(self):
        if not self.started:
            return
        self.started = False
        try:
            self.stop_event.set()
            thread = self.thread
            if thread is not None and thread is not threading.current_thread():
                thread.join(timeout=max(1.0, self.refresh_interval * 3))
            if self.stream is not None:
                self.stream.flush()
            self.active = False
            if self.original_stdout is not None and sys.stdout is self.stream:
                sys.stdout = self.original_stdout
            self.restore_signals()
            try:
                atexit.unregister(self.atexit_callback)
            except Exception:
                pass
            self.set_status("Stopped")
            self.render(force=True)
            self.write(SHOW_CURSOR + "\n")
        except Exception:
            try:
                if self.original_stdout is not None:
                    sys.stdout = self.original_stdout
            except Exception:
                pass

    def install_signals(self):
        try:
            self.previous_sigint = signal.getsignal(signal.SIGINT)
            signal.signal(signal.SIGINT, self.handle_sigint)
        except Exception:
            self.previous_sigint = None

    def restore_signals(self):
        try:
            if self.previous_sigint is not None:
                signal.signal(signal.SIGINT, self.previous_sigint)
        except Exception:
            pass

    def handle_sigint(self, signum, frame):
        self.stop()
        previous = self.previous_sigint
        if callable(previous) and previous is not self.handle_sigint:
            previous(signum, frame)
        else:
            raise KeyboardInterrupt

    def loop(self):
        while not self.stop_event.wait(self.refresh_interval):
            self.render()

    def set_status(self, value):
        self.set_metric("status", value)

    def set_identity(self, account=None, target=None, mode=None):
        try:
            with self.lock:
                if account is not None:
                    self.state["account"] = account
                if target is not None:
                    self.state["target"] = target
                if mode is not None:
                    self.state["mode"] = mode
        except Exception:
            pass

    def set_metric(self, key, value):
        try:
            with self.lock:
                self.state[key] = value
        except Exception:
            pass

    def incr_metric(self, key, amount=1):
        try:
            with self.lock:
                current = self.state.get(key, 0)
                if not isinstance(current, (int, float)) or isinstance(current, bool):
                    current = 0
                self.state[key] = current + amount
        except Exception:
            pass

    def log(self, message, level=None):
        try:
            text = self.clean(message)
            if not text:
                return
            if level is None:
                level = self.infer_level(text)
            entry = (time.strftime("%H:%M:%S"), level, text)
            with self.lock:
                self.logs.append(entry)
        except Exception:
            pass

    def clean(self, message):
        try:
            text = ANSI_PATTERN.sub("", str(message))
            text = text.translate(BOX_TRANSLATION)
            text = text.replace("\r", " ").replace("\n", " ").replace("\t", " ")
            return " ".join(text.split())
        except Exception:
            return ""

    def infer_level(self, text):
        lower = text.lower()
        if any(word in lower for word in ("error", "failed", "exception", "traceback", "denied")):
            return "error"
        if any(word in lower for word in ("warn", "skip", "rejected", "waiting", "cooldown", "rate limit", "retry")):
            return "warn"
        if any(word in lower for word in ("released", "sold", "ok", "success", "enhanced", "downloaded", "complete")):
            return "success"
        return "info"

    def paint(self, code, text, enabled=True):
        if not enabled:
            return text
        return f"{code}{text}{RESET}"

    def fit(self, text, width):
        try:
            text = str(text)
            width = max(8, int(width))
            if len(text) <= width:
                return text
            return text[: max(1, width - 3)] + "..."
        except Exception:
            return ""

    def number(self, value):
        try:
            if value is None:
                return "0"
            if isinstance(value, bool):
                return str(value)
            if isinstance(value, int):
                return f"{value:,}"
            if isinstance(value, float):
                return f"{value:,.2f}"
            return str(value)
        except Exception:
            return "0"

    def uptime(self):
        try:
            started = self.started_at
            if started is None:
                return "00:00:00"
            total = max(0, int(time.time() - started))
            hours = total // 3600
            minutes = (total % 3600) // 60
            seconds = total % 60
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        except Exception:
            return "00:00:00"

    def status_color(self, status):
        if status == "Running":
            return GREEN
        if status == "Stopped":
            return RED
        return YELLOW

    def level_color(self, level):
        if level == "success":
            return GREEN
        if level == "warn":
            return YELLOW
        if level == "error":
            return RED
        return BOLD_WHITE

    def field(self, label, value, color, use_color):
        try:
            if value is None:
                value = "N/A"
            width = shutil.get_terminal_size((80, 24)).columns
            value_text = self.fit(value, max(16, width - 15))
            label_text = self.fit(label, 11).ljust(11)
            return (
                self.paint(CYAN, label_text, use_color)
                + self.paint(DIM_GRAY, ":", use_color)
                + " "
                + self.paint(color, value_text, use_color)
            )
        except Exception:
            return f"{label}: N/A"

    def build_frame(self, color=None):
        try:
            with self.lock:
                return "\n".join(self.build_lines(color))
        except Exception:
            return ""

    def build_lines(self, color=None):
        use_color = self.color if color is None else color
        state = getattr(self, "state", {}) or {}
        logs = list(getattr(self, "logs", []) or [])
        status = str(state.get("status") or "N/A")
        lines = []

        lines.append(
            self.paint(BOLD_WHITE, str(getattr(self, "tool_name", "Clothes Uploader Roblox")), use_color)
            + "  "
            + self.paint(DIM_GRAY, "v" + str(getattr(self, "version", "1.0")), use_color)
        )
        lines.append(self.field("Status", status, self.status_color(status), use_color))
        lines.append(self.field("Uptime", self.uptime(), BOLD_WHITE, use_color))

        lines.append("")

        lines.append(self.field("Account", state.get("account", "N/A"), BOLD_WHITE, use_color))
        lines.append(self.field("Target", state.get("target", "N/A"), BOLD_WHITE, use_color))
        lines.append(self.field("Mode", state.get("mode", "N/A"), BOLD_WHITE, use_color))

        lines.append("")

        for key in ("uploaded", "remaining", "skipped", "failed", "pending", "round", "candidates"):
            lines.append(self.field(key.capitalize(), self.number(state.get(key, 0)), BOLD_WHITE, use_color))

        lines.append("")

        lines.append(self.paint(CYAN, "Recent activity", use_color))
        for index in range(5):
            if index < len(logs):
                try:
                    timestamp, level, message = logs[index]
                except Exception:
                    continue
                width = shutil.get_terminal_size((80, 24)).columns
                lines.append(
                    self.paint(DIM_GRAY, f"[{timestamp}]", use_color)
                    + " "
                    + self.paint(DIM_GRAY, ">", use_color)
                    + " "
                    + self.paint(self.level_color(level), self.fit(message, max(16, width - 14)), use_color)
                )
            else:
                lines.append("")

        lines.append(self.paint(DIM_GRAY, "[Ctrl+C to stop]", use_color))
        return lines

    def render(self, force=False):
        if not self.active and not force:
            return
        try:
            frame = self.build_frame()
            if not frame:
                return
            body = HOME + "\n".join(line + ERASE_LINE for line in frame.split("\n")) + CLEAR_BELOW
            self.write(body)
        except Exception:
            if not self.render_failed:
                self.render_failed = True

    def write(self, text):
        try:
            with self.write_lock:
                output = self.original_stdout or sys.stdout
                try:
                    output.write(text)
                    output.flush()
                except UnicodeEncodeError:
                    encoding = getattr(output, "encoding", None) or "utf-8"
                    safe = text.encode(encoding, "replace").decode(encoding, "replace")
                    output.write(safe)
                    output.flush()
        except Exception:
            pass
