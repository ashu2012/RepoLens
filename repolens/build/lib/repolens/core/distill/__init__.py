"""Context distillation engine for RepoLens.

Reduces token consumption by generating code skeletons, assembling
blast-radius context, and enforcing token budgets.
"""

from repolens.core.distill.skeleton import build_skeleton, SkeletonResult
from repolens.core.distill.context_builder import ContextBuilder, ContextResult
from repolens.core.distill.token_estimator import estimate_tokens, TokenStats
from repolens.core.distill.budget import TokenBudget

__all__ = [
    "build_skeleton",
    "SkeletonResult",
    "ContextBuilder",
    "ContextResult",
    "estimate_tokens",
    "TokenStats",
    "TokenBudget",
]
