from __future__ import annotations
from pydantic import BaseModel, Field
from typing import List, Optional, Literal

PoemStyle = Literal[
    "free_verse",
    "haiku",
    "limerick",
    "acrostic",
    "sonnet_like",
    "spoken_word",
    "rhymed_couplets",
]

ReadingLevel = Literal["simple", "general", "advanced"]


class PoemRequest(BaseModel):
    occasion: str = "just for fun"
    theme: str
    audience: Optional[str] = None

    style: PoemStyle = "free_verse"
    tone: str = "warm"
    writer_vibe: Optional[str] = None

    must_include: List[str] = Field(default_factory=list)
    avoid: List[str] = Field(default_factory=list)

    line_count: int = Field(12, ge=2, le=60)
    rhyme: bool = False
    syllable_hints: Optional[str] = None
    no_cliches: bool = True
    reading_level: ReadingLevel = "general"

    acrostic_word: Optional[str] = None


class Critique(BaseModel):
    constraint_issues: List[str] = Field(default_factory=list)
    cliches_detected: List[str] = Field(default_factory=list)
    imagery_score: int = Field(..., ge=1, le=10)
    coherence_score: int = Field(..., ge=1, le=10)
    originality_score: int = Field(..., ge=1, le=10)
    suggestions: List[str] = Field(default_factory=list)
