from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any


@dataclass
class ChartAsset:
    """
    Represents a single weather chart or image.
    """
    name: str                     # Human-readable name
    kind: str                     # 'analysis', 'radar', 'satellite', etc.
    original_url: str
    fetched_at_utc: datetime
    local_path: Optional[str] = None
    content_type: Optional[str] = None
    source: Optional[str] = None
    extras: Dict[str, Any] = field(default_factory=dict)

@dataclass
class TextAsset:
    """
    Represents a generated text artifact (e.g. NOTAM digest, summary, report).
    """
    name: str
    kind: str                  # e.g. "notams", "summary", "taf_digest"
    generated_at_utc: datetime
    local_path: Optional[str] = None
    source: Optional[str] = None
    extras: Dict[str, Any] = field(default_factory=dict)

@dataclass
class Briefing:
    generated_at_utc: datetime
    charts: List[ChartAsset] = field(default_factory=list)
    texts: List[TextAsset] = field(default_factory=list)  
    notes: List[str] = field(default_factory=list)
    health: Dict[str, Any] = field(default_factory=dict)

