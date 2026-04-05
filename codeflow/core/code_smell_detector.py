"""
Shared Code Smell Detector for CodeFlow Agent.

Provides centralized code smell detection used by Architect, QA,
Reviewer, and Refactor agents to eliminate duplication.

All agents should import from this module instead of
implementing their own smell detection logic.
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class SmellCategory(Enum):
    """Categories of code smells."""
    COMPLEXITY = "complexity"
    SIZE = "size"
    NAMING = "naming"
    DUPLICATION = "duplication"
    DESIGN = "design"
    DOCUMENTATION = "documentation"


class Severity(Enum):
    """Severity of a code smell."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class CodeSmell:
    """A single detected code smell."""
    category: SmellCategory
    severity: Severity
    name: str
    description: str
    file_path: str
    line_start: int = 0
    line_end: int = 0
    suggestion: str = ""
    evidence: str = ""


@dataclass
class SmellConfig:
    """Configurable thresholds for code smell detection."""
    long_method_lines: int = 50
    large_file_lines: int = 500
    god_class_methods: int = 20
    max_nesting_depth: int = 5
    max_function_params: int = 5
    line_length_limit: int = 120
    max_duplicate_lines_percent: float = 10.0


class CodeSmellDetector:
    """
    Detects common code smells across multiple categories.

    Used by Architect, QA, Reviewer, and Refactor agents
    to provide consistent code quality analysis.
    """

    def __init__(self, config: Optional[SmellConfig] = None):
        self.config = config or SmellConfig()

    def detect_all(self, file_path: str, content: str) -> list[CodeSmell]:
        """
        Run all smell detectors on a file.

        Args:
            file_path: Path to the file
            content: File content

        Returns:
            List of detected code smells
        """
        smells: list[CodeSmell] = []
        lines = content.splitlines()

        smells.extend(self._detect_long_methods(file_path, lines))
        smells.extend(self._detect_large_files(file_path, lines))
        smells.extend(self._detect_god_classes(file_path, content))
        smells.extend(self._detect_magic_numbers(file_path, content))
        smells.extend(self._detect_missing_docstrings(file_path, content))
        smells.extend(self._detect_long_lines(file_path, lines))
        smells.extend(self._detect_naming_issues(file_path, content))

        return smells

    def _detect_long_methods(
        self, file_path: str, lines: list[str]
    ) -> list[CodeSmell]:
        """Detect methods exceeding the configured line threshold."""
        smells: list[CodeSmell] = []
        in_method = False
        method_start = 0
        method_name = ""
        method_lines = 0

        for i, line in enumerate(lines):
            stripped = line.strip()

            # Detect method definition
            if re.match(r"^(async\s+)?def\s+\w+\s*\(", stripped):
                # Save previous method if it was too long
                if in_method and method_lines > self.config.long_method_lines:
                    smells.append(CodeSmell(
                        category=SmellCategory.COMPLEXITY,
                        severity=Severity.HIGH if method_lines > self.config.long_method_lines * 2 else Severity.MEDIUM,
                        name="Long Method",
                        description=f"Method '{method_name}' has {method_lines} lines (threshold: {self.config.long_method_lines})",
                        file_path=file_path,
                        line_start=method_start,
                        line_end=i,
                        suggestion="Extract smaller helper methods to improve readability",
                    ))

                in_method = True
                method_start = i + 1
                method_name = re.search(r"def\s+(\w+)", stripped).group(1)
                method_lines = 0
            elif in_method:
                if stripped and not stripped.startswith("#"):
                    method_lines += 1
                # Check if method ended (next top-level def or EOF)
                if re.match(r"^(class |def |@)", stripped) and not stripped.startswith("    "):
                    in_method = False

        # Check last method
        if in_method and method_lines > self.config.long_method_lines:
            smells.append(CodeSmell(
                category=SmellCategory.COMPLEXITY,
                severity=Severity.MEDIUM,
                name="Long Method",
                description=f"Method '{method_name}' has {method_lines} lines (threshold: {self.config.long_method_lines})",
                file_path=file_path,
                line_start=method_start,
                line_end=len(lines),
                suggestion="Extract smaller helper methods to improve readability",
            ))

        return smells

    def _detect_large_files(
        self, file_path: str, lines: list[str]
    ) -> list[CodeSmell]:
        """Detect files exceeding the configured line threshold."""
        if len(lines) > self.config.large_file_lines:
            return [CodeSmell(
                category=SmellCategory.SIZE,
                severity=Severity.HIGH if len(lines) > self.config.large_file_lines * 2 else Severity.MEDIUM,
                name="Large File",
                description=f"File has {len(lines)} lines (threshold: {self.config.large_file_lines})",
                file_path=file_path,
                line_start=1,
                line_end=len(lines),
                suggestion="Split into multiple modules for better maintainability",
            )]
        return []

    def _detect_god_classes(
        self, file_path: str, content: str
    ) -> list[CodeSmell]:
        """Detect classes with too many methods (god class anti-pattern)."""
        smells: list[CodeSmell] = []
        # Match class definitions
        for match in re.finditer(r"^class\s+(\w+)", content, re.MULTILINE):
            class_name = match.group(1)
            class_start = match.start()
            # Count methods in this class
            # Find the class body content
            remaining = content[class_start:]
            methods = re.findall(r"^\s+def\s+(\w+)", remaining, re.MULTILINE)
            # Filter out dunder methods for a cleaner count
            real_methods = [m for m in methods if not m.startswith("__")]

            if len(real_methods) > self.config.god_class_methods:
                smells.append(CodeSmell(
                    category=SmellCategory.DESIGN,
                    severity=Severity.HIGH,
                    name="God Class",
                    description=f"Class '{class_name}' has {len(real_methods)} methods (threshold: {self.config.god_class_methods})",
                    file_path=file_path,
                    line_start=content[:class_start].count("\n") + 1,
                    suggestion="Split into smaller, focused classes following Single Responsibility Principle",
                ))

        return smells

    def _detect_magic_numbers(
        self, file_path: str, content: str
    ) -> list[CodeSmell]:
        """Detect hardcoded numeric literals (magic numbers)."""
        smells: list[CodeSmell] = []
        acceptable = {"0", "1", "-1", "0.0", "1.0", "2", "100", "1000"}

        for i, line in enumerate(content.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("import"):
                continue
            # Find numeric literals
            numbers = re.findall(r"(?<![a-zA-Z_\.\"])\\b(\\d+\\.?\\d*)\\b", stripped)
            for num in numbers:
                if num not in acceptable:
                    smells.append(CodeSmell(
                        category=SmellCategory.NAMING,
                        severity=Severity.LOW,
                        name="Magic Number",
                        description=f"Magic number '{num}' found on line {i}",
                        file_path=file_path,
                        line_start=i,
                        evidence=stripped,
                        suggestion=f"Extract '{num}' into a named constant",
                    ))

        return smells

    def _detect_missing_docstrings(
        self, file_path: str, content: str
    ) -> list[CodeSmell]:
        """Detect functions and classes without docstrings."""
        smells: list[CodeSmell] = []
        lines = content.splitlines()

        for i, line in enumerate(lines):
            stripped = line.strip()
            # Check function definitions
            if re.match(r"^(async\s+)?def\s+\w+", stripped):
                # Look for docstring in next non-empty line
                has_docstring = False
                for j in range(i + 1, min(i + 4, len(lines))):
                    next_stripped = lines[j].strip()
                    if next_stripped:
                        if next_stripped.startswith('"""') or next_stripped.startswith("'''"):
                            has_docstring = True
                        break
                if not has_docstring:
                    func_name = re.search(r"def\s+(\w+)", stripped).group(1)
                    smells.append(CodeSmell(
                        category=SmellCategory.DOCUMENTATION,
                        severity=Severity.LOW,
                        name="Missing Docstring",
                        description=f"Function '{func_name}' lacks a docstring",
                        file_path=file_path,
                        line_start=i + 1,
                        suggestion="Add a docstring describing the function's purpose, parameters, and return value",
                    ))

            # Check class definitions
            if re.match(r"^class\s+\w+", stripped):
                has_docstring = False
                for j in range(i + 1, min(i + 4, len(lines))):
                    next_stripped = lines[j].strip()
                    if next_stripped:
                        if next_stripped.startswith('"""') or next_stripped.startswith("'''"):
                            has_docstring = True
                        break
                if not has_docstring:
                    class_name = re.search(r"class\s+(\w+)", stripped).group(1)
                    smells.append(CodeSmell(
                        category=SmellCategory.DOCUMENTATION,
                        severity=Severity.LOW,
                        name="Missing Docstring",
                        description=f"Class '{class_name}' lacks a docstring",
                        file_path=file_path,
                        line_start=i + 1,
                        suggestion="Add a class docstring describing its purpose and responsibilities",
                    ))

        return smells

    def _detect_long_lines(
        self, file_path: str, lines: list[str]
    ) -> list[CodeSmell]:
        """Detect lines exceeding the configured length limit."""
        smells: list[CodeSmell] = []
        for i, line in enumerate(lines, 1):
            if len(line.rstrip()) > self.config.line_length_limit:
                smells.append(CodeSmell(
                    category=SmellCategory.SIZE,
                    severity=Severity.LOW,
                    name="Line Too Long",
                    description=f"Line {i} has {len(line.rstrip())} characters (limit: {self.config.line_length_limit})",
                    file_path=file_path,
                    line_start=i,
                    suggestion="Break the line into multiple lines or use line continuation",
                ))
        return smells

    def _detect_naming_issues(
        self, file_path: str, content: str
    ) -> list[CodeSmell]:
        """Detect naming convention issues."""
        smells: list[CodeSmell] = []

        # Detect single-letter variable names (except in loops)
        for i, line in enumerate(content.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("import"):
                continue
            # Match assignments with single-letter names (excluding common patterns)
            matches = re.findall(r"\b([a-z])\s*=\s*(?!for)", stripped)
            for var in matches:
                if var not in ("x", "y", "i", "j", "k", "f", "e", "_"):
                    smells.append(CodeSmell(
                        category=SmellCategory.NAMING,
                        severity=Severity.LOW,
                        name="Single-Letter Variable",
                        description=f"Single-letter variable '{var}' on line {i}",
                        file_path=file_path,
                        line_start=i,
                        evidence=stripped,
                        suggestion="Use a descriptive variable name",
                    ))

        return smells
