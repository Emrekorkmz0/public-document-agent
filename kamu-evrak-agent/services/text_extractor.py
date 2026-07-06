from io import BytesIO
from typing import Tuple, Dict, Any


def extract_text_from_uploaded_file(uploaded_file) -> Tuple[str, Dict[str, Any]]:
    """Streamlit UploadedFile nesnesinden metin çıkarır."""
    file_name = uploaded_file.name
    file_type = uploaded_file.type or "unknown"
    suffix = file_name.lower().split(".")[-1]
    raw = uploaded_file.getvalue()

    meta = {
        "file_name": file_name,
        "file_type": file_type,
        "page_count": None,
    }

    if suffix == "txt":
        return raw.decode("utf-8", errors="ignore"), meta

    if suffix == "pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError("PDF okumak için pypdf kurulu olmalı: pip install pypdf") from exc

        reader = PdfReader(BytesIO(raw))
        meta["page_count"] = len(reader.pages)
        texts = []
        for page in reader.pages:
            texts.append(page.extract_text() or "")
        text = "\n\n".join(texts).strip()
        if not text:
            raise RuntimeError(
                "Bu PDF metin katmanı içermiyor olabilir. Taranmış PDF için OCR modülü eklenmeli."
            )
        return text, meta

    if suffix == "docx":
        try:
            from docx import Document
        except ImportError as exc:
            raise RuntimeError("DOCX okumak için python-docx kurulu olmalı: pip install python-docx") from exc

        doc = Document(BytesIO(raw))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n".join(paragraphs), meta

    raise RuntimeError(f"Desteklenmeyen dosya türü: {suffix}")
