"""
双链记忆隔离测试

覆盖：
  - 自动分链（按敏感度）
  - 私有链加密 / 解密
  - 知识链明文存储
  - 链间迁移
  - 查询过滤
  - 统计信息
  - 删除与清空
"""

import os
import tempfile
import unittest
from unittest.mock import patch

from core.dual_chain import DualChainManager, _derive_key, _encrypt, _decrypt, PRIVACY_THRESHOLD


class TestKeyDerivation(unittest.TestCase):
    """密钥派生"""

    def test_derive_deterministic(self):
        """相同 DID + salt 派生相同密钥"""
        salt = b"fixed_salt_16byt"
        key1 = _derive_key("did:aid:test123", salt)
        key2 = _derive_key("did:aid:test123", salt)
        self.assertEqual(key1, key2)

    def test_derive_different_dids(self):
        """不同 DID 派生不同密钥"""
        salt = b"fixed_salt_16byt"
        key1 = _derive_key("did:aid:user_a", salt)
        key2 = _derive_key("did:aid:user_b", salt)
        self.assertNotEqual(key1, key2)

    def test_derive_32_bytes(self):
        """派生密钥长度为 32 字节"""
        salt = b"fixed_salt_16byt"
        key = _derive_key("did:aid:test", salt)
        self.assertEqual(len(key), 32)


class TestEncryption(unittest.TestCase):
    """加解密"""

    def test_encrypt_decrypt_roundtrip(self):
        """加密后解密得到原文"""
        salt = b"test_salt_16byte"
        key = _derive_key("did:aid:roundtrip", salt)
        original = "这是一段需要加密的敏感记忆内容"
        encrypted = _encrypt(original, key)
        decrypted = _decrypt(encrypted, key)
        self.assertEqual(original, decrypted)

    def test_encrypt_produces_different_ciphertext(self):
        """相同明文加密产生不同密文（随机 nonce）"""
        salt = b"test_salt_16byte"
        key = _derive_key("did:aid:random", salt)
        plaintext = "same content"
        enc1 = _encrypt(plaintext, key)
        enc2 = _encrypt(plaintext, key)
        self.assertNotEqual(enc1["ciphertext"], enc2["ciphertext"])

    def test_decrypt_wrong_key_fails(self):
        """错误密钥解密失败"""
        salt = b"test_salt_16byte"
        key1 = _derive_key("did:aid:user1", salt)
        key2 = _derive_key("did:aid:user2", salt)
        encrypted = _encrypt("secret data", key1)
        with self.assertRaises(Exception):
            _decrypt(encrypted, key2)


class TestDualChainManager(unittest.TestCase):
    """双链管理器"""

    def setUp(self):
        """每个测试用例使用临时目录"""
        self.tmpdir = tempfile.mkdtemp()
        self.alpha_id = "did:aid:test_user_001"
        # 重定向存储路径到临时目录
        self.patcher = patch.dict(os.environ, {"COZE_WORKSPACE_PATH": self.tmpdir})
        self.patcher.start()
        # 强制重载 settings，使新环境变量生效
        from core.settings import reload_settings
        reload_settings()
        # 清理可能存在的 salt
        salt_path = os.path.join(self.tmpdir, "assets", ".salt_" + self.alpha_id.replace(":", "_"))
        if os.path.exists(salt_path):
            os.remove(salt_path)
        self.mgr = DualChainManager(self.alpha_id)

    def tearDown(self):
        self.patcher.stop()
        # 恢复 settings
        from core.settings import reload_settings
        reload_settings()
        # 清理临时目录
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_mgr(self):
        """创建新的管理器实例（模拟重启）"""
        return DualChainManager(self.alpha_id)

    # ── 分链测试 ──

    def test_high_sensitivity_goes_private(self):
        """高敏感度记忆进入私有链"""
        result = self.mgr.save("我的银行密码", sensitivity=85)
        self.assertEqual(result["chain"], "private")
        self.assertTrue(result["encrypted"])

    def test_low_sensitivity_goes_knowledge(self):
        """低敏感度记忆进入知识链"""
        result = self.mgr.save("今天天气很好", sensitivity=20)
        self.assertEqual(result["chain"], "knowledge")
        self.assertFalse(result["encrypted"])

    def test_threshold_boundary(self):
        """阈值边界测试：70 → 私有链，69 → 知识链"""
        r1 = self.mgr.save("boundary test 70", sensitivity=PRIVACY_THRESHOLD)
        r2 = self.mgr.save("boundary test 69", sensitivity=PRIVACY_THRESHOLD - 1)
        self.assertEqual(r1["chain"], "private")
        self.assertEqual(r2["chain"], "knowledge")

    # ── 加密测试 ──

    def test_private_content_encrypted_at_rest(self):
        """私有链内容在存储中加密"""
        self.mgr.save("绝密：我的私钥是abc123", sensitivity=95, category="secret")
        # 直接读取存储文件，确认内容已加密
        priv_data = self.mgr._private_storage.load(self.mgr._chain_key_private)
        memories = priv_data.get("memories", {})
        self.assertTrue(len(memories) > 0)
        for mem in memories.values():
            self.assertTrue(mem.get("encrypted"))
            self.assertIn("nonce", mem)
            # 密文不包含明文
            self.assertNotIn("绝密", mem["content"])

    def test_knowledge_content_plain(self):
        """知识链内容明文存储"""
        self.mgr.save("公开知识：Python 3.12发布了", sensitivity=10, category="knowledge")
        know_data = self.mgr._knowledge_storage.load(self.mgr._chain_key_knowledge)
        memories = know_data.get("memories", {})
        for mem in memories.values():
            self.assertFalse(mem.get("encrypted", False))
            self.assertIn("Python", mem["content"])

    # ── 读取测试 ──

    def test_get_private_decrypts(self):
        """读取私有链记忆自动解密"""
        original = "这是我的秘密日记内容"
        result = self.mgr.save(original, sensitivity=80)
        memory_id = result["memory_id"]

        record = self.mgr.get(memory_id)
        self.assertIsNotNone(record)
        self.assertEqual(record["content"], original)
        self.assertEqual(record["_chain"], "private")

    def test_get_knowledge_returns_plain(self):
        """读取知识链记忆返回明文"""
        original = "公开笔记：学习 FastAPI"
        result = self.mgr.save(original, sensitivity=30)
        memory_id = result["memory_id"]

        record = self.mgr.get(memory_id)
        self.assertIsNotNone(record)
        self.assertEqual(record["content"], original)

    def test_get_nonexistent_returns_none(self):
        """获取不存在的记忆返回 None"""
        record = self.mgr.get("nonexistent_id")
        self.assertIsNone(record)

    # ── 查询测试 ──

    def test_query_by_chain(self):
        """按链查询"""
        self.mgr.save("私有记忆1", sensitivity=80)
        self.mgr.save("私有记忆2", sensitivity=90)
        self.mgr.save("知识记忆1", sensitivity=20)
        self.mgr.save("知识记忆2", sensitivity=30)

        priv_results = self.mgr.query(chain="private")
        know_results = self.mgr.query(chain="knowledge")

        self.assertEqual(len(priv_results), 2)
        self.assertEqual(len(know_results), 2)
        for r in priv_results:
            self.assertEqual(r["_chain"], "private")
        for r in know_results:
            self.assertEqual(r["_chain"], "knowledge")

    def test_query_keyword_search(self):
        """关键词搜索"""
        self.mgr.save("我喜欢吃苹果", sensitivity=10, tags=["水果"])
        self.mgr.save("今天去了北京", sensitivity=15, tags=["旅行"])
        self.mgr.save("苹果公司的产品", sensitivity=20, tags=["科技"])

        results = self.mgr.query(keyword="苹果")
        self.assertEqual(len(results), 2)

    def test_query_sensitivity_filter(self):
        """敏感度过滤"""
        self.mgr.save("低敏感", sensitivity=10)
        self.mgr.save("中敏感", sensitivity=50)
        self.mgr.save("高敏感", sensitivity=90)

        results = self.mgr.query(max_sensitivity=50)
        self.assertEqual(len(results), 2)

    # ── 迁移测试 ──

    def test_migrate_private_to_knowledge(self):
        """私有链 → 知识链迁移"""
        original = "降级为公开的记忆"
        result = self.mgr.save(original, sensitivity=85)
        memory_id = result["memory_id"]

        # 迁移
        mig_result = self.mgr.migrate(memory_id, "knowledge")
        self.assertTrue(mig_result["success"])
        self.assertEqual(mig_result["migrated_from"], "private")

        # 验证在新链
        record = self.mgr.get(memory_id)
        self.assertEqual(record["_chain"], "knowledge")
        self.assertEqual(record["content"], original)
        self.assertLess(record["sensitivity"], PRIVACY_THRESHOLD)

    def test_migrate_knowledge_to_private(self):
        """知识链 → 私有链迁移"""
        original = "升级为私有的记忆"
        result = self.mgr.save(original, sensitivity=20)
        memory_id = result["memory_id"]

        mig_result = self.mgr.migrate(memory_id, "private")
        self.assertTrue(mig_result["success"])

        record = self.mgr.get(memory_id)
        self.assertEqual(record["_chain"], "private")
        self.assertEqual(record["content"], original)
        self.assertGreaterEqual(record["sensitivity"], PRIVACY_THRESHOLD)

    def test_migrate_nonexistent_fails(self):
        """迁移不存在的记忆失败"""
        result = self.mgr.migrate("nonexistent", "private")
        self.assertFalse(result["success"])

    def test_migrate_same_chain_fails(self):
        """迁移到相同链失败"""
        result = self.mgr.save("test", sensitivity=80)
        memory_id = result["memory_id"]
        mig = self.mgr.migrate(memory_id, "private")
        self.assertFalse(mig["success"])

    # ── 统计测试 ──

    def test_stats(self):
        """统计信息正确"""
        self.mgr.save("私有1", sensitivity=80)
        self.mgr.save("私有2", sensitivity=90)
        self.mgr.save("知识1", sensitivity=10)
        self.mgr.save("知识2", sensitivity=20)
        self.mgr.save("知识3", sensitivity=30)

        stats = self.mgr.stats()
        self.assertEqual(stats.private_count, 2)
        self.assertEqual(stats.knowledge_count, 3)
        self.assertEqual(stats.total_count, 5)
        self.assertEqual(stats.private_encrypted_ratio, 1.0)

    def test_stats_empty(self):
        """空链统计"""
        stats = self.mgr.stats()
        self.assertEqual(stats.private_count, 0)
        self.assertEqual(stats.knowledge_count, 0)
        self.assertEqual(stats.total_count, 0)

    # ── 删除测试 ──

    def test_delete_from_private(self):
        """从私有链删除"""
        result = self.mgr.save("待删除", sensitivity=80)
        memory_id = result["memory_id"]

        del_result = self.mgr.delete(memory_id)
        self.assertTrue(del_result["success"])
        self.assertIsNone(self.mgr.get(memory_id))

    def test_delete_from_knowledge(self):
        """从知识链删除"""
        result = self.mgr.save("待删除", sensitivity=20)
        memory_id = result["memory_id"]

        del_result = self.mgr.delete(memory_id)
        self.assertTrue(del_result["success"])
        self.assertIsNone(self.mgr.get(memory_id))

    def test_delete_nonexistent(self):
        """删除不存在的记忆"""
        result = self.mgr.delete("nonexistent")
        self.assertFalse(result["success"])

    def test_clear_chain(self):
        """清空链"""
        self.mgr.save("私有1", sensitivity=80)
        self.mgr.save("私有2", sensitivity=90)
        self.mgr.save("知识1", sensitivity=10)

        self.mgr.clear_chain("private")
        stats = self.mgr.stats()
        self.assertEqual(stats.private_count, 0)
        self.assertEqual(stats.knowledge_count, 1)  # 知识链不受影响

    # ── 持久化测试 ──

    def test_persistence(self):
        """记忆在管理器重启后仍然存在"""
        original = "持久化的私有记忆"
        result = self.mgr.save(original, sensitivity=85, tags=["持久"])
        memory_id = result["memory_id"]

        # 创建新管理器实例（模拟重启）
        new_mgr = self._make_mgr()
        record = new_mgr.get(memory_id)
        self.assertIsNotNone(record)
        self.assertEqual(record["content"], original)
        self.assertEqual(record["_chain"], "private")

    def test_list_chain(self):
        """列出链内容"""
        self.mgr.save("私有记忆", sensitivity=80)
        self.mgr.save("知识记忆", sensitivity=20)

        priv_list = self.mgr.list_chain("private")
        know_list = self.mgr.list_chain("knowledge")

        self.assertEqual(len(priv_list), 1)
        self.assertEqual(len(know_list), 1)
        # 私有链列表显示 [已加密]
        self.assertEqual(priv_list[0]["content"], "[已加密]")
        # 知识链列表显示明文
        self.assertIn("知识记忆", know_list[0]["content"])


if __name__ == "__main__":
    unittest.main()
