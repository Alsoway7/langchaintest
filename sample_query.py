from pathlib import Path
import re

from data_access import find_files
from query_intent import infer_sample_metadata_intent
from rag import extract_text, should_ignore_file
from task_understanding import understand_sample_request


SAMPLE_ID_PATTERN = r"r\d+[A-Za-z]?(?:-\d+[A-Za-z]?)+"
SUBJECT_LABELS = {
    "Honey": {"ja": "ハチミツ", "zh": "蜂蜜", "en": "Honey"},
    "Nest": {"ja": "巣くず", "zh": "巢屑", "en": "Nest"},
    "Propolis": {"ja": "プロポリス", "zh": "蜂胶", "en": "Propolis"},
}
SPECIES_LABELS = {
    "mellifera": {"ja": "セイヨウミツバチ", "zh": "西洋蜜蜂", "en": "mellifera"},
    "japonica": {"ja": "ニホンミツバチ", "zh": "日本蜜蜂", "en": "japonica"},
}
SAMPLE_METADATA_HINTS = [
    "site",
    "location",
    "coordinate",
    "region",
    "where",
    "sample info",
    "metadata",
    "sample",
    "試料",
    "採取",
    "採取地",
    "採取地名",
    "緯度経度",
    "座標",
    "ハチミツ",
    "巣くず",
    "プロポリス",
    "ニホンミツバチ",
    "セイヨウミツバチ",
    "采样",
    "地点",
    "经纬度",
    "样本",
    "蜂蜜",
    "蜂胶",
]


def detect_sample_ids(question: str) -> list[str]:
    matches = re.findall(SAMPLE_ID_PATTERN, question, flags=re.IGNORECASE)
    return list(dict.fromkeys(matches))


def should_use_sample_query(question: str, chat_model=None) -> bool:
    sample_ids = detect_sample_ids(question)
    if not sample_ids:
        return False

    normalized = question.lower()
    if any(term in normalized for term in SAMPLE_METADATA_HINTS):
        return True

    intent = infer_sample_metadata_intent(question, sample_ids, chat_model)
    if not intent:
        return False
    return bool(intent.get("should_use_sample_query"))


def parse_sample_records(text: str, source: str) -> list[dict]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    records = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not re.match(rf"^{SAMPLE_ID_PATTERN}\t", line, flags=re.IGNORECASE):
            index += 1
            continue

        parts = [part.strip() for part in line.split("\t")]
        if len(parts) < 6:
            index += 1
            continue

        sample_id, subject, species, coordinates, region = parts[:5]
        site_parts = parts[5:]
        lookahead = index + 1
        while lookahead < len(lines):
            next_line = lines[lookahead]
            if re.match(rf"^{SAMPLE_ID_PATTERN}\t", next_line, flags=re.IGNORECASE):
                break
            if "\t" in next_line or next_line.startswith("Sample ID"):
                break
            site_parts.append(next_line)
            lookahead += 1

        records.append(
            {
                "sample_id": sample_id,
                "subject": subject,
                "species": species,
                "coordinates": coordinates,
                "region": region,
                "site": "".join(site_parts),
                "source": source,
            }
        )
        index = lookahead

    return records


def _is_valid_record(record: dict) -> bool:
    coords = record.get("coordinates", "")
    if not coords or coords == "-":
        return True
    # Valid: "36.331, 138.973" or "-"
    return bool(re.match(r"^-?\d+\.\d+,\s*-?\d+\.\d+$", coords.strip()))


def load_sample_records(data_dir: Path) -> list[dict]:
    records = []
    seen: set[str] = set()
    for path in find_files(data_dir, suffixes={".docx", ".pdf"}, category="knowledge"):
        if should_ignore_file(path):
            continue
        try:
            text = extract_text(path)
        except Exception:
            continue
        for record in parse_sample_records(text, str(path.relative_to(data_dir))):
            key = record["sample_id"].lower()
            if key in seen:
                continue
            if not _is_valid_record(record):
                continue
            seen.add(key)
            records.append(record)
    return records


def answer_sample_query(question: str, data_dir: Path, chat_model=None) -> dict | None:
    if not should_use_sample_query(question, chat_model=chat_model):
        return None

    wanted = {sample_id.lower() for sample_id in detect_sample_ids(question)}
    records = []
    seen = set()
    for record in load_sample_records(data_dir):
        key = record["sample_id"].lower()
        if key not in wanted or key in seen:
            continue
        seen.add(key)
        records.append(record)

    if not records:
        return None
    return {
        "question": question,
        "records": records,
        "response_requirements": understand_sample_request(question, chat_model=chat_model),
    }


# ---------------------------------------------------------------------------
# Gather pattern: collect any sample-metadata records the question references,
# without making a "should I answer?" decision based on keywords.
# ---------------------------------------------------------------------------


def gather_sample_data(question: str, data_dir: Path, chat_model=None) -> dict | None:
    sample_ids = detect_sample_ids(question)
    if not sample_ids:
        return None

    wanted = {sample_id.lower() for sample_id in sample_ids}
    records = []
    seen = set()
    for record in load_sample_records(data_dir):
        key = record["sample_id"].lower()
        if key not in wanted or key in seen:
            continue
        seen.add(key)
        records.append(record)

    if not records:
        return None
    return {"sample_ids": sample_ids, "records": records}


def format_sample_entries(gathered) -> list[dict]:
    if not gathered:
        return []
    entries = []
    for record in gathered["records"]:
        text = (
            f"sample_id: {record['sample_id']}\n"
            f"subject (material): {record['subject']}\n"
            f"bee species: {record['species']}\n"
            f"coordinates: {record['coordinates']}\n"
            f"region: {record['region']}\n"
            f"site: {record['site']}"
        )
        entries.append(
            {
                "kind": "sample_metadata",
                "source": record["source"],
                "text": text,
            }
        )
    return entries


def detect_output_language(question: str) -> str:
    if re.search(r"[\u3040-\u30ff]", question):
        return "ja"
    if re.search(r"[\u4e00-\u9fff]", question):
        return "zh"
    return "en"


def format_subject(subject: str, language: str) -> str:
    labels = SUBJECT_LABELS.get(subject)
    if not labels:
        return subject
    return labels.get(language, labels["en"])


def format_species(species: str, language: str) -> str:
    labels = SPECIES_LABELS.get(species)
    if not labels:
        return species
    return labels.get(language, labels["en"])


def _field_label(field: str, language: str) -> str:
    labels = {
        "site": {"ja": "採取地名", "zh": "采样地点", "en": "Site"},
        "coordinates": {"ja": "採取地の緯度経度", "zh": "采样地经纬度", "en": "Coordinates"},
        "subject": {"ja": "試料区分", "zh": "样本类型", "en": "Material"},
        "species": {"ja": "ミツバチ種", "zh": "蜜蜂种类", "en": "Bee species"},
    }
    return labels[field][language]


def _field_value(record: dict, field: str, language: str) -> str:
    if field == "site":
        return record["site"]
    if field == "coordinates":
        return record["coordinates"]
    if field == "subject":
        return format_subject(record["subject"], language)
    if field == "species":
        return format_species(record["species"], language)
    return ""


def format_sample_answer(result: dict) -> str:
    question = result.get("question", "")
    language = detect_output_language(question)
    requirements = result.get("response_requirements") or {}
    requested_fields = requirements.get("requested_fields") or ["site", "coordinates", "subject", "species"]
    output_mode = requirements.get("output_mode") or "prose"
    records = result["records"]

    if output_mode == "markdown_table":
        headers = ["試料番号" if language == "ja" else "样本编号" if language == "zh" else "Sample ID"]
        headers.extend(_field_label(field, language) for field in requested_fields)
        lines = [
            "| " + " | ".join(headers) + " |",
            "|" + "|".join("---" for _ in headers) + "|",
        ]
        for record in records:
            row = [record["sample_id"]]
            row.extend(_field_value(record, field, language) for field in requested_fields)
            lines.append("| " + " | ".join(row) + " |")
        return "\n".join(lines)

    if output_mode == "bullet_list":
        lines = []
        for record in records:
            lines.append(record["sample_id"])
            for field in requested_fields:
                lines.append(f"- {_field_label(field, language)}: {_field_value(record, field, language)}")
        return "\n".join(lines)

    if language == "ja":
        lines = []
        for record in records:
            lines.append(f"{record['sample_id']} は以下の試料です。")
            for field in requested_fields:
                lines.append(f"{_field_label(field, 'ja')}：{_field_value(record, field, 'ja')}")
        return "\n".join(lines)

    if language == "zh":
        lines = []
        for record in records:
            lines.append(f"{record['sample_id']} 的信息如下：")
            for field in requested_fields:
                lines.append(f"{_field_label(field, 'zh')}：{_field_value(record, field, 'zh')}")
        return "\n".join(lines)

    lines = []
    for record in records:
        lines.append(f"{record['sample_id']}:")
        for field in requested_fields:
            lines.append(f"- {_field_label(field, 'en')}: {_field_value(record, field, 'en')}")
    return "\n".join(lines)
