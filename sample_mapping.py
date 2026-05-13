from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import csv
import re

from data_access import find_sequence_fasta_files, logical_stem
from sample_query import load_sample_records


THESIS_SAMPLE_ID_PATTERN = re.compile(r"^r\d+[A-Za-z]?(?:-\d+[A-Za-z]?)+$", re.IGNORECASE)
SEQUENCE_SAMPLE_NAME_PATTERN = re.compile(r"^\d{6}[A-Za-z](?:-\d+)?$", re.IGNORECASE)
THESIS_TOKEN_PATTERN = re.compile(r"^r\d+[A-Za-z]?-(.+)$", re.IGNORECASE)
MAPPING_FILE_PATH = Path("data") / "sample_id_mapping.csv"


@dataclass(frozen=True)
class SampleResolution:
    requested_id: str
    resolved_sample_name: str | None
    status: str
    reason: str
    thesis_record: dict | None = None
    thesis_token: str | None = None
    evidence: tuple[str, ...] = ()


def _extract_thesis_token(sample_id: str) -> str | None:
    match = THESIS_TOKEN_PATTERN.match(sample_id)
    return match.group(1) if match else None


def _load_sequence_sample_names(data_dir: Path) -> list[str]:
    names = []
    for path in find_sequence_fasta_files(data_dir):
        if logical_stem(path).lower() == "repset":
            continue
        names.append(logical_stem(path))
    return names


def _find_thesis_record(data_dir: Path, sample_id: str) -> dict | None:
    wanted = sample_id.lower()
    for record in load_sample_records(data_dir):
        if record["sample_id"].lower() == wanted:
            return record
    return None


def _load_mapping_file(data_dir: Path) -> dict[str, str]:
    path = data_dir / MAPPING_FILE_PATH.relative_to("data")
    if not path.exists():
        return {}

    mappings = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            thesis_id = (row.get("thesis_sample_id") or row.get("sample_id") or "").strip()
            sequence_name = (row.get("sequence_sample_name") or row.get("sequence_id") or "").strip()
            if thesis_id and sequence_name:
                mappings[thesis_id.lower()] = sequence_name
    return mappings


def resolve_sample_identifier(data_dir: Path, sample_id: str) -> SampleResolution:
    available_names = _load_sequence_sample_names(data_dir)
    available_lookup = {name.lower(): name for name in available_names}

    direct = available_lookup.get(sample_id.lower())
    if direct:
        return SampleResolution(
            requested_id=sample_id,
            resolved_sample_name=direct,
            status="direct",
            reason="exact_sequence_sample_name",
            evidence=("exact_sequence_sample_name",),
        )

    thesis_token = _extract_thesis_token(sample_id)
    if thesis_token:
        token_direct = available_lookup.get(thesis_token.lower())
        if token_direct:
            return SampleResolution(
                requested_id=sample_id,
                resolved_sample_name=token_direct,
                status="mapped",
                reason="thesis_token_matches_sequence_sample_name",
                thesis_record=_find_thesis_record(data_dir, sample_id),
                thesis_token=thesis_token,
                evidence=(f"thesis_token={thesis_token}", "exact_token_match"),
            )

    mapping_file = _load_mapping_file(data_dir)
    mapped_name = mapping_file.get(sample_id.lower())
    if mapped_name:
        resolved = available_lookup.get(mapped_name.lower(), mapped_name)
        return SampleResolution(
            requested_id=sample_id,
            resolved_sample_name=resolved,
            status="mapped",
            reason="mapping_file",
            thesis_record=_find_thesis_record(data_dir, sample_id),
            thesis_token=thesis_token,
            evidence=(str(MAPPING_FILE_PATH),),
        )

    thesis_record = _find_thesis_record(data_dir, sample_id) if THESIS_SAMPLE_ID_PATTERN.match(sample_id) else None
    if thesis_record:
        evidence = []
        if thesis_token:
            evidence.append(f"thesis_token={thesis_token}")
            if thesis_token.lower() not in available_lookup:
                evidence.append("token_not_present_in_sequence_samples")
        if mapping_file:
            evidence.append("mapping_file_loaded_but_no_entry")
        else:
            evidence.append("no_mapping_file")
        return SampleResolution(
            requested_id=sample_id,
            resolved_sample_name=None,
            status="mapping_missing",
            reason="thesis_sample_exists_but_no_explicit_sequence_mapping",
            thesis_record=thesis_record,
            thesis_token=thesis_token,
            evidence=tuple(evidence),
        )

    return SampleResolution(
        requested_id=sample_id,
        resolved_sample_name=None,
        status="missing",
        reason="unknown_sample_identifier",
    )


def summarize_thesis_record(record: dict | None) -> str:
    if not record:
        return ""
    parts = []
    if record.get("site"):
        parts.append(f"site={record['site']}")
    if record.get("coordinates"):
        parts.append(f"coordinates={record['coordinates']}")
    if record.get("subject"):
        parts.append(f"material={record['subject']}")
    if record.get("species"):
        parts.append(f"bee={record['species']}")
    return ", ".join(parts)
