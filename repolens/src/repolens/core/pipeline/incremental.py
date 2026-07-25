import time
import structlog
from typing import Optional
from .orchestrator import PipelineResult, PhaseResult
from .checkpoint import Checkpoint

logger = structlog.get_logger(__name__)

class IncrementalPipeline:
    """Handles incremental indexing of repositories."""
    
    async def run(self, repo_path: str, last_commit: Optional[str]) -> PipelineResult:
        """Delegate to the production incremental orchestrator."""
        from .orchestrator import PipelineOrchestrator

        return await PipelineOrchestrator().run_incremental(repo_path, last_commit)
