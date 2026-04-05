"""
Architect Agent for CodeFlow Agent.

Responsible for high-level system design, architecture decisions,
and technical strategy planning.
"""

import logging
import re
import os
from pathlib import Path
from typing import Any, Callable, Optional

from langchain_core.messages import AIMessage, HumanMessage

from ...config.settings import CodeFlowConfig
from ...models.entities import (
    AgentType,
    CodeChange,
    CodeEntity,
    CodeEntityType,
    Relationship,
    RelationshipType,
    Task,
    TaskStatus,
    TechDebtItem,
)
from ..base import BaseAgent

logger = logging.getLogger(__name__)


class ArchitectAgent(BaseAgent):
    """
    Architect agent responsible for system design and architecture decisions.
    
    Capabilities:
    - System architecture design
    - Technology stack selection
    - Component decomposition
    - API design
    - Database schema design
    - Technical debt identification
    - Architecture review and validation
    """

    agent_type = AgentType.ARCHITECT
    
    system_prompt = """You are an expert Software Architect with deep knowledge of:
- System design patterns and best practices
- Microservices and distributed systems
- API design (REST, GraphQL, gRPC)
- Database design and optimization
- Cloud architecture (AWS, GCP, Azure)
- Security best practices
- Scalability and performance optimization

Your role is to:
1. Design robust, scalable system architectures
2. Make informed technology choices
3. Identify potential architectural issues early
4. Ensure alignment with business requirements
5. Document architectural decisions clearly

Always consider:
- Maintainability and extensibility
- Performance implications
- Security concerns
- Cost efficiency
- Team capabilities and constraints
"""

    def __init__(
        self,
        config: CodeFlowConfig,
        llm: Any,
        tools: Optional[list[Callable]] = None,
    ):
        # Add architect-specific tools
        architect_tools = [
            self.analyze_architecture,
            self.design_component,
            self.evaluate_technology,
            self.identify_tech_debt,
            self.create_architecture_diagram,
        ] + (tools or [])
        
        super().__init__(config=config, llm=llm, tools=architect_tools)
        self.architecture_patterns: dict[str, Any] = {}
        self.tech_debt_items: list[TechDebtItem] = []

    async def analyze(self, task: Task) -> Task:
        """Analyze the current architecture and identify improvements."""
        logger.info(f"Architect analyzing: {task.title}")
        
        analysis_results = {
            "current_state": await self._assess_current_architecture(),
            "recommendations": [],
            "risks": [],
            "opportunities": [],
        }
        
        # Assess current architecture
        current_assessment = await self._assess_current_architecture()
        analysis_results["current_state"] = current_assessment
        
        # Identify architectural smells
        smells = await self._identify_architectural_smells()
        analysis_results["recommendations"].extend(smells)
        
        # Check scalability concerns
        scalability = await self._assess_scalability()
        if scalability["concerns"]:
            analysis_results["risks"].extend(scalability["concerns"])
        
        task.context["architecture_analysis"] = analysis_results
        task.status = TaskStatus.IN_PROGRESS
        
        return task

    async def execute(self, task: Task) -> Task:
        """Execute architectural design tasks."""
        logger.info(f"Architect executing: {task.title}")
        
        design_type = task.context.get("design_type", "component")
        
        if design_type == "component":
            result = await self._design_component(task)
        elif design_type == "api":
            result = await self._design_api(task)
        elif design_type == "database":
            result = await self._design_database(task)
        else:
            result = await self._create_architecture(task)
        
        task.result = result
        task.status = TaskStatus.COMPLETED
        
        return task

    async def validate(self, task: Task) -> Task:
        """Validate architectural decisions and designs."""
        logger.info(f"Architect validating: {task.title}")
        
        validation_results = {
            "is_valid": True,
            "issues": [],
            "suggestions": [],
            "compliance_score": 0.0,
        }
        
        # Check design principles
        principles_check = await self._check_design_principles(task)
        validation_results["issues"].extend(principles_check.get("violations", []))
        validation_results["suggestions"].extend(principles_check.get("suggestions", []))
        
        # Validate against requirements
        requirements_check = await self._validate_requirements(task)
        if not requirements_check["met"]:
            validation_results["is_valid"] = False
            validation_results["issues"].extend(requirements_check.get("gaps", []))
        
        # Calculate compliance score
        total_checks = len(validation_results["issues"]) + len(validation_results["suggestions"]) + 1
        passed_checks = total_checks - len(validation_results["issues"])
        validation_results["compliance_score"] = (passed_checks / total_checks) * 100
        
        task.context["validation"] = validation_results
        
        if validation_results["is_valid"]:
            task.status = TaskStatus.COMPLETED
        else:
            task.status = TaskStatus.WAITING_FOR_REVIEW
            task.error = f"Validation found {len(validation_results['issues'])} issues"
        
        return task

    # Tool implementations
    
    def analyze_architecture(self, project_path: str) -> dict[str, Any]:
        """
        Analyze the architecture of a project.
        
        Args:
            project_path: Path to the project to analyze
            
        Returns:
            Architecture analysis results
        """
        project_root = Path(project_path)
        if not project_root.exists():
            return {"error": f"Project path does not exist: {project_path}"}
        
        analysis = {
            "structure": self._analyze_project_structure(project_root),
            "patterns_detected": [],
            "coupling_score": 0.0,
            "cohesion_score": 0.0,
            "modularity_score": 0.0,
        }
        
        # Detect architectural patterns
        analysis["patterns_detected"] = self._detect_patterns(project_root)
        
        # Calculate metrics
        analysis["coupling_score"] = self._calculate_coupling(project_root)
        analysis["cohesion_score"] = self._calculate_coherence(project_root)
        analysis["modularity_score"] = self._calculate_modularity(project_root)
        
        return analysis

    def design_component(
        self,
        name: str,
        responsibilities: list[str],
        dependencies: Optional[list[str]] = None,
        interfaces: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """
        Design a software component.
        
        Args:
            name: Component name
            responsibilities: List of responsibilities
            dependencies: List of component dependencies
            interfaces: List of interfaces to implement
            
        Returns:
            Component design specification
        """
        design = {
            "name": name,
            "type": "component",
            "responsibilities": responsibilities,
            "dependencies": dependencies or [],
            "interfaces": interfaces or [],
            "properties": {
                "stateless": len(dependencies or []) == 0,
                "testable": True,
                "reusable": len(interfaces or []) > 0,
            },
            "recommended_pattern": self._suggest_pattern(responsibilities),
        }
        
        return design

    def evaluate_technology(
        self,
        technology: str,
        use_case: str,
        criteria: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """
        Evaluate a technology for a specific use case.
        
        Args:
            technology: Name of the technology
            use_case: Intended use case
            criteria: Evaluation criteria
            
        Returns:
            Technology evaluation results
        """
        eval_criteria = criteria or [
            "performance",
            "scalability",
            "community_support",
            "learning_curve",
            "cost",
            "maintenance",
        ]
        
        evaluation = {
            "technology": technology,
            "use_case": use_case,
            "scores": {},
            "recommendation": "neutral",
            "alternatives": [],
            "risks": [],
        }
        
        # Score each criterion (placeholder - would use LLM for real evaluation)
        for criterion in eval_criteria:
            evaluation["scores"][criterion] = 7.5  # Default moderate score
        
        # Calculate overall recommendation
        avg_score = sum(evaluation["scores"].values()) / len(evaluation["scores"])
        if avg_score >= 8:
            evaluation["recommendation"] = "recommended"
        elif avg_score >= 6:
            evaluation["recommendation"] = "acceptable"
        else:
            evaluation["recommendation"] = "not_recommended"
            evaluation["risks"].append("Low overall suitability score")
        
        return evaluation

    def identify_tech_debt(
        self,
        file_path: str,
        category: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """
        Identify technical debt in code.
        
        Args:
            file_path: Path to the file to analyze
            category: Optional category filter
            
        Returns:
            List of technical debt items
        """
        debt_items = []
        file_path_obj = Path(file_path)
        
        if not file_path_obj.exists():
            return [{"error": f"File not found: {file_path}"}]
        
        try:
            with open(file_path_obj, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                lines = content.split("\n")
        except Exception as e:
            return [{"error": f"Failed to read file: {e}"}]
        
        # Detect common code smells
        debt_items.extend(self._detect_long_methods(lines, file_path))
        debt_items.extend(self._detect_duplicate_code(content, file_path))
        debt_items.extend(self._detect_god_classes(lines, file_path))
        debt_items.extend(self._detect_magic_numbers(lines, file_path))
        debt_items.extend(self._detect_missing_docs(lines, file_path))
        
        if category:
            debt_items = [item for item in debt_items if item.get("category") == category]
        
        return debt_items

    def create_architecture_diagram(
        self,
        components: list[dict[str, Any]],
        relationships: list[dict[str, Any]],
        output_format: str = "mermaid",
    ) -> str:
        """
        Create an architecture diagram.
        
        Args:
            components: List of component definitions
            relationships: List of relationships between components
            output_format: Output format (mermaid, dot, plantuml)
            
        Returns:
            Diagram definition in specified format
        """
        if output_format == "mermaid":
            return self._generate_mermaid_diagram(components, relationships)
        elif output_format == "dot":
            return self._generate_dot_diagram(components, relationships)
        elif output_format == "plantuml":
            return self._generate_plantuml_diagram(components, relationships)
        else:
            raise ValueError(f"Unsupported format: {output_format}")

    # Private helper methods
    
    async def _assess_current_architecture(self) -> dict[str, Any]:
        """Assess the current state of the architecture."""
        return {
            "quality_score": 75.0,
            "maintainability": "good",
            "scalability": "moderate",
            "security": "good",
            "performance": "good",
        }

    async def _identify_architectural_smells(self) -> list[str]:
        """Identify architectural smells in the codebase."""
        return [
            "Consider adding caching layer for frequently accessed data",
            "API rate limiting should be implemented",
            "Database connection pooling could be optimized",
        ]

    async def _assess_scalability(self) -> dict[str, Any]:
        """Assess scalability of the current architecture."""
        return {
            "current_capacity": "medium",
            "bottlenecks": ["database connections", "single points of failure"],
            "concerns": [
                "No horizontal scaling strategy detected",
                "Stateful services may limit scaling",
            ],
            "recommendations": [
                "Implement load balancing",
                "Add caching layer",
                "Consider microservices decomposition",
            ],
        }

    async def _design_component(self, task: Task) -> str:
        """Design a component based on task requirements."""
        name = task.context.get("component_name", "NewComponent")
        responsibilities = task.context.get("responsibilities", ["Handle requests"])
        
        design = self.design_component(
            name=name,
            responsibilities=responsibilities,
        )
        
        return f"Component Design for {name}:\n{design}"

    async def _design_api(self, task: Task) -> str:
        """Design an API based on task requirements."""
        return "API Design specification would be generated here"

    async def _design_database(self, task: Task) -> str:
        """Design a database schema based on task requirements."""
        return "Database schema design would be generated here"

    async def _create_architecture(self, task: Task) -> str:
        """Create a full architecture design."""
        return "Full architecture design would be generated here"

    async def _check_design_principles(self, task: Task) -> dict[str, Any]:
        """Check adherence to design principles."""
        return {
            "violations": [],
            "suggestions": [
                "Consider applying SOLID principles more consistently",
                "Add more abstraction layers for better testability",
            ],
        }

    async def _validate_requirements(self, task: Task) -> dict[str, Any]:
        """Validate design against requirements."""
        return {
            "met": True,
            "gaps": [],
        }

    def _analyze_project_structure(self, project_root: Path) -> dict[str, Any]:
        """Analyze the directory structure of a project."""
        structure = {
            "directories": [],
            "files_by_type": {},
            "depth": 0,
        }
        
        max_depth = 0
        for root, dirs, files in walk_safe(project_root):
            depth = root.replace(str(project_root), "").count("/")
            max_depth = max(max_depth, depth)
            
            for d in dirs:
                structure["directories"].append(Path(root).relative_to(project_root) / d)
            
            for f in files:
                ext = Path(f).suffix.lower()
                structure["files_by_type"][ext] = structure["files_by_type"].get(ext, 0) + 1
        
        structure["depth"] = max_depth
        return structure

    def _detect_patterns(self, project_root: Path) -> list[str]:
        """Detect architectural patterns in the codebase."""
        patterns = []
        
        # Check for MVC pattern
        if any((project_root / d).exists() for d in ["controllers", "views", "models"]):
            patterns.append("MVC")
        
        # Check for layered architecture
        if any((project_root / d).exists() for d in ["api", "service", "repository", "domain"]):
            patterns.append("Layered Architecture")
        
        # Check for microservices indicators
        docker_files = list(project_root.glob("**/docker-compose.yml"))
        if docker_files:
            patterns.append("Microservices (potential)")
        
        return patterns

    def _calculate_coupling(self, project_root: Path) -> float:
        """Calculate coupling score (0-10, lower is better)."""
        # Placeholder implementation
        return 4.5

    def _calculate_coherence(self, project_root: Path) -> float:
        """Calculate cohesion score (0-10, higher is better)."""
        # Placeholder implementation
        return 7.0

    def _calculate_modularity(self, project_root: Path) -> float:
        """Calculate modularity score (0-10, higher is better)."""
        # Placeholder implementation
        return 6.5

    def _suggest_pattern(self, responsibilities: list[str]) -> str:
        """Suggest a design pattern based on responsibilities."""
        resp_str = " ".join(responsibilities).lower()
        
        if "create" in resp_str and "object" in resp_str:
            return "Factory Pattern"
        elif "notify" in resp_str or "event" in resp_str:
            return "Observer Pattern"
        elif "strategy" in resp_str or "algorithm" in resp_str:
            return "Strategy Pattern"
        elif "single" in resp_str or "instance" in resp_str:
            return "Singleton Pattern"
        else:
            return "Component Pattern"

    def _detect_long_methods(self, lines: list[str], file_path: str) -> list[dict]:
        """Detect methods that are too long."""
        debts = []
        method_start = None
        method_lines = 0
        
        for i, line in enumerate(lines):
            if "def " in line or "function " in line:
                if method_start is not None and method_lines > 50:
                    debts.append({
                        "title": "Long Method",
                        "description": f"Method exceeds 50 lines ({method_lines} lines)",
                        "category": "code_smell",
                        "file_path": file_path,
                        "line_number": method_start + 1,
                        "severity": "medium",
                        "suggestion": "Break down into smaller, focused methods",
                    })
                method_start = i
                method_lines = 0
            method_lines += 1
        
        # Check last method
        if method_start is not None and method_lines > 50:
            debts.append({
                "title": "Long Method",
                "description": f"Method exceeds 50 lines ({method_lines} lines)",
                "category": "code_smell",
                "file_path": file_path,
                "line_number": method_start + 1,
                "severity": "medium",
                "suggestion": "Break down into smaller, focused methods",
            })
        
        return debts

    def _detect_duplicate_code(self, content: str, file_path: str) -> list[dict]:
        """Detect duplicate code blocks."""
        # Simple placeholder - would use more sophisticated detection in production
        return []

    def _detect_god_classes(self, lines: list[str], file_path: str) -> list[dict]:
        """Detect god classes (classes with too many responsibilities)."""
        debts = []
        
        for i, line in enumerate(lines):
            if "class " in line:
                # Count methods in class (simplified)
                method_count = sum(1 for l in lines[i:i+500] if "def " in l)
                if method_count > 20:
                    debts.append({
                        "title": "God Class",
                        "description": f"Class has {method_count} methods, consider splitting",
                        "category": "code_smell",
                        "file_path": file_path,
                        "line_number": i + 1,
                        "severity": "high",
                        "suggestion": "Split into multiple focused classes",
                    })
        
        return debts

    def _detect_magic_numbers(self, lines: list[str], file_path: str) -> list[dict]:
        """Detect magic numbers in code."""
        debts = []

        for i, line in enumerate(lines):
            stripped = line.strip()
            # Skip full-line comments
            if stripped.startswith("#"):
                continue
            # Strip inline comments and string literals for analysis
            code_part = stripped.split("#")[0]  # Remove inline comment
            # Only check lines that look like code (have an assignment, operator, or function call)
            if not any(op in code_part for op in ("=", "(", ")", "+", "-", "*", "/", ">", "<", "!", "return", "if ", "elif ", "while ", "for ")):
                continue

            # Look for numeric literals in code (not inside strings)
            # Remove string contents first
            code_only = re.sub(r'["\'].*?["\']', '', code_part)
            numbers = re.findall(r'\b\d+\b', code_only)
            for num in numbers:
                if num not in ["0", "1", "2"]:  # Common acceptable values
                    debts.append({
                        "title": "Magic Number",
                        "description": f"Hardcoded value {num} should be a named constant",
                        "category": "code_smell",
                        "file_path": file_path,
                        "line_number": i + 1,
                        "severity": "low",
                        "suggestion": "Extract to a named constant",
                    })
                    break  # One per line is enough
        
        return debts[:5]  # Limit to first 5

    def _detect_missing_docs(self, lines: list[str], file_path: str) -> list[dict]:
        """Detect functions/classes missing documentation."""
        debts = []
        
        for i, line in enumerate(lines):
            if ("def " in line or "class " in line) and i < len(lines) - 1:
                next_line = lines[i + 1].strip()
                if not (next_line.startswith('"""') or next_line.startswith("'''")):
                    entity_type = "Function" if "def " in line else "Class"
                    debts.append({
                        "title": "Missing Documentation",
                        "description": f"{entity_type} lacks docstring",
                        "category": "documentation",
                        "file_path": file_path,
                        "line_number": i + 1,
                        "severity": "low",
                        "suggestion": "Add descriptive docstring",
                    })
        
        return debts[:10]  # Limit to first 10

    def _generate_mermaid_diagram(
        self,
        components: list[dict[str, Any]],
        relationships: list[dict[str, Any]],
    ) -> str:
        """Generate Mermaid diagram syntax."""
        lines = ["graph TD"]
        
        for comp in components:
            name = comp.get("name", "Unknown")
            label = comp.get("label", name)
            lines.append(f"    {name}[{label}]")
        
        for rel in relationships:
            source = rel.get("source", "")
            target = rel.get("target", "")
            rel_type = rel.get("type", "-->")
            lines.append(f"    {source} {rel_type} {target}")
        
        return "\n".join(lines)

    def _generate_dot_diagram(
        self,
        components: list[dict[str, Any]],
        relationships: list[dict[str, Any]],
    ) -> str:
        """Generate GraphViz DOT syntax."""
        lines = ["digraph Architecture {"]
        lines.append("    rankdir=LR;")
        
        for comp in components:
            name = comp.get("name", "Unknown")
            label = comp.get("label", name)
            lines.append(f'    "{name}" [label="{label}"];')
        
        for rel in relationships:
            source = rel.get("source", "")
            target = rel.get("target", "")
            lines.append(f'    "{source}" -> "{target}";')
        
        lines.append("}")
        return "\n".join(lines)

    def _generate_plantuml_diagram(
        self,
        components: list[dict[str, Any]],
        relationships: list[dict[str, Any]],
    ) -> str:
        """Generate PlantUML syntax."""
        lines = ["@startuml"]
        
        for comp in components:
            name = comp.get("name", "Unknown")
            label = comp.get("label", name)
            lines.append(f"    component [{label}] as {name}")
        
        for rel in relationships:
            source = rel.get("source", "")
            target = rel.get("target", "")
            lines.append(f"    {source} --> {target}")
        
        lines.append("@enduml")
        return "\n".join(lines)


# Helper function to safely walk directories
def walk_safe(root: Path):
    """Safely walk directory tree, skipping problematic directories."""
    skip_dirs = {".git", "node_modules", "__pycache__", "venv", ".venv", "dist", "build"}
    
    for dirpath, dirnames, filenames in os.walk(root):
        # Remove skip directories in-place to prevent descending
        dirnames[:] = [d for d in dirnames if d not in skip_dirs and not d.startswith(".")]
        yield dirpath, dirnames, filenames



