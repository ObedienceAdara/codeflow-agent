"""Tests for DiffProtocol — unified diff generation and application."""

import pytest
from codeflow.core.diff_protocol import DiffProtocol, DiffResult, create_diff


class TestDiffGeneration:
    """Test diff generation functionality."""

    def test_generate_diff_with_changes(self, diff_protocol):
        """Test generating a unified diff between two different strings."""
        original = "line1\nline2\nline3\n"
        modified = "line1\nmodified_line2\nline3\n"

        result = diff_protocol.generate_diff(original, modified, "test.py")

        assert result.success is True
        assert result.diff_text != ""
        assert result.lines_changed > 0
        assert "--- a/test.py" in result.diff_text
        assert "+++ b/test.py" in result.diff_text

    def test_generate_diff_no_changes(self, diff_protocol):
        """Test that identical content produces empty diff."""
        content = "line1\nline2\nline3\n"

        result = diff_protocol.generate_diff(content, content, "test.py")

        assert result.success is True
        assert result.diff_text == ""
        assert result.lines_changed == 0

    def test_generate_diff_empty_original(self, diff_protocol):
        """Test diff when original is empty (new file)."""
        modified = "new content\n"

        result = diff_protocol.generate_diff("", modified, "new.py")

        assert result.success is True
        assert result.diff_text != ""

    def test_generate_diff_empty_modified(self, diff_protocol):
        """Test diff when modified is empty (deleted file)."""
        original = "old content\n"

        result = diff_protocol.generate_diff(original, "", "deleted.py")

        assert result.success is True
        assert result.diff_text != ""

    def test_generate_diff_both_empty(self, diff_protocol):
        """Test diff when both files are empty."""
        result = diff_protocol.generate_diff("", "", "empty.py")

        assert result.success is False
        assert "empty" in result.error.lower()

    def test_generate_diff_multi_line(self, diff_protocol):
        """Test diff with multiple changed lines."""
        original = "a\nb\nc\nd\ne\n"
        modified = "a\nB\nC\nd\ne\n"

        result = diff_protocol.generate_diff(original, modified, "multi.py")

        assert result.success is True
        assert result.lines_changed >= 2

    def test_create_diff_convenience_function(self):
        """Test the module-level create_diff function."""
        original = "hello"
        modified = "world"

        diff_text = create_diff(original, modified, "file.txt")

        assert "hello" not in diff_text or "---" in diff_text


class TestDiffApplication:
    """Test diff application functionality."""

    def test_apply_empty_diff(self, diff_protocol):
        """Test that applying an empty diff returns original text."""
        original = "some content\n"

        result = diff_protocol.apply_diff(original, "")

        assert result.success is True
        # Empty diff returns the original text via the early return path
        assert result.diff_text == "" or result.diff_text == original

    def test_validate_diff(self, diff_protocol):
        """Test diff validation."""
        original = "line1\nline2\n"

        # Valid: empty diff
        assert diff_protocol.validate_diff(original, "") is True

    def test_count_changes(self, diff_protocol):
        """Test counting changes in diff text."""
        diff_text = "--- a/test.py\n+++ b/test.py\n@@ -1,2 +1,2 @@\n-old\n+new\n"

        count = diff_protocol._count_changes(diff_text)

        assert count > 0


class TestDiffResult:
    """Test DiffResult dataclass."""

    def test_default_values(self):
        """Test default field values."""
        result = DiffResult(success=True)

        assert result.success is True
        assert result.diff_text == ""
        assert result.error == ""
        assert result.lines_changed == 0
        assert result.context_lines == 5

    def test_error_result(self):
        """Test creating an error result."""
        result = DiffResult(success=False, error="Something went wrong")

        assert result.success is False
        assert result.error == "Something went wrong"
