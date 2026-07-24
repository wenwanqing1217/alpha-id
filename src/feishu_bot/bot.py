"""
飞书机器人主服务
使用 WebSocket 模式接收消息，不需要公网服务器
"""

import json
import logging
import os
from typing import Callable, Optional

from lark_oapi import Client, EventDispatcherHandler, LogLevel
from lark_oapi.api.im.v1 import (
    CreateMessageRequest,
    CreateMessageRequestBody,
    P2ImMessageReceiveV1,
)
from lark_oapi.ws import Client as WSClient

logger = logging.getLogger("feishu_bot")

# ── 飞书应用凭证（从环境变量读取） ──
APP_ID = os.getenv("FEISHU_APP_ID", "")
APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")


class FeishuBot:
    """飞书机器人，通过 WebSocket 接收消息并转发给 AID"""

    def __init__(self, message_handler: Optional[Callable] = None):
        """
        message_handler: 收到消息后的回调函数
            签名: handler(sender_id, text, chat_id, image_bytes=None) -> str | None
            返回值: 要回复给用户的消息文本（None 则不回复）
        """
        self._handler = message_handler
        self._ws_client: Optional[WSClient] = None
        self._api_client: Optional[Client] = None
        self._log_level = os.getenv("FEISHU_LOG_LEVEL", "INFO").upper()
        self._processed_msgs: set = set()  # 消息去重

    @property
    def api(self) -> Client:
        """获取或创建 API 客户端（用于主动发消息）"""
        if self._api_client is None:
            self._api_client = (
                Client.builder()
                .app_id(APP_ID)
                .app_secret(APP_SECRET)
                .build()
            )
        return self._api_client

    # ── 消息接收 ──

    def _on_message(self, ctx: P2ImMessageReceiveV1) -> None:
        """收到飞书消息时的回调"""
        try:
            event_data = ctx.event
            if not event_data:
                return

            msg = event_data.message
            if not msg:
                return

            # 消息去重：同一消息 ID 只处理一次
            msg_id = msg.message_id if hasattr(msg, 'message_id') else None
            if msg_id:
                if msg_id in self._processed_msgs:
                    logger.info(f"[去重] 跳过重复消息: {msg_id}")
                    return
                self._processed_msgs.add(msg_id)
                # 只保留最近 100 条，防止内存泄漏
                if len(self._processed_msgs) > 100:
                    self._processed_msgs = set(list(self._processed_msgs)[-50:])

            msg_type = msg.message_type
            sender_obj = event_data.sender
            chat_id = msg.chat_id

            # 获取发送者ID
            sender_id = ""
            if sender_obj and sender_obj.sender_id:
                sender_id = (sender_obj.sender_id.user_id
                             or sender_obj.sender_id.open_id
                             or sender_obj.sender_id.union_id
                             or "")

            # ── 图片消息 ──
            image_bytes = None
            if msg_type == "image":
                logger.info(f"[收到图片] from={sender_id} chat={chat_id}")
                image_bytes = self._download_message_image(msg)
                if not image_bytes:
                    self._send_text(chat_id, "图片没下载下来，重新发一张试试？")
                    return
                # 图片消息没有文字，用空文本
                text = "[图片]"

            # 只处理文本和图片消息
            if msg_type not in ("text", "image"):
                return

            # 解析文本内容（content 是 JSON 字符串）
            raw_text = msg.content or ""
            import re
            # 文本消息的 content 格式: {"text":"xxx"}
            try:
                content_json = json.loads(raw_text)
                raw_text = content_json.get("text", raw_text)
            except json.JSONDecodeError:
                pass

            raw_text = raw_text.strip()

            # 去掉 @机器人 前缀
            text = re.sub(r"@_user_\d+\s*", "", raw_text).strip()

            if not text:
                return

            logger.info(f"[收到消息] from={sender_id} chat={chat_id} text={text[:80]}")

            # 调用外部处理器（透传图片数据）
            if self._handler:
                import asyncio
                import inspect
                try:
                    handler = self._handler
                    kwargs = {"image_bytes": image_bytes} if image_bytes else {}
                    if inspect.iscoroutinefunction(handler):
                        reply = asyncio.run(handler(sender_id, text, chat_id, **kwargs))
                    else:
                        reply = handler(sender_id, text, chat_id, **kwargs)
                    if reply:
                        # 如果返回的是 dict（卡片消息），发送卡片
                        if isinstance(reply, dict) and reply.get("type") == "card":
                            card = self._build_nav_card(reply)
                            logger.info(f"  📤 发送卡片 ({reply.get('title', '导航')})")
                            try:
                                self._send_card(chat_id, card)
                            except Exception as card_err:
                                # 卡片发送失败时，降级为纯文本+深链
                                logger.warning(f"  ⚠️ 卡片发送失败({card_err})，降级纯文本")
                                deep_link = reply.get("url", "")
                                fallback_text = reply.get("title", "🗺️ 导航") + "\n"
                                if deep_link:
                                    fallback_text += "📱 点击打开百度地图：\n" + deep_link
                                self._send_text(chat_id, fallback_text)
                        else:
                            logger.info(f"  📤 发送回复 ({len(str(reply))}字)")
                            self._send_text(chat_id, str(reply))
                    else:
                        logger.info(f"  ⏭️ 处理器返回空，不回复")
                except TypeError:
                    # 处理器不支持 image_bytes 参数，降级为纯文本
                    if image_bytes:
                        self._send_text(chat_id, "收到图片，但当前版本暂不支持图片识别，请用文字描述。")
                    else:
                        raise
                except Exception as e:
                    logger.error(f"处理器执行异常: {e}")
            else:
                self._send_text(chat_id, "👻 MindFlow 已上线\n发「注册身份」开始\n或直接告诉我你的地址")

        except Exception as e:
            logger.error(f"解析消息异常: {e}", exc_info=True)

    def _on_message_read(self, ctx) -> None:
        """收到已读回执 — 什么都不做，防止误触发"""
        logger.debug("[已读回执] 忽略，不处理")

    # ── 图片下载（LLM 视觉识别由 main.py 处理） ──

    def _download_message_image(self, msg) -> Optional[bytes]:
        """从飞书下载消息中的图片"""
        try:
            from lark_oapi.api.im.v1 import GetMessageResourceRequest

            image_key = msg.image_key if hasattr(msg, 'image_key') else None
            if not image_key:
                # 尝试从 content 中获取
                try:
                    content = json.loads(msg.content or "{}")
                    image_key = content.get("image_key", "")
                except (json.JSONDecodeError, AttributeError):
                    pass

            if not image_key:
                logger.warning("图片消息没有 image_key")
                return None

            # 调用飞书 API 下载图片
            req = GetMessageResourceRequest.builder() \
                .message_id(msg.message_id) \
                .file_key(image_key) \
                .type("image") \
                .build()

            resp = self.api.im.v1.message_resource.get(req)
            if resp.success() and resp.file:
                return resp.file.read()
            else:
                logger.error(f"下载图片失败: code={resp.code} msg={resp.msg}")
                return None

        except Exception as e:
            logger.error(f"下载图片异常: {e}")
            return None

    # ── 发送消息 ──

    def _send_text(self, chat_id: str, text: str) -> None:
        """发送文本消息到指定会话"""
        try:
            logger.info(f"  📤 发送文本 ({len(text)}字): {text[:80]}")
            body = CreateMessageRequestBody.builder() \
                .receive_id(chat_id) \
                .msg_type("text") \
                .content(json.dumps({"text": text})) \
                .build()

            req = CreateMessageRequest.builder() \
                .receive_id_type("chat_id") \
                .request_body(body) \
                .build()

            resp = self.api.im.v1.message.create(req)

            if not resp.success():
                logger.error(f"发送消息失败: code={resp.code} msg={resp.msg}")

        except Exception as e:
            logger.error(f"发送消息异常: {e}")

    def _send_card(self, chat_id: str, card_json: dict) -> None:
        """内部包装：发送卡片并打印日志"""
        self.send_card(chat_id, card_json)

    def _build_nav_card(self, reply: dict) -> dict:
        """根据 navigate_to 处理器返回的 dict，构建飞书交互卡片

        支持：
        - 单个导航按钮（deep link + HTTP 链接双按钮）
        - 多个候选地点按钮（用 HTTP 链接，兼容性最好）
        """
        elements = [
            {
                "tag": "div",
                "text": {
                    "content": reply.get("content", ""),
                    "tag": "lark_md",
                },
            }
        ]

        deep_link = reply.get("url", "")
        http_link = reply.get("http_url", "")

        # 如果有候选地点列表，为每个候选生成一个按钮（用 HTTP 链接）
        candidates = reply.get("candidates", [])
        if candidates:
            actions = []
            for poi in candidates[:5]:
                name = poi.get("name", "")
                addr = poi.get("address", "")
                lat = poi.get("lat", 0)
                lng = poi.get("lng", 0)
                # 用 HTTP 链接（兼容性最好，浏览器自动跳转 App）
                poi_url = f"https://api.map.baidu.com/destination/marker?location={lat},{lng}&title={name}&coord_type=bd09ll&src=com.feishu.mindflow&output=html"
                actions.append({
                    "tag": "button",
                    "text": {
                        "tag": "plain_text",
                        "content": name + (" — " + addr if addr else ""),
                    },
                    "type": "default",
                    "url": poi_url,
                })
            elements.append({"tag": "action", "actions": actions})
        else:
            # 单按钮：直接打开百度地图 App
            if deep_link:
                elements.append({
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "📱 打开百度地图"},
                            "type": "primary",
                            "url": deep_link,
                        }
                    ],
                })

        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {
                    "content": reply.get("title", "🗺️ 导航"),
                    "tag": "plain_text",
                },
                "template": "turquoise",
            },
            "elements": elements,
        }

    def send_card(self, chat_id: str, card_json: dict) -> None:
        """发送消息卡片到指定会话"""
        try:
            title = card_json.get("header", {}).get("title", {}).get("content", "卡片")
            logger.info(f"  📤 发送卡片: {title}")
            body = CreateMessageRequestBody.builder() \
                .receive_id(chat_id) \
                .msg_type("interactive") \
                .content(json.dumps(card_json, ensure_ascii=False)) \
                .build()

            req = CreateMessageRequest.builder() \
                .receive_id_type("chat_id") \
                .request_body(body) \
                .build()

            resp = self.api.im.v1.message.create(req)

            if not resp.success():
                logger.error(f"发送卡片失败: code={resp.code} msg={resp.msg}")

        except Exception as e:
            logger.error(f"发送卡片异常: {e}")

    # ── 启动/停止 ──

    def start(self) -> None:
        """启动飞书机器人（阻塞）"""
        logger.info("🚀 飞书机器人启动中...")

        # 注册事件处理器（长连接模式不需要 encrypt_key 和 verification_token）
        handler = (
            EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(self._on_message)
            .register_p2_im_message_message_read_v1(self._on_message_read)
            .build()
        )

        self._ws_client = WSClient(
            app_id=APP_ID,
            app_secret=APP_SECRET,
            event_handler=handler,
            log_level=getattr(LogLevel, self._log_level, LogLevel.INFO),
        )

        logger.info("✅ 飞书机器人已就绪，等待消息...")
        logger.info("💡 现在去飞书给机器人发消息试试！")
        self._ws_client.start()

    def stop(self) -> None:
        """停止飞书机器人"""
        logger.info("🛑 飞书机器人停止")


# ── 快捷启动 ──

def run_bot(message_handler=None):
    """启动飞书机器人（快捷入口）"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    bot = FeishuBot(message_handler=message_handler)
    bot.start()
