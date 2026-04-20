from __future__ import annotations

import html
import json
import re
import shutil
from collections import defaultdict
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape


WIKI_PAGE_SPECS = (
    ("index", "Corpus Index"),
    ("lint", "Maintenance Lint"),
    ("log", "Build Log"),
    ("areas", "Research Areas"),
    ("model-families", "Model Families"),
    ("chronology", "Chronology"),
    ("hubs", "Connectivity Hubs"),
)


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


def _search_type_priority(item: dict[str, object]) -> tuple[int, str]:
    order = {
        "topic page": 0,
        "source page": 1,
        "wiki page": 2,
    }
    item_type = str(item.get("type", ""))
    title = str(item.get("title", ""))
    return (order.get(item_type, 99), title.lower())


def _load_build_meta(site_dir: Path) -> dict[str, str | int | None]:
    workspace_dir = site_dir.parent
    manifest_path = workspace_dir / "build.json"
    log_path = workspace_dir / "wiki" / "log.md"
    meta: dict[str, str | int | None] = {
        "generated_at_display": None,
        "source_file": None,
        "source_file_name": None,
        "log_entries": 0,
        "latest_log_entry": None,
    }

    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        source_file = manifest.get("source_file")
        generated_at = manifest.get("generated_at")
        meta["source_file"] = source_file
        if source_file:
            meta["source_file_name"] = Path(source_file).name
        if generated_at:
            parsed = datetime.fromisoformat(generated_at).astimezone(timezone.utc)
            meta["generated_at_display"] = parsed.strftime("%Y-%m-%d %H:%M UTC")

    if log_path.exists():
        headings = [
            line[3:].strip()
            for line in log_path.read_text(encoding="utf-8").splitlines()
            if line.startswith("## ")
        ]
        meta["log_entries"] = len(headings)
        if headings:
            meta["latest_log_entry"] = headings[-1]

    return meta


def _topic_coverage(topic, document_map: dict[str, object]) -> dict[str, list[str]]:
    documents = [document_map[doc_id] for doc_id in topic.document_ids if doc_id in document_map]
    years = sorted({str(document.year) for document in documents if document.year is not None})
    areas = sorted({document.area for document in documents if document.area})
    families = sorted({family for document in documents for family in document.families})
    return {"years": years, "areas": areas, "families": families}


def _slugify_fragment(text: str) -> str:
    fragment = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return fragment or "section"


def _rewrite_wiki_target(target: str) -> str:
    match = re.match(r"^(.*?\.md)(#.*)?$", target)
    if match:
        base = match.group(1)[:-3] + ".html"
        fragment = match.group(2) or ""
        return base + fragment
    return target


def _tokenize_inline_markdown(text: str) -> list[tuple[str, str, str | None]]:
    tokens: list[tuple[str, str, str | None]] = []
    buffer: list[str] = []
    index = 0

    def flush_buffer() -> None:
        nonlocal buffer
        if buffer:
            tokens.append(("text", "".join(buffer), None))
            buffer = []

    while index < len(text):
        if text[index] == "`":
            end = text.find("`", index + 1)
            if end != -1:
                flush_buffer()
                tokens.append(("code", text[index + 1 : end], None))
                index = end + 1
                continue

        if text[index] == "[":
            label_end = index + 1
            bracket_depth = 1
            while label_end < len(text):
                if text[label_end] == "[":
                    bracket_depth += 1
                elif text[label_end] == "]":
                    bracket_depth -= 1
                    if bracket_depth == 0:
                        break
                label_end += 1
            if bracket_depth == 0 and label_end + 1 < len(text) and text[label_end + 1] == "(":
                href_end = label_end + 2
                paren_depth = 1
                while href_end < len(text):
                    if text[href_end] == "(":
                        paren_depth += 1
                    elif text[href_end] == ")":
                        paren_depth -= 1
                        if paren_depth == 0:
                            break
                    href_end += 1
                if paren_depth == 0:
                    flush_buffer()
                    tokens.append(
                        (
                            "link",
                            text[index + 1 : label_end],
                            text[label_end + 2 : href_end],
                        )
                    )
                    index = href_end + 1
                    continue

        buffer.append(text[index])
        index += 1

    flush_buffer()
    return tokens


def _plain_inline_markdown(text: str) -> str:
    plain_parts: list[str] = []
    for token_type, value, href in _tokenize_inline_markdown(text):
        if token_type == "link":
            plain_parts.append(_plain_inline_markdown(value))
        else:
            plain_parts.append(value)
    return "".join(plain_parts)


def _render_inline_markdown(text: str) -> str:
    rendered: list[str] = []
    for token_type, value, href in _tokenize_inline_markdown(text):
        if token_type == "text":
            rendered.append(html.escape(value))
        elif token_type == "code":
            rendered.append(f"<code>{html.escape(value)}</code>")
        else:
            label = html.escape(_plain_inline_markdown(value))
            target = html.escape(_rewrite_wiki_target(href or ""), quote=True)
            rendered.append(f'<a href="{target}">{label}</a>')
    return "".join(rendered)


def _extract_markdown_headings(markdown_text: str) -> list[dict[str, str | int]]:
    headings: list[dict[str, str | int]] = []
    pending_anchor: str | None = None
    for line in markdown_text.splitlines():
        stripped = line.strip()
        anchor_match = re.match(r'^<a\s+id="([^"]+)"></a>$', stripped)
        if anchor_match:
            pending_anchor = anchor_match.group(1)
            continue

        match = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if not match:
            continue
        title = match.group(2).strip()
        plain_title = _plain_inline_markdown(title).strip()
        headings.append(
            {
                "level": len(match.group(1)),
                "title": plain_title,
                "anchor": pending_anchor or _slugify_fragment(plain_title),
            }
        )
        pending_anchor = None
    return headings


def _first_markdown_paragraph(markdown_text: str) -> str:
    paragraph: list[str] = []
    for raw_line in markdown_text.splitlines():
        line = raw_line.strip()
        if not line:
            if paragraph:
                break
            continue
        if line.startswith("#") or line.startswith("- ") or re.match(r"^\d+\.\s+", line):
            if paragraph:
                break
            continue
        paragraph.append(line)
    return " ".join(paragraph)


def _markdown_to_html(markdown_text: str) -> str:
    rendered: list[str] = []
    paragraph: list[str] = []
    list_items: list[str] = []
    list_tag: str | None = None
    pending_anchor: str | None = None

    def flush_paragraph() -> None:
        nonlocal paragraph
        if not paragraph:
            return
        rendered.append(f"<p>{_render_inline_markdown(' '.join(paragraph))}</p>")
        paragraph = []

    def flush_list() -> None:
        nonlocal list_items, list_tag
        if not list_items or not list_tag:
            return
        rendered.append(f'<{list_tag} class="md-list">')
        for item in list_items:
            rendered.append(f"<li>{_render_inline_markdown(item)}</li>")
        rendered.append(f"</{list_tag}>")
        list_items = []
        list_tag = None

    def flush_pending_anchor() -> None:
        nonlocal pending_anchor
        if not pending_anchor:
            return
        rendered.append(f'<a id="{html.escape(pending_anchor, quote=True)}"></a>')
        pending_anchor = None

    for raw_line in markdown_text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            flush_list()
            continue

        anchor_match = re.match(r'^<a\s+id="([^"]+)"></a>$', stripped)
        if anchor_match:
            flush_paragraph()
            flush_list()
            pending_anchor = anchor_match.group(1)
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading_match:
            flush_paragraph()
            flush_list()
            level = len(heading_match.group(1))
            title = heading_match.group(2).strip()
            plain_title = _plain_inline_markdown(title).strip()
            anchor = pending_anchor or _slugify_fragment(plain_title)
            pending_anchor = None
            rendered.append(
                f'<h{level} id="{html.escape(anchor, quote=True)}">{_render_inline_markdown(title)}</h{level}>'
            )
            continue

        bullet_match = re.match(r"^-\s+(.*)$", stripped)
        ordered_match = re.match(r"^\d+\.\s+(.*)$", stripped)
        if bullet_match or ordered_match:
            flush_paragraph()
            flush_pending_anchor()
            next_tag = "ol" if ordered_match else "ul"
            if list_tag and list_tag != next_tag:
                flush_list()
            list_tag = next_tag
            list_items.append((ordered_match or bullet_match).group(1).strip())
            continue

        flush_pending_anchor()
        paragraph.append(stripped)

    flush_paragraph()
    flush_list()
    flush_pending_anchor()
    return "\n".join(rendered)


def _load_wiki_pages(workspace_dir: Path) -> tuple[list[dict[str, object]], dict[str, dict[str, object]]]:
    wiki_dir = workspace_dir / "wiki"
    pages: list[dict[str, object]] = []
    page_map: dict[str, dict[str, object]] = {}
    for slug, fallback_title in WIKI_PAGE_SPECS:
        markdown_path = wiki_dir / f"{slug}.md"
        if not markdown_path.exists():
            continue
        markdown_text = markdown_path.read_text(encoding="utf-8")
        headings = _extract_markdown_headings(markdown_text)
        title = str(headings[0]["title"]) if headings else fallback_title
        page = {
            "slug": slug,
            "title": title,
            "url": "index.html" if slug == "index" else f"{slug}.html",
            "markdown_path": markdown_path,
            "summary": _first_markdown_paragraph(markdown_text),
            "headings": [item for item in headings if int(item["level"]) >= 2],
            "content_html": _markdown_to_html(markdown_text),
        }
        pages.append(page)
        page_map[slug] = page
    return pages, page_map


def _load_markdown_page(markdown_path: Path, fallback_title: str, url: str, page_kind: str) -> dict[str, object]:
    markdown_text = markdown_path.read_text(encoding="utf-8")
    headings = _extract_markdown_headings(markdown_text)
    title = str(headings[0]["title"]) if headings else fallback_title
    if page_kind in {"topic", "source"}:
        nav_headings = [item for item in headings if int(item["level"]) == 2]
    else:
        nav_headings = [item for item in headings if int(item["level"]) >= 2]
    return {
        "slug": markdown_path.stem,
        "title": title,
        "url": url,
        "kind": page_kind,
        "markdown_path": markdown_path,
        "summary": _first_markdown_paragraph(markdown_text),
        "headings": nav_headings,
        "content_html": _markdown_to_html(markdown_text),
    }


def render_site(site_dir: Path, documents: list, sections: list, topics: list, views: dict[str, object]) -> None:
    site_dir.mkdir(parents=True, exist_ok=True)
    (site_dir / "topics").mkdir(exist_ok=True)
    (site_dir / "sources").mkdir(exist_ok=True)
    _copy_static(site_dir)

    env = _env()
    index_template = env.get_template("index.html.j2")
    markdown_template = env.get_template("markdown_page.html.j2")

    build_meta = _load_build_meta(site_dir)
    workspace_dir = site_dir.parent
    nav_pages, nav_page_map = _load_wiki_pages(workspace_dir)

    document_map = {document.doc_id: document for document in documents}

    topics_by_document: defaultdict[str, list] = defaultdict(list)
    for topic in topics:
        for doc_id in topic.document_ids:
            topics_by_document[doc_id].append(topic)

    search_index = []

    topic_pages: dict[str, dict[str, object]] = {}
    for topic in topics:
        page = _load_markdown_page(
            workspace_dir / "wiki" / "topics" / f"{topic.topic_id}.md",
            topic.title,
            f"topics/{topic.topic_id}.html",
            "topic",
        )
        topic_pages[topic.topic_id] = page
        coverage = _topic_coverage(topic, document_map)
        search_index.append(
            {
                "title": str(page["title"]),
                "type": "topic page",
                "url": f"topics/{topic.topic_id}.html",
                "summary": _safe_excerpt(str(page["summary"]), limit=220),
                "keywords": topic.keywords + topic.key_phrases + coverage["areas"] + coverage["families"] + coverage["years"],
            }
        )

    source_pages: dict[str, dict[str, object]] = {}
    for document in documents:
        page = _load_markdown_page(
            workspace_dir / "wiki" / "sources" / f"{document.doc_id}.md",
            document.title,
            f"sources/{document.doc_id}.html",
            "source",
        )
        source_pages[document.doc_id] = page
        search_index.append(
            {
                "title": str(page["title"]),
                "type": "source page",
                "url": f"sources/{document.doc_id}.html",
                "summary": _safe_excerpt(str(page["summary"]), limit=220),
                "keywords": document.keywords
                + [topic.title for topic in topics_by_document.get(document.doc_id, [])]
                + [document.area or ""]
                + document.families
                + document.tags
                + ([str(document.year)] if document.year is not None else []),
            }
        )

    for page in nav_pages:
        search_index.append(
            {
                "title": str(page["title"]),
                "type": "wiki page",
                "url": str(page["url"]),
                "summary": _safe_excerpt(str(page["summary"]), limit=220),
                "keywords": [str(page["title"])] + [str(item["title"]) for item in page["headings"][:8]],
            }
        )

    search_blob = json.dumps(search_index, ensure_ascii=False)
    explore_items = sorted(
        [item for item in search_index if item.get("type") in {"topic page", "source page"}],
        key=_search_type_priority,
    )[:8]
    crosslink_total = sum(len(topic.section_ids) for topic in topics)

    for topic in topics:
        page = topic_pages[topic.topic_id]
        rendered = markdown_template.render(
            page_title=f"Karpathy Wiki | {page['title']}",
            page=page,
            nav_pages=nav_pages,
            current_slug="topic",
            build_meta=build_meta,
            search_blob=search_blob,
            document_total=len(documents),
            section_total=len(sections),
            topic_total=len(topics),
            base_prefix="../",
            page_caption="topic synthesis with source-backed evidence",
            explore_items=explore_items,
        )
        (site_dir / "topics" / f"{topic.topic_id}.html").write_text(rendered, encoding="utf-8")

    for document in documents:
        page = source_pages[document.doc_id]
        rendered = markdown_template.render(
            page_title=f"Karpathy Wiki | {page['title']}",
            page=page,
            nav_pages=nav_pages,
            current_slug="source",
            build_meta=build_meta,
            search_blob=search_blob,
            document_total=len(documents),
            section_total=len(sections),
            topic_total=len(topics),
            base_prefix="../",
            page_caption="source record derived from the immutable PDF corpus",
            explore_items=explore_items,
        )
        (site_dir / "sources" / f"{document.doc_id}.html").write_text(rendered, encoding="utf-8")

    for page in nav_pages:
        template = index_template if page["slug"] == "index" else markdown_template
        rendered = template.render(
            page_title=f"Karpathy Wiki | {page['title']}",
            page=page,
            nav_pages=nav_pages,
            current_slug=page["slug"],
            build_meta=build_meta,
            search_blob=search_blob,
            document_total=len(documents),
            section_total=len(sections),
            topic_total=len(topics),
            base_prefix="",
            page_caption="wiki maintenance, navigation, and corpus structure",
            explore_items=explore_items,
            crosslink_total=crosslink_total,
            topic_hubs=views.get("topic_hubs", [])[:10],
            source_hubs=views.get("source_hubs", [])[:10],
            index_page=nav_page_map.get("index"),
        )
        output_path = site_dir / ("index.html" if page["slug"] == "index" else f"{page['slug']}.html")
        output_path.write_text(rendered, encoding="utf-8")
