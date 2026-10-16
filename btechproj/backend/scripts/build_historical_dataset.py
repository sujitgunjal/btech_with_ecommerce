import json
from pathlib import Path


# ---------------------------------------------------------
# Paths
# ---------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]

INCIDENTS_DIR = PROJECT_ROOT / "incidents"
OUTPUT_DIR = PROJECT_ROOT / "backend" / "data"
OUTPUT_FILE = OUTPUT_DIR / "historical_incidents.json"


# ---------------------------------------------------------
# Convert timeline into readable text
# ---------------------------------------------------------

def format_timeline(timeline):
    if not timeline:
        return "No timeline information available."

    lines = []

    for item in timeline:
        phase = item.get("phase", "unknown")
        event = item.get("event", "")

        lines.append(
            f"- {phase}: {event}"
        )

    return "\n".join(lines)


# ---------------------------------------------------------
# Convert one scenario.json into a RAG document
# ---------------------------------------------------------

def scenario_to_document(data):

    incident_id = data.get("incident_id", "UNKNOWN")
    incident_type = data.get("type", "unknown")
    service = data.get("affected_service", "unknown")

    start_time = data.get("start_time", "")
    end_time = data.get("end_time", "")

    root_cause = data.get(
        "expected_root_cause",
        "Not specified"
    )

    symptoms = data.get(
        "expected_symptoms",
        []
    )

    evidence = data.get(
        "expected_evidence",
        []
    )

    resolution = data.get(
        "expected_resolution",
        "Not specified"
    )

    severity = data.get(
        "severity",
        "UNKNOWN"
    )

    timeline = data.get(
        "timeline",
        []
    )

    # -----------------------------------------------------
    # Convert lists to readable text
    # -----------------------------------------------------

    symptoms_text = "\n".join(
        f"- {item}" for item in symptoms
    ) if symptoms else "- No symptoms specified."

    evidence_text = "\n".join(
        f"- {item}" for item in evidence
    ) if evidence else "- No expected evidence specified."

    timeline_text = format_timeline(timeline)

    # -----------------------------------------------------
    # Optional deployment information
    # -----------------------------------------------------

    deployment = data.get("related_deployment")

    deployment_text = ""

    if deployment:
        deployment_text = f"""
Related Deployment:
- Service: {deployment.get("service", "unknown")}
- Version: {deployment.get("version", "unknown")}
- Commit: {deployment.get("commit_id", "unknown")}
"""

    # -----------------------------------------------------
    # Create semantic document
    # -----------------------------------------------------

    document = f"""
Historical DevOps Incident

Incident ID: {incident_id}

Incident Type: {incident_type}

Affected Service: {service}

Severity: {severity}

Incident Time:
- Start: {start_time}
- End: {end_time}

Root Cause:
{root_cause}

Symptoms:
{symptoms_text}

Expected Evidence:
{evidence_text}

Resolution:
{resolution}

Timeline:
{timeline_text}

{deployment_text}
""".strip()

    # -----------------------------------------------------
    # Metadata
    # -----------------------------------------------------

    metadata = {
        "incident_id": incident_id,
        "incident_type": incident_type,
        "affected_service": service,
        "severity": severity,
        "start_time": start_time,
        "end_time": end_time,
    }

    if deployment:
        metadata.update({
            "deployment_service": deployment.get(
                "service"
            ),
            "deployment_version": deployment.get(
                "version"
            ),
            "commit_id": deployment.get(
                "commit_id"
            ),
        })

    return {
        "id": incident_id,
        "text": document,
        "metadata": metadata,
    }


# ---------------------------------------------------------
# Find and process all scenario.json files
# ---------------------------------------------------------

def build_dataset():

    print("=" * 60)
    print("Building Historical Incident Dataset")
    print("=" * 60)

    if not INCIDENTS_DIR.exists():
        raise FileNotFoundError(
            f"Incidents directory not found: {INCIDENTS_DIR}"
        )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    scenario_files = sorted(
        INCIDENTS_DIR.glob("*/scenario.json")
    )

    if not scenario_files:
        raise FileNotFoundError(
            f"No scenario.json files found in {INCIDENTS_DIR}"
        )

    documents = []

    for scenario_file in scenario_files:

        print(
            f"\nProcessing: "
            f"{scenario_file.parent.name}/scenario.json"
        )

        try:
            with open(
                scenario_file,
                "r",
                encoding="utf-8"
            ) as file:
                data = json.load(file)

        except json.JSONDecodeError as error:
            print(
                f"ERROR: Invalid JSON in {scenario_file}"
            )
            print(error)
            continue

        document = scenario_to_document(data)

        documents.append(document)

        print(
            f"  Incident ID : "
            f"{document['metadata']['incident_id']}"
        )

        print(
            f"  Type        : "
            f"{document['metadata']['incident_type']}"
        )

        print(
            f"  Service     : "
            f"{document['metadata']['affected_service']}"
        )

    # -----------------------------------------------------
    # Save dataset
    # -----------------------------------------------------

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            documents,
            file,
            indent=2,
            ensure_ascii=False
        )

    print("\n" + "=" * 60)
    print("Dataset creation complete")
    print("=" * 60)

    print(
        f"Total incidents : {len(documents)}"
    )

    print(
        f"Output file     : {OUTPUT_FILE}"
    )

    print("=" * 60)


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

if __name__ == "__main__":
    build_dataset()