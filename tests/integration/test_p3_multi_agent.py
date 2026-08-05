"""Tests for AgentNetwork — multi-agent collaboration (P3-3)"""


import pytest

from alpha_id.agent_network import (
    AgentNetwork,
    CallChain,
    CallChainLink,
)
from alpha_id.poe import PoEClient, PoEStore
from alpha_id.signer import AIDSigner
from alpha_id.skill_signer import (
    SkillAttributionTracker,
    SkillRegistry,
    sign_skill,
)


class TestAgentNetwork:
    """AgentNetwork 核心功能测试"""

    def test_create_network(self):
        signer = AIDSigner()
        signer.generate()
        network = AgentNetwork(signer)
        assert network.my_did == signer.did

    def test_register_peer(self):
        signer = AIDSigner()
        signer.generate()
        network = AgentNetwork(signer)

        peer_signer = AIDSigner()
        peer_signer.generate()

        peer = network.register_peer(
            did=peer_signer.did,
            public_key_hex=peer_signer.public_key.hex(),
            alpha_id="Alpha-Peer",
            alias="Peer 1",
            trust_level=50,
        )
        assert peer.did == peer_signer.did
        assert peer.alpha_id == "Alpha-Peer"
        assert peer.trust_level == 50

        # get_peer
        assert network.get_peer(peer_signer.did) is not None
        assert network.get_peer("did:aid:nonexistent") is None

    def test_register_peer_invalid_did(self):
        signer = AIDSigner()
        signer.generate()
        network = AgentNetwork(signer)

        with pytest.raises(ValueError, match="DID"):
            network.register_peer("invalid-did")

    def test_register_peer_key_mismatch(self):
        signer = AIDSigner()
        signer.generate()
        network = AgentNetwork(signer)

        other = AIDSigner()
        other.generate()

        with pytest.raises(ValueError, match="不匹配"):
            network.register_peer(signer.did, public_key_hex=other.public_key.hex())

    def test_list_peers(self):
        signer = AIDSigner()
        signer.generate()
        network = AgentNetwork(signer)

        for i in range(3):
            ps = AIDSigner()
            ps.generate()
            network.register_peer(ps.did, public_key_hex=ps.public_key.hex())

        assert len(network.list_peers()) == 3

    def test_remove_peer(self):
        signer = AIDSigner()
        signer.generate()
        network = AgentNetwork(signer)

        ps = AIDSigner()
        ps.generate()
        network.register_peer(ps.did, public_key_hex=ps.public_key.hex())
        assert len(network.list_peers()) == 1

        network.remove_peer(ps.did)
        assert len(network.list_peers()) == 0

    def test_authenticate_peer(self):
        signer = AIDSigner()
        signer.generate()
        network = AgentNetwork(signer)

        peer_signer = AIDSigner()
        peer_signer.generate()
        network.register_peer(
            peer_signer.did,
            public_key_hex=peer_signer.public_key.hex(),
        )

        assert network.authenticate_peer(peer_signer.did) is True
        assert network.authenticate_peer("did:aid:nobody") is False

    def test_call_skill_basic(self, tmp_path):
        local = AIDSigner()
        local.generate()

        peer = AIDSigner()
        peer.generate()

        # Set up registry with a skill
        registry = SkillRegistry(storage_dir=str(tmp_path / "reg"))
        tracker = SkillAttributionTracker(storage_dir=str(tmp_path / "attrib"))
        poe_store = PoEStore(storage_dir=str(tmp_path / "poes"))

        # Register a skill as the peer
        skill_file = tmp_path / "greet.py"
        skill_file.write_text("def main(p): return 'Hello, ' + p.get('name', 'World')")
        pkg = sign_skill(skill_file, peer, name="greet")
        registry.register(pkg, content=skill_file.read_bytes())

        network = AgentNetwork(local, registry=registry, tracker=tracker, poe_store=poe_store)
        network.register_peer(
            peer.did,
            public_key_hex=peer.public_key.hex(),
        )

        result = network.call_skill(peer.did, "greet", {"name": "Alice"})
        assert result["success"] is True
        # 安全模式：text 类型直接返回文件原文
        assert "def main(p)" in result["result"]

    def test_call_skill_nonexistent_peer(self, tmp_path):
        local = AIDSigner()
        local.generate()
        network = AgentNetwork(local)

        result = network.call_skill("did:aid:nobody", "test")
        assert result["success"] is False
        assert result.get("error", "")

    def test_call_skill_unauthenticated_peer(self, tmp_path):
        local = AIDSigner()
        local.generate()
        network = AgentNetwork(local)

        peer = AIDSigner()
        peer.generate()
        # Register without public key -> can't authenticate
        network.register_peer(peer.did)

        result = network.call_skill(peer.did, "test")
        assert result["success"] is False
        assert not result.get("success", True)


class TestCallChain:
    """调用链追踪测试"""

    def test_empty_chain(self):
        chain = CallChain()
        assert chain.depth() == 0
        assert chain.all_successful() is True  # vacuously true
        assert "(empty" in chain.summary()

    def test_single_link(self):
        link = CallChainLink(
            poe_id="abc123",
            skill_name="greet",
            executor_did="did:aid:exec",
            author_did="did:aid:author",
            timestamp=1000.0,
            success=True,
        )
        chain = CallChain()
        chain.add(link)
        assert chain.depth() == 1
        assert chain.all_successful() is True
        assert chain.last() is not None
        assert chain.first() is not None
        assert chain.last().poe_id == "abc123"

    def test_multi_hop_chain(self):
        chain = CallChain()
        hops = [
            ("poe3", "skill-c", "did:aid:c", "did:aid:author", "poe2"),
            ("poe2", "skill-b", "did:aid:b", "did:aid:author", "poe1"),
            ("poe1", "skill-a", "did:aid:a", "did:aid:author", ""),
        ]
        for poe_id, skill, executor, author, parent in hops:
            chain.add(
                CallChainLink(
                    poe_id=poe_id,
                    skill_name=skill,
                    executor_did=executor,
                    author_did=author,
                    timestamp=0,
                    success=True,
                    parent_poe_id=parent,
                )
            )
        assert chain.depth() == 3
        assert chain.first().poe_id == "poe3"
        assert chain.last().poe_id == "poe1"

    def test_chain_verification(self):
        link = CallChainLink(
            poe_id="test",
            skill_name="t",
            executor_did="d",
            author_did="a",
            timestamp=0,
            success=True,
            verified=True,
        )
        chain = CallChain()
        chain.add(link)
        assert chain.all_verified() is True

        link2 = CallChainLink(
            poe_id="test2",
            skill_name="t",
            executor_did="d",
            author_did="a",
            timestamp=0,
            success=False,
            verified=False,
        )
        chain.add(link2)
        assert chain.all_verified() is False
        assert chain.all_successful() is False


class TestPoEAggregation:
    """多方 PoE 聚合测试"""

    def test_aggregate_empty(self, tmp_path):
        local = AIDSigner()
        local.generate()
        network = AgentNetwork(local)

        result = network.aggregate_poes([])
        assert result["total"] == 0
        assert result["successful"] == 0

    def test_aggregate_multiple(self, tmp_path):
        local = AIDSigner()
        local.generate()
        poe_store = PoEStore(storage_dir=str(tmp_path / "poes"))
        poe_client = PoEClient(local, store=poe_store)
        network = AgentNetwork(local, poe_store=poe_store)
        network.register_peer(local.did, public_key_hex=local.public_key.hex())

        # Generate some PoEs
        poe_ids = []
        for i in range(3):
            poe = poe_client.generate(
                skill_name=f"skill-{i}",
                skill_version="1.0",
                skill_content_hash=f"hash{i}",
                executor_did=local.did,
                author_did=local.did,
                params={"n": i},
                output=f"result-{i}",
                success=i % 2 == 0,
                duration_ms=10,
            )
            poe_ids.append(poe.poe_id)

        result = network.aggregate_poes(poe_ids)
        assert result["total"] == 3
        assert result["successful"] == 2  # i=0,2 are even
        assert result["failed"] == 1
        assert len(result["skills"]) == 3

    def test_aggregate_with_chain(self, tmp_path):
        local = AIDSigner()
        local.generate()
        peer = AIDSigner()
        peer.generate()

        poe_store = PoEStore(storage_dir=str(tmp_path / "poes"))
        network = AgentNetwork(local, poe_store=poe_store)
        network.register_peer(local.did, public_key_hex=local.public_key.hex())
        network.register_peer(peer.did, public_key_hex=peer.public_key.hex())

        # Chain: local calls peer's skill -> generates PoE with parent
        child_poe_client = PoEClient(local, store=poe_store, parent_poe_id="parent-chain-1")
        poe1 = child_poe_client.generate(
            skill_name="chain-skill",
            skill_version="1.0",
            skill_content_hash="ch",
            executor_did=local.did,
            author_did=peer.did,
            params={},
            output="ok",
            success=True,
            duration_ms=5,
        )

        result = network.aggregate_poes([poe1.poe_id, "parent-chain-1"])
        assert result["total"] == 1  # only 1 real PoE found (other is missing)
        assert result["successful"] == 1
        assert len(result["errors"]) == 1  # "parent-chain-1" not found

    def test_aggregate_verified_count(self, tmp_path):
        local = AIDSigner()
        local.generate()

        poe_store = PoEStore(storage_dir=str(tmp_path / "poes"))
        poe_client = PoEClient(local, store=poe_store)
        network = AgentNetwork(local, poe_store=poe_store)
        network.register_peer(local.did, public_key_hex=local.public_key.hex())

        poe = poe_client.generate(
            skill_name="v-skill",
            skill_version="1.0",
            skill_content_hash="vh",
            executor_did=local.did,
            author_did=local.did,
            params={},
            output="v",
            success=True,
            duration_ms=1,
        )
        result = network.aggregate_poes([poe.poe_id])
        assert result["verified"] == 1


class TestCallChainIntegration:
    """调用链端到端集成测试"""

    def test_call_skill_generates_poe(self, tmp_path):
        local = AIDSigner()
        local.generate()
        peer = AIDSigner()
        peer.generate()

        registry = SkillRegistry(storage_dir=str(tmp_path / "reg"))
        tracker = SkillAttributionTracker(storage_dir=str(tmp_path / "attrib"))
        poe_store = PoEStore(storage_dir=str(tmp_path / "poes"))

        skill_file = tmp_path / "t.py"
        skill_file.write_text("def main(p): return 'ok'")
        pkg = sign_skill(skill_file, peer, name="test-skill")
        registry.register(pkg, content=skill_file.read_bytes())

        network = AgentNetwork(
            local,
            registry=registry,
            tracker=tracker,
            poe_store=poe_store,
        )
        network.register_peer(peer.did, public_key_hex=peer.public_key.hex())

        result = network.call_skill(peer.did, "test-skill", {})
        assert result["success"]

        # PoE should have been generated
        assert poe_store.count() > 0

    def test_call_chain_from_skill_execution(self, tmp_path):
        local = AIDSigner()
        local.generate()
        peer = AIDSigner()
        peer.generate()

        registry = SkillRegistry(storage_dir=str(tmp_path / "reg"))
        poe_store = PoEStore(storage_dir=str(tmp_path / "poes"))

        skill_file = tmp_path / "chain.py"
        skill_file.write_text("def main(p): return 'chained'")
        pkg = sign_skill(skill_file, peer, name="chain-me")
        registry.register(pkg, content=skill_file.read_bytes())

        network = AgentNetwork(
            local,
            registry=registry,
            poe_store=poe_store,
        )
        network.register_peer(peer.did, public_key_hex=peer.public_key.hex())

        # Execute twice with chaining
        r1 = network.call_skill(peer.did, "chain-me", {})
        assert r1["success"]

        r2 = network.call_skill(peer.did, "chain-me", {}, parent_poe_id=r1["poe_id"])
        assert r2["success"]

        # Trace chain from r2
        chain = network.get_call_chain(r2["poe_id"])
        assert chain.depth() >= 1

    def test_discover_peers_from_repo(self, tmp_path):
        """从仓库发现对等节点"""
        local = AIDSigner()
        local.generate()
        network = AgentNetwork(local)

        # Create a repo with author_did
        repo_path = tmp_path / "peer-repo"
        from alpha_id.skill_repository import SkillRepository

        sr = SkillRepository()
        peer_author = AIDSigner()
        peer_author.generate()
        sr.init_repo(repo_path, name="Peer Skills", author_did=peer_author.did)

        discovered = network.discover_peers_from_repo([str(repo_path)])
        assert len(discovered) == 1
        assert discovered[0].did == peer_author.did
        assert discovered[0].trust_level == 30

    def test_peer_persistence(self, tmp_path):
        """对等节点列表持久化"""
        signer = AIDSigner()
        signer.generate()
        network = AgentNetwork(signer)

        peers = [AIDSigner() for _ in range(3)]
        for p in peers:
            p.generate()
            network.register_peer(p.did, public_key_hex=p.public_key.hex())

        save_path = str(tmp_path / "peers.json")
        network.save_peers(save_path)

        # New network, load back
        network2 = AgentNetwork(signer)
        network2.load_peers(save_path)
        assert len(network2.list_peers()) == 3
        for p in peers:
            assert network2.get_peer(p.did) is not None
