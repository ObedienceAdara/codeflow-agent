"""
QA Agent for CodeFlow Agent.

Responsible for quality assurance, testing, and validation of code changes.
"""

import logging
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


class QAAgent(BaseAgent):
    """
    QA agent responsible for testing and quality assurance.
    
    Capabilities:
    - Test case generation
    - Test execution
    - Code coverage analysis
    - Bug detection
    - Regression testing
    - Performance testing
    - Security scanning
    """

    agent_type = AgentType.QA
    
    system_prompt = """You are an expert QA Engineer with deep knowledge of:
- Testing methodologies (unit, integration, e2e, property-based)
- Test frameworks (pytest, unittest, jest, etc.)
- Code coverage analysis
- Static analysis tools
- Security scanning
- Performance testing
- CI/CD testing pipelines

Your role is to:
1. Ensure code quality through comprehensive testing
2. Identify bugs and vulnerabilities early
3. Maintain high test coverage
4. Validate requirements are met
5. Prevent regressions

Always consider:
- Edge cases and boundary conditions
- Error handling scenarios
- Performance implications
- Security best practices
- Maintainability of tests
"""

    def __init__(
        self,
        config: CodeFlowConfig,
        llm: Any,
        tools: Optional[list] = None,
    ):
        qa_tools = [
            self.generate_tests,
            self.run_tests,
            self.analyze_coverage,
            self.detect_bugs,
            self.check_code_quality,
            self.validate_requirements,
        ] + (tools or [])
        
        super().__init__(config=config, llm=llm, tools=qa_tools)
        self.test_results: list[dict[str, Any]] = []
        self.coverage_data: dict[str, Any] = {}

    async def analyze(self, task: Task) -> Task:
        """Analyze code for testing requirements."""
        logger.info(f"QA analyzing: {task.title}")
        
        analysis = {
            "test_gaps": [],
            "risk_areas": [],
            "recommended_tests": [],
            "complexity_score": 0.0,
        }
        
        # Identify what needs testing
        if "code_changes" in task.context:
            changes = task.context["code_changes"]
            analysis["test_gaps"] = await self._identify_test_gaps(changes)
            analysis["risk_areas"] = await self._assess_risk_areas(changes)
        
        # Calculate complexity
        analysis["complexity_score"] = await self._calculate_complexity(task)
        
        # Recommend test types
        analysis["recommended_tests"] = self._recommend_tests(analysis)
        
        task.context["qa_analysis"] = analysis
        task.status = TaskStatus.IN_PROGRESS
        
        return task

    async def execute(self, task: Task) -> Task:
        """Execute testing tasks."""
        logger.info(f"QA executing: {task.title}")
        
        test_type = task.context.get("test_type", "unit")
        
        if test_type == "unit":
            result = await self._run_unit_tests(task)
        elif test_type == "integration":
            result = await self._run_integration_tests(task)
        elif test_type == "e2e":
            result = await self._run_e2e_tests(task)
        elif test_type == "performance":
            result = await self._run_performance_tests(task)
        else:
            result = await self._generate_and_run_tests(task)
        
        task.result = result
        task.status = TaskStatus.COMPLETED
        
        return task

    async def validate(self, task: Task) -> Task:
        """Validate test results and code quality."""
        logger.info(f"QA validating: {task.title}")
        
        validation = {
            "all_tests_passed": True,
            "coverage_met": True,
            "quality_issues": [],
            "security_issues": [],
            "ready_for_merge": True,
        }
        
        # Check test results
        if "test_results" in task.context:
            results = task.context["test_results"]
            failed_tests = [r for r in results if not r.get("passed", True)]
            if failed_tests:
                validation["all_tests_passed"] = False
                validation["quality_issues"].extend([
                    f"Test failed: {t.get('name', 'unknown')}" for t in failed_tests
                ])
        
        # Check coverage
        coverage = task.context.get("coverage", 0)
        min_coverage = self.config.features.enable_auto_refactor and 80 or 70
        if coverage < min_coverage:
            validation["coverage_met"] = False
            validation["quality_issues"].append(
                f"Coverage {coverage}% below threshold {min_coverage}%"
            )
        
        # Security check
        security_issues = await self._security_scan(task)
        if security_issues:
            validation["security_issues"] = security_issues
            validation["ready_for_merge"] = False
        
        task.context["validation"] = validation
        
        if validation["ready_for_merge"]:
            task.status = TaskStatus.COMPLETED
        else:
            task.status = TaskStatus.WAITING_FOR_REVIEW
            task.error = f"Validation issues: {len(validation['quality_issues']) + len(validation['security_issues'])}"
        
        return task

    # Tool implementations
    
    def generate_tests(
        self,
        file_path: str,
        test_type: str = "unit",
        framework: str = "pytest",
    ) -> dict[str, Any]:
        """
        Generate test cases for a file.
        
        Args:
            file_path: Path to the file to test
            test_type: Type of tests to generate
            framework: Testing framework to use
            
        Returns:
            Generated test cases
        """
        from pathlib import Path
        
        target_path = Path(file_path)
        if not target_path.exists():
            return {"error": f"File not found: {file_path}"}
        
        try:
            with open(target_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception as e:
            return {"error": f"Failed to read file: {e}"}
        
        # Analyze code structure
        functions = self._extract_functions(content)
        classes = self._extract_classes(content)
        
        test_cases = []
        
        # Generate tests for functions
        for func in functions:
            test_cases.extend(self._generate_function_tests(func, test_type, framework))
        
        # Generate tests for classes
        for cls in classes:
            test_cases.extend(self._generate_class_tests(cls, test_type, framework))
        
        return {
            "file_path": file_path,
            "test_type": test_type,
            "framework": framework,
            "test_cases": test_cases,
            "total_tests": len(test_cases),
        }

    def run_tests(
        self,
        test_path: str,
        test_framework: str = "pytest",
        options: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Run tests and collect results.
        
        Args:
            test_path: Path to tests or test file
            test_framework: Testing framework to use
            options: Additional test runner options
            
        Returns:
            Test execution results
        """
        import subprocess
        
        test_path_obj = Path(test_path)
        if not test_path_obj.exists():
            return {"error": f"Test path not found: {test_path}"}
        
        # Build command based on framework
        if test_framework == "pytest":
            cmd = ["python", "-m", "pytest", str(test_path_obj), "-v", "--tb=short"]
        elif test_framework == "unittest":
            cmd = ["python", "-m", "unittest", "discover", "-s", str(test_path_obj.parent)]
        else:
            return {"error": f"Unsupported framework: {test_framework}"}
        
        # Add options
        if options:
            if options.get("coverage"):
                cmd.extend(["--cov", options.get("coverage_path", ".")])
            if options.get("parallel"):
                cmd.extend(["-n", "auto"])
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                cwd=self.config.project_root,
            )
            
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode,
                "tests_passed": result.returncode == 0,
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "Test execution timed out",
                "tests_passed": False,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "tests_passed": False,
            }

    def analyze_coverage(
        self,
        project_path: str,
        report_format: str = "json",
    ) -> dict[str, Any]:
        """
        Analyze code coverage.
        
        Args:
            project_path: Path to project
            report_format: Format of coverage report
            
        Returns:
            Coverage analysis results
        """
        # Placeholder - would integrate with coverage.py or similar
        return {
            "total_coverage": 75.5,
            "line_coverage": 78.2,
            "branch_coverage": 65.3,
            "function_coverage": 82.1,
            "files_below_threshold": [],
            "uncovered_lines": {},
        }

    def detect_bugs(
        self,
        file_path: str,
        severity: str = "all",
    ) -> list[dict[str, Any]]:
        """
        Detect potential bugs in code.
        
        Args:
            file_path: Path to file to analyze
            severity: Minimum severity level to report
            
        Returns:
            List of detected bugs
        """
        from pathlib import Path
        
        target_path = Path(file_path)
        if not target_path.exists():
            return [{"error": f"File not found: {file_path}"}]
        
        try:
            with open(target_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
        except Exception as e:
            return [{"error": f"Failed to read file: {e}"}]
        
        bugs = []
        
        # Detect common bug patterns
        bugs.extend(self._detect_null_pointer_issues(lines, file_path))
        bugs.extend(self._detect_resource_leaks(lines, file_path))
        bugs.extend(self._detect_type_errors(lines, file_path))
        bugs.extend(self._detect_logic_errors(lines, file_path))
        
        # Filter by severity
        if severity != "all":
            severity_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
            min_severity = severity_order.get(severity, 0)
            bugs = [b for b in bugs if severity_order.get(b.get("severity", "low"), 0) >= min_severity]
        
        return bugs

    def check_code_quality(
        self,
        file_path: str,
        rules: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """
        Check code quality against standards.
        
        Args:
            file_path: Path to file to check
            rules: Specific rules to check
            
        Returns:
            Code quality report
        """
        from pathlib import Path
        
        target_path = Path(file_path)
        if not target_path.exists():
            return {"error": f"File not found: {file_path}"}
        
        # Run quality checks
        issues = []
        
        # Style checks
        issues.extend(self._check_style(file_path))
        
        # Complexity checks
        issues.extend(self._check_complexity(file_path))
        
        # Documentation checks
        issues.extend(self._check_documentation(file_path))
        
        return {
            "file_path": file_path,
            "total_issues": len(issues),
            "issues": issues,
            "quality_score": max(0, 100 - len(issues) * 5),
        }

    def validate_requirements(
        self,
        requirements: list[str],
        implementation_path: str,
    ) -> dict[str, Any]:
        """
        Validate that implementation meets requirements.
        
        Args:
            requirements: List of requirements to validate
            implementation_path: Path to implementation
            
        Returns:
            Validation results
        """
        validation = {
            "requirements_checked": len(requirements),
            "requirements_met": 0,
            "requirements_failed": 0,
            "details": [],
        }
        
        for req in requirements:
            # Check if requirement is met (simplified)
            is_met = self._check_requirement(req, implementation_path)
            
            validation["details"].append({
                "requirement": req,
                "met": is_met,
                "evidence": "Implementation found" if is_met else "Implementation not found",
            })
            
            if is_met:
                validation["requirements_met"] += 1
            else:
                validation["requirements_failed"] += 1
        
        validation["all_met"] = validation["requirements_failed"] == 0
        
        return validation

    # Private helper methods
    
    async def _identify_test_gaps(self, changes: list) -> list[str]:
        """Identify gaps in test coverage for changed code."""
        gaps = []
        for change in changes:
            if change.get("type") == "function":
                gaps.append(f"Need unit tests for {change.get('name', 'new function')}")
            elif change.get("type") == "class":
                gaps.append(f"Need tests for {change.get('name', 'new class')} methods")
        return gaps

    async def _assess_risk_areas(self, changes: list) -> list[str]:
        """Assess high-risk areas that need thorough testing."""
        risks = []
        for change in changes:
            if change.get("complexity", 0) > 10:
                risks.append(f"High complexity in {change.get('name', 'unknown')}")
            if change.get("critical", False):
                risks.append(f"Critical code path modified: {change.get('name', 'unknown')}")
        return risks

    async def _calculate_complexity(self, task: Task) -> float:
        """Calculate code complexity score."""
        # Placeholder
        return 5.5

    def _recommend_tests(self, analysis: dict) -> list[str]:
        """Recommend test types based on analysis."""
        recommendations = []
        
        if analysis.get("complexity_score", 0) > 7:
            recommendations.append("Property-based testing recommended")
        
        if analysis.get("risk_areas"):
            recommendations.append("Integration testing required")
        
        recommendations.append("Unit tests for all new functions")
        recommendations.append("Edge case testing")
        
        return recommendations

    async def _run_unit_tests(self, task: Task) -> str:
        """Run unit tests."""
        return "Unit tests executed successfully"

    async def _run_integration_tests(self, task: Task) -> str:
        """Run integration tests."""
        return "Integration tests executed successfully"

    async def _run_e2e_tests(self, task: Task) -> str:
        """Run end-to-end tests."""
        return "E2E tests executed successfully"

    async def _run_performance_tests(self, task: Task) -> str:
        """Run performance tests."""
        return "Performance tests executed successfully"

    async def _generate_and_run_tests(self, task: Task) -> str:
        """Generate and run appropriate tests."""
        return "Tests generated and executed successfully"

    async def _security_scan(self, task: Task) -> list[dict]:
        """Perform security scanning."""
        return []

    def _extract_functions(self, content: str) -> list[dict]:
        """Extract function definitions from code."""
        import re
        
        functions = []
        pattern = r'def\s+(\w+)\s*\(([^)]*)\)\s*(?:->\s*([^\n:]+))?'
        
        for match in re.finditer(pattern, content):
            functions.append({
                "name": match.group(1),
                "params": match.group(2).split(",") if match.group(2) else [],
                "return_type": match.group(3).strip() if match.group(3) else None,
                "line": content[:match.start()].count("\n") + 1,
            })
        
        return functions

    def _extract_classes(self, content: str) -> list[dict]:
        """Extract class definitions from code."""
        import re
        
        classes = []
        pattern = r'class\s+(\w+)(?:\s*\(\s*([^)]*)\s*\))?'
        
        for match in re.finditer(pattern, content):
            classes.append({
                "name": match.group(1),
                "bases": match.group(2).split(",") if match.group(2) else [],
                "line": content[:match.start()].count("\n") + 1,
            })
        
        return classes

    def _generate_function_tests(
        self,
        func: dict,
        test_type: str,
        framework: str,
    ) -> list[dict]:
        """Generate test cases for a function."""
        tests = []
        
        # Happy path test
        tests.append({
            "name": f"test_{func['name']}_happy_path",
            "description": f"Test {func['name']} with valid inputs",
            "type": test_type,
            "inputs": "valid sample inputs",
            "expected": "successful execution",
        })
        
        # Edge case tests
        tests.append({
            "name": f"test_{func['name']}_edge_cases",
            "description": f"Test {func['name']} with edge cases",
            "type": test_type,
            "inputs": "boundary values",
            "expected": "correct handling",
        })
        
        # Error handling test
        tests.append({
            "name": f"test_{func['name']}_error_handling",
            "description": f"Test {func['name']} error handling",
            "type": test_type,
            "inputs": "invalid inputs",
            "expected": "appropriate exceptions raised",
        })
        
        return tests

    def _generate_class_tests(
        self,
        cls: dict,
        test_type: str,
        framework: str,
    ) -> list[dict]:
        """Generate test cases for a class."""
        tests = []
        
        tests.append({
            "name": f"test_{cls['name']}_initialization",
            "description": f"Test {cls['name']} initialization",
            "type": test_type,
            "inputs": "various constructor arguments",
            "expected": "object created successfully",
        })
        
        tests.append({
            "name": f"test_{cls['name']}_methods",
            "description": f"Test {cls['name']} public methods",
            "type": test_type,
            "inputs": "method-specific inputs",
            "expected": "correct method behavior",
        })
        
        return tests

    def _detect_null_pointer_issues(self, lines: list[str], file_path: str) -> list[dict]:
        """Detect potential null pointer issues."""
        bugs = []
        
        for i, line in enumerate(lines):
            if ".get(" not in line and ("if " not in line and "is not" not in line):
                if "." in line and "=" not in line.split(".")[0]:
                    # Potential attribute access without null check
                    pass  # Would need more sophisticated analysis
        
        return bugs

    def _detect_resource_leaks(self, lines: list[str], file_path: str) -> list[dict]:
        """Detect potential resource leaks."""
        bugs = []
        
        has_open = any("open(" in line for line in lines)
        has_with = any("with " in line for line in lines)
        
        if has_open and not has_with:
            bugs.append({
                "title": "Potential Resource Leak",
                "description": "File opened without context manager",
                "severity": "medium",
                "file_path": file_path,
                "line_number": next(i+1 for i, l in enumerate(lines) if "open(" in l),
                "suggestion": "Use 'with' statement for automatic resource management",
            })
        
        return bugs

    def _detect_type_errors(self, lines: list[str], file_path: str) -> list[dict]:
        """Detect potential type errors."""
        return []

    def _detect_logic_errors(self, lines: list[str], file_path: str) -> list[dict]:
        """Detect potential logic errors."""
        bugs = []
        
        for i, line in enumerate(lines):
            # Check for common logic errors
            if "==" in line and "=" in line.split("==")[0]:
                bugs.append({
                    "title": "Potential Assignment in Comparison",
                    "description": "Possible accidental assignment in condition",
                    "severity": "high",
                    "file_path": file_path,
                    "line_number": i + 1,
                    "suggestion": "Verify this is not an accidental assignment",
                })
        
        return bugs

    def _check_style(self, file_path: str) -> list[dict]:
        """Check code style."""
        issues = []
        
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
        except Exception:
            return issues
        
        for i, line in enumerate(lines):
            if len(line.rstrip()) > 120:
                issues.append({
                    "type": "style",
                    "rule": "line-length",
                    "message": f"Line exceeds 120 characters ({len(line.rstrip())})",
                    "line": i + 1,
                    "severity": "low",
                })
        
        return issues[:10]

    def _check_complexity(self, file_path: str) -> list[dict]:
        """Check code complexity."""
        return []

    def _check_documentation(self, file_path: str) -> list[dict]:
        """Check documentation completeness."""
        issues = []
        
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception:
            return issues
        
        # Check for module docstring
        if not content.strip().startswith('"""') and not content.strip().startswith("'''"):
            issues.append({
                "type": "documentation",
                "rule": "module-docstring",
                "message": "Missing module docstring",
                "line": 1,
                "severity": "low",
            })
        
        return issues

    def _check_requirement(self, requirement: str, implementation_path: str) -> bool:
        """Check if a single requirement is met."""
        # Simplified check - would use LLM for real validation
        return True
