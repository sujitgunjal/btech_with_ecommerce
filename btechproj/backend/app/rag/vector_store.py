import chromadb
from pathlib import Path


class VectorStore:
    """
    Persistent ChromaDB vector store for historical DevOps incidents.
    """

    def __init__(self):
        project_root = Path(__file__).resolve().parents[2]
        chroma_path = project_root / "data" / "chroma"

        chroma_path.mkdir(parents=True, exist_ok=True)

        print(f"Initializing ChromaDB at: {chroma_path}")

        self.client = chromadb.PersistentClient(
            path=str(chroma_path)
        )

        self.collection = self.client.get_or_create_collection(
            name="historical_incidents"
        )

        print(
            f"ChromaDB collection loaded. "
            f"Documents: {self.collection.count()}"
        )

    def add_incidents(self, incidents):
        """
        Add historical incidents to ChromaDB.
        """

        if not incidents:
            return

        ids = []
        documents = []
        embeddings = []
        metadatas = []

        for incident in incidents:
            ids.append(incident["id"])
            documents.append(incident["text"])
            embeddings.append(incident["embedding"])
            metadatas.append(incident["metadata"])

        self.collection.upsert(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )

        print(f"Stored {len(incidents)} incidents in ChromaDB.")

    def search(self, query_embedding, top_k=3):
        """
        Search historical incidents using semantic similarity.
        """

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
        )

        return results