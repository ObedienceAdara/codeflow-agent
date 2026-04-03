"""
Monitor Agent for CodeFlow Agent.

Responsible for system monitoring, alerting, and incident response.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ..config.settings import CodeFlowConfig
from ..models.entities import (
    AgentType,
    ExecutionResult,
    Task,
    TaskStatus,
)
from .base import BaseAgent

logger = logging.getLogger(__name__)


class MonitorAgent(BaseAgent):
    """
    Monitor agent responsible for system monitoring and incident response.
    
    Capabilities:
    - System health monitoring
    - Performance metrics collection
    - Log analysis
    - Alert management
    - Incident detection
    - Automated incident response
    - Anomaly detection
    """

    agent_type = AgentType.MONITOR
    
    system_prompt = """You are an expert Site Reliability Engineer with deep knowledge of:
- Monitoring systems (Prometheus, Grafana, Datadog)
- Log aggregation (ELK, Splunk, Loki)
- Alerting systems (PagerDuty, OpsGenie)
- Incident response procedures
- Performance optimization
- Capacity planning
- Observability best practices

Your role is to:
1. Monitor system health and performance
2. Detect anomalies and potential issues
3. Respond to incidents automatically when possible
4. Generate actionable alerts
5. Provide insights for system improvement

Always prioritize:
- System availability
- Response time
- Error rates
- Resource utilization
- User experience
"""

    def __init__(
        self,
        config: CodeFlowConfig,
        llm: Any,
        tools: Optional[list] = None,
    ):
        monitor_tools = [
            self.check_system_health,
            self.analyze_logs,
            self.get_metrics,
            self.create_alert,
            self.respond_to_incident,
            self.detect_anomalies,
        ] + (tools or [])
        
        super().__init__(config=config, llm=llm, tools=monitor_tools)
        self.alerts: list[dict[str, Any]] = []
        self.incidents: list[dict[str, Any]] = []
        self.metrics_history: dict[str, list] = {}

    async def analyze(self, task: Task) -> Task:
        """Analyze system state and identify issues."""
        logger.info(f"Monitor agent analyzing: {task.title}")
        
        analysis = {
            "system_health": "unknown",
            "active_alerts": 0,
            "active_incidents": 0,
            "anomalies_detected": [],
            "recommendations": [],
        }
        
        # Check system health
        health = await self._check_overall_health()
        analysis["system_health"] = health["status"]
        
        # Count active alerts and incidents
        analysis["active_alerts"] = len([a for a in self.alerts if a.get("status") == "active"])
        analysis["active_incidents"] = len([i for i in self.incidents if i.get("status") == "open"])
        
        task.context["monitor_analysis"] = analysis
        task.status = TaskStatus.IN_PROGRESS
        
        return task

    async def execute(self, task: Task) -> Task:
        """Execute monitoring tasks."""
        logger.info(f"Monitor agent executing: {task.title}")
        
        action_type = task.context.get("action_type", "monitor")
        
        if action_type == "alert":
            result = await self._handle_alert(task)
        elif action_type == "incident":
            result = await self._handle_incident(task)
        elif action_type == "investigate":
            result = await self._investigate_issue(task)
        else:
            result = await self._collect_metrics(task)
        
        task.result = result
        task.status = TaskStatus.COMPLETED
        
        return task

    async def validate(self, task: Task) -> Task:
        """Validate monitoring results."""
        logger.info(f"Monitor agent validating: {task.title}")
        
        validation = {
            "monitoring_active": True,
            "alerts_configured": True,
            "metrics_collected": True,
            "issues": [],
        }
        
        # Check if monitoring is properly configured
        if not self.metrics_history:
            validation["metrics_collected"] = False
            validation["issues"].append("No metrics collected yet")
        
        task.context["validation"] = validation
        
        if all([validation["monitoring_active"], validation["metrics_collected"]]):
            task.status = TaskStatus.COMPLETED
        else:
            task.status = TaskStatus.WAITING_FOR_REVIEW
        
        return task

    # Tool implementations
    
    def check_system_health(
        self,
        components: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """
        Check overall system health.
        
        Args:
            components: Specific components to check
            
        Returns:
            System health status
        """
        default_components = ["api", "database", "cache", "queue", "storage"]
        check_components = components or default_components
        
        health = {
            "overall_status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "components": {},
        }
        
        for component in check_components:
            component_health = self._check_component_health(component)
            health["components"][component] = component_health
            
            if component_health["status"] != "healthy":
                if component_health["status"] == "critical":
                    health["overall_status"] = "critical"
                elif health["overall_status"] != "critical":
                    health["overall_status"] = "degraded"
        
        return health

    def analyze_logs(
        self,
        log_source: str,
        time_range: str = "1h",
        patterns: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """
        Analyze logs for issues.
        
        Args:
            log_source: Source of logs to analyze
            time_range: Time range to analyze
            patterns: Patterns to search for
            
        Returns:
            Log analysis results
        """
        analysis = {
            "log_source": log_source,
            "time_range": time_range,
            "total_entries": 0,
            "error_count": 0,
            "warning_count": 0,
            "patterns_found": [],
            "recommendations": [],
        }
        
        # Placeholder - would integrate with actual log system
        analysis["total_entries"] = 1000
        analysis["error_count"] = 5
        analysis["warning_count"] = 23
        
        if patterns:
            for pattern in patterns:
                analysis["patterns_found"].append({
                    "pattern": pattern,
                    "count": 0,
                    "examples": [],
                })
        
        return analysis

    def get_metrics(
        self,
        metric_names: list[str],
        time_range: str = "1h",
        aggregation: str = "avg",
    ) -> dict[str, Any]:
        """
        Get system metrics.
        
        Args:
            metric_names: Names of metrics to retrieve
            time_range: Time range for metrics
            aggregation: Aggregation method
            
        Returns:
            Metric values
        """
        metrics = {
            "time_range": time_range,
            "aggregation": aggregation,
            "data": {},
        }
        
        # Placeholder metrics
        default_metrics = {
            "cpu_usage": {"value": 45.2, "unit": "%"},
            "memory_usage": {"value": 62.8, "unit": "%"},
            "request_latency": {"value": 125, "unit": "ms"},
            "error_rate": {"value": 0.5, "unit": "%"},
            "requests_per_second": {"value": 150, "unit": "req/s"},
        }
        
        for name in metric_names:
            if name in default_metrics:
                metrics["data"][name] = default_metrics[name]
            else:
                metrics["data"][name] = {"value": 0, "unit": "unknown"}
        
        return metrics

    def create_alert(
        self,
        name: str,
        severity: str,
        condition: str,
        message: str,
        recipients: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """
        Create a new alert.
        
        Args:
            name: Alert name
            severity: Alert severity (low, medium, high, critical)
            condition: Condition that triggers the alert
            message: Alert message
            recipients: List of recipients to notify
            
        Returns:
            Created alert information
        """
        alert = {
            "id": f"alert_{len(self.alerts) + 1}",
            "name": name,
            "severity": severity,
            "condition": condition,
            "message": message,
            "recipients": recipients or [],
            "status": "active",
            "created_at": datetime.utcnow().isoformat(),
            "triggered_count": 0,
        }
        
        self.alerts.append(alert)
        
        return alert

    def respond_to_incident(
        self,
        incident_id: str,
        action: str,
        details: Optional[dict] = None,
    ) -> dict[str, Any]:
        """
        Respond to an incident.
        
        Args:
            incident_id: ID of the incident
            action: Response action to take
            details: Additional action details
            
        Returns:
            Response result
        """
        # Find the incident
        incident = next((i for i in self.incidents if i["id"] == incident_id), None)
        
        if not incident:
            return {"success": False, "error": f"Incident not found: {incident_id}"}
        
        response = {
            "incident_id": incident_id,
            "action": action,
            "success": True,
            "timestamp": datetime.utcnow().isoformat(),
            "details": details or {},
        }
        
        # Update incident
        if "responses" not in incident:
            incident["responses"] = []
        incident["responses"].append(response)
        
        if action == "resolve":
            incident["status"] = "resolved"
            incident["resolved_at"] = datetime.utcnow().isoformat()
        elif action == "acknowledge":
            incident["status"] = "acknowledged"
            incident["acknowledged_at"] = datetime.utcnow().isoformat()
        
        return response

    def detect_anomalies(
        self,
        metric_name: str,
        sensitivity: float = 0.95,
        time_window: str = "1h",
    ) -> list[dict[str, Any]]:
        """
        Detect anomalies in metrics.
        
        Args:
            metric_name: Name of metric to analyze
            sensitivity: Detection sensitivity (0-1)
            time_window: Time window for analysis
            
        Returns:
            List of detected anomalies
        """
        anomalies = []
        
        # Placeholder - would use statistical analysis or ML
        if metric_name in self.metrics_history:
            history = self.metrics_history[metric_name]
            if len(history) > 10:
                # Simple anomaly detection based on standard deviation
                values = [h["value"] for h in history[-100:]]
                avg = sum(values) / len(values)
                std_dev = (sum((v - avg) ** 2 for v in values) / len(values)) ** 0.5
                
                threshold = avg + (std_dev * (2 - sensitivity) * 2)
                
                for i, h in enumerate(history[-10:]):
                    if h["value"] > threshold:
                        anomalies.append({
                            "metric": metric_name,
                            "value": h["value"],
                            "expected_max": threshold,
                            "timestamp": h["timestamp"],
                            "severity": "medium",
                        })
        
        return anomalies

    # Private helper methods
    
    async def _check_overall_health(self) -> dict[str, Any]:
        """Check overall system health."""
        health = self.check_system_health()
        return {
            "status": health["overall_status"],
            "checked_at": datetime.utcnow().isoformat(),
        }

    async def _handle_alert(self, task: Task) -> str:
        """Handle an alert."""
        return "Alert handled successfully"

    async def _handle_incident(self, task: Task) -> str:
        """Handle an incident."""
        return "Incident handled successfully"

    async def _investigate_issue(self, task: Task) -> str:
        """Investigate a reported issue."""
        return "Investigation completed"

    async def _collect_metrics(self, task: Task) -> str:
        """Collect system metrics."""
        return "Metrics collected successfully"

    def _check_component_health(self, component: str) -> dict[str, Any]:
        """Check health of a specific component."""
        # Placeholder - would integrate with actual health checks
        return {
            "status": "healthy",
            "last_check": datetime.utcnow().isoformat(),
            "response_time_ms": 50,
            "details": {},
        }
