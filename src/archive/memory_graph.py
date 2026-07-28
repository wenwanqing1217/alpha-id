"""
AID Memory Graph — 记忆关联网络可视化

从 MemoryStore 中读取所有记忆，基于共享标签 + 语义相似度
构建关联图，输出为交互式 D3.js HTML。
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.settings import settings

try:
    from core.memory_store import MemoryStore
    from core.storage_sqlite import SqliteStorage

    HAS_STORE = True
except ImportError:
    MemoryStore = None
    SqliteStorage = None
    HAS_STORE = False


def _cosine_sim(
    tags_a: List[str],
    tags_b: List[str],
    content_a: str = "",
    content_b: str = "",
) -> float:
    """计算两条记忆之间的相似度（0-1），基于共享标签 + 内容 n-gram 重叠。"""
    score = 0.0
    # 1. 标签重叠
    set_a = set(t.strip().lower() for t in tags_a)
    set_b = set(t.strip().lower() for t in tags_b)
    union = set_a | set_b
    if union:
        score += len(set_a & set_b) / len(union) * 0.6  # 标签占 60%

    # 2. 内容中文字符级 bigram 重叠（轻量语义）
    def bigrams(text: str) -> set:
        clean = text.lower().strip()
        return {clean[i : i + 2] for i in range(len(clean) - 1)}

    grams_a = bigrams(content_a)
    grams_b = bigrams(content_b)
    gram_union = grams_a | grams_b
    if gram_union:
        score += len(grams_a & grams_b) / len(gram_union) * 0.4  # 内容占 40%

    return min(1.0, score)


def build_graph(
    store: Any,
    min_similarity: float = 0.05,
    max_nodes: int = 80,
    include_categories: Optional[List[str]] = None,
    max_sensitivity: int = 100,
) -> Dict:
    """
    从 MemoryStore 读取记忆，构建图数据。

    返回: {"nodes": [...], "edges": [...], "stats": {...}}
    每个 node: {"id": str, "label": str(截取), "category": str, "sensitivity": int,
                 "tags": list, "group": str, "content_preview": str, "size": int}
    每个 edge: {"source": str, "target": str, "weight": float, "label": str}
    """
    memories = store.query(limit=9999)  # 取出所有
    if not memories:
        return {"nodes": [], "edges": [], "stats": {"total": 0}}

    # 过滤
    if include_categories:
        memories = [m for m in memories if m.get("category", "") in include_categories]
    memories = [
        m for m in memories if isinstance(m.get("sensitivity", 0), (int, float)) and m["sensitivity"] <= max_sensitivity
    ]

    # 截取到 max_nodes
    memories = memories[:max_nodes]

    # 颜色映射
    category_colors = {
        "general": "#6b7280",
        "knowledge": "#3b82f6",
        "preference": "#8b5cf6",
        "social": "#ec4899",
        "action": "#f59e0b",
        "daily": "#10b981",
        "error": "#ef4444",
    }

    nodes = []
    for m in memories:
        mid = m.get("memory_id", "")
        content = m.get("content", "")
        label = content[:32] + ("…" if len(content) > 32 else "")
        cat = m.get("category", "general")
        nodes.append(
            {
                "id": mid,
                "label": label,
                "category": cat,
                "sensitivity": m.get("sensitivity", 0),
                "tags": m.get("tags", []),
                "group": cat,
                "color": category_colors.get(cat, "#9ca3af"),
                "content_preview": content[:120] + ("…" if len(content) > 120 else ""),
                "size": 5,
            }
        )

    # 计算边：共享标签 + 内容相似度
    edges = []
    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            ni = nodes[i]
            nj = nodes[j]
            sim = _cosine_sim(
                ni["tags"],
                nj["tags"],
                memories[i].get("content", ""),
                memories[j].get("content", ""),
            )
            if sim >= min_similarity:
                shared = set(ni["tags"]) & set(nj["tags"])
                label = f"{sim:.2f}"
                if shared:
                    label += f" [{','.join(list(shared)[:3])}]"
                edges.append(
                    {
                        "source": ni["id"],
                        "target": nj["id"],
                        "weight": round(sim, 3),
                        "label": label,
                    }
                )

    # 统计
    stats = {
        "total": len(memories),
        "edges": len(edges),
        "categories": {},
    }
    for n in nodes:
        stats["categories"][n["category"]] = stats["categories"].get(n["category"], 0) + 1

    return {"nodes": nodes, "edges": edges, "stats": stats}


def render_html(graph_data: Dict, title: str = "AID 记忆网络") -> str:
    """将图数据渲染为自包含的 D3.js HTML。"""
    nodes_json = json.dumps(graph_data.get("nodes", []), ensure_ascii=False)
    edges_json = json.dumps(graph_data.get("edges", []), ensure_ascii=False)
    stats = graph_data.get("stats", {})

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f172a; color: #e2e8f0; overflow: hidden; }}
#header {{ position: fixed; top: 0; left: 0; right: 0; z-index: 10; padding: 12px 24px; background: rgba(15,23,42,0.9); backdrop-filter: blur(8px); border-bottom: 1px solid #1e293b; display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }}
#header h1 {{ font-size: 18px; font-weight: 600; white-space: nowrap; }}
#header .stats {{ font-size: 13px; color: #94a3b8; white-space: nowrap; }}
#header .spacer {{ flex: 1; min-width: 8px; }}
#search {{ background: #1e293b; border: 1px solid #334155; border-radius: 6px; padding: 6px 12px; color: #e2e8f0; font-size: 13px; width: 200px; outline: none; transition: border-color 0.2s; }}
#search:focus {{ border-color: #3b82f6; }}
#search::placeholder {{ color: #64748b; }}
.filter-group {{ display: flex; align-items: center; gap: 6px; font-size: 13px; flex-wrap: wrap; }}
.filter-group label {{ color: #94a3b8; cursor: pointer; display: flex; align-items: center; gap: 4px; }}
.filter-group input[type="checkbox"] {{ accent-color: #3b82f6; }}
#result-count {{ font-size: 12px; color: #64748b; margin-left: 4px; }}
#legend {{ position: fixed; bottom: 24px; left: 24px; z-index: 10; background: rgba(15,23,42,0.85); backdrop-filter: blur(6px); border: 1px solid #1e293b; border-radius: 8px; padding: 12px 16px; font-size: 12px; }}
#legend .dot {{ display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 6px; }}
.legend-row {{ display: flex; align-items: center; gap: 8px; margin: 2px 0; cursor: pointer; opacity: 0.6; transition: opacity 0.2s; }}
.legend-row.active {{ opacity: 1; }}
.legend-row:hover {{ opacity: 1; }}
#tooltip {{ position: fixed; z-index: 20; background: rgba(15,23,42,0.95); border: 1px solid #334155; border-radius: 8px; padding: 10px 14px; font-size: 13px; max-width: 360px; pointer-events: none; display: none; box-shadow: 0 4px 20px rgba(0,0,0,0.5); }}
#tooltip .tt-title {{ font-weight: 600; margin-bottom: 4px; }}
#tooltip .tt-meta {{ color: #94a3b8; font-size: 11px; }}
#tooltip .tt-content {{ margin-top: 6px; color: #cbd5e1; }}
svg {{ width: 100vw; height: 100vh; }}
.link {{ stroke-opacity: 0.4; transition: stroke-opacity 0.2s; }}
.link.faded {{ stroke-opacity: 0.05 !important; }}
.link.highlighted {{ stroke-opacity: 0.7 !important; }}
.node-label {{ font-size: 11px; fill: #94a3b8; pointer-events: none; text-shadow: 0 1px 3px rgba(0,0,0,0.8); }}
.node-circle {{ transition: opacity 0.2s; }}
.node-circle.faded {{ opacity: 0.1 !important; }}
</style>
</head>
<body>
<div id="header">
  <h1>🧠 {title}</h1>
  <span class="stats"><span id="shown-count">{stats.get("total", 0)}</span> / {stats.get("total", 0)} 条 · 关联 {stats.get("edges", 0)} 条</span>
  <span class="spacer"></span>
  <input id="search" type="text" placeholder="🔍 搜索记忆内容…" oninput="applyFilters()">
  <div class="filter-group" id="category-filters"></div>
  <span id="result-count"></span>
</div>
<div id="tooltip"></div>
<div id="legend"></div>
<svg id="graph"></svg>

<script src="https://d3js.org/d3.v7.min.js"></script>
<script>
const nodes = {nodes_json};
const edges = {edges_json};

const width = window.innerWidth, height = window.innerHeight;
const svg = d3.select("#graph").attr("width", width).attr("height", height);

// 深色主题背景渐变
svg.append("defs").append("radialGradient").attr("id","bg").attr("cx","50%").attr("cy","50%").attr("r","50%")
  .append("stop").attr("offset","0%").attr("stop-color","#1e293b")
svg.select("#bg").append("stop").attr("offset","100%").attr("stop-color","#0f172a");
svg.append("rect").attr("width",width).attr("height",height).attr("fill","url(#bg)");

// 箭头标记
svg.append("defs").selectAll("marker").data(["arrow"]).join("marker")
  .attr("id", d => d).attr("viewBox","0 -5 10 10").attr("refX",18).attr("refY",0)
  .attr("markerWidth",6).attr("markerHeight",6).attr("orient","auto")
  .append("path").attr("d","M0,-5 L10,0 L0,5").attr("fill","#475569");

const CATEGORY_COLORS = {{"general":"#6b7280","knowledge":"#3b82f6","preference":"#8b5cf6","social":"#ec4899","action":"#f59e0b","daily":"#10b981","error":"#ef4444"}};

const nodeMap = new Map(nodes.map(n => [n.id, n]));

// 构建类别过滤器
const cats = [...new Set(nodes.map(n => n.category))].filter(Boolean);
const activeCats = new Set(cats);
const catFiltersEl = document.getElementById("category-filters");
catFiltersEl.innerHTML = cats.map(c => `<label><input type="checkbox" checked onchange="toggleCategory('${{c}}',this.checked)"><span class="dot" style="background:${{CATEGORY_COLORS[c]||'#6b7280'}};display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:2px;"></span>${{c}}</label>`).join("");

// 图例
const legendEl = document.getElementById("legend");
legendEl.innerHTML = cats.map(c => `<div class="legend-row active" data-cat="${{c}}" onclick="toggleCategory('${{c}}', false)"><span class="dot" style="background:${{CATEGORY_COLORS[c]||'#6b7280'}}"></span>${{c}}</div>`).join("") +
  `<div style="margin-top:6px;font-size:11px;color:#64748b;">💡 拖拽·悬停查看</div>`;

function toggleCategory(cat, show) {{
  if (show === undefined) show = !activeCats.has(cat);
  if (show) {{ activeCats.add(cat); }} else {{ activeCats.delete(cat); }}
  const checkboxes = catFiltersEl.querySelectorAll(`input[value="${{cat}}"]`);
  const legendRows = legendEl.querySelectorAll(`[data-cat="${{cat}}"]`);
  checkboxes.forEach(cb => {{ cb.checked = show; }});
  legendRows.forEach(r => r.classList.toggle("active", show));
  applyFilters();
}}

function applyFilters() {{
  const query = document.getElementById("search").value.trim().toLowerCase();
  const visible = new Set();

  // 筛选匹配搜索+类别的节点
  nodes.forEach(n => {{
    const catOk = activeCats.has(n.category);
    const searchOk = !query || (n.content_preview||"").toLowerCase().includes(query)
      || (n.label||"").toLowerCase().includes(query)
      || (n.tags||[]).some(t => t.toLowerCase().includes(query));
    if (catOk && searchOk) visible.add(n.id);
  }});

  // 搜索时显示一跳关联
  if (query) {{
    const extra = new Set(visible);
    edges.forEach(e => {{
      const sid = e.source.id || e.source;
      const tid = e.target.id || e.target;
      if (query.length > 1) {{
        if (visible.has(sid)) extra.add(tid);
        if (visible.has(tid)) extra.add(sid);
      }}
    }});
    extra.forEach(id => visible.add(id));
  }}

  // 更新节点可见性
  nodeG.selectAll("circle.node-circle")
    .attr("class", d => visible.has(d.id) ? "node-circle" : "node-circle faded");

  nodeG.selectAll("text.node-label")
    .attr("opacity", d => visible.has(d.id) ? 1 : 0.05);

  // 更新边
  linkG.attr("class", d => {{
    const sid = d.source.id || d.source;
    const tid = d.target.id || d.target;
    if (visible.has(sid) && visible.has(tid)) return "link highlighted";
    if (query && (visible.has(sid) || visible.has(tid))) return "link";
    return "link faded";
  }});

  document.getElementById("shown-count").textContent = visible.size;
}}

const linkG = svg.append("g").selectAll("line").data(edges).join("line")
  .attr("class", "link").attr("stroke","#475569").attr("stroke-width", d => Math.max(0.5, d.weight * 4));

const nodeG = svg.append("g").selectAll("g").data(nodes).join("g").call(d3.drag()
  .on("start", (ev, d) => {{ if(!ev.active) sim.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; }})
  .on("drag", (ev, d) => {{ d.fx = ev.x; d.fy = ev.y; }})
  .on("end", (ev, d) => {{ if(!ev.active) sim.alphaTarget(0); d.fx = null; d.fy = null; }}));

nodeG.append("circle").attr("class","node-circle").attr("r", d => d.size + 2).attr("fill", d => d.color)
  .attr("stroke","#1e293b").attr("stroke-width",1.5)
  .on("mouseover", (ev, d) => {{
    const tt = d3.select("#tooltip");
    tt.style("display","block")
      .html(`<div class="tt-title">${{d.label}}</div><div class="tt-meta">${{d.category}} · tags [${{(d.tags||[]).join(", ")}}]</div><div class="tt-content">${{d.content_preview}}</div>`);
    const rect = svg.node().getBoundingClientRect();
    tt.style("left", (ev.clientX + 14) + "px").style("top", (ev.clientY - 10) + "px");
    d3.select(this).attr("stroke","#e2e8f0").attr("stroke-width",2.5);
  }})
  .on("mousemove", (ev) => {{
    d3.select("#tooltip").style("left", (ev.clientX + 14) + "px").style("top", (ev.clientY - 10) + "px");
  }})
  .on("mouseout", function() {{
    d3.select("#tooltip").style("display","none");
    d3.select(this).attr("stroke","#1e293b").attr("stroke-width",1.5);
  }});

nodeG.append("text").attr("class","node-label").attr("dx",16).attr("dy",4)
  .text(d => d.label);

const sim = d3.forceSimulation(nodes)
  .force("link", d3.forceLink(edges).id(d => d.id).distance(100).strength(d => d.weight * 0.5))
  .force("charge", d3.forceManyBody().strength(-200))
  .force("center", d3.forceCenter(width/2, height/2))
  .force("collision", d3.forceCollide(30))
  .on("tick", () => {{
    linkG.attr("x1", d => d.source.x).attr("y1", d => d.source.y)
         .attr("x2", d => d.target.x).attr("y2", d => d.target.y);
    nodeG.attr("transform", d => `translate(${{d.x}},${{d.y}})`);
  }});
</script>
</body>
</html>"""


def generate_graph_html(
    store: Any,
    output_path: Optional[str] = None,
    min_similarity: float = 0.05,
    max_nodes: int = 80,
    title: str = "AID 记忆网络",
    auto_open: bool = False,
) -> str:
    """
    生成记忆网络 HTML 文件。

    参数:
        store: MemoryStore 实例
        output_path: 输出路径，None 则生成到临时文件
        min_similarity: 最小相似度阈值 (0-1)
        max_nodes: 最大节点数
        title: 页面标题
        auto_open: 是否自动打开浏览器

    返回:
        HTML 文件路径
    """
    graph = build_graph(store, min_similarity=min_similarity, max_nodes=max_nodes)
    html = render_html(graph, title=title)

    if output_path:
        path = Path(output_path)
    else:
        path = Path(tempfile.gettempdir()) / f"aid_memory_graph_{hash(title) & 0xFFFFFFFF:08x}.html"

    path.write_text(html, encoding="utf-8")

    if auto_open:
        import webbrowser

        webbrowser.open(str(path.resolve()))

    return str(path.resolve())


def graph_stats_text(store: Any) -> str:
    """生成文本格式的记忆网络统计报告。"""
    graph = build_graph(store)
    stats = graph.get("stats", {})
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    if not nodes:
        return "🧠 记忆网络为空，还没有任何记忆。"

    lines = [
        "🧠 记忆网络统计",
        f"{'─' * 40}",
        f"记忆总数:  {stats.get('total', 0)} 条",
        f"关联总数:  {stats.get('edges', 0)} 条",
        "",
        "分类分布:",
    ]
    for cat, count in sorted(stats.get("categories", {}).items(), key=lambda x: -x[1]):
        lines.append(f"  · {cat}: {count} 条")

    # 找连接最多的记忆（枢纽节点）
    if edges and nodes:
        conn_count: Dict[str, int] = {}
        for e in edges:
            src = e["source"]
            tgt = e["target"]
            conn_count[src] = conn_count.get(src, 0) + 1
            conn_count[tgt] = conn_count.get(tgt, 0) + 1

        top = sorted(conn_count.items(), key=lambda x: -x[1])[:5]
        node_map = {n["id"]: n for n in nodes}
        lines.append("\n枢纽节点 (关联最多的记忆):")
        for nid, cnt in top:
            n = node_map.get(nid, {})
            label = n.get("label", nid[:16])
            lines.append(f"  · {label} — {cnt} 条关联")

    lines.append("\n💡 提示: 调用 memory_graph_html 生成可视化 HTML")

    return "\n".join(lines)


# ── MCP 工具包装 ──


def memory_graph_html(
    alpha_id: str = "Alpha-001",
    output_path: str = "",
    min_similarity: float = 0.05,
    max_nodes: int = 80,
) -> str:
    """
    生成记忆网络 HTML 交互式可视化文件。
    返回文件路径，可在浏览器中打开。
    """
    if not HAS_STORE:
        return "[Error] 无法加载 MemoryStore / SqliteStorage"

    db_path = os.path.join(
        str(settings.coze_workspace),
        "assets",
        "alpha_id.db",
    )
    storage = SqliteStorage(db_path)
    store = MemoryStore(alpha_id=alpha_id, storage=storage)

    path = generate_graph_html(
        store,
        output_path=output_path or None,
        min_similarity=min_similarity,
        max_nodes=max_nodes,
        title=f"AID 记忆网络 - {alpha_id}",
    )
    return f"[OK] 记忆网络已生成: {path}"


def memory_graph_stats(alpha_id: str = "Alpha-001") -> str:
    """查看当前记忆网络的统计摘要。"""
    if not HAS_STORE:
        return "[Error] 无法加载 MemoryStore / SqliteStorage"

    db_path = os.path.join(
        str(settings.coze_workspace),
        "assets",
        "alpha_id.db",
    )
    storage = SqliteStorage(db_path)
    store = MemoryStore(alpha_id=alpha_id, storage=storage)

    return graph_stats_text(store)


def memory_graph_search(
    alpha_id: str = "Alpha-001",
    query: str = "",
    limit: int = 20,
) -> str:
    """搜索记忆网络，返回匹配的记忆列表（文本格式）。"""
    if not query:
        return "[Error] 请提供搜索关键词 query"

    if not HAS_STORE:
        return "[Error] 无法加载 MemoryStore / SqliteStorage"

    db_path = os.path.join(
        str(settings.coze_workspace),
        "assets",
        "alpha_id.db",
    )
    storage = SqliteStorage(db_path)
    store = MemoryStore(alpha_id=alpha_id, storage=storage)
    memories = store.query(limit=9999)

    if not memories:
        return "🧠 记忆网络为空。"

    q = query.lower().strip()
    results = []
    for m in memories:
        content = (m.get("content") or "").lower()
        label = (m.get("label") or "").lower()
        tags = [t.lower() for t in (m.get("tags") or [])]

        # 多字段匹配
        score = 0
        if q in content:
            score += 10
            # 精确匹配加权
            if content.strip() == q:
                score += 5
        if q in label:
            score += 10
        if any(q in t for t in tags):
            score += 8

        # 词组匹配：关键词分散命中
        if score == 0 and len(q) > 2:
            q_words = set(q.split())
            content_words = set(content.split())
            match_count = len(q_words & content_words)
            if match_count > 0:
                score = match_count * 3
                tag_matches = sum(1 for t in tags for w in q_words if w in t)
                score += tag_matches * 2

        if score > 0:
            results.append((score, m))

    if not results:
        return f"🔍 未找到与「{query}」相关的记忆。"

    # 按分数排序
    results.sort(key=lambda x: -x[0])
    results = results[:limit]

    lines = [
        f"🔍 搜索「{query}」共 {len(results)} 条结果：",
        "─" * 50,
    ]
    for i, (score, m) in enumerate(results, 1):
        content = m.get("content", "")[:200]
        cat = m.get("category", "general")
        tags = ", ".join(m.get("tags", []) or [])
        mid = m.get("memory_id", "")[:12]

        lines.append(
            f"\n{i}. [{score:.0f}分] {content}"
            f"\n   类别: {cat}  | 标签: {tags or '(无)'}"
            f"\n   ID: {mid}  |  敏感度: {m.get('sensitivity', '?')}"
        )

    return "\n".join(lines)


def memory_graph_save(
    alpha_id: str = "Alpha-001",
    content: str = "",
    category: str = "general",
    tags: Optional[List[str]] = None,
    sensitivity: int = 0,
    source: str = "self",
) -> str:
    """保存一条记忆到记忆网络。"""
    if not content:
        return "[Error] 请提供记忆内容 content"

    if not HAS_STORE:
        return "[Error] 无法加载 MemoryStore / SqliteStorage"

    db_path = os.path.join(
        str(settings.coze_workspace),
        "assets",
        "alpha_id.db",
    )
    storage = SqliteStorage(db_path)
    store = MemoryStore(alpha_id=alpha_id, storage=storage)

    try:
        result = store.save(
            content=content,
            category=category,
            tags=tags or [],
            sensitivity=sensitivity,
            source=source,
        )
        mid = result.get("memory_id", "?")[:12]
        return f"[OK] 记忆已保存 (ID: {mid}, 类别: {category})"
    except Exception as e:
        return f"[Error] 保存失败: {e}"


def memory_graph_delete(alpha_id: str = "Alpha-001", memory_id: str = "") -> str:
    """从记忆网络中删除一条记忆。"""
    if not memory_id:
        return "[Error] 请提供 memory_id"

    if not HAS_STORE:
        return "[Error] 无法加载 MemoryStore / SqliteStorage"

    db_path = os.path.join(
        str(settings.coze_workspace),
        "assets",
        "alpha_id.db",
    )
    storage = SqliteStorage(db_path)
    store = MemoryStore(alpha_id=alpha_id, storage=storage)

    try:
        result = store.delete(memory_id)
        if result:
            return f"[OK] 记忆已删除 (ID: {memory_id[:12]})"
        else:
            return f"[Warn] 未找到 ID 为 {memory_id[:12]} 的记忆"
    except Exception as e:
        return f"[Error] 删除失败: {e}"


def memory_graph_update(
    alpha_id: str = "Alpha-001",
    memory_id: str = "",
    content: Optional[str] = None,
    category: Optional[str] = None,
    tags: Optional[List[str]] = None,
    sensitivity: Optional[int] = None,
    source: Optional[str] = None,
) -> str:
    """更新一条已有记忆。只更新提供的字段，其余保持不变。"""
    if not memory_id:
        return "[Error] 请提供 memory_id"

    if not HAS_STORE:
        return "[Error] 无法加载 MemoryStore / SqliteStorage"

    db_path = os.path.join(
        str(settings.coze_workspace),
        "assets",
        "alpha_id.db",
    )
    storage = SqliteStorage(db_path)
    store = MemoryStore(alpha_id=alpha_id, storage=storage)

    try:
        result = store.update(
            memory_id=memory_id,
            content=content,
            category=category,
            tags=tags,
            sensitivity=sensitivity,
            source=source,
        )
        if result.get("success"):
            return f"[OK] 记忆已更新 (ID: {memory_id[:12]})"
        else:
            return f"[Warn] {result.get('message', '更新失败')}"
    except Exception as e:
        return f"[Error] 更新失败: {e}"


# ── CLI 入口（供命令行直接使用） ──


def cli():
    """命令行工具：从任意 MemoryStore 生成记忆网络可视化"""
    import argparse

    parser = argparse.ArgumentParser(
        description="🧠 AID 记忆网络可视化工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  # 查看统计\n"
            "  python memory_graph.py stats\n"
            "  python memory_graph.py stats --alpha-id Beta\n"
            "\n"
            "  # 生成 HTML 可视化\n"
            "  python memory_graph.py html -o my_memory_graph.html\n"
            "  python memory_graph.py html --min-sim 0.1 --max-nodes 50\n"
            "\n"
            "  # 直接从 JSON 文件生成（不依赖 MemoryStore）\n"
            "  python memory_graph.py json memories.json -o graph.html\n"
        ),
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # stats 子命令
    p_stats = sub.add_parser("stats", help="查看记忆网络统计摘要")
    p_stats.add_argument("--alpha-id", default="Alpha-001", help="Alpha ID (默认: Alpha-001)")
    p_stats.add_argument("--db", default="", help="SQLite 数据库路径（留空则使用默认路径）")

    # html 子命令
    p_html = sub.add_parser("html", help="生成交互式 HTML 可视化")
    p_html.add_argument("--alpha-id", default="Alpha-001", help="Alpha ID (默认: Alpha-001)")
    p_html.add_argument("--db", default="", help="SQLite 数据库路径（留空则使用默认路径）")
    p_html.add_argument("-o", "--output", default="", help="输出 HTML 文件路径（留空则生成到临时文件）")
    p_html.add_argument("--min-sim", type=float, default=0.05, help="最小相似度阈值 (默认: 0.05)")
    p_html.add_argument("--max-nodes", type=int, default=80, help="最大节点数 (默认: 80)")
    p_html.add_argument("--title", default="", help="页面标题（留空则自动生成）")
    p_html.add_argument("--open", action="store_true", dest="auto_open", help="生成后自动在浏览器中打开")

    # json 子命令：直接从 JSON 文件生成（不依赖 MemoryStore，便携）
    p_json = sub.add_parser("json", help="从 JSON 数据文件直接生成可视化（不依赖 MemoryStore）")
    p_json.add_argument("input", help="输入 JSON 文件路径（格式见说明）")
    p_json.add_argument("-o", "--output", default="", help="输出 HTML 文件路径")
    p_json.add_argument("--min-sim", type=float, default=0.05, help="最小相似度阈值 (默认: 0.05)")
    p_json.add_argument("--max-nodes", type=int, default=80, help="最大节点数 (默认: 80)")
    p_json.add_argument("--title", default="记忆网络", help="页面标题 (默认: 记忆网络)")
    p_json.add_argument("--open", action="store_true", dest="auto_open", help="生成后自动在浏览器中打开")

    args = parser.parse_args()

    # ── json 子命令：直接从 JSON 文件构建图 ──
    if args.command == "json":
        if not os.path.isfile(args.input):
            print(f"[Error] 找不到文件: {args.input}")
            return 1
        with open(args.input, encoding="utf-8") as f:
            raw_memories = json.load(f)

        # 构造 fake store 或直接用内存数据结构
        class FakeStore:
            def __init__(self, data):
                self.data = data

            def query(self, limit=9999):
                return self.data

        store = FakeStore(raw_memories)
        title = args.title
        path = generate_graph_html(
            store,
            output_path=args.output or None,
            min_similarity=args.min_sim,
            max_nodes=args.max_nodes,
            title=title,
            auto_open=args.auto_open,
        )
        print(f"[OK] 记忆网络已生成: {path}")
        return 0

    # ── 需要 MemoryStore ──
    if not HAS_STORE:
        print("[Error] 无法加载 MemoryStore / SqliteStorage")
        print("请确保在项目根目录下运行，或安装 core 模块。")
        return 1

    if args.db:
        db_path = args.db
    else:
        db_path = os.path.join(
            str(settings.coze_workspace),
            "assets",
            "alpha_id.db",
        )

    if not os.path.isfile(db_path):
        print(f"[Error] 数据库不存在: {db_path}")
        print("提示: 可用 memory_graph.py json <file.json> 直接传入 JSON 数据。")
        return 1

    storage = SqliteStorage(db_path)
    store = MemoryStore(alpha_id=args.alpha_id, storage=storage)

    if args.command == "stats":
        print(graph_stats_text(store))
        return 0

    if args.command == "html":
        title = args.title or f"AID 记忆网络 - {args.alpha_id}"
        path = generate_graph_html(
            store,
            output_path=args.output or None,
            min_similarity=args.min_sim,
            max_nodes=args.max_nodes,
            title=title,
            auto_open=args.auto_open,
        )
        print(f"[OK] 记忆网络已生成: {path}")
        return 0

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(cli())
