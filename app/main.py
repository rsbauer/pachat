from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from routes import router

app = FastAPI(title="Pachat", version="0.1.0")
app.include_router(router)

base_dir = Path(__file__).resolve().parent

app.mount("/static", StaticFiles(directory=base_dir / "static"), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(base_dir / "templates" / "index.html")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
