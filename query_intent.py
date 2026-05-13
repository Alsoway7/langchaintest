import json
import re


VALID_MARKERS = {"COI", "gPlant", "all"}
VALID_CATEGORIES = {"knowledge", "tables", "reports", "sequences"}
VALID_TABLE_QUERY_TYPES = {
    "asv_details",
    "species_matches",
    "top_asvs",
    "top_species",
    "sample_species",
    "sample_asvs",
    "sample_total_reads",
    "unknown",
}


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


def _normalize_markers(values) -> list[str]:
    if not isinstance(values, list):
        return []
    markers = []
    for value in values:
        text = str(value).strip()
        lowered = text.lower()
        if lowered == "coi":
            markers.append("COI")
        elif lowered in {"gplant", "rbcl", "rbc", "g plant"}:
            markers.append("gPlant")
        elif lowered == "all":
            markers.append("all")
    return list(dict.fromkeys(markers))


def _normalize_categories(values) -> list[str]:
    if not isinstance(values, list):
        return []
    categories = []
    for value in values:
        text = str(value).strip().lower()
        if text in VALID_CATEGORIES:
            categories.append(text)
    return list(dict.fromkeys(categories))


def _normalize_table_query_type(value: object) -> str:
    text = str(value or "").strip().lower()
    return text if text in VALID_TABLE_QUERY_TYPES else "unknown"


def _normalize_string_list(values) -> list[str]:
    if not isinstance(values, list):
        return []
    result = []
    for value in values:
        text = str(value).strip()
        if text:
            result.append(text)
    return list(dict.fromkeys(result))


def _normalize_limit(value: object, default: int = 10) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(number, 50))


def _invoke_json(chat_model, prompt: str) -> dict | None:
    if chat_model is None:
        return None
    try:
        response = chat_model.invoke(prompt)
    except Exception:
        return None
    return _extract_json_object(getattr(response, "content", response))


def infer_sample_metadata_intent(question: str, sample_ids: list[str], chat_model) -> dict | None:
    if not sample_ids:
        return None

    prompt = (
        "You classify whether a question is asking for sample metadata from thesis documents. "
        "Metadata means collection site, region, coordinates, material type, or bee species for the sample. "
        "The user may write freely in Chinese, Japanese, or English. "
        "Return JSON only with keys: should_use_sample_query (boolean), confidence (0 to 1), reason (string).\n\n"
        f"Question: {question}\n"
        f"Detected sample IDs: {json.dumps(sample_ids, ensure_ascii=False)}"
    )
    return _invoke_json(chat_model, prompt)


def infer_table_query_intent(question: str, chat_model) -> dict | None:
    prompt = (
        "You classify a biological data question for a structured table lookup system. "
        "The user may write in free prose and does not need to use fixed keywords. "
        "Return JSON only with these keys:\n"
        "- should_use_table_query: boolean\n"
        "- query_type: one of asv_details, species_matches, top_asvs, top_species, sample_species, sample_asvs, sample_total_reads, unknown\n"
        "- markers: array containing any of COI, gPlant, all\n"
        "- asv_ids: array of ASV IDs exactly as referenced when possible\n"
        "- sample_ids: array of sample IDs exactly as referenced when possible\n"
        "- species_name: string or null\n"
        "- limit: integer 1 to 50\n"
        "- confidence: number 0 to 1\n"
        "- reason: short string\n"
        "Choose should_use_table_query=true only if the question is mainly asking for exact reads, ASVs, species assignments, "
        "rankings, or what was detected in a sample from the structured analysis tables.\n\n"
        f"Question: {question}"
    )
    payload = _invoke_json(chat_model, prompt)
    if not payload:
        return None

    return {
        "should_use_table_query": bool(payload.get("should_use_table_query")),
        "query_type": _normalize_table_query_type(payload.get("query_type")),
        "markers": _normalize_markers(payload.get("markers")) or ["all"],
        "asv_ids": _normalize_string_list(payload.get("asv_ids")),
        "sample_ids": _normalize_string_list(payload.get("sample_ids")),
        "species_name": (str(payload.get("species_name")).strip() or None)
        if payload.get("species_name") is not None
        else None,
        "limit": _normalize_limit(payload.get("limit"), default=10),
        "confidence": payload.get("confidence"),
        "reason": str(payload.get("reason") or "").strip(),
    }


def infer_rag_query_plan(question: str, chat_model) -> dict | None:
    prompt = (
        "You plan retrieval routes for a local biological data RAG system. "
        "The user may ask in free prose without fixed keywords. "
        "Return JSON only with keys: markers, categories, mode, confidence, reason.\n"
        "- markers: array of COI, gPlant, or all\n"
        "- categories: array of knowledge, tables, reports, sequences\n"
        "- mode: single or comparison\n"
        "Use comparison only when the user is explicitly comparing COI and gPlant or two data scopes.\n\n"
        f"Question: {question}"
    )
    payload = _invoke_json(chat_model, prompt)
    if not payload:
        return None

    markers = _normalize_markers(payload.get("markers")) or ["all"]
    categories = _normalize_categories(payload.get("categories")) or ["knowledge", "tables", "reports"]
    mode = str(payload.get("mode") or "single").strip().lower()
    if mode not in {"single", "comparison"}:
        mode = "single"

    return {
        "markers": markers,
        "categories": categories,
        "mode": mode,
        "confidence": payload.get("confidence"),
        "reason": str(payload.get("reason") or "").strip(),
    }
