"""
Alpha-ID 可观测性系统

实现完整的监控、日志、告警、追踪系统

核心功能：
1. 监控指标（延迟、准确率、token 消耗）
2. 日志系统（结构化日志）
3. 告警机制（阈值告警）
4. 追踪系统（请求追踪）

依据：
- 生产级 Agent 系统要求
- Mem0 可观测性实践
"""

import json
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


class MetricType(Enum):
    """指标类型"""
    LATENCY = "latency"           # 延迟（毫秒）
    ACCURACY = "accuracy"         # 准确率（0-100）
    TOKEN_USAGE = "token_usage"   # Token 消耗
    MEMORY_COUNT = "memory_count" # 记忆数量
    ERROR_RATE = "error_rate"     # 错误率（0-100）
    THROUGHPUT = "throughput"     # 吞吐量（请求/秒）


class LogLevel(Enum):
    """日志级别"""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertSeverity(Enum):
    """告警严重程度"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Metric:
    """监控指标"""
    name: str
    type: MetricType
    value: float
    timestamp: float
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class LogEntry:
    """日志条目"""
    level: LogLevel
    message: str
    timestamp: float
    context: Dict[str, Any] = field(default_factory=dict)
    trace_id: str = ""


@dataclass
class Alert:
    """告警"""
    name: str
    severity: AlertSeverity
    message: str
    timestamp: float
    metric_value: float
    threshold: float
    resolved: bool = False


@dataclass
class TraceSpan:
    """追踪跨度"""
    trace_id: str
    span_id: str
    parent_span_id: str
    operation: str
    start_time: float
    end_time: float = 0
    duration_ms: float = 0
    status: str = "pending"  # "pending", "success", "error"
    tags: Dict[str, str] = field(default_factory=dict)
    logs: List[LogEntry] = field(default_factory=list)


class MetricsCollector:
    """
    指标收集器

    收集和存储监控指标
    """

    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path
        self.metrics: Dict[str, List[Metric]] = defaultdict(list)
        self.aggregations: Dict[str, Dict[str, float]] = {}

    def record(self, name: str, type: MetricType, value: float, tags: Dict[str, str] = {}):
        """记录指标"""
        metric = Metric(
            name=name,
            type=type,
            value=value,
            timestamp=time.time(),
            tags=tags,
        )
        self.metrics[name].append(metric)

        # 更新聚合统计
        self._update_aggregation(name)

    def _update_aggregation(self, name: str):
        """更新聚合统计"""
        values = [m.value for m in self.metrics[name]]
        if values:
            self.aggregations[name] = {
                "count": len(values),
                "sum": sum(values),
                "avg": sum(values) / len(values),
                "min": min(values),
                "max": max(values),
                "latest": values[-1],
            }

    def get_metrics(self, name: str, hours: int = 24) -> List[Metric]:
        """获取最近 N 小时的指标"""
        cutoff = time.time() - hours * 3600
        return [m for m in self.metrics[name] if m.timestamp > cutoff]

    def get_aggregation(self, name: str) -> Dict[str, float]:
        """获取聚合统计"""
        return self.aggregations.get(name, {})

    def get_all_aggregations(self) -> Dict[str, Dict[str, float]]:
        """获取所有聚合统计"""
        return self.aggregations


class StructuredLogger:
    """
    结构化日志系统

    记录结构化日志，支持追踪 ID
    """

    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path
        self.logs: List[LogEntry] = []
        self.max_logs = 10000

    def log(
        self,
        level: LogLevel,
        message: str,
        context: Dict[str, Any] = {},
        trace_id: str = ""
    ):
        """记录日志"""
        entry = LogEntry(
            level=level,
            message=message,
            timestamp=time.time(),
            context=context,
            trace_id=trace_id,
        )
        self.logs.append(entry)

        # 限制日志数量
        if len(self.logs) > self.max_logs:
            self.logs = self.logs[-self.max_logs:]

        # 写入文件
        if self.storage_path:
            self._write_to_file(entry)

    def debug(self, message: str, **kwargs):
        self.log(LogLevel.DEBUG, message, kwargs)

    def info(self, message: str, **kwargs):
        self.log(LogLevel.INFO, message, kwargs)

    def warning(self, message: str, **kwargs):
        self.log(LogLevel.WARNING, message, kwargs)

    def error(self, message: str, **kwargs):
        self.log(LogLevel.ERROR, message, kwargs)

    def critical(self, message: str, **kwargs):
        self.log(LogLevel.CRITICAL, message, kwargs)

    def get_logs(self, level: Optional[LogLevel] = None, hours: int = 24) -> List[LogEntry]:
        """获取日志"""
        cutoff = time.time() - hours * 3600
        logs = [log for log in self.logs if log.timestamp > cutoff]

        if level:
            logs = [log for log in logs if log.level == level]

        return logs

    def get_by_trace(self, trace_id: str) -> List[LogEntry]:
        """获取特定追踪的日志"""
        return [log for log in self.logs if log.trace_id == trace_id]

    def _write_to_file(self, entry: LogEntry):
        """写入日志文件"""
        if not self.storage_path:
            return

        log_path = self.storage_path / "logs.json"
        log_data = {
            "level": entry.level.value,
            "message": entry.message,
            "timestamp": entry.timestamp,
            "context": entry.context,
            "trace_id": entry.trace_id,
        }

        with open(log_path, "a") as f:
            f.write(json.dumps(log_data) + "\n")


class AlertManager:
    """
    告警管理器

    监控指标阈值，触发告警
    """

    def __init__(self, metrics_collector: MetricsCollector):
        self.metrics = metrics_collector
        self.alerts: List[Alert] = []
        self.thresholds: Dict[str, Dict[str, Any]] = {}
        self.handlers: List[Callable[[Alert], None]] = []

    def set_threshold(
        self,
        metric_name: str,
        warning_threshold: float,
        critical_threshold: float,
        comparison: str = "greater"  # "greater" or "less"
    ):
        """设置阈值"""
        self.thresholds[metric_name] = {
            "warning": warning_threshold,
            "critical": critical_threshold,
            "comparison": comparison,
        }

    def check_alerts(self) -> List[Alert]:
        """检查告警"""
        new_alerts = []

        for metric_name, threshold in self.thresholds.items():
            aggregation = self.metrics.get_aggregation(metric_name)
            if not aggregation:
                continue

            latest_value = aggregation.get("latest", 0)

            # 检查阈值
            if threshold["comparison"] == "greater":
                if latest_value > threshold["critical"]:
                    alert = Alert(
                        name=metric_name,
                        severity=AlertSeverity.CRITICAL,
                        message=f"{metric_name} 超过严重阈值: {latest_value} > {threshold['critical']}",
                        timestamp=time.time(),
                        metric_value=latest_value,
                        threshold=threshold["critical"],
                    )
                    new_alerts.append(alert)
                elif latest_value > threshold["warning"]:
                    alert = Alert(
                        name=metric_name,
                        severity=AlertSeverity.HIGH,
                        message=f"{metric_name} 超过警告阈值: {latest_value} > {threshold['warning']}",
                        timestamp=time.time(),
                        metric_value=latest_value,
                        threshold=threshold["warning"],
                    )
                    new_alerts.append(alert)

            elif threshold["comparison"] == "less":
                if latest_value < threshold["critical"]:
                    alert = Alert(
                        name=metric_name,
                        severity=AlertSeverity.CRITICAL,
                        message=f"{metric_name} 低于严重阈值: {latest_value} < {threshold['critical']}",
                        timestamp=time.time(),
                        metric_value=latest_value,
                        threshold=threshold["critical"],
                    )
                    new_alerts.append(alert)
                elif latest_value < threshold["warning"]:
                    alert = Alert(
                        name=metric_name,
                        severity=AlertSeverity.HIGH,
                        message=f"{metric_name} 低于警告阈值: {latest_value} < {threshold['warning']}",
                        timestamp=time.time(),
                        metric_value=latest_value,
                        threshold=threshold["warning"],
                    )
                    new_alerts.append(alert)

        # 保存告警并触发处理器
        for alert in new_alerts:
            self.alerts.append(alert)
            for handler in self.handlers:
                handler(alert)

        return new_alerts

    def add_handler(self, handler: Callable[[Alert], None]):
        """添加告警处理器"""
        self.handlers.append(handler)

    def get_active_alerts(self) -> List[Alert]:
        """获取活跃告警"""
        return [alert for alert in self.alerts if not alert.resolved]

    def resolve_alert(self, alert_index: int):
        """解决告警"""
        if 0 <= alert_index < len(self.alerts):
            self.alerts[alert_index].resolved = True


class TraceCollector:
    """
    追踪收集器

    收集请求追踪信息
    """

    def __init__(self):
        self.traces: Dict[str, List[TraceSpan]] = defaultdict(list)
        self.current_spans: Dict[str, TraceSpan] = {}

    def start_span(
        self,
        trace_id: str,
        span_id: str,
        operation: str,
        parent_span_id: str = "",
        tags: Dict[str, str] = {}
    ) -> TraceSpan:
        """开始追踪跨度"""
        span = TraceSpan(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            operation=operation,
            start_time=time.time(),
            tags=tags,
        )
        self.current_spans[span_id] = span
        self.traces[trace_id].append(span)
        return span

    def end_span(self, span_id: str, status: str = "success"):
        """结束追踪跨度"""
        if span_id in self.current_spans:
            span = self.current_spans[span_id]
            span.end_time = time.time()
            span.duration_ms = (span.end_time - span.start_time) * 1000
            span.status = status
            del self.current_spans[span_id]

    def add_log_to_span(self, span_id: str, level: LogLevel, message: str):
        """向跨度添加日志"""
        if span_id in self.current_spans:
            log = LogEntry(
                level=level,
                message=message,
                timestamp=time.time(),
            )
            self.current_spans[span_id].logs.append(log)

    def get_trace(self, trace_id: str) -> List[TraceSpan]:
        """获取追踪"""
        return self.traces.get(trace_id, [])

    def get_trace_summary(self, trace_id: str) -> Dict[str, Any]:
        """获取追踪摘要"""
        spans = self.get_trace(trace_id)
        if not spans:
            return {}

        total_duration = sum(s.duration_ms for s in spans)
        operations = [s.operation for s in spans]
        status_counts = defaultdict(int)
        for s in spans:
            status_counts[s.status] += 1

        return {
            "trace_id": trace_id,
            "span_count": len(spans),
            "total_duration_ms": total_duration,
            "operations": operations,
            "status_distribution": dict(status_counts),
        }


class ObservabilitySystem:
    """
    可观测性系统（整合层）

    整合监控、日志、告警、追踪
    """

    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path
        self.metrics = MetricsCollector(storage_path)
        self.logger = StructuredLogger(storage_path)
        self.alerts = AlertManager(self.metrics)
        self.traces = TraceCollector()

        # 设置默认阈值
        self._setup_default_thresholds()

    def _setup_default_thresholds(self):
        """设置默认阈值"""
        # 延迟阈值（毫秒）
        self.alerts.set_threshold("latency", warning_threshold=1000, critical_threshold=5000, comparison="greater")

        # 错误率阈值（百分比）
        self.alerts.set_threshold("error_rate", warning_threshold=5, critical_threshold=10, comparison="greater")

        # Token 消耗阈值
        self.alerts.set_threshold("token_usage", warning_threshold=10000, critical_threshold=50000, comparison="greater")

    def record_latency(self, operation: str, latency_ms: float, trace_id: str = ""):
        """记录延迟"""
        self.metrics.record("latency", MetricType.LATENCY, latency_ms, {"operation": operation, "trace_id": trace_id})

    def record_accuracy(self, benchmark: str, accuracy: float):
        """记录准确率"""
        self.metrics.record("accuracy", MetricType.ACCURACY, accuracy, {"benchmark": benchmark})

    def record_token_usage(self, operation: str, tokens: int, trace_id: str = ""):
        """记录 Token 消耗"""
        self.metrics.record("token_usage", MetricType.TOKEN_USAGE, tokens, {"operation": operation, "trace_id": trace_id})

    def record_error(self, operation: str, error_type: str, trace_id: str = ""):
        """记录错误"""
        self.logger.error(f"{operation} 发生错误: {error_type}", trace_id=trace_id)

        # 更新错误率
        error_count = len(self.logger.get_logs(level=LogLevel.ERROR, hours=1))
        total_count = len(self.metrics.get_metrics("latency", hours=1))
        if total_count > 0:
            error_rate = (error_count / total_count) * 100
            self.metrics.record("error_rate", MetricType.ERROR_RATE, error_rate, {"operation": operation})

    def start_trace(self, trace_id: str, operation: str) -> str:
        """开始追踪"""
        span_id = f"{trace_id}_0"
        self.traces.start_span(trace_id, span_id, operation)
        return span_id

    def end_trace(self, trace_id: str, status: str = "success"):
        """结束追踪"""
        spans = self.traces.get_trace(trace_id)
        for span in spans:
            if span.status == "pending":
                self.traces.end_span(span.span_id, status)

    def check_health(self) -> Dict[str, Any]:
        """检查系统健康状态"""
        # 检查告警
        new_alerts = self.alerts.check_alerts()

        # 获取指标摘要
        metrics_summary = self.metrics.get_all_aggregations()

        # 获取活跃告警
        active_alerts = self.alerts.get_active_alerts()

        # 判断健康状态
        health_status = "healthy"
        if any(a.severity == AlertSeverity.CRITICAL for a in active_alerts):
            health_status = "critical"
        elif any(a.severity == AlertSeverity.HIGH for a in active_alerts):
            health_status = "warning"

        return {
            "status": health_status,
            "metrics": metrics_summary,
            "active_alerts": len(active_alerts),
            "recent_errors": len(self.logger.get_logs(level=LogLevel.ERROR, hours=1)),
        }

    def get_dashboard_data(self) -> Dict[str, Any]:
        """获取仪表盘数据"""
        return {
            "health": self.check_health(),
            "metrics": {
                "latency": self.metrics.get_aggregation("latency"),
                "accuracy": self.metrics.get_aggregation("accuracy"),
                "token_usage": self.metrics.get_aggregation("token_usage"),
                "error_rate": self.metrics.get_aggregation("error_rate"),
            },
            "alerts": {
                "total": len(self.alerts.alerts),
                "active": len(self.alerts.get_active_alerts()),
            },
            "logs": {
                "total": len(self.logger.logs),
                "errors": len(self.logger.get_logs(level=LogLevel.ERROR)),
                "warnings": len(self.logger.get_logs(level=LogLevel.WARNING)),
            },
        }


# 使用示例
if __name__ == "__main__":
    # 创建可观测性系统
    obs = ObservabilitySystem(storage_path=Path("./data"))

    # 记录指标
    obs.record_latency("memory_search", 150.5, "trace_001")
    obs.record_accuracy("locomo", 92.5)
    obs.record_token_usage("memory_search", 500, "trace_001")

    # 记录日志
    obs.logger.info("记忆搜索完成", trace_id="trace_001", query="用户偏好")

    # 追踪请求
    span_id = obs.start_trace("trace_002", "memory_add")
    obs.traces.add_log_to_span(span_id, LogLevel.INFO, "开始添加记忆")
    obs.traces.end_span(span_id, "success")
    obs.end_trace("trace_002", "success")

    # 检查健康状态
    health = obs.check_health()
    print(f"健康状态: {json.dumps(health, indent=2)}")

    # 获取仪表盘数据
    dashboard = obs.get_dashboard_data()
    print(f"仪表盘: {json.dumps(dashboard, indent=2)}")
