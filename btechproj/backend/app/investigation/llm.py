"""LLM client for root cause analysis generation.

Configured for Ollama (gemma4:12b-it-qat) via the OpenAI-compatible API.
Also works with any other OpenAI-compatible endpoint.
"""

import json
import logging
import re
from typing import Any

from ..config import get_settings
from ..schemas.investigation import RootCauseAnalysis

logger = logging.getLogger("incident-backend")


class LLMClient:
    """Wrapper around the OpenAI-compatible chat completions API.

    Default configuration targets Ollama running on the host machine
    at http://host.docker.internal:11434/v1 (reachable from Docker).
    """

    def __init__(self) -> None:
        settings = get_settings()
        self.model = settings.LLM_MODEL
        self.temperature = settings.LLM_TEMPERATURE
        self.max_tokens = settings.LLM_MAX_TOKENS
        self._api_key = settings.LLM_API_KEY
        self._base_url = settings.LLM_BASE_URL or None

    @property
    def is_configured(self) -> bool:
        """Return True if the LLM is reachable (API key is set)."""
        return bool(self._api_key)

    def _get_client(self):
        """Lazily create the OpenAI client."""
        try:
            from openai import OpenAI
        except ImportError:
            raise RuntimeError(
                "The 'openai' package is required. "
                "Install it with: pip install openai"
            )

        kwargs: dict[str, Any] = {"api_key": self._api_key}
        if self._base_url:
            kwargs["base_url"] = self._base_url
        return OpenAI(**kwargs)

    async def generate_rca(
        self, system_prompt: str, user_prompt: str
    ) -> dict[str, Any]:
        """Call the LLM and return a validated RCA dict.

        Uses synchronous OpenAI client inside an async method for
        simplicity — acceptable for a project-scope backend.
        """
        if not self.is_configured:
            raise RuntimeError(
                "LLM_API_KEY is not configured. "
                "Set it in the environment or .env file."
            )

        client = self._get_client()

        logger.info(
            "Calling Ollama LLM model=%s temperature=%.2f max_tokens=%d base_url=%s",
            self.model,
            self.temperature,
            self.max_tokens,
            self._base_url or "default",
        )

        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                response_format={"type": "json_object"},
            )
        except Exception as exc:
            logger.error("Ollama LLM API call failed: %s", exc)
            raise RuntimeError(f"Ollama LLM API call failed: {exc}") from exc

        raw_content = response.choices[0].message.content
        logger.info("LLM response received, length=%d", len(raw_content or ""))

        return self._parse_response(raw_content)

    @staticmethod
    def _parse_response(raw: str | None) -> dict[str, Any]:
        """Parse and validate the LLM JSON response into an RCA dict.

        Ollama models sometimes wrap JSON in markdown code fences or
        include extra text. This method extracts the JSON robustly.
        """
        if not raw:
            raise ValueError("LLM returned an empty response.")

        text = raw.strip()

        # Try direct JSON parse first
        data = _try_parse_json(text)

        # Fallback: extract from markdown code fences
        if data is None:
            json_match = re.search(
                r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL
            )
            if json_match:
                data = _try_parse_json(json_match.group(1).strip())

        # Fallback: find the first { ... } block
        if data is None:
            brace_match = re.search(r"\{.*\}", text, re.DOTALL)
            if brace_match:
                data = _try_parse_json(brace_match.group(0))

        if data is None:
            logger.error("Could not extract JSON from LLM response: %s", text[:500])
            raise ValueError("LLM response does not contain valid JSON.")

        if not isinstance(data, dict):
            raise ValueError("LLM response is not a JSON object.")

        rca = RootCauseAnalysis(
            root_cause=data.get("root_cause", "Unable to determine root cause."),
            supporting_evidence=_ensure_list(data.get("supporting_evidence")),
            affected_services=_ensure_list(data.get("affected_services")),
            confidence=_clamp(float(data.get("confidence", 0.3)), 0.0, 1.0),
            timeline=_parse_timeline(data.get("timeline")),
            alternative_explanations=_ensure_list(
                data.get("alternative_explanations")
            ),
            recommended_actions=_ensure_list(data.get("recommended_actions")),
            relevant_historical_incidents=_parse_historical_refs(
                data.get("relevant_historical_incidents")
            ),
        )

        return rca.model_dump()


def _try_parse_json(text: str) -> dict | None:
    """Attempt to parse text as JSON, returning None on failure."""
    try:
        result = json.loads(text)
        return result if isinstance(result, dict) else None
    except (json.JSONDecodeError, TypeError):
        return None


def _ensure_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value]
    return []


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _parse_timeline(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if isinstance(item, dict):
            result.append(
                {
                    "timestamp": str(item.get("timestamp", "")),
                    "event": str(item.get("event", "")),
                }
            )
    return result


def _parse_historical_refs(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if isinstance(item, dict):
            result.append(
                {
                    "incident_id": str(item.get("incident_id", "")),
                    "incident_type": str(item.get("incident_type", "")),
                    "similarity_score": float(item.get("similarity_score", 0.0)),
                    "relevance": str(item.get("relevance", "")),
                }
            )
    return result
