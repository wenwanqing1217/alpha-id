"""飞书连接诊断脚本 — 独立验证 SDK 能否连通飞书"""
import json
import os
import sys
import time

os.environ.setdefault("LARK_LOG_LEVEL", "DEBUG")

def main():
    print("=" * 60)
    print("飞书连接诊断")
    print("=" * 60)

    # 1. 检查凭证
    app_id = os.environ.get("FEISHU_APP_ID", "")
    app_secret = os.environ.get("FEISHU_APP_SECRET", "")

    if not app_id:
        print("❌ FEISHU_APP_ID 未设置")
        sys.exit(1)
    if not app_secret:
        print("❌ FEISHU_APP_SECRET 未设置")
        sys.exit(1)

    print(f"✅ FEISHU_APP_ID: {app_id[:4]}...{app_id[-4:]}")
    print(f"✅ FEISHU_APP_SECRET: {app_secret[:4]}...{app_secret[-4:]}")

    # 2. 检查飞书后台配置（提示用户）
    print("\n" + "=" * 60)
    print("⚠️  请确认飞书开发者后台配置：")
    print("=" * 60)
    print("1. 进入 https://open.feishu.cn/app → 你的应用")
    print("2. 左侧菜单 → 事件与回调 → 事件配置")
    print("3. 订阅方式：选择「使用长连接接收事件回调」")
    print("4. 已添加事件：im.message.receive_v1（接收消息 v2.0）")
    print("5. 权限管理：已开启 im:message（获取与发送消息）")

    # 3. 测试 token 获取
    print("\n" + "=" * 60)
    print("测试 1: 获取 tenant_access_token")
    print("=" * 60)
    try:
        import httpx
        resp = httpx.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": app_id, "app_secret": app_secret},
            timeout=10,
        )
        data = resp.json()
        if data.get("code") == 0:
            print(f"✅ Token 获取成功 (expires_in={data.get('expire', '?')}s)")
        else:
            print(f"❌ Token 获取失败: code={data.get('code')}, msg={data.get('msg')}")
            print("   → 请检查 App ID 和 App Secret 是否正确")
            sys.exit(1)
    except Exception as e:
        print(f"❌ 网络异常: {e}")
        sys.exit(1)

    # 4. 测试 SDK 连接
    print("\n" + "=" * 60)
    print("测试 2: 启动飞书 WebSocket 长连接（10 秒后自动退出）")
    print("=" * 60)

    try:
        import lark_oapi as lark

        received = []

        def on_message(data):
            received.append(data)
            event_type = data.header.event_type if hasattr(data, 'header') else 'unknown'
            print(f"📩 收到事件: type={event_type}")
            if data.event and hasattr(data.event, 'message') and data.event.message:
                msg = data.event.message
                content = msg.content or "{}"
                try:
                    c = json.loads(content)
                    print(f"   内容: {c.get('text', content[:80])}")
                except Exception:
                    print(f"   内容: {content[:80]}")

        event_handler = lark.EventDispatcherHandler.builder("", "") \
            .register_p2_im_message_receive_v1(on_message) \
            .build()

        cli = lark.ws.Client(
            app_id, app_secret,
            event_handler=event_handler,
            log_level=lark.LogLevel.INFO,
        )

        print("⏳ 连接中... (10 秒后自动退出)")

        import threading
        timer = threading.Timer(10, lambda: os._exit(0))
        timer.daemon = True
        timer.start()

        cli.start()

    except SystemExit:
        print("\n" + "=" * 60)
        print("测试完成")
        if received:
            print(f"✅ 成功收到 {len(received)} 条消息")
        else:
            print("⚠️  10 秒内未收到任何消息")
            print("   可能原因：")
            print("   - 飞书后台未配置「使用长连接接收事件回调」")
            print("   - 未添加 im.message.receive_v1 事件")
            print("   - 机器人未被添加到对话中（单聊需先在后台开启机器人能力）")
            print("   - 等待时间太短，多试几次")
        sys.exit(0)
    except Exception as e:
        print(f"❌ SDK 错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()