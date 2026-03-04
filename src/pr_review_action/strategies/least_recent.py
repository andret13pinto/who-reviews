from __future__ import annotations

import json
import time
from pathlib import Path

from pr_review_action.strategies.base import ReviewState, SelectionContext


class LeastRecentStrategy:
    def __init__(self, state_path: Path = Path(".pr-review-state.json")) -> None:
        self._state_path = state_path

    def select(self, candidates: list[str], context: SelectionContext) -> str:
        timestamps = self._load_timestamps()
        candidate_ts = {c: timestamps.get(c, 0.0) for c in candidates}
        selected = min(candidate_ts, key=candidate_ts.__getitem__)
        timestamps[selected] = time.time()
        self._save_timestamps(timestamps)
        return selected

    def _load_timestamps(self) -> dict[str, float]:
        if not self._state_path.exists():
            return {}
        data: ReviewState = json.loads(self._state_path.read_text())
        return data.get("last_assigned", {})

    def _save_timestamps(self, timestamps: dict[str, float]) -> None:
        data: ReviewState = {}
        if self._state_path.exists():
            data = json.loads(self._state_path.read_text())
        data["last_assigned"] = timestamps
        self._state_path.write_text(json.dumps(data, indent=2))
