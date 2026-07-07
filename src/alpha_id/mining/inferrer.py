"""Mining inferrer — 将原始痕迹信号推断成 Alpha-ID 画像。"""

import logging
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Dict, List, Optional

from alpha_id.profile_schema import AlphaIDProfile

logger = logging.getLogger(__name__)

LANGUAGE_PATTERNS = {
    "Python": r"\bpython\b",
    "TypeScript": r"\btypescript\b",
    "JavaScript": r"\bjavascript\b",
    "Rust": r"\brust\b",
    "Go": r"\bgo\b",
    "Java": r"\bjava\b",
    "Kotlin": r"\bkotlin\b",
    "Swift": r"\bswift\b",
    "C++": r"\bc\+\+\b",
    "C": r"\bc语言\b|\bc\b",
    "Shell": r"\bbash\b|\bshell\b",
    "SQL": r"\bsql\b",
}

FRAMEWORK_PATTERNS = {
    "FastAPI": r"\bfastapi\b",
    "Django": r"\bdjango\b",
    "React": r"\breact\b",
    "Vue": r"\bvue\b",
    "Node": r"\bnode\.js\b|\bnodejs\b",
    "PyTorch": r"\bpytorch\b",
    "TensorFlow": r"\btensorflow\b",
    "Docker": r"\bdocker\b",
    "Kubernetes": r"\bkubernetes\b|\bk8s\b",
    "Rust": r"\bcargo\b|\bsolana\b|\bstarknet\b",
}

STYLE_PATTERNS = {
    "functional": r"\b(functional|lambda|immutable|compose|monad)\b",
    "oop": r"\b(class|inheritance|interface|abstract)\b",
    "systems": r"\b(memory|unsafe|allocator|syscall|kernel)\b",
    "data": r"\b(pandas|numpy|dataframe|etl|analytics)\b",
}


def infer_profile(signals: List[Dict[str, object]], seed_did: str = "") -> AlphaIDProfile:
    profile = AlphaIDProfile(
        did=seed_did,
        created_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )

    provenance: Dict[str, Dict[str, object]] = {}
    all_messages: List[str] = []
    all_timestamps: List[str] = []
    code_exts: List[str] = []
    repo_count = 0

    for signal in signals:
        messages = signal.get("messages") or []
        timestamps = signal.get("timestamps") or []
        if isinstance(messages, list):
            all_messages.extend([m for m in messages if isinstance(m, str)])
        if isinstance(timestamps, list):
            all_timestamps.extend([t for t in timestamps if isinstance(t, str)])
        if signal.get("source_kind") == "git_repo":
            repo_count += 1
            exts = signal.get("code_extensions") or []
            if isinstance(exts, list):
                code_exts.extend([e for e in exts if isinstance(e, str)])

    text = " ".join(all_messages)
    _infer_technical(profile, provenance, text, code_exts)
    _infer_communication(profile, provenance, text)
    _infer_temporal(profile, provenance, all_timestamps)
    _apply_activity_meta(profile, repo_count=repo_count, source_count=len(signals))
    _apply_provenance(profile, provenance)

    return profile


def _infer_technical(
    profile: AlphaIDProfile, provenance: Dict[str, Dict[str, object]], text: str, code_exts: List[str]
) -> None:
    langs = [lang for lang, pat in LANGUAGE_PATTERNS.items() if re.search(pat, text, re.IGNORECASE)]
    frameworks = [name for name, pat in FRAMEWORK_PATTERNS.items() if re.search(pat, text, re.IGNORECASE)]
    ext_counter = Counter(code_exts)
    top_exts = [ext for ext, _ in ext_counter.most_common(6) if ext]

    if top_exts and not langs:
        ext_to_lang = {
            ".py": "Python",
            ".ts": "TypeScript",
            ".js": "JavaScript",
            ".rs": "Rust",
            ".go": "Go",
            ".java": "Java",
            ".rb": "Ruby",
            ".php": "PHP",
        }
        for ext in top_exts:
            lang = ext_to_lang.get(ext)
            if lang and lang not in langs:
                langs.append(lang)

    profile.persona.technical.primary_languages = langs[:8]
    profile.persona.technical.framework_preferences = frameworks[:6]

    style = "unknown"
    for candidate, pat in STYLE_PATTERNS.items():
        if re.search(pat, text, re.IGNORECASE):
            style = candidate
            break
    if style == "unknown" and top_exts:
        style = "mixed"
    profile.persona.technical.coding_style = style
    _set_provenance(provenance, "technical.primary_languages", langs, confidence=0.6, method="keyword")
    _set_provenance(provenance, "technical.framework_preferences", frameworks, confidence=0.6, method="keyword")
    _set_provenance(provenance, "technical.coding_style", [style], confidence=0.5, method="heuristic")


def _infer_communication(profile: AlphaIDProfile, provenance: Dict[str, Dict[str, object]], text: str) -> None:
    segments = [segment.strip() for segment in text.split("\n") if segment.strip()]
    if not segments:
        return
    lengths = [len(segment.split()) for segment in segments if segment.split()]
    avg = sum(lengths) / len(lengths)
    profile.persona.communication.sentence_length = "short" if avg < 18 else ("medium" if avg < 45 else "long")

    question_ratio = sum(segment.count("?") for segment in segments) / max(sum(len(segment) for segment in segments), 1)
    if question_ratio > 0.08:
        profile.persona.communication.tone = "analytical"
    elif any(word in text.lower() for word in ["please", "thanks", "麻烦", "谢谢", "麻烦你了"]):
        profile.persona.communication.tone = "polite"
    else:
        profile.persona.communication.tone = "direct"
    _set_provenance(
        provenance,
        "communication.sentence_length",
        [profile.persona.communication.sentence_length],
        confidence=0.7,
        method="statistics",
    )
    _set_provenance(
        provenance, "communication.tone", [profile.persona.communication.tone], confidence=0.55, method="heuristic"
    )


def _infer_temporal(profile: AlphaIDProfile, provenance: Dict[str, Dict[str, object]], timestamps: List[str]) -> None:
    hour_counts: Counter = Counter()
    for ts in timestamps:
        dt = _try_parse_timestamp(ts)
        if dt:
            hour_counts[dt.hour] += 1
    if hour_counts:
        profile.persona.communication.active_hours = sorted(h for h, _ in hour_counts.most_common(5))
        night = sum(c for h, c in hour_counts.items() if h >= 22 or h <= 5)
        day = sum(c for h, c in hour_counts.items() if 6 <= h <= 18)
        profile.persona.temporal.work_rhythm = (
            "night_owl" if (night + day > 0 and night / (night + day) > 0.4) else "daytime"
        )
        _set_provenance(
            provenance,
            "communication.active_hours",
            profile.persona.communication.active_hours,
            confidence=0.8,
            method="timestamp",
        )
        _set_provenance(
            provenance,
            "temporal.work_rhythm",
            [profile.persona.temporal.work_rhythm],
            confidence=0.7,
            method="timestamp",
        )


def _apply_activity_meta(profile: AlphaIDProfile, repo_count: int = 0, source_count: int = 0) -> None:
    profile.extra["x_mining"] = {
        "repo_count": repo_count,
        "source_count": source_count,
        "engine": "mining",
    }


def _apply_provenance(profile: AlphaIDProfile, provenance: Dict[str, Dict[str, object]]) -> None:
    cleaned = {}
    for key, value in provenance.items():
        confidence = value.get("confidence")
        if confidence is None or not isinstance(confidence, (int, float)):
            confidence = 0.0
        cleaned[key] = {
            "value": value.get("value"),
            "confidence": round(float(confidence), 2),
            "source": value.get("source", "mining"),
            "method": value.get("method", "heuristic"),
        }
    profile.extra["x_provenance"] = cleaned


def _set_provenance(
    provenance: Dict[str, Dict[str, object]], key: str, value, confidence: float, method: str, source: str = "mining"
) -> None:
    provenance[key] = {
        "value": value,
        "confidence": confidence,
        "source": source,
        "method": method,
    }


def _try_parse_timestamp(value: str) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
