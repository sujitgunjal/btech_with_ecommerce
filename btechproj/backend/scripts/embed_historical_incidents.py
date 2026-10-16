import json
from pathlib import Path

from app.rag.embeddings import EmbeddingService


PROJECT_ROOT = Path(__file__).resolve().parents[2]

INPUT_FILE = (
    PROJECT_ROOT
    / "backend"
    / "data"
    / "historical_incidents.json"
)

OUTPUT_FILE = (
    PROJECT_ROOT
    / "backend"
    / "data"
    / "historical_incidents_embeddings.json"
)


def main():

    print("=" * 60)
    print("Embedding Historical Incidents")
    print("=" * 60)

    # -----------------------------------------------------
    # Load historical incidents
    # -----------------------------------------------------

    with open(
        INPUT_FILE,
        "r",
        encoding="utf-8"
    ) as file:

        incidents = json.load(file)

    print(
        f"\nLoaded {len(incidents)} incidents."
    )

    # -----------------------------------------------------
    # Initialize embedding model
    # -----------------------------------------------------

    embedding_service = EmbeddingService()

    # -----------------------------------------------------
    # Extract text
    # -----------------------------------------------------

    documents = [
        incident["text"]
        for incident in incidents
    ]

    # -----------------------------------------------------
    # Generate embeddings
    # -----------------------------------------------------

    embeddings = (
        embedding_service.embed_documents(
            documents
        )
    )

    # -----------------------------------------------------
    # Attach embeddings
    # -----------------------------------------------------

    for incident, embedding in zip(
        incidents,
        embeddings
    ):

        incident["embedding"] = embedding

    # -----------------------------------------------------
    # Save
    # -----------------------------------------------------

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            incidents,
            file,
            indent=2
        )

    print(
        f"\nSaved embeddings to:"
    )

    print(OUTPUT_FILE)

    print(
        f"\nEmbedding dimension: "
        f"{len(embeddings[0])}"
    )

    print(
        f"Total embedded incidents: "
        f"{len(embeddings)}"
    )

    print("\nEmbedding generation complete.")


if __name__ == "__main__":
    main()