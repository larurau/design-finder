from pathlib import Path
from typing import List, Optional
from app.config import PHOTOS_DIR
from app.thumbnailer import is_image, ensure_thumb

def list_collections() -> List[Path]:
    """Immediate subfolders of PHOTOS_DIR that contain at least one image."""
    if not PHOTOS_DIR.exists():
        return []
    cols = []
    for p in PHOTOS_DIR.iterdir():
        if p.is_dir():
            if any(is_image(f) for f in p.iterdir() if f.is_file()):
                cols.append(p)
    cols.sort(key=lambda p: p.name.lower())
    return cols

def cover_image_for(collection_dir: Path) -> Optional[Path]:
    """Pick a stable cover: first image sorted by name."""
    imgs = [f for f in collection_dir.iterdir() if f.is_file() and is_image(f)]
    if not imgs:
        return None
    imgs.sort(key=lambda f: f.name.lower())
    return imgs[0]

def list_images_in_collection(collection_dir: Path) -> List[Path]:
    imgs = [f for f in collection_dir.iterdir() if f.is_file() and is_image(f)]
    imgs.sort(key=lambda f: f.name.lower())
    return imgs
