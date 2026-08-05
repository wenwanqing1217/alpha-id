"""
Alpha-ID 统一配置管理 — 基于 pydantic-settings

所有环境变量、默认值、类型校验都集中在这里。
各模块通过 `from core.settings import settings` 读取配置，
不再散落使用 os.getenv()。

向后兼容：支持旧环境变量名（如 OPENAI_API_KEY, LLM_API_KEY）。
"""

import os
import threading
from pathlib import Path
from typing import ClassVar, Dict, List, Optional

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.secrets import decrypt_if_needed

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"

_settings_lock = threading.Lock()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ClassVar 不被 pydantic 视为字段，可安全用作实例级存储
    _callbacks: ClassVar[List] = []

    def on_change(self, callback):
        """注册配置变更回调 — 当 reload_settings() 触发时，回调接收变更字段名列表。"""
        with _settings_lock:
            self._callbacks.append(callback)

    # ── 应用基础 ──
    app_name: str = "Alpha-ID"
    app_version: str = "0.3.3"
    debug: bool = False
    environment: str = "development"
    log_level: str = Field(default="INFO", validation_alias=AliasChoices("LOG_LEVEL"))
    allowed_origins: str = Field(
        default="http://localhost:3000,http://localhost:8000,http://127.0.0.1:3000,http://127.0.0.1:8000",
        validation_alias=AliasChoices("AID_ALLOWED_ORIGINS", "ALLOWED_ORIGINS"),
    )

    # ── 路径（环境变量优先，否则用默认路径） ──
    ghost_workspace_path: str = Field(default="", validation_alias=AliasChoices("GHOST_WORKSPACE_PATH"))
    coze_workspace_path: str = Field(default="", validation_alias=AliasChoices("COZE_WORKSPACE_PATH"))
    aid_dir: str = Field(default="", validation_alias=AliasChoices("AID_DIR"))
    alpha_id_dir: str = Field(default="", validation_alias=AliasChoices("ALPHA_ID_DIR"))

    @field_validator("ghost_workspace_path", "coze_workspace_path", mode="before")
    @classmethod
    def _default_workspace(cls, v, info):
        if v:
            return v
        return os.getcwd()

    @field_validator("aid_dir", mode="before")
    @classmethod
    def _default_aid_dir(cls, v):
        if v:
            return v
        return str(Path.home() / ".aid")

    @field_validator("alpha_id_dir", mode="before")
    @classmethod
    def _default_alpha_id_dir(cls, v):
        if v:
            return v
        return str(Path.home() / ".alpha-id")

    # ── 认证/JWT ──
    auth_master_key: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("AUTH_MASTER_KEY"),
    )
    jwt_access_expire_minutes: int = Field(
        default=30,
        validation_alias=AliasChoices("JWT_ACCESS_EXPIRE_MINUTES"),
    )
    jwt_refresh_expire_days: int = Field(
        default=7,
        validation_alias=AliasChoices("JWT_REFRESH_EXPIRE_DAYS"),
    )

    # ── LLM 配置（向后兼容 OPENAI_API_KEY / LLM_API_KEY） ──
    llm_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("LLM_API_KEY", "OPENAI_API_KEY", "COZE_WORKLOAD_IDENTITY_API_KEY"),
    )
    llm_base_url: str = Field(
        default="https://api.deepseek.com/v1",
        validation_alias=AliasChoices("LLM_BASE_URL", "OPENAI_BASE_URL"),
    )
    llm_model: str = Field(
        default="deepseek-v4-flash",
        validation_alias=AliasChoices("LLM_MODEL"),
    )
    llm_timeout: float = 10.0
    llm_max_retries: int = 2
    react_max_turns: int = Field(default=5, validation_alias=AliasChoices("REACT_MAX_TURNS"))

    # ── 存储 ──
    storage_backend: str = Field(default="", validation_alias=AliasChoices("STORAGE_BACKEND"))
    database_url: Optional[str] = Field(default=None, validation_alias=AliasChoices("DATABASE_URL"))
    token_store_path: Optional[str] = Field(default=None, validation_alias=AliasChoices("TOKEN_STORE_PATH"))

    # ── Fairy（桌面宠物） ──
    ollama_url: str = Field(default="http://localhost:11434", validation_alias=AliasChoices("OLLAMA_URL"))
    fairy_model: str = Field(default="minicpm-o:4.5-4bit", validation_alias=AliasChoices("FAIRY_MODEL"))
    fairy_whisper_model: str = Field(default="tiny", validation_alias=AliasChoices("FAIRY_WHISPER_MODEL"))
    fairy_whisper_device: str = Field(default="cpu", validation_alias=AliasChoices("FAIRY_WHISPER_DEVICE"))
    fairy_tts_model_name: str = Field(
        default="tts_models/zh-CN/baker/tacotron2-DDC-GST",
        validation_alias=AliasChoices("FAIRY_TTS_MODEL_NAME"),
    )
    fairy_tts_speaker_wav: Optional[str] = Field(default=None, validation_alias=AliasChoices("FAIRY_TTS_SPEAKER_WAV"))

    # ── 社交/身份 ──
    founder_alpha_id: str = Field(default="Alpha-000", validation_alias=AliasChoices("FOUNDER_ALPHA_ID"))
    founder_code_hash: str = Field(default="", validation_alias=AliasChoices("FOUNDER_CODE_HASH"))

    # ── API 第三方 ──
    alibaba_access_key_id: str = Field(default="", validation_alias=AliasChoices("ALIBABA_ACCESS_KEY_ID"))
    alibaba_access_key_secret: str = Field(default="", validation_alias=AliasChoices("ALIBABA_ACCESS_KEY_SECRET"))
    alibaba_sms_sign_name: str = Field(default="", validation_alias=AliasChoices("ALIBABA_SMS_SIGN_NAME"))
    sms_demo_mode: str = Field(default="true", validation_alias=AliasChoices("SMS_DEMO_MODE"))
    alipay_app_id: str = Field(default="", validation_alias=AliasChoices("ALIPAY_APP_ID"))
    alipay_private_key: str = Field(default="", validation_alias=AliasChoices("ALIPAY_PRIVATE_KEY"))
    alipay_demo_mode: str = Field(default="false", validation_alias=AliasChoices("ALIPAY_DEMO_MODE"))
    baidu_map_auth_token: str = Field(default="", validation_alias=AliasChoices("BAIDU_MAP_AUTH_TOKEN"))

    # ── 飞书集成 ──
    feishu_app_id: str = Field(default="", validation_alias=AliasChoices("FEISHU_APP_ID"))
    feishu_app_secret: str = Field(default="", validation_alias=AliasChoices("FEISHU_APP_SECRET"))
    feishu_verification_token: str = Field(default="", validation_alias=AliasChoices("FEISHU_VERIFICATION_TOKEN"))
    feishu_encrypt_key: str = Field(default="", validation_alias=AliasChoices("FEISHU_ENCRYPT_KEY"))
    feishu_webhook_enabled: bool = Field(default=True, validation_alias=AliasChoices("FEISHU_WEBHOOK_ENABLED"))

    # ── A2A 协议 ──
    a2a_enabled: bool = Field(default=True, validation_alias=AliasChoices("A2A_ENABLED"))
    a2a_port: int = Field(default=9001, validation_alias=AliasChoices("A2A_PORT"))

    # ── 限流 ──
    rate_limit_enabled: bool = Field(default=True, validation_alias=AliasChoices("RATE_LIMIT_ENABLED"))
    rate_limit_requests_per_minute: int = Field(default=60, validation_alias=AliasChoices("RATE_LIMIT_RPM"))

    # ── 网关/代理 ──
    gateway_url: str = Field(default="http://localhost:18080", validation_alias=AliasChoices("GATEWAY_URL"))
    default_alpha_id: str = Field(default="Alpha-001", validation_alias=AliasChoices("DEFAULT_ALPHA_ID"))
    ghost_alpha_id: str = Field(default="Ghost-001", validation_alias=AliasChoices("GHOST_ALPHA_ID"))
    code_runner_dir: str = Field(default="", validation_alias=AliasChoices("CODE_RUNNER_DIR"))

    # ── 可选 LLM 备用 ──
    deepseek_api_key: str = Field(default="", validation_alias=AliasChoices("DEEPSEEK_API_KEY"))

    @field_validator("auth_master_key", "llm_api_key", "alibaba_access_key_secret",
                    "alipay_private_key", "deepseek_api_key", "database_url", "baidu_map_auth_token",
                    "feishu_app_secret", "feishu_encrypt_key",
                    mode="after")
    @classmethod
    def _decrypt_sensitive(cls, v):
        """自动解密 ENC[...] 格式的敏感字段"""
        return decrypt_if_needed(v)

    @property
    def ghost_workspace(self) -> Path:
        return Path(self.ghost_workspace_path)

    @property
    def coze_workspace(self) -> Path:
        return Path(self.coze_workspace_path)

    @property
    def aid_path(self) -> Path:
        return Path(self.aid_dir)

    @property
    def alpha_id_path(self) -> Path:
        return Path(self.alpha_id_dir)

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


settings = Settings()

# ── 文件监听：.env 变更自动触发 reload ──

_watcher_thread: Optional[threading.Thread] = None
_watcher_stop = threading.Event()
_env_mtime_cache: Dict[str, float] = {}


def _watch_env_file(interval: float = 2.0) -> None:
    """后台线程：定期检查 .env 文件 mtime，变更时自动 reload"""
    global settings
    while not _watcher_stop.is_set():
        try:
            mtime = _ENV_FILE.stat().st_mtime if _ENV_FILE.exists() else 0.0
            cached = _env_mtime_cache.get("env", 0.0)
            if mtime > 0 and mtime != cached:
                _env_mtime_cache["env"] = mtime
                changed_fields = reload_settings_internal()
                if changed_fields:
                    import logging
                    logging.getLogger(__name__).info(
                        "[settings] .env changed, reloaded: %s", changed_fields
                    )
        except Exception:
            pass
        _watcher_stop.wait(interval)


def start_file_watcher(interval: float = 2.0) -> None:
    """启动配置文件监听（后台线程，守护模式）"""
    global _watcher_thread
    if _watcher_thread and _watcher_thread.is_alive():
        return
    _watcher_stop.clear()
    _env_mtime_cache["env"] = _ENV_FILE.stat().st_mtime if _ENV_FILE.exists() else 0.0
    _watcher_thread = threading.Thread(target=_watch_env_file, args=(interval,), daemon=True)
    _watcher_thread.start()


def stop_file_watcher() -> None:
    """停止配置文件监听"""
    _watcher_stop.set()


def reload_settings_internal() -> list[str]:
    """内部 reload（无锁，由调用方保证线程安全）"""
    global settings
    changed: list[str] = []
    new = Settings()
    for field_name in Settings.model_fields:
        try:
            old_val = getattr(settings, field_name)
            new_val = getattr(new, field_name)
            object.__setattr__(settings, field_name, new_val)
            if old_val != new_val:
                changed.append(field_name)
        except Exception:
            pass
    if changed and settings._callbacks:
        for cb in list(settings._callbacks):
            try:
                cb(changed)
            except Exception:
                pass
    return changed


def reload_settings() -> Settings:
    """强制重新加载配置（用于测试环境切换）——原地更新所有字段，触发变更回调。"""
    global settings
    with _settings_lock:
        new = Settings()
        changed: list[str] = []
        for field_name in Settings.model_fields:
            try:
                old_val = getattr(settings, field_name)
                new_val = getattr(new, field_name)
                object.__setattr__(settings, field_name, new_val)
                if old_val != new_val:
                    changed.append(field_name)
            except Exception:
                pass
        if changed and settings._callbacks:
            for cb in list(settings._callbacks):
                try:
                    cb(changed)
                except Exception:
                    pass
    return settings
