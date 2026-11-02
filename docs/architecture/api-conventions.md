# API Conventions

**Status:** Conventions apply from Phase 1. The endpoints implemented so far are listed in §8; domain endpoints follow in Phase 3.

## 1. Base path and versioning

- All endpoints live under `/api/v1`. A breaking change gets `/api/v2`; additive changes do not.
- OpenAPI document: `GET /api/openapi.json`; interactive docs: `GET /api/docs`.

## 2. Resources and naming

- JSON only, UTF-8. Field names in `snake_case`.
- Plural nouns for collections (`/plants`, `/drugs`, `/interactions`), identifiers in the path (`/plants/{wfo_id}`).
- **External identifiers are preferred in URLs** where they are stable: `wfo_id` for plants, RxCUI for drugs, PMID for articles. Internal UUIDs are used for HerbaGuard-specific records.
- Read operations use `GET`. Operations that compute results from a submitted body (e.g. checking a medication list, asking the assistant) use `POST`, so medication names are not placed in URLs (which end up in browser history and proxy logs).

## 3. Pagination, filtering, sorting

List endpoints accept `limit` (1–100, default 20) and `offset` (≥ 0) and return:

```json
{ "items": [ ... ], "total": 137, "limit": 20, "offset": 0 }
```

Filters are explicit query parameters (`?evidence_type=RCT&year_from=2015`). Sorting uses `sort=field` or `sort=-field`.

## 4. Error envelope

Every error response — validation, not found, domain errors, unexpected failures — has this shape:

```json
{
  "error": {
    "code": "ambiguous_entity",
    "message": "Several taxa match 'ginseng'.",
    "details": { "candidates": ["wfo-0000263606", "wfo-0000948117"] },
    "request_id": "5f0c2d6e8f3a4b0c9a1d2e3f4a5b6c7d"
  }
}
```

| HTTP | `code` | When |
|---|---|---|
| 400 | `bad_request` | Malformed request |
| 404 | `not_found` | Unknown resource or route |
| 409 | `ambiguous_entity` | A name matches several entities; `details.candidates` lists them so the client can ask the user |
| 409 | `conflict` | State conflict |
| 422 | `validation_error` | Invalid parameters; `details` is a list of `{location, message, type}` |
| 502 | `upstream_unavailable` | An external source failed during a live lookup |
| 503 | `service_unavailable` | A dependency (e.g. the database) is down |
| 500 | `internal_error` | Unexpected error; the message is generic and details go only to the logs |

`code` values are stable and machine-readable; `message` is for humans and may change.

## 5. Request IDs

Clients may send `X-Request-ID` (`[A-Za-z0-9._-]{1,64}`); otherwise the server generates one. It is returned in the response header and in error bodies, and attached to every log line for that request.

## 6. Scientific response conventions (Phase 3 onward)

These are binding for every endpoint that returns scientific content:

1. **Provenance object.** Every finding includes a `provenance` array:
   ```json
   {
     "source_code": "ema_hmpc",
     "source_name": "EMA HMPC — EU herbal monograph",
     "document_id": "EMA/HMPC/7695/2021",
     "location": "section 4.5, well-established use",
     "url": "https://www.ema.europa.eu/...",
     "retrieved_at": "2026-11-03T09:12:00Z",
     "licence_status": "to_verify"
   }
   ```
2. **Evidence class, not verdicts.** Interaction results carry `interaction_class` (`A`–`E`), the label text, and the list of contributing assertions. There is no `safe: true` field and no computed severity.
3. **Explicit coverage for "no evidence".** Class D responses list `sources_searched` with their versions or retrieval dates.
4. **Use category always present** on indications and assertions from EMA (`well_established_use` / `traditional_use`).
5. **Disclaimer.** `GET /api/v1/meta` returns the canonical disclaimer; clients must display it. AI-generated text is returned in a separate field from source quotations.

## 7. Caching and limits

- `GET` responses for reference data may set `Cache-Control: max-age` (from Phase 3).
- Rate limiting is not implemented in the MVP (local deployment); it is a production item.

## 8. Implemented endpoints (Phase 1)

| Method | Path | Response | Notes |
|---|---|---|---|
| GET | `/api/v1/health` | `{"status": "ok"}` | Liveness; no dependencies checked |
| GET | `/api/v1/health/ready` | `{"status": "ok"\|"degraded", "checks": [...]}` | 200 if the database answers, 503 otherwise |
| GET | `/api/v1/meta` | name, version, environment, api_version, disclaimer | Source of the disclaimer text |
