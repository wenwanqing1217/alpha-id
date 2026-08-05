# TERM: TenantPanel — 一用户一多租户工作台面板
"""多租户面板入口路由：每个用户在 `/u/{alpha_id}` 下有一个独立的工作台。

目标：
  - 不强制用户进 Ghost DS；给每个 Alpha-ID 一个"我自己的面板"入口。
  - 多租户隔离：所有请求带 alpha_id 前缀，后端按 alpha_id 做 storage/credits/social 隔离。
  - 常用工作台对接支持：用户能把自己常用的工作台（飞书多维表格、Obsidian、Grafana、Notion 等）
    以外链嵌入或一键跳转的方式挂进来；反过来 Ghost DS / 飞书也能把"本面板"嵌入进去。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from auth.jwt import parse_jwt_or_none  # type: ignore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/u", tags=["tenant-panel"])


# ── 模型 ───────────────────────────────────────────────────────

class WorkbenchLink(BaseModel):
    """用户自己挂的常用工作台链接（多租户：按 alpha_id 分开存）"""
    key: str = Field(..., description="唯一 key，例如 'feishu-bitable-xxx'")
    title: str = Field(..., description="显示标题")
    url: str = Field(..., description="跳转/嵌入 URL")
    embed: bool = Field(False, description="是否允许 iframe 嵌入 (CSP 允许才生效)")
    icon: str = Field("", description="emoji 或图片 URL")


class TenantConfig(BaseModel):
    """一个用户的面板配置（存 Container.storage.tenant_configs:{alpha_id}）"""
    alpha_id: str
    display_name: str = ""
    avatar: str = ""
    # DIY 能力开关（用户自己决定哪些 tab 打开）
    enabled_tabs: List[str] = Field(
        default_factory=lambda: ["overview", "agents", "workflows", "credits", "social", "diy", "workbenches"]
    )
    # 用户挂的常用工作台
    workbenches: List[WorkbenchLink] = Field(default_factory=list)
    # 一键嵌入/跳转 Ghost DS（L6 业务层）面板入口
    ghost_ds_url: str = Field("", description="该用户在 Ghost DS 上的看板 URL")
    # 飞书工作台入口
    feishu_workspace_url: str = Field("", description="该用户在飞书侧的工作台/多维表格入口")
    # 开放给"把我们嵌入到别人"的 token（签名过的短期 token 由 gateway 统一发放，这里存元数据）
    allow_embed_from: List[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "https://*.feishu.cn"]
    )
    extras: Dict[str, Any] = Field(default_factory=dict)


# ── storage helpers ─────────────────────────────────────────────

_NS = "tenant_configs"


def _load(c, alpha_id: str) -> TenantConfig:
    raw = c.storage.kv_get(_NS, alpha_id) if c.storage else None
    if raw:
        try:
            if isinstance(raw, str):
                return TenantConfig(**json.loads(raw))
            return TenantConfig(**raw)
        except Exception:
            logger.exception("tenant config parse fail: %s", alpha_id)
    # 默认
    return TenantConfig(
        alpha_id=alpha_id,
        display_name=alpha_id,
    )


def _save(c, cfg: TenantConfig) -> None:
    if c.storage is None:
        return
    c.storage.kv_put(_NS, cfg.alpha_id, cfg.model_dump(mode="json"))


def _owner_or_403(request: Request, alpha_id: str) -> None:
    """多租户隔离：校验请求者确实是该 alpha_id 的拥有者（或 master key）"""
    # 1) JWT sub == alpha_id
    claims = parse_jwt_or_none(request)
    if claims:
        sub = claims.get("sub") or claims.get("alpha_id") or ""
        if sub and sub == alpha_id:
            return
        if claims.get("role") == "master":
            return
    # 2) 临时简单策略：X-Alpha-ID header 匹配（开发期方便，生产应强制 JWT）
    if request.headers.get("x-alpha-id") == alpha_id:
        return
    raise HTTPException(status_code=403, detail="tenant_mismatch: 仅面板所有者可修改")


# ── 面板主入口 ─────────────────────────────────────────────────

@router.get("/{alpha_id}/dashboard", response_class=HTMLResponse)
def dashboard_html(alpha_id: str, request: Request):
    """每个用户独立的工作台面板入口页（HTML）：
       想干嘛干嘛（agents / 工作流 / 飞书 / 常用工作台 嵌入）。
       多租户隔离：URL 中带 alpha_id，后端按 alpha_id 过滤所有数据。
    """
    from alpha_id.container import get_container
    c = get_container()
    cfg = _load(c, alpha_id)

    # 预取一些面板数据：我的 agents / 好友数 / 积分余额
    my_agents_count = 0
    friends_count = 0
    credits_balance = 0.0
    try:
        from core.agent_graph import get_agent_graph
        g = get_agent_graph()
        my_agents_count = sum(1 for n in g.list_agents() if n.owner_alpha_id == alpha_id)
    except Exception:
        pass
    try:
        friends_count = len(c.social.get_friends(alpha_id)) if c.social else 0
    except Exception:
        pass
    try:
        credits_balance = round(float(c.credits.get_balance(alpha_id) or 0.0), 2)
    except Exception:
        pass

    tabs_html = "".join(
        "<button class='tab' data-tab='{t}'>{label}</button>".format(
            t=t, label=(t.upper() if len(t) <= 3 else t.title())
        )
        for t in cfg.enabled_tabs
    )
    links_html = "".join(
        "<a class='wb' href='{url}' target='_blank' title='{title}'>"
        "  <span class='ico'>{ico}</span><span>{title}</span>"
        "  {embed_tag}"
        "</a>".format(
            url=w.url,
            title=w.title,
            ico=(w.icon or "🔗"),
            embed_tag="(嵌入)" if w.embed else "",
        ) for w in cfg.workbenches
    ) or "<div class='muted'>还没挂工作台，点右侧「添加」挂上飞书多维表格 / Notion / Obsidian 等</div>"

    ghost_ds_link = (
        "<a class='wb' href='{url}' target='_blank'>"
        "  <span class='ico'>🛒</span><span>Ghost DS 业务看板</span></a>"
    ).format(url=cfg.ghost_ds_url) if cfg.ghost_ds_url else ""
    feishu_ws_link = (
        "<a class='wb' href='{url}' target='_blank'>"
        "  <span class='ico'>💬</span><span>我的飞书工作台</span></a>"
    ).format(url=cfg.feishu_workspace_url) if cfg.feishu_workspace_url else ""

    title_display = cfg.display_name or alpha_id
    avatar_chars = title_display[:2].upper()
    iframe_code = (
        "&lt;iframe src='/u/{aid}/dashboard' width='100%' "
        "height='800' frameborder='0'&gt;&lt;/iframe&gt;"
    ).format(aid=alpha_id)

    # 组装 dict 给后面的 HTML 模板做 format_map（注意 JS 里的单大括号不要写成占位符！）
    data = {
        "TITLE": title_display,
        "AVATAR": avatar_chars,
        "AGENTS": str(my_agents_count),
        "FRIENDS": str(friends_count),
        "CREDITS": str(credits_balance),
        "TABS": tabs_html,
        "WBS": ghost_ds_link + feishu_ws_link + links_html,
        "IFRAME_CODE": iframe_code,
        "AID": alpha_id,
    }

    html = _DASHBOARD_TEMPLATE.format_map(data)
    return HTMLResponse(content=html)


# 注意：这份模板使用 {占位符} 来注入服务器侧变量，**只**有上面 data 里的 key 会被替换。
# JS/CSS 里所有其他 { } 都直接保留，所以不能用 f-string。
_DASHBOARD_TEMPLATE = """<!doctype html>
<html lang='zh-CN'>
<head>
<meta charset='utf-8'/>
<title>{TITLE} · Alpha-ID 工作台</title>
<meta name='viewport' content='width=device-width,initial-scale=1'/>
<style>
:root{--brand:#6c5ce7;--bg:#0f1117;--panel:#171a23;--muted:#8b92a7;--fg:#e6e8ef;--ok:#27c28a;--warn:#f0b429;--bad:#ef4444}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.6 system-ui,-apple-system,"PingFang SC","Microsoft YaHei",sans-serif}
header{display:flex;align-items:center;gap:16px;padding:16px 24px;border-bottom:1px solid #232838;background:linear-gradient(180deg,#111420,#0f1117)}
.avatar{width:44px;height:44px;border-radius:12px;background:linear-gradient(135deg,#6c5ce7,#22d3ee);display:flex;align-items:center;justify-content:center;font-weight:700}
.title h1{margin:0;font-size:18px}.title p{margin:2px 0 0;color:var(--muted);font-size:12px}
.stats{margin-left:auto;display:flex;gap:20px}
.stat{text-align:right}.stat b{font-size:18px}.stat div{color:var(--muted);font-size:12px}
main{padding:16px 24px}
.tabs{display:flex;gap:6px;border-bottom:1px solid #232838;margin-bottom:16px;flex-wrap:wrap}
.tab{padding:8px 14px;border:1px solid #232838;border-bottom:none;background:transparent;color:var(--muted);border-radius:8px 8px 0 0;cursor:pointer}
.tab.active{background:var(--panel);color:var(--fg);border-color:#2c3347}
.panel{display:none;background:var(--panel);border-radius:12px;padding:20px;min-height:240px}
.panel.active{display:block}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:14px}
.card{background:#1d2130;border:1px solid #272d42;border-radius:10px;padding:14px}
.card h3{margin:0 0 6px;font-size:14px}.card p{margin:0;color:var(--muted);font-size:12px;min-height:32px}
.card a.btn{display:inline-block;margin-top:10px;padding:6px 10px;background:var(--brand);color:#fff;border-radius:6px;text-decoration:none;font-size:12px}
.wbs{display:flex;flex-wrap:wrap;gap:10px}
.wb{display:flex;align-items:center;gap:8px;padding:10px 12px;background:#1d2130;border:1px solid #272d42;border-radius:10px;color:var(--fg);text-decoration:none;font-size:13px;min-width:180px}
.wb:hover{border-color:var(--brand)}
.wb .ico{font-size:18px}.muted{color:var(--muted)}
form.inline{display:flex;gap:6px;margin-top:12px}form.inline input{flex:1;padding:8px 10px;border-radius:6px;border:1px solid #272d42;background:#0f1117;color:var(--fg)}
form.inline button{padding:8px 14px;background:var(--brand);color:#fff;border:0;border-radius:6px;cursor:pointer}
code{background:#0b0d14;border:1px solid #232838;padding:2px 6px;border-radius:6px;color:#c7d2fe}
</style>
</head>
<body>
<header>
  <div class='avatar'>{AVATAR}</div>
  <div class='title'>
    <h1>{TITLE} <span class='muted' style='font-size:12px;font-weight:400'>· Alpha-ID 工作台</span></h1>
    <p>一用户一多租户面板 · 和自己的 Alpha-ID 聊天就能 DIY 功能 · CLI / Web / 飞书全打通</p>
  </div>
  <div class='stats'>
    <div class='stat'><b>{AGENTS}</b><div>我的 Agents</div></div>
    <div class='stat'><b>{FRIENDS}</b><div>平台好友</div></div>
    <div class='stat'><b>{CREDITS}</b><div>积分余额</div></div>
  </div>
</header>
<main>
  <div class='tabs'>{TABS}</div>

  <section id='overview' class='panel active'>
    <h3>🚀 开始 DIY 你的工作台</h3>
    <div class='muted' style='margin:8px 0 14px'>不用写代码 — 对 CLI / 飞书 / Web 里的 Alpha-ID 说句话即可。接入你常用的工作台，也可以把本面板嵌入到飞书 / Notion / Ghost DS 里。</div>
    <div class='grid'>
      <div class='card'><h3>🧠 对话即实现（CLI）</h3><p>终端里 <code>aid chat "xxx"</code>，自然语言翻译成命令 / agent / 工作流</p>
        <a class='btn' href='#' onclick='alert("试试: aid chat \\\"搭个 Python 项目脚手架\\\" 或 aid diy repl")'>查看帮助</a></div>
      <div class='card'><h3>🤖 注册我自己的 Agent</h3><p>一句话接入自己写的 agent，自动上架 A2A 市场，还能定价</p>
        <a class='btn' href='#' onclick='addTabValue("agents")'>去 Agents</a></div>
      <div class='card'><h3>🔗 挂常用工作台</h3><p>把飞书多维表格 / Notion / Obsidian / Grafana / 你自己的服务挂进来</p>
        <a class='btn' href='#' onclick='addTabValue("workbenches")'>去 Workbenches</a></div>
      <div class='card'><h3>🪐 跑工作流</h3><p>咸鱼文案、小红书、视频脚本、日报，一句话让工作流执行</p>
        <a class='btn' href='#' onclick='addTabValue("workflows")'>去 Workflows</a></div>
      <div class='card'><h3>💬 飞书通讯 & 好友</h3><p>绑定飞书后，通讯录里有 Alpha-ID 的人自动加平台好友</p>
        <a class='btn' href='#' onclick='addTabValue("social")'>去 Social</a></div>
      <div class='card'><h3>🧩 把我嵌入到别处</h3><p>本面板支持 iframe 嵌入 Ghost DS / 飞书多维表格 / 你的内部站点</p>
        <a class='btn' href='#' onclick='document.getElementById("embedcode").scrollIntoView({behavior:"smooth"})'>查看嵌入代码</a></div>
    </div>
  </section>

  <section id='agents' class='panel'>
    <h3>🤖 我的 Agents（多租户：只看我自己的）</h3>
    <div id='agents-list' class='grid' style='margin-top:12px'><div class='muted'>加载中…</div></div>
    <form class='inline' onsubmit='registerAgent(event)'>
      <input id='ragent-name' placeholder='Agent 名称，例如 咸鱼文案生成器' required/>
      <input id='ragent-skills' placeholder='skills，逗号分隔，例如 xianyu_copywriter'/>
      <input id='ragent-price' placeholder='价格积分，0 表示免费' type='number' min='0' value='0'/>
      <input id='ragent-endpoint' placeholder='Agent HTTP 回调 URL (可选)'/>
      <button>一键注册</button>
    </form>
  </section>

  <section id='workflows' class='panel'>
    <h3>🪐 工作流（一句话让 Nebula / Gateway 执行）</h3>
    <div class='muted' style='margin:8px 0'>例：生成咸鱼 iphone 15 文案、制作小红书露营攻略、生成抖音 30 秒视频脚本</div>
    <form class='inline' onsubmit='runWorkflow(event)'>
      <input id='wf-text' placeholder='用自然语言描述工作流和需求' required style='flex:3'/>
      <button>执行</button>
    </form>
    <pre id='wf-out' style='margin-top:14px;background:#0b0d14;border:1px solid #232838;padding:14px;border-radius:10px;max-height:360px;overflow:auto;color:#c7d2fe'></pre>
  </section>

  <section id='credits' class='panel'>
    <h3>💳 积分钱包</h3>
    <div class='grid'>
      <div class='card'><h3>当前余额</h3><p id='cbal'>查询中…</p></div>
      <div class='card'><h3>充值 / 奖励</h3><p>开发期可自助增加积分</p>
        <form class='inline' onsubmit='rewardCredits(event)'>
          <input id='camt' type='number' placeholder='数量，例如 100' required min='1'/>
          <button>奖励积分</button>
        </form></div>
      <div class='card'><h3>交易记录</h3><p id='ctrx'>查询中…</p></div>
    </div>
  </section>

  <section id='social' class='panel'>
    <h3>💬 社交（基于飞书通讯录自动加好友）</h3>
    <div class='grid'>
      <div class='card'><h3>绑定飞书账号</h3><p>绑定后，你的飞书同事只要也绑定了飞书 → 两边自动互认为平台好友</p>
        <form class='inline' onsubmit='bindFeishu(event)'>
          <input id='f-open' placeholder='飞书 open_id (ou_xxx)'/>
          <input id='f-uid' placeholder='飞书 user_id'/>
          <input id='f-phone' placeholder='手机号 (可选，辅助匹配)'/>
          <button>绑定</button>
        </form>
      </div>
      <div class='card'><h3>同步飞书通讯录</h3><p>拉取飞书通讯录 → 匹配平台内 Alpha-ID → 自动互认好友</p>
        <a class='btn' href='#' onclick='syncFeishu()'>立即同步</a>
        <div id='f-out' class='muted' style='margin-top:10px;font-size:12px'></div>
      </div>
      <div class='card'><h3>我的平台好友</h3><p id='friends' class='muted'>加载中…</p></div>
    </div>
  </section>

  <section id='diy' class='panel'>
    <h3>🧠 Alpha-ID DIY Chat（Web 版）</h3>
    <div class='muted' style='margin:8px 0'>和 CLI 的 <code>aid chat xxx</code> 完全等价；说自然语言即可自动选择工具/agent/工作流。</div>
    <form class='inline' onsubmit='diyChat(event)'>
      <input id='diy-prompt' placeholder='例：接一个免费翻译 agent；同步飞书通讯录；生成咸鱼 MacBook 文案' style='flex:3' required/>
      <button>发送</button>
    </form>
    <pre id='diy-out' style='margin-top:14px;background:#0b0d14;border:1px solid #232838;padding:14px;border-radius:10px;max-height:420px;overflow:auto;color:#c7d2fe'></pre>
  </section>

  <section id='workbenches' class='panel'>
    <h3>🔗 常用工作台对接</h3>
    <div class='muted' style='margin-bottom:12px'>把你每天用的工作台挂进来；或者反过来，把"本面板"嵌入到它们里面。</div>
    <div class='wbs' id='wbs'>{WBS}</div>
    <form class='inline' onsubmit='addWorkbench(event)'>
      <input id='wb-key' placeholder='key, 例 my-notion' required/>
      <input id='wb-title' placeholder='标题, 例 我的 Notion' required/>
      <input id='wb-url' placeholder='https://...' required/>
      <input id='wb-icon' placeholder='emoji, 例 📝'/>
      <label style='display:flex;align-items:center;gap:6px'><input id='wb-embed' type='checkbox'/>允许嵌入</label>
      <button>添加</button>
    </form>
    <div id='embedcode' class='muted' style='margin-top:16px'>
      把本面板嵌入到别处：<br/>
      <code>{IFRAME_CODE}</code>
    </div>
  </section>
</main>
<script>
const AID = '{AID}';
const $ = (s,el=document)=>el.querySelector(s);
const $$ = (s,el=document)=>[...el.querySelectorAll(s)];
$$('.tab').forEach(t=>t.addEventListener('click',()=>switchTab(t.dataset.tab)));
function switchTab(name){
  $$('.tab').forEach(t=>t.classList.toggle('active', t.dataset.tab===name));
  $$('.panel').forEach(p=>p.classList.toggle('active', p.id===name));
  if(name==='agents') loadAgents();
  if(name==='credits') loadCredits();
  if(name==='social') loadFriends();
}
function addTabValue(name){ switchTab(name); }
async function api(method, path, body){
  const res = await fetch(path,{
    method,
    headers:{'content-type':'application/json','x-alpha-id':AID},
    ...(body?{body:JSON.stringify(body)}:{}),
  });
  const txt = await res.text();
  let data=null; try{ data = JSON.parse(txt); }catch(_){ data = {raw:txt}; }
  return {ok:res.ok,status:res.status,data};
}
async function loadAgents(){
  const r = await api('GET','/api/v1/a2a/market?owner='+encodeURIComponent(AID));
  const list = (r.data||{}).agents || r.data || [];
  const html = list.length ? list.map(a=>`<div class='card'><h3>${a.agent_id || a.name || '?'}</h3>
    <p>技能: ${(a.skills||[]).join(', ')}<br/>定价: ${a.price_credits ?? 0} 积分</p>
    <a class='btn' href='#'>详情</a></div>`).join('') : `<div class='muted'>还没有自己的 agent，用下方表单一键注册一个</div>`;
  $('#agents-list').innerHTML = html;
}
async function registerAgent(e){
  e.preventDefault();
  const r = await api('POST','/api/v1/a2a/register',{
    agent_id:$('#ragent-name').value.trim(),
    name:$('#ragent-name').value.trim(),
    endpoint:$('#ragent-endpoint').value.trim() || 'https://example.com/placeholder',
    api_key:'user-set-later',
    skill_list:$('#ragent-skills').value.split(/[,，]/).map(s=>s.trim()).filter(Boolean) || [$('#ragent-name').value.trim()],
    owner_alpha_id:AID,
    price_credits:+$('#ragent-price').value||0,
    auto_submit:true,
  });
  alert(JSON.stringify(r.data,null,2));
  loadAgents();
}
async function runWorkflow(e){
  e.preventDefault();
  const prompt = $('#wf-text').value.trim();
  $('#wf-out').textContent = '执行中…';
  const r = await api('POST','/api/v1/u/'+AID+'/diy',{prompt, alpha_id:AID});
  $('#wf-out').textContent = JSON.stringify(r.data,null,2);
}
async function loadCredits(){
  const r = await api('GET','/api/v1/credits/'+encodeURIComponent(AID));
  $('#cbal').textContent = String((r.data||{}).balance ?? '查询失败');
  const r2 = await api('GET','/api/v1/credits/'+encodeURIComponent(AID)+'/history');
  const h = (r2.data||{}).history || [];
  $('#ctrx').textContent = h.length ? h.slice(0,10).map(x=>`${x.dt}  ${x.type}  ${x.amount}  ${x.reason||''}`).join('\\n') : '暂无记录';
}
async function rewardCredits(e){
  e.preventDefault();
  const r = await api('POST','/api/v1/credits/reward',{alpha_id:AID, amount:+$('#camt').value, reason:'self_reward'});
  alert(JSON.stringify(r.data,null,2));
  loadCredits();
}
async function bindFeishu(e){
  e.preventDefault();
  const r = await api('POST',`/api/v1/social/${AID}/bind/feishu`,{
    alpha_id:AID,
    feishu_open_id:$('#f-open').value.trim(),
    feishu_user_id:$('#f-uid').value.trim(),
    phone:$('#f-phone').value.trim(),
  });
  alert(JSON.stringify(r.data,null,2));
}
async function syncFeishu(){
  $('#f-out').textContent='同步中…';
  const r = await api('POST',`/api/v1/social/${AID}/sync-feishu-contacts`,{});
  $('#f-out').textContent = JSON.stringify(r.data,null,2);
  loadFriends();
}
async function loadFriends(){
  const r = await api('GET',`/api/v1/social/${AID}/friends`);
  const f = (r.data||{}).friends || [];
  $('#friends').textContent = f.length ? f.join(', ') : '还没有好友，绑定飞书后同步通讯录自动加好友';
}
async function diyChat(e){
  e.preventDefault();
  const p = $('#diy-prompt').value.trim();
  $('#diy-out').textContent='思考中…';
  const r = await api('POST','/api/v1/u/'+AID+'/diy',{prompt:p, alpha_id:AID});
  $('#diy-out').textContent = JSON.stringify(r.data,null,2);
}
async function addWorkbench(e){
  e.preventDefault();
  const wb = {
    key:$('#wb-key').value.trim(),
    title:$('#wb-title').value.trim(),
    url:$('#wb-url').value.trim(),
    icon:$('#wb-icon').value.trim(),
    embed:$('#wb-embed').checked,
  };
  const r = await api('POST','/api/v1/u/'+AID+'/workbenches', wb);
  alert(JSON.stringify(r.data,null,2));
  location.reload();
}
// 首屏默认 overview 打开即可
</script>
</body>
</html>"""


# ── JSON 配置接口 ──────────────────────────────────────────────

@router.get("/{alpha_id}/config")
def get_config(alpha_id: str):
    from alpha_id.container import get_container
    c = get_container()
    return JSONResponse(_load(c, alpha_id).model_dump(mode="json"))


@router.post("/{alpha_id}/config")
def save_config(alpha_id: str, cfg: TenantConfig, request: Request):
    _owner_or_403(request, alpha_id)
    if cfg.alpha_id != alpha_id:
        raise HTTPException(status_code=400, detail="alpha_id mismatch")
    from alpha_id.container import get_container
    c = get_container()
    _save(c, cfg)
    return {"ok": True, "message": f"多租户面板配置已保存: {alpha_id}"}


@router.get("/{alpha_id}/workbenches")
def list_workbenches(alpha_id: str):
    from alpha_id.container import get_container
    c = get_container()
    cfg = _load(c, alpha_id)
    return {"alpha_id": alpha_id, "workbenches": [w.model_dump(mode="json") for w in cfg.workbenches]}


@router.post("/{alpha_id}/workbenches")
def add_workbench(alpha_id: str, wb: WorkbenchLink, request: Request):
    _owner_or_403(request, alpha_id)
    from alpha_id.container import get_container
    c = get_container()
    cfg = _load(c, alpha_id)
    # upsert by key
    others = [x for x in cfg.workbenches if x.key != wb.key]
    others.append(wb)
    cfg.workbenches = others
    _save(c, cfg)
    return {"ok": True, "message": f"工作台已添加: {wb.key}"}


@router.delete("/{alpha_id}/workbenches/{key}")
def remove_workbench(alpha_id: str, key: str, request: Request):
    _owner_or_403(request, alpha_id)
    from alpha_id.container import get_container
    c = get_container()
    cfg = _load(c, alpha_id)
    cfg.workbenches = [x for x in cfg.workbenches if x.key != key]
    _save(c, cfg)
    return {"ok": True}


# ── Web 版 DIY chat（和 CLI 的 aid chat 等价）───────────────────

class DiyChatReq(BaseModel):
    prompt: str
    alpha_id: str = ""
    dry_run: bool = False
    use_local_parser: bool = False


@router.post("/{alpha_id}/diy")
def web_diy_chat(alpha_id: str, req: DiyChatReq, request: Request):
    # 多租户隔离：URL 里的 alpha_id 优先级高于 body
    aid = alpha_id or req.alpha_id
    # 任何人只读自己面板里的；允许所有人试用 demo，严格场景可加 _owner_or_403
    try:
        from alpha_id.diy_cli import IntentExecutor, _llm_parse_intent, _local_parse_intent
        parser = _local_parse_intent if req.use_local_parser else _llm_parse_intent
        intent = parser(req.prompt)
        intent.params.setdefault("prompt", req.prompt)
        executor = IntentExecutor(alpha_id=aid)
        result = executor.execute(intent)
        return {
            "alpha_id": aid,
            "intent": intent.intent,
            "confidence": intent.confidence,
            "params": intent.params,
            "result": result,
        }
    except Exception as e:
        logger.exception("web diy chat fail")
        return {"alpha_id": aid, "error": str(e)}
