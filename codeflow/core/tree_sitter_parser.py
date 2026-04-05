"""
Tree-sitter AST Parser for CodeFlow Agent.

Uses tree-sitter grammars to parse code into Abstract Syntax Trees,
enabling accurate extraction of code entities (classes, functions, imports)
and relationships without fragile regex.
"""

import logging
from pathlib import Path
from typing import Any, Optional

from ..models.entities import (
    CodeEntity,
    CodeEntityType,
)

logger = logging.getLogger(__name__)


class TreeSitterParser:
    """
    Parses code files using tree-sitter AST grammars.

    Supports Python, JavaScript, and TypeScript files.
    Falls back to regex-based parsing if tree-sitter is unavailable.

    Features:
    - Accurate entity extraction via AST traversal
    - Proper handling of nested classes/functions
    - Import/module dependency detection
    - Language-specific node type mappings
    """

    def __init__(self):
        self._parsers: dict[str, Any] = {}
        self._available: dict[str, bool] = {}
        self._initialize_parsers()

    def _initialize_parsers(self) -> None:
        """Initialize tree-sitter parsers for supported languages."""
        try:
            import tree_sitter_python
            import tree_sitter_javascript
            import tree_sitter_typescript

            from tree_sitter import Language, Parser

            # Python
            python_lang = Language(tree_sitter_python.language())
            python_parser = Parser(python_lang)
            self._parsers["python"] = python_parser
            self._available["python"] = True

            # JavaScript
            js_lang = Language(tree_sitter_javascript.language())
            js_parser = Parser(js_lang)
            self._parsers["javascript"] = js_parser
            self._available["javascript"] = True

            # TypeScript
            ts_lang = Language(tree_sitter_typescript.language_typescript())
            ts_parser = Parser(ts_lang)
            self._parsers["typescript"] = ts_parser
            self._available["typescript"] = True

            logger.info(
                f"Tree-sitter parsers initialized: {list(self._available.keys())}"
            )

        except ImportError:
            logger.debug(
                "Tree-sitter not installed. "
                "Run: pip install tree-sitter tree-sitter-python "
                "tree-sitter-javascript tree-sitter-typescript"
            )
            self._available = {
                "python": False,
                "javascript": False,
                "typescript": False,
            }

    def is_available(self, language: str) -> bool:
        """Check if tree-sitter parser is available for a language."""
        return self._available.get(language, False)

    def parse_file(
        self, content: str, file_path: str, language: str
    ) -> list[CodeEntity]:
        """
        Parse a code file using tree-sitter AST.

        Args:
            content: File content as string
            file_path: Relative path to the file
            language: Language identifier (python, javascript, typescript)

        Returns:
            List of CodeEntity objects extracted from the AST
        """
        # Normalize language
        lang_map = {
            "py": "python",
            "js": "javascript",
            "jsx": "javascript",
            "ts": "typescript",
            "tsx": "typescript",
        }
        normalized = lang_map.get(language, language)

        # Try tree-sitter first
        if self._available.get(normalized, False):
            try:
                return self._parse_with_treesitter(content, file_path, normalized)
            except Exception as e:
                logger.warning(
                    f"Tree-sitter parsing failed for {file_path}: {e}. "
                    "Falling back to regex."
                )

        # Fallback: return empty list — caller should use regex fallback
        return []

    def _parse_with_treesitter(
        self, content: str, file_path: str, language: str
    ) -> list[CodeEntity]:
        """Parse code using tree-sitter AST."""
        parser = self._parsers[language]
        if isinstance(content, str):
            content_bytes = content.encode("utf-8")
        else:
            content_bytes = content

        tree = parser.parse(content_bytes)
        root = tree.root_node

        entities: list[CodeEntity] = []
        lines = content.splitlines()

        if language == "python":
            self._extract_python_entities(root, content_bytes, file_path, lines, entities)
        elif language in ("javascript", "typescript"):
            self._extract_js_ts_entities(root, content_bytes, file_path, lines, entities)

        return entities

    def _extract_python_entities(
        self,
        node: Any,
        content_bytes: bytes,
        file_path: str,
        lines: list[str],
        entities: list[CodeEntity],
        parent_type: Optional[str] = None,
    ) -> None:
        """Recursively extract Python entities from AST."""
        if node.type == "class_definition":
            name = self._get_python_node_name(node)
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1
            content_text = content_bytes[
                node.start_byte : node.end_byte
            ].decode("utf-8", errors="replace")

            entities.append(CodeEntity(
                entity_type=CodeEntityType.CLASS,
                name=name,
                file_path=file_path,
                line_start=start_line,
                line_end=end_line,
                content=content_text,
                language="python",
                metadata={"parent_type": parent_type} if parent_type else {},
            ))

            # Recurse into class body for methods
            for child in node.children:
                self._extract_python_entities(
                    child, content_bytes, file_path, lines, entities,
                    parent_type=name,
                )

        elif node.type == "function_definition":
            name = self._get_python_node_name(node)
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1
            content_text = content_bytes[
                node.start_byte : node.end_byte
            ].decode("utf-8", errors="replace")

            entity_type = (
                CodeEntityType.METHOD
                if parent_type
                else CodeEntityType.FUNCTION
            )
            entities.append(CodeEntity(
                entity_type=entity_type,
                name=name,
                file_path=file_path,
                line_start=start_line,
                line_end=end_line,
                content=content_text,
                language="python",
                metadata={"parent_type": parent_type} if parent_type else {},
            ))

        elif node.type == "import_statement" or node.type == "import_from_statement":
            self._extract_python_imports(node, file_path, lines, entities)
        else:
            # Only recurse into children for nodes not handled above
            for child in node.children:
                self._extract_python_entities(
                    child, content_bytes, file_path, lines, entities,
                    parent_type=parent_type,
                )

    def _get_python_node_name(self, node: Any) -> str:
        """Extract name from a Python AST node."""
        for child in node.children:
            if child.type == "identifier":
                return child.text.decode("utf-8", errors="replace")
        return "unknown"

    def _extract_python_imports(
        self,
        node: Any,
        file_path: str,
        lines: list[str],
        entities: list[CodeEntity],
    ) -> None:
        """Extract import statements as entities."""
        start_line = node.start_point[0] + 1
        content_text = node.text.decode("utf-8", errors="replace")

        # Extract imported names
        for child in node.children:
            if child.type == "dotted_name":
                name = child.text.decode("utf-8", errors="replace")
                entities.append(CodeEntity(
                    entity_type=CodeEntityType.IMPORT,
                    name=name,
                    file_path=file_path,
                    line_start=start_line,
                    line_end=start_line,
                    content=content_text,
                    language="python",
                ))
            elif child.type == "aliased_import":
                for sub in child.children:
                    if sub.type == "identifier":
                        name = sub.text.decode("utf-8", errors="replace")
                        entities.append(CodeEntity(
                            entity_type=CodeEntityType.IMPORT,
                            name=name,
                            file_path=file_path,
                            line_start=start_line,
                            line_end=start_line,
                            content=content_text,
                            language="python",
                        ))

    def _extract_js_ts_entities(
        self,
        node: Any,
        content_bytes: bytes,
        file_path: str,
        lines: list[str],
        entities: list[CodeEntity],
        parent_type: Optional[str] = None,
    ) -> None:
        """Recursively extract JavaScript/TypeScript entities from AST."""
        node_type = node.type

        if node_type == "class_declaration":
            name = self._get_js_ts_node_name(node)
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1
            content_text = content_bytes[
                node.start_byte : node.end_byte
            ].decode("utf-8", errors="replace")

            entities.append(CodeEntity(
                entity_type=CodeEntityType.CLASS,
                name=name,
                file_path=file_path,
                line_start=start_line,
                line_end=end_line,
                content=content_text,
                language="javascript",
                metadata={"parent_type": parent_type} if parent_type else {},
            ))

            # Recurse into class body
            for child in node.children:
                self._extract_js_ts_entities(
                    child, content_bytes, file_path, lines, entities,
                    parent_type=name,
                )

        elif node_type == "function_declaration" or node_type == "method_definition":
            name = self._get_js_ts_node_name(node)
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1
            content_text = content_bytes[
                node.start_byte : node.end_byte
            ].decode("utf-8", errors="replace")

            entity_type = (
                CodeEntityType.METHOD
                if parent_type or node_type == "method_definition"
                else CodeEntityType.FUNCTION
            )
            entities.append(CodeEntity(
                entity_type=entity_type,
                name=name,
                file_path=file_path,
                line_start=start_line,
                line_end=end_line,
                content=content_text,
                language="javascript",
                metadata={"parent_type": parent_type} if parent_type else {},
            ))

        elif node_type == "lexical_declaration" or node_type == "variable_declaration":
            # Check for arrow/regular function assignments
            for child in node.children:
                if child.type == "variable_declarator":
                    name = self._get_js_ts_node_name(child)
                    # Check if value is a function
                    for sub in child.children:
                        if sub.type in ("arrow_function", "function"):
                            start_line = node.start_point[0] + 1
                            end_line = node.end_point[0] + 1
                            content_text = content_bytes[
                                node.start_byte : node.end_byte
                            ].decode("utf-8", errors="replace")
                            entities.append(CodeEntity(
                                entity_type=CodeEntityType.FUNCTION,
                                name=name,
                                file_path=file_path,
                                line_start=start_line,
                                line_end=end_line,
                                content=content_text,
                                language="javascript",
                            ))

        elif node_type == "import_statement":
            start_line = node.start_point[0] + 1
            content_text = node.text.decode("utf-8", errors="replace")
            name = content_text[:100]  # Truncate for storage
            entities.append(CodeEntity(
                entity_type=CodeEntityType.IMPORT,
                name=name,
                file_path=file_path,
                line_start=start_line,
                line_end=start_line,
                content=content_text,
                language="javascript",
            ))
        else:
            # Only recurse into children for nodes not handled above
            for child in node.children:
                self._extract_js_ts_entities(
                    child, content_bytes, file_path, lines, entities,
                    parent_type=parent_type,
                )

    def _get_js_ts_node_name(self, node: Any) -> str:
        """Extract name from a JS/TS AST node."""
        for child in node.children:
            if child.type == "identifier" or child.type == "property_identifier":
                return child.text.decode("utf-8", errors="replace")
            if child.type == "variable_declarator":
                return self._get_js_ts_node_name(child)
        return "unknown"
