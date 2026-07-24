"""
短剧审核后台服务（Auto-start Background Service）

功能：
1. 自动加载持久化审核队列
2. 定期扫描待处理任务
3. 自动执行 AI 预扫 + 提交审核
4. 监控审核状态变化
5. 可选：自动上传到短剧平台（浏览器自动化）

启动方式：
  python -m src.entrypoints.shortdrama_service

Windows 开机自启：
  将 scripts/start_shortdrama_service.bat 放入启动文件夹
  %APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Startup\
"""

import argparse
import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict

# ── 日志 ──

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("shortdrama_service.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("shortdrama_service")

# ── 全局状态 ──

PID_FILE = "shortdrama_service.pid"
STATE_FILE = "shortdrama_service_state.json"
DEFAULT_CHECK_INTERVAL = 60  # 秒


def get_pid_file() -> Path:
    return Path(PID_FILE)


def get_state_file() -> Path:
    return Path(STATE_FILE)


def write_pid():
    pid = os.getpid()
    get_pid_file().write_text(str(pid), encoding="utf-8")
    logger.info("PID 文件已写入: %s", pid)


def remove_pid():
    try:
        get_pid_file().unlink()
    except FileNotFoundError:
        pass


def is_running() -> bool:
    pid_file = get_pid_file()
    if not pid_file.exists():
        return False
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
        # 检查进程是否存活
        os.kill(pid, 0)
        return True
    except (ValueError, ProcessLookupError, PermissionError):
        # PID 文件存在但进程已退出
        try:
            pid_file.unlink()
        except FileNotFoundError:
            pass
        return False


def load_state() -> Dict[str, Any]:
    state_file = get_state_file()
    if state_file.exists():
        try:
            return json.loads(state_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "started_at": datetime.now().isoformat(),
        "last_check": None,
        "processed_jobs": [],
        "errors": [],
    }


def save_state(state: Dict[str, Any]):
    state["last_check"] = datetime.now().isoformat()
    try:
        get_state_file().write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as e:
        logger.warning("保存状态文件失败: %s", e)


# ── 核心服务 ──


class ShortDramaBackgroundService:
    """短剧审核后台服务"""

    def __init__(self, check_interval: int = DEFAULT_CHECK_INTERVAL, auto_upload: bool = False):
        self.check_interval = check_interval
        self.auto_upload = auto_upload
        self._running = False
        self._queue = None
        self._browser = None

    def _init_storage(self):
        """初始化存储后端（优先 SqliteStorage，降级到内存）"""
        try:
            from core.storage_sqlite import SqliteStorage
            from tools.shortdrama_tool import ReviewQueue

            db_path = os.path.join(os.getcwd(), "assets", "shortdrama_jobs.db")
            storage = SqliteStorage(db_path)
            self._queue = ReviewQueue(storage_backend=storage, storage_key="jobs")
            logger.info("使用 SqliteStorage 持久化: %s", db_path)
        except Exception as e:
            logger.warning("SqliteStorage 初始化失败，降级到内存: %s", e)
            try:
                from tools.shortdrama_tool import ReviewQueue
                self._queue = ReviewQueue()
                logger.info("使用内存 ReviewQueue")
            except ImportError:
                logger.error("无法导入 ReviewQueue")
                raise

    def _init_browser(self):
        """初始化浏览器自动化（可选）"""
        if not self.auto_upload:
            return
        try:
            from tools.shortdrama_tool import ShortDramaBrowserAutomation
            self._browser = ShortDramaBrowserAutomation(headless=True)
            logger.info("浏览器自动化已启用（headless 模式）")
        except Exception as e:
            logger.warning("浏览器自动化初始化失败: %s", e)
            self._browser = None

    def _process_pending_jobs(self, state: Dict[str, Any]):
        """处理待提交的任务"""
        try:
            pending_jobs = self._queue.list_jobs(status="pending")
            logger.info("发现 %d 个待处理任务", len(pending_jobs))

            for job in pending_jobs:
                job_id = job["job_id"]
                if job_id in state.get("processed_jobs", []):
                    continue

                logger.info("处理任务: %s - %s", job_id, job.get("title", ""))
                try:
                    # 任务已在提交时完成 AI 预扫，这里只做状态流转
                    self._queue.update_status(job_id, "reviewing")
                    state.setdefault("processed_jobs", []).append(job_id)
                    logger.info("任务 %s 状态已更新为 reviewing", job_id)
                except Exception as e:
                    logger.error("处理任务 %s 失败: %s", job_id, e)
                    state.setdefault("errors", []).append({
                        "time": datetime.now().isoformat(),
                        "job_id": job_id,
                        "error": str(e),
                    })
        except Exception as e:
            logger.error("获取待处理任务失败: %s", e)

    def _auto_upload_approved(self, state: Dict[str, Any]):
        """自动上传已通过的短剧到平台（如果启用）"""
        if not self._browser:
            return
        try:
            approved_jobs = self._queue.list_jobs(status="approved")
            for job in approved_jobs:
                job_id = job["job_id"]
                upload_key = f"uploaded_{job_id}"
                if upload_key in state.get("processed_jobs", []):
                    continue

                logger.info("自动上传任务: %s", job_id)
                try:
                    result = self._browser.upload_content(
                        title=job.get("title", ""),
                        content=job.get("content", ""),
                    )
                    if result.get("success"):
                        state.setdefault("processed_jobs", []).append(upload_key)
                        logger.info("任务 %s 上传成功", job_id)
                    else:
                        logger.warning("任务 %s 上传失败: %s", job_id, result.get("error"))
                except Exception as e:
                    logger.error("上传任务 %s 异常: %s", job_id, e)
        except Exception as e:
            logger.error("自动上传扫描失败: %s", e)

    def run(self):
        """主循环"""
        logger.info("=" * 50)
        logger.info("短剧审核后台服务启动")
        logger.info("检查间隔: %d 秒", self.check_interval)
        logger.info("自动上传: %s", "开启" if self.auto_upload else "关闭")
        logger.info("=" * 50)

        self._init_storage()
        self._init_browser()
        write_pid()
        self._running = True
        state = load_state()

        try:
            while self._running:
                try:
                    logger.info("开始检查...")
                    self._process_pending_jobs(state)
                    self._auto_upload_approved(state)
                    save_state(state)
                    logger.info("检查完成，等待 %d 秒后下次检查", self.check_interval)
                except Exception as e:
                    logger.error("检查周期异常: %s", e, exc_info=True)

                # 休眠（可被中断）
                time.sleep(self.check_interval)
        except KeyboardInterrupt:
            logger.info("收到中断信号，正在关闭...")
        finally:
            self._running = False
            if self._browser:
                try:
                    self._browser.close()
                except Exception:
                    pass
            remove_pid()
            save_state(state)
            logger.info("短剧审核后台服务已停止")


def main():
    parser = argparse.ArgumentParser(description="短剧审核后台服务")
    parser.add_argument(
        "--interval",
        "-i",
        type=int,
        default=DEFAULT_CHECK_INTERVAL,
        help=f"检查间隔（秒，默认 {DEFAULT_CHECK_INTERVAL}）",
    )
    parser.add_argument(
        "--auto-upload",
        action="store_true",
        help="自动上传已通过的短剧到平台",
    )
    parser.add_argument(
        "--daemon",
        "-d",
        action="store_true",
        help="以守护进程方式运行（Windows 下使用 pythonw）",
    )
    args = parser.parse_args()

    if is_running():
        logger.warning("服务已在运行（PID: %s），请先停止现有进程", get_pid_file().read_text().strip())
        sys.exit(1)

    if args.daemon:
        logger.info("守护进程模式需要配合 pythonw 或独立启动器使用")
        logger.info("当前仍以前台进程运行...")

    service = ShortDramaBackgroundService(
        check_interval=args.interval,
        auto_upload=args.auto_upload,
    )
    service.run()


if __name__ == "__main__":
    main()
