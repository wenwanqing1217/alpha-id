"""微信适配器 — 通过 EventBus 发布行动事件，跨服务分发执行"""
import logging
from typing import Any, Dict

from core.event_bus import emit, EventType
from . import PlatformAdapter

logger = logging.getLogger(__name__)


class WeChatAdapter(PlatformAdapter):
    """
    微信适配器：将行动发布到 EventBus 跨服务事件总线。

    不直接调用微信 API，而是通过 EventBus 将行动事件发布到 Redis Stream，
    由 Gateway /webhook/wechat 或其他消费者实际执行微信调用。
    """

    @property
    def platform_name(self) -> str:
        return "wechat"

    def execute(self, action) -> Dict[str, Any]:
        logger.info("[WeChatAdapter] 发布行动到 EventBus: %s", action.intent)
        event = emit(
            EventType.SOCIAL_MESSAGE,
            {
                "platform": "wechat",
                "action_type": action.action_type.name,
                "intent": action.intent,
                "payload": action.payload,
                "source_alpha_id": getattr(action, "source_alpha_id", ""),
            },
            source="wechat_adapter",
        )
        return {
            "success": True,
            "message": f"[WeChat] 行动已发布到 EventBus (event_id={event.event_id})",
            "data": {"event_id": event.event_id, "platform": "wechat"},
            "executed_at": event.timestamp,
        }

    def get_capabilities(self) -> Dict[str, Any]:
        return {
            "platform": "wechat",
            "actions": ["POST", "SEND_MESSAGE", "SEND_IMAGE", "ADD_FRIEND"],
            "authenticated": False,
            "note": "EventBus-backed adapter — actions published to Redis Stream",
        }
