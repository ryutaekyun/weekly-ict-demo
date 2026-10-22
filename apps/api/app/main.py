from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, candidates, sources
from app.core.config import settings
from app.core.csrf import CSRFMiddleware

app = FastAPI(title="TNP AI Platform API", version="0.1.0")

app.add_middleware(CSRFMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(candidates.router)
app.include_router(sources.router)


@app.get("/health")
def health():
    return {"status": "ok"}
