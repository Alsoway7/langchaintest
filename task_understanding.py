import json
import re


def _extract_json_object(text: str) -> dict | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
        return payload if isinstance(payload, dict) else None
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return None
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def understand_sequence_request(question: str, chat_model=None) -> dict:
    fallback = _understand_sequence_request_heuristic(question)
    if chat_model is None:
        return fallback

    prompt = (
        "You analyze a user's request about sample-linked FASTA / ASV / BLAST data. "
        "The user may ask in flexible prose, not fixed templates. "
        "Return JSON only with keys:\n"
        "- task_type: one of fasta_count, blast_top10_table, blast_top1_table, grouped_species_table, compare_species_sets, unknown\n"
        "- output_mode: one of prose, bullet_list, markdown_table\n"
        "- include_ratio_percent: boolean\n"
        "- top_n: integer or null\n"
        "- aggregate_by_species: boolean\n"
        "- use_previous_context: boolean\n"
        "- reason: short string\n\n"
        f"Question: {question}"
    )
    try:
        response = chat_model.invoke(prompt)
    except Exception:
        return fallback

    payload = _extract_json_object(getattr(response, "content", response))
    if not payload:
        return fallback

    task_type = str(payload.get("task_type") or "").strip()
    if task_type not in {
        "fasta_count",
        "blast_top10_table",
        "blast_top1_table",
        "grouped_species_table",
        "compare_species_sets",
        "unknown",
    }:
        task_type = fallback["task_type"]

    output_mode = str(payload.get("output_mode") or "").strip()
    if output_mode not in {"prose", "bullet_list", "markdown_table"}:
        output_mode = fallback["output_mode"]

    try:
        top_n = int(payload["top_n"]) if payload.get("top_n") is not None else None
    except (TypeError, ValueError):
        top_n = fallback["top_n"]

    return {
        "task_type": task_type,
        "output_mode": output_mode,
        "include_ratio_percent": bool(payload.get("include_ratio_percent", fallback["include_ratio_percent"])),
        "top_n": top_n,
        "aggregate_by_species": bool(payload.get("aggregate_by_species", fallback["aggregate_by_species"])),
        "use_previous_context": bool(payload.get("use_previous_context", fallback["use_previous_context"])),
        "reason": str(payload.get("reason") or "").strip(),
    }


def _understand_sequence_request_heuristic(question: str) -> dict:
    normalized = question.lower()

    include_ratio_percent = any(
        term in normalized for term in ["ratio", "percent", "%", "割合", "比率", "リード数の割合"]
    )
    aggregate_by_species = any(
        term in normalized
        for term in ["まとめ", "同じ植物種", "aggregate", "group", "grouped", "合計", "sum"]
    )
    use_previous_context = any(
        term in normalized
        for term in ["次に", "最後に", "この表", "その表", "これ", "それ", "based on this table", "based on"]
    )

    task_type = "unknown"
    output_mode = "prose"
    top_n = None

    if "fasta" in normalized and any(
        term in normalized for term in ["数", "count", "how many", "何個", "何本"]
    ):
        task_type = "fasta_count"
    elif any(
        term in normalized
        for term in ["違い", "比較", "共通", "片方", "compare", "comparison", "shared", "common"]
    ):
        task_type = "compare_species_sets"
    elif aggregate_by_species:
        task_type = "grouped_species_table"
        output_mode = "markdown_table"
    elif any(term in normalized for term in ["blast", "blastn"]) and any(
        term in normalized for term in ["上位10", "top10", "top 10", "10位"]
    ):
        task_type = "blast_top10_table"
        output_mode = "markdown_table"
        top_n = 10
    elif re.search(r"(?:上位1位|top1|top 1|1位のみ)(?!\d)", normalized):
        task_type = "blast_top1_table"
        output_mode = "markdown_table"
        top_n = 1

    return {
        "task_type": task_type,
        "output_mode": output_mode,
        "include_ratio_percent": include_ratio_percent,
        "top_n": top_n,
        "aggregate_by_species": aggregate_by_species,
        "use_previous_context": use_previous_context,
        "reason": "",
    }


def understand_sample_request(question: str, chat_model=None) -> dict:
    fallback = _understand_sample_request_heuristic(question)
    if chat_model is None:
        return fallback

    prompt = (
        "You analyze a user's request about sample metadata from thesis or field records. "
        "The user may ask in flexible prose, not fixed templates. "
        "Return JSON only with keys:\n"
        "- requested_fields: array chosen from site, coordinates, subject, species\n"
        "- output_mode: one of prose, bullet_list, markdown_table\n"
        "- use_previous_context: boolean\n"
        "- reason: short string\n\n"
        f"Question: {question}"
    )
    try:
        response = chat_model.invoke(prompt)
    except Exception:
        return fallback

    payload = _extract_json_object(getattr(response, "content", response))
    if not payload:
        return fallback

    requested_fields = []
    for field in payload.get("requested_fields", []):
        text = str(field).strip().lower()
        if text in {"site", "coordinates", "subject", "species"} and text not in requested_fields:
            requested_fields.append(text)
    if not requested_fields:
        requested_fields = fallback["requested_fields"]

    output_mode = str(payload.get("output_mode") or "").strip()
    if output_mode not in {"prose", "bullet_list", "markdown_table"}:
        output_mode = fallback["output_mode"]

    return {
        "requested_fields": requested_fields,
        "output_mode": output_mode,
        "use_previous_context": bool(payload.get("use_previous_context", fallback["use_previous_context"])),
        "reason": str(payload.get("reason") or "").strip(),
    }


def _understand_sample_request_heuristic(question: str) -> dict:
    normalized = question.lower()
    requested_fields = []

    if any(term in normalized for term in ["採取地名", "採取地", "site", "location"]):
        requested_fields.append("site")
    if any(term in normalized for term in ["緯度経度", "座標", "coordinates", "longitude", "latitude"]):
        requested_fields.append("coordinates")
    if any(term in normalized for term in ["ハチミツ", "巣くず", "プロポリス", "material", "subject"]):
        requested_fields.append("subject")
    if any(term in normalized for term in ["ニホンミツバチ", "セイヨウミツバチ", "bee", "species"]):
        requested_fields.append("species")

    if not requested_fields:
        requested_fields = ["site", "coordinates", "subject", "species"]

    output_mode = "prose"
    if any(term in normalized for term in ["表", "table"]):
        output_mode = "markdown_table"
    elif any(term in normalized for term in ["list", "列出", "箇条書き"]):
        output_mode = "bullet_list"

    use_previous_context = any(
        term in normalized for term in ["次に", "最後に", "この表", "その表", "これ", "それ", "based on"]
    )

    return {
        "requested_fields": requested_fields,
        "output_mode": output_mode,
        "use_previous_context": use_previous_context,
        "reason": "",
    }


def understand_table_request(question: str, chat_model=None) -> dict:
    fallback = _understand_table_request_heuristic(question)
    if chat_model is None:
        return fallback

    prompt = (
        "You analyze a user's request about structured biological result tables. "
        "The user may ask in flexible prose, not fixed templates. "
        "Return JSON only with keys:\n"
        "- task_type: one of asv_details, species_matches, sample_species, sample_asvs, sample_total_reads, top_asvs, top_species, unknown\n"
        "- output_mode: one of prose, bullet_list, markdown_table\n"
        "- include_sample_breakdown: boolean\n"
        "- include_identity: boolean\n"
        "- include_target: boolean\n"
        "- top_n: integer or null\n"
        "- use_previous_context: boolean\n"
        "- reason: short string\n\n"
        f"Question: {question}"
    )
    try:
        response = chat_model.invoke(prompt)
    except Exception:
        return fallback

    payload = _extract_json_object(getattr(response, "content", response))
    if not payload:
        return fallback

    task_type = str(payload.get("task_type") or "").strip()
    if task_type not in {
        "asv_details",
        "species_matches",
        "sample_species",
        "sample_asvs",
        "sample_total_reads",
        "top_asvs",
        "top_species",
        "unknown",
    }:
        task_type = fallback["task_type"]

    output_mode = str(payload.get("output_mode") or "").strip()
    if output_mode not in {"prose", "bullet_list", "markdown_table"}:
        output_mode = fallback["output_mode"]

    try:
        top_n = int(payload["top_n"]) if payload.get("top_n") is not None else None
    except (TypeError, ValueError):
        top_n = fallback["top_n"]

    return {
        "task_type": task_type,
        "output_mode": output_mode,
        "include_sample_breakdown": bool(payload.get("include_sample_breakdown", fallback["include_sample_breakdown"])),
        "include_identity": bool(payload.get("include_identity", fallback["include_identity"])),
        "include_target": bool(payload.get("include_target", fallback["include_target"])),
        "top_n": top_n,
        "use_previous_context": bool(payload.get("use_previous_context", fallback["use_previous_context"])),
        "reason": str(payload.get("reason") or "").strip(),
    }


def _understand_table_request_heuristic(question: str) -> dict:
    normalized = question.lower()

    output_mode = "prose"
    if any(term in normalized for term in ["表", "table"]):
        output_mode = "markdown_table"
    elif any(term in normalized for term in ["list", "列出", "箇条書き"]):
        output_mode = "bullet_list"

    task_type = "unknown"
    if "asv" in normalized:
        task_type = "asv_details"
    elif any(term in normalized for term in ["合計", "sum", "total"]) and any(
        term in normalized for term in ["sample", "サンプル", "試料", "样本"]
    ):
        task_type = "sample_total_reads"
    elif any(term in normalized for term in ["sample", "サンプル", "試料", "样本"]) and any(
        term in normalized for term in ["asv", "otu"]
    ):
        task_type = "sample_asvs"
    elif any(term in normalized for term in ["sample", "サンプル", "試料", "样本"]):
        task_type = "sample_species"
    elif re.search(r"\b[A-Z][a-z]+\s+[a-z][a-z.\-]+\b", question):
        task_type = "species_matches"
    elif any(term in normalized for term in ["top", "上位", "最多"]) and "asv" in normalized:
        task_type = "top_asvs"
    elif any(term in normalized for term in ["top", "上位", "最多"]):
        task_type = "top_species"

    match = re.search(r"(?:top|上位)\s*(\d+)", normalized)
    top_n = int(match.group(1)) if match else None

    return {
        "task_type": task_type,
        "output_mode": output_mode,
        "include_sample_breakdown": any(term in normalized for term in ["sample reads", "各サンプル", "breakdown"]),
        "include_identity": any(term in normalized for term in ["identity", "相同性"]),
        "include_target": any(term in normalized for term in ["target", "blast"]),
        "top_n": top_n,
        "use_previous_context": any(
            term in normalized for term in ["次に", "最後に", "この表", "その表", "based on"]
        ),
        "reason": "",
    }
