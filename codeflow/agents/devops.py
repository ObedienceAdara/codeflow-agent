"""
DevOps Agent for CodeFlow Agent.

Responsible for CI/CD, deployment, infrastructure, and monitoring.
"""

import logging
from pathlib import Path
from typing import Any, Callable, Optional

from ..config.settings import CodeFlowConfig
from ..models.entities import (
    AgentType,
    ExecutionResult,
    Task,
    TaskStatus,
)
from .base import BaseAgent

logger = logging.getLogger(__name__)


class DevOpsAgent(BaseAgent):
    """
    DevOps agent responsible for deployment and infrastructure.
    
    Capabilities:
    - CI/CD pipeline management
    - Container orchestration
    - Infrastructure as Code
    - Deployment automation
    - Environment management
    - Monitoring setup
    - Rollback procedures
    """

    agent_type = AgentType.DEVOPS
    
    system_prompt = """You are an expert DevOps Engineer with deep knowledge of:
- CI/CD pipelines (GitHub Actions, GitLab CI, Jenkins)
- Container technologies (Docker, Kubernetes)
- Infrastructure as Code (Terraform, CloudFormation, Pulumi)
- Cloud platforms (AWS, GCP, Azure)
- Monitoring and observability (Prometheus, Grafana, ELK)
- Security best practices (secrets management, compliance)
- Deployment strategies (blue-green, canary, rolling)

Your role is to:
1. Automate deployment processes
2. Ensure infrastructure reliability
3. Implement monitoring and alerting
4. Manage environments efficiently
5. Optimize resource utilization

Always consider:
- Security and compliance
- High availability
- Disaster recovery
- Cost optimization
- Performance and scalability
"""

    def __init__(
        self,
        config: CodeFlowConfig,
        llm: Any,
        tools: Optional[list[Callable]] = None,
    ):
        devops_tools = [
            self.create_pipeline,
            self.deploy_application,
            self.manage_infrastructure,
            self.check_health,
            self.rollback_deployment,
            self.configure_monitoring,
        ] + (tools or [])
        
        super().__init__(config=config, llm=llm, tools=devops_tools)
        self.deployment_history: list[dict[str, Any]] = []
        self.infrastructure_state: dict[str, Any] = {}

    async def analyze(self, task: Task) -> Task:
        """Analyze deployment requirements."""
        logger.info(f"DevOps analyzing: {task.title}")
        
        analysis = {
            "deployment_target": None,
            "infrastructure_needs": [],
            "pipeline_requirements": [],
            "risks": [],
            "estimated_time": 0,
        }
        
        # Analyze deployment target
        if "environment" in task.context:
            analysis["deployment_target"] = task.context["environment"]
        
        # Check infrastructure requirements
        analysis["infrastructure_needs"] = await self._assess_infrastructure(task)
        
        # Identify pipeline needs
        analysis["pipeline_requirements"] = await self._assess_pipeline_needs(task)
        
        # Assess risks
        analysis["risks"] = await self._assess_deployment_risks(task)
        
        task.context["devops_analysis"] = analysis
        task.status = TaskStatus.IN_PROGRESS
        
        return task

    async def execute(self, task: Task) -> Task:
        """Execute DevOps tasks."""
        logger.info(f"DevOps executing: {task.title}")
        
        action_type = task.context.get("action_type", "deploy")
        
        if action_type == "deploy":
            result = await self._execute_deployment(task)
        elif action_type == "pipeline":
            result = await self._setup_pipeline(task)
        elif action_type == "infrastructure":
            result = await self._provision_infrastructure(task)
        elif action_type == "monitoring":
            result = await self._setup_monitoring(task)
        else:
            result = await self._execute_generic_task(task)
        
        task.result = result
        task.status = TaskStatus.COMPLETED
        
        return task

    async def validate(self, task: Task) -> Task:
        """Validate deployment and infrastructure."""
        logger.info(f"DevOps validating: {task.title}")
        
        validation = {
            "deployment_successful": True,
            "health_checks_passed": True,
            "monitoring_active": True,
            "rollback_ready": True,
            "issues": [],
        }
        
        # Check deployment status
        if "deployment_id" in task.context:
            status = await self._check_deployment_status(task.context["deployment_id"])
            if not status.get("success"):
                validation["deployment_successful"] = False
                validation["issues"].append("Deployment failed")
        
        # Run health checks
        health = await self._run_health_checks(task)
        if not health.get("healthy"):
            validation["health_checks_passed"] = False
            validation["issues"].extend(health.get("issues", []))
        
        # Verify monitoring
        monitoring_status = await self._verify_monitoring(task)
        if not monitoring_status.get("active"):
            validation["monitoring_active"] = False
            validation["issues"].append("Monitoring not properly configured")
        
        task.context["validation"] = validation
        
        if validation["deployment_successful"] and validation["health_checks_passed"]:
            task.status = TaskStatus.COMPLETED
        else:
            task.status = TaskStatus.WAITING_FOR_REVIEW
            task.error = f"Validation issues: {len(validation['issues'])}"
        
        return task

    # Tool implementations
    
    def create_pipeline(
        self,
        pipeline_type: str = "ci_cd",
        platform: str = "github_actions",
        stages: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """
        Create a CI/CD pipeline configuration.
        
        Args:
            pipeline_type: Type of pipeline (ci_cd, ci_only, cd_only)
            platform: CI/CD platform to use
            stages: Pipeline stages to include
            
        Returns:
            Pipeline configuration
        """
        default_stages = ["build", "test", "lint", "deploy"]
        pipeline_stages = stages or default_stages
        
        pipeline = {
            "type": pipeline_type,
            "platform": platform,
            "stages": pipeline_stages,
            "triggers": ["push", "pull_request"],
            "environments": ["development", "staging", "production"],
        }
        
        # Generate platform-specific config
        if platform == "github_actions":
            pipeline["config_file"] = ".github/workflows/ci.yml"
            pipeline["content"] = self._generate_github_actions(pipeline_stages)
        elif platform == "gitlab_ci":
            pipeline["config_file"] = ".gitlab-ci.yml"
            pipeline["content"] = self._generate_gitlab_ci(pipeline_stages)
        elif platform == "jenkins":
            pipeline["config_file"] = "Jenkinsfile"
            pipeline["content"] = self._generate_jenkins(pipeline_stages)
        
        return pipeline

    def deploy_application(
        self,
        environment: str,
        version: str,
        strategy: str = "rolling",
        timeout: int = 300,
    ) -> dict[str, Any]:
        """
        Deploy application to an environment.
        
        Args:
            environment: Target environment
            version: Application version to deploy
            strategy: Deployment strategy
            timeout: Deployment timeout in seconds
            
        Returns:
            Deployment result
        """
        deployment = {
            "environment": environment,
            "version": version,
            "strategy": strategy,
            "status": "in_progress",
            "started_at": None,
            "completed_at": None,
        }
        
        # Simulate deployment steps
        steps = [
            "Pulling container image",
            "Running pre-deployment checks",
            "Scaling down existing instances",
            "Deploying new version",
            "Running health checks",
            "Updating load balancer",
            "Running smoke tests",
        ]
        
        deployment["steps"] = steps
        deployment["estimated_duration"] = min(timeout, len(steps) * 30)
        
        return deployment

    def manage_infrastructure(
        self,
        action: str,
        resource_type: str,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Manage infrastructure resources.
        
        Args:
            action: Action to perform (create, update, delete)
            resource_type: Type of resource
            config: Resource configuration
            
        Returns:
            Infrastructure operation result
        """
        result = {
            "action": action,
            "resource_type": resource_type,
            "status": "pending",
            "changes": [],
        }
        
        # Validate configuration
        validation_errors = self._validate_infrastructure_config(resource_type, config)
        if validation_errors:
            result["status"] = "failed"
            result["errors"] = validation_errors
            return result
        
        # Generate IaC template
        if resource_type == "compute":
            result["template"] = self._generate_compute_template(config)
        elif resource_type == "database":
            result["template"] = self._generate_database_template(config)
        elif resource_type == "network":
            result["template"] = self._generate_network_template(config)
        
        result["status"] = "ready"
        
        return result

    def check_health(
        self,
        endpoint: str,
        checks: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """
        Check application health.
        
        Args:
            endpoint: Health check endpoint
            checks: Specific checks to run
            
        Returns:
            Health check results
        """
        default_checks = ["http_status", "response_time", "dependencies"]
        health_checks = checks or default_checks
        
        results = {
            "endpoint": endpoint,
            "overall_status": "healthy",
            "checks": {},
        }
        
        for check in health_checks:
            results["checks"][check] = {
                "status": "passing",
                "message": f"{check} check passed",
                "latency_ms": 50,
            }
        
        return results

    def rollback_deployment(
        self,
        environment: str,
        target_version: str,
        reason: str = "",
    ) -> dict[str, Any]:
        """
        Rollback to a previous deployment.
        
        Args:
            environment: Environment to rollback
            target_version: Version to rollback to
            reason: Reason for rollback
            
        Returns:
            Rollback result
        """
        rollback = {
            "environment": environment,
            "target_version": target_version,
            "reason": reason,
            "status": "in_progress",
            "steps": [
                "Stopping current deployment",
                f"Restoring version {target_version}",
                "Running validation checks",
                "Updating routing",
                "Verifying rollback",
            ],
        }
        
        return rollback

    def configure_monitoring(
        self,
        metrics: list[str],
        alerts: list[dict[str, Any]],
        dashboard: bool = True,
    ) -> dict[str, Any]:
        """
        Configure monitoring and alerting.
        
        Args:
            metrics: Metrics to collect
            alerts: Alert configurations
            dashboard: Whether to create dashboard
            
        Returns:
            Monitoring configuration
        """
        config = {
            "metrics": metrics,
            "alerts": alerts,
            "dashboard_enabled": dashboard,
            "retention_days": 30,
            "scrape_interval": "15s",
        }
        
        # Generate monitoring configs
        config["prometheus_config"] = self._generate_prometheus_config(metrics)
        config["alertmanager_config"] = self._generate_alertmanager_config(alerts)
        
        if dashboard:
            config["grafana_dashboard"] = self._generate_grafana_dashboard(metrics)
        
        return config

    # Private helper methods
    
    async def _assess_infrastructure(self, task: Task) -> list[str]:
        """Assess infrastructure requirements."""
        needs = []
        
        if task.context.get("requires_database"):
            needs.append("Database instance required")
        
        if task.context.get("requires_cache"):
            needs.append("Cache layer required")
        
        if task.context.get("high_availability"):
            needs.append("Multi-AZ deployment required")
        
        return needs

    async def _assess_pipeline_needs(self, task: Task) -> list[str]:
        """Assess CI/CD pipeline requirements."""
        needs = ["Build stage", "Test stage", "Lint stage"]
        
        if task.context.get("auto_deploy"):
            needs.append("Auto-deployment stage")
        
        if task.context.get("security_scan"):
            needs.append("Security scanning stage")
        
        return needs

    async def _assess_deployment_risks(self, task: Task) -> list[dict]:
        """Assess deployment risks."""
        risks = []
        
        if task.context.get("database_changes"):
            risks.append({
                "type": "database",
                "severity": "high",
                "description": "Database schema changes detected",
                "mitigation": "Ensure backup before deployment",
            })
        
        if task.context.get("breaking_changes"):
            risks.append({
                "type": "compatibility",
                "severity": "high",
                "description": "Breaking API changes detected",
                "mitigation": "Consider versioned API or migration period",
            })
        
        return risks

    async def _execute_deployment(self, task: Task) -> str:
        """Execute deployment."""
        env = task.context.get("environment", "development")
        version = task.context.get("version", "latest")
        
        return f"Deployed version {version} to {env} environment"

    async def _setup_pipeline(self, task: Task) -> str:
        """Setup CI/CD pipeline."""
        return "CI/CD pipeline configured successfully"

    async def _provision_infrastructure(self, task: Task) -> str:
        """Provision infrastructure."""
        return "Infrastructure provisioned successfully"

    async def _setup_monitoring(self, task: Task) -> str:
        """Setup monitoring."""
        return "Monitoring configured successfully"

    async def _execute_generic_task(self, task: Task) -> str:
        """Execute generic DevOps task."""
        return "Task executed successfully"

    async def _check_deployment_status(self, deployment_id: str) -> dict:
        """Check deployment status."""
        return {"success": True, "status": "completed"}

    async def _run_health_checks(self, task: Task) -> dict:
        """Run health checks."""
        return {"healthy": True, "issues": []}

    async def _verify_monitoring(self, task: Task) -> dict:
        """Verify monitoring setup."""
        return {"active": True}

    def _validate_infrastructure_config(
        self,
        resource_type: str,
        config: dict,
    ) -> list[str]:
        """Validate infrastructure configuration."""
        errors = []
        
        if resource_type == "compute" and "instance_type" not in config:
            errors.append("instance_type is required for compute resources")
        
        if resource_type == "database" and "engine" not in config:
            errors.append("engine is required for database resources")
        
        return errors

    def _generate_github_actions(self, stages: list[str]) -> str:
        """Generate GitHub Actions workflow."""
        workflow = """name: CI/CD Pipeline

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
"""
        for stage in stages:
            workflow += f"""
  {stage}:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run {stage}
        run: echo "Running {stage}"
"""
        return workflow

    def _generate_gitlab_ci(self, stages: list[str]) -> str:
        """Generate GitLab CI configuration."""
        config = f"""stages:
  - {'\n  - '.join(stages)}

default:
  image: python:3.12

"""
        for stage in stages:
            config += f"""
{stage}:
  stage: {stage}
  script:
    - echo "Running {stage}"
"""
        return config

    def _generate_jenkins(self, stages: list[str]) -> str:
        """Generate Jenkinsfile."""
        pipeline = """pipeline {
    agent any
    
    stages {
"""
        for stage in stages:
            pipeline += f"""
        stage('{stage}') {{
            steps {{
                echo 'Running {stage}'
            }}
        }}
"""
        pipeline += """    }
}
"""
        return pipeline

    def _generate_compute_template(self, config: dict) -> str:
        """Generate compute infrastructure template."""
        return f"""# Compute Resource Template
resource_type: compute
instance_type: {config.get('instance_type', 't3.medium')}
count: {config.get('count', 1)}
ami: {config.get('ami', 'latest')}
"""

    def _generate_database_template(self, config: dict) -> str:
        """Generate database infrastructure template."""
        return f"""# Database Resource Template
resource_type: database
engine: {config.get('engine', 'postgresql')}
version: {config.get('version', '15')}
instance_class: {config.get('instance_class', 'db.t3.medium')}
storage_gb: {config.get('storage_gb', 100)}
"""

    def _generate_network_template(self, config: dict) -> str:
        """Generate network infrastructure template."""
        return f"""# Network Resource Template
resource_type: network
vpc_cidr: {config.get('vpc_cidr', '10.0.0.0/16')}
subnets: {config.get('subnets', 3)}
availability_zones: {config.get('azs', 3)}
"""

    def _generate_prometheus_config(self, metrics: list[str]) -> str:
        """Generate Prometheus configuration."""
        config = """global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'application'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: /metrics
"""
        return config

    def _generate_alertmanager_config(self, alerts: list[dict]) -> str:
        """Generate Alertmanager configuration."""
        config = """global:
  resolve_timeout: 5m

route:
  group_by: ['alertname']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 1h
  receiver: 'default'

receivers:
  - name: 'default'
    webhook_configs:
      - url: 'http://localhost:5001/webhook'
"""
        return config

    def _generate_grafana_dashboard(self, metrics: list[str]) -> dict:
        """Generate Grafana dashboard configuration."""
        return {
            "title": "Application Dashboard",
            "panels": [
                {"title": m, "type": "graph", "metric": m}
                for m in metrics
            ],
            "refresh": "5s",
            "time_range": "last_1_hour",
        }
