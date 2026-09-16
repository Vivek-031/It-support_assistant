"""Keyword retrieval over the knowledge base using BM25 (no external dependencies)."""

import math
import re
from collections import Counter
from dataclasses import dataclass

TOKEN_RE = re.compile(r"[a-z0-9]+")

STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "is", "are", "was", "were", "be", "been", "am",
    "i", "im", "my", "me", "we", "our", "you", "your", "it", "its", "this", "that", "these",
    "to", "of", "in", "on", "for", "with", "at", "by", "from", "as", "into", "up", "out",
    "can", "cannot", "cant", "could", "will", "won", "wont", "would", "should", "not", "no",
    "do", "does", "did", "dont", "doesn", "didn", "have", "has", "had", "how", "what", "why",
    "when", "where", "which", "who", "there", "get", "got", "keep", "keeps", "just", "so",
    "if", "any", "all", "some", "after", "again", "now", "please", "help", "issue", "issues",
    "problem", "problems", "working", "trying", "tried", "anymore", "still", "very",
}


def _stem(token: str) -> str:
    for suffix in ("ing", "ed", "s"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            if suffix == "s" and token.endswith("ss"):
                continue
            return token[: -len(suffix)]
    return token


def tokenize(text: str) -> list[str]:
    return [
        _stem(tok)
        for tok in TOKEN_RE.findall(text.lower())
        if len(tok) > 1 and tok not in STOPWORDS
    ]


@dataclass(frozen=True)
class Article:
    id: int
    title: str
    category: str
    keywords: str
    problem: str
    solution: str


@dataclass(frozen=True)
class Match:
    article: Article
    score: float


def _document_text(article: Article) -> str:
    # Title and keywords are repeated so they weigh more than body text.
    return " ".join(
        [article.title] * 2 + [article.keywords] * 2 + [article.problem, article.solution]
    )


class KnowledgeBaseIndex:
    def __init__(self, articles: list[Article], k1: float = 1.5, b: float = 0.75) -> None:
        self.articles = articles
        self.k1 = k1
        self.b = b
        self.term_freqs = [Counter(tokenize(_document_text(a))) for a in articles]
        self.doc_lengths = [sum(tf.values()) for tf in self.term_freqs]
        self.avg_length = (sum(self.doc_lengths) / len(articles)) if articles else 1.0

        doc_freq: Counter[str] = Counter()
        for tf in self.term_freqs:
            doc_freq.update(tf.keys())
        n = len(articles)
        self.idf = {
            term: math.log(1 + (n - df + 0.5) / (df + 0.5)) for term, df in doc_freq.items()
        }

    def search(self, query: str, top_k: int = 3, min_score: float = 1.0) -> list[Match]:
        query_terms = set(tokenize(query))
        matches = []
        for article, tf, length in zip(self.articles, self.term_freqs, self.doc_lengths):
            score = 0.0
            for term in query_terms:
                freq = tf.get(term)
                if not freq:
                    continue
                norm = self.k1 * (1 - self.b + self.b * length / self.avg_length)
                score += self.idf[term] * freq * (self.k1 + 1) / (freq + norm)
            if score >= min_score:
                matches.append(Match(article=article, score=score))
        matches.sort(key=lambda m: m.score, reverse=True)
        return matches[:top_k]


def format_context(matches: list[Match]) -> str:
    if not matches:
        return "No matching knowledge base articles were found."
    return "\n\n".join(
        f"[KB-{m.article.id}] {m.article.title} (category: {m.article.category})\n"
        f"Problem: {m.article.problem}\n"
        f"Solution:\n{m.article.solution}"
        for m in matches
    )
