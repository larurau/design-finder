from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import *

from app.config import *
from app.gallery import *

app = FastAPI(title="Design Tinder (skeleton)")

BASE_DIR = os.path.dirname(__file__)
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)


@app.get("/healthz", response_class=PlainTextResponse)
async def healthz():
    return "ok"


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    cols = list_collections()
    cards = []
    for c in cols:
        imgs = list_images_in_collection(c)
        cards.append({
            "name": c.name,
            "first3": [p.name for p in imgs[:3]],
            "extra": max(0, len(imgs) - 3),
        })
    return templates.TemplateResponse("collections.html", {
        "request": request,
        "collections": cards
    })


@app.get("/api/ping", response_class=PlainTextResponse)
async def ping():
    return "pong"


@app.get("/collection/{collection}", response_class=HTMLResponse)
async def collection_detail(request: Request, collection: str):
    col_dir = (PHOTOS_DIR / collection).resolve()
    if not col_dir.exists() or not col_dir.is_dir() or str(col_dir).startswith(str(PHOTOS_DIR.resolve())) is False:
        raise HTTPException(status_code=404, detail="Collection not found")
    imgs = list_images_in_collection(col_dir)
    vm = [{"name": p.name, "url": f"/image/{collection}/{p.name}"} for p in imgs]
    return templates.TemplateResponse("collection.html", {"request": request, "collection": collection, "images": vm})


@app.get("/image/{collection}/{filename}")
async def image(collection: str, filename: str):
    col_dir = (PHOTOS_DIR / collection).resolve()
    if not col_dir.exists() or not col_dir.is_dir() or str(col_dir).startswith(str(PHOTOS_DIR.resolve())) is False:
        raise HTTPException(status_code=404, detail="Collection not found")
    src = (col_dir / filename).resolve()
    # path traversal guard: src must be within col_dir
    if not src.exists() or not src.is_file() or str(src).startswith(str(col_dir)) is False:
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(src)


@app.get("/thumb/{collection}/{filename}")
async def thumb_in_collection(collection: str, filename: str):
    col_dir = (PHOTOS_DIR / collection).resolve()
    if not col_dir.exists() or not col_dir.is_dir() or not str(col_dir).startswith(str(PHOTOS_DIR.resolve())):
        raise HTTPException(status_code=404, detail="Collection not found")
    src = (col_dir / filename).resolve()
    if not src.exists() or not src.is_file() or not str(src).startswith(str(col_dir)):
        raise HTTPException(status_code=404, detail="Image not found")
    out = ensure_thumb(src)
    return FileResponse(out)
