# Karpathy Wiki PDF Compiler

This project turns a list of PDF URLs into a browsable, Wikipedia-like static site.

Pipeline:

1. Download PDFs into an immutable `raw/` archive.
2. Extract text and segment each document into chapter-like sections.
3. Cluster related sections across documents into topics.
4. Compile wiki markdown artifacts.
5. Render a static HTML site with an `index.html` landing page and linked topic/source pages.

## Quick Start

Create a source list:

```text
https://arxiv.org/pdf/1706.03762.pdf | Attention Is All You Need
https://arxiv.org/pdf/2005.14165.pdf | Language Models are Few-Shot Learners
```

Run the build:

```bash
python3 build_wiki.py --sources sources.txt --workspace workspace
```

Build and publish a GitHub Pages site into the repo root:

```bash
python3 build_wiki.py --sources sources.txt --workspace workspace --publish-dir .
```

The final site lands in:

```text
workspace/site/index.html
```

The compiled markdown wiki lands in:

```text
workspace/wiki/
```

## Output Layout

- `workspace/raw/`: downloaded PDFs and source metadata.
- `workspace/extracted/`: extracted plain text and section JSON.
- `workspace/wiki/`: Karpathy-style compiled markdown artifacts.
- `workspace/site/`: static HTML site.
- `workspace/build.json`: run manifest.
- repo root publish:
  - `index.html`
  - `style.css`
  - `search.js`
  - `sources/`
  - `topics/`

## Notes

- PDF chapter detection uses document-outline-like heuristics from extracted text. When a PDF lacks clean headings, the pipeline falls back to size-based segmentation so the build still completes.
- Topic synthesis is deterministic and extractive. That keeps the site source-backed and reproducible without requiring an external LLM.

## GitHub Pages

The easiest deploy path is:

```bash
python3 build_wiki.py --sources sources.example.txt --workspace workspace --publish-dir .
```

Then push `main` and configure GitHub Pages to serve from:

- Branch: `main`
- Folder: `/ (root)`

The build writes a root `.nojekyll` file so GitHub Pages serves the static site without Jekyll processing.
