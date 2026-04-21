from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class AP2IntentMandate(BaseModel):
    """
    Standard 2026 AP2-compliant Intent Mandate.
    """
    mandate_id: str
    user_id: str
    max_budget: float = Field(..., description="Max USD for this task cycle")
    currency: str = "USD"
    resource_scope: list[str] = ["inference", "search", "vector_db"]
    expires_at: datetime
    signature: str  # BBS+ or ES256 cryptographic signature
