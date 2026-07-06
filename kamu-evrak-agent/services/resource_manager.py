from __future__ import annotations

import re
import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

RESOURCE_CATEGORIES: Dict[str, Dict[str, str]] = {
    "Mevzuat / Kural": {
        "folder": "regulations",
        "source_type": "regulation",
        "description": "Yönetmelik, yönerge, mevzuat özeti ve yazışma kuralları.",
    },
    "Yazı Şablonu": {
        "folder": "templates",
        "source_type": "template",
        "description": "Cevap yazısı, üst yazı, iç yönlendirme ve eksik bilgi talebi şablonları.",
    },
    "Birim Görev Tanımı": {
        "folder": "unit_definitions",
        "source_type": "unit_definition",
        "description": "Müdürlük/birim görev alanları ve yönlendirme kuralları.",
    },
    "Örnek Evrak": {
        "folder": "sample_documents",
        "source_type": "sample_document",
        "description": "Test ve demo için kullanılacak örnek evraklar.",
    },
}

TURKISH_MAP = str.maketrans({
    "ç": "c", "Ç": "c", "ğ": "g", "Ğ": "g", "ı": "i", "I": "i", "İ": "i",
    "ö": "o", "Ö": "o", "ş": "s", "Ş": "s", "ü": "u", "Ü": "u",
})


@dataclass
class ResourceFile:
    category: str
    folder: str
    file_name: str
    path: Path
    size_bytes: int
    modified_at: str
    preview: str

    def to_dict(self) -> Dict[str, str | int]:
        return {
            "category": self.category,
            "folder": self.folder,
            "file_name": self.file_name,
            "size_bytes": self.size_bytes,
            "modified_at": self.modified_at,
            "preview": self.preview,
            "path": str(self.path),
        }


def safe_slug(value: str, default: str = "kaynak") -> str:
    value = (value or default).translate(TURKISH_MAP).lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value or default


def category_folder(category: str) -> str:
    if category not in RESOURCE_CATEGORIES:
        raise ValueError(f"Bilinmeyen kaynak kategorisi: {category}")
    return RESOURCE_CATEGORIES[category]["folder"]


def ensure_resource_dirs(data_dir: Path) -> None:
    for info in RESOURCE_CATEGORIES.values():
        (data_dir / info["folder"]).mkdir(parents=True, exist_ok=True)


def list_resources(data_dir: Path) -> List[ResourceFile]:
    ensure_resource_dirs(data_dir)
    resources: List[ResourceFile] = []
    for category, info in RESOURCE_CATEGORIES.items():
        folder = info["folder"]
        folder_path = data_dir / folder
        for path in sorted(folder_path.glob("*.txt")):
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                text = ""
            stat = path.stat()
            resources.append(
                ResourceFile(
                    category=category,
                    folder=folder,
                    file_name=path.name,
                    path=path,
                    size_bytes=stat.st_size,
                    modified_at=datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                    preview=" ".join(text.strip().split())[:220],
                )
            )
    return resources


def count_resources_by_category(data_dir: Path) -> Dict[str, int]:
    counts = {category: 0 for category in RESOURCE_CATEGORIES}
    for res in list_resources(data_dir):
        counts[res.category] += 1
    return counts


def resolve_resource_path(data_dir: Path, category: str, file_name: str) -> Path:
    folder = category_folder(category)
    safe_name = Path(file_name).name
    if not safe_name.endswith(".txt"):
        safe_name += ".txt"
    path = (data_dir / folder / safe_name).resolve()
    root = (data_dir / folder).resolve()
    if root not in path.parents and path != root:
        raise ValueError("Geçersiz dosya yolu.")
    return path


def read_resource(data_dir: Path, category: str, file_name: str) -> str:
    path = resolve_resource_path(data_dir, category, file_name)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def save_resource(data_dir: Path, category: str, title: str, content: str, *, overwrite: bool = False, file_name: Optional[str] = None) -> Path:
    ensure_resource_dirs(data_dir)
    folder = category_folder(category)
    title_slug = safe_slug(file_name or title or "kaynak")
    if not title_slug.endswith(".txt"):
        title_slug += ".txt"
    path = data_dir / folder / title_slug

    if path.exists() and not overwrite:
        stem = path.stem
        suffix = path.suffix
        counter = 2
        while path.exists():
            path = data_dir / folder / f"{stem}_{counter}{suffix}"
            counter += 1

    text = (content or "").strip()
    if not text:
        raise ValueError("Kaynak içeriği boş olamaz.")
    path.write_text(text + "\n", encoding="utf-8")
    return path


def delete_resource(data_dir: Path, category: str, file_name: str, *, trash_dir: Optional[Path] = None) -> Path:
    path = resolve_resource_path(data_dir, category, file_name)
    if not path.exists():
        raise FileNotFoundError(f"Kaynak bulunamadı: {file_name}")
    if trash_dir is None:
        trash_dir = data_dir.parent / "outputs" / "deleted_resources"
    trash_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = trash_dir / f"{timestamp}_{path.name}"
    shutil.move(str(path), str(target))
    return target


def build_resources_zip(data_dir: Path) -> bytes:
    ensure_resource_dirs(data_dir)
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for res in list_resources(data_dir):
            arcname = f"{res.folder}/{res.file_name}"
            zf.write(res.path, arcname)
    buffer.seek(0)
    return buffer.getvalue()


def clear_vector_store(vector_store_dir: Path) -> int:
    vector_store_dir.mkdir(parents=True, exist_ok=True)
    removed = 0
    for path in vector_store_dir.iterdir():
        if path.name == ".gitkeep":
            continue
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        removed += 1
    return removed
