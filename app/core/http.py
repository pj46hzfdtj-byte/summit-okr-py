"""HTTP 客户端：Bearer 注入、ApiResponse 解包、401 自动刷新（对齐 react-desktop lib/http.ts）。"""
from __future__ import annotations

import threading
from typing import Any, Callable, Optional

import requests

from ..config import API_BASE, TIMEOUT


class ApiError(Exception):
    """业务错误（code != 0 或 HTTP 非 2xx）。"""

    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.status = status


class TokenStore:
    """token 持久化（QSettings），进程内共享。"""

    def __init__(self):
        self._lock = threading.Lock()
        self.access: Optional[str] = None
        self.refresh: Optional[str] = None

    def load(self):
        from PySide6.QtCore import QSettings
        s = QSettings()
        self.access = s.value("auth/accessToken") or None
        self.refresh = s.value("auth/refreshToken") or None

    def save(self):
        from PySide6.QtCore import QSettings
        s = QSettings()
        s.setValue("auth/accessToken", self.access or "")
        s.setValue("auth/refreshToken", self.refresh or "")

    def clear(self):
        with self._lock:
            self.access = None
            self.refresh = None
        self.save()

    def set_tokens(self, access: str, refresh: str):
        with self._lock:
            self.access = access
            self.refresh = refresh
        self.save()


tokens = TokenStore()


class HttpClient:
    """同步 HTTP 客户端。仅在 worker 线程中调用（UI 线程禁止直接请求）。"""

    def __init__(self, base_url: str = API_BASE):
        self.base_url = base_url
        self._session = requests.Session()
        self._refresh_lock = threading.Lock()
        self._on_session_expired: Optional[Callable[[], None]] = None

    def set_session_expired_handler(self, cb: Callable[[], None]):
        self._on_session_expired = cb

    # ---------- core ----------
    def _request(self, method: str, path: str, *, params=None, json_body=None, retry=True) -> Any:
        headers = {}
        if tokens.access:
            headers["Authorization"] = f"Bearer {tokens.access}"
        url = f"{self.base_url}{path}"
        try:
            resp = self._session.request(method, url, params=params, json=json_body,
                                         headers=headers, timeout=TIMEOUT)
        except requests.ConnectionError:
            raise ApiError("无法连接后端，请确认服务已启动（localhost:3001）", 0)
        except requests.Timeout:
            raise ApiError("请求超时", 0)

        if resp.status_code == 401 and retry:
            if self._try_refresh():
                return self._request(method, path, params=params, json_body=json_body, retry=False)
            tokens.clear()
            if self._on_session_expired:
                self._on_session_expired()
            raise ApiError("登录已过期，请重新登录", 401)

        try:
            data = resp.json()
        except ValueError:
            raise ApiError(f"响应解析失败（HTTP {resp.status_code}）", resp.status_code)

        if isinstance(data, dict) and "code" in data:
            if data["code"] == 0:
                return data.get("data")
            raise ApiError(data.get("message") or "请求失败", resp.status_code)
        if resp.status_code >= 400:
            raise ApiError(str(data), resp.status_code)
        return data

    def _try_refresh(self) -> bool:
        if not tokens.refresh:
            return False
        with self._refresh_lock:
            # 双检：其他线程可能已刷新成功
            try:
                resp = self._session.post(
                    f"{self.base_url}/auth/refresh",
                    json={"refreshToken": tokens.refresh}, timeout=TIMEOUT)
                data = resp.json()
                if data.get("code") == 0 and data.get("data", {}).get("accessToken"):
                    d = data["data"]
                    tokens.set_tokens(d["accessToken"], d.get("refreshToken", tokens.refresh))
                    return True
            except Exception:
                pass
            return False

    # ---------- verbs ----------
    def get(self, path, params=None):
        return self._request("GET", path, params=params)

    def post(self, path, body=None, params=None):
        return self._request("POST", path, json_body=body, params=params)

    def put(self, path, body=None):
        return self._request("PUT", path, json_body=body)

    def patch(self, path, body=None):
        return self._request("PATCH", path, json_body=body)

    def delete(self, path):
        return self._request("DELETE", path)

    def get_raw(self, path, params=None) -> requests.Response:
        """导出等二进制场景：返回原始 Response。"""
        headers = {}
        if tokens.access:
            headers["Authorization"] = f"Bearer {tokens.access}"
        return self._session.get(f"{self.base_url}{path}", params=params, headers=headers, timeout=TIMEOUT)


http = HttpClient()
