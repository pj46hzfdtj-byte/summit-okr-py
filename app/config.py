"""应用级配置：后端地址、超时、持久化键。"""
from __future__ import annotations

import os

# 后端 API 根地址（与桌面端 VITE_API_BASE 对齐，可用环境变量覆盖）
API_BASE = os.environ.get("SUMMITOKR_API_BASE", "http://localhost:3001/api")
TIMEOUT = 15  # 秒

APP_NAME = "Summit OKR"
APP_TITLE = "甘特图 - Summit OKR"
ORG_NAME = "Summit OKR"

# QSettings 组织/应用（token 与外观持久化）
SETTINGS_ORG = "summitokr"
SETTINGS_APP = "py-desktop"

# 演示账号（登录页预填，与其他端一致）
DEMO_EMAIL = "demo@summitokr.com"
DEMO_PASSWORD = "password123"
