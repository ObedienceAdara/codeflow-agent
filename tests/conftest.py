"""Shared fixtures for CodeFlow tests."""

import pytest
from pathlib import Path

from codeflow.config.settings import CodeFlowConfig
from codeflow.core.diff_protocol import DiffProtocol
from codeflow.core.knowledge_graph import KnowledgeGraph
from codeflow.core.sandbox import DockerSandboxExecutor
from codeflow.core.tree_sitter_parser import TreeSitterParser
from codeflow.models.entities import (
    CodeEntity,
    CodeEntityType,
    Relationship,
    RelationshipType,
    Task,
    TaskPriority,
    TaskStatus,
    AgentType,
)


@pytest.fixture
def config():
    """Return a default CodeFlowConfig instance."""
    return CodeFlowConfig()


@pytest.fixture
def diff_protocol():
    """Return a DiffProtocol instance."""
    return DiffProtocol()


@pytest.fixture
def knowledge_graph():
    """Return an empty KnowledgeGraph."""
    return KnowledgeGraph()


@pytest.fixture
def sandbox(config):
    """Return a DockerSandboxExecutor."""
    return DockerSandboxExecutor(config)


@pytest.fixture
def tree_sitter_parser():
    """Return a TreeSitterParser."""
    return TreeSitterParser()


@pytest.fixture
def sample_code_entity():
    """Return a sample CodeEntity."""
    return CodeEntity(
        entity_type=CodeEntityType.FUNCTION,
        name="calculate_sum",
        file_path="test.py",
        line_start=1,
        line_end=5,
        content="def calculate_sum(a, b):\n    return a + b",
        language="python",
    )


@pytest.fixture
def sample_task():
    """Return a sample Task."""
    return Task(
        title="Test task",
        description="A task for testing",
        priority=TaskPriority.MEDIUM,
        context={"test": True},
    )


@pytest.fixture
def temp_project_dir(tmp_path):
    """Create a temporary project directory with sample files."""
    # Create Python file
    py_file = tmp_path / "sample.py"
    py_file.write_text(
        "import os\n"
        "import sys\n"
        "\n"
        "class MyClass:\n"
        "    def __init__(self):\n"
        "        self.value = 0\n"
        "\n"
        "    def do_something(self):\n"
        "        return self.value + 1\n"
        "\n"
        "def helper_function(x):\n"
        "    return x * 2\n"
    )

    # Create JS file
    js_file = tmp_path / "app.js"
    js_file.write_text(
        "const fs = require('fs');\n"
        "\n"
        "class App {\n"
        "    constructor() {\n"
        "        this.name = 'test';\n"
        "    }\n"
        "\n"
        "    run() {\n"
        "        console.log('running');\n"
        "    }\n"
        "}\n"
        "\n"
        "function main() {\n"
        "    const app = new App();\n"
        "    app.run();\n"
        "}\n"
    )

    # Create requirements.txt
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("requests==2.31.0\nflask>=2.0\n")

    return tmp_path
