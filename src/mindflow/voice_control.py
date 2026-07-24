"""
MindFlow 语音唤起 & 手机控制

架构设计：
  ┌──────────────┐     WebSocket      ┌──────────────┐
  │  Android App │ ◄──────────────► │  MindFlow    │
  │  (小流助手)   │    语音/指令       │  Bot Server  │
  └──────────────┘                   └──────────────┘
        │                                  │
    ┌───┴───┐                          ┌───┴───┐
    │语音唤醒│                          │ LLM   │
    │语音识别│                          │ 意图  │
    │TTS回复 │                          │ 执行  │
    │系统控制│                          │       │
    └───────┘                          └───────┘

Android 端（小流助手 App）职责：
  1. 常驻后台，监听唤醒词"小流"
  2. 唤醒后录音 → 语音识别（ASR）→ 发送文字给 MindFlow
  3. 接收 MindFlow 返回的文字/指令
  4. TTS 朗读回复
  5. 解析控制指令，执行系统操作

手机控制指令（MindFlow → Android）：
  { "type": "navigate", "destination": "公司" }     → 打开百度地图导航
  { "type": "call", "contact": "张三" }              → 拨打电话
  { "type": "sms", "contact": "张三", "text": "..." } → 发送短信
  { "type": "app", "name": "微信" }                  → 打开应用
  { "type": "reminder", "time": "18:00", "text": "下班" } → 设置提醒
  { "type": "tts", "text": "你好" }                  → TTS 朗读
  { "type": "camera", "mode": "photo" }             → 打开相机
  { "type": "screenshot" }                           → 截屏
"""

import json
import logging
import os
import time
from typing import Any, Dict, Optional

logger = logging.getLogger("mindflow.voice_control")


# ── 指令类型常量 ──

class PhoneCommand:
    """手机控制指令类型"""
    NAVIGATE = "navigate"       # 导航
    CALL = "call"               # 打电话
    SMS = "sms"                 # 发短信
    APP = "app"                 # 打开应用
    REMINDER = "reminder"       # 设置提醒
    TTS = "tts"                 # TTS 朗读
    CAMERA = "camera"           # 相机
    SCREENSHOT = "screenshot"   # 截屏
    HOME = "home"               # 回到主页
    WEATHER = "weather"         # 查天气（语音播报）
    MUSIC = "music"             # 播放音乐


# ── 指令构建器 ──

def build_navigate_command(destination: str, mode: str = "driving") -> Dict:
    """构建导航指令"""
    import urllib.parse
    return {
        "type": PhoneCommand.NAVIGATE,
        "destination": destination,
        "mode": mode,
        "deep_link": f"baidumap://map/destination?destination={urllib.parse.quote(destination)}&mode={mode}",
    }


def build_call_command(contact: str) -> Dict:
    """构建打电话指令"""
    return {
        "type": PhoneCommand.CALL,
        "contact": contact,
    }


def build_sms_command(contact: str, text: str) -> Dict:
    """构建发短信指令"""
    return {
        "type": PhoneCommand.SMS,
        "contact": contact,
        "text": text,
    }


def build_app_command(app_name: str) -> Dict:
    """构建打开应用指令"""
    # 常见应用包名映射
    app_packages = {
        "微信": "com.tencent.mm",
        "支付宝": "com.eg.android.AlipayGphone",
        "抖音": "com.ss.android.ugc.aweme",
        "淘宝": "com.taobao.taobao",
        "百度地图": "com.baidu.BaiduMap",
        "高德地图": "com.autonavi.minimap",
        "美团": "com.sankuai.meituan",
        "滴滴": "com.sdu.didi.psnger",
        "京东": "com.jingdong.app.mall",
        "QQ": "com.tencent.mobileqq",
        "微博": "com.sina.weibo",
        "bilibili": "tv.danmaku.bili",
    }
    return {
        "type": PhoneCommand.APP,
        "name": app_name,
        "package": app_packages.get(app_name, ""),
    }


def build_reminder_command(time_str: str, text: str) -> Dict:
    """构建提醒指令"""
    return {
        "type": PhoneCommand.REMINDER,
        "time": time_str,
        "text": text,
    }


def build_tts_command(text: str) -> Dict:
    """构建 TTS 朗读指令"""
    return {
        "type": PhoneCommand.TTS,
        "text": text,
    }


def build_music_command(song: str = "", action: str = "play") -> Dict:
    """构建音乐控制指令"""
    return {
        "type": PhoneCommand.MUSIC,
        "song": song,
        "action": action,  # play / pause / next / prev
    }


# ── 语音命令路由器 ──

def route_voice_command(text: str, user_profile=None) -> Dict:
    """
    将用户的语音文字转为手机控制指令
    
    返回格式：
      { "action": "command", "command": { ... } }  → 执行指令
      { "action": "chat", "text": "..." }          → 普通对话
    """
    text = text.strip()

    # 导航相关
    navigate_keywords = ["导航", "去", "到", "怎么走", "路线"]
    if any(kw in text for kw in navigate_keywords):
        # 提取目的地
        import re
        m = re.search(r'(?:导航|去|到|路线)\s*(.+?)$', text)
        if m:
            dest = m.group(1).strip()
            # 去除语气词
            dest = re.sub(r'^[吧啊呀嘛]+|[吧啊呀嘛]+$', '', dest).strip()
            if dest:
                cmd = build_navigate_command(dest)
                return {"action": "command", "command": cmd, "reply": f"好的，为你导航到{dest}"}

    # 打电话
    if "打电话" in text or "拨打" in text or "呼叫" in text:
        import re
        m = re.search(r'(?:打电话|拨打|呼叫)\s*(.+?)$', text)
        if m:
            contact = m.group(1).strip()
            contact = re.sub(r'^[给向对]|[吧啊呀嘛]+$', '', contact).strip()
            cmd = build_call_command(contact)
            return {"action": "command", "command": cmd, "reply": f"好的，拨打{contact}"}

    # 发短信
    if "发短信" in text or "发消息" in text or "发微信" in text:
        import re
        m = re.search(r'(?:发短信|发消息|发微信)\s*(?:给|向)?\s*(.+?)[，,]?\s*(?:说|内容|告诉)\s*(.+)$', text)
        if m:
            contact = m.group(1).strip()
            msg = m.group(2).strip()
            cmd = build_sms_command(contact, msg)
            return {"action": "command", "command": cmd, "reply": f"好的，给{contact}发消息：{msg}"}

    # 打开应用
    if "打开" in text or "启动" in text:
        import re
        m = re.search(r'(?:打开|启动)\s*(.+?)$', text)
        if m:
            app_name = m.group(1).strip()
            cmd = build_app_command(app_name)
            return {"action": "command", "command": cmd, "reply": f"好的，打开{app_name}"}

    # 设提醒
    if "提醒" in text or "闹钟" in text:
        import re
        m = re.search(r'(.+?)(?:点|时)(.+?)(?:提醒|闹钟)\s*(?:我)?\s*(.+?)$', text)
        if m:
            hour = m.group(1).strip()
            minute = m.group(2).strip()
            reminder_text = m.group(3).strip()
            time_str = f"{hour}:{minute}"
            cmd = build_reminder_command(time_str, reminder_text)
            return {"action": "command", "command": cmd, "reply": f"好的，{time_str}提醒你{reminder_text}"}

    # 音乐控制
    if "播放" in text or "听歌" in text or "音乐" in text:
        import re
        m = re.search(r'(?:播放|听歌|音乐)\s*(.+?)$', text)
        if m:
            song = m.group(1).strip()
            cmd = build_music_command(song)
            return {"action": "command", "command": cmd, "reply": f"好的，播放{song}"}

    if "暂停" in text or "停止播放" in text:
        cmd = build_music_command(action="pause")
        return {"action": "command", "command": cmd, "reply": "已暂停"}

    if "下一首" in text or "切歌" in text:
        cmd = build_music_command(action="next")
        return {"action": "command", "command": cmd, "reply": "下一首"}

    # 截屏
    if "截屏" in text or "截图" in text or "拍照" in text:
        return {"action": "command", "command": {"type": PhoneCommand.SCREENSHOT}, "reply": "已截屏"}

    # 天气语音播报
    if "天气" in text and ("语音" in text or "播报" in text or "读" in text):
        return {"action": "command", "command": {"type": PhoneCommand.WEATHER}, "reply": "好的，为你查询天气"}

    # 默认 → 普通对话
    return {"action": "chat", "text": text}


# ── Android App 占位（后续实现） ──

ANDROID_APP_TEMPLATE = """
// 小流助手 Android App 骨架
// 文件：app/src/main/java/com/mindflow/xiaoliu/

// MainActivity.kt - 主界面
// VoiceService.kt - 后台语音唤醒服务
// WakeWordDetector.kt - 唤醒词检测（"小流"）
// CommandExecutor.kt - 指令执行器
// MindFlowApi.kt - 与 Bot 服务器通信

// 核心流程：
// 1. VoiceService 常驻后台
// 2. WakeWordDetector 检测到"小流" → 开始录音
// 3. 录音结束 → ASR（语音识别）→ 发送文字到 MindFlow
// 4. 接收回复 → TTS 朗读 + 执行控制指令

// 实现优先级：
// P0: 基础对话（语音问 → Bot 回 → TTS 读）
// P1: 导航指令（调用百度地图）
// P2: 电话/短信/应用控制
// P3: 提醒/音乐/相机
// P4: 离线唤醒词（不用云端）
"""

# ── 测试入口 ──

if __name__ == "__main__":
    # 测试命令路由
    test_cases = [
        "导航到公司",
        "打电话给张三",
        "发短信给老婆说我晚点回家",
        "打开微信",
        "明天早上7点提醒我开会",
        "播放周杰伦的稻香",
        "截屏",
        "今天天气怎么样",
        "你好",
    ]

    for text in test_cases:
        result = route_voice_command(text)
        print(f"📝 \"{text}\"")
        print(f"   → {result}")
        print()
