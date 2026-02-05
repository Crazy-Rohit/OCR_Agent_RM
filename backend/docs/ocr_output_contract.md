# Universal OCR Agent – Output Contract (V0)

This document describes the **stable, universal output format** returned by the backend OCR API in **Milestone V0 (Baseline Stabilization)**.

The goals of V0 are:

- Keep existing working behavior intact
- Provide a consistent response shape for all consuming projects (Prior Auth, Discovery, etc.)
- Enable safe monitoring and regression testing

## Endpoints

- **Single**: `POST /api/v1/ocr`
- **Batch**: `POST /api/v1/ocr/batch`

## Content Types

- `multipart/form-data` upload

### Parameters

| Field | Type | Default | Notes |
|---|---|---:|---|
| `file` | file | required | Single document |
| `files` | file[] | required | Batch documents |
| `document_type` | string | `generic` | Consumer hint; does not change OCR engine in V0 |
| `zero_retention` | bool | `true` | If `true`, uploaded files are **not** retained on disk |
| `enable_layout` | bool | `true` | If `true`, include words/lines/blocks/tables (bigger payload) |

## OCRResponse schema

### Top level

| Field | Type | Description |
|---|---|---|
| `job_id` | string (uuid) | Unique id per OCR run |
| `status` | string | `success` for successful extraction |
| `document_type` | string | Echoes request `document_type` |
| `pages` | `PageText[]` | Per-page extraction |
| `full_text` | string | All page texts joined with blank lines |
| `metadata` | object | Engine + timing + file attributes |

### PageText

| Field | Type | Description |
|---|---|---|
| `page_number` | int | 1-based page index |
| `text` | string | Page-level text |
| `words` | `WordBox[] | null` | Present when `enable_layout=true` and OCR path used |
| `lines` | `LineBox[] | null` | Derived from words |
| `blocks` | `BlockBox[] | null` | Derived from lines |
| `tables` | `TableBox[] | null` | Table candidates; may include structured rows/cols when possible |

### WordBox

| Field | Type | Description |
|---|---|---|
| `text` | string | Recognized token |
| `x1,y1,x2,y2` | int | Bounding box in image/pixel coordinates |
| `confidence` | float | null | OCR confidence when available |

### metadata

| Field | Type | Description |
|---|---|---|
| `file_name` | string | Original filename |
| `file_type` | string | Extension (e.g., `pdf`, `png`) |
| `num_pages` | int | Number of pages returned |
| `processing_time_ms` | int | End-to-end OCR time |
| `engine` | string | `tesseract` in V0 |
| `zero_retention` | bool | Echoes effective retention policy |
| `enable_layout` | bool | Echoes effective layout setting |

## Batch response

`POST /api/v1/ocr/batch` returns:

| Field | Type | Description |
|---|---|---|
| `status` | string | `success` if the batch request succeeded |
| `document_type` | string | Echo |
| `zero_retention` | bool | Echo |
| `max_docs_allowed` | int | Server max batch size |
| `results` | `OCRBatchItem[]` | Per-file results |

Each `OCRBatchItem` contains:

- `filename`
- `file_hash` (sha256)
- `response` (OCRResponse) or `error`

## Stability guarantees (V0)

- Existing endpoints remain unchanged
- New endpoints added:
  - `GET /version`
  - `GET /capabilities`
- New server-side limits are enforced:
  - `MAX_DOCS_PER_BATCH` (default 20)
  - `MAX_FILE_SIZE_MB` (default 20)
