"""微信适配器（暂未实现，占位）"""
from core.action_engine.adapters import PlatformAdapter
class WeChatAdapter(PlatformAdapter):
    async def execute(self, action):
        return {"success": False, "error": "微信适配器未实现"}
