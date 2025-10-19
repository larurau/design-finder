from pathlib import Path
from PIL import Image
import hashlib
from .config import THUMBS_DIR, THUMB_SIZE

ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

def is_image(path: Path) -> bool:

    return path.suffix.lower() in ALLOWED_EXTS

def thumb_key(source: Path) -> str:
    h = hashlib.sha256()
    h.update(str(source).encode("utf-8"))
    h.update(f"{THUMBS_DIR}:{THUMB_SIZE}".encode("utf-8"))
    return h.hexdigest() + ".jpg"

def ensure_thumb(source: Path) -> Path:
    out = THUMBS_DIR / thumb_key(source)
    if out.exists():
        return out
    with Image.open(source) as im:
        im = im.convert("RGB")
        im.thumbnail(THUMB_SIZE)
        out.parent.mkdir(parents=True, exist_ok=True)
        im.save(out, "JPEG", quality=85, optimize=True)
    return out
