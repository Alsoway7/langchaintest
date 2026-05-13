from dataclasses import dataclass

from query_intent import infer_rag_query_plan


@dataclass(frozen=True)
class QueryPlan:
    markers: tuple[str, ...]
    categories: tuple[str, ...]
    mode: str


def _plan_query_heuristic(question: str) -> QueryPlan:
    normalized = question.lower()
    markers = []
    categories = []

    mentions_coi = "coi" in normalized
    mentions_gplant = any(term in normalized for term in ["gplant", "rbcl", "rbc"])
    asks_comparison = any(
        term in normalized
        for term in ["compare", "comparison", "difference", "versus", "vs", "对比", "比较", "違い", "比較して"]
    )

    if mentions_coi:
        markers.append("COI")
    if mentions_gplant:
        markers.append("gPlant")

    table_terms = [
        "blast",
        "read",
        "reads",
        "asv",
        "identity",
        "species",
        "sample",
        "detected",
        "top",
        "count",
        "物种",
        "生物",
        "检测",
        "检出",
        "配列",
        "相同性",
    ]
    report_terms = [
        "quality",
        "report",
        "fastq",
        "fasta",
        "xlsx",
        "tsv",
        "qza",
        "qzv",
        "报告",
        "文件",
        "レポート",
    ]
    knowledge_terms = [
        "thesis",
        "research",
        "background",
        "method",
        "methods",
        "conclusion",
        "summary",
        "study",
        "paper",
        "论文",
        "研究",
        "背景",
        "方法",
        "目的",
        "考察",
        "結論",
    ]
    sequence_terms = ["fasta", "sequence", "配列", "塩基", "序列"]

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


def plan_query(question: str, chat_model=None) -> QueryPlan:
    llm_plan = infer_rag_query_plan(question, chat_model)
    if llm_plan:
        return QueryPlan(
            markers=tuple(llm_plan["markers"]),
            categories=tuple(llm_plan["categories"]),
            mode=llm_plan["mode"],
        )
    return _plan_query_heuristic(question)
