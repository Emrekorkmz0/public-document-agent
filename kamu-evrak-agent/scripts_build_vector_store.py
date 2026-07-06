from pathlib import Path
from services.vector_rag_service import VectorRAGService

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
VECTOR_DIR = BASE_DIR / "vector_store"

if __name__ == "__main__":
    source_dirs = [
        DATA_DIR / "regulations",
        DATA_DIR / "templates",
        DATA_DIR / "unit_definitions",
    ]
    rag = VectorRAGService(source_dirs=source_dirs, vector_store_dir=VECTOR_DIR)
    info = rag.build_index(force_rebuild=True)
    print("Vector store hazır:", info)
