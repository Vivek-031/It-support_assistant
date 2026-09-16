import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import BASE_DIR, settings
from app.database import Base, SessionLocal, engine, get_db
from app.knowledge_base import load_articles, seed_knowledge_base
from app.llm import LLMError, generate_answer
from app.models import KBArticle, Ticket
from app.retrieval import KnowledgeBaseIndex, format_context
from app.schemas import KBArticleOut, KBSearchResult, TicketCreate, TicketOut, TicketSummary

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("it_support")

FRONTEND_DIR = BASE_DIR / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seeded = seed_knowledge_base(db)
        articles = load_articles(db)
    if seeded:
        logger.info("Seeded %d knowledge base articles", seeded)
    app.state.kb_index = KnowledgeBaseIndex(articles)
    if not settings.llm_api_key:
        logger.warning("No API key configured for LLM_PROVIDER=%s", settings.llm_provider)
    yield


app = FastAPI(title="AI IT Support Assistant", version="1.0.0", lifespan=lifespan)


def get_kb_index(request: Request) -> KnowledgeBaseIndex:
    return request.app.state.kb_index


@app.get("/api/health")
def health(index: KnowledgeBaseIndex = Depends(get_kb_index)):
    return {
        "status": "ok",
        "llm_provider": settings.llm_provider,
        "llm_configured": bool(settings.llm_api_key),
        "kb_articles": len(index.articles),
    }


@app.post("/api/tickets", response_model=TicketOut, status_code=201)
def create_ticket(
    payload: TicketCreate,
    db: Session = Depends(get_db),
    index: KnowledgeBaseIndex = Depends(get_kb_index),
):
    matches = index.search(payload.question, top_k=settings.kb_top_k)
    ticket = Ticket(
        question=payload.question,
        status="open",
        retrieved_context=format_context(matches),
        sources=[
            {
                "id": m.article.id,
                "title": m.article.title,
                "category": m.article.category,
                "score": round(m.score, 2),
            }
            for m in matches
        ],
    )
    # Persist before calling the LLM so the ticket survives an AI failure.
    db.add(ticket)
    db.commit()

    try:
        answer = generate_answer(ticket.question, ticket.retrieved_context)
    except LLMError as exc:
        ticket.status = "failed"
        ticket.error_message = str(exc)
        db.commit()
        raise HTTPException(
            status_code=exc.status_code,
            detail={"message": str(exc), "ticket_id": ticket.id},
        ) from exc

    ticket.ai_response = answer
    ticket.llm_provider = settings.llm_provider
    ticket.status = "answered"
    db.commit()
    db.refresh(ticket)
    return ticket


@app.get("/api/tickets", response_model=list[TicketSummary])
def list_tickets(limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    return db.scalars(select(Ticket).order_by(Ticket.id.desc()).limit(limit)).all()


@app.get("/api/tickets/{ticket_id}", response_model=TicketOut)
def get_ticket(ticket_id: int, db: Session = Depends(get_db)):
    ticket = db.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found.")
    return ticket


@app.get("/api/kb", response_model=list[KBArticleOut])
def list_kb_articles(db: Session = Depends(get_db)):
    return db.scalars(select(KBArticle).order_by(KBArticle.id)).all()


@app.get("/api/kb/search", response_model=list[KBSearchResult])
def search_kb(
    q: str = Query(..., min_length=2, max_length=200),
    index: KnowledgeBaseIndex = Depends(get_kb_index),
):
    return [
        KBSearchResult(
            id=m.article.id,
            title=m.article.title,
            category=m.article.category,
            score=round(m.score, 2),
            solution=m.article.solution,
        )
        for m in index.search(q, top_k=5)
    ]


# Mounted last so the /api routes above take precedence.
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
