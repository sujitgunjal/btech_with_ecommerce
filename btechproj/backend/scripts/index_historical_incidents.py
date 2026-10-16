import json
from pathlib import Path

from app.rag.vector_store import VectorStore


PROJECT_ROOT = Path(__file__).resolve().parents[2]

INPUT_FILE = (
    PROJECT_ROOT
    / "backend"
    / "data"
    / "historical_incidents_embeddings.json"
)


def main():

    print("=" * 60)
    print("Indexing Historical Incidents into ChromaDB")
    print("=" * 60)

    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Input file not found: {INPUT_FILE}"
        )

    with open(INPUT_FILE, "r", encoding="utf-8") as file:
        incidents = json.load(file)

    print(f"\nLoaded incidents: {len(incidents)}")

    vector_store = VectorStore()

    vector_store.add_incidents(incidents)

    print("\nChromaDB indexing complete.")
    print(
        f"Total documents in collection: "
        f"{vector_store.collection.count()}"
    )


if __name__ == "__main__":
    main()