# -*- coding: utf-8 -*-
"""PAY.153 协议支付服务配置。"""
from config.env_loader import apply_env_overrides

# 外部 PAY.153 子项目地址；client 会自动补齐 /api。
PAY153_API_BASE: str = "http://127.0.0.1:8080"

# 是否允许 GPT Registrator 调用 PAY.153。
PAY153_ENABLED: bool = True

# Registrator -> PAY.153 单次 HTTP 请求超时。
PAY153_REQUEST_TIMEOUT: int = 30

# 创建协议支付任务时的默认参数，前端/调用方可在 body 中覆盖。
PAY153_DEFAULT_COUNTRY: str = "BR"
PAY153_DEFAULT_BUYER_MODE: str = "identity_elevation"
PAY153_DEFAULT_AGREEMENT_ONLY: bool = False

apply_env_overrides(globals(), {
    "PAY153_API_BASE": "str",
    "PAY153_ENABLED": "bool",
    "PAY153_REQUEST_TIMEOUT": "int",
    "PAY153_DEFAULT_COUNTRY": "str",
    "PAY153_DEFAULT_BUYER_MODE": "str",
    "PAY153_DEFAULT_AGREEMENT_ONLY": "bool",
})
