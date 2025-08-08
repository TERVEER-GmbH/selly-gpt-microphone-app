import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Literal, Optional, List

logger = logging.getLogger('logger')

@dataclass
class TestParams:
    model: str
    temperature: float
    max_tokens: int
    top_p: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "TestParams":
        try:
            return cls(**data)
        except TypeError as e:
            logger.error("Invalid TestParams data: %s – %s", data, e)
            raise
@dataclass
class TestResult:
    id: str
    run_id: str
    prompt_id: str
    prompt_text: str
    ai_response: str
    golden_answer: str
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "TestResult":
        """
        Baut ein TestResult nur aus den erwarteten Feldern und ignoriert
        alle anderen Keys (z.B. Cosmos-Metadaten).
        """
        try:
            return cls(
                id            = data["id"],
                run_id        = data["run_id"],      # holt jetzt auch run_id
                prompt_id     = data["prompt_id"],
                prompt_text   = data["prompt_text"],
                ai_response   = data["ai_response"],
                golden_answer = data["golden_answer"],
                timestamp     = datetime.fromisoformat(data["timestamp"])
            )
        except KeyError as e:
            logger.error("Missing required TestResult field %s in %s", e, data)
            raise
        except Exception as e:
            logger.error("Invalid TestResult data: %s – %s", data, e)
            raise

@dataclass
class TestRun:
    id: str
    prompt_ids: List[str]
    params: TestParams
    status: Literal["Pending", "Running", "Done"]
    created_at: str
    results: List[TestResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "prompt_ids": self.prompt_ids,
            "params": self.params.to_dict(),
            "status": self.status,
            "created_at": self.created_at,
            "results": [r.to_dict() for r in self.results],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TestRun":
        try:
            params = TestParams.from_dict(data["params"])
            results = [TestResult.from_dict(r) for r in data.get("results", [])]
            return cls(
                id=data["id"],
                prompt_ids=data["prompt_ids"],
                params=params,
                status=data["status"],
                created_at=data["created_at"],
                results=results,
            )
        except Exception as e:
            logger.error("Invalid TestRun data: %s – %s", data, e)
            raise
