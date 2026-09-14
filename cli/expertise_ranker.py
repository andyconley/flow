"""Local semantic provider port and exact expertise ranking."""
from __future__ import annotations

import math
import os
from pathlib import Path
import sys
from typing import Iterable

from expertise_model import SCHEMA_VERSION, validate_ranking_result
from expertise_projection import ExpertiseProjectionError, vectors_for_role


PROVIDER_REVISION = "fastembed-bge-small-en-v1.5-v1"
SCORE_SEMANTICS = "exact-cosine-local-bge-small-en-v1.5"
QUERY_PREFIX = "Represent this task for retrieving a relevant operating method: "


class ExpertiseProviderError(ValueError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class FastEmbedProvider:
    """Load only an already installed local runtime and verified model tree."""

    provider_revision = PROVIDER_REVISION

    def __init__(self, runtime_site: Path, model_dir: Path, model_artifact_digest: str, runtime_revision: str) -> None:
        self.runtime_site = Path(runtime_site)
        self.model_dir = Path(model_dir)
        self.model_artifact_digest = model_artifact_digest
        self.runtime_revision = runtime_revision
        self._model = None

    def _load(self):
        if self._model is not None:
            return self._model
        if not self.runtime_site.is_dir() or not self.model_dir.is_dir():
            raise ExpertiseProviderError("provider_missing")
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
        # The verified site is immutable. Prevent imports from creating
        # unlisted bytecode beside the pinned executable files.
        sys.dont_write_bytecode = True
        site = str(self.runtime_site.resolve())
        if site not in sys.path:
            sys.path.insert(0, site)
        try:
            from fastembed.text.onnx_embedding import OnnxTextEmbedding
            self._model = OnnxTextEmbedding(
                model_name="BAAI/bge-small-en-v1.5",
                specific_model_path=str(self.model_dir.resolve()),
                local_files_only=True,
                providers=["CPUExecutionProvider"],
                threads=2,
            )
        except Exception as error:  # noqa: BLE001 - provider boundary erases sensitive exception text.
            raise ExpertiseProviderError("provider_load_failed") from error
        return self._model

    def embed(self, texts: Iterable[str]):
        bounded = list(texts)
        if any(not isinstance(text, str) or len(text.encode("utf-8")) > 32768 for text in bounded):
            raise ExpertiseProviderError("provider_input_invalid")
        try:
            return list(self._load().embed(bounded))
        except ExpertiseProviderError:
            raise
        except Exception as error:  # noqa: BLE001 - normalized at trust boundary.
            raise ExpertiseProviderError("provider_load_failed") from error


def normalized(values: Iterable[float]) -> tuple[float, ...]:
    vector = tuple(float(value) for value in values)
    if not vector or any(not math.isfinite(value) for value in vector):
        raise ExpertiseProviderError("provider_output_invalid")
    norm = math.sqrt(sum(value * value for value in vector))
    if not math.isfinite(norm) or norm == 0:
        raise ExpertiseProviderError("provider_output_invalid")
    return tuple(value / norm for value in vector)


def exact_cosine(left: Iterable[float], right: Iterable[float]) -> float:
    a, b = tuple(left), tuple(right)
    if len(a) != len(b) or not a:
        raise ExpertiseProviderError("provider_output_invalid")
    score = sum(x * y for x, y in zip(a, b))
    if not math.isfinite(score):
        raise ExpertiseProviderError("provider_output_invalid")
    return float(score)


def rank(
    flow_home: Path,
    role: str,
    query: str,
    provider: object,
    projection_digest: str,
    *,
    window: int = 3,
) -> dict:
    if not isinstance(query, str) or not query.strip() or len(query.encode("utf-8")) > 32768:
        raise ExpertiseProviderError("provider_input_invalid")
    try:
        rows = vectors_for_role(flow_home, role, projection_digest)
    except ExpertiseProjectionError:
        raise
    try:
        result = list(provider.embed([QUERY_PREFIX + query]))
        if len(result) != 1:
            raise ExpertiseProviderError("provider_output_invalid")
        query_vector = normalized(result[0])
        scored = []
        lowered = query.casefold()
        for row in rows:
            score = exact_cosine(query_vector, row["vector"])
            scored.append((score, row["entry_id"], row))
        ordered = sorted(scored, key=lambda item: (-item[0], item[1]))[:window]
        candidates = [
            {
                "entry_id": entry_id,
                "ordinal": ordinal,
                "provider_score": score,
                "entry_digest": row["entry_digest"],
                "score_semantics": SCORE_SEMANTICS,
                "structured_exact_match": entry_id.casefold() in lowered,
            }
            for ordinal, (score, entry_id, row) in enumerate(ordered, 1)
        ]
        return validate_ranking_result({
            "schema_version": SCHEMA_VERSION,
            "state": "ranked" if candidates else "not_run",
            "reason": "ranked" if candidates else "not_run_empty_eligibility",
            "provider_calls": 1,
            "candidates": candidates,
            "identity": projection_digest,
        })
    except ExpertiseProviderError:
        raise
    except Exception as error:  # noqa: BLE001 - do not leak model inputs or exceptions.
        raise ExpertiseProviderError("provider_output_invalid") from error
