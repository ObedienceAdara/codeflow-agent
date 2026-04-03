"""
Diff Protocol for token-efficient code changes.

Implements unified diff generation and application with fuzzy matching
to handle line number shifts and whitespace differences.
"""

import difflib
import logging
import re
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class DiffResult:
    """Result of diff generation or application."""
    success: bool
    diff_text: str = ""
    error: str = ""
    lines_changed: int = 0
    context_lines: int = 5


class DiffProtocol:
    """
    Handles generation and application of unified diffs.
    
    Features:
    - Generates compact unified diffs instead of full files
    - Fuzzy patch matching for robust application
    - Self-validation before returning results
    - Configurable context window size
    """
    
    def __init__(self, context_lines: int = 5, max_retries: int = 3):
        """
        Initialize diff protocol.
        
        Args:
            context_lines: Number of context lines around changes
            max_retries: Maximum retries for failed diff application
        """
        self.context_lines = context_lines
        self.max_retries = max_retries
    
    def generate_diff(
        self, 
        original_text: str, 
        modified_text: str, 
        filename: str = "file.py"
    ) -> DiffResult:
        """
        Generate unified diff between original and modified text.
        
        Args:
            original_text: Original file content
            modified_text: Modified file content
            filename: Name of the file for diff header
            
        Returns:
            DiffResult with unified diff text
        """
        try:
            original_lines = original_text.splitlines(keepends=True)
            modified_lines = modified_text.splitlines(keepends=True)
            
            # Handle empty files
            if not original_lines and not modified_lines:
                return DiffResult(success=False, error="Both files are empty")
            
            diff = difflib.unified_diff(
                original_lines,
                modified_lines,
                fromfile=f"a/{filename}",
                tofile=f"b/{filename}",
                n=self.context_lines
            )
            
            diff_text = ''.join(diff)
            
            # Count changed lines
            lines_changed = sum(
                1 for line in diff_text.splitlines() 
                if line.startswith('+') or line.startswith('-')
            ) // 2  # Divide by 2 since each change has + and -
            
            if not diff_text.strip():
                return DiffResult(
                    success=True, 
                    diff_text="", 
                    lines_changed=0,
                    context_lines=self.context_lines
                )
            
            return DiffResult(
                success=True,
                diff_text=diff_text,
                lines_changed=max(1, lines_changed),
                context_lines=self.context_lines
            )
            
        except Exception as e:
            logger.error(f"Error generating diff: {e}")
            return DiffResult(success=False, error=str(e))
    
    def apply_diff(
        self, 
        original_text: str, 
        diff_text: str,
        filename: str = "file.py"
    ) -> DiffResult:
        """
        Apply unified diff to original text with fuzzy matching.
        
        Uses a multi-strategy approach:
        1. Try exact patch application
        2. Try fuzzy matching with context search
        3. Try line-by-line reconstruction
        
        Args:
            original_text: Original file content
            diff_text: Unified diff to apply
            filename: Name of the file for error messages
            
        Returns:
            DiffResult with modified text or error
        """
        if not diff_text.strip():
            return DiffResult(
                success=True,
                diff_text="",
                lines_changed=0
            )
        
        original_lines = original_text.splitlines(keepends=True)
        
        # Ensure lines end with newline for patch
        if original_lines and not original_lines[-1].endswith('\n'):
            original_lines[-1] += '\n'
        
        try:
            # Strategy 1: Try exact application using difflib
            result = self._apply_exact(original_lines, diff_text)
            if result[0]:
                return DiffResult(
                    success=True,
                    diff_text=''.join(result[1]),
                    lines_changed=self._count_changes(diff_text)
                )
            
            # Strategy 2: Fuzzy matching
            logger.debug(f"Exact match failed, trying fuzzy matching for {filename}")
            result = self._apply_fuzzy(original_text, diff_text)
            if result[0]:
                return DiffResult(
                    success=True,
                    diff_text=result[1],
                    lines_changed=self._count_changes(diff_text)
                )
            
            # Strategy 3: Manual patch application
            logger.debug(f"Fuzzy match failed, trying manual patch for {filename}")
            result = self._apply_manual(original_text, diff_text)
            if result[0]:
                return DiffResult(
                    success=True,
                    diff_text=result[1],
                    lines_changed=self._count_changes(diff_text)
                )
            
            return DiffResult(
                success=False,
                error="Failed to apply diff after multiple strategies"
            )
            
        except Exception as e:
            logger.error(f"Error applying diff: {e}")
            return DiffResult(success=False, error=str(e))
    
    def _apply_exact(self, original_lines: list, diff_text: str) -> tuple[bool, list]:
        """Try exact patch application."""
        try:
            # Parse diff and apply
            new_lines = self._parse_and_apply_patch(original_lines, diff_text)
            if new_lines is not None:
                return True, new_lines
            return False, []
        except Exception:
            return False, []
    
    def _apply_fuzzy(self, original_text: str, diff_text: str) -> tuple[bool, str]:
        """Apply diff with fuzzy context matching."""
        try:
            lines = original_text.splitlines(keepends=True)
            diff_lines = diff_text.splitlines(keepends=True)
            
            # Extract hunks from diff
            hunks = self._parse_hunks(diff_lines)
            
            # Apply each hunk with fuzzy matching
            offset = 0
            for hunk in hunks:
                applied = False
                search_range = max(10, self.context_lines * 2)
                
                # Try to find matching context within range
                for delta in range(-search_range, search_range + 1):
                    test_line = hunk['original_start'] + delta + offset
                    if test_line < 0 or test_line > len(lines):
                        continue
                    
                    if self._matches_context(lines, hunk, test_line):
                        # Apply the hunk
                        lines = self._apply_hunk(lines, hunk, test_line)
                        offset += hunk['added'] - hunk['removed']
                        applied = True
                        break
                
                if not applied:
                    return False, ""
            
            return True, ''.join(lines)
            
        except Exception as e:
            logger.debug(f"Fuzzy apply failed: {e}")
            return False, ""
    
    def _apply_manual(self, original_text: str, diff_text: str) -> tuple[bool, str]:
        """Manual line-by-line patch application."""
        try:
            lines = original_text.splitlines(keepends=True)
            diff_lines = diff_text.splitlines(keepends=True)
            
            # Simple replacement based on + and - lines
            result_lines = []
            skip_until = -1
            
            for i, line in enumerate(diff_lines):
                if line.startswith('@@'):
                    # Parse hunk header
                    match = re.search(r'\+(\d+)', line)
                    if match:
                        start = int(match.group(1)) - 1
                        result_lines = lines[:start]
                    continue
                
                if line.startswith('-'):
                    # Skip this line in original
                    continue
                elif line.startswith('+'):
                    # Add new line
                    result_lines.append(line[1:])
                elif not line.startswith('\\'):
                    # Context line
                    if len(result_lines) < len(lines):
                        result_lines.append(lines[len(result_lines)])
            
            if result_lines:
                return True, ''.join(result_lines)
            
            return False, ""
            
        except Exception as e:
            logger.debug(f"Manual apply failed: {e}")
            return False, ""
    
    def _parse_hunks(self, diff_lines: list) -> list[dict]:
        """Parse diff into hunks."""
        hunks = []
        current_hunk = None
        
        for line in diff_lines:
            if line.startswith('@@'):
                if current_hunk:
                    hunks.append(current_hunk)
                
                # Parse @@ -start,count +start,count @@
                match = re.match(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@', line)
                if match:
                    current_hunk = {
                        'original_start': int(match.group(1)) - 1,
                        'original_count': int(match.group(2)) if match.group(2) else 1,
                        'modified_start': int(match.group(3)) - 1,
                        'modified_count': int(match.group(4)) if match.group(4) else 1,
                        'changes': [],
                        'added': 0,
                        'removed': 0
                    }
            elif current_hunk:
                if line.startswith('-'):
                    current_hunk['changes'].append(('remove', line[1:]))
                    current_hunk['removed'] += 1
                elif line.startswith('+'):
                    current_hunk['changes'].append(('add', line[1:]))
                    current_hunk['added'] += 1
                elif not line.startswith('\\'):
                    current_hunk['changes'].append(('context', line))
        
        if current_hunk:
            hunks.append(current_hunk)
        
        return hunks
    
    def _matches_context(self, lines: list, hunk: dict, start_line: int) -> bool:
        """Check if context matches at given line position."""
        ctx_lines = [c for t, c in hunk['changes'] if t == 'context']
        
        if start_line + len(ctx_lines) > len(lines):
            return False
        
        for i, ctx in enumerate(ctx_lines):
            orig_line = lines[start_line + i] if start_line + i < len(lines) else ""
            # Normalize whitespace for comparison
            if ctx.strip() != orig_line.strip():
                return False
        
        return True
    
    def _apply_hunk(self, lines: list, hunk: dict, start_line: int) -> list:
        """Apply a single hunk at specified position."""
        result = lines[:start_line]
        
        # Skip removed lines in original
        skip_count = hunk['removed']
        ctx_idx = 0
        
        for change_type, content in hunk['changes']:
            if change_type == 'context':
                ctx_idx += 1
            elif change_type == 'add':
                result.append(content)
            elif change_type == 'remove':
                skip_count -= 1
        
        # Add remaining lines after removed ones
        remaining_start = start_line + hunk['removed'] + len([c for t, c in hunk['changes'] if t == 'context'])
        result.extend(lines[remaining_start:])
        
        return result
    
    def _parse_and_apply_patch(self, original_lines: list, diff_text: str) -> Optional[list]:
        """Parse unified diff and apply to lines."""
        try:
            diff_lines = diff_text.splitlines(keepends=True)
            result_lines = list(original_lines)
            
            current_hunk_start = None
            current_hunk_offset = 0
            
            i = 0
            while i < len(diff_lines):
                line = diff_lines[i]
                
                if line.startswith('@@'):
                    match = re.search(r'\+(\d+)', line)
                    if match:
                        current_hunk_start = int(match.group(1)) - 1 + current_hunk_offset
                    i += 1
                    continue
                
                if line.startswith('-'):
                    # Find and remove matching line
                    content = line[1:].rstrip('\n')
                    for j in range(max(0, current_hunk_start or 0), len(result_lines)):
                        if result_lines[j].rstrip('\n') == content:
                            result_lines.pop(j)
                            if current_hunk_start is not None:
                                current_hunk_offset -= 1
                            break
                    i += 1
                    continue
                
                if line.startswith('+') and not line.startswith('+++'):
                    # Add line at current position
                    content = line[1:]
                    if not content.endswith('\n'):
                        content += '\n'
                    insert_pos = max(0, current_hunk_start or 0)
                    result_lines.insert(insert_pos, content)
                    if current_hunk_start is not None:
                        current_hunk_offset += 1
                        current_hunk_start += 1
                    i += 1
                    continue
                
                i += 1
            
            return result_lines
            
        except Exception as e:
            logger.debug(f"Patch parsing failed: {e}")
            return None
    
    def _count_changes(self, diff_text: str) -> int:
        """Count number of changed lines in diff."""
        additions = sum(1 for line in diff_text.splitlines() if line.startswith('+') and not line.startswith('+++'))
        deletions = sum(1 for line in diff_text.splitlines() if line.startswith('-') and not line.startswith('---'))
        return (additions + deletions) // 2 + 1
    
    def validate_diff(self, original_text: str, diff_text: str) -> bool:
        """
        Validate that diff can be applied to original text.
        
        Returns True if diff application succeeds, False otherwise.
        """
        result = self.apply_diff(original_text, diff_text)
        return result.success


# Convenience function for quick diff generation
def create_diff(original: str, modified: str, filename: str = "file.py") -> str:
    """Generate unified diff between two strings."""
    protocol = DiffProtocol()
    result = protocol.generate_diff(original, modified, filename)
    return result.diff_text if result.success else ""
