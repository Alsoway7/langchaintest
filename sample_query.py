from pathlib import Path
import re

from rag import extract_text, should_ignore_file


SAMPLE_ID_PATTERN = r"r\d+[A-Za-z]?(?:-\d+[A-Za-z]?)+"
SUBJECT_LABELS = {
    "Honey": "ハチミツ",
    "Nest": "巣くず",
    "Propolis": "プロポリス",
}
SPECIES_LABELS = {
    "mellifera": "セイヨウミツバチ",
    "japonica": "ニホンミツバチ",
}


def detect_sample_ids(question: str) -> list[str]:
    matches = re.findall(SAMPLE_ID_PATTERN, question, flags=re.IGNORECASE)
    return list(dict.fromkeys(matches))


def should_use_sample_query(question: str) -> bool:
    if not detect_sample_ids(question):
        return False
    terms = [
        "試料",
        "採取地",
        "緯度",
        "経度",
        "ハチミツ",
        "はちみつ",
        "巣くず",
        "巣クズ",
        "プロポリス",
        "ニホンミツバチ",
        "セイヨウミツバチ",
        "どのような",
        "sample",
        "site",
        "coordinate",
        "honey",
        "nest",
        "propolis",
        "mellifera",
        "japonica",
    ]
    return any(term.lower() in question.lower() for term in terms)


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
                "subject_label": SUBJECT_LABELS.get(subject, subject),
                "species": species,
                "species_label": SPECIES_LABELS.get(species, species),
                "coordinates": coordinates,
                "region": region,
                "site": "".join(site_parts),
                "source": source,
            }
        )
        index = lookahead

    return records


def load_sample_records(data_dir: Path) -> list[dict]:
    records = []
    for path in sorted((data_dir / "01_knowledge_docs").rglob("*")):
        if should_ignore_file(path) or not path.is_file() or path.suffix.lower() not in {".docx", ".pdf"}:
            continue
        try:
            text = extract_text(path)
        except Exception:
            continue
        records.extend(parse_sample_records(text, str(path.relative_to(data_dir))))
    return records


def answer_sample_query(question: str, data_dir: Path) -> dict | None:
    if not should_use_sample_query(question):
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
    return {"question": question, "records": records}


def format_sample_answer(result: dict) -> str:
    lines = ["Sample information from thesis documents:"]
    for record in result["records"]:
        lines.append(f"\n[{record['sample_id']}]")
        lines.append(f"- 採取地名: {record['site']} ({record['region']})")
        lines.append(f"- 緯度経度: {record['coordinates']}")
        lines.append(f"- 試料種別: {record['subject_label']} ({record['subject']})")
        lines.append(f"- ミツバチ: {record['species_label']} ({record['species']})")
        lines.append(f"- Source: {record['source']}")
    return "\n".join(lines)
