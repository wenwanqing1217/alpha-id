"""
Profile Wizard — 零数据魔法时刻

通过3个问题快速生成用户画像，不需要 ChatGPT 导出。
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

import typer

from alpha_id.did import DIDRegistry
from alpha_id.profile_schema import (
    AlphaIDProfile,
    CommunicationPersona,
    TechnicalPersona,
    TemporalPersona,
    save_profile,
    summary,
)

logger = logging.getLogger(__name__)
wizard_app = typer.Typer(help="画像向导")


@wizard_app.command("start")
def cmd_wizard():
    """零数据魔法时刻 — 3个问题生成基础画像"""
    typer.echo("\n[向导] 还没有数据？没关系，先回答3个问题。")
    typer.echo("=" * 40)

    # 问题1: 编程语言
    typer.echo("\n问题 1/3: 你平时主要用什么编程语言？")
    lang = typer.prompt("  输入 (Python / TypeScript / Go / Rust / Java / 其他)", default="Python")
    lang_map = {
        "python": "Python",
        "py": "Python",
        "typescript": "TypeScript",
        "ts": "TypeScript",
        "js": "JavaScript",
        "go": "Go",
        "golang": "Go",
        "rust": "Rust",
        "rs": "Rust",
        "java": "Java",
    }
    primary_lang = lang_map.get(lang.strip().lower(), lang.strip())

    # 问题2: 编码风格
    typer.echo("\n问题 2/3: 你写代码喜欢哪种风格？")
    style = typer.prompt("  输入 (functional / oop / mixed)", default="mixed")
    style_map = {"f": "functional", "func": "functional", "o": "oop", "object": "oop", "m": "mixed"}
    coding_style = style_map.get(style.strip().lower(), style.strip())

    # 问题3: 工作时段
    typer.echo("\n问题 3/3: 你一般在什么时段工作？")
    rhythm = typer.prompt("  输入 (daytime / night_owl / mixed)", default="daytime")
    rhythm_map = {"d": "daytime", "day": "daytime", "n": "night_owl", "night": "night_owl", "m": "mixed"}
    work_rhythm = rhythm_map.get(rhythm.strip().lower(), rhythm.strip())

    typer.echo("\n" + "=" * 40)
    typer.echo("正在生成你的数字画像...")

    # 生成 DID
    reg = DIDRegistry()
    did = reg.generate()
    key_dir = Path.home() / ".alpha-id" / "keys"
    key_dir.mkdir(parents=True, exist_ok=True)
    (key_dir / "private_key.bin").write_bytes(reg.export_private_key())

    # 构建画像
    profile = AlphaIDProfile(
        did=did,
        created_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        persona={
            "communication": CommunicationPersona(
                tone="direct",
                sentence_length="medium",
            ),
            "technical": TechnicalPersona(
                primary_languages=[primary_lang],
                coding_style=coding_style,
            ),
            "temporal": TemporalPersona(
                work_rhythm=work_rhythm,
            ),
        },
    )

    # 写时复制：确保 profile.persona 是 Persona 对象
    from alpha_id.profile_schema import Persona

    if not isinstance(profile.persona, Persona):
        profile.persona = Persona(
            communication=CommunicationPersona(
                tone="direct",
                sentence_length="medium",
            ),
            technical=TechnicalPersona(
                primary_languages=[primary_lang],
                coding_style=coding_style,
            ),
            temporal=TemporalPersona(
                work_rhythm=work_rhythm,
            ),
        )

    save_profile(profile)

    typer.echo("\n[OK] 画像已生成！")
    typer.echo(summary(profile))
    typer.echo("\n  下一步:")
    typer.echo("     aid profile web              浏览器查看画像")
    typer.echo("     aid collect chatgpt <zip>    导入更多数据完善画像")
