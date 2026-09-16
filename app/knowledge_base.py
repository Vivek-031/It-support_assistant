import json
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import KBArticle
from app.retrieval import Article

SEED_FILE = Path(__file__).with_name("kb_seed.json")


def seed_knowledge_base(db: Session) -> int:
    if db.scalar(select(func.count()).select_from(KBArticle)):
        return 0
    rows = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    db.add_all([KBArticle(**row) for row in rows])
    db.commit()
    return len(rows)


def load_articles(db: Session) -> list[Article]:
    rows = db.scalars(select(KBArticle).order_by(KBArticle.id)).all()
    return [
        Article(
            id=row.id,
            title=row.title,
            category=row.category,
            keywords=row.keywords,
            problem=row.problem,
            solution=row.solution,
        )
        for row in rows
    ]
