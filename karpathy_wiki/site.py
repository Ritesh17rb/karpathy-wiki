from __future__ import annotations

import html
import json
import posixpath
import re
import shutil
from collections import defaultdict
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path, PurePosixPath

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

STUDENT_NAV_SLUGS = {"index", "areas"}

AUTOLINK_ALIAS_STOP_PHRASES = {
    "check understanding",
    "learning objectives",
    "see figure",
    "interactive link",
    "did you know",
    "chapter outline",
    "critical thinking",
}

AUTOLINK_SINGLE_TERM_STOP_WORDS = {
    "acid",
    "acids",
    "animal",
    "animals",
    "atom",
    "atoms",
    "bacteria",
    "blood",
    "body",
    "bone",
    "bones",
    "carbon",
    "cell",
    "cells",
    "chemical",
    "chemicals",
    "chromosome",
    "chromosomes",
    "compound",
    "compounds",
    "disease",
    "diseases",
    "electron",
    "electrons",
    "energy",
    "enzyme",
    "enzymes",
    "figure",
    "food",
    "gene",
    "genes",
    "growth",
    "heart",
    "hormone",
    "hormones",
    "infection",
    "infections",
    "light",
    "membrane",
    "molecule",
    "molecules",
    "muscle",
    "muscles",
    "nerve",
    "nerves",
    "nervous",
    "organ",
    "organs",
    "organism",
    "organisms",
    "oxygen",
    "plant",
    "plants",
    "population",
    "populations",
    "pressure",
    "protein",
    "proteins",
    "reaction",
    "reactions",
    "response",
    "responses",
    "section",
    "species",
    "system",
    "systems",
    "tissue",
    "tissues",
    "trait",
    "traits",
    "virus",
    "viruses",
    "water",
}

AUTOLINK_SINGLE_TERM_EXACT = {
    "adp",
    "atp",
    "cns",
    "dna",
    "mri",
    "mrna",
    "nadh",
    "nadph",
    "pcr",
    "pns",
    "rna",
    "trna",
}


def _site_identity(build_meta: dict[str, str | int | None]) -> dict[str, str]:
    source_file_name = str(build_meta.get("source_file_name") or "")
    if source_file_name.startswith("sources.openstax"):
        return {
            "site_title": "OpenStax Life Sciences Wiki",
            "site_caption": "a source-backed mini encyclopedia compiled from related OpenStax books",
        }
    return {
        "site_title": "Karpathy Wiki",
        "site_caption": "source-backed markdown wiki compiled from immutable PDFs",
    }


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


def _topic_autolink_terms(topic) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()

    def register(term: str) -> None:
        cleaned = " ".join(term.split()).strip(" ,.;:()[]{}")
        normalized = cleaned.casefold()
        if not cleaned or normalized in seen:
            return
        seen.add(normalized)
        terms.append(cleaned)

    register(topic.title)

    for phrase in topic.key_phrases[:12]:
        cleaned = " ".join(phrase.split()).strip(" ,.;:()[]{}")
        words = re.findall(r"[a-z0-9]+", cleaned.casefold())
        if len(cleaned) < 8 or len(words) < 2:
            continue
        if cleaned.casefold() in AUTOLINK_ALIAS_STOP_PHRASES:
            continue
        if all(len(word) <= 2 for word in words):
            continue
        register(cleaned)

    for keyword in topic.keywords[:10]:
        cleaned = " ".join(keyword.split()).strip(" ,.;:()[]{}")
        normalized = cleaned.casefold()
        words = re.findall(r"[a-z0-9]+", normalized)
        if len(words) != 1:
            continue
        token = words[0]
        if token in AUTOLINK_SINGLE_TERM_STOP_WORDS:
            continue
        if token in AUTOLINK_SINGLE_TERM_EXACT:
            register(cleaned)
            continue
        if len(token) >= 11 and token.isalpha():
            register(cleaned)
            continue
        if len(token) >= 8 and token.endswith(("sis", "tion", "ment", "tide", "zyme")):
            register(cleaned)

    return terms


def _portal_links(base_prefix: str, *, areas: list[str], families: list[str], years: list[str]) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    for area in areas:
        links.append(
            {
                "kind": "Area",
                "title": area,
                "url": f"{base_prefix}areas.html#{_slugify_fragment(area)}",
            }
        )
    for family in families:
        links.append(
            {
                "kind": "Family",
                "title": family,
                "url": f"{base_prefix}model-families.html#{_slugify_fragment(family)}",
            }
        )
    for year in years:
        links.append(
            {
                "kind": "Year",
                "title": year,
                "url": f"{base_prefix}chronology.html#{_slugify_fragment(year)}",
            }
        )
    return links


def _relative_page_url(current_url: str, target_url: str) -> str:
    current_dir = posixpath.dirname(current_url) or "."
    relative = posixpath.relpath(target_url, start=current_dir)
    return str(PurePosixPath(relative))


def _autolink_priority(kind: str) -> int:
    order = {
        "topic page": 0,
        "wiki page": 1,
        "source page": 2,
    }
    return order.get(kind, 99)


def _build_autolink_index(
    current_url: str,
    wiki_pages: list[dict[str, object]],
    topics: list,
    documents: list,
    include_kinds: tuple[str, ...] = ("topic page",),
) -> dict[str, object] | None:
    entries_by_title: dict[str, dict[str, str]] = {}
    canonical_topic_titles = {
        " ".join(topic.title.split()).casefold(): f"topics/{topic.topic_id}.html"
        for topic in topics
    }
    topic_terms_by_target: dict[str, list[str]] = {}
    alias_targets: defaultdict[str, set[str]] = defaultdict(set)

    def register(title: str, target_url: str, kind: str) -> None:
        normalized = " ".join(title.split()).casefold()
        if len(normalized) < 4:
            return
        existing = entries_by_title.get(normalized)
        if existing and _autolink_priority(existing["kind"]) <= _autolink_priority(kind):
            return
        relative_url = _relative_page_url(current_url, target_url)
        if relative_url in {"", "."}:
            return
        entries_by_title[normalized] = {
            "title": title,
            "url": relative_url,
            "kind": kind,
        }

    if "wiki page" in include_kinds:
        for page in wiki_pages:
            page_url = str(page["url"])
            if page_url != current_url:
                register(str(page["title"]), page_url, "wiki page")

    if "topic page" in include_kinds:
        for topic in topics:
            target_url = f"topics/{topic.topic_id}.html"
            if target_url != current_url:
                terms = _topic_autolink_terms(topic)
                topic_terms_by_target[target_url] = terms
                for index, term in enumerate(terms):
                    normalized = " ".join(term.split()).casefold()
                    if index > 0:
                        alias_targets[normalized].add(target_url)

        for topic in topics:
            target_url = f"topics/{topic.topic_id}.html"
            if target_url != current_url:
                for index, term in enumerate(topic_terms_by_target.get(target_url, [])):
                    normalized = " ".join(term.split()).casefold()
                    if index > 0 and canonical_topic_titles.get(normalized) not in {None, target_url}:
                        continue
                    if index > 0 and len(alias_targets.get(normalized, set())) > 1:
                        continue
                    register(term, target_url, "topic page")

    if "source page" in include_kinds:
        for document in documents:
            target_url = f"sources/{document.doc_id}.html"
            if target_url != current_url:
                register(document.title, target_url, "source page")

    if not entries_by_title:
        return None

    ordered_entries = sorted(
        entries_by_title.values(),
        key=lambda item: (-len(item["title"]), _autolink_priority(item["kind"]), item["title"].casefold()),
    )
    pattern = re.compile(
        r"(?<![A-Za-z0-9])(" + "|".join(re.escape(item["title"]) for item in ordered_entries) + r")(?![A-Za-z0-9])",
        flags=re.IGNORECASE,
    )
    return {
        "pattern": pattern,
        "entries": {item["title"].casefold(): item for item in ordered_entries},
    }


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


def _autolink_plain_text(text: str, autolink_index: dict[str, object] | None) -> str:
    if not text:
        return ""
    if not autolink_index:
        return html.escape(text)

    pattern = autolink_index["pattern"]
    entries = autolink_index["entries"]
    rendered: list[str] = []
    last_index = 0
    used_targets: set[str] = set()

    for match in pattern.finditer(text):
        matched_text = match.group(0)
        entry = entries.get(matched_text.casefold())
        if entry is None:
            continue
        rendered.append(html.escape(text[last_index : match.start()]))
        if entry["url"] in used_targets:
            rendered.append(html.escape(matched_text))
        else:
            rendered.append(
                f'<a class="wiki-link" href="{html.escape(entry["url"], quote=True)}">{html.escape(matched_text)}</a>'
            )
            used_targets.add(entry["url"])
        last_index = match.end()

    rendered.append(html.escape(text[last_index:]))
    return "".join(rendered)


def _render_inline_markdown(text: str, autolink_index: dict[str, object] | None = None) -> str:
    rendered: list[str] = []
    for token_type, value, href in _tokenize_inline_markdown(text):
        if token_type == "text":
            rendered.append(_autolink_plain_text(value, autolink_index))
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


def _markdown_to_html(markdown_text: str, autolink_index: dict[str, object] | None = None) -> str:
    rendered: list[str] = []
    paragraph: list[str] = []
    list_items: list[str] = []
    list_tag: str | None = None
    pending_anchor: str | None = None

    def flush_paragraph() -> None:
        nonlocal paragraph
        if not paragraph:
            return
        rendered.append(f"<p>{_render_inline_markdown(' '.join(paragraph), autolink_index)}</p>")
        paragraph = []

    def flush_list() -> None:
        nonlocal list_items, list_tag
        if not list_items or not list_tag:
            return
        rendered.append(f'<{list_tag} class="md-list">')
        for item in list_items:
            rendered.append(f"<li>{_render_inline_markdown(item, autolink_index)}</li>")
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
            "markdown_text": markdown_text,
            "summary": _first_markdown_paragraph(markdown_text),
            "headings": [item for item in headings if int(item["level"]) >= 2],
            "content_html": "",
        }
        pages.append(page)
        page_map[slug] = page
    return pages, page_map


def _load_markdown_page(
    markdown_path: Path,
    fallback_title: str,
    url: str,
    page_kind: str,
    autolink_index: dict[str, object] | None,
) -> dict[str, object]:
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
        "markdown_text": markdown_text,
        "summary": _first_markdown_paragraph(markdown_text),
        "headings": nav_headings,
        "content_html": _markdown_to_html(markdown_text, autolink_index),
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
    site_identity = _site_identity(build_meta)
    workspace_dir = site_dir.parent
    nav_pages, nav_page_map = _load_wiki_pages(workspace_dir)
    student_nav_pages = [page for page in nav_pages if str(page["slug"]) in STUDENT_NAV_SLUGS]

    document_map = {document.doc_id: document for document in documents}
    topic_map = {topic.topic_id: topic for topic in topics}

    topics_by_document: defaultdict[str, list] = defaultdict(list)
    for topic in topics:
        for doc_id in topic.document_ids:
            topics_by_document[doc_id].append(topic)

    search_index = []

    nav_autolink_indexes = {
        str(page["slug"]): _build_autolink_index(
            str(page["url"]),
            nav_pages,
            topics,
            documents,
            include_kinds=("topic page", "wiki page"),
        )
        for page in nav_pages
    }

    for page in nav_pages:
        page["content_html"] = _markdown_to_html(
            str(page["markdown_text"]),
            nav_autolink_indexes.get(str(page["slug"])),
        )

    topic_pages: dict[str, dict[str, object]] = {}
    for topic in topics:
        page = _load_markdown_page(
            workspace_dir / "wiki" / "topics" / f"{topic.topic_id}.md",
            topic.title,
            f"topics/{topic.topic_id}.html",
            "topic",
            _build_autolink_index(
                f"topics/{topic.topic_id}.html",
                nav_pages,
                topics,
                documents,
                include_kinds=("topic page",),
            ),
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
            _build_autolink_index(
                f"sources/{document.doc_id}.html",
                nav_pages,
                topics,
                documents,
                include_kinds=("topic page",),
            ),
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
    book_total = len({" — ".join(document.title.split(" — ", 1)[:1]) for document in documents})

    for topic in topics:
        page = topic_pages[topic.topic_id]
        coverage = _topic_coverage(topic, document_map)
        related_topic_links = [
            {"title": topic_pages[related_id]["title"], "url": f"../topics/{related_id}.html"}
            for related_id in topic.related_topics
            if related_id in topic_pages
        ]
        contributing_source_links = [
            {"title": source_pages[doc_id]["title"], "url": f"../sources/{doc_id}.html"}
            for doc_id in topic.document_ids[:6]
            if doc_id in source_pages
        ]
        evidence_links = [
            {
                "title": f"{item.doc_title}: {item.section_title}",
                "url": f"../sources/{item.doc_id}.html#{item.section_anchor}",
            }
            for item in topic.evidence[:6]
        ]
        rendered = markdown_template.render(
            page_title=f"{site_identity['site_title']} | {page['title']}",
            page=page,
            nav_pages=student_nav_pages,
            current_slug="topic",
            build_meta=build_meta,
            search_blob=search_blob,
            document_total=len(documents),
            section_total=len(sections),
            topic_total=len(topics),
            base_prefix="../",
            page_caption="topic synthesis with source-backed evidence",
            site_title=site_identity["site_title"],
            site_caption=site_identity["site_caption"],
            page_kicker="Topic article",
            explore_items=explore_items,
            related_links=related_topic_links + contributing_source_links,
            related_heading="Linked Pages",
            portal_links=_portal_links(
                "../",
                areas=coverage["areas"],
                families=coverage["families"],
                years=coverage["years"],
            ),
            evidence_links=evidence_links,
            hatnote_links=related_topic_links[:4],
            hatnote_heading="See also",
        )
        (site_dir / "topics" / f"{topic.topic_id}.html").write_text(rendered, encoding="utf-8")

    for document in documents:
        page = source_pages[document.doc_id]
        linked_topic_pages = [
            {"title": topic_map[topic_id].title, "url": f"../topics/{topic_id}.html"}
            for topic_id in document.topic_ids[:10]
            if topic_id in topic_map
        ]
        portal_links = _portal_links(
            "../",
            areas=[document.area] if document.area else [],
            families=document.families,
            years=[str(document.year)] if document.year is not None else [],
        )
        rendered = markdown_template.render(
            page_title=f"{site_identity['site_title']} | {page['title']}",
            page=page,
            nav_pages=student_nav_pages,
            current_slug="source",
            build_meta=build_meta,
            search_blob=search_blob,
            document_total=len(documents),
            section_total=len(sections),
            topic_total=len(topics),
            base_prefix="../",
            page_caption="source record derived from the immutable PDF corpus",
            site_title=site_identity["site_title"],
            site_caption=site_identity["site_caption"],
            page_kicker="Source article",
            explore_items=explore_items,
            related_links=linked_topic_pages,
            related_heading="Linked Topics",
            portal_links=portal_links,
            evidence_links=[],
            hatnote_links=linked_topic_pages[:4],
            hatnote_heading="See also",
        )
        (site_dir / "sources" / f"{document.doc_id}.html").write_text(rendered, encoding="utf-8")

    for page in nav_pages:
        template = index_template if page["slug"] == "index" else markdown_template
        rendered = template.render(
            page_title=f"{site_identity['site_title']} | {page['title']}",
            page=page,
            nav_pages=student_nav_pages,
            current_slug=page["slug"],
            build_meta=build_meta,
            search_blob=search_blob,
            document_total=len(documents),
            section_total=len(sections),
            topic_total=len(topics),
            base_prefix="",
            page_caption="wiki maintenance, navigation, and corpus structure",
            site_title=site_identity["site_title"],
            site_caption=site_identity["site_caption"],
            page_kicker="Wiki page",
            explore_items=explore_items,
            crosslink_total=crosslink_total,
            book_total=book_total,
            topic_hubs=views.get("topic_hubs", [])[:10],
            source_hubs=views.get("source_hubs", [])[:10],
            index_page=nav_page_map.get("index"),
            related_links=[],
            related_heading="Linked Articles",
            portal_links=[],
            evidence_links=[],
            hatnote_links=[],
            hatnote_heading="See also",
        )
        output_path = site_dir / ("index.html" if page["slug"] == "index" else f"{page['slug']}.html")
        output_path.write_text(rendered, encoding="utf-8")
