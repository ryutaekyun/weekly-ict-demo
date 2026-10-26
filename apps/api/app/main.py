from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, candidates, card_news, dashboard, documents, editions, issues, manuscripts, reports, sources, users
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
app.include_router(documents.router)
app.include_router(issues.router)
app.include_router(dashboard.router)
app.include_router(editions.router)
app.include_router(manuscripts.router)
app.include_router(users.router)
app.include_router(reports.router)
app.include_router(card_news.router)
app.include_router(reports.template_router)


@app.get("/health")
def health():
    return {"status": "ok"}
