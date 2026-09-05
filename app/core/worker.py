"""异步任务：QThreadPool 中执行网络请求，结果经信号回主线程。

用法：
    w = run_async(lambda: api.summary_get(), on_ok=self._apply)
    # w.busy 期间可禁用按钮；w.finished 信号在成功/失败后都会触发
"""
from __future__ import annotations

import traceback
from typing import Any, Callable, Optional

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot


class _Signals(QObject):
    ok = Signal(object)
    err = Signal(str)
    finished = Signal()


class Worker(QRunnable):
    def __init__(self, fn: Callable[[], Any]):
        super().__init__()
        self.fn = fn
        self.signals = _Signals()
        self.setAutoDelete(True)

    @Slot()
    def run(self):
        try:
            result = self.fn()
        except Exception as e:  # noqa: BLE001
            from .http import ApiError
            if not isinstance(e, ApiError):
                traceback.print_exc()
            self.signals.err.emit(str(e))
        else:
            self.signals.ok.emit(result)
        finally:
            self.signals.finished.emit()


_pool = QThreadPool.globalInstance()

# 持有 Worker 引用，防止 QRunnable 在信号投递前被 C++ 侧销毁
# （autoDelete 会在 run() 结束后立即删除 _Signals，导致 ok/err 永远收不到）
_keepalive: set = set()


def run_async(fn: Callable[[], Any],
              on_ok: Optional[Callable[[Any], None]] = None,
              on_err: Optional[Callable[[str], None]] = None,
              on_finished: Optional[Callable[[], None]] = None) -> Worker:
    """提交后台任务；回调均在主线程执行。返回 Worker 以便挂接 busy 状态。"""
    w = Worker(fn)
    w.setAutoDelete(False)
    _keepalive.add(w)
    if on_ok:
        w.signals.ok.connect(on_ok)
    w.signals.err.connect(lambda msg: (on_err(msg) if on_err else _default_error(msg)))
    if on_finished:
        w.signals.finished.connect(on_finished)
    w.signals.finished.connect(lambda: _keepalive.discard(w))
    _pool.start(w)
    return w


def _default_error(msg: str):
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    toast = getattr(app, "vis_toast", None) if app else None
    if toast:
        toast.error(msg)
    else:
        print("[api error]", msg)
