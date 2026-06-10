"""
Alpha-ID 采集器基类 — Phase 1 统一协议

所有采集器继承 BaseCollector，实现 detect/collect/summary。
自动发现依赖此基类，每个采集器模块只需导入 BaseCollector 并定义子类。
"""

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from alpha_id.profile_schema import AlphaIDProfile


@dataclass
class CollectorInfo:
    """采集器元信息 — 替代旧版 info() 函数返回值"""

    name: str
    display_name: str
    description: str
    category: str = "other"
    priority: int = 100
    requires_input: bool = False


class BaseCollector(ABC):
    """采集器抽象基类

    子类必须：
      1. 定义 `info: CollectorInfo` 类属性
      2. 实现 `detect() → bool`
      3. 实现 `collect(input_path) → Optional[AlphaIDProfile]`
    可选覆盖：
      4. `summary(profile) → str`（基类有默认实现）
    """

    info: CollectorInfo

    @abstractmethod
    def detect(self) -> bool:
        """检测本机是否存在可采集数据"""
        ...

    @abstractmethod
    def collect(self, input_path: Optional[Path] = None) -> Optional[AlphaIDProfile]:
        """采集数据并返回画像，无数据时返回 None"""
        ...

    def summary(self, profile: AlphaIDProfile) -> str:
        """采集摘要，默认实现提取沟通风格 + 技术语言"""
        c = profile.persona.communication
        t = profile.persona.technical
        lines = [f"[{self.info.display_name}] 数据采集"]
        if c.tone:
            lines.append(f"   沟通风格: {c.tone}")
        if c.sentence_length:
            lines.append(f"   句子长度: {c.sentence_length}")
        if t.primary_languages:
            lines.append(f"   技术语言: {', '.join(t.primary_languages)}")
        if profile.persona.temporal.work_rhythm:
            lines.append(f"   工作节奏: {profile.persona.temporal.work_rhythm}")
        return "\n".join(lines)

    # ─── 模块级兼容 ───

    def module_info(self) -> dict:
        """返回 info 的 dict 形式，兼容旧版 info() 函数调用"""
        return asdict(self.info)

    @classmethod
    def create_module_functions(cls):
        """创建模块级函数 info/detect/collect/summary，向后兼容 CLI 的 getattr 调用

        用法（在采集器模块末尾）：
            _instance = MyCollector()
            info, detect, collect, summary = _instance.create_module_functions()
        """
        instance = cls()

        def info():
            return instance.module_info()

        def detect():
            return instance.detect()

        def collect(input_path: Optional[Path] = None):
            return instance.collect(input_path)

        def summary(profile: AlphaIDProfile):
            return instance.summary(profile)

        return info, detect, collect, summary
