"""Code skeleton generator for RepoLens.

Produces file skeletons by preserving signatures and eliding function bodies.
Reduces a 500-line file to ~50 lines of structural outline, achieving
80-95% token savings while preserving navigational context.

Two modes:
- 'signatures': Structure only. Every signature present, all bodies elided.
- 'smart': Signatures plus bodies of the most important symbols under a budget.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from repolens.core.distill.token_estimator import estimate_tokens

__all__ = ["build_skeleton", "SkeletonResult"]

DEFAULT_TOKEN_BUDGET = 1800
_IMPORT_RE = re.compile(
    r"^\s*(import\s|from\s+\S+\s+import\s|use\s|require\s*\(|#include\s|using\s|package\s)"
)
_DECOR_RE = re.compile(r"^\s*(?:#|//)[\s\-=~*#_]{4,}\s*$")
_DOCSTRING_DELIMS = ('"""', "'''")
_PREAMBLE_KEEP_LINES = 60
_GAP_KEEP_LINES = 4


@dataclass
class SkeletonSymbol:
    """A symbol extracted from the source for skeleton generation."""

    name: str
    kind: str  # function, class, method
    start_line: int  # 1-indexed
    end_line: int  # 1-indexed, inclusive
    importance: float = 0.0  # Higher = more important


@dataclass
class SkeletonResult:
    """Result of skeleton generation."""

    skeleton: str
    mode: str  # signatures, smart, raw
    original_tokens: int
    skeleton_tokens: int
    symbols_included: int
    symbols_total: int

    @property
    def reduction_pct(self) -> float:
        """Percentage of tokens saved."""
        if self.original_tokens == 0:
            return 0.0
        return (1 - self.skeleton_tokens / self.original_tokens) * 100

    @property
    def savings_summary(self) -> str:
        return (
            f"{self.reduction_pct:.1f}% reduction "
            f"({self.original_tokens:,} → {self.skeleton_tokens:,} tokens)"
        )


def _find_signature_end(lines: list[str], start_idx: int, max_scan: int = 12) -> int:
    """Find the end of a multi-line signature (e.g., def foo(\\n  arg1,\\n):)."""
    # Look for the colon or closing bracket/paren that ends the signature
    depth = 0
    for i in range(start_idx, min(start_idx + max_scan, len(lines))):
        line = lines[i]
        depth += line.count("(") + line.count("[") + line.count("{")
        depth -= line.count(")") + line.count("]") + line.count("}")
        if depth <= 0 and (":" in line or "{" in line or line.rstrip().endswith(")")):
            return i
    return start_idx


def _is_import_line(line: str) -> bool:
    """Check if a line is an import/include statement."""
    return bool(_IMPORT_RE.match(line))


def _extract_preamble(lines: list[str]) -> list[str]:
    """Extract the file preamble (imports, module docstring, constants)."""
    preamble: list[str] = []
    in_docstring = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        # Track docstrings
        for delim in _DOCSTRING_DELIMS:
            if stripped.startswith(delim):
                in_docstring = not in_docstring
                if stripped.count(delim) >= 2:
                    in_docstring = False
        if in_docstring or _is_import_line(line) or stripped.startswith("#"):
            preamble.append(line)
        elif stripped == "":
            preamble.append(line)
        elif i < _PREAMBLE_KEEP_LINES:
            preamble.append(line)
        else:
            break
    return preamble


def build_skeleton(
    source: str,
    symbols: list[SkeletonSymbol] | None = None,
    mode: str = "signatures",
    token_budget: int = DEFAULT_TOKEN_BUDGET,
) -> SkeletonResult:
    """Build a token-reduced skeleton of a source file.

    Args:
        source: Full source code of the file.
        symbols: List of symbols with line ranges. If None, returns raw source.
        mode: 'signatures' (structure only) or 'smart' (include important bodies).
        token_budget: Maximum tokens for smart mode body inclusion.

    Returns:
        SkeletonResult with the generated skeleton and statistics.
    """
    original_tokens = estimate_tokens(source)

    if not symbols or not source.strip():
        return SkeletonResult(
            skeleton=source,
            mode="raw",
            original_tokens=original_tokens,
            skeleton_tokens=original_tokens,
            symbols_included=0,
            symbols_total=0,
        )

    lines = source.splitlines(keepends=True)
    # Sort symbols by start_line
    sorted_symbols = sorted(symbols, key=lambda s: s.start_line)

    # Build covered ranges
    covered: list[tuple[int, int, SkeletonSymbol]] = []
    for sym in sorted_symbols:
        start = max(0, sym.start_line - 1)  # Convert to 0-indexed
        end = min(len(lines), sym.end_line)  # Exclusive
        covered.append((start, end, sym))

    skeleton_lines: list[str] = []

    # Add preamble (imports, module docstring)
    if covered and covered[0][0] > 0:
        preamble = lines[: covered[0][0]]
        for line in preamble:
            if not _DECOR_RE.match(line):
                skeleton_lines.append(line)

    # Process each symbol
    bodies_budget = token_budget
    included_bodies = 0

    for i, (start, end, sym) in enumerate(covered):
        # Add gap between symbols (constants, blank lines)
        if i > 0:
            prev_end = covered[i - 1][1]
            gap = lines[prev_end:start]
            if len(gap) <= _GAP_KEEP_LINES:
                skeleton_lines.extend(gap)
            elif gap:
                skeleton_lines.append("\n")

        # Find signature end
        sig_end = _find_signature_end(lines, start) + 1
        sig_lines = lines[start:sig_end]
        skeleton_lines.extend(sig_lines)

        body_lines = lines[sig_end:end]
        body_line_count = end - sig_end

        if mode == "smart" and sym.importance > 0 and body_line_count > 0:
            # Check if body fits in budget
            body_text = "".join(body_lines)
            body_tokens = estimate_tokens(body_text)
            if bodies_budget >= body_tokens and included_bodies < 5:
                skeleton_lines.extend(body_lines)
                bodies_budget -= body_tokens
                included_bodies += 1
                continue

        # Elide body with marker
        if body_line_count > 0:
            indent = "    "
            if sig_lines:
                # Match indentation of signature
                sig_stripped = sig_lines[0]
                indent = sig_stripped[: len(sig_stripped) - len(sig_stripped.lstrip())] + "    "
            skeleton_lines.append(
                f"{indent}# ... ({body_line_count} lines elided)\n"
            )

    # Add trailing content after last symbol
    if covered:
        last_end = covered[-1][1]
        trailing = lines[last_end:]
        for line in trailing:
            if not _DECOR_RE.match(line):
                skeleton_lines.append(line)

    skeleton = "".join(skeleton_lines)
    skeleton_tokens = estimate_tokens(skeleton)

    return SkeletonResult(
        skeleton=skeleton,
        mode=mode,
        original_tokens=original_tokens,
        skeleton_tokens=skeleton_tokens,
        symbols_included=included_bodies if mode == "smart" else len(sorted_symbols),
        symbols_total=len(sorted_symbols),
    )
