from dataclasses import dataclass
from typing import List, Optional

@dataclass
class SearchSource:
    name: str
    url: Optional[str]
    content: str

@dataclass
class MultiSourceResult:
    query: str
    sources: List[SearchSource]
    
    def is_empty(self) -> bool:
        return len(self.sources) == 0
