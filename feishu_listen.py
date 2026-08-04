"""实时监听飞书所有事件 — 诊断消息是否到达"""
import os, sys, time, threading

# 加载环境变量
from dotenv import load_dotenv
load_dotenv(r"d:\MW\alphaid\projects\.env")

app_id = os.environ.get("FEISHU_APP_ID", "")
app_secret = os.environ.get("FEISHU_APP_SECRET", "")

print("=" * 60)
print("飞书实时事件监听（60秒）")
print("=" * 60)
print(f"APP_ID: {app_id}")
print(f"APP_SECRET: {app_secret[:6]}...{app_secret[-4:]}")
print()
print(">>> 请现在打开飞书，给机器人发一条消息 <<<")
print()

try:
    import lark_oapi as lark
    from lark_oapi.api.im.v1 import P2ImMessageReceiveV1

    received_count = 0

    def on_message(data):
        global received_count
        received_count += 1
        print(f"\n[收到消息 #{received_count}] 类型: {type(data).__name__}")
        try:
            if hasattr(data, 'header') and data.header:
                print(f"  event_type: {data.header.event_type}")
            if hasattr(data, 'event') and data.event:
                if hasattr(data.event, 'message') and data.event.message:
                    msg = data.event.message
                    print(f"  message_id: {msg.message_id}")
                    print(f"  chat_id: {msg.chat_id}")
                    print(f"  msg_type: {msg.message_type}")
                    print(f"  content: {msg.content}")
                if hasattr(data.event, 'sender') and data.event.sender:
                    sender = data.event.sender
                    if hasattr(sender, 'sender_id') and sender.sender_id:
                        print(f"  sender open_id: {sender.sender_id.open_id}")
        except Exception as e:
            print(f"  解析异常: {e}")

    # 注册所有可能的事件处理器
    event_handler = lark.EventDispatcherHandler.builder("", "") \
        .register_p2_im_message_receive_v1(on_message) \
        .build()

    cli = lark.ws.Client(
        app_id,
        app_secret,
        event_handler=event_handler,
        log_level=lark.LogLevel.DEBUG,
    )

    # 60秒后自动退出
    def stop_after_60s():
        time.sleep(60)
        print("\n" + "=" * 60)
        print(f"监听结束。共收到 {received_count} 条消息")
        if received_count == 0:
            print(">>> 没收到任何消息！问题在飞书后台配置 <<<")
            print("请检查：")
            print("  1. 事件订阅：im.message.receive_v1 是否已添加")
            print("  2. 订阅方式：是否选了「长连接」")
            print("  3. 机器人是否已添加到对话（群聊需拉入，单聊需先加机器人）")
            print("  4. 应用是否已发布（版本管理→创建版本→发布）")
        else:
            print(">>> 消息接收正常！问题在回复链路 <<<")
        os._exit(0)

    timer = threading.Thread(target=stop_after_60s, daemon=True)
    timer.start()

    print("连接中...")
    cli.start()

except Exception as e:
    print(f"启动失败: {e}")
    import traceback
    traceback.print_exc()
