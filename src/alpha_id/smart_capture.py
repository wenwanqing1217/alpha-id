"""
Alpha-ID Smart Capture — 智能采集层
====================================

不是搬运工，是侦探：
  - 观察产出（Git 提交、代码变更、项目文件）
  - 理解含义（LLM 分析变更的意义）
  - 发现异常（言行不一、卡住、方向偏离）
  - 触发反馈（提醒、询问、建议）

数据源：
  - Git commit / diff
  - 项目文件变更
  - 用户主动输入
  - Obsidian 笔记修改
  - 飞书工作消息

核心原则：
  - 不存原始数据，存理解后的洞察
  - 发现矛盾比记录事实更重要
  - 只有触发行动的观察才值得保留
"""

import hashlib
import json
import logging
import subprocess
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Observation:
    """一次观察结果"""
    id: str = ""
    type: str = ""              # contradiction / stuck / deviation / progress / insight
    source: str = ""            # git / file / user / obsidian / feishu
    title: str = ""
    detail: str = ""
    evidence: str = ""          # 原始证据
    action: str = ""            # ask_user / suggest / notify / auto_resolve
    severity: float = 0.0       # 0-1，严重程度
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    resolved: bool = False
    user_response: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class UserContext:
    """用户当前上下文（从记忆系统获取）"""
    current_projects: List[str] = field(default_factory=list)
    recent_focus: str = ""
    stated_goals: List[str] = field(default_factory=list)
    languages: List[str] = field(default_factory=list)
    domains: List[str] = field(default_factory=list)
    constraints: Dict[str, Any] = field(default_factory=dict)
    recent_decisions: List[Dict] = field(default_factory=list)

    @classmethod
    def from_memory(cls, memory_store) -> "UserContext":
        """从记忆系统构建用户上下文"""
        ctx = cls()
        if memory_store is None:
            return ctx

        try:
            # 从记忆中提取相关信息
            memories = memory_store.search(query="项目 目标 计划 决定", limit=20)
            for mem in memories:
                content = mem.get("content", "")
                if "项目" in content or "在做" in content:
                    ctx.current_projects.append(content)
                if "目标" in content or "计划" in content:
                    ctx.stated_goals.append(content)
                if "决定" in content or "选择" in content:
                    ctx.recent_decisions.append({"content": content})
        except Exception:
            pass

        return ctx


class SmartCapture:
    """
    智能采集器 — 侦探模式

    用法：
        capture = SmartCapture(llm_enricher, memory_store)
        capture.watch_git_repo("/path/to/repo")
        capture.watch_obsidian_vault("/path/to/vault")
        observations = capture.scan()
    """

    def __init__(self, llm_enricher=None, memory_store=None):
        self._enricher = llm_enricher
        self._memory = memory_store
        self._observations: List[Observation] = []
        self._callbacks: List[Callable[[Observation], None]] = []
        self._git_repos: List[Path] = []
        self._obsidian_vaults: List[Path] = []
        self._watched_files: Dict[Path, float] = {}  # path -> last_modified
        self._last_scan: float = 0
        self._stats = {"observations": 0, "actions_triggered": 0}

    def on_observation(self, callback: Callable[[Observation], None]):
        """注册观察回调"""
        self._callbacks.append(callback)

    # ── Git 监控 ──

    def watch_git_repo(self, path: str):
        """添加 Git 仓库监控"""
        p = Path(path)
        if (p / ".git").exists():
            self._git_repos.append(p)
            logger.info("监控 Git 仓库: %s", p)

    def scan_git(self) -> List[Observation]:
        """扫描 Git 仓库变更"""
        observations = []

        for repo in self._git_repos:
            try:
                # 获取最近一次扫描后的新 commit
                since = datetime.fromtimestamp(self._last_scan).isoformat() if self._last_scan else "1 day ago"
                result = subprocess.run(
                    ["git", "log", f"--since={since}", "--oneline", "--no-merges"],
                    cwd=str(repo),
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                if result.returncode == 0 and result.stdout.strip():
                    commits = result.stdout.strip().split("\n")

                    # 分析：卡住检测（同一文件反复修改）
                    stuck = self._detect_stuck(repo, commits)
                    if stuck:
                        observations.append(stuck)

                    # 分析：方向偏离检测
                    deviation = self._detect_deviation(repo, commits)
                    if deviation:
                        observations.append(deviation)

                    # 分析：进展检测
                    progress = self._detect_progress(repo, commits)
                    if progress:
                        observations.append(progress)

            except Exception as e:
                logger.debug("Git scan error (%s): %s", repo, e)

        return observations

    def _detect_stuck(self, repo: Path, commits: List[str]) -> Optional[Observation]:
        """检测是否卡住（反复修改同一处）"""
        if len(commits) < 3:
            return None

        try:
            # 获取最近修改的文件
            result = subprocess.run(
                ["git", "log", "-3", "--name-only", "--pretty=format:"],
                cwd=str(repo),
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
                # 如果最近 3 次提交都修改了同一文件，可能卡住
                from collections import Counter
                file_counts = Counter(files)
                for f, count in file_counts.most_common(3):
                    if count >= 3 and f:
                        return Observation(
                            id=hashlib.md5(f"stuck_{f}_{time.time()}".encode()).hexdigest()[:16],
                            type="stuck",
                            source="git",
                            title=f"可能在 {f} 上卡住了",
                            detail=f"最近 3 次提交都修改了 {f}，可能是遇到困难",
                            evidence=f"文件: {f}, 修改次数: {count}",
                            action="suggest_help",
                            severity=0.6,
                        )
        except Exception:
            pass

        return None

    def _detect_deviation(self, repo: Path, commits: List[str]) -> Optional[Observation]:
        """检测方向偏离"""
        ctx = UserContext.from_memory(self._memory)

        if not ctx.stated_goals:
            return None

        # 简单的关键词偏离检测
        commit_text = " ".join(commits).lower()
        goal_keywords = []
        for goal in ctx.stated_goals:
            # 提取目标关键词（简单分词）
            words = goal.lower().split()
            goal_keywords.extend([w for w in words if len(w) > 3])

        # 如果 commit 内容跟目标关键词完全不相关
        if goal_keywords:
            matches = sum(1 for kw in goal_keywords if kw in commit_text)
            if matches == 0 and len(commits) > 2:
                return Observation(
                    id=hashlib.md5(f"deviation_{time.time()}".encode()).hexdigest()[:16],
                    type="deviation",
                    source="git",
                    title="当前工作可能偏离了目标",
                    detail=f"最近 {len(commits)} 次提交跟你之前说的目标不太一致",
                    evidence=f"commits: {commits[:3]}",
                    action="gentle_reminder",
                    severity=0.4,
                )

        return None

    def _detect_progress(self, repo: Path, commits: List[str]) -> Optional[Observation]:
        """检测进展"""
        if len(commits) >= 5:
            return Observation(
                id=hashlib.md5(f"progress_{time.time()}".encode()).hexdigest()[:16],
                type="progress",
                source="git",
                title=f"最近有 {len(commits)} 次提交，进展不错",
                detail="保持节奏",
                evidence=f"commits: {commits[:3]}",
                action="notify",
                severity=0.1,
            )
        return None

    # ── Obsidian 监控 ──

    def watch_obsidian_vault(self, path: str):
        """添加 Obsidian 笔记库监控"""
        p = Path(path)
        if p.exists():
            self._obsidian_vaults.append(p)
            # 初始化文件状态
            for md_file in p.rglob("*.md"):
                self._watched_files[md_file] = md_file.stat().st_mtime
            logger.info("监控 Obsidian 笔记库: %s", p)

    def scan_obsidian(self) -> List[Observation]:
        """扫描 Obsidian 笔记变更"""
        observations = []

        for vault in self._obsidian_vaults:
            try:
                current_files = {f: f.stat().st_mtime for f in vault.rglob("*.md") if f.is_file()}

                # 新增的笔记
                new_files = set(current_files.keys()) - set(self._watched_files.keys())
                for f in new_files:
                    observations.append(Observation(
                        id=hashlib.md5(f"new_note_{f.name}_{time.time()}".encode()).hexdigest()[:16],
                        type="progress",
                        source="obsidian",
                        title=f"新增笔记: {f.stem}",
                        detail="记录了新内容",
                        evidence=str(f),
                        action="none",
                        severity=0.1,
                    ))

                # 修改的笔记
                for f in set(current_files.keys()) & set(self._watched_files.keys()):
                    if current_files[f] > self._watched_files[f]:
                        observations.append(Observation(
                            id=hashlib.md5(f"edit_note_{f.name}_{time.time()}".encode()).hexdigest()[:16],
                            type="insight",
                            source="obsidian",
                            title=f"修改了笔记: {f.stem}",
                            detail="思考有更新",
                            evidence=str(f),
                            action="learn_from_content",
                            severity=0.3,
                        ))

                # 更新状态
                self._watched_files = current_files

            except Exception as e:
                logger.debug("Obsidian scan error (%s): %s", vault, e)

        return observations

    # ── 用户输入采集 ──

    def capture_user_input(self, text: str, source: str = "manual") -> Optional[Observation]:
        """
        采集用户主动输入

        如果 enricher 可用，用 LLM 分析输入内容
        否则用规则提取关键信息
        """
        if not text or len(text.strip()) < 5:
            return None

        # 用 LLM 分析
        if self._enricher:
            try:
                analysis = self._enricher.analyze(text, source=source)
                if analysis and analysis.get("technical"):
                    return Observation(
                        id=hashlib.md5(f"user_{text[:50]}_{time.time()}".encode()).hexdigest()[:16],
                        type="insight",
                        source=source,
                        title="用户输入的新信息",
                        detail=text[:200],
                        evidence=json.dumps(analysis, ensure_ascii=False)[:500],
                        action="update_memory",
                        severity=0.3,
                    )
            except Exception as e:
                logger.debug("LLM analysis failed for user input: %s", e)

        # 降级：直接记录
        return Observation(
            id=hashlib.md5(f"user_{text[:50]}_{time.time()}".encode()).hexdigest()[:16],
            type="insight",
            source=source,
            title="用户说了一句话",
            detail=text[:200],
            evidence=text[:500],
            action="store_raw",
            severity=0.2,
        )

    # ── 统一扫描 ──

    def scan(self) -> List[Observation]:
        """执行完整扫描"""
        all_obs: List[Observation] = []

        # Git 扫描
        all_obs.extend(self.scan_git())

        # Obsidian 扫描
        all_obs.extend(self.scan_obsidian())

        # 分析：言行不一（用户说的 vs 做的）
        contradiction = self._detect_contradiction()
        if contradiction:
            all_obs.append(contradiction)

        # 存储观察
        self._observations.extend(all_obs)
        self._last_scan = time.time()
        self._stats["observations"] += len(all_obs)

        # 通知回调
        for obs in all_obs:
            for cb in self._callbacks:
                try:
                    cb(obs)
                except Exception:
                    pass

        return all_obs

    def _detect_contradiction(self) -> Optional[Observation]:
        """检测言行不一"""
        # 从记忆中提取用户最近说的
        ctx = UserContext.from_memory(self._memory)

        if not ctx.stated_goals or not ctx.current_projects:
            return None

        # 简单检测：用户说要做 A，但项目进展在 B
        # 这只是一个启发式检测，更精确的判断需要 LLM
        return None  # 留给 LLM 判断

    def get_pending_actions(self) -> List[Observation]:
        """获取需要用户处理的观察"""
        return [o for o in self._observations if not o.resolved and o.action in ("ask_user", "suggest_help")]

    def resolve(self, obs_id: str, user_response: str):
        """用户回应了观察"""
        for obs in self._observations:
            if obs.id == obs_id:
                obs.resolved = True
                obs.user_response = user_response
                break

    def get_stats(self) -> Dict[str, int]:
        return self._stats.copy()
