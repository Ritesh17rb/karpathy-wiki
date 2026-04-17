from __future__ import annotations

import json
import shutil
from importlib import resources
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape


def _env() -> Environment:
    template_dir = resources.files("karpathy_wiki").joinpath("templates")
    return Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _copy_static(out_dir: Path) -> None:
    static_dir = resources.files("karpathy_wiki").joinpath("static")
    for name in ("style.css", "search.js"):
        src = static_dir / name
        shutil.copyfile(src, out_dir / name)


def _safe_excerpt(text: str, limit: int = 280) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1].rstrip() + "…"


def render_site(site_dir: Path, documents: list, sections: list, topics: list) -> None:
    site_dir.mkdir(parents=True, exist_ok=True)
    (site_dir / "topics").mkdir(exist_ok=True)
    (site_dir / "sources").mkdir(exist_ok=True)
    _copy_static(site_dir)

    env = _env()
    topic_template = env.get_template("topic.html.j2")
    doc_template = env.get_template("document.html.j2")
    index_template = env.get_template("index.html.j2")

    section_map = {section.section_id: section for section in sections}
    document_map = {document.doc_id: document for document in documents}
    topic_map = {topic.topic_id: topic for topic in topics}

    search_index = []

    for topic in topics:
        related = [topic_map[item] for item in topic.related_topics if item in topic_map]
        topic_sections = [section_map[section_id] for section_id in topic.section_ids]
        topic_documents = [document_map[doc_id] for doc_id in topic.document_ids]
        rendered = topic_template.render(
            page_title=topic.title,
            topic=topic,
            related=related,
            sections=topic_sections,
            documents=topic_documents,
            document_map=document_map,
            excerpt=_safe_excerpt,
        )
        (site_dir / "topics" / f"{topic.topic_id}.html").write_text(rendered, encoding="utf-8")
        search_index.append(
            {
                "title": topic.title,
                "type": "topic",
                "url": f"topics/{topic.topic_id}.html",
                "summary": topic.summary,
                "keywords": topic.keywords,
            }
        )

    for document in documents:
        doc_sections = [section_map[section_id] for section_id in document.section_ids]
        doc_topics = [topic for topic in topics if document.doc_id in topic.document_ids]
        rendered = doc_template.render(
            page_title=document.title,
            document=document,
            sections=doc_sections,
            topics=doc_topics,
            excerpt=_safe_excerpt,
        )
        (site_dir / "sources" / f"{document.doc_id}.html").write_text(rendered, encoding="utf-8")
        search_index.append(
            {
                "title": document.title,
                "type": "source",
                "url": f"sources/{document.doc_id}.html",
                "summary": document.summary,
                "keywords": [],
            }
        )

    topic_cards = []
    for topic in sorted(topics, key=lambda item: item.title.lower()):
        topic_cards.append(
            {
                "topic_id": topic.topic_id,
                "title": topic.title,
                "summary": topic.summary,
                "keywords": topic.keywords[:6],
                "document_count": len(topic.document_ids),
                "section_count": len(topic.section_ids),
            }
        )

    document_cards = []
    for document in sorted(documents, key=lambda item: item.title.lower()):
        document_cards.append(
            {
                "doc_id": document.doc_id,
                "title": document.title,
                "summary": document.summary,
                "section_count": document.section_count,
                "page_count": document.page_count,
            }
        )

    index_html = index_template.render(
        page_title="Knowledge Index",
        topic_cards=topic_cards,
        document_cards=document_cards,
        topic_total=len(topics),
        document_total=len(documents),
        section_total=len(sections),
        search_blob=json.dumps(search_index, ensure_ascii=False),
    )
    (site_dir / "index.html").write_text(index_html, encoding="utf-8")
