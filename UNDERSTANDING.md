# Karpathy LLM Wiki: Research Synthesis

## What it is

Andrej Karpathy's "LLM Wiki" is not a product or a finished implementation. It is a design pattern for building a persistent knowledge base where an LLM incrementally maintains a markdown wiki from a growing collection of source materials.

The central claim is:

- Typical document chat and RAG workflows answer each question by retrieving raw fragments again.
- An LLM wiki instead compiles knowledge into durable pages, links, summaries, comparisons, and logs that persist across sessions.
- The artifact compounds over time because the LLM keeps updating the wiki instead of re-deriving everything from scratch.

The gist is best read as an architecture memo or promptable operating model for an agent, not as a drop-in codebase.

## The core mental model

Karpathy frames the wiki as a layer between raw sources and the user:

1. Raw sources are immutable and remain the source of truth.
2. The wiki is LLM-written markdown that stores synthesized understanding.
3. A schema file such as `AGENTS.md` or `CLAUDE.md` tells the agent how to maintain the wiki consistently.

That makes the workflow feel more like "knowledge compilation" than plain retrieval.

Useful shorthand:

- RAG: retrieve and answer.
- LLM Wiki: ingest, synthesize, persist, then answer from the maintained synthesis.

## How it is supposed to work

Karpathy's gist describes three recurring operations:

- Ingest: add a source, have the agent read it, summarize it, update related pages, and log the change.
- Query: ask a question against the wiki, then optionally write the answer back into the wiki as a durable artifact.
- Lint: ask the agent to check for contradictions, stale claims, orphan pages, missing concepts, and possible gaps worth researching.

Two files are especially important:

- `index.md`: a content-oriented map of the wiki.
- `log.md`: an append-only chronological history of ingests, queries, and maintenance.

At smaller scale, Karpathy suggests the index alone can be enough to navigate the wiki. As the system grows, he explicitly suggests adding a proper search layer.

## Why people find the idea compelling

The pattern is attractive because it shifts the LLM from "answer machine" to "maintainer of a long-lived knowledge artifact."

What is genuinely strong about the idea:

- It preserves raw sources separately from synthesized knowledge.
- It creates durable outputs instead of losing everything in chat history.
- It encourages cross-linking and contradiction tracking earlier, during ingestion.
- It fits existing tools people already like, especially Obsidian and git-backed markdown repos.

This is why the gist spread quickly: it gives a simple, legible operating model for long-term memory without requiring a heavyweight database-first architecture.

## What Karpathy is really optimizing for

The problem he is targeting is not just search quality. It is bookkeeping.

The thesis is that humans abandon personal or team wikis because maintaining links, summaries, updates, and consistency is tedious. LLMs are good at exactly that kind of repetitive cross-file maintenance, so the wiki can stay alive instead of decaying.

In Karpathy's framing:

- humans curate sources, steer investigation, and ask good questions;
- the LLM handles summarizing, filing, cross-referencing, and routine upkeep.

That division of labor is the heart of the proposal.

## Tooling assumptions in the original gist

The original note is strongly shaped by a markdown-and-files workflow:

- Obsidian is the preferred browsing environment.
- Web clipping is an easy way to collect sources into markdown.
- Graph view helps inspect structure and orphans.
- Optional plugins and tools like Dataview, Marp, and QMD extend querying, presentation, and local search.
- The wiki can simply live in a git repo.

So the pattern is local-first and file-first by design, not SaaS-first.

## What it is not

It is easy to misread the gist as one of these, but it is not:

- not a replacement for source documents;
- not a guarantee of truth;
- not a complete memory system by itself;
- not a universal schema for every domain;
- not an argument against RAG in all cases.

It is better understood as a practical middle layer:

- more structured and persistent than chat-with-files;
- lighter and more legible than a full custom knowledge graph stack;
- more synthesis-oriented than classic retrieval pipelines.

## Likely strengths

If implemented well, the strongest benefits are:

- accumulated understanding instead of repeated rediscovery;
- human-readable intermediate state in markdown;
- easier collaboration with an LLM because the knowledge artifact is inspectable;
- natural support for research projects, book notes, due diligence, course notes, coding knowledge, and team memory;
- a workflow that can start extremely small and remain useful before "real infrastructure" exists.

The "small and useful first" property is a major reason the idea resonated.

## Likely failure modes

The original gist already hints at several limits, and follow-on builders make them more explicit.

### 1. Drift and trust

Because the wiki stores synthesized claims, it can become confidently wrong if provenance is weak or updates are sloppy. Karpathy partly addresses this by keeping raw sources immutable and recommending periodic linting, but the problem does not disappear.

### 2. Scale pressure

Karpathy says the plain `index.md` approach works surprisingly well only at moderate scale. Once the wiki becomes large, search, retrieval quality, and maintenance mechanics become first-order concerns.

### 3. Maintenance can move rather than vanish

A recurring critique from early builders is that wiki maintenance can turn into a different kind of maintenance burden: schema rules, lint passes, page taxonomies, and supervision of the agent itself.

### 4. Source-shaped pages can recreate the original problem

If ingestion produces one page per source file or document, the knowledge base may still be organized around the corpus rather than around the questions the user actually asks. In that case, the agent still has to re-synthesize scattered information at query time.

### 5. Long-session instruction decay

Some builders argue that giant prompt files and long sessions make the maintenance rules less reliable over time, which pushes the design toward stronger workflow enforcement or more structured provenance.

## How the community is already extending the idea

Within days of the gist, builders were already pushing the pattern in two directions:

### Direction A: stronger wiki maintenance

One extension keeps the wiki model but adds things like:

- confidence scoring for claims;
- recency and contradiction handling;
- hybrid search beyond a flat index;
- more automation around ingest and lint;
- stronger support for larger collections.

This treats Karpathy's model as correct in spirit, but incomplete at scale.

### Direction B: smaller claims and graph-like memory

Another extension argues that "markdown wiki pages" are still too coarse. Instead of large wiki articles, it stores smaller sourced claims or propositions, often with provenance and validation on read. The main idea here is that the agent should walk a graph of compact knowledge units rather than re-read broad markdown articles.

This is less "wiki as pages" and more "wiki as compiled knowledge graph with markdown ergonomics."

## My synthesis

The best way to understand Karpathy's note is:

- It is a proposal for compiled memory.
- The durable artifact is the main product.
- Markdown is chosen because it is inspectable, editable, diffable, and easy for agents to operate on.
- The real design challenge is not ingesting one document. It is keeping the compiled knowledge trustworthy as sources, questions, and scale change.

So the idea is strong, but the hard part starts after the first week:

- provenance,
- refresh mechanics,
- scope control,
- schema evolution,
- search quality,
- and deciding the right unit of memory.

## Practical takeaway if you want to build one

A good MVP would stay close to Karpathy's original shape:

- `raw/` for immutable sources
- `wiki/` for agent-maintained markdown
- `AGENTS.md` for conventions and workflows
- `wiki/index.md`
- `wiki/log.md`

Then keep the process disciplined:

1. Ingest one source at a time.
2. Require the agent to update existing pages, not only add new ones.
3. Keep explicit links back to sources.
4. Run periodic lint or review passes.
5. Add better search only when the simple index stops being enough.

If it grows beyond a few hundred pages or starts drifting, that is the moment to add stronger provenance, retrieval, and workflow mechanics instead of just writing a bigger prompt.

## Bottom line

Karpathy's LLM Wiki is best understood as a high-leverage pattern for turning LLMs into maintainers of a persistent knowledge artifact. Its core insight is good: do not keep re-reading the world from scratch if the agent can continuously compile what it learns into a navigable, updateable wiki.

The open question is not whether the pattern is useful. It clearly is. The open question is what structure keeps that compiled knowledge reliable as it scales: markdown pages, hybrid search, explicit provenance, smaller claims, or some graph-backed variant.

## Sources

- Original gist: https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f
- Obsidian Web Clipper: https://obsidian.md/clipper
- Obsidian Graph View help: https://obsidian.md/help/Plugins/Graph%2Bview
- Dataview docs: https://blacksmithgu.github.io/obsidian-dataview/
- QMD repo: https://github.com/tobi/qmd
- LLM Wiki v2 gist: https://gist.github.com/rohitg00/2067ab416f7bbe447c1977edaaa681e2
- "Here's What Breaks" critique gist: https://gist.github.com/Jwcjwc12/6bfb80a0bd274cb965deb5dbd2f5d63f
- Chroma Context Rot report: https://www.trychroma.com/research/context-rot
