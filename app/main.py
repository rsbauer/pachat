from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from starlette.concurrency import run_in_threadpool

from config import settings
from database import init_db
from intake import encrypt_existing_documents
from routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await run_in_threadpool(init_db)
    if settings.FILE_ENCRYPTION_ENABLED:
        await run_in_threadpool(
            encrypt_existing_documents,
            settings.UPLOAD_DIR,
            settings.FILE_ENCRYPTION_KEY,
        )
    yield


app = FastAPI(title="Pachat", version="0.1.0", lifespan=lifespan)
app.include_router(router)

base_dir = Path(__file__).resolve().parent

app.mount("/static", StaticFiles(directory=base_dir / "static"), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(base_dir / "templates" / "index.html")


@app.get("/admin/")
async def admin_index() -> FileResponse:
    return FileResponse(base_dir / "templates" / "admin.html")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
