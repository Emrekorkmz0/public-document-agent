from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


@dataclass
class RAGChunk:
    chunk_id: str
    title: str
    content: str
    file_name: str
    source_type: str
    source_path: str
    chunk_index: int


class VectorRAGService:
    """
    MVP-1 embedding tabanlı lokal RAG servisi.

    Çalışma mantığı:
    1. data/regulations, data/templates, data/unit_definitions klasörlerindeki .txt dosyalarını okur.
    2. Metinleri küçük parçalara böler.
    3. SentenceTransformer ile embedding üretir.
    4. Varsa FAISS index kullanır; yoksa numpy cosine similarity ile arama yapar.
    5. Kurulum veya model hatası olursa app.py tarafında eski TF-IDF servisine düşülebilir.
    """

    def __init__(
        self,
        source_dirs: List[Path],
        vector_store_dir: Path,
        model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        chunk_size: int = 900,
        chunk_overlap: int = 180,
    ):
        self.source_dirs = source_dirs
        self.vector_store_dir = vector_store_dir
        self.model_name = model_name
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

        self.vector_store_dir.mkdir(parents=True, exist_ok=True)
        self.chunks_path = self.vector_store_dir / "chunks.json"
        self.embeddings_path = self.vector_store_dir / "embeddings.npy"
        self.meta_path = self.vector_store_dir / "meta.json"
        self.faiss_index_path = self.vector_store_dir / "faiss.index"

        self._model = None
        self._faiss = None
        self._index = None
        self._chunks: List[RAGChunk] = []
        self._embeddings: Optional[np.ndarray] = None

    def _load_model(self):
        if self._model is not None:
            return self._model
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "Embedding RAG için sentence-transformers kurulu olmalı. "
                "Kurulum: pip install sentence-transformers"
            ) from exc

        self._model = SentenceTransformer(self.model_name)
        return self._model

    @staticmethod
    def _title_from_file(path: Path) -> str:
        return path.stem.replace("_", " ").replace("-", " ").title()

    def _source_type_from_folder(self, folder: Path) -> str:
        mapping = {
            "regulations": "mevzuat / yazışma kuralı",
            "templates": "yazı şablonu",
            "unit_definitions": "birim görev tanımı",
            "sample_documents": "örnek evrak",
        }
        return mapping.get(folder.name, folder.name)

    def _load_text_files(self) -> List[Dict[str, Any]]:
        docs: List[Dict[str, Any]] = []
        for folder in self.source_dirs:
            if not folder.exists():
                continue
            for path in sorted(folder.glob("*.txt")):
                content = path.read_text(encoding="utf-8", errors="ignore").strip()
                if not content:
                    continue
                docs.append(
                    {
                        "title": self._title_from_file(path),
                        "content": content,
                        "file_name": path.name,
                        "source_type": self._source_type_from_folder(folder),
                        "source_path": str(path),
                    }
                )
        return docs

    def _split_text(self, text: str) -> List[str]:
        text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
        if len(text) <= self.chunk_size:
            return [text]

        chunks: List[str] = []
        start = 0
        while start < len(text):
            end = min(start + self.chunk_size, len(text))
            raw_chunk = text[start:end]

            # Cümle ortasından kesmemek için son nokta veya satır sonuna geri kırp.
            if end < len(text):
                cut_candidates = [raw_chunk.rfind(". "), raw_chunk.rfind("\n"), raw_chunk.rfind("; ")]
                cut = max(cut_candidates)
                if cut > self.chunk_size * 0.55:
                    raw_chunk = raw_chunk[: cut + 1]
                    end = start + cut + 1

            chunk = raw_chunk.strip()
            if chunk:
                chunks.append(chunk)

            next_start = end - self.chunk_overlap
            if next_start <= start:
                next_start = end
            start = max(0, next_start)

        return chunks

    def build_chunks(self) -> List[RAGChunk]:
        docs = self._load_text_files()
        chunks: List[RAGChunk] = []
        for doc_idx, doc in enumerate(docs):
            pieces = self._split_text(doc["content"])
            for piece_idx, piece in enumerate(pieces):
                chunks.append(
                    RAGChunk(
                        chunk_id=f"doc{doc_idx:03d}_chunk{piece_idx:03d}",
                        title=doc["title"],
                        content=piece,
                        file_name=doc["file_name"],
                        source_type=doc["source_type"],
                        source_path=doc["source_path"],
                        chunk_index=piece_idx,
                    )
                )
        return chunks

    def build_index(self, force_rebuild: bool = False) -> Dict[str, Any]:
        if self.index_exists() and not force_rebuild:
            self.load_index()
            return {
                "status": "loaded_existing",
                "chunk_count": len(self._chunks),
                "backend": "faiss" if self._index is not None else "numpy",
                "model_name": self.model_name,
            }

        chunks = self.build_chunks()
        if not chunks:
            raise RuntimeError("RAG index oluşturmak için kaynak doküman bulunamadı.")

        model = self._load_model()
        texts = [chunk.content for chunk in chunks]
        embeddings = model.encode(
            texts,
            batch_size=16,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        ).astype("float32")

        self._chunks = chunks
        self._embeddings = embeddings

        self.chunks_path.write_text(
            json.dumps([asdict(chunk) for chunk in chunks], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        np.save(self.embeddings_path, embeddings)
        self.meta_path.write_text(
            json.dumps(
                {
                    "model_name": self.model_name,
                    "chunk_count": len(chunks),
                    "chunk_size": self.chunk_size,
                    "chunk_overlap": self.chunk_overlap,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        backend = "numpy"
        try:
            import faiss  # type: ignore

            index = faiss.IndexFlatIP(embeddings.shape[1])
            index.add(embeddings)
            faiss.write_index(index, str(self.faiss_index_path))
            self._faiss = faiss
            self._index = index
            backend = "faiss"
        except Exception:
            # Windows/Python sürümü uyumsuzsa FAISS olmadan numpy ile devam eder.
            self._faiss = None
            self._index = None

        return {
            "status": "rebuilt",
            "chunk_count": len(chunks),
            "backend": backend,
            "model_name": self.model_name,
        }

    def index_exists(self) -> bool:
        return self.chunks_path.exists() and self.embeddings_path.exists() and self.meta_path.exists()

    def load_index(self) -> None:
        if not self.index_exists():
            raise RuntimeError("Vektör index bulunamadı. Önce build_index() çalıştırılmalı.")

        raw_chunks = json.loads(self.chunks_path.read_text(encoding="utf-8"))
        self._chunks = [RAGChunk(**item) for item in raw_chunks]
        self._embeddings = np.load(self.embeddings_path).astype("float32")

        self._index = None
        self._faiss = None
        if self.faiss_index_path.exists():
            try:
                import faiss  # type: ignore

                self._faiss = faiss
                self._index = faiss.read_index(str(self.faiss_index_path))
            except Exception:
                self._index = None
                self._faiss = None

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        if not query.strip():
            return []

        if not self.index_exists():
            self.build_index(force_rebuild=True)
        elif not self._chunks or self._embeddings is None:
            self.load_index()

        model = self._load_model()
        query_embedding = model.encode(
            [query],
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        ).astype("float32")

        if self._index is not None:
            scores, indices = self._index.search(query_embedding, top_k)
            pairs = list(zip(indices[0].tolist(), scores[0].tolist()))
        else:
            assert self._embeddings is not None
            scores = (self._embeddings @ query_embedding[0]).astype(float)
            top_indices = np.argsort(scores)[::-1][:top_k]
            pairs = [(int(idx), float(scores[idx])) for idx in top_indices]

        results: List[Dict[str, Any]] = []
        for idx, score in pairs:
            if idx < 0 or idx >= len(self._chunks):
                continue
            chunk = self._chunks[idx]
            item = asdict(chunk)
            item["score"] = float(score)
            item["backend"] = "faiss" if self._index is not None else "numpy"
            results.append(item)

        return results
