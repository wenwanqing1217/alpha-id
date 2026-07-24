"""
短剧自动化工具 —— AI预检 + 人工审核 + 状态追踪

功能：
1. AI 本地预扫描：检测违规内容，严重违规直接拦截
2. 提交到审核队列：等待人工审核（1-3天）
3. 状态追踪：查询审核结果
4. 可选浏览器自动化：自动上传到短剧平台（需要 playwright/edge）

使用方式：
- FairyBrain 自然语言调用
- AID API 直接调用
- 命令行独立使用
"""

import json
import logging
import os
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── 可选依赖：浏览器自动化 ──

HAS_PLAYWRIGHT = False
try:
    from playwright.sync_api import sync_playwright

    HAS_PLAYWRIGHT = True
except ImportError:
    pass

# ── 数据存储 ──


class ReviewQueue:
    """本地审核队列（支持内存存储或 StorageBackend 持久化）"""

    def __init__(self, storage_backend=None, storage_key: str = "shortdrama_jobs"):
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._storage = storage_backend
        self._storage_key = storage_key
        # 如果提供了存储后端，启动时加载已有数据
        if self._storage is not None:
            try:
                stored = self._storage.load(self._storage_key)
                if stored and isinstance(stored, dict):
                    self._jobs.update(stored)
            except Exception as e:
                logger.warning("ReviewQueue 加载持久化数据失败: %s", e)

    def _persist(self):
        """将当前任务快照写入存储后端（如果配置了）"""
        if self._storage is None:
            return
        try:
            self._storage.save(self._storage_key, dict(self._jobs))
        except Exception as e:
            logger.warning("ReviewQueue 持久化失败: %s", e)

    def submit(self, title: str, content: str, content_type: str = "video", user_id: str = "default") -> Dict[str, Any]:
        """提交内容到审核队列"""
        job_id = f"sd_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        now = datetime.now()
        self._jobs[job_id] = {
            "job_id": job_id,
            "user_id": user_id,
            "title": title,
            "content": content,
            "content_type": content_type,
            "status": "pending",  # pending -> reviewing -> approved/rejected
            "ai_scan_result": None,
            "review_result": None,
            "platform_status": None,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "reviewed_at": None,
            "notes": [],
        }
        self._persist()
        return self._jobs[job_id]

    def get(self, job_id: str) -> Optional[Dict[str, Any]]:
        """查询任务状态"""
        return self._jobs.get(job_id)

    def list_jobs(self, user_id: str = "default", status: Optional[str] = None) -> List[Dict[str, Any]]:
        """列出任务"""
        jobs = list(self._jobs.values())
        if user_id != "default":
            jobs = [j for j in jobs if j["user_id"] == user_id]
        if status:
            jobs = [j for j in jobs if j["status"] == status]
        return sorted(jobs, key=lambda x: x["created_at"], reverse=True)

    def update_ai_scan(self, job_id: str, ai_result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """更新 AI 扫描结果"""
        job = self._jobs.get(job_id)
        if not job:
            return None
        job["ai_scan_result"] = ai_result
        job["updated_at"] = datetime.now().isoformat()
        self._persist()
        return job

    def update_status(self, job_id: str, status: str, review_result: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """更新审核状态"""
        job = self._jobs.get(job_id)
        if not job:
            return None
        job["status"] = status
        job["updated_at"] = datetime.now().isoformat()
        if review_result:
            job["review_result"] = review_result
            job["reviewed_at"] = datetime.now().isoformat()
        self._persist()
        return job

    def add_note(self, job_id: str, note: str) -> Optional[Dict[str, Any]]:
        """添加备注"""
        job = self._jobs.get(job_id)
        if not job:
            return None
        job["notes"].append({
            "time": datetime.now().isoformat(),
            "text": note,
        })
        job["updated_at"] = datetime.now().isoformat()
        self._persist()
        return job


# 全局审核队列
_review_queue = ReviewQueue()


# ── AI 内容扫描器 ──


class AIContentScanner:
    """基于 LLM 的内容合规扫描器"""

    def __init__(self):
        self.api_key = os.getenv("DEEPSEEK_API_KEY", "") or os.getenv("OPENAI_API_KEY", "")
        self.api_base = os.getenv("DEEPSEEK_API_BASE", "") or os.getenv("OPENAI_API_BASE", "")
        if os.getenv("DEEPSEEK_API_KEY") and not os.getenv("DEEPSEEK_API_BASE") and not os.getenv("OPENAI_API_BASE"):
            self.api_base = "https://api.deepseek.com"
        self.model = os.getenv("AID_LLM_MODEL", "deepseek-chat")
        self._client = None

    @property
    def client(self):
        if self._client is None and self.api_key:
            try:
                from openai import OpenAI
                kwargs = {"api_key": self.api_key}
                if self.api_base:
                    kwargs["base_url"] = self.api_base
                self._client = OpenAI(**kwargs)
            except ImportError:
                pass
        return self._client

    def scan(self, title: str, content: str) -> Dict[str, Any]:
        """
        扫描内容合规性。

        Returns:
            {
                "risk_level": "safe" | "warning" | "blocked",
                "violations": [...],
                "suggestions": [...],
                "summary": "..."
            }
        """
        if not self.client:
            return {
                "risk_level": "unknown",
                "violations": ["AI 扫描服务未配置"],
                "suggestions": ["请配置 DEEPSEEK_API_KEY 或 OPENAI_API_KEY"],
                "summary": "扫描跳过",
            }

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": """你是短剧内容合规审查专家。请检查以下内容是否违反平台规则。

违规类型（严重）：
- 色情低俗、性暗示
- 暴力血腥、虐待
- 政治敏感、违法违规
- 诈骗、传销、虚假宣传
- 侵犯知识产权、抄袭

轻微问题：
- 标题党、夸大宣传
- 低质量内容、灌水
- 诱导分享、强制关注

请返回 JSON：
{
  "risk_level": "safe|warning|blocked",
  "violations": ["违规类型1", ...],
  "suggestions": ["修改建议1", ...],
  "summary": "一句话总结"
}

严格返回 JSON，不要额外文字。""",
                    },
                    {
                        "role": "user",
                        "content": f"标题：{title}\n\n内容：\n{content[:2000]}",
                    },
                ],
                temperature=0.1,
                max_tokens=256,
            )
            result_text = response.choices[0].message.content.strip()
            if result_text.startswith("```"):
                result_text = result_text.split("```", 2)[1]
                if result_text.startswith("json"):
                    result_text = result_text[4:]
                result_text = result_text.strip()
            return json.loads(result_text)
        except Exception as e:
            logger.error("AI content scan failed: %s", e)
            return {
                "risk_level": "unknown",
                "violations": [],
                "suggestions": [f"扫描失败: {str(e)}"],
                "summary": "扫描失败，建议人工复核",
            }


# ── 浏览器自动化（可选） ──


class ShortDramaBrowserAutomation:
    """浏览器自动化：自动上传到短剧平台"""

    # 默认选择器（可根据平台页面结构调整）
    SELECTORS = {
        "login_email": 'input[type="email"], input[name="email"], input[placeholder*="邮箱"]',
        "login_password": 'input[type="password"], input[name="password"]',
        "login_button": 'button:has-text("登录"), button:has-text("Log in"), input[type="submit"]',
        "new_content_button": 'text=新建短剧, text=上传内容, text=发布, a:has-text("新建")',
        "title_input": 'input[name="title"], input[placeholder*="标题"], textarea[name="title"]',
        "content_textarea": 'textarea[name="content"], textarea[placeholder*="内容"], .editor-content',
        "submit_button": 'button:has-text("提交审核"), button:has-text("发布"), button[type="submit"]',
        "success_message": 'text=提交成功, text=审核中, .success-message',
    }

    def __init__(self, headless: bool = False):
        self.headless = headless
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    def _ensure_playwright(self) -> bool:
        if not HAS_PLAYWRIGHT:
            return False
        if self._playwright is None:
            self._playwright = sync_playwright().start()
        if self._browser is None:
            self._browser = self._playwright.chromium.launch(headless=self.headless)
        if self._context is None:
            self._context = self._browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            )
        if self._page is None:
            self._page = self._context.new_page()
        return True

    def open_platform(self, url: str = "https://www.shortdramas.com"):
        """打开短剧平台并返回页面状态"""
        if not self._ensure_playwright():
            return {"success": False, "error": "Playwright 未安装，无法自动打开浏览器"}
        try:
            self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
            title = self._page.title()
            return {"success": True, "message": f"已打开 {url}", "page_title": title}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def login(self, email: str, password: str) -> Dict[str, Any]:
        """尝试登录平台（如果页面有登录表单）"""
        if not self._ensure_playwright():
            return {"success": False, "error": "Playwright 未安装"}
        try:
            page = self._page
            selectors = self.SELECTORS

            # 查找并填写邮箱
            email_input = page.locator(selectors["login_email"]).first
            if email_input.count() > 0:
                email_input.fill(email)
            else:
                return {"success": False, "error": "未找到邮箱输入框", "logged_in": False}

            # 查找并填写密码
            password_input = page.locator(selectors["login_password"]).first
            if password_input.count() > 0:
                password_input.fill(password)
            else:
                return {"success": False, "error": "未找到密码输入框", "logged_in": False}

            # 点击登录按钮
            login_btn = page.locator(selectors["login_button"]).first
            if login_btn.count() > 0:
                login_btn.click()
                page.wait_for_timeout(2000)
            else:
                return {"success": False, "error": "未找到登录按钮", "logged_in": False}

            return {"success": True, "message": "登录请求已发送", "logged_in": True}
        except Exception as e:
            return {"success": False, "error": str(e), "logged_in": False}

    def upload_content(self, title: str, content: str, cover_image_path: Optional[str] = None) -> Dict[str, Any]:
        """
        上传内容到短剧平台。

        流程：
        1. 打开平台
        2. 点击"新建短剧"或"上传"
        3. 填写标题
        4. 填写内容/上传文件
        5. 提交审核
        6. 截图保存证据

        Returns:
            {
                "success": bool,
                "job_id": str (如果平台返回),
                "screenshot": str (截图路径),
                "error": str (如果失败),
                "steps": list (执行步骤)
            }
        """
        if not self._ensure_playwright():
            return {"success": False, "error": "Playwright 未安装"}

        steps = []
        screenshot_path = None

        try:
            page = self._page
            selectors = self.SELECTORS

            # 步骤 1: 确保在平台首页
            if "shortdramas" not in (page.url or ""):
                result = self.open_platform()
                steps.append(f"打开平台: {result.get('message', result.get('error'))}")
                if not result.get("success"):
                    return {"success": False, "error": result.get("error"), "steps": steps}

            # 步骤 2: 点击新建按钮
            new_btn = page.locator(selectors["new_content_button"]).first
            if new_btn.count() > 0:
                new_btn.click()
                page.wait_for_timeout(1000)
                steps.append("点击新建按钮")
            else:
                steps.append("未找到新建按钮，可能需要手动操作")

            # 步骤 3: 填写标题
            title_input = page.locator(selectors["title_input"]).first
            if title_input.count() > 0:
                title_input.fill(title)
                steps.append(f"填写标题: {title[:50]}")
            else:
                steps.append("未找到标题输入框")

            # 步骤 4: 填写内容
            content_area = page.locator(selectors["content_textarea"]).first
            if content_area.count() > 0:
                content_area.fill(content[:2000])
                steps.append(f"填写内容: {len(content[:2000])} 字符")
            else:
                steps.append("未找到内容输入框")

            # 步骤 5: 提交审核
            submit_btn = page.locator(selectors["submit_button"]).first
            if submit_btn.count() > 0:
                submit_btn.click()
                page.wait_for_timeout(2000)
                steps.append("点击提交审核")

                # 尝试提取 job_id 或成功信息
                try:
                    success_el = page.locator(selectors["success_message"]).first
                    if success_el.count() > 0:
                        success_text = success_el.inner_text()
                        steps.append(f"平台响应: {success_text[:100]}")
                except Exception:
                    pass

            # 步骤 6: 截图保存证据
            screenshot_path = f"shortdrama_upload_{int(time.time())}.png"
            try:
                page.screenshot(path=screenshot_path)
                steps.append(f"截图已保存: {screenshot_path}")
            except Exception:
                screenshot_path = None

            return {
                "success": True,
                "message": "上传流程执行完成，请检查平台确认提交状态",
                "screenshot": screenshot_path,
                "steps": steps,
            }

        except Exception as e:
            # 出错时也截图
            try:
                if self._page:
                    screenshot_path = f"shortdrama_error_{int(time.time())}.png"
                    self._page.screenshot(path=screenshot_path)
            except Exception:
                pass
            return {
                "success": False,
                "error": str(e),
                "screenshot": screenshot_path,
                "steps": steps,
            }

    def check_status(self, job_id: str) -> Dict[str, Any]:
        """检查平台上的审核状态"""
        if not self._ensure_playwright():
            return {"success": False, "error": "Playwright 未安装"}

        try:
            page = self._page
            # 尝试访问内容管理页面
            if "shortdramas" not in (page.url or ""):
                self.open_platform()

            # 刷新页面查看状态
            page.reload(wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(1000)

            # 截图记录当前状态
            screenshot_path = f"shortdrama_status_{job_id}_{int(time.time())}.png"
            try:
                page.screenshot(path=screenshot_path)
            except Exception:
                screenshot_path = None

            return {
                "success": True,
                "message": "状态页面已打开，请手动查看",
                "job_id": job_id,
                "screenshot": screenshot_path,
                "url": page.url,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def close(self):
        """关闭浏览器"""
        try:
            if self._context:
                self._context.close()
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass
        finally:
            self._page = None
            self._context = None
            self._browser = None
            self._playwright = None


# ── 主工具类 ──


class ShortDramaTool:
    """
    短剧自动化工具。

    支持三种使用方式：
    1. AI 预扫 + 本地审核队列（完全可用）
    2. AI 预扫 + 浏览器自动化上传（需要 playwright）
    3. 仅复制内容到剪贴板，手动上传（兜底方案）
    """

    def __init__(self):
        self.scanner = AIContentScanner()
        self.queue = _review_queue

    def scan_and_submit(self, title: str, content: str, content_type: str = "video", user_id: str = "default") -> Dict[str, Any]:
        """
        扫描并提交到审核队列。

        流程：
        1. AI 本地预扫
        2. 如果 blocked -> 直接拒绝
        3. 如果 safe/warning -> 提交到审核队列
        """
        # 1. AI 预扫
        ai_result = self.scanner.scan(title=title, content=content)

        # 2. 创建任务
        job = self.queue.submit(
            title=title,
            content=content,
            content_type=content_type,
            user_id=user_id,
        )

        # 3. 更新 AI 扫描结果
        self.queue.update_ai_scan(job["job_id"], ai_result)

        # 4. 根据扫描结果决定下一步
        if ai_result.get("risk_level") == "blocked":
            self.queue.update_status(
                job["job_id"],
                "rejected",
                review_result={"by": "ai_local", "reason": "严重违规，自动拦截"},
            )
            return {
                "success": False,
                "status": "rejected",
                "job_id": job["job_id"],
                "rejected_by": "ai_local",
                "ai_scan_result": ai_result,
                "message": f"内容被 AI 预检拦截：{'; '.join(ai_result.get('violations', []))}",
            }

        # 5. 提交到审核队列（等待人工审核）
        self.queue.update_status(job["job_id"], "reviewing")

        return {
            "success": True,
            "status": "reviewing",
            "job_id": job["job_id"],
            "ai_scan_result": ai_result,
            "message": "内容已提交审核，预计1-3天出结果",
            "manual_upload": self._get_manual_upload_info(title, content),
        }

    def query_status(self, job_id: str) -> Dict[str, Any]:
        """查询审核状态"""
        job = self.queue.get(job_id)
        if not job:
            return {"success": False, "error": f"任务 {job_id} 不存在"}
        return {
            "success": True,
            "job_id": job_id,
            "status": job["status"],
            "title": job["title"],
            "ai_scan_result": job["ai_scan_result"],
            "review_result": job["review_result"],
            "created_at": job["created_at"],
            "updated_at": job["updated_at"],
        }

    def list_jobs(self, user_id: str = "default", status: Optional[str] = None) -> Dict[str, Any]:
        """列出审核任务"""
        jobs = self.queue.list_jobs(user_id=user_id, status=status)
        return {
            "success": True,
            "total": len(jobs),
            "jobs": jobs,
        }

    def approve_job(self, job_id: str, reviewer: str = "admin") -> Dict[str, Any]:
        """人工审核通过"""
        job = self.queue.update_status(
            job_id,
            "approved",
            review_result={"by": reviewer, "decision": "approve", "time": datetime.now().isoformat()},
        )
        if not job:
            return {"success": False, "error": f"任务 {job_id} 不存在"}
        return {"success": True, "job_id": job_id, "status": "approved", "message": "审核通过"}

    def reject_job(self, job_id: str, reason: str, reviewer: str = "admin") -> Dict[str, Any]:
        """人工审核拒绝"""
        job = self.queue.update_status(
            job_id,
            "rejected",
            review_result={"by": reviewer, "decision": "reject", "reason": reason, "time": datetime.now().isoformat()},
        )
        if not job:
            return {"success": False, "error": f"任务 {job_id} 不存在"}
        return {"success": True, "job_id": job_id, "status": "rejected", "message": f"审核拒绝：{reason}"}

    def _get_manual_upload_info(self, title: str, content: str) -> Dict[str, Any]:
        """获取手动上传信息（浏览器自动化不可用时的兜底方案）"""
        return {
            "platform_url": "https://www.shortdramas.com",
            "steps": [
                "1. 登录创作者账号",
                "2. 进入'内容管理与经营' -> '正片管理'",
                "3. 点击'新建短剧'或'上传'",
                f"4. 填写标题：{title}",
                f"5. 上传内容（视频/剧本）：{content[:100]}...",
                "6. 提交审核",
            ],
            "clipboard_title": title,
            "clipboard_content": content[:500],
        }

    def get_upload_info(self, job_id: str) -> Dict[str, Any]:
        """获取任务的上传信息，用于复制到剪贴板"""
        job = self.queue.get(job_id)
        if not job:
            return {"success": False, "error": f"任务 {job_id} 不存在"}
        info = self._get_manual_upload_info(job["title"], job["content"])
        text = f"标题：{info['clipboard_title']}\n\n内容：\n{info['clipboard_content']}\n\n平台：{info['platform_url']}"
        return {"success": True, "text": text, "upload_info": info}

    def copy_to_clipboard(self, text: str) -> Dict[str, Any]:
        """复制内容到剪贴板，方便手动粘贴"""
        try:
            import pyperclip
            pyperclip.copy(text)
            return {"success": True, "message": "已复制到剪贴板"}
        except ImportError:
            return {
                "success": False,
                "error": "pyperclip 未安装，请运行: pip install pyperclip",
                "text_preview": text[:200],
            }
