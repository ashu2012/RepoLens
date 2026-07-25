"""Token estimation utilities for RepoLens.

Provides fast heuristic-based token counting and optional tiktoken
verification for accurate token budgeting.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TokenStats:
    """Token statistics for a piece of content.

    Attributes:
        estimated: Heuristic token count (4 chars/token).
        char_count: Raw character count.
        line_count: Number of lines.
        verified: Tiktoken-verified count (None if not verified).
    """

    estimated: int
    char_count: int
    line_count: int
    verified: int | None = None

    @property
    def tokens(self) -> int:
        """Best available token count."""
        return self.verified if self.verified is not None else self.estimated


def estimate_tokens(text: str) -> int:
    """Fast heuristic token estimation.

    Uses the conservative 4 characters per token approximation,
    which is within ~10% of cl100k_base for typical code.

    Args:
        text: Text to estimate tokens for.

    Returns:
        Estimated token count.
    """
    return max(1, len(text) // 4)


def estimate_tokens_detailed(text: str) -> TokenStats:
    """Detailed token statistics for a piece of content.

    Args:
        text: Text to analyze.

    Returns:
        TokenStats with heuristic estimates and character/line counts.
    """
    return TokenStats(
        estimated=estimate_tokens(text),
        char_count=len(text),
        line_count=text.count("\n") + 1 if text else 0,
    )


def verify_with_tiktoken(text: str) -> TokenStats:
    """Verify token count using OpenAI's tiktoken tokenizer.

    Falls back to heuristic if tiktoken is not installed.

    Args:
        text: Text to tokenize.

    Returns:
        TokenStats with both estimated and verified counts.
    """
    stats = estimate_tokens_detailed(text)
    try:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        verified = len(enc.encode(text))
        return TokenStats(
            estimated=stats.estimated,
            char_count=stats.char_count,
            line_count=stats.line_count,
            verified=verified,
        )
    except ImportError:
        return stats


def format_savings(raw_tokens: int, reduced_tokens: int) -> str:
    """Format token savings as a human-readable string.

    Args:
        raw_tokens: Tokens in the uncompressed content.
        reduced_tokens: Tokens after distillation.

    Returns:
        Formatted string like "95.2% reduction (50,000 → 2,400 tokens)"
    """
    if raw_tokens == 0:
        return "No content to compare"
    saved = raw_tokens - reduced_tokens
    pct = (saved / raw_tokens) * 100
    return (
        f"{pct:.1f}% reduction "
        f"({raw_tokens:,} → {reduced_tokens:,} tokens, "
        f"{saved:,} saved)"
    )
