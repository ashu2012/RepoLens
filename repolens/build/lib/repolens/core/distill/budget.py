"""Token budget enforcement for RepoLens context distillation."""

from __future__ import annotations

from dataclasses import dataclass

from repolens.core.distill.token_estimator import estimate_tokens


@dataclass
class TokenBudget:
    """Manages a token budget for context assembly.

    Tracks remaining capacity and provides allocation decisions.

    Args:
        total: Total token budget.
    """

    total: int
    used: int = 0

    @property
    def remaining(self) -> int:
        return max(0, self.total - self.used)

    @property
    def utilization(self) -> float:
        """Fraction of budget used (0.0 to 1.0)."""
        if self.total == 0:
            return 1.0
        return self.used / self.total

    def can_fit(self, content: str) -> bool:
        """Check if content fits in the remaining budget."""
        return estimate_tokens(content) <= self.remaining

    def allocate(self, content: str) -> str | None:
        """Try to allocate budget for content.

        Returns the content if it fits, None otherwise.
        Updates the used counter.
        """
        tokens = estimate_tokens(content)
        if tokens <= self.remaining:
            self.used += tokens
            return content
        return None

    def force_allocate(self, content: str, max_tokens: int | None = None) -> str:
        """Allocate content, truncating if necessary.

        Args:
            content: Content to fit.
            max_tokens: Override maximum tokens for this allocation.

        Returns:
            Content, possibly truncated to fit budget.
        """
        limit = min(self.remaining, max_tokens) if max_tokens else self.remaining
        tokens = estimate_tokens(content)

        if tokens <= limit:
            self.used += tokens
            return content

        # Truncate to fit
        char_limit = limit * 4  # Approximate chars from tokens
        truncated = content[:char_limit]
        if truncated != content:
            truncated += "\n# ... (truncated to fit budget)"
        actual_tokens = estimate_tokens(truncated)
        self.used += actual_tokens
        return truncated

    def reset(self) -> None:
        """Reset the budget to fully available."""
        self.used = 0
