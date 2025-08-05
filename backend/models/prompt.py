from dataclasses import dataclass, field
from typing import List, Optional
from uuid import uuid4

@dataclass
class Prompt:
    """
    Domain model for a test prompt with its golden answer and optional tags.
    """
    id: str
    text: str
    golden_answer: str
    tags: List[str] = field(default_factory=list)

    @staticmethod
    def create(text: str, golden_answer: str, tags: Optional[List[str]] = None) -> "Prompt":
        """
        Factory method to create a new Prompt instance with a generated UUID.
        """
        return Prompt(
            id=str(uuid4()),
            text=text,
            golden_answer=golden_answer,
            tags=tags or []
        )

    def to_dict(self) -> dict:
        """
        Convert the Prompt instance to a dictionary for persistence.
        """
        return {
            "id": self.id,
            "text": self.text,
            "golden_answer": self.golden_answer,
            "tags": self.tags
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Prompt":
        """
        Construct a Prompt instance from a dictionary.
        """
        return Prompt(
            id=data["id"],
            text=data.get("text", ""),
            golden_answer=data.get("golden_answer", ""),
            tags=data.get("tags", []),
        )
