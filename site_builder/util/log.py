"""CLI logging：彩色等級、時間戳，以及執行結束時的 WARNING/ERROR 摘要。

由 build.py 在進入點呼叫 ``setup_logging``，結束時呼叫 ``log_run_summary``。
site_builder 其他模組只用標準 ``logging.getLogger(__name__)``，不需要知道這裡。
"""

import logging
import os
import sys
from collections import Counter

_RESET = "\033[0m"
_DIM = "\033[2m"
_LEVEL_COLORS = {
    logging.DEBUG: _DIM,
    logging.WARNING: "\033[33m",
    logging.ERROR: "\033[31m",
    logging.CRITICAL: "\033[1;31m",
}
_PKG_PREFIX = "site_builder."
# 最長的常見 logger 名稱（sync.statcast、api.league_stats）剛好放得下；更長的直接溢出，不截斷
_NAME_WIDTH = 16
# 摘要每一類只列第一則訊息當範例，過長的 URL/例外訊息截斷，避免摘要本身洗版
_SUMMARY_EXAMPLE_MAX = 240


def describe_exc(exc: BaseException) -> str:
    """``ReadTimeout: HTTPSConnectionPool(...)``：帶例外類型，KeyError 這類 ``str(e)`` 只剩 ``'teams'`` 的也看得懂。"""
    text = str(exc)
    name = type(exc).__name__
    return f"{name}: {text}" if text else name


def _use_color(stream) -> bool:
    """TTY 才上色；NO_COLOR（https://no-color.org）強制關閉，FORCE_COLOR 強制開啟。

    GitHub Actions 的 stdout 不是 TTY，但它的 log 檢視器會渲染 ANSI 碼，
    需要時可在 workflow 設 ``FORCE_COLOR=1``。
    """
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return hasattr(stream, "isatty") and stream.isatty()


class ColorFormatter(logging.Formatter):
    """``HH:MM:SS LEVEL   module           message``，等級依嚴重度上色。

    欄寬在上色前先補齊：ANSI 碼不佔顯示寬度，先上色再補空白會讓欄位對不齊。
    """

    def __init__(self, color: bool):
        super().__init__(datefmt="%H:%M:%S")
        self._color = color

    def format(self, record: logging.LogRecord) -> str:
        time_str = self.formatTime(record, self.datefmt)
        level = f"{record.levelname:<7}"
        name = f"{record.name.removeprefix(_PKG_PREFIX):<{_NAME_WIDTH}}"
        message = record.getMessage()
        if record.exc_info:
            message = f"{message}\n{self.formatException(record.exc_info)}"
        if self._color:
            level_color = _LEVEL_COLORS.get(record.levelno)
            time_str = f"{_DIM}{time_str}{_RESET}"
            name = f"{_DIM}{name}{_RESET}"
            if level_color:
                level = f"{level_color}{level}{_RESET}"
                if record.levelno >= logging.WARNING:
                    message = f"{level_color}{message}{_RESET}"
        return f"{time_str} {level} {name} {message}"


class _ProblemCollector(logging.Handler):
    """統計每一類 WARNING/ERROR 出現次數，供結尾摘要。

    以 (等級, logger, 訊息模板) 分組：同一個 ``logger.warning("... %s", x)`` 呼叫點
    不論參數為何都算同一類，摘要才不會變成逐行重印。``Handler.handle`` 會先取鎖
    再呼叫 ``emit``，多執行緒同時記錄也安全。
    """

    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.counts: Counter = Counter()
        self.examples: dict[tuple, str] = {}

    def emit(self, record: logging.LogRecord) -> None:
        key = (record.levelno, record.name, str(record.msg))
        self.counts[key] += 1
        self.examples.setdefault(key, record.getMessage())


class _DropUrllib3RetryWarnings(logging.Filter):
    """丟掉 urllib3 自己的 ``Retrying (Retry(...)) after connection broken`` 訊息。

    重試改由 ``api/client.py`` 的 ``_LoggingRetry`` 統一記錄（含 429/5xx 狀態碼重試，
    urllib3 對那種只記 DEBUG）；不濾掉的話連線錯誤的重試會印兩行。
    其他 urllib3 警告（例如 connection pool 已滿）照常輸出。
    """

    def filter(self, record: logging.LogRecord) -> bool:
        return not str(record.msg).startswith("Retrying (")


_collector = _ProblemCollector()


def setup_logging(level: int = logging.INFO) -> None:
    """設定 root logger：彩色輸出到 stderr，並掛上摘要統計。重複呼叫不會重複加 handler。"""
    root = logging.getLogger()
    root.setLevel(level)
    if _collector in root.handlers:
        return
    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setFormatter(ColorFormatter(_use_color(sys.stderr)))
    root.addHandler(stream_handler)
    root.addHandler(_collector)
    logging.getLogger("urllib3.connectionpool").addFilter(_DropUrllib3RetryWarnings())


def log_run_summary() -> None:
    """印出本次執行所有 WARNING/ERROR 的分類統計（依次數由多到少）。

    只做報告，不影響 exit code：API 暫時失敗時 DB 保留舊值，下次執行會重抓，
    不需要讓整個 pipeline 失敗。
    """
    counts = _collector.counts
    logger = logging.getLogger(__name__)
    if not counts:
        logger.info("Run summary: no warnings or errors")
        return
    n_warn = sum(n for (lvl, _, _), n in counts.items() if lvl < logging.ERROR)
    n_err = sum(n for (lvl, _, _), n in counts.items() if lvl >= logging.ERROR)
    lines = [f"Run summary: {n_warn} warning(s), {n_err} error(s)"]
    for key, n in counts.most_common():
        lvl, name, _ = key
        example = _collector.examples[key].splitlines()[0]
        if len(example) > _SUMMARY_EXAMPLE_MAX:
            example = example[:_SUMMARY_EXAMPLE_MAX] + "..."
        lines.append(
            f"  {n:>4}x {logging.getLevelName(lvl):<7} "
            f"{name.removeprefix(_PKG_PREFIX)}: {example}"
        )
    # 摘要本身用 INFO 輸出，不會被 _collector 計入
    logger.info("\n".join(lines))
