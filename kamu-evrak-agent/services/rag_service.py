from pathlib import Path
from typing import List, Dict, Any


class LocalRAGService:
    """
    İlk MVP için basit RAG servisi.
    Şimdilik TF-IDF benzerliği kullanır.
    Sonraki aşamada embedding + vector DB ile değiştirilebilir.
    """

    def __init__(self, source_dirs: List[Path]):
        self.documents = self._load_documents(source_dirs)

    def _load_documents(self, source_dirs: List[Path]) -> List[Dict[str, Any]]:
        docs = []
        for folder in source_dirs:
            if not folder.exists():
                continue
            for path in folder.glob("*.txt"):
                content = path.read_text(encoding="utf-8", errors="ignore").strip()
                if not content:
                    continue
                source_type = folder.name
                docs.append({
                    "title": self._title_from_file(path),
                    "content": content,
                    "file_name": path.name,
                    "source_type": source_type,
                })
        return docs

    @staticmethod
    def _title_from_file(path: Path) -> str:
        return path.stem.replace("_", " ").replace("-", " ").title()

    def search(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        if not self.documents:
            return []

        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.metrics.pairwise import cosine_similarity
        except ImportError as exc:
            raise RuntimeError("Basit RAG için scikit-learn kurulu olmalı: pip install scikit-learn") from exc

        corpus = [doc["content"] for doc in self.documents]
        vectorizer = TfidfVectorizer(lowercase=True, ngram_range=(1, 2))
        matrix = vectorizer.fit_transform(corpus + [query])
        doc_vectors = matrix[:-1]
        query_vector = matrix[-1]
        scores = cosine_similarity(query_vector, doc_vectors).flatten()

        ranked = sorted(enumerate(scores), key=lambda item: item[1], reverse=True)
        results = []
        for idx, score in ranked[:top_k]:
            doc = self.documents[idx].copy()
            doc["score"] = float(score)
            results.append(doc)
        return results
