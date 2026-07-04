from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from privatetv.db.media_repository import MediaRepository
from privatetv.domain.models import MediaAsset, MediaItem, ScanStatus, SourceKind

ScanItems = list[tuple[MediaItem, tuple[MediaAsset, ...]]]


@dataclass(frozen=True, slots=True)
class CatalogScanSummary:
    scanned_items: int
    imported_items: int
    failed_items: int
    missing_items: int


def store_scan_results(
    connection: sqlite3.Connection,
    scan_results: ScanItems,
    source_kinds_to_mark_missing: set[SourceKind],
) -> CatalogScanSummary:
    repository = MediaRepository(connection)
    seen_by_kind: dict[SourceKind, set[str]] = {kind: set() for kind in source_kinds_to_mark_missing}
    imported_items = 0
    failed_items = 0
    for item, assets in scan_results:
        repository.upsert_media_item(item, assets)
        if item.source_kind in seen_by_kind:
            seen_by_kind[item.source_kind].add(item.source_uri)
        if item.scan_status == ScanStatus.OK:
            imported_items += 1
        else:
            failed_items += 1

    missing_items = 0
    for source_kind, seen_source_uris in seen_by_kind.items():
        missing_items += repository.mark_missing_except(source_kind, seen_source_uris)

    connection.commit()
    return CatalogScanSummary(
        scanned_items=len(scan_results),
        imported_items=imported_items,
        failed_items=failed_items,
        missing_items=missing_items,
    )


def store_local_scan_results(
    connection: sqlite3.Connection,
    scan_results: ScanItems,
) -> CatalogScanSummary:
    return store_scan_results(connection, scan_results, {SourceKind.LOCAL_FILE})
