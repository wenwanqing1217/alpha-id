"""
出行Agent — 对接百度地图 Agent Plan API

基于 baidu-ai-map skill，使用语义化 API（user_raw_request）
不需要传统 origin/destination 参数，直接传自然语言

核心能力：
  1. 路线规划（Direction）：自然语言描述起点终点，返回路线
  2. 地点搜索（Place）：自然语言描述要找什么
  3. 地理编码（Geocoding）：地址转坐标
  4. 天气查询（Weather）
  5. 生成百度地图 Deep Link（一键跳转手机App）

需要环境变量：
  BAIDU_MAP_AUTH_TOKEN = sk-ap-5h1Eit4VKkhGRV3VmKZb4Z2dmgnex6UrRrFOMFx6HRNSXIbwfahDeq8V7HzVL0cS
"""

import json
import logging
import os
import urllib.parse
import urllib.request
from typing import Optional

logger = logging.getLogger("mindflow.agents.travel")

# ── 配置 ──
API_BASE = "https://api.map.baidu.com/agent_plan/v1"


def _get_token() -> str:
    """获取百度地图 Auth Token"""
    token = os.getenv("BAIDU_MAP_AUTH_TOKEN", "")
    if not token:
        logger.warning("⚠️ BAIDU_MAP_AUTH_TOKEN 未配置")
    return token


def _api_call(endpoint: str, params: dict) -> Optional[dict]:
    """通用 API 调用"""
    token = _get_token()
    if not token:
        return None

    url = f"{API_BASE}/{endpoint}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.error(f"百度地图 API 调用失败 [{endpoint}]: {e}")
        return None


def _call_direction_api(user_raw_request: str, location: str, mode: str = "transit") -> dict:
    """
    调用百度地图 direction API。

    API 实际返回结构:
      {"result": {"answer_type": "...", "navigation_data": {...}}, "resource_key": "..."}

    navigation_data 包含:
      - deeplink_app_url: 百度地图深链（含起终点，可直接用）
      - destination: {lat, lng, name}
      - driving_routes / transit_routes: 路线列表
      - clarify_list: 候选地点（需要澄清时）
    """
    data = _api_call("direction", {
        "user_raw_request": user_raw_request,
        "location": location,
    })

    if not data:
        return {"summary": "API 调用失败", "resource_key": ""}

    # answer_type 在 result 内部！
    result = data.get("result", {})
    answer_type = result.get("answer_type", "")
    nav_data = result.get("navigation_data", {})

    if answer_type == "gptmodel_navigate":
        # 路线规划成功 — API 直接返回 deeplink_app_url！
        deeplink = nav_data.get("deeplink_app_url", "")
        dest_info = nav_data.get("destination", {})
        dest_lat = float(dest_info.get("lat", 0)) if dest_info.get("lat") else 0
        dest_lng = float(dest_info.get("lng", 0)) if dest_info.get("lng") else 0
        dest_name = dest_info.get("name", "")

        # 路线时间/距离
        routes = nav_data.get("driving_routes", nav_data.get("transit_routes", []))
        route = routes[0] if routes else {}
        duration = route.get("duration", 0)
        distance = route.get("distance", 0)

        if duration < 3600:
            time_str = f"{duration // 60}分钟" if duration >= 60 else f"{duration}秒"
        else:
            time_str = f"{duration // 3600}小时{(duration % 3600) // 60}分钟"
        dist_str = f"{distance / 1000:.1f}公里" if distance >= 1000 else f"{distance}米"

        return {
            "answer_type": answer_type,
            "resource_key": data.get("resource_key", ""),
            "summary": f"{time_str} ({dist_str})",
            "duration_text": time_str,
            "distance_text": dist_str,
            "needs_clarification": False,
            # API 生成的深链（含起终点坐标，格式正确）
            "deeplink_app_url": deeplink,
            "dest_lat": dest_lat,
            "dest_lng": dest_lng,
            "dest_name": dest_name,
        }

    elif answer_type in ("gptmodel_poi_clarify", "gptmodel_onway_search_clarify"):
        # 需要澄清 — 从 navigation_data.clarify_list 取候选
        candidates_raw = nav_data.get("clarify_list", [])
        candidates = []
        for item in candidates_raw:
            candidates.append({
                "name": item.get("name", ""),
                "address": item.get("address", ""),
                "lat": item.get("lat", item.get("location", {}).get("lat", 0)),
                "lng": item.get("lng", item.get("location", {}).get("lng", 0)),
                "uid": item.get("uid", ""),
            })

        return {
            "answer_type": answer_type,
            "resource_key": data.get("resource_key", ""),
            "summary": "找到多个地点，请确认",
            "needs_clarification": True,
            "candidates": candidates,
        }

    else:
        # 其他响应类型
        return {
            "answer_type": answer_type,
            "resource_key": data.get("resource_key", ""),
            "summary": f"已查询: {user_raw_request}",
            "needs_clarification": False,
        }


# ════════════════════════════════════════════════════════════════
# 工具函数（注册到 Mindflow）
# ════════════════════════════════════════════════════════════════

def route_plan(params: dict) -> dict:
    """
    语义化路线规划 — 内部使用 _call_direction_api
    参数：
      - destination: 目的地
      - origin: 起点（可选，默认当前位置）
      - mode: 出行方式（driving/transit/walking/riding，可选）
      - raw_text: 原始文本（如果有，直接用作 user_raw_request）
    """
    raw_text = params.get("raw_text") or params.get("params", {}).get("original_text", "")
    destination = params.get("destination") or params.get("params", {}).get("destination", "")
    origin = params.get("origin") or params.get("params", {}).get("origin", "")
    mode = params.get("mode", "transit")

    # 构造自然语言请求
    if raw_text:
        user_request = raw_text
    elif origin and destination:
        user_request = f"从{origin}到{destination}"
    elif destination:
        user_request = f"去{destination}"
    else:
        return {"error": "缺少目的地", "summary": "请告诉我你要去哪里"}

    # 调用 direction API
    location = "39.914590,116.403770"  # 默认北京
    result = _call_direction_api(user_raw_request=user_request, location=location, mode=mode)

    # 补充导航链接（deep + http）和 destination
    nav_links = _build_nav_links(destination or user_request, mode=mode)
    result["deep_link"] = nav_links["deep"]
    result["http_link"] = nav_links["http"]
    result["destination"] = destination or user_request

    return result


def search_place(params: dict) -> dict:
    """
    语义化地点搜索
    参数：
      - query: 搜索内容
      - region: 城市（可选）
    """
    query = params.get("query") or params.get("params", {}).get("query", "")
    region = params.get("region", "")

    if not query:
        return {"error": "缺少搜索内容", "results": []}

    data = _api_call("place", {
        "user_raw_request": query,
        "region": region or "北京市",
        "sort": "relevance",
    })

    if not data:
        return {"query": query, "results": [], "_note": "API 调用失败"}

    results = []
    # API 返回的 POI 列表在 "results" 字段（不是 "pois"）
    for poi in data.get("results", []):
        detail = poi.get("detail_info", {})
        navi = detail.get("navi_location", {})
        results.append({
            "name": poi.get("name") or detail.get("brand") or query,
            "address": poi.get("address", ""),
            "lat": navi.get("lat", 0),
            "lng": navi.get("lng", 0),
            "distance": poi.get("distance", 0),
            "rating": detail.get("overall_rating", ""),
            "label": detail.get("label", ""),
        })

    return {
        "query": query,
        "results": results,
        "count": len(results),
        "resource_key": data.get("resource_key", ""),
        "summary": f"找到 {len(results)} 个结果",
    }


def geocode(params: dict) -> dict:
    """地址转坐标"""
    address = params.get("address") or params.get("params", {}).get("address", "")
    region = params.get("region", "")

    if not address:
        return {"error": "缺少地址"}

    data = _api_call("geocoding", {
        "address": address,
        "region": region or "北京市",
    })

    if not data:
        return {"address": address, "_note": "API 调用失败"}

    return {
        "address": address,
        "lat": data.get("lat", 0),
        "lng": data.get("lng", 0),
        "precise": data.get("precise", 0),
        "confidence": data.get("confidence", 0),
        "level": data.get("level", ""),
    }


def query_weather(params: dict) -> dict:
    """天气查询"""
    location = params.get("location") or params.get("params", {}).get("location", "")
    region = params.get("region") or params.get("params", {}).get("region", "")

    api_params = {}
    if region:
        api_params["region"] = region
    if location:
        api_params["location"] = location

    if not api_params:
        # 默认北京
        api_params["region"] = "北京市"

    data = _api_call("weather", api_params)
    if not data:
        return {"_note": "API 调用失败"}

    return {
        "temperature": data.get("temperature", ""),
        "weather": data.get("weather", ""),
        "humidity": data.get("humidity", ""),
        "wind": data.get("wind", ""),
        "region": data.get("region", ""),
        "summary": f"{data.get('weather', '')} {data.get('temperature', '')}℃",
    }


# ════════════════════════════════════════════════════════════════
# 结果解析
# ════════════════════════════════════════════════════════════════

def _parse_navigate_result(data: dict, user_request: str, destination: str, mode: str = "transit") -> dict:
    """解析路线规划结果"""
    routes = data.get("routes", [])
    if not routes:
        return {"summary": f"已查询: {user_request}", "deep_link": _build_deep_link(destination, mode=mode)}

    route = routes[0]
    duration = route.get("duration", 0)
    distance = route.get("distance", 0)

    # 格式化
    if duration < 3600:
        time_str = f"{duration // 60}分钟"
    else:
        time_str = f"{duration // 3600}小时{(duration % 3600) // 60}分钟"

    dist_str = f"{distance / 1000:.1f}公里" if distance >= 1000 else f"{distance}米"

    # 提取路线描述
    description = ""
    steps = route.get("steps", [])
    if steps:
        descriptions = []
        for s in steps[:5]:  # 最多取5段
            desc = s.get("instruction", s.get("name", ""))
            if desc:
                if isinstance(desc, dict):
                    desc = desc.get("text", "")
                descriptions.append(desc)
        description = " → ".join(descriptions) if descriptions else ""

    return {
        "summary": f"{time_str} ({dist_str})",
        "duration": duration,
        "duration_text": time_str,
        "distance": distance,
        "distance_text": dist_str,
        "description": description,
        "destination": destination or user_request,
        "resource_key": data.get("resource_key", ""),
        "deep_link": _build_deep_link(destination or user_request, mode=mode),
    }


def _parse_clarify_result(data: dict, user_request: str) -> dict:
    """解析POI澄清结果（用户需要选择具体地点）"""
    pois = []
    for poi in data.get("pois", []):
        pois.append({
            "name": poi.get("name", ""),
            "address": poi.get("address", ""),
            "lat": poi.get("lat", 0),
            "lng": poi.get("lng", 0),
        })

    return {
        "summary": f"找到多个地点，请确认: {', '.join(p['name'] for p in pois[:3])}",
        "needs_clarification": True,
        "candidates": pois,
        "raw_text": user_request,
    }


# ════════════════════════════════════════════════════════════════
# Deep Link 生成（百度地图手机App跳转）
# ════════════════════════════════════════════════════════════════

def _build_nav_links(destination: str, origin: str = "", mode: str = "transit") -> dict:
    """
    生成百度地图导航链接（深链 + HTTP 兜底）
    返回: {"deep": "baidumap://...", "http": "https://..."}
    mode: driving | transit | walking | riding
    """
    dest_encoded = urllib.parse.quote(destination)
    origin_encoded = urllib.parse.quote(origin) if origin else ""
    src = "src=com.feishu.mindflow"

    if origin:
        deep = f"baidumap://map/direction?destination={dest_encoded}&origin={origin_encoded}&coord_type=bd09ll&mode={mode}&{src}"
        http = f"https://api.map.baidu.com/direction?destination={dest_encoded}&origin={origin_encoded}&coord_type=bd09ll&mode={mode}&output=html&{src}"
    else:
        deep = f"baidumap://map/direction?destination={dest_encoded}&coord_type=bd09ll&mode={mode}&{src}"
        http = f"https://api.map.baidu.com/direction?destination={dest_encoded}&coord_type=bd09ll&mode={mode}&output=html&{src}"

    return {"deep": deep, "http": http}


# ════════════════════════════════════════════════════════════════
# 注册到 Mindflow
# ════════════════════════════════════════════════════════════════

def register_tools(engine):
    """将出行Agent的所有工具注册到 Mindflow 引擎"""
    engine.register_tool("baidu_map", route_plan)
    engine.register_tool("route_plan", route_plan)
    engine.register_tool("place_search", search_place)
    engine.register_tool("geocoding", geocode)
    engine.register_tool("weather_api", query_weather)
    logger.info("  🗺️  出行Agent已注册 (baidu-ai-map skill)")
    return engine
