from dataclasses import dataclass
from typing import Optional
from datetime import datetime

@dataclass
class MarketplaceMessage:
    id: str
    marketplace: str  # "ozon" or "wb"
    message_type: str # "question", "review", "chat"
    item_id: str
    product_name: str
    text: str
    status: str       # "new", "processing", "answered", "failed"
    created_at: datetime
    answer_text: Optional[str] = None
    answered_at: Optional[datetime] = None
