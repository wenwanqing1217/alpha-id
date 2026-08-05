"""Credits Wallet — 用户积分钱包（a-to-a 经济模型基础）

TERM: Credits — 积分系统（社交免费 + 陌生人付费）

设计理念：
  用户调用其他用户的 agent 时，按社交关系计费：
    - 好友免费（owner_alpha_id 是调用方好友 → price_credits=0）
    - 陌生人付费（按 agent.price_credits 扣分）
    - 自己的 agent 永远免费

  平台基建 agent（owner_alpha_id=""）永远免费。

核心接口：
  - balance(alpha_id) → int                    查询余额
  - charge(alpha_id, amount, reason, ...) → Tx  扣分（调用方付费）
  - reward(alpha_id, amount, reason, ...) → Tx  得分（agent owner 收益）
  - settle_call(caller, owner, price, ...) →   一次调用的完整结算
      - caller 扣 price，owner 得 price * (1 - fee_rate)
      - 平台抽成 fee_rate（默认 0.1）
  - get_transactions(alpha_id, limit) → List    交易流水

存储：复用 StorageBackend（SQLite/Postgres），key="credits_wallets" / "credits_transactions"
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.storage import StorageBackend

logger = logging.getLogger(__name__)


# ── 默认配置 ──────────────────────────────────────────────────

DEFAULT_INITIAL_CREDITS = 100         # 新用户注册赠送 100 积分
DEFAULT_PLATFORM_FEE_RATE = 0.10      # 平台抽成 10%
DEFAULT_MIN_BALANCE = 0               # 余额下限（不允许欠费）


# ── 数据模型 ──────────────────────────────────────────────────

@dataclass
class Wallet:
    """用户钱包"""
    alpha_id: str
    balance: int = DEFAULT_INITIAL_CREDITS
    total_earned: int = 0       # 累计收入
    total_spent: int = 0        # 累计支出
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


@dataclass
class Transaction:
    """交易记录"""
    tx_id: str                       # 交易 ID
    alpha_id: str                    # 所属用户
    direction: str                   # "credit"（得分）/ "debit"（扣分）
    amount: int                      # 积分数（正数）
    reason: str                      # trade_code: a2a_call / reward / register / refund
    counterparty: str = ""           # 对手方 alpha_id（如有）
    agent_id: str = ""               # 涉及的 agent_id（如有）
    skill: str = ""                  # 调用的 skill（如有）
    request_id: str = ""             # A2A request_id（如有）
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


# ── 钱包管理器 ────────────────────────────────────────────────

class CreditsManager:
    """积分钱包管理器

    线程安全。复用 StorageBackend.load/save 接口（与 AlphaSocialManager 一致）。
    """

    def __init__(
        self,
        storage: Optional[StorageBackend] = None,
        social_manager=None,  # AlphaSocialManager，用于判断好友关系
        platform_fee_rate: float = DEFAULT_PLATFORM_FEE_RATE,
        initial_credits: int = DEFAULT_INITIAL_CREDITS,
    ):
        if storage is None:
            from core.storage_sqlite import SqliteStorage
            storage = SqliteStorage()
        self._storage = storage
        self._social = social_manager
        self._platform_fee_rate = platform_fee_rate
        self._initial_credits = initial_credits
        self._lock = threading.RLock()
        self._init_storage()

    def _init_storage(self) -> None:
        """初始化存储集合"""
        if self._storage.load("credits_wallets") is None:
            self._storage.save("credits_wallets", {})
        if self._storage.load("credits_transactions") is None:
            self._storage.save("credits_transactions", {})

    # ── 钱包操作 ──

    def get_wallet(self, alpha_id: str) -> Wallet:
        """获取钱包（不存在则自动创建，赠送初始积分）"""
        with self._lock:
            wallets = self._storage.load("credits_wallets") or {}
            data = wallets.get(alpha_id)
            if data is None:
                wallet = Wallet(alpha_id=alpha_id)
                wallets[alpha_id] = asdict(wallet)
                self._storage.save("credits_wallets", wallets)
                # 记录初始赠送
                self._record_tx(Transaction(
                    tx_id=self._gen_tx_id(),
                    alpha_id=alpha_id,
                    direction="credit",
                    amount=self._initial_credits,
                    reason="register",
                    metadata={"note": "新用户注册赠送"},
                ))
                logger.info("Credits 钱包创建: %s (+%d)", alpha_id, self._initial_credits)
                return wallet
            return Wallet(**data)

    def balance(self, alpha_id: str) -> int:
        """查询余额"""
        return self.get_wallet(alpha_id).balance

    def charge(
        self,
        alpha_id: str,
        amount: int,
        reason: str,
        counterparty: str = "",
        agent_id: str = "",
        skill: str = "",
        request_id: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Transaction:
        """扣分

        Raises:
            InsufficientBalanceError: 余额不足
        """
        if amount < 0:
            raise ValueError("扣分金额必须 >= 0")
        if amount == 0:
            return Transaction(
                tx_id=self._gen_tx_id(),
                alpha_id=alpha_id,
                direction="debit",
                amount=0,
                reason=reason,
                counterparty=counterparty,
                agent_id=agent_id,
                skill=skill,
                request_id=request_id,
                metadata=metadata or {},
            )

        with self._lock:
            wallets = self._storage.load("credits_wallets") or {}
            data = wallets.get(alpha_id)
            if data is None:
                # 自动建钱包
                wallet = self.get_wallet(alpha_id)
                wallets = self._storage.load("credits_wallets") or {}
                data = wallets[alpha_id]

            wallet = Wallet(**data)
            if wallet.balance < amount:
                raise InsufficientBalanceError(
                    f"余额不足: {wallet.balance} < {amount} (用户 {alpha_id})"
                )

            wallet.balance -= amount
            wallet.total_spent += amount
            wallet.updated_at = time.time()
            wallets[alpha_id] = asdict(wallet)
            self._storage.save("credits_wallets", wallets)

            tx = Transaction(
                tx_id=self._gen_tx_id(),
                alpha_id=alpha_id,
                direction="debit",
                amount=amount,
                reason=reason,
                counterparty=counterparty,
                agent_id=agent_id,
                skill=skill,
                request_id=request_id,
                metadata=metadata or {},
            )
            self._record_tx(tx)
            logger.info(
                "Credits 扣分: %s -%d (reason=%s, agent=%s) → 余额 %d",
                alpha_id, amount, reason, agent_id, wallet.balance,
            )
            return tx

    def reward(
        self,
        alpha_id: str,
        amount: int,
        reason: str,
        counterparty: str = "",
        agent_id: str = "",
        skill: str = "",
        request_id: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Transaction:
        """得分"""
        if amount < 0:
            raise ValueError("得分金额必须 >= 0")
        if amount == 0:
            return Transaction(
                tx_id=self._gen_tx_id(),
                alpha_id=alpha_id,
                direction="credit",
                amount=0,
                reason=reason,
                counterparty=counterparty,
                agent_id=agent_id,
                skill=skill,
                request_id=request_id,
                metadata=metadata or {},
            )

        with self._lock:
            # 自动建钱包
            self.get_wallet(alpha_id)
            wallets = self._storage.load("credits_wallets") or {}
            data = wallets[alpha_id]
            wallet = Wallet(**data)
            wallet.balance += amount
            wallet.total_earned += amount
            wallet.updated_at = time.time()
            wallets[alpha_id] = asdict(wallet)
            self._storage.save("credits_wallets", wallets)

            tx = Transaction(
                tx_id=self._gen_tx_id(),
                alpha_id=alpha_id,
                direction="credit",
                amount=amount,
                reason=reason,
                counterparty=counterparty,
                agent_id=agent_id,
                skill=skill,
                request_id=request_id,
                metadata=metadata or {},
            )
            self._record_tx(tx)
            logger.info(
                "Credits 得分: %s +%d (reason=%s, agent=%s) → 余额 %d",
                alpha_id, amount, reason, agent_id, wallet.balance,
            )
            return tx

    def refund(self, tx_id: str, reason: str = "refund") -> Optional[Transaction]:
        """退款（按原 tx_id 找到扣分记录，等额返还）"""
        with self._lock:
            txs = self._storage.load("credits_transactions") or {}
            original = None
            for tx_data in txs.values():
                if tx_data.get("tx_id") == tx_id:
                    original = tx_data
                    break
            if not original:
                return None
            if original["direction"] != "debit":
                return None
            return self.reward(
                alpha_id=original["alpha_id"],
                amount=original["amount"],
                reason=reason,
                counterparty=original.get("counterparty", ""),
                agent_id=original.get("agent_id", ""),
                skill=original.get("skill", ""),
                request_id=original.get("request_id", ""),
                metadata={"refund_of": tx_id},
            )

    # ── A2A 调用结算 ──

    def settle_call(
        self,
        caller_alpha_id: str,
        owner_alpha_id: str,
        price_credits: int,
        agent_id: str = "",
        skill: str = "",
        request_id: str = "",
        is_friend: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """A2A 调用结算 — 一次完整扣分+得分流程

        规则：
          1. owner_alpha_id 空（平台基建）→ 免费
          2. caller == owner → 免费（自己的 agent）
          3. is_friend=True（好友）→ 免费
          4. 其他情况 → caller 扣 price_credits，owner 得 price * (1 - fee_rate)

        Args:
            is_friend: 显式传入好友关系；None 则自动用 social_manager 判断

        Returns:
            {"charged": bool, "price": int, "caller_tx": ..., "owner_tx": ...,
             "platform_fee": int, "reason": str}
        """
        # 平台基建 agent 免费
        if not owner_alpha_id:
            return {
                "charged": False,
                "price": 0,
                "reason": "platform_infra_free",
                "caller_tx": None,
                "owner_tx": None,
                "platform_fee": 0,
            }
        # 自己的 agent 免费
        if caller_alpha_id == owner_alpha_id:
            return {
                "charged": False,
                "price": 0,
                "reason": "self_owned_free",
                "caller_tx": None,
                "owner_tx": None,
                "platform_fee": 0,
            }
        # 好友免费
        if is_friend is None and self._social is not None:
            try:
                is_friend = owner_alpha_id in self._social.get_friends(caller_alpha_id)
            except Exception as e:
                logger.warning("好友关系查询失败: %s", e)
                is_friend = False

        if is_friend:
            return {
                "charged": False,
                "price": 0,
                "reason": "friend_free",
                "caller_tx": None,
                "owner_tx": None,
                "platform_fee": 0,
            }

        # 陌生人付费
        if price_credits <= 0:
            return {
                "charged": False,
                "price": 0,
                "reason": "free_agent",
                "caller_tx": None,
                "owner_tx": None,
                "platform_fee": 0,
            }

        # 平台抽成
        platform_fee = int(price_credits * self._platform_fee_rate)
        owner_gain = price_credits - platform_fee

        # 扣分（caller）
        caller_tx = self.charge(
            alpha_id=caller_alpha_id,
            amount=price_credits,
            reason="a2a_call",
            counterparty=owner_alpha_id,
            agent_id=agent_id,
            skill=skill,
            request_id=request_id,
            metadata={"platform_fee": platform_fee, "owner_gain": owner_gain},
        )
        # 得分（owner）
        owner_tx = self.reward(
            alpha_id=owner_alpha_id,
            amount=owner_gain,
            reason="a2a_earning",
            counterparty=caller_alpha_id,
            agent_id=agent_id,
            skill=skill,
            request_id=request_id,
            metadata={"platform_fee": platform_fee, "original_price": price_credits},
        )

        return {
            "charged": True,
            "price": price_credits,
            "reason": "stranger_paid",
            "caller_tx": asdict(caller_tx),
            "owner_tx": asdict(owner_tx),
            "platform_fee": platform_fee,
            "owner_gain": owner_gain,
        }

    # ── 查询 ──

    def get_transactions(
        self,
        alpha_id: str,
        limit: int = 50,
        offset: int = 0,
        direction: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """查询用户交易流水"""
        txs = self._storage.load("credits_transactions") or {}
        items = [t for t in txs.values() if t.get("alpha_id") == alpha_id]
        if direction:
            items = [t for t in items if t.get("direction") == direction]
        items.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
        return items[offset:offset + limit]

    def get_wallet_summary(self, alpha_id: str) -> Dict[str, Any]:
        """钱包摘要（前端展示用）"""
        wallet = self.get_wallet(alpha_id)
        txs = self.get_transactions(alpha_id, limit=9999)
        return {
            "alpha_id": wallet.alpha_id,
            "balance": wallet.balance,
            "total_earned": wallet.total_earned,
            "total_spent": wallet.total_spent,
            "transaction_count": len(txs),
            "created_at": wallet.created_at,
            "updated_at": wallet.updated_at,
        }

    # ── 内部工具 ──

    def _record_tx(self, tx: Transaction) -> None:
        """记录交易流水"""
        with self._lock:
            txs = self._storage.load("credits_transactions") or {}
            txs[tx.tx_id] = asdict(tx)
            self._storage.save("credits_transactions", txs)

    @staticmethod
    def _gen_tx_id() -> str:
        return f"tx_{uuid.uuid4().hex[:20]}"


class InsufficientBalanceError(Exception):
    """余额不足"""
    pass


# ── 全局单例 ──────────────────────────────────────────────────

_global_manager: Optional[CreditsManager] = None
_singleton_lock = threading.Lock()


def get_credits_manager(
    storage: Optional[StorageBackend] = None,
    social_manager=None,
) -> CreditsManager:
    """获取全局 CreditsManager 单例

    首次调用时初始化，后续调用忽略参数（除非强制 reset）。
    """
    global _global_manager
    if _global_manager is None:
        with _singleton_lock:
            if _global_manager is None:
                _global_manager = CreditsManager(
                    storage=storage,
                    social_manager=social_manager,
                )
    return _global_manager


def reset_credits_manager() -> None:
    """重置单例（测试用）"""
    global _global_manager
    with _singleton_lock:
        _global_manager = None
