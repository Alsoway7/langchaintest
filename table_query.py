from pathlib import Path
import re

from openpyxl import load_workbook


RESULT_FILE_NAME = "3_代表配列のリード数と相同性解析結果.xlsx"


# 从 BLAST Target 字段里解析物种名称，供表格查询和聚合使用。
def parse_species_name(target: object) -> str:
    if not target:
        return "Unknown"

    text = str(target)
    text = re.sub(r"^[A-Z]{1,3}_?\d+(?:\.\d+)?_", "", text)
    text = text.replace(",", " ").replace(";", " ")
    parts = text.split("_")

    for index in range(len(parts) - 1):
        genus = parts[index]
        species = parts[index + 1]
        if genus and species and genus[0].isupper() and species.islower():
            return f"{genus} {species}"

    return text[:100]


# 根据问题内容判断用户是在问 COI、gPlant，还是二者都问。
def detect_markers(question: str) -> list[str]:
    normalized = question.lower()
    markers = []
    if "coi" in normalized:
        markers.append("COI")
    if "gplant" in normalized or "rbc" in normalized or "rbcl" in normalized:
        markers.append("gPlant")
    return markers


# 从问题中提取所有 ASV 编号，例如 ASV_001、ASV_002。
def detect_asv_ids(question: str) -> list[str]:
    matches = re.findall(r"ASV[_\-\s]?(\d+)", question, flags=re.IGNORECASE)
    return list(dict.fromkeys(f"ASV_{int(match):03d}" for match in matches))


# 从问题中提取可能的拉丁物种名片段，例如 Procyon lotor。
def detect_species_name(question: str) -> str | None:
    match = re.search(r"\b([A-Z][a-z]+)\s+([a-z][a-z.\-]+)\b", question)
    if not match:
        return None
    return f"{match.group(1)} {match.group(2)}"


# 从问题中提取“上位 5 件 / top 10”这类数量限制。
def detect_limit(question: str, default: int = 10) -> int:
    patterns = [
        r"上位\s*(\d+)",
        r"top\s*(\d+)",
        r"前\s*(\d+)",
        r"(\d+)\s*件",
        r"(\d+)\s*个",
    ]
    for pattern in patterns:
        match = re.search(pattern, question, flags=re.IGNORECASE)
        if match:
            return max(1, min(int(match.group(1)), 50))
    return default


# 判断问题是否属于需要精确读表的查询。
def should_use_table_query(question: str) -> bool:
    normalized = question.lower()
    if not detect_markers(question):
        return False

    terms = [
        "asv",
        "read",
        "リード",
        "リード数",
        "identity",
        "相同性",
        "target",
        "blast",
        "生物種",
        "植物種",
        "検出",
        "上位",
        "前",
        "多い",
        "いくつ",
        "多少",
        "几个",
        "哪些",
        "读数",
        "物种",
    ]
    return any(term in normalized for term in terms)


# 读取指定 marker 的结果 Excel，并转换为结构化记录。
def load_result_rows(data_dir: Path, marker: str) -> list[dict]:
    path = data_dir / "02_tables" / marker / RESULT_FILE_NAME
    if not path.exists():
        return []

    workbook = load_workbook(path, read_only=True, data_only=True)
    sheet = workbook.active
    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        return []

    header = list(rows[0])
    target_index = header.index("Target")
    identity_index = header.index("Identity")
    sample_columns = [
        (index, str(value))
        for index, value in enumerate(header[:target_index])
        if index > 0 and value
    ]

    records = []
    for row in rows[1:]:
        if not row or not row[0]:
            continue

        sample_reads = {}
        total_reads = 0
        for index, sample_name in sample_columns:
            value = row[index] if index < len(row) else 0
            try:
                read_count = int(value or 0)
            except (TypeError, ValueError):
                read_count = 0
            sample_reads[sample_name] = read_count
            total_reads += read_count

        target = row[target_index] if target_index < len(row) else ""
        identity = row[identity_index] if identity_index < len(row) else ""
        records.append(
            {
                "marker": marker,
                "asv_id": str(row[0]),
                "sample_reads": sample_reads,
                "total_reads": total_reads,
                "target": target,
                "species": parse_species_name(target),
                "identity": identity,
                "source": str(path.relative_to(data_dir)),
            }
        )

    return records


# 按物种聚合 reads，返回 read 数最多的物种。
def get_top_species(data_dir: Path, marker: str, limit: int = 10) -> list[dict]:
    totals = {}
    examples = {}
    for row in load_result_rows(data_dir, marker):
        species = row["species"]
        totals[species] = totals.get(species, 0) + row["total_reads"]
        examples.setdefault(species, row)

    return [
        {
            "marker": marker,
            "species": species,
            "total_reads": total_reads,
            "example_asv": examples[species]["asv_id"],
            "source": examples[species]["source"],
        }
        for species, total_reads in sorted(totals.items(), key=lambda item: item[1], reverse=True)[:limit]
    ]


# 返回 read 数最多的 ASV 记录。
def get_top_asvs(data_dir: Path, marker: str, limit: int = 10) -> list[dict]:
    rows = load_result_rows(data_dir, marker)
    return sorted(rows, key=lambda row: row["total_reads"], reverse=True)[:limit]


# 精确查询某个 ASV 的 target、identity、总 reads 和样本 reads。
def get_asv_detail(data_dir: Path, marker: str, asv_id: str) -> dict | None:
    for row in load_result_rows(data_dir, marker):
        if row["asv_id"].upper() == asv_id.upper():
            return row
    return None


# 根据物种名片段查找对应 ASV。
def find_species(data_dir: Path, marker: str, species_name: str) -> list[dict]:
    normalized = species_name.lower()
    rows = load_result_rows(data_dir, marker)
    return [
        row for row in rows
        if normalized in row["species"].lower() or normalized in str(row["target"]).lower()
    ]


# 根据问题决定执行哪一种表格查询，并生成结构化结果。
def answer_table_query(question: str, data_dir: Path) -> dict | None:
    if not should_use_table_query(question):
        return None

    markers = detect_markers(question)
    asv_ids = detect_asv_ids(question)
    species_name = detect_species_name(question)
    limit = detect_limit(question)
    normalized = question.lower()
    results = []

    for marker in markers:
        if asv_ids:
            details = [
                detail for asv_id in asv_ids
                if (detail := get_asv_detail(data_dir, marker, asv_id))
            ]
            if details:
                results.append({"type": "asv_details", "marker": marker, "data": details})
            continue

        if species_name:
            matches = find_species(data_dir, marker, species_name)
            if matches:
                results.append(
                    {
                        "type": "species_matches",
                        "marker": marker,
                        "species_name": species_name,
                        "data": sorted(matches, key=lambda row: row["total_reads"], reverse=True)[:limit],
                    }
                )
            continue

        if "asv" in normalized and ("上位" in normalized or "多い" in normalized):
            results.append({"type": "top_asvs", "marker": marker, "data": get_top_asvs(data_dir, marker, limit)})
            continue

        results.append({"type": "top_species", "marker": marker, "data": get_top_species(data_dir, marker, limit)})

    if not results:
        return None

    return {
        "question": question,
        "results": results,
    }


# 根据问题文字判断输出语言：日语、中文或英语。
def detect_output_language(question: str) -> str:
    if re.search(r"[\u3040-\u30ff]", question):
        return "ja"
    if re.search(r"[\u4e00-\u9fff]", question):
        return "zh"
    return "en"


# 根据输出语言准备字段标签。
def get_output_labels(language: str) -> dict:
    if language == "ja":
        return {
            "details": "の詳細",
            "estimated_species": "推定生物種",
            "sample_reads": "サンプル別 reads",
            "source": "出典",
            "top_asvs": "total reads が多い ASV",
            "top_species": "total reads が多い生物種",
            "assigned_asvs_prefix": "",
            "assigned_asvs_suffix": "と判定された ASV",
        }
    if language == "zh":
        return {
            "details": "详情",
            "estimated_species": "推定物种",
            "sample_reads": "各样本 reads",
            "source": "来源",
            "top_asvs": "total reads 最高的 ASV",
            "top_species": "total reads 最高的物种",
            "assigned_asvs_prefix": "判定为",
            "assigned_asvs_suffix": "的 ASV",
        }
    return {
        "details": "details",
        "estimated_species": "Estimated species",
        "sample_reads": "Sample reads",
        "source": "Source",
        "top_asvs": "Top ASVs by total reads",
        "top_species": "Top species by total reads",
        "assigned_asvs_prefix": "ASVs assigned to",
        "assigned_asvs_suffix": "",
    }


# 将结构化表格查询结果格式化为可直接展示的文本答案。
def format_table_answer(table_result: dict) -> str:
    lines = ["Structured table query result:"]
    question = table_result.get("question", "")
    language = detect_output_language(question)
    labels = get_output_labels(language)

    for result in table_result["results"]:
        result_type = result["type"]

        if result_type == "asv_details":
            for row in result["data"]:
                if language == "ja":
                    lines.append(f"\n[{row['marker']}] {row['asv_id']} {labels['details']}")
                elif language == "zh":
                    lines.append(f"\n[{row['marker']}] {row['asv_id']} {labels['details']}")
                else:
                    lines.append(f"\n[{row['marker']}] {row['asv_id']} {labels['details']}")
                lines.append(f"- {labels['estimated_species']}: {row['species']}")
                lines.append(f"- BLAST target: {row['target']}")
                lines.append(f"- Identity: {row['identity']}")
                lines.append(f"- Total reads: {row['total_reads']}")
                nonzero = {
                    sample: reads
                    for sample, reads in row["sample_reads"].items()
                    if reads
                }
                if nonzero:
                    lines.append(f"- {labels['sample_reads']}:")
                    for sample, reads in sorted(nonzero.items(), key=lambda item: item[1], reverse=True):
                        lines.append(f"  - {sample}: {reads}")
                lines.append(f"- {labels['source']}: {row['source']}")

        if result_type == "asv_detail":
            row = result["data"]
            if language == "ja":
                lines.append(f"\n[{row['marker']}] {row['asv_id']} {labels['details']}")
            elif language == "zh":
                lines.append(f"\n[{row['marker']}] {row['asv_id']} {labels['details']}")
            else:
                lines.append(f"\n[{row['marker']}] {row['asv_id']} {labels['details']}")
            lines.append(f"- {labels['estimated_species']}: {row['species']}")
            lines.append(f"- BLAST target: {row['target']}")
            lines.append(f"- Identity: {row['identity']}")
            lines.append(f"- Total reads: {row['total_reads']}")
            nonzero = {
                sample: reads
                for sample, reads in row["sample_reads"].items()
                if reads
            }
            if nonzero:
                lines.append(f"- {labels['sample_reads']}:")
                for sample, reads in sorted(nonzero.items(), key=lambda item: item[1], reverse=True):
                    lines.append(f"  - {sample}: {reads}")
            lines.append(f"- {labels['source']}: {row['source']}")

        if result_type == "top_asvs":
            lines.append(f"\n[{result['marker']}] {labels['top_asvs']}")
            for row in result["data"]:
                lines.append(
                    f"- {row['asv_id']}: {row['species']}; "
                    f"total_reads={row['total_reads']}; identity={row['identity']}"
                )

        if result_type == "top_species":
            lines.append(f"\n[{result['marker']}] {labels['top_species']}")
            for row in result["data"]:
                lines.append(
                    f"- {row['species']}: total_reads={row['total_reads']}; "
                    f"example_asv={row['example_asv']}"
                )

        if result_type == "species_matches":
            if language == "ja":
                lines.append(f"\n[{result['marker']}] {result['species_name']} {labels['assigned_asvs_suffix']}")
            elif language == "zh":
                lines.append(
                    f"\n[{result['marker']}] {labels['assigned_asvs_prefix']} "
                    f"{result['species_name']} {labels['assigned_asvs_suffix']}"
                )
            else:
                lines.append(f"\n[{result['marker']}] {labels['assigned_asvs_prefix']} {result['species_name']}")
            for row in result["data"]:
                lines.append(
                    f"- {row['asv_id']}: total_reads={row['total_reads']}; "
                    f"identity={row['identity']}; target={row['target']}"
                )
                nonzero = {
                    sample: reads
                    for sample, reads in row["sample_reads"].items()
                    if reads
                }
                if nonzero:
                    sample_text = ", ".join(
                        f"{sample}={reads}"
                        for sample, reads in sorted(nonzero.items(), key=lambda item: item[1], reverse=True)[:8]
                    )
                    lines.append(f"  sample_reads: {sample_text}")

    return "\n".join(lines)
