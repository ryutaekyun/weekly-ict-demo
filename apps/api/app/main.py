from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin_users, ai, auth, work_dashboard, candidates, card_news, dashboard, documents, editions, followups, issues, journal, journal_portal, manuscripts, reports, sources, users
from app.core.config import settings
from app.core.csrf import CSRFMiddleware
from app.core.deps import guard_external_users

app = FastAPI(title="TNP AI Platform API", version="0.1.0", dependencies=[Depends(guard_external_users)],
              docs_url=None if settings.app_env == "production" else "/docs", redoc_url=None, openapi_url=None if settings.app_env == "production" else "/openapi.json")

app.add_middleware(CSRFMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(admin_users.router)
app.include_router(ai.router)
app.include_router(candidates.router)
app.include_router(sources.router)
app.include_router(documents.router)
app.include_router(issues.router)
app.include_router(dashboard.router)
app.include_router(work_dashboard.router)
app.include_router(editions.router)
app.include_router(manuscripts.router)
app.include_router(users.router)
app.include_router(reports.router)
app.include_router(card_news.router)
app.include_router(followups.router)
app.include_router(journal.router)
app.include_router(journal_portal.router)
app.include_router(reports.template_router)


@app.get("/health")
def health():
    return {"status": "ok"}
