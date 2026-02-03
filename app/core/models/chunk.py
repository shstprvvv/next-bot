from dataclasses import dataclass
from typing import Dict, Any

@dataclass
class RetrievedChunk:
    content: str
    score: float = 0.0
    metadata: Dict[str, Any] = None
