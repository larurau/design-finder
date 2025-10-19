from fastapi import FastAPI, Request, HTTPException, Form
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import *

from app.config import *
from app.gallery import *
from app.db import init as db_init, get_db
from app.thumbnailer import ensure_thumb

app = FastAPI(title="Design Tinder (skeleton)")

BASE_DIR = os.path.dirname(__file__)
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

db_init()


def _active_refinements():
    with get_db() as db:
        return db.execute("SELECT id, name FROM refinements WHERE status='active' ORDER BY id DESC").fetchall()


def _root_collection_for_refinement(rid: int) -> str:
    """Follow the refinement chain to the original folder name (source_key of the root 'collection')."""
    seen = set()
    current = rid
    for _ in range(32):  # safety cap
        if current in seen:
            raise HTTPException(500, "Refinement cycle detected")
        seen.add(current)
        with get_db() as db:
            ref = db.execute("SELECT source_type, source_key FROM refinements WHERE id=?", (current,)).fetchone()
            if not ref:
                raise HTTPException(404, "Refinement not found")
            if ref["source_type"] == "collection":
                return ref["source_key"]  # folder name
            # else it's sourced from another refinement
            try:
                current = int(ref["source_key"])
            except ValueError:
                raise HTTPException(500, "Invalid refinement chain")
    raise HTTPException(500, "Refinement chain too deep")


@app.get("/healthz", response_class=PlainTextResponse)
async def healthz():
    return "ok"


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    # --- physical collections
    cols = list_collections()
    cards = []
    for c in cols:
        imgs = list_images_in_collection(c)
        thumbs = [f"/thumb/{c.name}/{p.name}" for p in imgs[:3]]
        cards.append({
            "kind": "folder",
            "name": c.name,
            "href": f"/collection/{c.name}",
            "refine_href": f"/refine/start/{c.name}",
            "first3": thumbs,
            "extra": max(0, len(imgs) - 3),
        })

    # --- completed refinements as virtual collections
    with get_db() as db:
        completed = db.execute(
            "SELECT id, name FROM refinements WHERE status='complete' ORDER BY id DESC"
        ).fetchall()

    for ref in completed:
        # all YES images
        with get_db() as db:
            rows = db.execute(
                "SELECT relpath FROM refinement_items WHERE refinement_id=? AND rating='yes' ORDER BY id",
                (ref["id"],),
            ).fetchall()
        rels = [r["relpath"] for r in rows]

        # ✅ resolve the ORIGINAL folder for URL building
        root_folder = _root_collection_for_refinement(ref["id"])
        thumbs = [f"/thumb/{root_folder}/{r}" for r in rels[:3]]

        cards.append({
            "kind": "refinement",
            "name": ref["name"],
            "href": f"/collection/from-refinement/{ref['id']}",
            "refine_href": f"/refine/start/ref/{ref['id']}",
            "first3": thumbs,
            "extra": max(0, len(rels) - 3),
        })

    return templates.TemplateResponse("collections.html", {
        "request": request,
        "collections": cards,
        # ✅ show the 'Active refinements' section again
        "refinements": _active_refinements(),
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


@app.get("/refine/start/{collection}", response_class=HTMLResponse)
async def refine_start(request: Request, collection: str):
    suggested = f"{collection}-refine"
    return templates.TemplateResponse("refine_start.html", {
        "request": request, "collection": collection, "suggested": suggested
    })


@app.post("/refine/create")
async def refine_create(collection: str = Form(...), name: str = Form(...)):
    with get_db() as db:
        cur = db.execute(
            "INSERT INTO refinements(name, source_type, source_key) VALUES(?, 'collection', ?)",
            (name, collection)
        )
        rid = cur.lastrowid
        col_dir = PHOTOS_DIR / collection
        from app.thumbnailer import is_image
        rels = [p.name for p in col_dir.iterdir() if p.is_file() and is_image(p)]
        rels.sort()
        db.executemany(
            "INSERT INTO refinement_items(refinement_id, relpath) VALUES(?, ?)",
            [(rid, r) for r in rels]
        )
    return RedirectResponse(url=f"/refine/{rid}", status_code=303)


def _next_item(db, rid: int):
    row = db.execute(
        "SELECT id, relpath FROM refinement_items WHERE refinement_id=? AND rating IS NULL ORDER BY id LIMIT 1",
        (rid,)
    ).fetchone()
    if row: return row
    # if none pending, see if any 'skip' exist and reset them to NULL to retry
    skipped = db.execute(
        "SELECT COUNT(*) AS c FROM refinement_items WHERE refinement_id=? AND rating='skip'",
        (rid,)
    ).fetchone()["c"]
    if skipped > 0:
        db.execute("UPDATE refinement_items SET rating=NULL WHERE refinement_id=? AND rating='skip'", (rid,))
        return db.execute(
            "SELECT id, relpath FROM refinement_items WHERE refinement_id=? AND rating IS NULL ORDER BY id LIMIT 1",
            (rid,)
        ).fetchone()
    return None


@app.get("/refine/{rid}", response_class=HTMLResponse)
async def refine_view(request: Request, rid: int):
    with get_db() as db:
        ref = db.execute("SELECT * FROM refinements WHERE id=?", (rid,)).fetchone()
        if not ref: raise HTTPException(404, "Refinement not found")

        item = _next_item(db, rid)
        if not item:
            # nothing pending -> mark complete and go to the new collection
            db.execute("UPDATE refinements SET status='complete' WHERE id=?", (rid,))
            return RedirectResponse(url=f"/collection/from-refinement/{rid}", status_code=303)

        # build image URL for the pending item
        root_folder = _root_collection_for_refinement(ref["id"])  # ✅
        url = f"/image/{root_folder}/{item['relpath']}"
        thumb = f"/thumb/{root_folder}/{item['relpath']}"
        return templates.TemplateResponse("refine.html", {
            "request": request,
            "ref": ref,
            "item": {"id": item["id"], "relpath": item["relpath"], "url": url, "thumb": thumb}
        })


@app.post("/refine/{rid}/rate", response_class=HTMLResponse)
async def refine_rate(
        request: Request,  # ✅ add this
        rid: int,
        item_id: int = Form(...),
        action: str = Form(...)
):
    if action not in ("yes", "no", "skip"):
        raise HTTPException(400, "Invalid action")

    with get_db() as db:
        # update rating
        db.execute(
            "UPDATE refinement_items SET rating=? WHERE id=? AND refinement_id=?",
            (action, item_id, rid)
        )

        # next item (or recycle skips → NULL→pending)
        next_item = _next_item(db, rid)

        # if nothing left, show a small done panel fragment
        if not next_item:
            db.execute("UPDATE refinements SET status='complete' WHERE id=?", (rid,))
            return HTMLResponse("", headers={"HX-Redirect": f"/collection/from-refinement/{rid}"})

        # we still have an item → render just the item fragment
        ref = db.execute("SELECT * FROM refinements WHERE id=?", (rid,)).fetchone()
        root_folder = _root_collection_for_refinement(ref["id"])
        item_ctx = {
            "id": next_item["id"],
            "relpath": next_item["relpath"],
            "url": f"/image/{root_folder}/{next_item['relpath']}",
            "thumb": f"/thumb/{root_folder}/{next_item['relpath']}",
        }

        # ✅ pass the real request + ref so the form action has the right rid
        return templates.TemplateResponse(
            "_refine_item.html",
            {
                "request": request,
                "ref": ref,
                "item": item_ctx,
            },
        )


@app.get("/collection/from-refinement/{rid}", response_class=HTMLResponse)
async def collection_from_refinement(request: Request, rid: int):
    with get_db() as db:
        ref = db.execute("SELECT * FROM refinements WHERE id=?", (rid,)).fetchone()
        if not ref: raise HTTPException(404, "Refinement not found")
        rows = db.execute(
            "SELECT relpath FROM refinement_items WHERE refinement_id=? AND rating='yes' ORDER BY id",
            (rid,)
        ).fetchall()
        root_folder = _root_collection_for_refinement(rid)
        images = [{"name": r["relpath"], "url": f"/image/{root_folder}/{r['relpath']}"} for r in rows]
    # reuse collection template
    return templates.TemplateResponse("collection.html", {
        "request": request,
        "collection": ref["name"],
        "images": images
    })


@app.get("/refine/start/ref/{rid}", response_class=HTMLResponse)
async def refine_start_from_ref(request: Request, rid: int):
    with get_db() as db:
        ref = db.execute("SELECT * FROM refinements WHERE id=?", (rid,)).fetchone()
        if not ref: raise HTTPException(404, "Refinement not found")
    suggested = f"{ref['name']}-refine"
    return templates.TemplateResponse("refine_start_ref.html", {
        "request": request, "rid": rid, "suggested": suggested
    })


@app.post("/refine/create_ref")
async def refine_create_from_ref(rid: int = Form(...), name: str = Form(...)):
    with get_db() as db:
        # new refinement sourced from previous refinement's YES items
        cur = db.execute(
            "INSERT INTO refinements(name, source_type, source_key) VALUES(?, 'refinement', ?)",
            (name, str(rid))
        )
        new_id = cur.lastrowid
        yes_rows = db.execute(
            "SELECT relpath FROM refinement_items WHERE refinement_id=? AND rating='yes' ORDER BY id",
            (rid,)
        ).fetchall()
        db.executemany(
            "INSERT INTO refinement_items(refinement_id, relpath) VALUES(?, ?)",
            [(new_id, r["relpath"]) for r in yes_rows]
        )
    return RedirectResponse(url=f"/refine/{new_id}", status_code=303)
