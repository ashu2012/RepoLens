import json
import os
import uuid
from pathlib import Path
from typing import Optional
import structlog

logger = structlog.get_logger(__name__)

class Checkpoint:
    """Store/load pipeline state."""
    
    def __init__(self):
        self.last_commit: Optional[str] = None
        self.last_full_index: Optional[float] = None
        self.last_incremental: Optional[float] = None
        self.phase_completed: Optional[str] = None
        self.error: Optional[str] = None

    def save(self, repo_path: str) -> None:
        """Save pipeline state to .repolens/state.json."""
        state_dir = Path(repo_path) / ".repolens"
        state_dir.mkdir(parents=True, exist_ok=True)
        state_file = state_dir / "state.json"
        temporary = state_dir / f".state.{uuid.uuid4().hex}.tmp"
        
        data = {
            "last_commit": self.last_commit,
            "last_full_index": self.last_full_index,
            "last_incremental": self.last_incremental,
            "phase_completed": self.phase_completed,
            "error": self.error
        }
        
        with open(temporary, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, state_file)
        logger.debug("checkpoint.saved", path=str(state_file))

    @classmethod
    def load(cls, repo_path: str) -> Optional['Checkpoint']:
        """Load pipeline state from .repolens/state.json."""
        state_file = Path(repo_path) / ".repolens" / "state.json"
        if not state_file.exists():
            return None
            
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            checkpoint = cls()
            checkpoint.last_commit = data.get("last_commit")
            checkpoint.last_full_index = data.get("last_full_index")
            checkpoint.last_incremental = data.get("last_incremental")
            checkpoint.phase_completed = data.get("phase_completed")
            checkpoint.error = data.get("error")
            return checkpoint
        except Exception as e:
            logger.error("checkpoint.load.failed", error=str(e), path=str(state_file))
            return None
