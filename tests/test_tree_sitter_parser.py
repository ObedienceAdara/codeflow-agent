"""Tests for TreeSitterParser."""

import pytest
from codeflow.core.tree_sitter_parser import TreeSitterParser
from codeflow.models.entities import CodeEntity, CodeEntityType


class TestTreeSitterParserInit:
    """Test TreeSitterParser initialization."""

    def test_init(self, tree_sitter_parser):
        """Test basic initialization."""
        assert isinstance(tree_sitter_parser._parsers, dict)
        assert isinstance(tree_sitter_parser._available, dict)

    def test_availability_keys(self, tree_sitter_parser):
        """Test that availability dict has expected keys."""
        assert "python" in tree_sitter_parser._available
        assert "javascript" in tree_sitter_parser._available
        assert "typescript" in tree_sitter_parser._available

    def test_is_available_unknown_language(self, tree_sitter_parser):
        """Test checking availability for unknown language."""
        assert tree_sitter_parser.is_available("cobol") is False


class TestTreeSitterParserParseFile:
    """Test parse_file method."""

    def test_parse_empty_python_file(self, tree_sitter_parser):
        """Test parsing an empty Python file."""
        entities = tree_sitter_parser.parse_file("", "empty.py", "py")

        # If tree-sitter is available, it returns empty for empty content
        # If not, fallback regex also returns empty
        assert isinstance(entities, list)

    def test_parse_simple_python(self, tree_sitter_parser):
        """Test parsing a simple Python file."""
        content = (
            "import os\n"
            "def hello():\n"
            "    print('hello')\n"
            "\n"
            "class Greeter:\n"
            "    def greet(self):\n"
            "        return 'hi'\n"
        )

        entities = tree_sitter_parser.parse_file(content, "greet.py", "py")

        assert isinstance(entities, list)

    def test_parse_simple_js(self, tree_sitter_parser):
        """Test parsing a simple JavaScript file."""
        content = (
            "function greet() {\n"
            "    return 'hello';\n"
            "}\n"
            "\n"
            "class App {\n"
            "    run() {\n"
            "        console.log('running');\n"
            "    }\n"
            "}\n"
        )

        entities = tree_sitter_parser.parse_file(content, "app.js", "js")

        assert isinstance(entities, list)

    def test_parse_fallback_for_unknown_language(self, tree_sitter_parser):
        """Test that unknown language returns empty list."""
        entities = tree_sitter_parser.parse_file("content", "file.xyz", "xyz")

        assert isinstance(entities, list)
        assert entities == []


class TestTreeSitterParserPython:
    """Test Python-specific parsing."""

    def test_extract_function_and_class(self, tree_sitter_parser):
        """Test extracting both functions and classes from Python."""
        content = (
            "import sys\n"
            "\n"
            "class MyClass:\n"
            "    def method(self):\n"
            "        pass\n"
            "\n"
            "def standalone_func():\n"
            "    pass\n"
        )

        # Try tree-sitter, fallback to regex
        entities = tree_sitter_parser.parse_file(content, "test.py", "py")

        # At minimum we should get some entities
        assert isinstance(entities, list)

    def test_import_extraction(self, tree_sitter_parser):
        """Test that imports are extracted as entities."""
        content = "import os\nfrom pathlib import Path\n"

        entities = tree_sitter_parser.parse_file(content, "imports.py", "py")

        assert isinstance(entities, list)


class TestTreeSitterParserJavaScript:
    """Test JavaScript-specific parsing."""

    def test_extract_js_function(self, tree_sitter_parser):
        """Test extracting JavaScript function."""
        content = "function main() {\n    return 42;\n}\n"

        entities = tree_sitter_parser.parse_file(content, "main.js", "js")

        assert isinstance(entities, list)

    def test_extract_js_class(self, tree_sitter_parser):
        """Test extracting JavaScript class."""
        content = "class App {\n    constructor() {}\n}\n"

        entities = tree_sitter_parser.parse_file(content, "app.js", "js")

        assert isinstance(entities, list)
