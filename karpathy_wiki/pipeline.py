from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

import requests

from .site import render_site


STOPWORDS = {
    "about", "above", "after", "again", "against", "all", "also", "among", "an", "and",
    "any", "are", "around", "as", "at", "be", "because", "been", "before", "being",
    "between", "both", "but", "by", "can", "could", "did", "do", "does", "done", "down",
    "during", "each", "few", "for", "from", "further", "had", "has", "have", "having",
    "he", "her", "here", "hers", "him", "his", "how", "however", "i", "if", "in", "into",
    "is", "it", "its", "itself", "just", "many", "may", "me", "might", "more", "most",
    "much", "must", "my", "need", "no", "nor", "not", "now", "of", "off", "on", "once",
    "one", "only", "or", "other", "our", "out", "over", "own", "same", "she", "should",
    "so", "some", "such", "than", "that", "the", "their", "them", "then", "there",
    "these", "they", "this", "those", "through", "to", "too", "under", "until", "up",
    "use", "used", "using", "very", "was", "we", "were", "what", "when", "where", "which",
    "while", "who", "why", "will", "with", "within", "without", "would", "you", "your",
}


GENERIC_TITLES = {
    "abstract",
    "average",
    "introduction",
    "conclusion",
    "contents",
    "references",
    "appendix",
    "related work",
    "background",
    "discussion",
    "results",
    "method",
    "methods",
    "approach",
    "evaluation",
}


NOISY_TITLE_PATTERNS = (
    r"^references?$",
    r"^bibliography$",
    r"^acknowledg",
    r"^appendix",
    r"^supplement",
    r"^contributions?$",
    r"^figure\s",
    r"^table\s",
    r"^context\s",
    r"^correct answer",
    r"^incorrect answer",
    r"^target completion",
)


@dataclass
class SourceSpec:
    url: str
    title: str | None = None


@dataclass
class Document:
    doc_id: str
    title: str
    url: str
    pdf_path: str
    text_path: str
    section_count: int
    page_count: int
    summary: str
    section_ids: list[str]


@dataclass
class Section:
    section_id: str
    doc_id: str
    doc_title: str
    title: str
    start_page: int
    end_page: int
    text: str
    token_count: int
    keywords: list[str]


@dataclass
class Topic:
    topic_id: str
    title: str
    keywords: list[str]
    summary: str
    section_ids: list[str]
    document_ids: list[str]
    related_topics: list[str]


def slugify(value: str) -> str:
    clean = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return clean or "item"


def normalize_whitespace(text: str) -> str:
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def read_sources(path: Path) -> list[SourceSpec]:
    specs: list[SourceSpec] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "|" in line:
            url, title = [part.strip() for part in line.split("|", 1)]
            specs.append(SourceSpec(url=url, title=title or None))
        else:
            specs.append(SourceSpec(url=line))
    return specs


def ensure_dirs(workspace: Path) -> dict[str, Path]:
    paths = {
        "workspace": workspace,
        "raw": workspace / "raw",
        "extracted": workspace / "extracted",
        "wiki": workspace / "wiki",
        "site": workspace / "site",
        "topics": workspace / "wiki" / "topics",
        "sources": workspace / "wiki" / "sources",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


def clean_generated_dirs(paths: dict[str, Path]) -> None:
    for directory, suffix in (
        (paths["topics"], ".md"),
        (paths["sources"], ".md"),
        (paths["site"] / "topics", ".html"),
        (paths["site"] / "sources", ".html"),
    ):
        directory.mkdir(parents=True, exist_ok=True)
        for item in directory.glob(f"*{suffix}"):
            item.unlink()


def publish_site(site_dir: Path, publish_dir: Path) -> None:
    publish_dir.mkdir(parents=True, exist_ok=True)
    for name in ("index.html", "style.css", "search.js", ".nojekyll"):
        target = publish_dir / name
        if target.exists():
            target.unlink()
    for name in ("topics", "sources"):
        target_dir = publish_dir / name
        if target_dir.exists():
            shutil.rmtree(target_dir)
    for item in site_dir.iterdir():
        target = publish_dir / item.name
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)
    (publish_dir / ".nojekyll").write_text("", encoding="utf-8")


def filename_from_url(url: str) -> str:
    parsed = urlparse(url)
    name = Path(parsed.path).name or "document.pdf"
    if not name.lower().endswith(".pdf"):
        name = f"{name}.pdf"
    return name


def download_pdf(spec: SourceSpec, raw_dir: Path, force: bool) -> Path:
    base_name = spec.title or Path(filename_from_url(spec.url)).stem
    pdf_path = raw_dir / f"{slugify(base_name)}.pdf"
    if pdf_path.exists() and not force:
        return pdf_path
    response = requests.get(spec.url, timeout=60)
    response.raise_for_status()
    if not response.content.startswith(b"%PDF"):
        raise ValueError(f"URL did not return a PDF: {spec.url}")
    pdf_path.write_bytes(response.content)
    return pdf_path


def extract_pdf_text(pdf_path: Path, output_path: Path, force: bool) -> str:
    if output_path.exists() and not force:
        return output_path.read_text(encoding="utf-8")
    result = subprocess.run(
        ["pdftotext", "-layout", str(pdf_path), "-"],
        check=True,
        capture_output=True,
    )
    text = result.stdout.decode("utf-8", errors="ignore")
    output_path.write_text(text, encoding="utf-8")
    return text


def guess_document_title(spec: SourceSpec, pages: list[str]) -> str:
    if spec.title:
        return spec.title
    for line in pages[0].splitlines()[:20]:
        stripped = " ".join(line.split())
        if looks_like_heading(stripped, allow_generic=True):
            return stripped
    return Path(filename_from_url(spec.url)).stem.replace("-", " ").title()


def clean_page_text(page: str) -> str:
    lines = [line.rstrip() for line in page.splitlines()]
    cleaned = "\n".join(line for line in lines if line.strip())
    return normalize_whitespace(cleaned)


def looks_like_heading(line: str, allow_generic: bool = False) -> bool:
    if not line:
        return False
    line = " ".join(line.split())
    if len(line) < 3 or len(line) > 110:
        return False
    if line.endswith(".") or line.endswith(","):
        return False
    if sum(char.isalpha() for char in line) < 4:
        return False
    if re.search(r"[>@]|https?://", line):
        return False
    if re.match(r"^(figure|table)\b", line, flags=re.IGNORECASE):
        return False
    if line.count(",") >= 2:
        return False
    alpha_ratio = sum(char.isalpha() for char in line) / max(len(line), 1)
    if alpha_ratio < 0.55:
        return False
    if re.match(r"^\d+$", line):
        return False
    words = line.split()
    if len(words) > 14:
        return False
    if re.match(r"^(chapter|section|appendix)\b", line, flags=re.IGNORECASE):
        return True
    if re.match(r"^[ivxlcdm]+[.)]?\s+[A-Za-z]", line, flags=re.IGNORECASE):
        return True
    if re.match(r"^\d+(\.\d+)*[.)]?\s+[A-Za-z]", line):
        return True
    alpha_words = [word for word in words if re.search(r"[A-Za-z]", word)]
    if not alpha_words:
        return False
    title_like = sum(word[0].isupper() for word in alpha_words if word[0].isalpha()) / max(len(alpha_words), 1)
    upper_like = line == line.upper() and len(alpha_words) <= 10
    generic = line.lower() in GENERIC_TITLES
    return upper_like or title_like >= 0.7 or (allow_generic and generic)


def top_heading_candidate(page_text: str) -> str | None:
    lines = []
    for raw_line in page_text.splitlines()[:18]:
        line = " ".join(raw_line.split())
        if not line:
            continue
        lines.append(line)
    for line in lines:
        if looks_like_heading(line):
            return line
    return None


def tokenise(text: str) -> list[str]:
    return [token for token in re.findall(r"[a-zA-Z]{3,}", text.lower()) if token not in STOPWORDS]


def normalize_title(title: str) -> str:
    title = re.sub(r"^\d+(\.\d+)*[.)]?\s*", "", title).strip()
    title = re.sub(r"^[ivxlcdm]+[.)]?\s*", "", title, flags=re.IGNORECASE).strip()
    return title


def title_is_generic(title: str) -> bool:
    normalized = normalize_title(title).lower()
    return normalized in GENERIC_TITLES


def title_is_noisy(title: str) -> bool:
    normalized = normalize_title(title)
    lowered = normalized.lower()
    if len(normalized) > 90:
        return True
    first_alpha = next((char for char in normalized if char.isalpha()), "")
    if first_alpha and first_alpha.islower():
        return True
    if len(normalized.split()) > 8:
        return True
    if re.search(r"[\[\]+]", normalized):
        return True
    words = re.findall(r"[A-Za-z]+", lowered)
    if words and len(set(words)) / len(words) < 0.65:
        return True
    return any(re.search(pattern, lowered) for pattern in NOISY_TITLE_PATTERNS)


def section_text_is_noisy(text: str) -> bool:
    lowered = text.lower()
    noisy_markers = (
        lowered.count("correct answer")
        + lowered.count("incorrect answer")
        + lowered.count("target completion")
        + lowered.count("figure g.")
        + lowered.count("appendix")
    )
    citation_markers = lowered.count("arxiv") + lowered.count("proceedings of") + lowered.count("et al")
    arrow_markers = lowered.count("→") + lowered.count("->")
    if noisy_markers >= 3:
        return True
    if citation_markers >= 4:
        return True
    if arrow_markers >= 6:
        return True
    if "this appendix" in lowered or "appendix contains" in lowered:
        return True
    if lowered.count("figure ") >= 12:
        return True
    return False


def extract_keywords(text: str, limit: int = 8) -> list[str]:
    counts = Counter(tokenise(text))
    return [word for word, _ in counts.most_common(limit)]


def fallback_section_slices(pages: list[str]) -> list[tuple[str, int, int]]:
    slices: list[tuple[str, int, int]] = []
    cursor = 0
    block = 4
    part = 1
    while cursor < len(pages):
        end = min(len(pages), cursor + block)
        slices.append((f"Part {part:02d}", cursor, end - 1))
        cursor = end
        part += 1
    return slices


def segment_sections(doc_id: str, doc_title: str, pages: list[str]) -> list[Section]:
    candidates = [top_heading_candidate(page) for page in pages]
    counts = Counter(candidate for candidate in candidates if candidate)
    cut_points: list[tuple[str, int]] = []
    for page_index, candidate in enumerate(candidates):
        if not candidate:
            continue
        if counts[candidate] > max(2, len(pages) // 5):
            continue
        cut_points.append((candidate, page_index))

    if not cut_points:
        cut_ranges = fallback_section_slices(pages)
    else:
        cut_ranges = []
        starts = [(title, page) for title, page in cut_points]
        if starts[0][1] != 0:
            starts.insert(0, ("Overview", 0))
        for idx, (title, start_page) in enumerate(starts):
            end_page = starts[idx + 1][1] - 1 if idx + 1 < len(starts) else len(pages) - 1
            cut_ranges.append((title, start_page, end_page))

    sections: list[Section] = []
    for idx, (title, start_page, end_page) in enumerate(cut_ranges, start=1):
        body = "\n\n".join(clean_page_text(page) for page in pages[start_page : end_page + 1]).strip()
        if len(body) < 400:
            continue
        keywords = extract_keywords(f"{title}\n{body}")
        section_title = title
        if section_title.lower() in {"overview", "part", "part 01"}:
            section_title = f"{doc_title}: Overview"
        section_id = slugify(f"{doc_id}-{idx}-{section_title}")[:80]
        sections.append(
            Section(
                section_id=section_id,
                doc_id=doc_id,
                doc_title=doc_title,
                title=section_title,
                start_page=start_page + 1,
                end_page=end_page + 1,
                text=body,
                token_count=len(tokenise(body)),
                keywords=keywords,
            )
        )

    if not sections:
        whole_text = "\n\n".join(clean_page_text(page) for page in pages).strip()
        sections.append(
            Section(
                section_id=slugify(f"{doc_id}-full-text"),
                doc_id=doc_id,
                doc_title=doc_title,
                title=f"{doc_title}: Full Text",
                start_page=1,
                end_page=len(pages),
                text=whole_text,
                token_count=len(tokenise(whole_text)),
                keywords=extract_keywords(whole_text),
            )
        )
    return sections


def compute_tfidf(sections: list[Section]) -> dict[str, dict[str, float]]:
    doc_tokens: dict[str, Counter[str]] = {}
    df: Counter[str] = Counter()
    for section in sections:
        tokens = tokenise(f"{section.title}\n{section.text}")
        counts = Counter(tokens)
        doc_tokens[section.section_id] = counts
        df.update(counts.keys())
    total_docs = max(len(sections), 1)
    vectors: dict[str, dict[str, float]] = {}
    for section_id, counts in doc_tokens.items():
        vector: dict[str, float] = {}
        for token, tf in counts.items():
            idf = math.log((1 + total_docs) / (1 + df[token])) + 1
            vector[token] = (1 + math.log(tf)) * idf
        vectors[section_id] = vector
    return vectors


def cosine_similarity(left: dict[str, float], right: dict[str, float]) -> float:
    if not left or not right:
        return 0.0
    if len(left) > len(right):
        left, right = right, left
    numerator = sum(weight * right.get(token, 0.0) for token, weight in left.items())
    if numerator <= 0:
        return 0.0
    left_norm = math.sqrt(sum(weight * weight for weight in left.values()))
    right_norm = math.sqrt(sum(weight * weight for weight in right.values()))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def average_vectors(vectors: Iterable[dict[str, float]]) -> dict[str, float]:
    totals: defaultdict[str, float] = defaultdict(float)
    count = 0
    for vector in vectors:
        count += 1
        for token, weight in vector.items():
            totals[token] += weight
    if count == 0:
        return {}
    return {token: weight / count for token, weight in totals.items()}


def choose_topic_title(sections: list[Section], vectors: dict[str, dict[str, float]]) -> tuple[str, list[str]]:
    cluster_vector = average_vectors(vectors[section.section_id] for section in sections)
    ranked_terms = [token for token, _ in sorted(cluster_vector.items(), key=lambda item: item[1], reverse=True)]
    keywords = ranked_terms[:8]

    best_section = None
    best_score = -1.0
    for section in sections:
        score = cosine_similarity(vectors[section.section_id], cluster_vector)
        if score > best_score:
            best_score = score
            best_section = section

    title = normalize_title(best_section.title) if best_section else "Topic"
    prefer_keywords = (
        title_is_generic(title)
        or title_is_noisy(title)
        or title.lower().endswith(": overview")
        or title.lower().startswith("part ")
        or len({section.doc_id for section in sections}) > 1
    )
    if prefer_keywords:
        title = " / ".join(word.title() for word in keywords[:3]) or "Synthesized Topic"
    return title, keywords


def split_sentences(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return []
    parts = re.split(r"(?<=[.!?])\s+", normalized)
    return [part.strip() for part in parts if 40 <= len(part.strip()) <= 280]


def summarize_text(title: str, text: str, keywords: list[str], sentence_limit: int = 4) -> str:
    sentences = split_sentences(text)
    if not sentences:
        return text[:400].strip()
    freq = Counter(tokenise(text))
    scored: list[tuple[float, str]] = []
    for sentence in sentences[:120]:
        tokens = tokenise(sentence)
        score = sum(freq[token] for token in tokens)
        score += sum(3 for keyword in keywords[:6] if keyword in sentence.lower())
        if title and title.lower() in sentence.lower():
            score += 5
        scored.append((score / max(len(tokens), 1), sentence))
    picked = [sentence for _, sentence in sorted(scored, reverse=True)[: sentence_limit * 2]]
    ordered = []
    seen = set()
    for sentence in sentences:
        if sentence in picked and sentence not in seen:
            ordered.append(sentence)
            seen.add(sentence)
        if len(ordered) >= sentence_limit:
            break
    return " ".join(ordered)


def cluster_sections(sections: list[Section]) -> list[list[Section]]:
    if len(sections) <= 3:
        return [[section] for section in sections]

    vectors = compute_tfidf(sections)
    target_clusters = max(4, round(len(sections) ** 0.6))
    ordered_sections = sorted(sections, key=lambda section: section.token_count, reverse=True)
    assignments: list[list[Section]] = []
    centroids: list[dict[str, float]] = []

    for section in ordered_sections:
        vector = vectors[section.section_id]
        best_index = -1
        best_score = 0.0
        for idx, centroid in enumerate(centroids):
            score = cosine_similarity(vector, centroid)
            if score > best_score:
                best_index = idx
                best_score = score
        if best_index >= 0 and (best_score >= 0.24 or len(assignments) >= target_clusters):
            assignments[best_index].append(section)
            centroids[best_index] = average_vectors(vectors[item.section_id] for item in assignments[best_index])
        else:
            assignments.append([section])
            centroids.append(vector)

    while len(assignments) > target_clusters:
        smallest = min(range(len(assignments)), key=lambda idx: len(assignments[idx]))
        cluster = assignments.pop(smallest)
        centroids.pop(smallest)
        best_index = max(
            range(len(assignments)),
            key=lambda idx: cosine_similarity(
                average_vectors(vectors[item.section_id] for item in cluster),
                centroids[idx],
            ),
        )
        assignments[best_index].extend(cluster)
        centroids[best_index] = average_vectors(vectors[item.section_id] for item in assignments[best_index])

    return assignments


def is_clusterable_section(section: Section) -> bool:
    title = normalize_title(section.title)
    if title_is_noisy(title):
        return False
    if section.token_count < 120:
        return False
    if section.token_count > 2600:
        return False
    if section_text_is_noisy(section.text):
        return False
    return True


def build_topics(sections: list[Section], documents: list[Document]) -> list[Topic]:
    clusterable = [section for section in sections if is_clusterable_section(section)]
    working_set = clusterable or sections
    clusters = cluster_sections(working_set)
    vectors = compute_tfidf(working_set)
    topics: list[Topic] = []
    topic_vectors: dict[str, dict[str, float]] = {}

    for index, cluster in enumerate(clusters, start=1):
        title, keywords = choose_topic_title(cluster, vectors)
        combined_text = "\n\n".join(section.text for section in cluster)
        summary = summarize_text(title, combined_text, keywords, sentence_limit=5)
        document_ids = sorted({section.doc_id for section in cluster})
        topic_id = slugify(f"topic-{index}-{title}")[:80]
        topics.append(
            Topic(
                topic_id=topic_id,
                title=title,
                keywords=keywords,
                summary=summary,
                section_ids=[section.section_id for section in cluster],
                document_ids=document_ids,
                related_topics=[],
            )
        )
        topic_vectors[topic_id] = average_vectors(vectors[section.section_id] for section in cluster)

    for topic in topics:
        similarities: list[tuple[float, str]] = []
        for other in topics:
            if other.topic_id == topic.topic_id:
                continue
            score = cosine_similarity(topic_vectors[topic.topic_id], topic_vectors[other.topic_id])
            similarities.append((score, other.topic_id))
        topic.related_topics = [topic_id for score, topic_id in sorted(similarities, reverse=True)[:3] if score > 0.08]
    return topics


def write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def write_wiki(paths: dict[str, Path], documents: list[Document], sections: list[Section], topics: list[Topic], source_path: Path) -> None:
    section_map = {section.section_id: section for section in sections}
    document_map = {document.doc_id: document for document in documents}
    topic_map = {topic.topic_id: topic for topic in topics}

    topic_lines = ["# Index", "", "## Topics", ""]
    for topic in sorted(topics, key=lambda item: item.title.lower()):
        topic_lines.append(f"- [{topic.title}](topics/{topic.topic_id}.md)")
    topic_lines.extend(["", "## Sources", ""])
    for document in sorted(documents, key=lambda item: item.title.lower()):
        topic_lines.append(f"- [{document.title}](sources/{document.doc_id}.md)")
    (paths["wiki"] / "index.md").write_text("\n".join(topic_lines).strip() + "\n", encoding="utf-8")

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    log_lines = [
        "# Build Log",
        "",
        f"- Built at: {timestamp}",
        f"- Source list: {source_path}",
        f"- Documents: {len(documents)}",
        f"- Sections: {len(sections)}",
        f"- Topics: {len(topics)}",
    ]
    (paths["wiki"] / "log.md").write_text("\n".join(log_lines) + "\n", encoding="utf-8")

    for document in documents:
        lines = [
            f"# {document.title}",
            "",
            f"- Source URL: {document.url}",
            f"- PDF path: `{document.pdf_path}`",
            f"- Extracted pages: {document.page_count}",
            f"- Sections: {document.section_count}",
            "",
            "## Summary",
            "",
            document.summary,
            "",
            "## Sections",
            "",
        ]
        for section_id in document.section_ids:
            section = section_map[section_id]
            lines.extend(
                [
                    f"### {section.title}",
                    "",
                    f"- Pages: {section.start_page}-{section.end_page}",
                    f"- Keywords: {', '.join(section.keywords[:8])}",
                    "",
                    summarize_text(section.title, section.text, section.keywords, sentence_limit=3),
                    "",
                ]
            )
        (paths["sources"] / f"{document.doc_id}.md").write_text("\n".join(lines).strip() + "\n", encoding="utf-8")

    for topic in topics:
        lines = [
            f"# {topic.title}",
            "",
            f"- Keywords: {', '.join(topic.keywords[:8])}",
            f"- Documents: {', '.join(document_map[doc_id].title for doc_id in topic.document_ids)}",
            "",
            "## Summary",
            "",
            topic.summary,
            "",
            "## Source Sections",
            "",
        ]
        for section_id in topic.section_ids:
            section = section_map[section_id]
            lines.extend(
                [
                    f"- {section.doc_title}: {section.title} (pages {section.start_page}-{section.end_page})",
                ]
            )
        lines.extend(["", "## Related Topics", ""])
        for related_id in topic.related_topics:
            lines.append(f"- [{topic_map[related_id].title}]({related_id}.md)")
        (paths["topics"] / f"{topic.topic_id}.md").write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def compile_documents(specs: list[SourceSpec], paths: dict[str, Path], force: bool) -> tuple[list[Document], list[Section]]:
    documents: list[Document] = []
    sections: list[Section] = []

    for index, spec in enumerate(specs, start=1):
        pdf_path = download_pdf(spec, paths["raw"], force=force)
        doc_stub = slugify(spec.title or pdf_path.stem or f"document-{index}")[:50]
        text_path = paths["extracted"] / f"{doc_stub}.txt"
        raw_text = extract_pdf_text(pdf_path, text_path, force=force)
        pages = [page for page in raw_text.split("\f") if page.strip()]
        title = guess_document_title(spec, pages)
        doc_id = slugify(f"{index}-{title}")[:60]
        document_sections = segment_sections(doc_id, title, pages)
        sections.extend(document_sections)
        summary_source = "\n\n".join(section.text for section in document_sections[:3])
        summary = summarize_text(title, summary_source, extract_keywords(summary_source), sentence_limit=4)
        documents.append(
            Document(
                doc_id=doc_id,
                title=title,
                url=spec.url,
                pdf_path=str(pdf_path),
                text_path=str(text_path),
                section_count=len(document_sections),
                page_count=len(pages),
                summary=summary,
                section_ids=[section.section_id for section in document_sections],
            )
        )
        write_json(
            paths["extracted"] / f"{doc_id}.sections.json",
            {
                "document": asdict(documents[-1]),
                "sections": [asdict(section) for section in document_sections],
            },
        )
    return documents, sections


def build_manifest(workspace: Path, documents: list[Document], sections: list[Section], topics: list[Topic], source_path: Path) -> None:
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workspace": str(workspace),
        "source_file": str(source_path),
        "documents": [asdict(document) for document in documents],
        "sections": [asdict(section) for section in sections],
        "topics": [asdict(topic) for topic in topics],
    }
    write_json(workspace / "build.json", manifest)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compile PDFs into a Karpathy-style wiki site.")
    parser.add_argument("--sources", required=True, help="Text file of PDF URLs.")
    parser.add_argument("--workspace", default="workspace", help="Build workspace directory.")
    parser.add_argument("--publish-dir", help="Optional output directory for publishing the generated site, e.g. docs.")
    parser.add_argument("--force", action="store_true", help="Re-download and re-extract PDFs.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    source_path = Path(args.sources).resolve()
    workspace = Path(args.workspace).resolve()
    specs = read_sources(source_path)
    if not specs:
        raise SystemExit("No PDF URLs found in the source list.")

    paths = ensure_dirs(workspace)
    clean_generated_dirs(paths)
    documents, sections = compile_documents(specs, paths, force=args.force)
    topics = build_topics(sections, documents)
    write_wiki(paths, documents, sections, topics, source_path)
    build_manifest(workspace, documents, sections, topics, source_path)
    render_site(paths["site"], documents, sections, topics)
    if args.publish_dir:
        publish_site(paths["site"], Path(args.publish_dir).resolve())
    print(f"Built site at {paths['site'] / 'index.html'}")
    return 0
