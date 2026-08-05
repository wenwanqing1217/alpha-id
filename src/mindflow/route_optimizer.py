"""
MindFlow 多目的地智能路线规划

给定多个目的地，自动：
  1. 地理编码（地址 → 坐标）
  2. 计算最优访问顺序（最近邻 + 时间窗口约束）
  3. 生成百度地图多点导航链接（支持 Deep Link 跳 App）

输入：
  places = ["家", "公司", "医院", "餐厅"]
  start = "家"  （可选，默认第一个）

输出：
  {
    "ordered_places": [...],
    "total_distance": 12.3,
    "total_duration": 45,
    "nav_link": "baidumap://map/direction?...",
    "web_link": "https://api.map.baidu.com/direction?...",
    "segments": [...]
  }
"""

import ipaddress
import json
import logging
import socket
import urllib.parse
import urllib.request
from typing import Dict, List, Optional

from core.settings import settings

logger = logging.getLogger("mindflow.route_optimizer")

API_BASE = "https://api.map.baidu.com/agent_plan/v1"
GEOCODING_URL = "https://api.map.baidu.com/geocoding/v3/"

# 允许的外部 API 域名白名单（防止 SSRF）
ALLOWED_HOSTS = {"api.map.baidu.com"}


def _validate_url_no_ssrf(url: str) -> None:
    """验证 URL 不指向内网地址，防止 SSRF 攻击。"""
    parsed = urllib.parse.urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        raise ValueError(f"URL 缺少主机名: {url}")

    # 白名单检查
    if hostname not in ALLOWED_HOSTS:
        logger.warning("URL 主机名不在白名单中: %s", hostname)

    # 禁止内网 IP
    try:
        addr = ipaddress.ip_address(hostname)
        if addr.is_private or addr.is_loopback or addr.is_link_local:
            raise ValueError(f"URL 指向内网地址，已阻止: {hostname}")
    except ValueError as e:
        if "内网地址" in str(e):
            raise

    # DNS 解析后再次检查
    try:
        for info in socket.getaddrinfo(hostname, parsed.port or 443):
            ip = info[4][0]
            addr = ipaddress.ip_address(ip)
            if addr.is_private or addr.is_loopback or addr.is_link_local:
                raise ValueError(f"URL 解析到内网地址，已阻止: {hostname} → {ip}")
    except socket.gaierror:
        raise ValueError(f"无法解析主机名: {hostname}")


def _get_token() -> str:
    return settings.baidu_map_auth_token


def geocode_address(address: str, city: str = "北京市") -> Optional[Dict]:
    """地址转坐标"""
    token = _get_token()
    if not token:
        return None

    params = {
        "address": address,
        "city": city,
        "output": "json",
        "ak": token,
    }
    url = f"{GEOCODING_URL}?{urllib.parse.urlencode(params)}"
    # SSRF 防护：验证目标 URL
    try:
        _validate_url_no_ssrf(url)
    except ValueError as e:
        logger.warning(f"地理编码 URL 安全验证失败: {e}")
        return None
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("status") == 0:
            result = data.get("result", {})
            location = result.get("location", {})
            return {
                "address": address,
                "lat": location.get("lat", 0),
                "lng": location.get("lng", 0),
                "confidence": result.get("confidence", 0),
            }
    except Exception as e:
        logger.warning(f"地理编码失败 [{address}]: {e}")
    return None


def batch_geocode(places: List[str], city: str = "北京市") -> Dict[str, Optional[Dict]]:
    """批量地理编码"""
    results = {}
    for place in places:
        results[place] = geocode_address(place, city)
    return results


def optimize_route_order(
    places: List[str],
    coordinates: Dict[str, Optional[Dict]],
    start_place: Optional[str] = None,
    time_windows: Optional[Dict[str, str]] = None,
) -> List[str]:
    """
    计算最优访问顺序

    策略：
      1. 有时间窗口约束的按时间排序
      2. 剩余地点用最近邻算法
      3. 起点如果指定则固定第一个
    """
    if not places:
        return []

    # 分离有时间和无时间约束的地点
    timed = []
    untimed = []
    for p in places:
        if time_windows and p in time_windows:
            timed.append((p, time_windows[p]))
        else:
            untimed.append(p)

    # 有时间约束的按时间排序
    timed.sort(key=lambda x: x[1])
    timed_places = [p for p, _ in timed]

    # 确定起点
    if start_place and start_place in untimed:
        untimed.remove(start_place)
        ordered = [start_place]
    elif start_place and start_place in timed_places:
        timed_places.remove(start_place)
        ordered = [start_place]
    else:
        ordered = [timed_places.pop(0)] if timed_places else [untimed.pop(0)]

    # 对剩余地点用最近邻
    remaining = timed_places + untimed
    while remaining:
        current = ordered[-1]
        current_coord = coordinates.get(current, {})
        cur_lat = current_coord.get("lat", 0) if current_coord else 0
        cur_lng = current_coord.get("lng", 0) if current_coord else 0

        if cur_lat == 0 and cur_lng == 0:
            # 没有坐标信息，直接追加
            ordered.append(remaining.pop(0))
            continue

        # 找最近的下一个点
        nearest_idx = 0
        nearest_dist = float("inf")
        for i, place in enumerate(remaining):
            coord = coordinates.get(place, {})
            lat = coord.get("lat", 0) if coord else 0
            lng = coord.get("lng", 0) if coord else 0
            if lat == 0 and lng == 0:
                continue
            # 简化的欧氏距离（小范围可用）
            dist = ((lat - cur_lat) ** 2 + (lng - cur_lng) ** 2) ** 0.5
            if dist < nearest_dist:
                nearest_dist = dist
                nearest_idx = i

        ordered.append(remaining.pop(nearest_idx))

    return ordered


def build_multi_stop_navigation(
    ordered_places: List[str],
    mode: str = "driving",
) -> Dict:
    """
    生成百度地图多点导航链接

    支持：
      - Deep Link（baidumap:// 协议，手机直接跳 App）
      - Web Link（浏览器打开）
    """
    if len(ordered_places) < 2:
        return {
            "error": "至少需要2个地点",
            "nav_link": "",
            "web_link": "",
        }

    origin = ordered_places[0]
    destination = ordered_places[-1]
    waypoints = ordered_places[1:-1] if len(ordered_places) > 2 else []

    # URL 编码
    origin_enc = urllib.parse.quote(origin)
    dest_enc = urllib.parse.quote(destination)
    waypoints_enc = urllib.parse.quote("|".join(waypoints)) if waypoints else ""

    # Deep Link（手机 App）
    deep_link = f"baidumap://map/direction?origin={origin_enc}&destination={dest_enc}&mode={mode}"
    if waypoints_enc:
        deep_link += f"&waypoints={waypoints_enc}"

    # Web Link（浏览器）
    web_link = f"https://api.map.baidu.com/direction?origin={origin_enc}&destination={dest_enc}&mode={mode}&output=html"
    if waypoints_enc:
        web_link += f"&waypoints={waypoints_enc}"

    return {
        "origin": origin,
        "destination": destination,
        "waypoints": waypoints,
        "deep_link": deep_link,
        "web_link": web_link,
        "mode": mode,
    }


def plan_multi_stop_route(
    places: List[str],
    start_place: Optional[str] = None,
    time_windows: Optional[Dict[str, str]] = None,
    city: str = "北京市",
    mode: str = "driving",
) -> Dict:
    """
    完整的多目的地路线规划流程

    参数：
      places: 目的地列表，如 ["家", "公司", "医院"]
      start_place: 起点（可选）
      time_windows: 时间约束，如 {"医院": "14:00"}
      city: 城市
      mode: 出行方式 driving/walking/transit

    返回完整规划结果
    """
    if not places:
        return {"error": "目的地列表为空", "ordered_places": []}

    # 去重
    unique_places = list(dict.fromkeys(places))

    if len(unique_places) == 1:
        return {
            "ordered_places": unique_places,
            "total_distance": 0,
            "total_duration": 0,
            "nav_link": f"baidumap://map/marker?location={urllib.parse.quote(unique_places[0])}",
            "web_link": f"https://api.map.baidu.com/marker?location={urllib.parse.quote(unique_places[0])}&output=html",
            "segments": [],
        }

    # 1. 批量地理编码
    coordinates = batch_geocode(unique_places, city)
    geocoded_count = sum(1 for v in coordinates.values() if v is not None)
    logger.info(f"地理编码完成: {geocoded_count}/{len(unique_places)} 成功")

    # 2. 优化顺序
    ordered = optimize_route_order(unique_places, coordinates, start_place, time_windows)

    # 3. 生成导航链接
    nav = build_multi_stop_navigation(ordered, mode)

    # 4. 构建结果
    segments = []
    for i in range(len(ordered) - 1):
        segments.append({
            "from": ordered[i],
            "to": ordered[i + 1],
            "index": i + 1,
        })

    result = {
        "ordered_places": ordered,
        "coordinates": {k: v for k, v in coordinates.items() if v},
        "total_distance": 0,  # TODO: 调用距离矩阵 API
        "total_duration": 0,
        "nav_link": nav.get("deep_link", ""),
        "web_link": nav.get("web_link", ""),
        "segments": segments,
        "mode": mode,
        "summary": f"最优路线: {' → '.join(ordered)}",
    }

    logger.info(f"路线规划完成: {result['summary']}")
    return result


def format_route_reply(route_result: Dict) -> str:
    """格式化路线规划结果为飞书回复文本"""
    ordered = route_result.get("ordered_places", [])
    segments = route_result.get("segments", [])
    web_link = route_result.get("web_link", "")
    deep_link = route_result.get("nav_link", "")

    lines = ["🗺️ 最优路线规划：\n"]

    # 路线概览
    route_str = " → ".join(ordered)
    lines.append(f"📍 {route_str}\n")

    # 每段详情
    if segments:
        lines.append("行程分段：")
        for seg in segments:
            lines.append(f"  {seg['index']}. {seg['from']} → {seg['to']}")

    # 导航链接
    lines.append(f"\n📱 手机点击导航：{deep_link}")
    lines.append(f"🌐 浏览器查看：{web_link}")

    return "\n".join(lines)
