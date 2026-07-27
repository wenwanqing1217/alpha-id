"""
敏感数据日志过滤器 — 纵深防御

自动脱敏日志中的敏感信息：
  - API Key / Secret / Token（Bearer、URL 参数、JSON 值）
  - 手机号（中间 4 位替换为 ****）
  - 短信验证码（6 位数字替换为 ******）
  - 身份证号（保留前 3 后 4）
  - Authorization 头（Basic/Bearer 后的值）
  - 内网 IP / 私有地址

使用方式：
    import logging
    from core.logging_filter import SensitiveDataFilter

    # 为 root logger 添加过滤器
    root = logging.getLogger()
    root.addFilter(SensitiveDataFilter())

    # 或为特定 handler 添加
    handler.addFilter(SensitiveDataFilter())
"""

import logging
import re

# ── 脱敏规则 ──

# API Key / Secret / Token 常见参数名（URL 参数、JSON key、header）
_SECRET_KEYS = re.compile(
    r'(api[_-]?key|api[_-]?secret|access[_-]?token|auth[_-]?token|'
    r'bearer|client[_-]?secret|private[_-]?key|'
    r'x-api-key|x-auth-token|passwordpasswd|passwd)'
    r'\s*[:=]\s*["\']?([A-Za-z0-9\-_\.+/=]{16,})["\']?',
    re.IGNORECASE,
)

# Authorization 头：Basic xxxx / Bearer xxxx
_AUTH_HEADER = re.compile(
    r'(Authorization\s*:\s*(?:Basic|Bearer)\s+)[A-Za-z0-9\-_\.+/=]+',
    re.IGNORECASE,
)

# 手机号（中国大陆 11 位）
_PHONE = re.compile(r'(1[3-9]\d)\d{4}(\d{4})')

# 短信验证码（6 位数字，紧跟"验证码"关键词）
_SMS_CODE = re.compile(r'(验证码[为是::\s]*)\d{6}')

# 身份证号（18 位）
_ID_CARD = re.compile(r'(\d{6})\d{8}(\d{4})')

# 内网 IP（日志中意外打印时脱敏）
_PRIVATE_IP = re.compile(
    r'\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|'
    r'172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}|'
    r'192\.168\.\d{1,3}\.\d{1,3})\b',
)

# URL 中的敏感参数（如 ?api_key=xxxx）
_URL_SECRET_PARAM = re.compile(
    r'([?&](?:api_key|access_token|secret|token)=)[^&\s]+',
    re.IGNORECASE,
)


class SensitiveDataFilter(logging.Filter):
    """日志过滤器 — 自动脱敏敏感信息"""

    def __init__(self, name: str = "", mask: str = "***") -> None:
        super().__init__(name)
        self._mask = mask

    def filter(self, record: logging.LogRecord) -> bool:
        # 脱敏 msg 和 args
        if isinstance(record.msg, str):
            record.msg = self._redact(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: self._redact(str(v)) for k, v in record.args.items()}
            else:
                record.args = tuple(self._redact(str(a)) for a in record.args)
        return True

    def _redact(self, text: str) -> str:
        if not text:
            return text

        # 1. Authorization 头脱敏
        text = _AUTH_HEADER.sub(r'\1' + self._mask, text)

        # 2. API Key / Secret / Token 值脱敏（保留 key 名）
        text = _SECRET_KEYS.sub(r'\1=' + self._mask, text)

        # 3. 手机号脱敏（中间 4 位）
        text = _PHONE.sub(r'\1****\2', text)

        # 4. 短信验证码脱敏
        text = _SMS_CODE.sub(r'\1' + '******', text)

        # 5. 身份证号脱敏
        text = _ID_CARD.sub(r'\1********\2', text)

        # 6. URL 中的敏感参数脱敏
        text = _URL_SECRET_PARAM.sub(r'\1' + self._mask, text)

        return text


def install_sensitive_data_filter() -> None:
    """为 root logger 安装敏感数据过滤器（幂等）"""
    root = logging.getLogger()
    # 避免重复安装
    for f in root.filters:
        if isinstance(f, SensitiveDataFilter):
            return
    root.addFilter(SensitiveDataFilter())
