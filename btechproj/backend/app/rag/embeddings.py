from sentence_transformers import SentenceTransformer


class EmbeddingService:
    """
    Generates semantic embeddings for incident documents
    and investigation queries.
    """

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2"
    ):
        print(
            f"Loading embedding model: {model_name}"
        )

        self.model = SentenceTransformer(
            model_name
        )

        print("Embedding model loaded successfully.")

    def embed_text(self, text: str):
        """
        Convert one piece of text into an embedding vector.
        """

        if not text or not text.strip():
            raise ValueError(
                "Cannot generate embedding for empty text."
            )

        embedding = self.model.encode(
            text,
            convert_to_numpy=True
        )

        return embedding.tolist()

    def embed_documents(self, documents):
        """
        Generate embeddings for multiple documents.
        """

        if not documents:
            return []

        embeddings = self.model.encode(
            documents,
            convert_to_numpy=True
        )

        return embeddings.tolist()