from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel

from backend.app.config import Settings
from backend.app.eval.long_session_templates import ScriptTurn
from backend.app.models import Product


class JudgeResult(BaseModel):
    raw: list[dict[str, Any]]
    mean: float
    disagreement: float
    call_count: int


class LongSessionJudge:
    def __init__(self, settings: Settings, *, call_count: int = 3):
        self.settings = settings
        self.call_count = call_count
        self._client: httpx.AsyncClient | None = None

        # Load prompt template
        prompt_path = Path(__file__).parent / "prompts" / "long_session_judge_v1.md"
        with open(prompt_path, "r", encoding="utf-8") as f:
            self.prompt_template = f.read()

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            api_key = self.settings.ark_api_key or ""
            self._client = httpx.AsyncClient(
                base_url=self.settings.ark_base_url,
                timeout=30.0,
                headers={"Authorization": f"Bearer {api_key}"},
            )
        return self._client

    async def judge(
        self, turn: ScriptTurn, answer_text: str, retrieved_top_k: list[str], product_map: dict[str, Product]
    ) -> JudgeResult:
        # Prepare template variables
        query = turn.query
        turn_type = turn.turn_type
        adversarial_subtype = turn.adversarial_subtype or ""
        answer = answer_text
        retrieved_top_k_str = ", ".join(retrieved_top_k)
        sample_catalog_ids = ", ".join(list(product_map.keys())[:20])  # Limit to 20
        expected_brief = json.dumps(turn.expected, ensure_ascii=False)

        # Format prompt (we use str.format with escaped JSON braces)
        prompt = self.prompt_template.format(
            query=query,
            turn_type=turn_type,
            adversarial_subtype=adversarial_subtype,
            answer=answer,
            retrieved_top_k=retrieved_top_k_str,
            sample_catalog_ids=sample_catalog_ids,
            expected_brief=expected_brief,
        )

        # Call LLM multiple times
        raw_results: list[dict[str, Any]] = []
        for _ in range(self.call_count):
            result = await self._call_once(prompt)
            raw_results.append(result)

        # Calculate mean score
        scores = [self._score(r) for r in raw_results]
        mean = sum(scores) / len(scores) if scores else 0.0

        # Calculate disagreement
        disagreement = self._disagreement(raw_results)

        return JudgeResult(
            raw=raw_results,
            mean=mean,
            disagreement=disagreement,
            call_count=self.call_count,
        )

    async def _call_once(self, prompt: str) -> dict[str, Any]:
        # Call ARK chat completions API
        payload = {
            "model": self.settings.ark_model,
            "messages": [
                {"role": "system", "content": "你是一个严格的评测员，只输出 JSON，不要任何其他文字。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.0,
        }

        try:
            response = await self.client.post("chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            return self._safe_parse(content)
        except Exception:
            # On any error, return default zero-score result
            return {
                "hit": 0,
                "fluent": 0,
                "no_hallucination": 0,
                "no_state_violation": 0,
                "reason": "parse_error",
            }

    def _safe_parse(self, content: str) -> dict[str, Any]:
        # Try to extract JSON from content (handle fenced code blocks)
        json_str = content.strip()

        # Extract from ```json ... ``` if present
        fenced_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
        if fenced_match:
            json_str = fenced_match.group(1).strip()

        try:
            parsed = json.loads(json_str)
            # Ensure all required fields exist
            result = {
                "hit": int(parsed.get("hit", 0)),
                "fluent": int(parsed.get("fluent", 0)),
                "no_hallucination": int(parsed.get("no_hallucination", 0)),
                "no_state_violation": int(parsed.get("no_state_violation", 0)),
                "reason": parsed.get("reason", ""),
            }
            # Clamp to 0/1
            for key in ["hit", "fluent", "no_hallucination", "no_state_violation"]:
                result[key] = 1 if result[key] >= 1 else 0
            return result
        except (json.JSONDecodeError, ValueError, TypeError):
            # Fallback to zero score
            return {
                "hit": 0,
                "fluent": 0,
                "no_hallucination": 0,
                "no_state_violation": 0,
                "reason": "parse_error",
            }

    def _score(self, result: dict[str, Any]) -> float:
        return float(
            result.get("hit", 0)
            + result.get("fluent", 0)
            + result.get("no_hallucination", 0)
            + result.get("no_state_violation", 0)
        )

    def _disagreement(self, raw_results: list[dict[str, Any]]) -> float:
        if len(raw_results) <= 1:
            return 0.0

        # For each dimension, check if there's any disagreement
        dimensions = ["hit", "fluent", "no_hallucination", "no_state_violation"]
        disagreed = 0

        for dim in dimensions:
            values = [r.get(dim, 0) for r in raw_results]
            if len(set(values)) > 1:
                disagreed += 1

        return disagreed / len(dimensions)

    @staticmethod
    def compute_disagreement_rate(results: list[JudgeResult]) -> float:
        if not results:
            return 0.0
        # Count how many turns have any disagreement
        disagreed_turns = sum(1 for r in results if r.disagreement > 0)
        return disagreed_turns / len(results)

    @staticmethod
    def recommend_pilot_call_count(disagreement_rate: float) -> int | None:
        if disagreement_rate < 0.05:
            return 1
        elif disagreement_rate < 0.20:
            return 3
        else:
            return None

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "LongSessionJudge":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.aclose()
