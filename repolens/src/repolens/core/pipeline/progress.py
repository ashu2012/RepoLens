import structlog
from typing import Any
from .orchestrator import PhaseResult

logger = structlog.get_logger(__name__)

class ProgressTracker:
    """Tracker for pipeline progress reporting."""

    def on_phase_start(self, phase_name: str) -> None:
        """Called when a pipeline phase starts."""
        logger.info("phase.start", phase_name=phase_name)

    def on_phase_end(self, phase_name: str, result: PhaseResult) -> None:
        """Called when a pipeline phase ends."""
        logger.info("phase.end", phase_name=phase_name, result=result.status)

    def on_file_processed(self, file_path: str) -> None:
        """Called when a file has been processed."""
        logger.debug("file.processed", file_path=file_path)

    def on_error(self, phase_name: str, error: Exception) -> None:
        """Called when an error occurs during a phase."""
        logger.error("phase.error", phase_name=phase_name, error=str(error))
