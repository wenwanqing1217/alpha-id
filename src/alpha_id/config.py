"""
Alpha-ID 配置模块 - 统一管理所有路径和配置

支持通过环境变量覆盖默认路径：
- ALPHA_ID_DIR: 主数据目录（默认 ~/.alpha-id）
- AID_DIR: 技能相关数据目录（默认 ~/.aid）
"""

import os
from pathlib import Path


def get_alpha_id_dir() -> Path:
    """获取 Alpha-ID 主数据目录"""
    env_dir = os.environ.get("ALPHA_ID_DIR")
    if env_dir:
        return Path(env_dir)
    return Path.home() / ".alpha-id"


def get_aid_dir() -> Path:
    """获取 .aid 技能数据目录"""
    env_dir = os.environ.get("AID_DIR")
    if env_dir:
        return Path(env_dir)
    return Path.home() / ".aid"


def get_skills_dir() -> Path:
    """获取技能存储目录"""
    return get_aid_dir() / "skills"


def get_attributions_dir() -> Path:
    """获取归因追踪目录"""
    return get_aid_dir() / "attributions"


def get_poes_dir() -> Path:
    """获取 PoE 存储目录"""
    return get_aid_dir()


def get_profile_dir() -> Path:
    """获取画像数据目录"""
    return get_alpha_id_dir() / "profile" / "v0.1"


def get_keys_dir() -> Path:
    """获取密钥存储目录"""
    return get_alpha_id_dir() / "keys"


def ensure_dir(directory: Path) -> Path:
    """确保目录存在，不存在则创建"""
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def get_downloads_dir() -> Path:
    """获取下载目录"""
    return Path.home() / "Downloads"


def get_desktop_dir() -> Path:
    """获取桌面目录"""
    return Path.home() / "Desktop"
