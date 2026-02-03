from typing import Protocol, List
from app.core.models.chunk import RetrievedChunk

class KnowledgeRetriever(Protocol):
    def retrieve(self, query: str, k: int = 6) -> List[RetrievedChunk]:
        """Ищет релевантные куски в базе знаний."""
        ...
