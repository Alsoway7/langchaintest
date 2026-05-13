from __future__ import annotations

from pathlib import Path


CATEGORY_PREFIXES = {
    "knowledge": "01_knowledge_docs__",
    "tables": "02_tables__",
    "reports": "03_reports__",
    "sequences": "04_sequences_fasta__",
    "raw_reads": "05_raw_reads_fastq__",
    "qiime2": "06_qiime2_artifacts__",
    "images": "07_images__",
}


def iter_data_files(data_dir: Path):
    for path in sorted(data_dir.rglob("*")):
        if path.is_file():
            yield path


def logical_name(path: Path) -> str:
    return path.name.split("__")[-1]


def logical_stem(path: Path) -> str:
    return path.stem.split("__")[-1]


def infer_marker_from_path(path: Path) -> str:
    text = str(path).replace("/", "\\").lower()
    if "\\coi\\" in text or "__coi__" in text or text.endswith("\\coi") or "coi__" in path.name.lower():
        return "COI"
    if "\\gplant\\" in text or "__gplant__" in text or text.endswith("\\gplant") or "rbcl" in text:
        return "gPlant"
    return "general"


def infer_category_from_path(path: Path) -> str:
    text = str(path).replace("/", "\\")
    name = path.name
    if "\\01_knowledge_docs\\" in text or name.startswith(CATEGORY_PREFIXES["knowledge"]):
        return "knowledge"
    if "\\02_tables\\" in text or name.startswith(CATEGORY_PREFIXES["tables"]):
        return "tables"
    if "\\03_reports\\" in text or name.startswith(CATEGORY_PREFIXES["reports"]):
        return "reports"
    if "\\04_sequences_fasta\\" in text or name.startswith(CATEGORY_PREFIXES["sequences"]):
        return "sequences"
    if "\\05_raw_reads_fastq\\" in text or name.startswith(CATEGORY_PREFIXES["raw_reads"]):
        return "raw_reads"
    if "\\06_qiime2_artifacts\\" in text or name.startswith(CATEGORY_PREFIXES["qiime2"]):
        return "qiime2"
    if "\\07_images\\" in text or name.startswith(CATEGORY_PREFIXES["images"]):
        return "images"
    return "other"


def find_files(
    data_dir: Path,
    *,
    suffixes: set[str] | None = None,
    marker: str | None = None,
    category: str | None = None,
    name_contains: list[str] | None = None,
):
    for path in iter_data_files(data_dir):
        if suffixes and path.suffix.lower() not in suffixes:
            continue
        if marker and infer_marker_from_path(path) != marker:
            continue
        if category and infer_category_from_path(path) != category:
            continue
        if name_contains:
            lowered = path.name.lower()
            if not all(fragment.lower() in lowered for fragment in name_contains):
                continue
        yield path


def find_marker_table_file(data_dir: Path, marker: str, table_code: str) -> Path | None:
    candidates = list(
        find_files(
            data_dir,
            suffixes={".xlsx"},
            marker=marker,
            category="tables",
            name_contains=[f"{table_code}_"],
        )
    )
    return candidates[0] if candidates else None


def find_sequence_fasta_files(data_dir: Path):
    for path in find_files(data_dir, suffixes={".fasta", ".fa"}, category="sequences"):
        yield path
