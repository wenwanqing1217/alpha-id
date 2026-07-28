"""
Alpha-ID Baidu AI Map — 百度地图 AI 技能
==========================================

将 skills/baidu-ai-map/SKILL.md 描述的百度地图能力集成为 Python 客户端：
  - 语义化 AI 地点检索
  - 语义化 AI 路线规划
  - 地理编码与逆地理编码
  - 天气查询
  - 地图展示

用法：
    from alpha_id.skills.baidu_ai_map import BaiduMapClient, BaiduMapConfig

    config = BaiduMapConfig(auth_token="your_sk")
    client = BaiduMapClient(config)

    # 地点检索
    results = client.search_places("北京可带宠物的咖啡馆", region="北京市")

    # 路线规划
    route = client.plan_route("北京站", "北京西站", mode="driving")

    # 地理编码
    coords = client.geocode("北京市海淀区中关村")

    # 天气
    weather = client.get_weather("北京市")

独立运行：
    python -m alpha_id.skills.baidu_ai_map
"""

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

# 百度地图 API Base URL
BASE_URL = "https://api.map.baidu.com"


@dataclass
class BaiduMapConfig:
    """百度地图配置"""
    auth_token: str = ""
    timeout: int = 30
    default_region: str = "北京市"

    def __post_init__(self):
        if not self.auth_token:
            self.auth_token = os.environ.get("BAIDU_MAP_AUTH_TOKEN", "")


class BaiduMapClient:
    """
    百度地图 AI 技能客户端

    封装百度地图 Agent Plan API，提供语义化地点检索、路线规划、
    地理编码、逆地理编码、天气查询等能力。
    """

    def __init__(self, config: Optional[BaiduMapConfig] = None):
        self._config = config or BaiduMapConfig()
        self._base_url = BASE_URL
        self._timeout = self._config.timeout
        self._stats = {"requests": 0, "errors": 0}

    # ── 内部 HTTP 方法 ──

    def _request(self, path: str, params: Dict[str, str],
                 method: str = "GET") -> Dict[str, Any]:
        """
        发送 API 请求

        Args:
            path: API 路径（如 /agent_plan/v1/place）
            params: 查询参数
            method: GET 或 POST

        Returns:
            JSON 响应
        """
        import urllib.request
        import urllib.error

        url = f"{self._base_url}{path}"

        if method == "GET" and params:
            url = f"{url}?{urlencode(params)}"

        headers = {}
        if self._config.auth_token:
            headers["Authorization"] = f"Bearer {self._config.auth_token}"

        self._stats["requests"] += 1

        try:
            if method == "POST":
                data = urlencode(params).encode("utf-8")
                req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            else:
                req = urllib.request.Request(url, headers=headers)

            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body) if body else {}

        except urllib.error.HTTPError as e:
            self._stats["errors"] += 1
            error_body = e.read().decode("utf-8", errors="replace")[:500]
            logger.error("百度地图 API HTTP %d: %s", e.code, error_body)
            return {"error": f"HTTP {e.code}", "message": error_body}
        except Exception as e:
            self._stats["errors"] += 1
            logger.error("百度地图 API 异常: %s", e)
            return {"error": str(e)}

    # ── 1. 语义化 AI 地点检索 ──

    def search_places(self, query: str, region: str = "",
                      **kwargs) -> Dict[str, Any]:
        """
        语义化 AI 地点检索

        Args:
            query: 用户原始需求（如"北京可带宠物的咖啡馆"）
            region: 城市或区域限制（如"北京市"）
            **kwargs: 其他参数

        Returns:
            地点列表
        """
        params = {
            "user_raw_request": query,
            "region": region or self._config.default_region,
        }
        params.update(kwargs)
        return self._request("/agent_plan/v1/place", params)

    # ── 2. 语义化 AI 路线规划 ──

    def plan_route(self, origin: str, destination: str,
                   mode: str = "driving", **kwargs) -> Dict[str, Any]:
        """
        语义化 AI 路线规划

        Args:
            origin: 起点（如"北京站"）
            destination: 终点（如"北京西站"）
            mode: 出行方式（driving / walking / riding / transit）
            **kwargs: 其他参数

        Returns:
            路线规划结果
        """
        params = {
            "user_raw_request": f"从{origin}到{destination}",
            "origin": origin,
            "destination": destination,
            "mode": mode,
        }
        params.update(kwargs)
        return self._request("/agent_plan/v1/route", params)

    # ── 3. 地理编码 ──

    def geocode(self, address: str, **kwargs) -> Dict[str, Any]:
        """
        地理编码（地址 → 坐标）

        Args:
            address: 地址（如"北京市海淀区中关村"）
            **kwargs: 其他参数

        Returns:
            坐标信息
        """
        params = {"address": address}
        params.update(kwargs)
        return self._request("/agent_plan/v1/geocoding", params)

    # ── 4. 逆地理编码 ──

    def reverse_geocode(self, lng: float, lat: float,
                        **kwargs) -> Dict[str, Any]:
        """
        逆地理编码（坐标 → 地址）

        Args:
            lng: 经度
            lat: 纬度
            **kwargs: 其他参数

        Returns:
            地址信息
        """
        params = {"location": f"{lat},{lng}"}
        params.update(kwargs)
        return self._request("/agent_plan/v1/reverse_geocoding", params)

    # ── 5. 天气查询 ──

    def get_weather(self, region: str = "", **kwargs) -> Dict[str, Any]:
        """
        天气查询

        Args:
            region: 城市或区域（如"北京市"）
            **kwargs: 其他参数

        Returns:
            天气信息
        """
        params = {"region": region or self._config.default_region}
        params.update(kwargs)
        return self._request("/agent_plan/v1/weather", params)

    # ── 6. 智能助手（综合） ──

    def assist(self, user_request: str, region: str = "") -> Dict[str, Any]:
        """
        智能助手 — 自动判断用户意图并调用对应工具

        支持：
        - "找XX" / "搜XX" → 地点检索
        - "从A到B" / "去XX" → 路线规划
        - "XX在哪里" → 地理编码
        - "天气" / "气温" → 天气查询

        Args:
            user_request: 用户原始请求
            region: 区域限制

        Returns:
            结果字典
        """
        request = user_request.strip()
        if not request:
            return {"error": "请求不能为空"}

        # 路线规划
        route_patterns = [
            r'从(.+?)到(.+?)',
            r'去(.+?)',
            r'到(.+?)怎么走',
            r'从(.+?)出发',
        ]
        for pattern in route_patterns:
            m = re.search(pattern, request)
            if m:
                if len(m.groups()) >= 2:
                    return self.plan_route(m.group(1).strip(), m.group(2).strip())
                else:
                    dest = m.group(1).strip()
                    return self.plan_route("我的位置", dest)

        # 天气
        weather_patterns = [r'天气', r'气温', r'下雨', r'刮风', r'温度']
        for pattern in weather_patterns:
            if re.search(pattern, request):
                return self.get_weather(region)

        # 地理编码
        geo_patterns = [r'(.+?)在哪里', r'(.+?)的位置', r'在哪']
        for pattern in geo_patterns:
            m = re.search(pattern, request)
            if m:
                return self.geocode(m.group(1).strip())

        # 默认：地点检索
        return self.search_places(request, region)

    # ── 统计 ──

    @property
    def stats(self) -> Dict[str, int]:
        return self._stats.copy()

    @property
    def is_available(self) -> bool:
        """是否配置了 auth_token"""
        return bool(self._config.auth_token)


# ══════════════════════════════════════════════════════════════
# CLI 入口
# ══════════════════════════════════════════════════════════════

def main():
    """独立运行入口"""
    import argparse

    parser = argparse.ArgumentParser(description="Alpha-ID Baidu AI Map")
    parser.add_argument("--token", default="", help="百度地图 Auth Token")
    parser.add_argument("--region", default="北京市", help="默认区域")
    parser.add_argument("query", nargs="?", help="查询内容")
    args = parser.parse_args()

    config = BaiduMapConfig(auth_token=args.token, default_region=args.region)
    client = BaiduMapClient(config)

    if args.query:
        result = client.assist(args.query, args.region)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"百度地图 AI 技能客户端")
        print(f"  Auth Token: {'已配置' if client.is_available else '未配置（设置 BAIDU_MAP_AUTH_TOKEN）'}")
        print(f"  默认区域: {args.region}")
        print(f"  用法: python -m alpha_id.skills.baidu_ai_map \"找北京咖啡馆\"")


if __name__ == "__main__":
    main()
