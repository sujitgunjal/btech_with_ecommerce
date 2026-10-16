from app.rag.embeddings import EmbeddingService
from app.rag.vector_store import VectorStore


def main():

    print("=" * 60)
    print("Testing Semantic Retrieval")
    print("=" * 60)

    embedding_service = EmbeddingService()
    vector_store = VectorStore()

    queries = [
        "PostgreSQL database connection timeout in order service",
        "Order service suddenly has extremely high CPU usage",
        "Requests became very slow and response latency increased",
        "Order service started failing after a new deployment",
    ]

    for query in queries:

        print("\n" + "-" * 60)
        print(f"Query: {query}")
        print("-" * 60)

        query_embedding = embedding_service.embed_text(query)

        results = vector_store.search(
            query_embedding=query_embedding,
            top_k=3
        )

        ids = results["ids"][0]
        distances = results["distances"][0]
        documents = results["documents"][0]

        for i, (incident_id, distance, document) in enumerate(
            zip(ids, distances, documents),
            start=1
        ):
            print(f"\n{i}. {incident_id}")
            print(f"Distance: {distance}")
            print(
                "Preview:",
                document[:200].replace("\n", " ")
            )


if __name__ == "__main__":
    main()