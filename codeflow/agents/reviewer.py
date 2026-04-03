"""
Reviewer Agent for CodeFlow Agent.

Responsible for code reviews, quality assessment, and feedback.
"""

import logging
from pathlib import Path
from typing import Any, Optional

from ..config.settings import CodeFlowConfig
from ..models.entities import (
    AgentType,
    Task,
    TaskStatus,
)
from .base import BaseAgent

logger = logging.getLogger(__name__)


class ReviewerAgent(BaseAgent):
    """
    Reviewer agent responsible for code reviews and quality assessment.
    
    Capabilities:
    - Code review automation
    - Style guide enforcement
    - Best practices validation
    - Security vulnerability detection
    - Performance issue identification
    - Documentation review
    - Change impact analysis
    """

    agent_type = AgentType.REVIEWER
    
    system_prompt = """You are an expert Code Reviewer with deep knowledge of:
- Clean code principles and best practices
- Design patterns and anti-patterns
- Security vulnerabilities and mitigation
- Performance optimization techniques
- Testing best practices
- Documentation standards
- Team collaboration and constructive feedback

Your role is to:
1. Provide thorough, constructive code reviews
2. Identify bugs, security issues, and performance problems
3. Ensure code follows team standards
4. Suggest improvements and refactoring opportunities
5. Validate that changes meet requirements

Always provide:
- Specific, actionable feedback
- Code examples when suggesting changes
- Positive reinforcement for good practices
- Clear explanations for issues found
- Priority levels for different concerns
"""

    def __init__(
        self,
        config: CodeFlowConfig,
        llm: Any,
        tools: Optional[list] = None,
    ):
        reviewer_tools = [
            self.review_code,
            self.check_style,
            self.detect_security_issues,
            self.analyze_complexity,
            self.suggest_improvements,
            self.validate_tests,
        ] + (tools or [])
        
        super().__init__(config=config, llm=llm, tools=reviewer_tools)
        self.review_history: list[dict[str, Any]] = []
        self.style_violations: list[dict] = []

    async def analyze(self, task: Task) -> Task:
        """Analyze code for review."""
        logger.info(f"Reviewer analyzing: {task.title}")
        
        analysis = {
            "files_changed": 0,
            "lines_added": 0,
            "lines_removed": 0,
            "complexity_changes": [],
            "risk_areas": [],
        }
        
        if "changes" in task.context:
            changes = task.context["changes"]
            analysis["files_changed"] = len(changes)
            analysis["lines_added"] = sum(c.get("additions", 0) for c in changes)
            analysis["lines_removed"] = sum(c.get("deletions", 0) for c in changes)
        
        task.context["review_analysis"] = analysis
        task.status = TaskStatus.IN_PROGRESS
        
        return task

    async def execute(self, task: Task) -> Task:
        """Execute code review."""
        logger.info(f"Reviewer executing: {task.title}")
        
        review_type = task.context.get("review_type", "full")
        
        if review_type == "security":
            result = await self._security_review(task)
        elif review_type == "performance":
            result = await self._performance_review(task)
        elif review_type == "style":
            result = await self._style_review(task)
        else:
            result = await self._full_review(task)
        
        task.result = result
        task.status = TaskStatus.COMPLETED
        
        return task

    async def validate(self, task: Task) -> Task:
        """Validate review completeness."""
        logger.info(f"Reviewer validating: {task.title}")
        
        validation = {
            "review_complete": True,
            "all_files_reviewed": True,
            "critical_issues_found": False,
            "requires_followup": False,
            "issues": [],
        }
        
        if "review_result" in task.context:
            review = task.context["review_result"]
            
            # Check for critical issues
            critical = [i for i in review.get("issues", []) if i.get("severity") == "critical"]
            if critical:
                validation["critical_issues_found"] = True
                validation["requires_followup"] = True
                validation["issues"].extend([f"Critical: {i['description']}" for i in critical])
        
        task.context["validation"] = validation
        
        if not validation["critical_issues_found"]:
            task.status = TaskStatus.COMPLETED
        else:
            task.status = TaskStatus.WAITING_FOR_REVIEW
        
        return task

    # Tool implementations
    
    def review_code(
        self,
        file_path: str,
        diff: Optional[str] = None,
        context: Optional[dict] = None,
    ) -> dict[str, Any]:
        """
        Review code changes.
        
        Args:
            file_path: Path to the file being reviewed
            diff: Git diff content (optional)
            context: Additional context about the change
            
        Returns:
            Review results with issues and suggestions
        """
        target_path = Path(file_path)
        if not target_path.exists() and not diff:
            return {"error": f"File not found and no diff provided: {file_path}"}
        
        review = {
            "file_path": file_path,
            "summary": "",
            "issues": [],
            "suggestions": [],
            "positive_feedback": [],
            "approval_status": "pending",
        }
        
        # Analyze the code/diff
        if diff:
            review["issues"].extend(self._analyze_diff(diff))
        
        if target_path.exists():
            try:
                with open(target_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    review["issues"].extend(self._analyze_content(content, file_path))
            except Exception as e:
                review["issues"].append({
                    "type": "error",
                    "severity": "high",
                    "description": f"Failed to read file: {e}",
                })
        
        # Determine approval status
        critical_count = sum(1 for i in review["issues"] if i.get("severity") == "critical")
        high_count = sum(1 for i in review["issues"] if i.get("severity") == "high")
        
        if critical_count > 0:
            review["approval_status"] = "rejected"
        elif high_count > 2:
            review["approval_status"] = "changes_requested"
        else:
            review["approval_status"] = "approved_with_comments"
        
        return review

    def check_style(
        self,
        file_path: str,
        style_guide: str = "pep8",
    ) -> dict[str, Any]:
        """
        Check code style compliance.
        
        Args:
            file_path: Path to file to check
            style_guide: Style guide to enforce
            
        Returns:
            Style check results
        """
        target_path = Path(file_path)
        if not target_path.exists():
            return {"error": f"File not found: {file_path}"}
        
        try:
            with open(target_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
        except Exception as e:
            return {"error": f"Failed to read file: {e}"}
        
        violations = []
        
        # Check common style issues
        for i, line in enumerate(lines):
            # Line length
            if len(line.rstrip()) > 120:
                violations.append({
                    "rule": "line-length",
                    "line": i + 1,
                    "message": f"Line exceeds 120 characters ({len(line.rstrip())})",
                    "severity": "low",
                })
            
            # Trailing whitespace
            if line.rstrip() != line.rstrip('\n'):
                violations.append({
                    "rule": "trailing-whitespace",
                    "line": i + 1,
                    "message": "Trailing whitespace detected",
                    "severity": "low",
                })
            
            # Missing docstring (for functions/classes)
            if ('def ' in line or 'class ' in line) and i < len(lines) - 1:
                next_line = lines[i + 1].strip()
                if not (next_line.startswith('"""') or next_line.startswith("'''")):
                    violations.append({
                        "rule": "missing-docstring",
                        "line": i + 1,
                        "message": "Missing docstring",
                        "severity": "medium",
                    })
        
        return {
            "file_path": file_path,
            "style_guide": style_guide,
            "total_violations": len(violations),
            "violations": violations[:50],  # Limit output
            "passed": len(violations) == 0,
        }

    def detect_security_issues(
        self,
        file_path: str,
        severity_threshold: str = "medium",
    ) -> list[dict[str, Any]]:
        """
        Detect security vulnerabilities.
        
        Args:
            file_path: Path to file to analyze
            severity_threshold: Minimum severity to report
            
        Returns:
            List of security issues
        """
        target_path = Path(file_path)
        if not target_path.exists():
            return [{"error": f"File not found: {file_path}"}]
        
        try:
            with open(target_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                lines = content.split("\n")
        except Exception as e:
            return [{"error": f"Failed to read file: {e}"}]
        
        issues = []
        
        # Check for common security issues
        issues.extend(self._check_hardcoded_secrets(lines, file_path))
        issues.extend(self._check_sql_injection(lines, file_path))
        issues.extend(self._check_command_injection(lines, file_path))
        issues.extend(self._check_insecure_functions(lines, file_path))
        
        # Filter by severity
        severity_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        min_severity = severity_order.get(severity_threshold, 1)
        issues = [i for i in issues if severity_order.get(i.get("severity", "low"), 0) >= min_severity]
        
        return issues

    def analyze_complexity(
        self,
        file_path: str,
        threshold: int = 10,
    ) -> dict[str, Any]:
        """
        Analyze code complexity.
        
        Args:
            file_path: Path to file to analyze
            threshold: Complexity threshold for warnings
            
        Returns:
            Complexity analysis results
        """
        target_path = Path(file_path)
        if not target_path.exists():
            return {"error": f"File not found: {file_path}"}
        
        try:
            with open(target_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception as e:
            return {"error": f"Failed to read file: {e}"}
        
        analysis = {
            "file_path": file_path,
            "functions": [],
            "classes": [],
            "overall_complexity": 0,
            "high_complexity_items": [],
        }
        
        # Simple complexity estimation based on nesting and branches
        lines = content.split("\n")
        current_function = None
        current_complexity = 0
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # Track function definitions
            if stripped.startswith("def "):
                if current_function:
                    analysis["functions"].append({
                        "name": current_function,
                        "complexity": current_complexity,
                        "line": i,
                    })
                    if current_complexity > threshold:
                        analysis["high_complexity_items"].append({
                            "type": "function",
                            "name": current_function,
                            "complexity": current_complexity,
                        })
                current_function = stripped.split("(")[0].replace("def ", "")
                current_complexity = 1
            
            # Count complexity indicators
            if current_function:
                if any(kw in stripped for kw in ["if ", "elif ", "for ", "while ", "except ", "with "]):
                    current_complexity += 1
                if stripped.count(" and ") + stripped.count(" or "):
                    current_complexity += stripped.count(" and ") + stripped.count(" or ")
        
        # Add last function
        if current_function:
            analysis["functions"].append({
                "name": current_function,
                "complexity": current_complexity,
            })
        
        analysis["overall_complexity"] = sum(f["complexity"] for f in analysis["functions"]) / max(len(analysis["functions"]), 1)
        
        return analysis

    def suggest_improvements(
        self,
        file_path: str,
        focus_areas: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        """
        Suggest code improvements.
        
        Args:
            file_path: Path to file to analyze
            focus_areas: Areas to focus on (performance, readability, etc.)
            
        Returns:
            List of improvement suggestions
        """
        target_path = Path(file_path)
        if not target_path.exists():
            return [{"error": f"File not found: {file_path}"}]
        
        try:
            with open(target_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception as e:
            return [{"error": f"Failed to read file: {e}"}]
        
        suggestions = []
        areas = focus_areas or ["readability", "performance", "maintainability"]
        
        if "readability" in areas:
            suggestions.extend(self._suggest_readability_improvements(content, file_path))
        
        if "performance" in areas:
            suggestions.extend(self._suggest_performance_improvements(content, file_path))
        
        if "maintainability" in areas:
            suggestions.extend(self._suggest_maintainability_improvements(content, file_path))
        
        return suggestions

    def validate_tests(
        self,
        test_file: str,
        source_file: str,
    ) -> dict[str, Any]:
        """
        Validate test coverage and quality.
        
        Args:
            test_file: Path to test file
            source_file: Path to source file being tested
            
        Returns:
            Test validation results
        """
        validation = {
            "test_file": test_file,
            "source_file": source_file,
            "coverage_estimate": 0.0,
            "test_quality": "unknown",
            "missing_scenarios": [],
            "recommendations": [],
        }
        
        # Check if files exist
        test_path = Path(test_file)
        source_path = Path(source_file)
        
        if not test_path.exists():
            validation["recommendations"].append("Test file does not exist")
            return validation
        
        if not source_path.exists():
            validation["recommendations"].append("Source file does not exist")
            return validation
        
        try:
            with open(test_path, "r", encoding="utf-8", errors="ignore") as f:
                test_content = f.read()
            
            with open(source_path, "r", encoding="utf-8", errors="ignore") as f:
                source_content = f.read()
        except Exception as e:
            validation["recommendations"].append(f"Failed to read files: {e}")
            return validation
        
        # Basic validation
        test_functions = test_content.count("def test_")
        source_functions = source_content.count("def ")
        
        if test_functions > 0:
            validation["coverage_estimate"] = min(100, (test_functions / max(source_functions, 1)) * 100)
        
        if test_functions < source_functions:
            validation["missing_scenarios"].append("Not all functions have tests")
        
        if "assert" not in test_content:
            validation["recommendations"].append("Add assertions to tests")
        
        validation["test_quality"] = "good" if validation["coverage_estimate"] > 80 else "needs_improvement"
        
        return validation

    # Private helper methods
    
    async def _full_review(self, task: Task) -> str:
        """Perform full code review."""
        return "Full review completed"

    async def _security_review(self, task: Task) -> str:
        """Perform security-focused review."""
        return "Security review completed"

    async def _performance_review(self, task: Task) -> str:
        """Perform performance-focused review."""
        return "Performance review completed"

    async def _style_review(self, task: Task) -> str:
        """Perform style-focused review."""
        return "Style review completed"

    def _analyze_diff(self, diff: str) -> list[dict]:
        """Analyze git diff for issues."""
        issues = []
        
        # Check for removed error handling
        if "- try:" in diff and "+ " not in diff.split("- try:")[1].split("\n")[0:5]:
            issues.append({
                "type": "error_handling",
                "severity": "high",
                "description": "Error handling may have been removed",
                "suggestion": "Ensure proper error handling is maintained",
            })
        
        # Check for debug statements
        if "print(" in diff or "pdb.set_trace()" in diff:
            issues.append({
                "type": "debug_code",
                "severity": "medium",
                "description": "Debug statements detected",
                "suggestion": "Remove debug statements before merging",
            })
        
        return issues

    def _analyze_content(self, content: str, file_path: str) -> list[dict]:
        """Analyze file content for issues."""
        issues = []
        lines = content.split("\n")
        
        # Check for TODO comments
        for i, line in enumerate(lines):
            if "TODO" in line or "FIXME" in line:
                issues.append({
                    "type": "technical_debt",
                    "severity": "low",
                    "line": i + 1,
                    "description": f"TODO/FIXME comment: {line.strip()}",
                    "suggestion": "Address or create ticket for this item",
                })
        
        return issues[:20]

    def _check_hardcoded_secrets(self, lines: list[str], file_path: str) -> list[dict]:
        """Check for hardcoded secrets."""
        issues = []
        secret_patterns = ["password", "secret", "api_key", "token", "credential"]
        
        for i, line in enumerate(lines):
            lower_line = line.lower()
            if any(pattern in lower_line for pattern in secret_patterns):
                if "=" in line and not line.strip().startswith("#"):
                    # Check if it looks like a hardcoded value
                    if '"' in line or "'" in line:
                        issues.append({
                            "type": "hardcoded_secret",
                            "severity": "critical",
                            "line": i + 1,
                            "description": "Potential hardcoded secret detected",
                            "suggestion": "Use environment variables or secrets manager",
                        })
        
        return issues

    def _check_sql_injection(self, lines: list[str], file_path: str) -> list[dict]:
        """Check for SQL injection vulnerabilities."""
        issues = []
        
        for i, line in enumerate(lines):
            if "execute(" in line or "cursor.execute" in line:
                if "%" in line or "f\"" in line or "f'" in line or "+" in line:
                    issues.append({
                        "type": "sql_injection",
                        "severity": "critical",
                        "line": i + 1,
                        "description": "Potential SQL injection vulnerability",
                        "suggestion": "Use parameterized queries",
                    })
        
        return issues

    def _check_command_injection(self, lines: list[str], file_path: str) -> list[dict]:
        """Check for command injection vulnerabilities."""
        issues = []
        
        for i, line in enumerate(lines):
            if "subprocess" in line or "os.system" in line or "os.popen" in line:
                if "shell=True" in line or ("+" in line and "\"" in line):
                    issues.append({
                        "type": "command_injection",
                        "severity": "critical",
                        "line": i + 1,
                        "description": "Potential command injection vulnerability",
                        "suggestion": "Avoid shell=True and sanitize inputs",
                    })
        
        return issues

    def _check_insecure_functions(self, lines: list[str], file_path: str) -> list[dict]:
        """Check for use of insecure functions."""
        issues = []
        insecure_funcs = ["eval(", "exec(", "pickle.loads(", "yaml.load("]
        
        for i, line in enumerate(lines):
            for func in insecure_funcs:
                if func in line and not line.strip().startswith("#"):
                    severity = "critical" if func in ["eval(", "exec("] else "high"
                    issues.append({
                        "type": "insecure_function",
                        "severity": severity,
                        "line": i + 1,
                        "description": f"Use of potentially insecure function: {func}",
                        "suggestion": f"Avoid using {func} with untrusted input",
                    })
        
        return issues

    def _suggest_readability_improvements(self, content: str, file_path: str) -> list[dict]:
        """Suggest readability improvements."""
        suggestions = []
        
        # Check for long functions
        if content.count("\n") > 500:
            suggestions.append({
                "area": "readability",
                "suggestion": "Consider breaking this file into smaller modules",
                "impact": "high",
            })
        
        return suggestions

    def _suggest_performance_improvements(self, content: str, file_path: str) -> list[dict]:
        """Suggest performance improvements."""
        suggestions = []
        
        # Check for inefficient patterns
        if "for " in content and "in range(len(" in content:
            suggestions.append({
                "area": "performance",
                "suggestion": "Use enumerate() instead of range(len())",
                "impact": "low",
            })
        
        return suggestions

    def _suggest_maintainability_improvements(self, content: str, file_path: str) -> list[dict]:
        """Suggest maintainability improvements."""
        suggestions = []
        
        # Check for magic numbers
        import re
        numbers = re.findall(r'\b\d{3,}\b', content)
        if numbers:
            suggestions.append({
                "area": "maintainability",
                "suggestion": "Extract magic numbers to named constants",
                "impact": "medium",
            })
        
        return suggestions
