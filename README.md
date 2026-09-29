# NCERT Chemistry Experiment Dataset

A lightweight, source-traceable catalog of school Chemistry and Physics experiments and activities for Classes 8-12. This repository contains dataset assets only; it does not clone or depend on the video-generation project or download model weights.

## Repository layout

- `data/chemistry_experiments.json`: canonical source-of-truth records for Chemistry and Physics
- `data/class12_practicals_index.json`: Class 12 practical inventory transcribed from the supplied index image
- `schema/experiment.schema.json`: JSON Schema for validating records
- `exports/`: generated retrieval and prompt-ready files
- `dataset/`: per-experiment JSON files organized by subject and difficulty, plus `metadata.json`
- `scripts/validate_dataset.py`: standard-library validator
- `scripts/build_exports.py`: builds JSONL exports for RAG and prompt generation
- `scripts/build_rag_index.py`: builds the local TF-IDF retrieval index
- `evidence/evidence_graph.json`: generated provenance graph joining catalog experiments and claims to proposed sections and exact extracted PDF pages
- `evidence/reviews.json`: human review decisions and passage hashes; empty until a reviewer approves evidence
- `scripts/build_evidence_graph.py`: rebuilds the local review-gated evidence graph
- `scripts/query_evidence_graph.py`: retrieves a catalog match with manual locations, exact page text, claim links, status, and nearby experiments
- `scripts/query_rag.py`: searches the local retrieval index
- `scripts/build_rag_prompt_bundle.py`: retrieves experiments and creates grounded scene-step prompts
- `scripts/build_pipeline_handoff.py`: validates an evidence-cleared experiment against the image-to-video `Experiment`/`Clip` contract
- `scripts/approve_vertical_slice.py`: records the small reviewed PDF-backed vertical slice
- `scripts/api_prompt_variation_test.py`: sends prompt variants to a video-generation API
- `requirements.txt`: dependencies for the local RAG index

The PDF audit tools use `pypdf`. The original manual PDFs are external source materials and are not required to run the existing dataset/RAG checks; provide their local paths when rebuilding the evidence extraction files.

The evidence graph is JSON so it stays inspectable and works locally without a graph service. Experiment and claim links derived from titles or text overlap are `candidate` edges. They are not citations or scientific verification. To approve a section or a claim, add an explicit entry to `evidence/reviews.json` with reviewer, review date, the manual hash and passage text hashes, then rebuild the graph. Pages with extraction warnings also require an explicit visual check. The query command returns `no_link_in_supplied_pdfs` when neither supplied manual contains a candidate section; that status does not mean no official source exists.

Review entries are keyed by stable section and claim IDs. A section review records `status: "approved_for_retrieval"`, reviewer, review date, the source PDF SHA-256, and a `passage_hashes` map copied from the referenced pages. A claim review records `status: "verified"`, reviewer, review date, the approved `passage_ids`, and matching passage hashes. Add flagged pages to `visually_checked_passage_ids` only after checking the rendered PDF page. The graph builder rejects stale hashes, missing reviewer metadata, and approvals that omit a flagged page. Claim support approvals never mark neighboring claims as verified.

After extracting or changing review decisions, rebuild sections and the graph:

```powershell
python scripts/ingest_manuals.py ..\Manual_01.pdf ..\Physics_Laboratory_Manual_11-12_E.pdf
python scripts/link_manual_sections.py
python scripts/migrate_evidence.py
python scripts/apply_evidence_reviews.py
python scripts/build_evidence_graph.py
python scripts/query_evidence_graph.py "Determine the boiling point of an organic compound" --top-n 1
```

The prompt builder now returns a review report with zero prompt inputs until each included action, observation, material, safety note, scene and step-to-scene link has verified source support. An explicit experiment ID selects a catalog record but does not bypass its evidence gate. Images remain optional placeholders.

## Evidence-gated pipeline handoff

The current CPU-only vertical slice uses `chem_12_101` (boiling point, Manual_01.pdf printed pages 17-18 / PDF pages 28-29). It maps to ordered pipeline clips without starting image or video generation:

```powershell
python scripts/approve_vertical_slice.py
python scripts/apply_evidence_reviews.py
python scripts/build_evidence_graph.py
python scripts/build_pipeline_handoff.py --experiment-id chem_12_101 --output reports/boiling_point_pipeline_handoff.json
python scripts/build_pipeline_handoff.py --experiment-id chem_9_001 --output reports/diffusion_pipeline_handoff.json
```

The first handoff should be `ready` with three ordered clips and passage IDs on every clip. The diffusion record is intentionally `blocked` because it has no matching passage in the supplied PDFs. The handoff maps to the downstream pipeline's `Experiment`, `Clip`, `Scene`, and `PromptBundle` fields, but leaves the starting image as `placeholder_requires_manual_image`.

The canonical catalog retains stable IDs and records review states for claims, source sections, retrieval eligibility, and video readiness. `evidence/passages.jsonl`, `evidence/sections.json`, and `evidence/evidence_graph.json` are generated evidence artifacts; `evidence/reviews.json` is the human-authored review overlay. A schema-valid record is not automatically source-verified. After editing reviews, run `python scripts/apply_evidence_reviews.py` and rebuild the graph. Keep each scene link at `needs_review` until that step-to-scene mapping has been checked; source claim approval alone does not make an experiment video-ready.

## Data contract

Each experiment has a stable `experiment_id`, class and subject metadata, learning goal, materials, ordered procedure steps, visual scenes, source references, and image metadata. `source_status` distinguishes records that still need manual source verification from verified records.

The canonical file is deliberately more detailed than the current video pipeline input. The video pipeline should consume a derived export, not become the source of truth.

`Manual_01.pdf` is the authoritative Chemistry source for the current Class 12 records. `Physics_Laboratory_Manual_11-12_E.pdf` is the authoritative Physics source for the current Classes XI-XII inventory. The photographed Chemistry index is retained only as superseded provenance in `data/class12_practicals_index.json`; its page numbers and formulas do not control the canonical catalog.

## Quick start

From this directory, create and activate the repository-local environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Validate the dataset and rebuild its derived exports:

```powershell
python scripts/validate_dataset.py
python scripts/build_exports.py
python scripts/build_dataset_directory.py
```

The exporter creates:

- `exports/chemistry_experiments.jsonl`: one complete record per line
- `exports/rag_documents.jsonl`: one searchable text document per experiment
- `exports/prompt_inputs.jsonl`: compact inputs for generating scene/prompt bundles

To build the directory-form dataset requested by downstream tooling:

```powershell
python scripts/build_dataset_directory.py
```

This creates `dataset/physics/{easy,medium,hard}/`, `dataset/chemistry/{easy,medium,hard}/`, and `dataset/metadata.json`. The image folders contain placeholders only; each record points to the expected local image path until a real, license-reviewed image is added.

To build or refresh the local RAG index:

```powershell
python scripts/build_rag_index.py
python scripts/demo_rag.py
```

The interactive search is domain-constrained. A confident result is labeled `confident_match`; a close but ambiguous query is labeled `selection_required` and shows nearby catalog options; a weak or unsupported query is labeled `out_of_scope` and does not silently choose an experiment for the user.

To evaluate retrieval against the calibration and holdout benchmark:

```powershell
python scripts/evaluate_benchmark.py --output reports/benchmark_evaluation.json
```

The evaluator reports top-1 accuracy, Recall@5, and abstention for unsupported or ambiguous queries. Use `--split holdout` for the held-out subset and `--min-score` to tune confidence on the calibration subset. The default margin is zero because close scores can still represent valid neighboring experiments.

To rebuild extracted PDF evidence from local source files:

```powershell
python scripts/ingest_manuals.py ..\Manual_01.pdf ..\Physics_Laboratory_Manual_11-12_E.pdf
python scripts/link_manual_sections.py
python scripts/audit_dataset.py
```

To retrieve an experiment and build prompts from its canonical scenes and procedure:

```powershell
python scripts/build_rag_prompt_bundle.py "ohm law" --top-k 1 --output exports/ohm_law_prompt_bundle.json
```

The prompt planner requires one selected experiment and returns a review report with zero prompt inputs while required claims or step-to-scene links remain unverified. Once the evidence gate passes, the bundle carries passage IDs alongside each step prompt. Do not send a review report to the API harness.

```powershell
python scripts/api_prompt_variation_test.py --prompts-file exports/ohm_law_prompt_bundle.json --url http://localhost:8000/generate --json-output exports/ohm_law_api_results.json
```

To run prompt variations against the video-generation API:

```powershell
python scripts/api_prompt_variation_test.py --url http://localhost:8000/generate --json-output results.json
```

The API server must already be running at that URL. This repository contains the client harness, but does not yet contain a local video-generation server or model runner.

## Source and image policy

NCERT is the primary curriculum anchor. The initial catalog uses official NCERT textbook and laboratory-manual landing pages as references, with page-level citations to be filled during source verification. Image fields may contain placeholders until a real, license-compatible image is selected. Do not treat a placeholder as a usable image asset.

## Scope

The current seed contains Chemistry Classes 8-12 and the Physics Classes XI-XII experiments and activities listed in the supplied manual. Physics records are initially marked `source_review`; their titles and source provenance are manual-grounded, while exact page-level citations, apparatus quantities, and real image assets remain a follow-up enrichment pass.

## Versioned CPU clip-plan export

`schema/clip_plan.schema.json` defines the provider-independent v1 handoff. Export with:

```bash
python scripts/plan_experiment.py --query "boiling point organic compound"
python scripts/plan_experiment.py --experiment-id chem_12_101 --output reports/boiling_point_clip_plan.json
```

Queries return candidates and zero clips; an explicit ID is required to plan. Evidence-blocked and unknown IDs also produce zero clips. The ready plan carries stable IDs, per-clip passage references, original source metadata, scene transitions, and dataset content hashes. The existing review gate remains authoritative; this exporter does not create approvals. Image and video review remain pending.

Duration defaults to one second per action, explicitly marked `provisional_cpu_test`. Use `--durations path.json` to override individual clip IDs in seconds; no experiment-wide duration division is used. Provide scene images to the downstream runner. The matching installable CPU runner and notebook live in `ssoommeesshh/image-to-video-pipeline`, branch `feat/cpu-notebook-module`. Its packaged copy of this schema must be kept identical.

Run planner tests with `python -m pytest tests -q` after installing pytest. The checked-in example is a snapshot: rebuild it when data or review records change.

Evidence graph and plan revision hashes normalize text line endings to LF so Windows and Linux checkouts agree. PDF and passage content hashes retain their original semantics.
