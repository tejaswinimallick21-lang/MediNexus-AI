"""
Vector Embedding and Space Representation for MediNexus AI RAG.
Uses TF-IDF and n-gram term frequency representations for robust, fast, local offline execution.
"""

from typing import List, Dict, Any, Tuple
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


class LocalVectorStore:
    """
    Lightweight, embedded in-memory vector store for healthcare knowledge chunks.
    """

    def __init__(self):
        self.vectorizer = TfidfVectorizer(
            stop_words="english",
            ngram_range=(1, 2),
            sublinear_tf=True,
        )
        self.chunks: List[Dict[str, Any]] = []
        self.tfidf_matrix = None
        self.is_indexed = False

    def build_index(self, chunks: List[Dict[str, Any]]) -> int:
        """Index a list of chunks and compute the term-document matrix."""
        if not chunks:
            return 0
        self.chunks = chunks
        corpus = [c["text"] for c in chunks]
        self.tfidf_matrix = self.vectorizer.fit_transform(corpus)
        self.is_indexed = True
        return len(chunks)

    def search(self, query: str, top_k: int = 3) -> List[Tuple[Dict[str, Any], float]]:
        """Search top-k most similar chunks for a given query."""
        if not self.is_indexed or not query.strip():
            return []

        query_vec = self.vectorizer.transform([query])
        similarities = cosine_similarity(query_vec, self.tfidf_matrix)[0]

        top_indices = np.argsort(similarities)[::-1][:top_k]
        results = []
        for idx in top_indices:
            score = float(similarities[idx])
            if score > 0.05:  # Relevance threshold
                results.append((self.chunks[idx], round(score, 3)))

        return results
