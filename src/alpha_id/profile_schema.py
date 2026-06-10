"""
Alpha-ID Profile Schema v0.1 — 数据模型

P0 原则：只留"缺了会崩的东西"。
  - profile_version / did / created_at ← 核心身份，缺了不能认人
  - persona.communication / technical / temporal ← 画像内容，缺了没东西展示
  - 其他全部 x_ 前缀预留
"""

import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = "0.1.0"
PROFILE_DIR = "v0.1"
PROFILE_FILE = "identity.yaml"


def _alpha_id_dir() -> Path:
    """动态获取 Alpha-ID 数据目录，支持环境变量 ALPHA_ID_DIR 覆盖"""
    env_dir = os.environ.get("ALPHA_ID_DIR")
    if env_dir:
        return Path(env_dir)
    return Path.home() / ".alpha-id"


@dataclass
class CommunicationPersona:
    tone: Optional[str] = None
    sentence_length: Optional[str] = None
    active_hours: List[int] = field(default_factory=list)


@dataclass
class TechnicalPersona:
    primary_languages: List[str] = field(default_factory=list)
    framework_preferences: List[str] = field(default_factory=list)
    coding_style: Optional[str] = None


@dataclass
class TemporalPersona:
    work_rhythm: Optional[str] = None
    focus_duration_minutes: Optional[int] = None


@dataclass
class Persona:
    communication: CommunicationPersona = field(default_factory=CommunicationPersona)
    technical: TechnicalPersona = field(default_factory=TechnicalPersona)
    temporal: TemporalPersona = field(default_factory=TemporalPersona)


@dataclass
class AlphaIDProfile:
    """P0 最小 profile：身份 + 画像"""

    profile_version: str = SCHEMA_VERSION
    did: str = ""
    created_at: str = ""
    persona: Persona = field(default_factory=Persona)
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        for k, v in self.extra.items():
            d[k] = v
        for k in list(d.keys()):
            if k == "extra":
                del d[k]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "AlphaIDProfile":
        extra = {k: d.pop(k) for k in list(d.keys()) if k.startswith("x_")}
        profile = cls(
            profile_version=d.get("profile_version", SCHEMA_VERSION),
            did=d.get("did", ""),
            created_at=d.get("created_at", ""),
        )
        pd = d.get("persona") or {}
        if pd:
            profile.persona = Persona(
                communication=CommunicationPersona(**(pd.get("communication") or {})),
                technical=TechnicalPersona(**(pd.get("technical") or {})),
                temporal=TemporalPersona(**(pd.get("temporal") or {})),
            )
        profile.extra = extra
        return profile


# ─── P0 目录管理 ───

def ensure_profile_dir() -> Path:
    d = _alpha_id_dir() / "profile" / PROFILE_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def profile_path() -> Path:
    return _alpha_id_dir() / "profile" / PROFILE_DIR / PROFILE_FILE


def profile_exists() -> bool:
    return profile_path().exists()


def load_profile() -> Optional[AlphaIDProfile]:
    if not profile_exists():
        return None
    import yaml
    with open(profile_path(), encoding="utf-8") as f:
        return AlphaIDProfile.from_dict(yaml.safe_load(f))


# ─── quality 定义 ───

QUALITY_EXPORT = 90
QUALITY_API = 70
QUALITY_LOCAL = 50
QUALITY_HEURISTIC = 30


def _quality_label(q: int) -> str:
    if q >= 90:
        return "export"
    if q >= 70:
        return "api"
    if q >= 50:
        return "local"
    return "heuristic"


def merge_profile(new: AlphaIDProfile, source: str = "unknown", quality: int = QUALITY_LOCAL) -> AlphaIDProfile:
    """基于 quality 的画像合并

    规则：
    - quality 高的值优先；同 quality → 旧值优先
    - 被覆盖的值保留到 extra.x_alternatives
    """
    old = load_profile()
    if old is None:
        _tag_source(new, source, quality)
        return new

    if old.did:
        new.did = old.did

    oc, nc = old.persona.communication, new.persona.communication

    # 沟通风格（quality 决策）
    _merge_field(new, "tone", oc.tone, nc.tone,
                 _get_q(old, "tone"), quality, lambda v: setattr(nc, "tone", v))
    _merge_field(new, "sentence_length", oc.sentence_length, nc.sentence_length,
                 _get_q(old, "sentence_length"), quality, lambda v: setattr(nc, "sentence_length", v))

    # 活跃时段（合并去重）
    if oc.active_hours:
        nc.active_hours = sorted(set(oc.active_hours + nc.active_hours))[:8]

    # 技术语言（合并去重）
    if old.persona.technical.primary_languages:
        nc.primary_languages = list(dict.fromkeys(
            old.persona.technical.primary_languages + new.persona.technical.primary_languages
        ))[:8]

    # 框架偏好（合并去重）
    ofp = old.persona.technical.framework_preferences or []
    nfp = new.persona.technical.framework_preferences or []
    if ofp:
        nc.framework_preferences = list(dict.fromkeys(ofp + nfp))[:5]

    # 编码风格（quality 决策）
    _merge_field(new, "coding_style", old.persona.technical.coding_style, new.persona.technical.coding_style,
                 _get_q(old, "coding_style"), quality, lambda v: setattr(new.persona.technical, "coding_style", v))

    # 工作节奏（quality 决策）
    ot, nt = old.persona.temporal, new.persona.temporal
    _merge_field(new, "work_rhythm", ot.work_rhythm, nt.work_rhythm,
                 _get_q(old, "work_rhythm"), quality, lambda v: setattr(nt, "work_rhythm", v))

    # extra 合并
    for k, v in old.extra.items():
        if k not in new.extra:
            new.extra[k] = v

    _tag_source(new, source, quality)
    return new


def _merge_field(profile, field, old_val, new_val, old_q, new_q, setter):
    """按 quality 合并单个字段"""
    if new_val is None and old_val is not None:
        setter(old_val)
        return
    if old_val is None:
        if new_val is not None:
            _set_q(profile, field, new_q)
        return
    if old_val == new_val:
        _set_q(profile, field, max(old_q, new_q))
        return
    if new_q >= old_q:
        _add_alt(profile, field, old_val, old_q)
        _set_q(profile, field, new_q)
    else:
        _add_alt(profile, field, new_val, new_q)
        setter(old_val)
        _set_q(profile, field, old_q)


def _add_alt(profile, field, value, quality):
    alts = profile.extra.get("x_alternatives", {})
    if not isinstance(alts, dict):
        alts = {}
    alts[field] = {"value": value, "quality": quality, "source": _quality_label(quality)}
    profile.extra["x_alternatives"] = alts


def _tag_source(profile, source, quality):
    profile.extra["x_last_source"] = source
    profile.extra["x_last_quality"] = quality
    sources = profile.extra.get("x_collected_sources", [])
    if not isinstance(sources, list):
        sources = []
    if source not in sources:
        sources.append(source)
    profile.extra["x_collected_sources"] = sources


def _get_q(profile, field):
    return profile.extra.get("x_quality_map", {}).get(field, QUALITY_LOCAL)


def _set_q(profile, field, q):
    qm = profile.extra.get("x_quality_map", {})
    if not isinstance(qm, dict):
        qm = {}
    qm[field] = q
    profile.extra["x_quality_map"] = qm


def save_profile(profile: AlphaIDProfile) -> Path:
    ensure_profile_dir()
    import yaml
    with open(profile_path(), "w", encoding="utf-8") as f:
        yaml.dump(profile.to_dict(), f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    return profile_path()


def add_collected_source(source_name: str) -> bool:
    try:
        profile = load_profile()
        if profile is None:
            profile = AlphaIDProfile()
        sources = profile.extra.get("x_collected_sources", [])
        if not isinstance(sources, list):
            sources = []
        if source_name not in sources:
            sources.append(source_name)
        profile.extra["x_collected_sources"] = sources
        save_profile(profile)
        return True
    except Exception:
        return False


def summary(profile: AlphaIDProfile) -> str:
    lines = ["[Profile] Alpha-ID Profile v%s" % profile.profile_version, "   DID: %s" % profile.did]
    aid = profile.extra.get("alpha_id")
    if aid:
        lines.append("   Alpha-ID: %s" % aid)
    lines.append("")
    p = profile.persona
    c = p.communication
    if c.tone:
        lines.append("[风格] 沟通风格: %s" % c.tone)
    if c.sentence_length:
        lines.append("[长度] 句子长度: %s" % c.sentence_length)
    if c.active_hours:
        lines.append("[时段] 活跃时段: %s" % ", ".join("%02d:00" % h for h in c.active_hours[:5]))
    if p.technical.primary_languages:
        lines.append("[语言] 主要语言: %s" % ", ".join(p.technical.primary_languages))
    if p.technical.framework_preferences:
        lines.append("[框架] 框架偏好: %s" % ", ".join(p.technical.framework_preferences))
    if p.technical.coding_style:
        lines.append("[编码] 编码风格: %s" % p.technical.coding_style)
    if p.temporal.work_rhythm:
        lines.append("[节奏] 工作节奏: %s" % p.temporal.work_rhythm)
    sources = profile.extra.get("x_collected_sources", [])
    if sources:
        lines.append("[来源] 数据来源: %s" % ", ".join(sources))
    return "\n".join(lines)


def compress_profile(profile: AlphaIDProfile, max_tokens: int = 200) -> str:
    parts = []
    p = profile.persona
    c = p.communication
    t = p.technical
    tm = p.temporal

    aid = profile.extra.get("alpha_id", "")
    if aid:
        parts.append(f"用户:{aid}")
    else:
        parts.append("用户:Alpha-ID")

    if t.primary_languages:
        parts.append(f"语言:{'/'.join(t.primary_languages[:3])}")
    if t.framework_preferences:
        parts.append(f"框架:{'/'.join(t.framework_preferences[:2])}")
    if t.coding_style:
        parts.append(f"风格:{t.coding_style}")

    if c.tone:
        parts.append(f"语气:{c.tone}")
    if c.sentence_length:
        parts.append(f"句长:{c.sentence_length}")

    if tm.work_rhythm:
        rhythm_label = "夜猫" if tm.work_rhythm == "night_owl" else "日间"
        parts.append(f"节奏:{rhythm_label}")
    if c.active_hours:
        peak = c.active_hours[0] if c.active_hours else None
        if peak is not None:
            parts.append(f"高峰:{peak:02d}:00")

    return " | ".join(parts)
