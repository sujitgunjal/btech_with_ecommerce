from app.rag.embeddings import EmbeddingService
import numpy as np


def cosine_similarity(a, b):

    a = np.array(a)
    b = np.array(b)

    return np.dot(a, b) / (
        np.linalg.norm(a) *
        np.linalg.norm(b)
    )


def main():

    embedding_service = EmbeddingService()

    text1 = (
        "PostgreSQL database connection timeout "
        "in order service."
    )

    text2 = (
        "Order service cannot connect to the "
        "PostgreSQL database."
    )

    text3 = (
        "The order service is experiencing "
        "extremely high CPU utilization."
    )

    embeddings = embedding_service.embed_documents(
        [
            text1,
            text2,
            text3
        ]
    )

    similarity_1_2 = cosine_similarity(
        embeddings[0],
        embeddings[1]
    )

    similarity_1_3 = cosine_similarity(
        embeddings[0],
        embeddings[2]
    )

    print("=" * 60)
    print("Semantic Similarity Test")
    print("=" * 60)

    print(
        f"\nDatabase ↔ Database: "
        f"{similarity_1_2:.4f}"
    )

    print(
        f"Database ↔ CPU: "
        f"{similarity_1_3:.4f}"
    )


if __name__ == "__main__":
    main()