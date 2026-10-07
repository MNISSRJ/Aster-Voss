"""Research paper ingestion, deduplication, and explainable internal ranking.

Ranking is deterministic and never calls an LLM. External metadata is treated
as untrusted source content; only bibliographic fields are retained.
"""
from __future__ import annotations

import hashlib
import math
import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any, Iterable

WEIGHTS = {
    "interest": 0.25,
    "novelty": 0.20,
    "influence": 0.15,
    "community": 0.15,
    "learning_direction": 0.10,
    "freshness": 0.15,
}
DEFAULT_REPEAT_PENALTY = 0.15
ARXIV_API = "https://export.arxiv.org/api/query"
S2_BATCH_API = "https://api.semanticscholar.org/graph/v1/paper/batch?fields=title,abstract,year,publicationDate,citationCount,influentialCitationCount,venue,externalIds,url"
ATOM = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
TOPICS = {
    "LLM": ("large language model", "llm", "language model", "pretraining", "instruction tuning"),
    "AI Agent": ("agent", "tool use", "tool calling", "planning", "multi-agent"),
    "RAG": ("retrieval augmented", "retrieval-augmented", "rag", "retrieval augmented generation"),
    "Multimodal": ("multimodal", "vision-language", "audio-language", "video-language"),
    "AI Safety": ("alignment", "safety", "robustness", "red teaming", "trustworthy"),
    "AI Coding": ("code generation", "program synthesis", "coding agent", "software engineering"),
    "ML": ("machine learning", "deep learning", "neural network", "optimization"),
    "新架构": ("architecture", "state space", "mixture of experts", "mamba", "transformer"),
    "Benchmark": ("benchmark", "evaluation", "dataset", "leaderboard"),
    "研究方法": ("method", "algorithm", "framework", "empirical study"),
}


def _clean(text: str) -> str:
    return " ".join((text or "").split())


def canonical_paper_id(item: dict[str, Any]) -> str:
    """Use DOI first, then arXiv base id, then a normalized title hash."""
    doi = _clean(str(item.get("doi", ""))).lower().removeprefix("https://doi.org/")
    if doi:
        return "doi:" + doi
    arxiv_id = _clean(str(item.get("arxiv_id", "")))
    if arxiv_id:
        return "arxiv:" + re.sub(r"v\d+$", "", arxiv_id)
    title = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", str(item.get("title_original") or item.get("title") or "").lower()).strip()
    return "title:" + hashlib.sha256(title.encode("utf-8")).hexdigest()[:24]


def parse_arxiv_atom(payload: bytes | str) -> list[dict[str, Any]]:
    """Parse an arXiv Atom response into compact metadata records."""
    root = ET.fromstring(payload)
    items = []
    for entry in root.findall("a:entry", ATOM):
        raw_id = _clean(entry.findtext("a:id", default="", namespaces=ATOM))
        match = re.search(r"/abs/([^?#]+)", raw_id)
        if not match:
            continue
        arxiv_id = match.group(1)
        title = _clean(entry.findtext("a:title", default="", namespaces=ATOM))
        abstract = _clean(entry.findtext("a:summary", default="", namespaces=ATOM))
        if not title:
            continue
        published = _clean(entry.findtext("a:published", default="", namespaces=ATOM))
        authors = [_clean(n.text or "") for n in entry.findall("a:author/a:name", ATOM) if _clean(n.text or "")]
        categories = [node.attrib.get("term", "") for node in entry.findall("a:category", ATOM) if node.attrib.get("term")]
        doi = _clean(entry.findtext("arxiv:doi", default="", namespaces=ATOM))
        items.append({
            "id": "arxiv:" + re.sub(r"v\d+$", "", arxiv_id),
            "arxiv_id": arxiv_id,
            "title_original": title,
            "summary_original": abstract[:6000],
            "authors": authors[:30],
            "topics": classify_topics(title + " " + abstract),
            "categories": categories[:8],
            "content_type": "论文",
            "published_at": published,
            "url": "https://arxiv.org/abs/" + arxiv_id,
            "source": "arXiv",
            "source_type": "paper",
            "doi": doi,
            "citation_count": None,
        })
    return items


def classify_topics(text: str) -> list[str]:
    lowered = (text or "").lower()
    return [topic for topic, terms in TOPICS.items() if any(term in lowered for term in terms)][:8]


def deduplicate_papers(papers: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge versions and duplicate source records, retaining the best metadata."""
    merged: dict[str, dict[str, Any]] = {}
    for source in papers:
        if not isinstance(source, dict):
            continue
        item = dict(source)
        key = canonical_paper_id(item)
        if not key or key == "title:" + hashlib.sha256(b"").hexdigest()[:24]:
            continue
        previous = merged.get(key)
        if previous is None:
            item["id"] = key
            item["source_list"] = sorted(set(item.get("source_list") or [item.get("source", "unknown")]))
            merged[key] = item
            continue
        # Latest arXiv version is retained while the first known publication date stays stable.
        if item.get("arxiv_id") and (not previous.get("arxiv_id") or _version(item["arxiv_id"]) > _version(previous["arxiv_id"])):
            for field in ("arxiv_id", "url", "published_at"):
                previous[field] = item.get(field) or previous.get(field)
        for field in ("authors", "topics", "categories"):
            previous[field] = list(dict.fromkeys((previous.get(field) or []) + (item.get(field) or [])))[:30 if field == "authors" else 8]
        if len(item.get("summary_original", "")) > len(previous.get("summary_original", "")):
            previous["summary_original"] = item["summary_original"][:6000]
        sources = set(previous.get("source_list", [])) | set(item.get("source_list") or [item.get("source", "unknown")])
        previous["source_list"] = sorted(s for s in sources if s)
        if item.get("citation_count") is not None:
            previous["citation_count"] = max(int(previous.get("citation_count") or 0), int(item["citation_count"]))
    return list(merged.values())


def _version(value: str) -> int:
    match = re.search(r"v(\d+)$", value)
    return int(match.group(1)) if match else 1


def _term_score(text: str, terms: Iterable[str]) -> float:
    terms = [term.lower().strip() for term in terms if str(term).strip()]
    if not terms:
        return 0.5
    lowered = text.lower()
    return min(1.0, sum(1 for term in terms if term in lowered) / min(3, len(terms)))


def score_paper(
    paper: dict[str, Any], *, interests: Iterable[str] = (), learning_directions: Iterable[str] = (),
    repeat_penalty: float = DEFAULT_REPEAT_PENALTY, now: datetime | None = None,
) -> tuple[float, dict[str, float]]:
    """Score a candidate from 0..1-weighted signals; missing signals stay neutral."""
    now = now or datetime.now(timezone.utc)
    text = " ".join(str(paper.get(field, "")) for field in ("title_original", "summary_original", "topics"))
    interest = _term_score(text, interests)
    novelty = _term_score(text, ("new", "novel", "first", "introduce", "newly", "首次", "新型"))
    citations = paper.get("citation_count")
    influence = min(1.0, math.log1p(max(0, int(citations or 0))) / math.log1p(1000)) if citations is not None else 0.5
    # There is no configured community-trend provider yet; neutral is honest, not a fabricated signal.
    community = 0.5
    learning = _term_score(text, learning_directions)
    date = _parse_datetime(paper.get("published_at"))
    age_days = max(0.0, (now - date).total_seconds() / 86400) if date else 90.0
    freshness = max(0.0, 1.0 - age_days / 180.0)
    components = {"interest": interest, "novelty": novelty, "influence": influence, "community": community, "learning_direction": learning, "freshness": freshness}
    base = sum(WEIGHTS[name] * components[name] for name in WEIGHTS)
    penalty = max(0.0, min(1.0, float(repeat_penalty))) if paper.get("seen_before") or paper.get("read") else 0.0
    return base - penalty, components


def _parse_datetime(value: Any) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def rank_papers(papers: Iterable[dict[str, Any]], **options) -> list[dict[str, Any]]:
    ranked = []
    for raw in papers:
        item = dict(raw)
        score, components = score_paper(item, **options)
        # score is internal only; API serializers omit it.
        item["_score"] = score
        item["_score_components"] = components
        item.setdefault("est_read_min", estimate_read_minutes(item))
        ranked.append(item)
    return sorted(ranked, key=lambda p: (p["_score"], p.get("published_at", "")), reverse=True)


def estimate_read_minutes(paper: dict[str, Any]) -> int:
    abstract_words = len(str(paper.get("summary_original", "")).split())
    return max(3, min(8, math.ceil(abstract_words / 110) + 2))


def knowledge_budget_items(ranked: list[dict[str, Any]], minutes: int) -> list[dict[str, Any]]:
    """Choose a soft number of papers from current rank; does not enforce total minutes."""
    target = 3 if minutes <= 10 else 6 if minutes <= 20 else 8
    return ranked[:target]


def search_pool(papers: Iterable[dict[str, Any]], query: str, limit: int = 50) -> list[dict[str, Any]]:
    terms = [part.lower() for part in re.findall(r"[\w\u4e00-\u9fff-]+", query or "") if part]
    if not terms:
        return []
    matches = []
    for item in papers:
        haystack = " ".join(str(item.get(key, "")) for key in ("title_original", "summary_original", "authors", "topics", "arxiv_id")).lower()
        if all(term in haystack for term in terms):
            matches.append(dict(item))
    return matches[:max(1, min(int(limit), 100))]


def fetch_arxiv(query: str = "cat:cs.AI OR cat:cs.CL OR cat:cs.LG OR cat:cs.CV OR cat:cs.SE OR cat:cs.RO OR cat:stat.ML", start: int = 0, limit: int = 500) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 500))
    params = urllib.parse.urlencode({"search_query": query, "start": max(0, int(start)), "max_results": limit, "sortBy": "submittedDate", "sortOrder": "descending"})
    request = urllib.request.Request(ARXIV_API + "?" + params, headers={"User-Agent": "Aster-Voss-Research/1.0 (contact: research@example.invalid)"})
    with urllib.request.urlopen(request, timeout=12) as response:
        return parse_arxiv_atom(response.read())


def fetch_semantic_scholar(arxiv_ids: list[str]) -> list[dict[str, Any]]:
    """Batch enrich arXiv records with S2 influence/venue metadata, when available."""
    ids = []
    for value in arxiv_ids[:500]:
        if value:
            ids.append("ARXIV:" + re.sub(r"v\d+$", "", value))
    if not ids:
        return []
    body = json.dumps({"ids": ids}).encode("utf-8")
    headers = {"Content-Type": "application/json", "User-Agent": "Aster-Voss-Research/1.0"}
    api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "").strip()
    if api_key:
        headers["x-api-key"] = api_key
    request = urllib.request.Request(S2_BATCH_API, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=12) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []

