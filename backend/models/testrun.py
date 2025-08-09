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

    relevance: float = 0.0
    relevance_comment: str = ""
    factual_accuracy: float = 0.0
    factual_accuracy_comment: str = ""
    completeness: float = 0.0
    completeness_comment: str = ""
    tone: float = 0.0
    tone_comment: str = ""
    comprehensibility: float = 0.0
    comprehensibility_comment: str = ""
    overall_comment: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "TestResult":
        """
        Baut ein TestResult aus den erwarteten Feldern und
        ignoriert alle Cosmos-Metadaten. Fehlende Felder
        werden mit Defaults belegt.
        """
        try:
            dd = data.copy()

            # 1) run_id (kommt jetzt immer)
            run_id = dd["run_id"]

            # 2) timestamp parsen
            ts = dd.get("timestamp")
            if isinstance(ts, str):
                dd["timestamp"] = datetime.fromisoformat(ts)
            else:
                dd["timestamp"] = datetime.utcnow()

            # 3) Defaulten für die neuen Felder, falls sie nicht da sind
            for score_field in (
                "relevance",
                "factual_accuracy",
                "completeness",
                "tone",
                "comprehensibility"
            ):
                dd.setdefault(score_field, 0.0)

            for comment_field in (
                "relevance_comment",
                "factual_accuracy_comment",
                "completeness_comment",
                "tone_comment",
                "comprehensibility_comment"
            ):
                dd.setdefault(comment_field, "")

            dd.setdefault("overall_comment", None)

            # 4) Konstruktion
            return cls(
                id=dd["id"],
                run_id=run_id,
                prompt_id=dd["prompt_id"],
                prompt_text=dd["prompt_text"],
                ai_response=dd["ai_response"],
                golden_answer=dd["golden_answer"],
                timestamp=dd["timestamp"],
                relevance=dd["relevance"],
                relevance_comment=dd["relevance_comment"],
                factual_accuracy=dd["factual_accuracy"],
                factual_accuracy_comment=dd["factual_accuracy_comment"],
                completeness=dd["completeness"],
                completeness_comment=dd["completeness_comment"],
                tone=dd["tone"],
                tone_comment=dd["tone_comment"],
                comprehensibility=dd["comprehensibility"],
                comprehensibility_comment=dd["comprehensibility_comment"],
                overall_comment=dd["overall_comment"],
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

@dataclass
class ComparisonResult:
    relevance: float
    relevance_comment: str
    factual_accuracy: float
    factual_accuracy_comment: str
    completeness: float
    completeness_comment: str
    tone: float
    tone_comment: str
    comprehensibility: float
    comprehensibility_comment: str
    overall_comment: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "ComparisonResult":
        """
        Baut ein ComparisonResult aus einem dict (z.B. geparstes JSON).
        """
        try:
            return cls(
                relevance                 = float(data["relevance"]),
                relevance_comment         = data["relevance_comment"],
                factual_accuracy          = float(data["factual_accuracy"]),
                factual_accuracy_comment  = data["factual_accuracy_comment"],
                completeness              = float(data["completeness"]),
                completeness_comment      = data["completeness_comment"],
                tone                      = float(data["tone"]),
                tone_comment              = data["tone_comment"],
                comprehensibility         = float(data["comprehensibility"]),
                comprehensibility_comment = data["comprehensibility_comment"],
                overall_comment           = data.get("overall_comment"),
            )
        except KeyError as e:
            logger.error("Missing comparison field %s in %s", e, data)
            raise
        except Exception as e:
            logger.error("Invalid ComparisonResult data: %s – %s", data, e)
            raise
