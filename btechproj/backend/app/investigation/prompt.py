"""Prompt templates for LLM-based root cause analysis."""

import json
from typing import Any

SYSTEM_PROMPT = """\
You are a senior DevOps incident investigator performing root cause analysis.

RULES:
1. Base your analysis ONLY on the current observability evidence provided below.
2. Historical incidents are contextual reference to help you pattern-match. \
They are NOT proof of the current root cause.
3. If evidence is insufficient or ambiguous, state this clearly and assign \
a LOW confidence score (below 0.5).
4. Do NOT fabricate logs, metrics, traces, or any evidence that was not provided.
5. Do NOT recommend autonomous remediation. Only recommend manual actions.
6. Correlation notes only mean the signals occurred together or on one trace. \
They are not proof of causation.

Respond with a single JSON object matching this exact schema:
{schema}

Every field is required. Use empty lists [] where you have nothing to report. \
confidence must be between 0.0 and 1.0.\
"""

RCA_SCHEMA = {
    "root_cause": "string — most probable root cause based on current evidence",
    "supporting_evidence": [
        "string — specific pieces of current evidence that support this conclusion"
    ],
    "affected_services": [
        "string — services affected by this incident"
    ],
    "confidence": "float 0.0-1.0 — how confident you are in this analysis",
    "timeline": [
        {
            "timestamp": "string — ISO timestamp or relative time",
            "event": "string — what happened at this point",
        }
    ],
    "alternative_explanations": [
        "string — other plausible explanations if confidence is not high"
    ],
    "recommended_actions": [
        "string — concrete steps the team should take"
    ],
    "relevant_historical_incidents": [
        {
            "incident_id": "string — ID of the historical incident",
            "incident_type": "string — type of the historical incident",
            "similarity_score": "float — semantic similarity score",
            "relevance": "string — why this historical incident is relevant",
        }
    ],
}

USER_PROMPT_TEMPLATE = """\
## Current Incident

- **Title:** {title}
- **Service:** {service}
- **Severity:** {severity}
- **Time window:** {start_time} to {end_time}
- **Description:** {description}

## Current Observability Evidence

{evidence_stats}

{evidence_text}

## Similar Historical Incidents (contextual reference only)

{historical_context}

---

Analyze the current evidence above and produce a structured root cause analysis. \
Remember: base your conclusions on the CURRENT evidence, not on historical patterns alone.\
"""


def build_system_prompt() -> str:
    """Return the system prompt with the embedded RCA JSON schema."""
    schema_str = json.dumps(RCA_SCHEMA, indent=2)
    return SYSTEM_PROMPT.format(schema=schema_str)


def build_user_prompt(
    incident: Any,
    evidence_formatted: dict[str, str],
    historical_incidents: list[dict[str, Any]],
) -> str:
    """Build the user prompt from incident details, evidence, and history."""
    title = getattr(incident, "title", "Unknown")
    service = getattr(incident, "service", "Unknown")
    severity = getattr(incident, "severity", "Unknown")
    description = getattr(incident, "description", "") or "No description provided."
    start_time = str(getattr(incident, "start_time", "N/A"))
    end_time = str(getattr(incident, "end_time", "N/A"))

    historical_context = _format_historical_context(historical_incidents)

    return USER_PROMPT_TEMPLATE.format(
        title=title,
        service=service,
        severity=severity,
        start_time=start_time,
        end_time=end_time,
        description=description,
        evidence_stats=evidence_formatted.get("evidence_stats", ""),
        evidence_text=evidence_formatted.get("evidence_text", "No evidence available."),
        historical_context=historical_context,
    )


def _format_historical_context(incidents: list[dict[str, Any]]) -> str:
    """Format retrieved historical incidents for the prompt."""
    if not incidents:
        return "No similar historical incidents found."

    sections = []
    for i, inc in enumerate(incidents, start=1):
        meta = inc.get("metadata", {})
        similarity = inc.get("similarity_score", 0.0)

        section = (
            f"**{i}. {inc.get('incident_id', 'Unknown')}** "
            f"(similarity: {similarity:.2f})\n"
            f"  Type: {meta.get('incident_type', 'unknown')}\n"
            f"  Service: {meta.get('affected_service', 'unknown')}\n"
            f"  Severity: {meta.get('severity', 'unknown')}\n"
        )

        doc = inc.get("document", "")
        if doc:
            preview = doc[:600].replace("\n", "\n  ")
            section += f"  Summary:\n  {preview}"
            if len(doc) > 600:
                section += "\n  ..."

        sections.append(section)

    return "\n\n".join(sections)
