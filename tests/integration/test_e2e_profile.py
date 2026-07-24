"""集成测试 - 确保 test_e2e_profile 可被 pytest 发现"""

from pathlib import Path

from alpha_id.collectors.chatgpt import collect as chatgpt_collect
from alpha_id.did import DIDRegistry
from alpha_id.profile_schema import save_profile, load_profile, profile_exists, summary


def test_e2e_did_generation():
    reg = DIDRegistry()
    did = reg.generate()
    assert did.startswith("did:aid:")
    assert len(did) > 20


def test_e2e_chatgpt_collect_via_pytest(tmp_path):
    import json, zipfile
    from alpha_id.collectors.chatgpt import collect as cg_collect

    z = tmp_path / "test.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr(
            "conversations.json",
            json.dumps(
                [
                    {
                        "title": "t1",
                        "create_time": "2026-01-01T10:00:00Z",
                        "messages": [{"role": "user", "content": "Python 怎么样？"}],
                    },
                    {
                        "title": "t2",
                        "create_time": "2026-01-01T11:00:00Z",
                        "messages": [{"role": "user", "content": "Rust 的性能如何？"}],
                    },
                    {
                        "title": "t3",
                        "create_time": "2026-01-01T12:00:00Z",
                        "messages": [{"role": "user", "content": "Go 适合做后端吗？"}],
                    },
                ]
            ),
        )
    p = cg_collect(z)
    assert p is not None
    assert "Python" in p.persona.technical.primary_languages


def test_e2e_sign_verify():
    reg = DIDRegistry()
    reg.generate()
    sig = reg.sign(b"hello")
    pub = reg.export_public_key()
    assert reg.verify(pub, b"hello", sig)
    assert not reg.verify(pub, b"wrong", sig)
