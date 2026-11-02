"""Ingestion run context: fetch + snapshot + ``source_record``, provenance, issues, statistics.

Every pipeline runs inside ``run_ingestion(...)``. The context guarantees that

* every external response is saved raw and registered as a ``source_record`` before parsing;
* derived rows get ``provenance`` links to the record(s) they came from;
* problems become ``data_quality_issue`` rows;
* the ``ingestion_run`` ends as succeeded, partial (issues of severity error) or failed.
"""

from __future__ import annotations

import json
import uuid
from collections import Counter
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from herbaguard import __version__
from herbaguard.core.config import Settings
from herbaguard.core.logging import get_logger
from herbaguard.domain.enums import IssueSeverity, RunStatus
from herbaguard.ingestion.http import HttpClient, HttpResult, RetryableStatusError
from herbaguard.ingestion.raw_store import RawStore, extension_for
from herbaguard.models import DataQualityIssue, IngestionRun, Provenance, SourceRecord

logger = get_logger("herbaguard.ingestion")

MAX_INLINE_PAYLOAD_BYTES = 64_000
STABLE_NAMESPACE = uuid.UUID("6f1c5d0e-3b0a-4b5e-9f7a-2a1d8c0e4b11")  # HerbaGuard deterministic IDs


def stable_id(*parts: object) -> uuid.UUID:
    """Deterministic UUID for derived rows, so re-running ingestion upserts instead of duplicating."""
    return uuid.uuid5(STABLE_NAMESPACE, "|".join(str(p) for p in parts))


@dataclass(frozen=True, slots=True)
class Fetched:
    record: SourceRecord
    result: HttpResult

    @property
    def content(self) -> bytes:
        return self.result.content

    @property
    def ok(self) -> bool:
        return 200 <= self.result.status_code < 300

    def json(self) -> Any:
        return self.result.json()


class IngestionContext:
    def __init__(
        self,
        session: Session,
        run: IngestionRun,
        http: HttpClient,
        raw_store: RawStore,
    ) -> None:
        self.session = session
        self.run = run
        self.http = http
        self.raw_store = raw_store
        self.stats: Counter[str] = Counter()
        self.error_issues = 0

    @property
    def source_code(self) -> str:
        return self.run.source_code

    # ------------------------------------------------------------------ fetching

    def fetch(
        self,
        url: str,
        *,
        native_id: str,
        params: dict[str, Any] | None = None,
        source_version: str | None = None,
        method: str = "GET",
        data: dict[str, Any] | None = None,
        source_code: str | None = None,
    ) -> Fetched:
        """GET (or POST) a URL, snapshot the raw response and register a ``source_record``.

        Any HTTP status is recorded (a 404 "no results" is evidence that a source was searched).
        Network failures after retries propagate to the caller.
        """
        source = source_code or self.source_code
        result = self.http.request(method, url, params=params, data=data)
        ext = extension_for(result.content_type, url)
        digest, path = self.raw_store.save(source, result.content, ext)
        payload: dict[str, Any] | None = None
        if ext == ".json" and len(result.content) <= MAX_INLINE_PAYLOAD_BYTES:
            try:
                loaded = json.loads(result.content)
                payload = loaded if isinstance(loaded, dict) else {"data": loaded}
            except ValueError:
                payload = None

        record = self.session.scalar(
            select(SourceRecord).where(
                SourceRecord.source_code == source,
                SourceRecord.native_id == native_id[:512],
                SourceRecord.content_sha256 == digest,
            )
        )
        if record is None:
            record = SourceRecord(
                id=uuid.uuid4(),
                source_code=source,
                ingestion_run_id=self.run.id,
                native_id=native_id[:512],
                url=result.url,
                request_parameters={"method": method, **({"data": data} if data else {})},
                http_status=result.status_code,
                content_type=result.content_type,
                content_sha256=digest,
                raw_path=str(path),
                payload=payload,
                source_version=source_version,
                retrieved_at=datetime.now(UTC),
            )
            self.session.add(record)
            self.session.flush()
            self.stats["records_new"] += 1
        else:
            self.stats["records_unchanged"] += 1
        self.stats[f"http_{result.status_code}"] += 1
        return Fetched(record=record, result=result)

    def register_local_file(self, path: Path, *, source_code: str, native_id: str) -> SourceRecord:
        """Register a committed local file (e.g. data/curated/herbs.yaml) as a source record,
        so curated values have the same lineage as fetched ones."""
        content = path.read_bytes()
        digest, stored = self.raw_store.save(source_code, content, path.suffix or ".bin")
        record = self.session.scalar(
            select(SourceRecord).where(
                SourceRecord.source_code == source_code,
                SourceRecord.native_id == native_id,
                SourceRecord.content_sha256 == digest,
            )
        )
        if record is None:
            record = SourceRecord(
                id=uuid.uuid4(),
                source_code=source_code,
                ingestion_run_id=self.run.id,
                native_id=native_id,
                url=f"file://{native_id}",
                request_parameters={},
                http_status=None,
                content_type="text/yaml",
                content_sha256=digest,
                raw_path=str(stored),
                payload=None,
                retrieved_at=datetime.now(UTC),
            )
            self.session.add(record)
            self.session.flush()
        return record

    @contextmanager
    def per_item(self, item: str, on_rollback: Callable[[], None] | None = None) -> Iterator[None]:
        """Isolate one unit of work (e.g. one herb). Network failures after retries roll back
        that unit, are recorded as an error-level issue, and the run continues (status
        ``partial``). Other exceptions propagate: programming errors must fail loudly."""
        try:
            yield
            self.session.commit()
        except (httpx.HTTPError, RetryableStatusError) as exc:
            self.session.rollback()
            if on_rollback:
                on_rollback()
            self.issue(
                "item_failed",
                f"{item}: {type(exc).__name__}: {str(exc)[:300]}",
                severity=IssueSeverity.ERROR,
                item=item,
            )
            self.session.commit()

    # ------------------------------------------------------------------ provenance & issues

    def provenance(
        self,
        entity_table: str,
        entity_id: object,
        record: SourceRecord,
        method: str,
        *,
        version: str | None = None,
        location: str | None = None,
        excerpt: str | None = None,
    ) -> None:
        stmt = (
            insert(Provenance)
            .values(
                id=uuid.uuid4(),
                entity_table=entity_table,
                entity_id=str(entity_id),
                source_record_id=record.id,
                ingestion_run_id=self.run.id,
                extraction_method=method,
                extraction_version=version,
                location=location,
                verbatim_excerpt=excerpt,
            )
            .on_conflict_do_update(
                constraint="uq_provenance_entity_table",
                set_={
                    "ingestion_run_id": self.run.id,
                    "extraction_version": version,
                    "location": location,
                    "verbatim_excerpt": excerpt,
                },
            )
        )
        self.session.execute(stmt)
        self.stats["provenance_links"] += 1

    def issue(
        self,
        rule: str,
        message: str,
        *,
        severity: IssueSeverity = IssueSeverity.WARNING,
        record: SourceRecord | None = None,
        **context: Any,
    ) -> None:
        self.session.add(
            DataQualityIssue(
                ingestion_run_id=self.run.id,
                source_record_id=record.id if record else None,
                rule=rule,
                severity=severity.value,
                message=message,
                context={k: v for k, v in context.items() if v is not None},
            )
        )
        self.stats[f"issue_{severity.value}"] += 1
        if severity is IssueSeverity.ERROR:
            self.error_issues += 1
        logger.info("data_quality_issue", rule=rule, severity=severity.value, message=message[:200])


@contextmanager
def run_ingestion(
    session: Session,
    source_code: str,
    settings: Settings,
    *,
    parameters: dict[str, Any] | None = None,
    http: HttpClient | None = None,
) -> Iterator[IngestionContext]:
    """Open an ``ingestion_run``; commit on success, record failure otherwise."""
    run = IngestionRun(
        id=uuid.uuid4(),
        source_code=source_code,
        status=RunStatus.RUNNING.value,
        parameters=parameters or {},
        statistics={},
        code_version=__version__,
    )
    session.add(run)
    session.commit()
    own_http = http is None
    client = http or HttpClient(settings)
    ctx = IngestionContext(session, run, client, RawStore(Path(settings.raw_data_dir)))
    logger.info("ingestion_started", source=source_code, run_id=str(run.id))
    try:
        yield ctx
    except Exception as exc:
        session.rollback()
        failed = session.get(IngestionRun, run.id)
        if failed is not None:
            failed.status = RunStatus.FAILED.value
            failed.finished_at = datetime.now(UTC)
            failed.error_message = f"{type(exc).__name__}: {exc}"[:2000]
            failed.statistics = dict(ctx.stats)
            session.commit()
        logger.exception("ingestion_failed", source=source_code, run_id=str(run.id))
        raise
    else:
        run.status = (RunStatus.PARTIAL if ctx.error_issues else RunStatus.SUCCEEDED).value
        run.finished_at = datetime.now(UTC)
        run.statistics = dict(ctx.stats)
        session.commit()
        logger.info("ingestion_finished", source=source_code, status=run.status, **dict(ctx.stats))
    finally:
        if own_http:
            client.close()
