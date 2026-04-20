# Karpathy Wiki PDF Maintainer

This project turns a list of PDF URLs into a source-backed wiki that is maintained across runs and rendered as a browsable static site.

Pipeline:

1. Download PDFs into an immutable `raw/` archive.
2. Extract text and segment each document into chapter-like sections.
3. Reuse prior wiki state when available and match new sections into existing topics.
4. Create new topics only for unmatched material.
5. Compile wiki markdown artifacts, including a maintenance lint report.
6. Render a static HTML site with an `index.html` landing page and linked topic/source pages.

## Quick Start

Create a source list:

```text
https://arxiv.org/pdf/1706.03762.pdf | Attention Is All You Need | year=2017; venue=NeurIPS; area=Foundation Models; families=Transformer,Encoder-Decoder; tags=attention,sequence-modeling
https://arxiv.org/pdf/2005.14165.pdf | Language Models are Few-Shot Learners | year=2020; venue=NeurIPS; area=Scaling and Foundation Models; families=Decoder-Only,In-Context Learning; tags=few-shot,scaling,emergence
```

The source format is:

```text
URL | Optional Title | year=YYYY; venue=...; area=...; families=a,b; tags=x,y
```

Run the build:

```bash
python3 build_wiki.py --sources sources.txt --workspace workspace
```

Build and publish a GitHub Pages site into `docs/`:

```bash
python3 build_wiki.py --sources sources.txt --workspace workspace --publish-dir docs
```

The final site lands in:

```text
workspace/site/index.html
```

The compiled markdown wiki lands in:

```text
workspace/wiki/
```

An advanced curated corpus is included at:

```text
sources.advanced.txt
```

## Output Layout

- `workspace/raw/`: downloaded PDFs and source metadata.
- `workspace/extracted/`: extracted plain text and section JSON.
- `workspace/wiki/`: Karpathy-style compiled markdown artifacts.
- `workspace/wiki/areas.md`: corpus grouped by curated research area.
- `workspace/wiki/model-families.md`: corpus grouped by architectural/workflow family.
- `workspace/wiki/chronology.md`: corpus organized by publication year.
- `workspace/wiki/hubs.md`: densest topic/source hubs in the current build.
- `workspace/wiki/lint.md`: maintenance report for orphan sections, weak topics, and duplicates.
- `workspace/site/`: static HTML site.
- `workspace/build.json`: run manifest.
- `docs/`: published static site snapshot for GitHub Pages.

## Notes

- PDF chapter detection uses document-outline-like heuristics from extracted text. When a PDF lacks clean headings, the pipeline falls back to size-based segmentation so the build still completes.
- Topic maintenance is incremental. Stable document IDs, section IDs, and topic IDs are preserved across repeated runs so existing wiki pages are updated instead of being replaced wholesale.
- Curated metadata now matters. Area, family, year, venue, and tags are carried into the wiki, the static site, and the maintenance reports.
- Topic synthesis is still deterministic and extractive. That keeps the site source-backed and reproducible without requiring an external LLM, but the maintenance model now behaves more like a Karpathy-style persistent wiki than a one-shot site generator.

## GitHub Pages

The easiest deploy path is:

```bash
python3 build_wiki.py --sources sources.example.txt --workspace workspace --publish-dir docs
```

Then push `main` and configure GitHub Pages to serve from:

- Branch: `main`
- Folder: `/docs`

The build writes a `.nojekyll` file into `docs/` so GitHub Pages serves the static site without Jekyll processing.
