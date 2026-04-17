# AGENTS.md

## Purpose

Maintain a source-backed wiki generated from PDFs.

## Rules

1. Treat `workspace/raw/` as immutable source material.
2. Prefer updating existing topic pages over creating duplicate topics.
3. Every topic page should link back to the source sections that support it.
4. `workspace/wiki/index.md` is the human-readable directory of the corpus.
5. `workspace/wiki/log.md` is append-only and records each compilation run.
6. The static HTML site in `workspace/site/` is generated output, not hand-edited content.

## Topic Page Shape

- Short synopsis
- Key terms
- Source sections used to derive the topic
- Related topics

## Source Page Shape

- Document metadata
- Section list
- Links into topic pages where the document contributed evidence
