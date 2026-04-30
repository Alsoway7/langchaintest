from dataclasses import dataclass


@dataclass(frozen=True)
class QueryPlan:
    markers: tuple[str, ...]
    categories: tuple[str, ...]
    mode: str


# 根据用户自然语言问题，自动判断应该优先检索哪些数据范围。
def plan_query(question: str) -> QueryPlan:
    normalized = question.lower()
    markers = []
    categories = []

    mentions_coi = "coi" in normalized
    mentions_gplant = "gplant" in normalized or "rbc" in normalized or "rbcl" in normalized
    asks_comparison = any(
        term in normalized
        for term in [
            "比較",
            "違い",
            "差",
            "compare",
            "comparison",
            "difference",
        ]
    )

    if mentions_coi:
        markers.append("COI")
    if mentions_gplant:
        markers.append("gPlant")

    table_terms = [
        "blast",
        "代表配列",
        "read",
        "リード",
        "asv",
        "相同性",
        "species",
        "生物種",
        "検出",
        "植物種",
        "リード数",
    ]
    report_terms = [
        "説明",
        "納品",
        "quality",
        "手順",
        "ファイル",
        "データ",
        "qza",
        "qzv",
        "fastq",
        "fasta",
        "xlsx",
        "tsv",
    ]
    knowledge_terms = [
        "論文",
        "目的",
        "背景",
        "考察",
        "概要",
        "研究",
        "調査",
        "要約",
        "方法",
        "結論",
    ]
    sequence_terms = [
        "fasta",
        "配列",
        "塩基",
        "sequence",
    ]

    has_table_intent = any(term in normalized for term in table_terms)
    has_report_intent = any(term in normalized for term in report_terms)
    has_knowledge_intent = any(term in normalized for term in knowledge_terms)
    has_sequence_intent = any(term in normalized for term in sequence_terms)

    if has_table_intent:
        categories.append("tables")
    if has_report_intent and not has_knowledge_intent:
        categories.append("reports")
    if has_knowledge_intent:
        categories.append("knowledge")
    if has_sequence_intent and not has_table_intent:
        categories.append("sequences")

    if not categories:
        categories.extend(["knowledge", "tables", "reports"])

    if not markers:
        markers.append("all")

    mode = "comparison" if asks_comparison and mentions_coi and mentions_gplant else "single"

    return QueryPlan(
        markers=tuple(dict.fromkeys(markers)),
        categories=tuple(dict.fromkeys(categories)),
        mode=mode,
    )
