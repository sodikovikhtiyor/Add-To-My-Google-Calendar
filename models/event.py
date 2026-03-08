from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Event:
    title: str
    start_dt: datetime
    end_dt: datetime
    location: Optional[str] = None
    description: Optional[str] = None
