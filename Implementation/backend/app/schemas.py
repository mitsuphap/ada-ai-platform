from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field

# ===== PUBLISHER SCHEMAS =====
class PublisherOut(BaseModel):
    id: int
    name: str
    website: Optional[str] = None
    country: Optional[str] = None
    genres: Optional[List[str]] = None

class PaginatedPublishers(BaseModel):
    items: List[PublisherOut]
    limit: int
    offset: int
    q: Optional[str] = None

class PublisherIn(BaseModel):
    name: str = Field(..., min_length=1)
    website: Optional[str] = None
    country: Optional[str] = None
    genres: List[str] = []                 # ["Poetry","Fiction",...]
    notes: Optional[str] = None

# ===== AGENT SCHEMAS =====
class AgentOut(BaseModel):
    id: int  # agent_id
    full_name: str
    agency: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    notes: Optional[str] = None

class AgentIn(BaseModel):
    full_name: str = Field(..., min_length=1)
    agency: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    notes: Optional[str] = None
class PaginatedAgents(BaseModel):
    items: List[AgentOut]
    limit: int
    offset: int
    q: Optional[str] = None

# ===== MAGAZINE SCHEMAS =====
class MagazineOut(BaseModel):
    id: int  # magazine_id
    name: str
    website: Optional[str] = None
    submission_guidelines: Optional[str] = None
class MagazineIn(BaseModel):
    name: str = Field(..., min_length=1)
    website: Optional[str] = None
    submission_guidelines: Optional[str] = None
class PaginatedMagazines(BaseModel):
    items: List[MagazineOut]
    limit: int
    offset: int
    q: Optional[str] = None
# ===== GENRE SCHEMAS =====
class GenreOut(BaseModel):
    id: int  # genre_id
    name: str
class GenreIn(BaseModel):
    name: str = Field(..., min_length=1)
class PaginatedGenres(BaseModel):
    items: List[GenreOut]
    limit: int
    offset: int
    q: Optional[str] = None
# ===== RELATIONSHIP SCHEMAS =====
class AgentPublisherAffiliation(BaseModel):
    agent_id: int
    publisher_id: int
    role: Optional[str] = None
    since_year: Optional[int] = Field(None, ge=1900, le=2025)

class PublisherGenre(BaseModel):
    publisher_id: int
    genre_id: int

# ===== SEARCH SCHEMA =====
class SearchResult(BaseModel):
    kind: str  # 'agent', 'publisher', 'magazine'
    id: str
    title: str
    url: Optional[str] = None