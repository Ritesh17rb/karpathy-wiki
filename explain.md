# Project Explanation

## What This Project Is

This project builds a **Karpathy-wiki-style knowledge site from PDFs**.

The goal is not to create a PDF folder or a chatbot.  
The goal is to convert a set of PDFs into a **structured, browsable, topic-first wiki** with:

- preserved raw PDF sources,
- extracted chapter-like sections,
- clustered topics across documents,
- synthesized wiki pages,
- and a final static website with `index.html`.

This matches the intent of a "Karpathy wiki" workflow:

- keep the raw sources,
- compile understanding into durable artifacts,
- organize knowledge into linked pages,
- and make the output easy to browse like Wikipedia.

## What We Have Built

We built a complete local pipeline that does the following:

1. Reads a text file containing PDF URLs.
2. Downloads each PDF into an immutable raw archive.
3. Extracts text from each PDF.
4. Splits the extracted text into chapter-like or section-like chunks.
5. Filters noisy sections such as references, appendices, and badly structured sections when building topic pages.
6. Clusters related sections across documents into topics.
7. Generates wiki markdown artifacts for sources and topics.
8. Generates a static HTML website with:
   - a homepage `index.html`,
   - topic pages,
   - source pages,
   - and search.

## High-Level Architecture

The architecture is a pipeline with four layers:

1. **Input Layer**
   - source list file with PDF URLs
   - optional custom titles

2. **Corpus Layer**
   - raw downloaded PDFs
   - extracted plain text
   - per-document section JSON

3. **Knowledge Compilation Layer**
   - section segmentation
   - keyword extraction
   - topic clustering
   - topic summaries
   - source summaries
   - wiki markdown generation

4. **Presentation Layer**
   - static HTML pages
   - homepage index
   - topic directory
   - source archive pages
   - client-side search

## Data Flow

The pipeline flow is:

```text
sources.txt
  -> download PDFs
  -> extract text with pdftotext
  -> split into sections
  -> compute keywords and token stats
  -> filter noisy sections for clustering
  -> cluster sections into topics
  -> generate markdown wiki
  -> render static HTML
  -> workspace/site/index.html
```

## Project Structure

The main project files are:

- [build_wiki.py](/home/ritesh/karpathy-wiki/build_wiki.py)
- [karpathy_wiki/pipeline.py](/home/ritesh/karpathy-wiki/karpathy_wiki/pipeline.py)
- [karpathy_wiki/site.py](/home/ritesh/karpathy-wiki/karpathy_wiki/site.py)
- [karpathy_wiki/templates/index.html.j2](/home/ritesh/karpathy-wiki/karpathy_wiki/templates/index.html.j2)
- [karpathy_wiki/templates/topic.html.j2](/home/ritesh/karpathy-wiki/karpathy_wiki/templates/topic.html.j2)
- [karpathy_wiki/templates/document.html.j2](/home/ritesh/karpathy-wiki/karpathy_wiki/templates/document.html.j2)
- [karpathy_wiki/static/style.css](/home/ritesh/karpathy-wiki/karpathy_wiki/static/style.css)
- [karpathy_wiki/static/search.js](/home/ritesh/karpathy-wiki/karpathy_wiki/static/search.js)
- [README.md](/home/ritesh/karpathy-wiki/README.md)
- [AGENTS.md](/home/ritesh/karpathy-wiki/AGENTS.md)

The generated output lives in:

- `workspace/raw/`
- `workspace/extracted/`
- `workspace/wiki/`
- `workspace/site/`
- `workspace/build.json`

## Main Components

### 1. CLI Entrypoint

File:

- [build_wiki.py](/home/ritesh/karpathy-wiki/build_wiki.py)

This is the small entrypoint that runs the pipeline.  
It delegates everything to `karpathy_wiki.pipeline.main()`.

### 2. Pipeline Engine

File:

- [karpathy_wiki/pipeline.py](/home/ritesh/karpathy-wiki/karpathy_wiki/pipeline.py)

This is the core backend. It handles:

- parsing the source list,
- creating workspace folders,
- cleaning previously generated artifacts,
- downloading PDFs,
- extracting text,
- section segmentation,
- keyword extraction,
- TF-IDF style vector creation,
- section clustering,
- topic generation,
- wiki markdown generation,
- manifest generation,
- and site rendering.

This file is the main "brain" of the project.

### 3. Site Renderer

File:

- [karpathy_wiki/site.py](/home/ritesh/karpathy-wiki/karpathy_wiki/site.py)

This module converts the compiled knowledge into a static website.

It renders:

- one homepage,
- one page per topic,
- one page per source document.

It also builds the client-side search index embedded into the homepage.

### 4. Templates

Files:

- [karpathy_wiki/templates/index.html.j2](/home/ritesh/karpathy-wiki/karpathy_wiki/templates/index.html.j2)
- [karpathy_wiki/templates/topic.html.j2](/home/ritesh/karpathy-wiki/karpathy_wiki/templates/topic.html.j2)
- [karpathy_wiki/templates/document.html.j2](/home/ritesh/karpathy-wiki/karpathy_wiki/templates/document.html.j2)

These Jinja templates define the final HTML layout.

The homepage behaves like a compact wiki directory:

- topic cards,
- source cards,
- project summary,
- search box.

### 5. Static Assets

Files:

- [karpathy_wiki/static/style.css](/home/ritesh/karpathy-wiki/karpathy_wiki/static/style.css)
- [karpathy_wiki/static/search.js](/home/ritesh/karpathy-wiki/karpathy_wiki/static/search.js)

`style.css` gives the site a wiki/editorial look.  
`search.js` provides simple client-side search over topics and source pages.

## How the Pipeline Works

### Step 1. Read Source URLs

The build starts from a text file like:

```text
https://arxiv.org/pdf/1706.03762.pdf | Attention Is All You Need
https://arxiv.org/pdf/2005.14165.pdf | Language Models are Few-Shot Learners
```

Each line contains:

- a PDF URL,
- and optionally a custom title after `|`.

### Step 2. Download PDFs

Each PDF is downloaded into:

```text
workspace/raw/
```

These raw files are treated as the immutable source archive.

### Step 3. Extract Text

The project uses `pdftotext` to extract plain text from each PDF.

Why:

- simple,
- fast,
- available locally,
- deterministic.

The extracted text is stored in:

```text
workspace/extracted/
```

### Step 4. Segment into Sections

The pipeline then tries to split the document into chapter-like sections.

It does this using heading heuristics:

- numbered headings,
- title-like headings,
- uppercase headings,
- common section markers like chapter/section/appendix.

If the PDF has weak structure, the pipeline falls back to chunking by page blocks.

This gives us section objects with:

- title,
- document id,
- page range,
- body text,
- token count,
- keywords.

### Step 5. Filter Noisy Sections

Not every extracted section is useful for topic clustering.

For example:

- references,
- appendices,
- answer keys,
- tables,
- repeated noisy headings,
- heavily citation-shaped sections.

These sections are still preserved in source pages, but they are filtered out from the topic clustering path when possible.

That is important because otherwise the wiki becomes a junk pile of references and appendix fragments.

### Step 6. Compute Keywords and Similarity

For each section, we extract tokens and build lightweight TF-IDF-like vectors.

These vectors are used to estimate semantic closeness between sections.

This allows the system to group related sections across multiple PDFs without requiring an external embedding API.

### Step 7. Cluster Sections into Topics

Clusterable sections are grouped into topic clusters.

Each cluster becomes a topic page with:

- a topic title,
- top keywords,
- a summary,
- source section links,
- related topics.

This is the key step that turns document fragments into a topic-first wiki.

### Step 8. Generate Wiki Markdown

The project writes markdown output into:

```text
workspace/wiki/
```

This includes:

- `index.md`
- `log.md`
- topic markdown pages
- source markdown pages

This is the Karpathy-wiki-style persistent artifact layer.

The markdown is useful because it is:

- readable,
- diffable,
- inspectable,
- and easy to regenerate.

### Step 9. Render Static HTML

The final step renders the HTML site into:

```text
workspace/site/
```

That includes:

- `index.html`
- topic pages under `topics/`
- source pages under `sources/`
- static CSS and JS

This is the end-user deliverable.

## Why This Design Was Chosen

We intentionally chose a **local-first, deterministic, no-API-required architecture**.

Reasons:

- easier to run anywhere,
- no dependency on external LLM APIs,
- faster iteration,
- easier debugging,
- reproducible output,
- simpler deployment.

This is a pragmatic MVP architecture.

Instead of depending on a remote model for every step, we built:

- heuristics for sectioning,
- extractive summarization,
- keyword-based topic naming,
- local clustering,
- static rendering.

That makes the project stable enough to demonstrate the product idea cleanly.

## Karpathy Wiki Interpretation

This project uses the "Karpathy wiki" idea in this practical form:

- raw PDFs are the truth layer,
- extracted sections are the intermediate layer,
- wiki markdown pages are the compiled knowledge layer,
- HTML pages are the presentation layer.

So the project is not just "chat over PDFs."  
It is "compile PDFs into a persistent knowledge artifact."

## Generated Artifacts

When a build runs, the important outputs are:

### Raw Corpus

- `workspace/raw/*.pdf`

### Extraction Layer

- `workspace/extracted/*.txt`
- `workspace/extracted/*.sections.json`

### Knowledge Layer

- `workspace/wiki/index.md`
- `workspace/wiki/log.md`
- `workspace/wiki/topics/*.md`
- `workspace/wiki/sources/*.md`

### Presentation Layer

- `workspace/site/index.html`
- `workspace/site/topics/*.html`
- `workspace/site/sources/*.html`

### Build Metadata

- `workspace/build.json`

## Current Limitations

This project is complete as a working pipeline, but it is still an MVP.

Known limitations:

1. PDF chapter detection is heuristic.
   - Some PDFs have messy layouts.
   - Some extracted headings are imperfect.

2. Summarization is extractive, not model-generated.
   - This keeps things deterministic, but not as polished as a true LLM synthesis layer.

3. Topic clustering is token/statistics based.
   - It works reasonably for related documents, but it is not as semantically deep as embeddings plus an LLM.

4. OCR-heavy scanned PDFs are not yet handled specially.
   - If the PDF text layer is bad, extraction quality will drop.

5. The homepage is wiki-like, but still a compact MVP.
   - It can be made richer with infoboxes, better navigation, timelines, or citations.

## How It Can Be Extended

Future improvements could include:

1. Better chapter detection using PDF outlines or layout parsing.
2. OCR integration for scanned PDFs.
3. Embedding-based clustering.
4. LLM-based synthesis for better topic pages.
5. Explicit citations inline on topic pages.
6. Stronger taxonomy and category pages.
7. Search across section text, not just page metadata.
8. Static site export with richer Wikipedia-like UI patterns.

## In One Sentence

This project takes PDFs and turns them into a **source-backed, topic-clustered, Karpathy-style wiki with a final static `index.html` website**.
