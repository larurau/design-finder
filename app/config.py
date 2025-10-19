import os
from pathlib import Path

PHOTOS_DIR = Path(os.getenv("PHOTOS_DIR", "photos")).resolve()
DATA_DIR = Path(os.getenv("DATA_DIR", "data")).resolve()
THUMBS_DIR = DATA_DIR / "thumbs"
THUMB_SIZE = (512, 512)

THUMBS_DIR.mkdir(parents=True, exist_ok=True)