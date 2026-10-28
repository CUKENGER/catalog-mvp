from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ProductOut(BaseModel):
    id: UUID
    name: str
    image_url: str
    created_at: datetime
