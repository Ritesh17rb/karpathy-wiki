from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
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

GENERIC_TOPIC_TERMS = {
    "model", "models", "language", "languages", "training", "tasks", "task", "results", "result",
    "evaluation", "evaluations", "method", "methods", "approach", "approaches", "learning",
    "performance", "dataset", "datasets", "section", "sections", "details", "additional",
    "using", "used", "study", "studies", "fine", "tuning", "pre", "shot", "zero", "one", "few",
    "input", "output", "context", "set", "sets", "prompt", "prompts", "response", "responses",
    "question", "questions", "answer", "answers", "example", "examples", "user", "users",
    "assistant", "assistants", "human", "humans", "data", "benchmark", "benchmarks", "scores",
    "score", "accuracy", "analysis", "system", "systems", "paper", "papers", "token", "tokens",
    "text", "texts", "image", "images", "visual", "caption", "captions", "checklist", "case",
    "safety", "judge", "judges", "table", "figure", "appendix", "appendices", "conversation",
    "conversations", "instruction", "instructions", "dialogue", "dialogues", "train", "test",
    "loss", "algorithm", "algorithms", "benchmarking",
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
    "experiments",
    "overview",
    "checklist",
    "prompt",
    "prompts",
    "user",
    "assistant",
    "captions",
    "case study",
    "broader impact",
    "broader impacts",
    "training details",
    "data collection",
    "limitations",
    "author contributions",
}


BENCHMARK_TERMS = {
    "aqua",
    "asdiv",
    "big-bench",
    "bigbench",
    "boolq",
    "cb",
    "csqa",
    "cnndm",
    "copa",
    "glue",
    "gsm8k",
    "hellaswag",
    "lambada",
    "math",
    "mawps",
    "mmlu",
    "mnli",
    "multiarith",
    "mt-bench",
    "ner",
    "rte",
    "sglue",
    "squad",
    "storycloze",
    "strategyqa",
    "superglue",
    "svamp",
    "toxigen",
    "truthfulqa",
    "wic",
    "wsc",
    "xsum",
}


METRIC_HEADING_TERMS = {
    "acc",
    "accuracy",
    "average",
    "avg",
    "delta",
    "human",
    "loss",
    "metric",
    "model",
    "normalized",
    "output",
    "outputs",
    "performance",
    "preferred",
    "score",
    "scores",
    "test",
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
    r"^setting\s",
    r"^input-input",
    r"^the the the",
    r"^contents$",
    r"^average$",
    r"^relative$",
    r"^title:",
    r"^context\s",
    r"^user$",
    r"^assistant\b",
    r"^prompt:?$",
    r"^premise:?$",
    r"^captions?$",
    r"^checklist$",
    r"^case study$",
    r"^broader impacts?$",
    r"^training details$",
    r"^data collection$",
    r"^author contributions?$",
    r"^limitations?$",
    r"^appendices$",
    r"^action\s+\d+",
    r"^observation\s+\d+",
    r"^thought\s+\d+",
    r"^judge\b",
    r"^claude[- ]?v",
    r"^gpt[- ]?\d",
    r"^algorithm\s+\d+",
    r"^backward pass$",
    r"^forward pass$",
    r"^safe responses?",
    r"^unsafe responses?",
    r"^false refusal rate",
    r"^train pm size",
    r"^use case example$",
    r"^generations? from",
    r"^instructions? and interface$",
    r"^additional (analysis|results)$",
    r"^random gaussian$",
    r"^microeconomics$",
    r"^(?:w[a-z0-9]{0,2}\s+){2,}",
)


ROLE_PATTERNS = (
    ("abstract", (r"^abstract$",)),
    ("introduction", (r"^introduction$", r"^\d+(\.\d+)*\s+introduction$")),
    ("background", (r"^background$", r"^related work$", r"^preliminaries?$")),
    ("method", (r"^model architecture$", r"^method", r"^methods$", r"^approach", r"^pre-training")),
    ("results", (r"^experiments?$", r"^evaluation$", r"^results?$", r"^analysis$", r"^discussion$")),
    ("conclusion", (r"^conclusion$", r"^conclusions$", r"^future work$")),
    ("appendix", (r"^appendix", r"^supplement")),
    ("references", (r"^references?$", r"^bibliography$")),
)


TRIM_START_MARKERS = (
    "abstract",
    "1 introduction",
    "introduction",
)


TRIM_END_MARKERS = (
    "references",
    "bibliography",
    "acknowledgements",
    "acknowledgments",
)


@dataclass
class SourceSpec:
    url: str
    title: str | None = None
    year: int | None = None
    venue: str | None = None
    area: str | None = None
    families: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


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
    keywords: list[str]
    topic_ids: list[str]
    section_ids: list[str]
    year: int | None
    venue: str | None
    area: str | None
    families: list[str]
    tags: list[str]


@dataclass
class Section:
    section_id: str
    anchor: str
    doc_id: str
    doc_title: str
    title: str
    normalized_title: str
    role: str
    start_page: int
    end_page: int
    text: str
    summary: str
    token_count: int
    keywords: list[str]
    key_phrases: list[str]
    quality_score: float
    clusterable: bool
    doc_year: int | None = None
    doc_area: str | None = None
    doc_families: list[str] = field(default_factory=list)
    doc_tags: list[str] = field(default_factory=list)


@dataclass
class TopicEvidence:
    doc_id: str
    doc_title: str
    section_id: str
    section_anchor: str
    section_title: str
    section_role: str
    start_page: int
    end_page: int
    excerpt: str
    section_summary: str


@dataclass
class Topic:
    topic_id: str
    title: str
    keywords: list[str]
    key_phrases: list[str]
    summary: str
    section_ids: list[str]
    document_ids: list[str]
    related_topics: list[str]
    evidence: list[TopicEvidence]
    quality_score: float


@dataclass
class PriorTopic:
    topic_id: str
    title: str
    keywords: list[str]
    key_phrases: list[str]
    section_ids: list[str]


def slugify(value: str) -> str:
    clean = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return clean or "item"


def short_hash(value: str, length: int = 8) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:length]


def stable_slug(title: str, seed: str, limit: int = 60) -> str:
    base = slugify(title)[: max(8, limit - 9)]
    return f"{base}-{short_hash(seed)}"[:limit]


def normalize_whitespace(text: str) -> str:
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_for_compare(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def title_case_phrase(text: str) -> str:
    return " ".join(part.capitalize() for part in text.split())


def unique_strings(values: Iterable[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for raw_value in values:
        value = normalize_whitespace(raw_value)
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(value)
    return ordered


def parse_metadata_list(value: str) -> list[str]:
    return unique_strings(part.strip() for part in value.split(","))


def parse_source_metadata(blob: str) -> dict[str, object]:
    metadata: dict[str, object] = {
        "year": None,
        "venue": None,
        "area": None,
        "families": [],
        "tags": [],
    }
    if not blob.strip():
        return metadata

    for raw_part in blob.split(";"):
        part = raw_part.strip()
        if not part:
            continue
        if "=" not in part:
            metadata["tags"] = unique_strings([*metadata["tags"], *parse_metadata_list(part)])  # type: ignore[arg-type]
            continue

        key, raw_value = [item.strip() for item in part.split("=", 1)]
        normalized_key = key.lower().replace("-", "_")
        if normalized_key == "year":
            if raw_value.isdigit():
                metadata["year"] = int(raw_value)
        elif normalized_key in {"venue", "area"}:
            metadata[normalized_key] = normalize_whitespace(raw_value)
        elif normalized_key in {"family", "families"}:
            metadata["families"] = unique_strings([*metadata["families"], *parse_metadata_list(raw_value)])  # type: ignore[arg-type]
        elif normalized_key in {"tag", "tags"}:
            metadata["tags"] = unique_strings([*metadata["tags"], *parse_metadata_list(raw_value)])  # type: ignore[arg-type]

    return metadata


def read_sources(path: Path) -> list[SourceSpec]:
    specs: list[SourceSpec] = []
    seen: set[tuple[str, str | None, int | None, str | None, str | None, tuple[str, ...], tuple[str, ...]]] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [part.strip() for part in line.split("|")]
        url = parts[0]
        title = parts[1] if len(parts) >= 2 and parts[1] else None
        metadata_blob = "|".join(parts[2:]).strip() if len(parts) >= 3 else ""
        metadata = parse_source_metadata(metadata_blob)
        spec = SourceSpec(
            url=url,
            title=title,
            year=metadata["year"],  # type: ignore[arg-type]
            venue=metadata["venue"],  # type: ignore[arg-type]
            area=metadata["area"],  # type: ignore[arg-type]
            families=list(metadata["families"]),  # type: ignore[arg-type]
            tags=list(metadata["tags"]),  # type: ignore[arg-type]
        )
        key = (
            spec.url,
            spec.title,
            spec.year,
            spec.venue,
            spec.area,
            tuple(spec.families),
            tuple(spec.tags),
        )
        if key in seen:
            continue
        seen.add(key)
        specs.append(spec)
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


def download_pdf(spec: SourceSpec, raw_dir: Path) -> Path:
    base_name = spec.title or Path(filename_from_url(spec.url)).stem
    pdf_path = raw_dir / f"{stable_slug(base_name, spec.url, limit=72)}.pdf"
    if pdf_path.exists():
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


def guess_document_title(spec: SourceSpec, pages: list[str]) -> str:
    if spec.title:
        return spec.title
    if pages:
        for line in pages[0].splitlines()[:20]:
            stripped = " ".join(line.split())
            if looks_like_heading(stripped, allow_generic=True):
                return stripped
    return Path(filename_from_url(spec.url)).stem.replace("-", " ").title()


def tokenise(text: str) -> list[str]:
    return [token for token in re.findall(r"[a-zA-Z]{3,}", text.lower()) if token not in STOPWORDS]


def normalize_title(title: str) -> str:
    title = re.sub(r"^\d+(\.\d+)*[.)]?\s+", "", title).strip()
    title = re.sub(r"^[ivxlcdm]+[.)]?\s+", "", title, flags=re.IGNORECASE).strip()
    title = re.sub(r"^[a-z](?:\.\d+)*[.)]?\s+", "", title, flags=re.IGNORECASE).strip()
    return title


def meaningful_tokens(text: str) -> set[str]:
    return {token for token in tokenise(text) if token not in GENERIC_TOPIC_TERMS}


def meaningful_keywords(values: Iterable[str]) -> set[str]:
    return {value for value in values if value not in GENERIC_TOPIC_TERMS}


def meaningful_key_phrases(values: Iterable[str]) -> set[str]:
    phrases = set()
    for phrase in values:
        if any(word not in GENERIC_TOPIC_TERMS for word in phrase.split()):
            phrases.add(phrase)
    return phrases


def title_tokens(title: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9][A-Za-z0-9-]*", title)


def title_has_fragmented_ocr(title: str) -> bool:
    tokens = title_tokens(title)
    single_letter_tokens = sum(1 for token in tokens if token.isalpha() and len(token) == 1)
    return len(tokens) >= 4 and single_letter_tokens >= 2


def title_has_technical_signal(title: str) -> bool:
    raw_tokens = title_tokens(title)
    lowered_tokens = {token.lower() for token in raw_tokens}
    meaningful = [token for token in lowered_tokens if token not in STOPWORDS and token not in GENERIC_TOPIC_TERMS]
    if not meaningful:
        return False
    if any("-" in token and len(token) >= 6 for token in raw_tokens):
        return True
    if any(any(char.isdigit() for char in token) for token in raw_tokens):
        return True
    if any(token.isupper() and len(token) >= 2 for token in raw_tokens):
        return True
    if any(token[:1].isupper() and any(char.isupper() for char in token[1:]) for token in raw_tokens):
        return True
    if len(meaningful) <= 3 and all(len(token) >= 5 for token in meaningful):
        return True
    if len(meaningful) <= 4 and any(len(token) >= 8 for token in meaningful):
        return True
    return False


def title_has_benchmark_markers(title: str) -> bool:
    lowered = normalize_title(title).lower()
    if "↑" in title or "↓" in title:
        return True
    if any(term in lowered for term in BENCHMARK_TERMS):
        return True
    return False


def title_looks_like_metric_heading(title: str) -> bool:
    tokens = [token.lower() for token in title_tokens(normalize_title(title))]
    if not 1 <= len(tokens) <= 6:
        return False
    metric_terms = sum(token in METRIC_HEADING_TERMS for token in tokens)
    return metric_terms >= max(2, len(tokens) - 1)


def title_looks_like_table_header(title: str) -> bool:
    tokens = title_tokens(normalize_title(title))
    if len(tokens) < 3:
        return False
    numeric_tokens = sum(1 for token in tokens if any(char.isdigit() for char in token))
    upper_tokens = sum(1 for token in tokens if token.isupper() and len(token) >= 2)
    capitalized_tokens = sum(1 for token in tokens if token[:1].isupper())
    if numeric_tokens + upper_tokens >= 3:
        return True
    if numeric_tokens >= 1 and capitalized_tokens >= max(3, len(tokens) - 1):
        return True
    return False


def text_has_reference_markers(text: str) -> bool:
    lowered = text.lower()
    years = len(re.findall(r"\b(?:19|20)\d{2}[a-z]?\b", lowered))
    return (
        lowered.count("proceedings of") >= 2
        or lowered.count("conference on") >= 2
        or (lowered.count("et al") >= 2 and years >= 3)
        or (lowered.count("pages ") >= 3 and years >= 3)
    )


def text_has_question_format(text: str) -> bool:
    lowered = text.lower()
    answer_choice_markers = len(re.findall(r"(?:^|\s)(?:[a-d][\).]|[ivx]{1,4}[\).])\s", lowered))
    qa_markers = (
        lowered.count("question:")
        + lowered.count("answer:")
        + lowered.count("options:")
        + lowered.count("answer choices:")
        + lowered.count("q:")
        + lowered.count("a:")
    )
    return answer_choice_markers >= 4 or qa_markers >= 3


def text_has_generation_markers(text: str) -> bool:
    lowered = text.lower()
    return (
        lowered.count("i would") >= 2
        or lowered.count("the following is") >= 2
        or lowered.count("assistant:") >= 2
        or lowered.count("user:") >= 2
    )


def title_looks_like_example(title: str) -> bool:
    lowered = normalize_title(title).lower()
    return (
        lowered.startswith("user")
        or lowered.startswith("assistant")
        or lowered.startswith("prompt")
        or lowered.startswith("premise")
        or lowered.startswith("action ")
        or lowered.startswith("observation ")
        or lowered.startswith("thought ")
    )


def title_is_generic(title: str) -> bool:
    normalized = normalize_title(title).lower()
    return normalized in GENERIC_TITLES


def title_is_noisy(title: str) -> bool:
    normalized = normalize_title(title)
    lowered = normalized.lower()
    if len(normalized) > 90:
        return True
    if title_has_fragmented_ocr(title):
        return True
    if title_looks_like_metric_heading(title) or title_looks_like_table_header(title):
        return True
    first_alpha = next((char for char in normalized if char.isalpha()), "")
    if first_alpha and first_alpha.islower():
        return True
    if len(normalized.split()) > 8:
        return True
    if re.search(r"[\[\]+]", normalized):
        return True
    if normalized.count(":") >= 2 or normalized.count("!") >= 2:
        return True
    if ":" in normalized and "!" in normalized:
        return True
    words = re.findall(r"[A-Za-z]+", lowered)
    if words and len(set(words)) / len(words) < 0.65:
        return True
    return any(re.search(pattern, lowered) for pattern in NOISY_TITLE_PATTERNS)


def should_drop_line(line: str) -> bool:
    lowered = line.lower()
    if not line.strip():
        return True
    if re.fullmatch(r"[\divxlcdm]+", lowered):
        return True
    if re.fullmatch(r"page\s+\d+", lowered):
        return True
    if re.search(r"https?://|www\.", lowered):
        return True
    if "@" in line and ("." in line or ".com" in lowered):
        return True
    if lowered.startswith("provided proper attribution"):
        return True
    if lowered.startswith("under review as a conference paper"):
        return True
    if lowered.startswith("copyright"):
        return True
    if re.match(r"^(figure|table)\s+\d+", lowered) and len(line) < 180:
        return True
    if lowered.count(".com") >= 1 and len(line.split()) < 20:
        return True
    if sum(char.isdigit() for char in line) / max(len(line), 1) > 0.45 and len(line) < 36:
        return True
    return False


def clean_page_text(page: str) -> str:
    cleaned_lines = []
    for raw_line in page.splitlines():
        line = " ".join(raw_line.replace("\u00a0", " ").split())
        if should_drop_line(line):
            continue
        cleaned_lines.append(line)
    return normalize_whitespace("\n".join(cleaned_lines))


def trim_section_boundaries(title: str, text: str, doc_title: str) -> str:
    normalized = normalize_whitespace(text)
    if not normalized:
        return ""
    lowered = normalized.lower()
    normalized_title = normalize_for_compare(normalize_title(title))
    doc_norm = normalize_for_compare(doc_title)
    if normalized_title in {"overview", doc_norm} or normalized_title.endswith("overview"):
        for marker in TRIM_START_MARKERS:
            idx = lowered.find(marker)
            if idx != -1 and idx < max(500, len(lowered) // 3):
                normalized = normalized[idx:]
                lowered = normalized.lower()
                break
    for marker in TRIM_END_MARKERS:
        idx = lowered.find(marker)
        if idx != -1 and idx > len(lowered) * 0.45:
            normalized = normalized[:idx]
            lowered = normalized.lower()
            break
    return normalize_whitespace(normalized)


def repetitive_text_score(text: str) -> float:
    tokens = tokenise(text)
    if len(tokens) < 12:
        return 0.0
    counts = Counter(tokens)
    unique_ratio = len(counts) / len(tokens)
    top_ratio = counts.most_common(1)[0][1] / len(tokens)
    return max(top_ratio, 1 - unique_ratio)


def paragraph_is_noise(paragraph: str) -> bool:
    lowered = paragraph.lower()
    tokens = tokenise(paragraph)
    if len(tokens) < 8:
        return True
    if text_has_reference_markers(paragraph):
        return True
    if re.search(r"https?://|www\.|@", paragraph):
        return True
    if lowered.startswith("figure ") or lowered.startswith("table "):
        return True
    if lowered.count("et al") >= 2:
        return True
    if lowered.count("arxiv") >= 2:
        return True
    if len(re.findall(r"\b(?:19|20)\d{2}[a-z]?\b", paragraph)) >= 6 and len(tokens) < 140:
        return True
    if len(re.findall(r"\[[0-9,\s]+\]", paragraph)) >= 3 and len(tokens) < 140:
        return True
    if lowered.count("user:") + lowered.count("assistant:") >= 2:
        return True
    if lowered.count("prompt:") >= 2:
        return True
    if text_has_question_format(paragraph):
        return True
    if text_has_generation_markers(paragraph):
        return True
    if repetitive_text_score(paragraph) > 0.68:
        return True
    return False


def section_text_is_noisy(text: str) -> bool:
    lowered = text.lower()
    noisy_markers = (
        lowered.count("correct answer")
        + lowered.count("incorrect answer")
        + lowered.count("target completion")
        + lowered.count("appendix")
    )
    citation_markers = lowered.count("arxiv") + lowered.count("proceedings of") + lowered.count("et al")
    arrow_markers = lowered.count("→") + lowered.count("->")
    dialogue_markers = lowered.count("user:") + lowered.count("assistant:") + lowered.count("prompt:")
    action_markers = lowered.count("action ") + lowered.count("observation ") + lowered.count("thought ")
    if noisy_markers >= 3:
        return True
    if text_has_reference_markers(text):
        return True
    if citation_markers >= 4:
        return True
    if arrow_markers >= 6:
        return True
    if lowered.count("figure ") >= 8:
        return True
    if dialogue_markers >= 3:
        return True
    if action_markers >= 5:
        return True
    if text_has_question_format(text) and lowered.count("question:") >= 2:
        return True
    if text_has_generation_markers(text):
        return True
    if repetitive_text_score(text) > 0.72:
        return True
    return False


def classify_section_role(title: str, text: str, doc_title: str) -> str:
    normalized = normalize_title(title).lower()
    if normalized in {doc_title.lower(), f"{doc_title.lower()}: overview", "overview"}:
        return "frontmatter"
    if normalized in {
        "contents",
        "acknowledgements",
        "acknowledgments",
        "contributions",
        "average",
        "relative",
        "broader impact",
        "broader impacts",
        "author contributions",
        "limitations",
        "data collection",
        "training details",
        "checklist",
        "captions",
        "use case example",
    }:
        return "boilerplate"
    if text_has_reference_markers(text):
        return "references"
    if normalized.startswith("setting "):
        return "benchmark"
    if title_looks_like_metric_heading(title) or title_looks_like_table_header(title):
        return "benchmark"
    if (
        normalized.startswith("generations from")
        or normalized.startswith("instruction and interface")
        or normalized.startswith("instructions and interface")
    ):
        return "example"
    if (
        normalized.startswith("title:")
        or normalized.startswith("context ")
        or normalized.startswith("target completion")
        or title_looks_like_example(title)
    ):
        return "example"
    for role, patterns in ROLE_PATTERNS:
        if any(re.match(pattern, normalized) for pattern in patterns):
            return role
    lowered = text.lower()
    if normalized.startswith("figure ") or normalized.startswith("table "):
        return "figure"
    if title_has_benchmark_markers(title):
        return "benchmark"
    if lowered.count("figure ") >= 6:
        return "figure"
    if text_has_question_format(text):
        return "benchmark"
    if lowered.count("user:") + lowered.count("assistant:") >= 2:
        return "example"
    if lowered.count("prompt:") >= 2:
        return "example"
    if text_has_generation_markers(text):
        return "example"
    if lowered.count("action ") + lowered.count("observation ") >= 3:
        return "example"
    return "section"


def compute_section_quality(title: str, text: str, role: str) -> float:
    score = 1.0
    tokens = tokenise(text)
    if role == "references":
        score -= 0.85
    elif role == "appendix":
        score -= 0.45
    elif role == "frontmatter":
        score -= 0.30
    elif role == "figure":
        score -= 0.40
    elif role == "benchmark":
        score -= 0.30
    elif role == "example":
        score -= 0.38
    elif role == "boilerplate":
        score -= 0.55
    if title_is_noisy(title):
        score -= 0.30
    elif title_is_generic(title):
        score -= 0.08
    if len(tokens) < 80:
        score -= 0.30
    if len(tokens) > 2600:
        score -= 0.15
    if section_text_is_noisy(text):
        score -= 0.40
    score -= min(0.4, repetitive_text_score(text) * 0.55)
    sentence_count = len(split_sentences(text))
    if sentence_count >= 3:
        score += 0.10
    if len(tokens) >= 140:
        score += 0.05
    return round(max(0.0, min(score, 1.0)), 3)


def extract_keywords(text: str, limit: int = 8) -> list[str]:
    counts = Counter(tokenise(text))
    return [word for word, _ in counts.most_common(limit)]


def extract_key_phrases(text: str, limit: int = 6) -> list[str]:
    words = [word for word in re.findall(r"[A-Za-z][A-Za-z-]{2,}", text.lower()) if word not in STOPWORDS]
    counts: Counter[str] = Counter()
    for size in (2, 3):
        for index in range(len(words) - size + 1):
            phrase_words = words[index : index + size]
            if len(set(phrase_words)) < size:
                continue
            phrase = " ".join(phrase_words)
            counts[phrase] += 1
    phrases: list[str] = []
    for phrase, count in counts.most_common():
        if count < 2:
            continue
        phrases.append(phrase)
        if len(phrases) >= limit:
            break
    return phrases


def split_sentences(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return []
    parts = re.split(r"(?<=[.!?])\s+", normalized)
    return [part.strip() for part in parts if 40 <= len(part.strip()) <= 320]


def summarize_text(title: str, text: str, keywords: list[str], sentence_limit: int = 4) -> str:
    sentences = split_sentences(text)
    if not sentences:
        collapsed = " ".join(text.split())
        return collapsed[:400].strip()
    freq = Counter(tokenise(text))
    title_tokens = set(tokenise(title))
    scored: list[tuple[float, int, str]] = []
    for index, sentence in enumerate(sentences[:160]):
        if paragraph_is_noise(sentence):
            continue
        tokens = tokenise(sentence)
        if not tokens:
            continue
        score = sum(freq[token] for token in tokens) / max(len(tokens), 1)
        score += sum(3 for keyword in keywords[:8] if keyword in sentence.lower())
        score += len(title_tokens.intersection(tokens)) * 2
        score -= repetitive_text_score(sentence) * 6
        scored.append((score, index, sentence))
    if not scored:
        return " ".join(sentences[:sentence_limit])
    picked = {sentence for _, _, sentence in sorted(scored, reverse=True)[: sentence_limit * 3]}
    ordered: list[str] = []
    for sentence in sentences:
        if sentence in picked and sentence not in ordered:
            ordered.append(sentence)
        if len(ordered) >= sentence_limit:
            break
    return " ".join(ordered)


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


def make_section(
    doc_id: str,
    doc_title: str,
    title: str,
    start_page: int,
    end_page: int,
    pages: list[str],
    ordinal: int,
    spec: SourceSpec | None = None,
) -> Section | None:
    page_texts = []
    for page in pages[start_page : end_page + 1]:
        cleaned = clean_page_text(page)
        if cleaned:
            page_texts.append(cleaned)
    body = trim_section_boundaries(title, "\n\n".join(page_texts), doc_title)
    paragraphs = [part.strip() for part in re.split(r"\n{2,}", body) if part.strip() and not paragraph_is_noise(part)]
    body = normalize_whitespace("\n\n".join(paragraphs))
    token_count = len(tokenise(body))
    if token_count < 60:
        return None

    section_title = title.strip() or f"{doc_title}: Section {ordinal:02d}"
    if normalize_title(section_title).lower() in {"overview", "part", "part 01"}:
        section_title = f"{doc_title}: Overview"
    normalized_title = normalize_title(section_title) or section_title
    role = classify_section_role(section_title, body, doc_title)
    quality_score = compute_section_quality(section_title, body, role)
    clusterable = quality_score >= 0.55 and role not in {
        "references",
        "appendix",
        "frontmatter",
        "figure",
        "benchmark",
        "example",
        "boilerplate",
    }
    keywords = extract_keywords(f"{normalized_title}\n{body}")
    key_phrases = extract_key_phrases(f"{normalized_title}\n{body}")
    summary = summarize_text(section_title, body, keywords, sentence_limit=3)
    section_id = slugify(f"{doc_id}-{normalized_title}-{start_page + 1}-{end_page + 1}")[:90]
    anchor = slugify(f"{normalized_title}-{start_page + 1}")[:80]
    return Section(
        section_id=section_id,
        anchor=anchor,
        doc_id=doc_id,
        doc_title=doc_title,
        title=section_title,
        normalized_title=normalized_title,
        role=role,
        start_page=start_page + 1,
        end_page=end_page + 1,
        text=body,
        summary=summary,
        token_count=token_count,
        keywords=keywords,
        key_phrases=key_phrases,
        quality_score=quality_score,
        clusterable=clusterable,
        doc_year=spec.year if spec else None,
        doc_area=spec.area if spec else None,
        doc_families=list(spec.families) if spec else [],
        doc_tags=list(spec.tags) if spec else [],
    )


def segment_sections(doc_id: str, doc_title: str, pages: list[str], spec: SourceSpec | None = None) -> list[Section]:
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
        section = make_section(doc_id, doc_title, title, start_page, end_page, pages, idx, spec=spec)
        if section:
            sections.append(section)

    if sections:
        return sections

    whole_text = "\n\n".join(clean_page_text(page) for page in pages)
    fallback = make_section(
        doc_id,
        doc_title,
        f"{doc_title}: Full Text",
        0,
        max(len(pages) - 1, 0),
        [whole_text],
        1,
        spec=spec,
    )
    if fallback:
        return [fallback]
    return []


def compute_tfidf(sections: list[Section]) -> dict[str, dict[str, float]]:
    doc_tokens: dict[str, Counter[str]] = {}
    df: Counter[str] = Counter()
    for section in sections:
        metadata_text = "\n".join(
            [
                section.doc_area or "",
                " ".join(section.doc_families),
                " ".join(section.doc_tags),
            ]
        )
        tokens = tokenise(f"{section.normalized_title}\n{metadata_text}\n{section.text}")
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


def has_lexical_alignment(left: Section, right: Section) -> bool:
    left_title_tokens = meaningful_tokens(left.normalized_title)
    right_title_tokens = meaningful_tokens(right.normalized_title)
    if left_title_tokens.intersection(right_title_tokens):
        return True
    if meaningful_key_phrases(left.key_phrases[:4]).intersection(meaningful_key_phrases(right.key_phrases[:4])):
        return True
    shared_keywords = meaningful_keywords(left.keywords[:6]).intersection(meaningful_keywords(right.keywords[:6]))
    if len(shared_keywords) >= 3:
        return True
    return normalize_for_compare(left.normalized_title) == normalize_for_compare(right.normalized_title)


def section_similarity(left: Section, right: Section, vectors: dict[str, dict[str, float]]) -> float:
    score = cosine_similarity(vectors[left.section_id], vectors[right.section_id])
    shared_keywords = len(meaningful_keywords(left.keywords[:6]).intersection(meaningful_keywords(right.keywords[:6])))
    shared_families = len(set(left.doc_families).intersection(right.doc_families))
    shared_tags = len(set(left.doc_tags).intersection(right.doc_tags))
    left_title_tokens = meaningful_tokens(left.normalized_title)
    right_title_tokens = meaningful_tokens(right.normalized_title)
    shared_title_tokens = len(left_title_tokens.intersection(right_title_tokens))
    shared_phrases = len(meaningful_key_phrases(left.key_phrases[:4]).intersection(meaningful_key_phrases(right.key_phrases[:4])))
    if shared_keywords:
        score += min(0.12, shared_keywords * 0.03)
    if left.doc_area and right.doc_area and left.doc_area == right.doc_area:
        score += 0.05
    if shared_families:
        score += min(0.12, shared_families * 0.04)
    if shared_tags:
        score += min(0.08, shared_tags * 0.02)
    if shared_title_tokens:
        score += min(0.18, shared_title_tokens * 0.09)
    if shared_phrases:
        score += min(0.24, shared_phrases * 0.12)
    if normalize_for_compare(left.normalized_title) == normalize_for_compare(right.normalized_title):
        score += 0.18
    if left.doc_year and right.doc_year and abs(left.doc_year - right.doc_year) <= 2:
        score += 0.02
    if left.doc_id == right.doc_id:
        if shared_title_tokens == 0 and shared_phrases == 0 and shared_keywords < 2:
            score *= 0.45
        else:
            score -= 0.02
    elif shared_title_tokens == 0 and shared_phrases == 0 and shared_keywords < 3:
        score *= 0.25
    return score


def cluster_fit_score(section: Section, cluster: list[Section], vectors: dict[str, dict[str, float]]) -> float:
    centroid = average_vectors(vectors[item.section_id] for item in cluster)
    centroid_score = cosine_similarity(vectors[section.section_id], centroid)
    if not any(has_lexical_alignment(section, item) for item in cluster):
        return centroid_score * 0.08
    pair_scores = sorted((section_similarity(section, item, vectors) for item in cluster), reverse=True)
    local_score = sum(pair_scores[:3]) / max(min(3, len(pair_scores)), 1)
    return centroid_score * 0.65 + local_score * 0.35


def cluster_sections(sections: list[Section]) -> list[list[Section]]:
    if len(sections) <= 4:
        return [[section] for section in sections]

    vectors = compute_tfidf(sections)
    target_clusters = max(4, round(len(sections) ** 0.65))
    ordered_sections = sorted(sections, key=lambda section: (section.quality_score, section.token_count), reverse=True)

    assignments: list[list[Section]] = []
    for section in ordered_sections:
        best_index = -1
        best_score = 0.0
        for idx, cluster in enumerate(assignments):
            score = cluster_fit_score(section, cluster, vectors)
            if score > best_score:
                best_index = idx
                best_score = score
        if best_index >= 0 and (best_score >= 0.46 or len(assignments) >= target_clusters):
            assignments[best_index].append(section)
        else:
            assignments.append([section])

    merged = True
    while merged and len(assignments) > 1:
        merged = False
        best_pair: tuple[int, int] | None = None
        best_score = 0.0
        for left_idx in range(len(assignments)):
            left_cluster = assignments[left_idx]
            left_centroid = average_vectors(vectors[item.section_id] for item in left_cluster)
            for right_idx in range(left_idx + 1, len(assignments)):
                right_cluster = assignments[right_idx]
                if not any(has_lexical_alignment(left_item, right_item) for left_item in left_cluster for right_item in right_cluster):
                    continue
                right_centroid = average_vectors(vectors[item.section_id] for item in right_cluster)
                score = cosine_similarity(left_centroid, right_centroid)
                if score > best_score:
                    best_score = score
                    best_pair = (left_idx, right_idx)
        if best_pair and (best_score >= 0.58 or (len(assignments) > target_clusters and best_score >= 0.48)):
            left_idx, right_idx = best_pair
            assignments[left_idx].extend(assignments[right_idx])
            assignments.pop(right_idx)
            merged = True

    return [sorted(cluster, key=lambda item: (item.doc_title.lower(), item.start_page)) for cluster in assignments]


def choose_topic_title(cluster: list[Section], vectors: dict[str, dict[str, float]]) -> tuple[str, list[str], list[str]]:
    cluster_vector = average_vectors(vectors[section.section_id] for section in cluster)
    cluster_text = "\n\n".join(f"{section.normalized_title}\n{section.text}" for section in cluster)
    keywords = extract_keywords(cluster_text, limit=10)
    key_phrases = extract_key_phrases(cluster_text, limit=6)
    cluster_doc_count = len({section.doc_id for section in cluster})
    usable_key_phrases = [
        phrase
        for phrase in key_phrases
        if any(word not in GENERIC_TOPIC_TERMS for word in phrase.split())
        and title_has_technical_signal(title_case_phrase(phrase))
        and sum(
            1
            for section in cluster
            if normalize_for_compare(phrase)
            in normalize_for_compare(f"{section.normalized_title}\n{section.summary}\n{' '.join(section.key_phrases[:4])}\n{section.text[:1800]}")
        )
        >= 2
    ]

    candidates: dict[str, dict[str, object]] = {}
    title_token_index = [
        meaningful_tokens(section.normalized_title)
        for section in cluster
    ]
    for section in cluster:
        title = normalize_title(section.title)
        normalized = normalize_for_compare(title)
        if not title or title_is_generic(title) or title_is_noisy(title) or title_looks_like_example(title):
            continue
        if section.role in {"references", "appendix", "frontmatter", "figure"}:
            continue
        section_title_tokens = meaningful_tokens(title)
        overlap_count = 0
        if section_title_tokens:
            overlap_count = sum(
                1
                for other, tokens in zip(cluster, title_token_index)
                if other.section_id != section.section_id and tokens.intersection(section_title_tokens)
            )
        overlap_bonus = overlap_count * 0.12
        entry = candidates.setdefault(
            normalized,
            {"title": title, "score": 0.0, "docs": set(), "count": 0, "support": 0},
        )
        entry["score"] = float(entry["score"]) + cosine_similarity(vectors[section.section_id], cluster_vector) + section.quality_score * 0.15 + overlap_bonus
        entry["count"] = int(entry["count"]) + 1
        entry["support"] = max(int(entry["support"]), overlap_count)
        entry["docs"].add(section.doc_id)

    if candidates:
        ranked = sorted(
            candidates.values(),
            key=lambda item: (
                len(item["docs"]),
                item["count"],
                item["score"],
                -len(str(item["title"]).split()),
            ),
            reverse=True,
        )
        top_candidate = ranked[0]
        if (
            (cluster_doc_count == 1 and (int(top_candidate["support"]) >= 1 or title_has_technical_signal(str(top_candidate["title"])) or int(top_candidate["count"]) >= 2))
            or len(top_candidate["docs"]) > 1
        ):
            title = str(top_candidate["title"])
        elif usable_key_phrases:
            title = title_case_phrase(usable_key_phrases[0])
        else:
            filtered_words = [word.title() for word in keywords if word not in GENERIC_TOPIC_TERMS][:3]
            title = " / ".join(filtered_words) or str(top_candidate["title"])
    elif usable_key_phrases:
        title = title_case_phrase(usable_key_phrases[0])
    elif keywords:
        filtered_words = [word.title() for word in keywords if word not in GENERIC_TOPIC_TERMS][:3]
        title = " / ".join(filtered_words)
    else:
        title = "Synthesized Topic"

    filtered_keywords = [word for word in keywords if word not in tokenise(title) and word not in GENERIC_TOPIC_TERMS]
    if len(filtered_keywords) < 4:
        filtered_keywords.extend(word for word in keywords if word not in tokenise(title) and word not in filtered_keywords)
    return title, filtered_keywords, key_phrases


def best_evidence_excerpt(section: Section, topic_title: str, topic_keywords: list[str]) -> str:
    sentences = split_sentences(section.text)
    if not sentences:
        return section.summary
    title_tokens = set(tokenise(topic_title))
    scored: list[tuple[float, str]] = []
    for sentence in sentences[:80]:
        tokens = tokenise(sentence)
        if not tokens:
            continue
        score = len(title_tokens.intersection(tokens)) * 2
        score += sum(2 for keyword in topic_keywords[:8] if keyword in sentence.lower())
        score += 1.0 / max(len(sentence), 1)
        score -= repetitive_text_score(sentence) * 5
        scored.append((score, sentence))
    if not scored:
        return section.summary
    return max(scored, key=lambda item: item[0])[1]


def load_prior_topics(workspace: Path) -> list[PriorTopic]:
    manifest_path = workspace / "build.json"
    if not manifest_path.exists():
        return []
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []

    topics: list[PriorTopic] = []
    for topic in payload.get("topics", []):
        topic_id = topic.get("topic_id")
        if not topic_id:
            continue
        topics.append(
            PriorTopic(
                topic_id=topic_id,
                title=topic.get("title", ""),
                keywords=list(topic.get("keywords", [])),
                key_phrases=list(topic.get("key_phrases", [])),
                section_ids=list(topic.get("section_ids", [])),
            )
        )
    return topics


def topic_has_support(cluster: list[Section], title: str) -> bool:
    title_tokens = meaningful_tokens(title)
    if not title_tokens:
        return False
    overlaps = 0
    for section in cluster:
        section_tokens = meaningful_tokens(section.normalized_title)
        if section_tokens.intersection(title_tokens):
            overlaps += 1
    return overlaps >= 1


def topic_text_support(cluster: list[Section], title: str) -> int:
    phrase = normalize_for_compare(title)
    if not phrase or len(phrase.split()) < 2:
        return 0
    support = 0
    for section in cluster:
        haystack = normalize_for_compare(
            "\n".join(
                [
                    section.normalized_title,
                    section.summary,
                    " ".join(section.key_phrases[:4]),
                    section.text[:2400],
                ]
            )
        )
        if phrase in haystack:
            support += 1
    return support


def topic_alignment_score(
    section: Section,
    cluster: list[Section],
    prior_topic: PriorTopic | None,
    vectors: dict[str, dict[str, float]],
) -> float:
    score = cluster_fit_score(section, cluster, vectors)
    if prior_topic:
        prior_title_tokens = meaningful_tokens(prior_topic.title)
        section_title_tokens = meaningful_tokens(section.normalized_title)
        if prior_title_tokens.intersection(section_title_tokens):
            score += 0.10
        keyword_overlap = len(meaningful_keywords(prior_topic.keywords[:8]).intersection(meaningful_keywords(section.keywords[:8])))
        if keyword_overlap:
            score += min(0.12, keyword_overlap * 0.04)
        phrase_overlap = len(meaningful_key_phrases(prior_topic.key_phrases[:4]).intersection(meaningful_key_phrases(section.key_phrases[:4])))
        if phrase_overlap:
            score += min(0.18, phrase_overlap * 0.09)
    return score


def make_topic_id(title: str, used_ids: set[str]) -> str:
    base_topic_id = f"topic-{slugify(title)}"[:90] or f"topic-{short_hash(title)}"
    candidate = base_topic_id
    suffix = 2
    while candidate in used_ids:
        candidate = f"{base_topic_id[:84]}-{suffix}"
        suffix += 1
    used_ids.add(candidate)
    return candidate


def materialize_topic(
    cluster: list[Section],
    vectors: dict[str, dict[str, float]],
    used_ids: set[str],
    prior_topic: PriorTopic | None = None,
) -> tuple[Topic, dict[str, float]]:
    title, keywords, key_phrases = choose_topic_title(cluster, vectors)
    if prior_topic and topic_has_support(cluster, prior_topic.title):
        title = prior_topic.title
    cluster_text = "\n\n".join(section.summary or section.text for section in cluster)
    summary = summarize_text(title, cluster_text, keywords, sentence_limit=4)
    document_ids = sorted({section.doc_id for section in cluster})
    reuse_prior_id = prior_topic and normalize_for_compare(prior_topic.title) == normalize_for_compare(title)
    topic_id = prior_topic.topic_id if reuse_prior_id else make_topic_id(title, used_ids)
    used_ids.add(topic_id)
    cluster_vector = average_vectors(vectors[item.section_id] for item in cluster)
    ranked_sections = sorted(
        cluster,
        key=lambda section: (
            cosine_similarity(vectors[section.section_id], cluster_vector),
            section.quality_score,
        ),
        reverse=True,
    )

    evidence: list[TopicEvidence] = []
    covered_docs: set[str] = set()
    for section in ranked_sections:
        if len(evidence) >= 6:
            break
        if len(evidence) >= 3 and section.doc_id in covered_docs and len(covered_docs) >= min(3, len(document_ids)):
            continue
        evidence.append(
            TopicEvidence(
                doc_id=section.doc_id,
                doc_title=section.doc_title,
                section_id=section.section_id,
                section_anchor=section.anchor,
                section_title=section.title,
                section_role=section.role,
                start_page=section.start_page,
                end_page=section.end_page,
                excerpt=best_evidence_excerpt(section, title, keywords),
                section_summary=section.summary,
            )
        )
        covered_docs.add(section.doc_id)

    quality_score = round(sum(section.quality_score for section in cluster) / max(len(cluster), 1), 3)
    topic = Topic(
        topic_id=topic_id,
        title=title,
        keywords=keywords[:8],
        key_phrases=key_phrases[:6],
        summary=summary,
        section_ids=[section.section_id for section in cluster],
        document_ids=document_ids,
        related_topics=[],
        evidence=evidence,
        quality_score=quality_score,
    )
    return topic, cluster_vector


def topic_title_is_unhelpful(title: str) -> bool:
    return (
        title_is_generic(title)
        or title_is_noisy(title)
        or title_looks_like_example(title)
        or not meaningful_tokens(title)
    )


def topic_title_support(cluster: list[Section], title: str) -> int:
    title_tokens = meaningful_tokens(title)
    if not title_tokens:
        return 0
    return sum(
        1
        for section in cluster
        if meaningful_tokens(section.normalized_title).intersection(title_tokens)
    )


def topic_should_publish(topic: Topic, cluster: list[Section]) -> bool:
    roles = Counter(section.role for section in cluster)
    noisy_roles = roles["example"] + roles["boilerplate"] + roles["appendix"] + roles["references"] + roles["frontmatter"] + roles["figure"]
    support = topic_title_support(cluster, topic.title)
    body_support = topic_text_support(cluster, topic.title)
    technical_signal = title_has_technical_signal(topic.title)
    support_density = (support + min(body_support, 3)) / max(len(cluster), 1)
    single_source = len(topic.document_ids) == 1

    if topic_title_is_unhelpful(topic.title):
        return False
    if " / " in topic.title:
        segments = [part.strip() for part in topic.title.split("/") if part.strip()]
        technical_segments = sum(1 for segment in segments if title_has_technical_signal(segment))
        if technical_segments < max(2, len(segments) - 1):
            return False
    if noisy_roles == len(cluster) and len(cluster) <= 6:
        return False
    if len(cluster) >= 12 and support_density < 0.18:
        return False
    if support == 0 and not technical_signal:
        return False
    if support == 0 and body_support < 2:
        return False
    if single_source and len(cluster) == 1 and (len(topic.evidence) <= 1 or not technical_signal):
        return False
    if single_source and noisy_roles >= max(1, len(cluster) - 1):
        return False
    if single_source and len(cluster) <= 2 and support == 0:
        return False
    if single_source and len(cluster) <= 2 and not technical_signal:
        return False
    return True


def merge_duplicate_topics(
    topics: list[Topic],
    topic_vectors: dict[str, dict[str, float]],
    vectors: dict[str, dict[str, float]],
    section_map: dict[str, Section],
) -> tuple[list[Topic], dict[str, dict[str, float]]]:
    grouped: defaultdict[str, list[Topic]] = defaultdict(list)
    for topic in topics:
        grouped[normalize_for_compare(topic.title)].append(topic)

    merged_topics: list[Topic] = []
    merged_vectors: dict[str, dict[str, float]] = {}
    used_ids = {topic.topic_id for topic in topics}

    for _, group in grouped.items():
        if len(group) == 1:
            topic = group[0]
            merged_topics.append(topic)
            merged_vectors[topic.topic_id] = topic_vectors[topic.topic_id]
            continue

        merged_sections = []
        seen_sections: set[str] = set()
        for topic in group:
            for section_id in topic.section_ids:
                if section_id in section_map and section_id not in seen_sections:
                    merged_sections.append(section_map[section_id])
                    seen_sections.add(section_id)
        merged_sections.sort(key=lambda item: (item.doc_title.lower(), item.start_page))
        prior = PriorTopic(
            topic_id=group[0].topic_id,
            title=group[0].title,
            keywords=group[0].keywords,
            key_phrases=group[0].key_phrases,
            section_ids=[section.section_id for section in merged_sections],
        )
        topic, cluster_vector = materialize_topic(merged_sections, vectors, used_ids=used_ids, prior_topic=prior)
        merged_topics.append(topic)
        merged_vectors[topic.topic_id] = cluster_vector

    return merged_topics, merged_vectors


def link_related_topics(topics: list[Topic], topic_vectors: dict[str, dict[str, float]]) -> None:
    for topic in topics:
        similarities: list[tuple[float, str]] = []
        for other in topics:
            if other.topic_id == topic.topic_id:
                continue
            score = cosine_similarity(topic_vectors[topic.topic_id], topic_vectors[other.topic_id])
            shared_keywords = len(set(topic.keywords).intersection(other.keywords))
            if shared_keywords:
                score += min(0.1, shared_keywords * 0.03)
            similarities.append((score, other.topic_id))
        topic.related_topics = [topic_id for score, topic_id in sorted(similarities, reverse=True)[:4] if score > 0.11]


def build_topics(sections: list[Section], documents: list[Document], prior_topics: list[PriorTopic] | None = None) -> list[Topic]:
    working_set = [section for section in sections if section.clusterable]
    if not working_set:
        working_set = sections
    vectors = compute_tfidf(sections)
    section_map = {section.section_id: section for section in working_set}

    assignments: list[tuple[PriorTopic | None, list[Section]]] = []
    assigned_section_ids: set[str] = set()
    prior_topics = prior_topics or []

    for prior_topic in prior_topics:
        cluster = [section_map[section_id] for section_id in prior_topic.section_ids if section_id in section_map]
        if not cluster:
            continue
        if topic_title_is_unhelpful(prior_topic.title):
            continue
        prior_support = topic_title_support(cluster, prior_topic.title)
        if prior_support == 0:
            continue
        assignments.append((prior_topic, sorted(cluster, key=lambda item: (item.doc_title.lower(), item.start_page))))
        assigned_section_ids.update(section.section_id for section in cluster)

    unassigned_sections = [section for section in working_set if section.section_id not in assigned_section_ids]
    if assignments:
        still_unassigned: list[Section] = []
        for section in unassigned_sections:
            best_index = -1
            best_score = 0.0
            for idx, (prior_topic, cluster) in enumerate(assignments):
                score = topic_alignment_score(section, cluster, prior_topic, vectors)
                if score > best_score:
                    best_index = idx
                    best_score = score
            if best_index >= 0 and best_score >= 0.46:
                assignments[best_index][1].append(section)
                assignments[best_index] = (
                    assignments[best_index][0],
                    sorted(assignments[best_index][1], key=lambda item: (item.doc_title.lower(), item.start_page)),
                )
            else:
                still_unassigned.append(section)
        unassigned_sections = still_unassigned

    if unassigned_sections:
        for cluster in cluster_sections(unassigned_sections):
            assignments.append((None, cluster))

    topics: list[Topic] = []
    topic_vectors: dict[str, dict[str, float]] = {}
    used_ids = {prior.topic_id for prior, _ in assignments if prior}

    for prior_topic, cluster in assignments:
        topic, cluster_vector = materialize_topic(cluster, vectors, used_ids=used_ids, prior_topic=prior_topic)
        topics.append(topic)
        topic_vectors[topic.topic_id] = cluster_vector

    topics, topic_vectors = merge_duplicate_topics(topics, topic_vectors, vectors, section_map)
    topics = [
        topic
        for topic in topics
        if topic_should_publish(topic, [section_map[section_id] for section_id in topic.section_ids if section_id in section_map])
    ]
    topic_vectors = {topic.topic_id: topic_vectors[topic.topic_id] for topic in topics if topic.topic_id in topic_vectors}

    link_related_topics(topics, topic_vectors)
    return sorted(topics, key=lambda item: item.title.lower())


def topic_metadata_profile(topic: Topic, document_map: dict[str, Document]) -> dict[str, list[str] | tuple[int, int] | None]:
    documents = [document_map[doc_id] for doc_id in topic.document_ids if doc_id in document_map]
    years = sorted({document.year for document in documents if document.year is not None})
    areas = unique_strings(document.area for document in documents if document.area)
    families = unique_strings(family for document in documents for family in document.families)
    tags = unique_strings(tag for document in documents for tag in document.tags)
    year_span = (years[0], years[-1]) if years else None
    return {
        "years": [str(year) for year in years],
        "areas": areas,
        "families": families,
        "tags": tags,
        "year_span": year_span,
    }


def build_navigation_views(documents: list[Document], topics: list[Topic]) -> dict[str, object]:
    document_map = {document.doc_id: document for document in documents}
    topic_map = {topic.topic_id: topic for topic in topics}
    topics_by_document: defaultdict[str, list[str]] = defaultdict(list)
    for topic in topics:
        for doc_id in topic.document_ids:
            topics_by_document[doc_id].append(topic.topic_id)

    area_groups: defaultdict[str, list[Document]] = defaultdict(list)
    family_groups: defaultdict[str, list[Document]] = defaultdict(list)
    chronology_groups: defaultdict[int, list[Document]] = defaultdict(list)

    for document in documents:
        area_groups[document.area or "Unclassified"].append(document)
        for family in document.families or ["Unspecified"]:
            family_groups[family].append(document)
        if document.year is not None:
            chronology_groups[document.year].append(document)

    def build_group(label: str, docs: list[Document]) -> dict[str, object]:
        topic_ids = sorted(
            {topic_id for document in docs for topic_id in topics_by_document.get(document.doc_id, [])},
            key=lambda item: topic_map[item].title.lower(),
        )
        families = unique_strings(family for document in docs for family in document.families)
        tags = unique_strings(tag for document in docs for tag in document.tags)
        years = sorted({document.year for document in docs if document.year is not None})
        return {
            "label": label,
            "slug": slugify(label),
            "documents": sorted(docs, key=lambda item: ((item.year or 0), item.title.lower())),
            "topics": [topic_map[topic_id] for topic_id in topic_ids],
            "document_count": len(docs),
            "topic_count": len(topic_ids),
            "families": families[:8],
            "tags": tags[:10],
            "years": years,
        }

    areas = sorted(
        (build_group(label, docs) for label, docs in area_groups.items()),
        key=lambda item: (-int(item["document_count"]), str(item["label"]).lower()),
    )
    families = sorted(
        (build_group(label, docs) for label, docs in family_groups.items()),
        key=lambda item: (-int(item["document_count"]), str(item["label"]).lower()),
    )
    chronology = sorted(
        (
            {
                "year": year,
                "documents": sorted(docs, key=lambda item: item.title.lower()),
                "topics": [
                    topic_map[topic_id]
                    for topic_id in sorted(
                        {topic_id for document in docs for topic_id in topics_by_document.get(document.doc_id, [])},
                        key=lambda item: topic_map[item].title.lower(),
                    )
                ],
                "document_count": len(docs),
            }
            for year, docs in chronology_groups.items()
        ),
        key=lambda item: int(item["year"]),
    )

    topic_hubs = []
    for topic in topics:
        profile = topic_metadata_profile(topic, document_map)
        topic_hubs.append(
            {
                "topic": topic,
                "areas": list(profile["areas"]),
                "families": list(profile["families"]),
                "years": list(profile["years"]),
            }
        )
    topic_hubs.sort(
        key=lambda item: (
            len(item["topic"].document_ids),
            len(item["topic"].section_ids),
            len(item["topic"].related_topics),
            item["topic"].quality_score,
        ),
        reverse=True,
    )

    source_hubs = sorted(
        documents,
        key=lambda item: (len(topics_by_document.get(item.doc_id, [])), item.section_count, item.page_count),
        reverse=True,
    )

    return {
        "areas": areas,
        "families": families,
        "chronology": chronology,
        "topic_hubs": topic_hubs[:16],
        "source_hubs": source_hubs[:16],
    }


def write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def append_build_log(log_path: Path, source_path: Path, documents: list[Document], sections: list[Section], topics: list[Topic]) -> None:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    topic_titles = ", ".join(topic.title for topic in sorted(topics, key=lambda item: item.title.lower())[:8])
    area_counts = Counter(document.area or "Unclassified" for document in documents)
    top_areas = ", ".join(
        f"{label} ({count})" for label, count in area_counts.most_common(4)
    )
    run_lines = [
        f"## {timestamp}",
        "",
        f"- Source list: `{source_path}`",
        f"- Documents: {len(documents)}",
        f"- Retained sections: {len(sections)}",
        f"- Topics: {len(topics)}",
        f"- Top areas: {top_areas or 'n/a'}",
        f"- Topic titles: {topic_titles or 'n/a'}",
    ]
    if log_path.exists():
        existing = log_path.read_text(encoding="utf-8").rstrip()
        if not existing:
            existing = "# Build Log"
        content = f"{existing}\n\n" + "\n".join(run_lines) + "\n"
    else:
        content = "# Build Log\n\n" + "\n".join(run_lines) + "\n"
    log_path.write_text(content, encoding="utf-8")


def write_lint_report(paths: dict[str, Path], documents: list[Document], sections: list[Section], topics: list[Topic]) -> None:
    topic_map = {topic.topic_id: topic for topic in topics}
    document_map = {document.doc_id: document for document in documents}
    section_topic_counts: Counter[str] = Counter()
    document_topic_counts: Counter[str] = Counter()
    for topic in topics:
        section_topic_counts.update(topic.section_ids)
        document_topic_counts.update(topic.document_ids)

    orphan_sections = [
        section for section in sections
        if section.clusterable and section.section_id not in section_topic_counts
    ]
    orphan_documents = [
        document for document in documents
        if document.doc_id not in document_topic_counts
    ]
    low_confidence_topics = [
        topic for topic in topics
        if topic.quality_score < 0.68 or len(topic.evidence) < 2
    ]
    single_source_topics = [topic for topic in topics if len(topic.document_ids) == 1]
    sparse_metadata_sources = [
        document for document in documents
        if document.year is None or not document.area or not document.families
    ]
    hub_topics = sorted(
        topics,
        key=lambda item: (len(item.document_ids), len(item.section_ids), len(item.related_topics)),
        reverse=True,
    )

    duplicate_candidates: list[tuple[float, Topic, Topic]] = []
    for index, left in enumerate(topics):
        left_terms = set(left.keywords[:8]) | set(tokenise(left.title))
        for right in topics[index + 1 :]:
            right_terms = set(right.keywords[:8]) | set(tokenise(right.title))
            overlap = len(left_terms.intersection(right_terms) - GENERIC_TOPIC_TERMS)
            title_overlap = len(set(tokenise(left.title)).intersection(tokenise(right.title)) - GENERIC_TOPIC_TERMS)
            shared_docs = len(set(left.document_ids).intersection(right.document_ids))
            score = overlap * 0.12 + title_overlap * 0.2 + shared_docs * 0.08
            if score >= 0.34:
                duplicate_candidates.append((score, left, right))

    lines = [
        "# Maintenance Lint",
        "",
        "This report flags wiki maintenance issues after the current ingest/update run.",
        "",
        "## Snapshot",
        "",
        f"- Documents: {len(documents)}",
        f"- Retained sections: {len(sections)}",
        f"- Topics: {len(topics)}",
        f"- Orphan clusterable sections: {len(orphan_sections)}",
        f"- Sources without topics: {len(orphan_documents)}",
        f"- Low-confidence topics: {len(low_confidence_topics)}",
        f"- Single-source topics: {len(single_source_topics)}",
        f"- Sparse-metadata sources: {len(sparse_metadata_sources)}",
        f"- Possible duplicate topics: {len(duplicate_candidates)}",
        "",
        "## Orphan Sections",
        "",
    ]
    if orphan_sections:
        for section in orphan_sections[:20]:
            lines.append(
                f"- [{section.doc_title}: {section.title}](sources/{section.doc_id}.md#{section.anchor})"
            )
    else:
        lines.append("- None.")

    lines.extend(["", "## Sources Without Topic Coverage", ""])
    if orphan_documents:
        for document in orphan_documents:
            lines.append(f"- [{document.title}](sources/{document.doc_id}.md)")
    else:
        lines.append("- None.")

    lines.extend(["", "## Low-Confidence Topics", ""])
    if low_confidence_topics:
        for topic in low_confidence_topics:
            lines.append(
                f"- [{topic.title}](topics/{topic.topic_id}.md) | quality {topic.quality_score:.2f} | evidence {len(topic.evidence)}"
            )
    else:
        lines.append("- None.")

    lines.extend(["", "## Single-Source Topics", ""])
    if single_source_topics:
        for topic in sorted(single_source_topics, key=lambda item: (len(item.section_ids), item.title.lower()), reverse=True)[:20]:
            source = document_map.get(topic.document_ids[0])
            source_label = source.title if source else topic.document_ids[0]
            lines.append(
                f"- [{topic.title}](topics/{topic.topic_id}.md) | source {source_label} | sections {len(topic.section_ids)}"
            )
    else:
        lines.append("- None.")

    lines.extend(["", "## Sparse-Metadata Sources", ""])
    if sparse_metadata_sources:
        for document in sparse_metadata_sources:
            missing = []
            if document.year is None:
                missing.append("year")
            if not document.area:
                missing.append("area")
            if not document.families:
                missing.append("families")
            lines.append(
                f"- [{document.title}](sources/{document.doc_id}.md) | missing {', '.join(missing)}"
            )
    else:
        lines.append("- None.")

    lines.extend(["", "## Possible Duplicate Topics", ""])
    if duplicate_candidates:
        for score, left, right in sorted(duplicate_candidates, key=lambda item: item[0], reverse=True)[:20]:
            lines.append(
                f"- [{left.title}](topics/{left.topic_id}.md) <> [{right.title}](topics/{right.topic_id}.md) | overlap {score:.2f}"
            )
    else:
        lines.append("- None.")

    lines.extend(["", "## Topic Hubs", ""])
    if hub_topics:
        for topic in hub_topics[:12]:
            lines.append(
                f"- [{topic.title}](topics/{topic.topic_id}.md) | sources {len(topic.document_ids)} | sections {len(topic.section_ids)} | related {len(topic.related_topics)}"
            )
    else:
        lines.append("- None.")

    paths["wiki"].joinpath("lint.md").write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def write_navigation_pages(
    paths: dict[str, Path],
    views: dict[str, object],
    topic_map: dict[str, Topic],
) -> None:
    areas = views["areas"]
    families = views["families"]
    chronology = views["chronology"]
    topic_hubs = views["topic_hubs"]
    source_hubs = views["source_hubs"]

    area_lines = [
        "# Research Areas",
        "",
        "This page groups the corpus by curated research area metadata.",
        "",
    ]
    for area in areas:
        area_lines.extend(
            [
                f"## {area['label']}",
                "",
                f"- Documents: {area['document_count']}",
                f"- Topic pages: {area['topic_count']}",
                f"- Model families: {', '.join(area['families']) if area['families'] else 'n/a'}",
                f"- Tags: {', '.join(area['tags']) if area['tags'] else 'n/a'}",
                "",
                "### Sources",
                "",
            ]
        )
        for document in area["documents"]:
            detail_bits = [str(document.year)] if document.year is not None else []
            if document.venue:
                detail_bits.append(document.venue)
            area_lines.append(
                f"- [{document.title}](sources/{document.doc_id}.md) | {' · '.join(detail_bits) if detail_bits else 'metadata pending'}"
            )
        area_lines.extend(["", "### Topic Pages", ""])
        if area["topics"]:
            for topic in area["topics"][:16]:
                area_lines.append(f"- [{topic.title}](topics/{topic.topic_id}.md)")
        else:
            area_lines.append("- None yet.")
        area_lines.append("")
    (paths["wiki"] / "areas.md").write_text("\n".join(area_lines).strip() + "\n", encoding="utf-8")

    family_lines = [
        "# Model Families",
        "",
        "This page groups the corpus by model family metadata such as decoder-only, seq2seq, retrieval-augmented, or vision-language.",
        "",
    ]
    for family in families:
        family_lines.extend(
            [
                f"## {family['label']}",
                "",
                f"- Documents: {family['document_count']}",
                f"- Topic pages: {family['topic_count']}",
                f"- Research areas: {', '.join(unique_strings(document.area for document in family['documents'] if document.area)) or 'n/a'}",
                "",
                "### Sources",
                "",
            ]
        )
        for document in family["documents"]:
            summary_bits = [document.area or "Unclassified"]
            if document.year is not None:
                summary_bits.append(str(document.year))
            family_lines.append(
                f"- [{document.title}](sources/{document.doc_id}.md) | {' · '.join(summary_bits)}"
            )
        family_lines.extend(["", "### Topic Pages", ""])
        if family["topics"]:
            for topic in family["topics"][:16]:
                family_lines.append(f"- [{topic.title}](topics/{topic.topic_id}.md)")
        else:
            family_lines.append("- None yet.")
        family_lines.append("")
    (paths["wiki"] / "model-families.md").write_text("\n".join(family_lines).strip() + "\n", encoding="utf-8")

    chronology_lines = [
        "# Chronology",
        "",
        "This page arranges the corpus by publication year so the wiki can track conceptual evolution over time.",
        "",
    ]
    for entry in chronology:
        chronology_lines.extend(
            [
                f"## {entry['year']}",
                "",
                f"- Documents: {entry['document_count']}",
                "",
                "### Sources",
                "",
            ]
        )
        for document in entry["documents"]:
            chronology_lines.append(
                f"- [{document.title}](sources/{document.doc_id}.md) | {document.area or 'Unclassified'}"
            )
        chronology_lines.extend(["", "### Topic Pages", ""])
        if entry["topics"]:
            for topic in entry["topics"][:18]:
                chronology_lines.append(f"- [{topic.title}](topics/{topic.topic_id}.md)")
        else:
            chronology_lines.append("- None yet.")
        chronology_lines.append("")
    (paths["wiki"] / "chronology.md").write_text("\n".join(chronology_lines).strip() + "\n", encoding="utf-8")

    hub_lines = [
        "# Connectivity Hubs",
        "",
        "These are the densest topic and source pages in the current corpus.",
        "",
        "## Topic Hubs",
        "",
    ]
    if topic_hubs:
        for item in topic_hubs:
            topic = item["topic"]
            hub_lines.append(
                f"- [{topic.title}](topics/{topic.topic_id}.md) | sources {len(topic.document_ids)} | sections {len(topic.section_ids)} | areas {', '.join(item['areas']) or 'n/a'} | families {', '.join(item['families']) or 'n/a'}"
            )
    else:
        hub_lines.append("- None.")

    hub_lines.extend(["", "## Source Hubs", ""])
    if source_hubs:
        for document in source_hubs:
            hub_lines.append(
                f"- [{document.title}](sources/{document.doc_id}.md) | topics {len(document.topic_ids)} | retained sections {document.section_count} | area {document.area or 'Unclassified'}"
            )
    else:
        hub_lines.append("- None.")
    (paths["wiki"] / "hubs.md").write_text("\n".join(hub_lines).strip() + "\n", encoding="utf-8")


def write_wiki(
    paths: dict[str, Path],
    documents: list[Document],
    sections: list[Section],
    topics: list[Topic],
    source_path: Path,
    views: dict[str, object],
) -> None:
    section_map = {section.section_id: section for section in sections}
    document_map = {document.doc_id: document for document in documents}
    topic_map = {topic.topic_id: topic for topic in topics}
    topics_by_document: defaultdict[str, list[str]] = defaultdict(list)
    topics_by_section: defaultdict[str, list[str]] = defaultdict(list)

    for topic in topics:
        for doc_id in topic.document_ids:
            topics_by_document[doc_id].append(topic.topic_id)
        for section_id in topic.section_ids:
            topics_by_section[section_id].append(topic.topic_id)

    for document in documents:
        document.topic_ids = sorted(topics_by_document.get(document.doc_id, []), key=lambda item: topic_map[item].title.lower())

    index_lines = [
        "# Corpus Index",
        "",
        "This directory is the human-readable map of the compiled PDF corpus.",
        "",
        "## Corpus Snapshot",
        "",
        f"- Source list: `{source_path.name}`",
        f"- Documents: {len(documents)}",
        f"- Retained sections: {len(sections)}",
        f"- Topics: {len(topics)}",
        "- Maintenance report: [Maintenance Lint](lint.md)",
        "- Research areas: [Research Areas](areas.md)",
        "- Model families: [Model Families](model-families.md)",
        "- Chronology: [Chronology](chronology.md)",
        "- Connectivity hubs: [Connectivity Hubs](hubs.md)",
        "",
        "## Corpus Facets",
        "",
    ]
    for area in views["areas"]:
        index_lines.extend(
            [
                f"### {area['label']}",
                "",
                f"- Documents: {area['document_count']}",
                f"- Topic pages: {area['topic_count']}",
                f"- Model families: {', '.join(area['families']) if area['families'] else 'n/a'}",
                "",
            ]
        )
    index_lines.extend(
        [
        "## Topic Directory",
        "",
    ])
    for topic in topics:
        profile = topic_metadata_profile(topic, document_map)
        evidence_links = []
        for item in topic.evidence[:3]:
            evidence_links.append(
                f"[{item.doc_title}: {item.section_title}](sources/{item.doc_id}.md#{item.section_anchor})"
            )
        index_lines.extend(
            [
                f"### [{topic.title}](topics/{topic.topic_id}.md)",
                "",
                topic.summary,
                "",
                f"- Key terms: {', '.join(topic.keywords) if topic.keywords else 'n/a'}",
                f"- Coverage: {len(topic.document_ids)} sources, {len(topic.section_ids)} sections",
                f"- Areas: {', '.join(profile['areas']) if profile['areas'] else 'n/a'}",
                f"- Model families: {', '.join(profile['families']) if profile['families'] else 'n/a'}",
                f"- Evidence trail: {', '.join(evidence_links) if evidence_links else 'n/a'}",
                "",
            ]
        )
    index_lines.extend(["## Source Archive", ""])
    for document in sorted(documents, key=lambda item: item.title.lower()):
        topic_links = [f"[{topic_map[topic_id].title}](topics/{topic_id}.md)" for topic_id in document.topic_ids[:6]]
        index_lines.extend(
            [
                f"### [{document.title}](sources/{document.doc_id}.md)",
                "",
                document.summary,
                "",
                f"- Metadata: {(str(document.year) + ' · ') if document.year is not None else ''}{document.venue + ' · ' if document.venue else ''}{document.area or 'Unclassified'}",
                f"- Model families: {', '.join(document.families) if document.families else 'n/a'}",
                f"- Key terms: {', '.join(document.keywords[:8]) if document.keywords else 'n/a'}",
                f"- Coverage: {document.page_count} pages, {document.section_count} retained sections",
                f"- Contributed topics: {', '.join(topic_links) if topic_links else 'No cross-document topics yet.'}",
                "",
            ]
        )
    (paths["wiki"] / "index.md").write_text("\n".join(index_lines).strip() + "\n", encoding="utf-8")

    append_build_log(paths["wiki"] / "log.md", source_path, documents, sections, topics)
    write_navigation_pages(paths, views, topic_map)

    for document in documents:
        topic_links = [f"[{topic_map[topic_id].title}](../topics/{topic_id}.md)" for topic_id in document.topic_ids]
        lines = [
            f"# {document.title}",
            "",
            "## Document Metadata",
            "",
            f"- Source URL: {document.url}",
            f"- PDF path: `{document.pdf_path}`",
            f"- Extracted text path: `{document.text_path}`",
            f"- Extracted pages: {document.page_count}",
            f"- Retained sections: {document.section_count}",
            f"- Year: {document.year if document.year is not None else 'n/a'}",
            f"- Venue: {document.venue or 'n/a'}",
            f"- Research area: {document.area or 'n/a'}",
            f"- Model families: {', '.join(document.families) if document.families else 'n/a'}",
            f"- Tags: {', '.join(document.tags) if document.tags else 'n/a'}",
            "",
            "## Synopsis",
            "",
            document.summary,
            "",
            "## Key Terms",
            "",
            f"- {', '.join(document.keywords[:10]) if document.keywords else 'n/a'}",
            "",
            "## Section List",
            "",
        ]
        for section_id in document.section_ids:
            section = section_map[section_id]
            section_topic_links = [f"[{topic_map[topic_id].title}](../topics/{topic_id}.md)" for topic_id in topics_by_section.get(section_id, [])]
            lines.extend(
                [
                    f'<a id="{section.anchor}"></a>',
                    f"### {section.title}",
                    "",
                    f"- Pages: {section.start_page}-{section.end_page}",
                    f"- Role: {section.role}",
                    f"- Quality score: {section.quality_score:.2f}",
                    f"- Key terms: {', '.join(section.keywords[:8]) if section.keywords else 'n/a'}",
                    f"- Topic links: {', '.join(section_topic_links) if section_topic_links else 'No topic citations yet.'}",
                    "",
                    section.summary,
                    "",
                ]
            )
        lines.extend(
            [
                "## Topic Links",
                "",
                *([f"- {item}" for item in topic_links] if topic_links else ["- No cross-document topics yet."]),
                "",
            ]
        )
        (paths["sources"] / f"{document.doc_id}.md").write_text("\n".join(lines).strip() + "\n", encoding="utf-8")

    for topic in topics:
        lines = [
            f"# {topic.title}",
            "",
            "## Short Synopsis",
            "",
            topic.summary,
            "",
            "## Key Terms",
            "",
            f"- {', '.join(topic.keywords) if topic.keywords else 'n/a'}",
            "",
            "## Source Sections Used to Derive This Topic",
            "",
        ]
        for item in topic.evidence:
            lines.extend(
                [
                    f"### [{item.doc_title}: {item.section_title}](../sources/{item.doc_id}.md#{item.section_anchor})",
                    "",
                    f"- Pages: {item.start_page}-{item.end_page}",
                    f"- Section role: {item.section_role}",
                    "",
                    item.excerpt,
                    "",
                ]
            )
        lines.extend(["## Related Topics", ""])
        if topic.related_topics:
            for related_id in topic.related_topics:
                lines.append(f"- [{topic_map[related_id].title}]({related_id}.md)")
        else:
            lines.append("- No closely related topics detected.")
        (paths["topics"] / f"{topic.topic_id}.md").write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def compile_documents(specs: list[SourceSpec], paths: dict[str, Path], force: bool) -> tuple[list[Document], list[Section]]:
    documents: list[Document] = []
    sections: list[Section] = []

    for spec in specs:
        pdf_path = download_pdf(spec, paths["raw"])
        doc_stub = stable_slug(spec.title or pdf_path.stem or "document", spec.url, limit=50)
        text_path = paths["extracted"] / f"{doc_stub}.txt"
        raw_text = extract_pdf_text(pdf_path, text_path, force=force)
        pages = [page for page in raw_text.split("\f") if page.strip()]
        title = guess_document_title(spec, pages)
        doc_id = stable_slug(title, spec.url, limit=60)
        document_sections = segment_sections(doc_id, title, pages, spec=spec)
        if not document_sections:
            continue
        sections.extend(document_sections)
        ranked_sections = sorted(document_sections, key=lambda item: (item.clusterable, item.quality_score, item.token_count), reverse=True)
        summary_source = "\n\n".join(section.summary or section.text for section in ranked_sections[:4])
        keywords = extract_keywords(summary_source or "\n\n".join(section.text for section in ranked_sections[:3]), limit=10)
        summary = summarize_text(title, summary_source or "\n\n".join(section.text for section in ranked_sections[:2]), keywords, sentence_limit=4)
        document = Document(
            doc_id=doc_id,
            title=title,
            url=spec.url,
            pdf_path=str(pdf_path),
            text_path=str(text_path),
            section_count=len(document_sections),
            page_count=len(pages),
            summary=summary,
            keywords=keywords,
            topic_ids=[],
            section_ids=[section.section_id for section in document_sections],
            year=spec.year,
            venue=spec.venue,
            area=spec.area,
            families=list(spec.families),
            tags=list(spec.tags),
        )
        documents.append(document)
        write_json(
            paths["extracted"] / f"{doc_id}.sections.json",
            {
                "document": asdict(document),
                "sections": [asdict(section) for section in document_sections],
            },
        )
    return documents, sections


def build_manifest(
    workspace: Path,
    documents: list[Document],
    sections: list[Section],
    topics: list[Topic],
    source_path: Path,
    views: dict[str, object] | None = None,
) -> None:
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workspace": str(workspace),
        "source_file": str(source_path),
        "documents": [asdict(document) for document in documents],
        "sections": [asdict(section) for section in sections],
        "topics": [asdict(topic) for topic in topics],
    }
    if views is not None:
        manifest["navigation"] = {
            "areas": [
                {
                    "label": area["label"],
                    "document_count": area["document_count"],
                    "topic_count": area["topic_count"],
                }
                for area in views["areas"]
            ],
            "families": [
                {
                    "label": family["label"],
                    "document_count": family["document_count"],
                    "topic_count": family["topic_count"],
                }
                for family in views["families"]
            ],
        }
    write_json(workspace / "build.json", manifest)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compile PDFs into a Karpathy-style wiki site.")
    parser.add_argument("--sources", required=True, help="Text file of PDF URLs.")
    parser.add_argument("--workspace", default="workspace", help="Build workspace directory.")
    parser.add_argument("--publish-dir", help="Optional output directory for publishing the generated site, e.g. docs.")
    parser.add_argument("--force", action="store_true", help="Re-extract text from existing raw PDFs.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    source_path = Path(args.sources).resolve()
    workspace = Path(args.workspace).resolve()
    specs = read_sources(source_path)
    if not specs:
        raise SystemExit("No PDF URLs found in the source list.")

    paths = ensure_dirs(workspace)
    prior_topics = load_prior_topics(workspace)
    clean_generated_dirs(paths)
    documents, sections = compile_documents(specs, paths, force=args.force)
    topics = build_topics(sections, documents, prior_topics=prior_topics)
    views = build_navigation_views(documents, topics)
    write_wiki(paths, documents, sections, topics, source_path, views)
    write_lint_report(paths, documents, sections, topics)
    build_manifest(workspace, documents, sections, topics, source_path, views=views)
    render_site(paths["site"], documents, sections, topics, views)
    if args.publish_dir:
        publish_site(paths["site"], Path(args.publish_dir).resolve())
    print(f"Built site at {paths['site'] / 'index.html'}")
    return 0
