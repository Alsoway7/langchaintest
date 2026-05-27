import argparse
import sys

from config import DATA_DIR, INDEX_DIR, load_settings, show_env_status
from llm_factory import build_chat_model, build_embedding_model
from rag import (
    SUPPORTED_EXTENSIONS,
    compose_answer,
    format_rag_entries,
    gather_rag_chunks,
    load_documents,
    render_evidence_block,
    split_documents,
)
from sample_query import format_sample_entries, gather_sample_data
from sequence_query import format_sequence_entries, gather_sequence_data
from table_query import format_table_entries, gather_table_data
from web_search import answer_from_web


def configure_console_encoding():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)


def parse_args():
    parser = argparse.ArgumentParser(description="Local document RAG demo with LangChain and OpenAI.")
    parser.add_argument("question", nargs="?", help="Question to ask about files under data/.")
    parser.add_argument("--dry-run", action="store_true", help="Check config and documents without calling OpenAI.")
    parser.add_argument("--rebuild-index", action="store_true", help="Force rebuilding the local vector index.")
    parser.add_argument("--debug", action="store_true", help="Print retrieved chunks used as answer context.")
    parser.add_argument("--k", type=int, default=8, help="Number of chunks to retrieve.")
    parser.add_argument("--no-web", action="store_true", help="Disable web search fallback.")
    parser.add_argument("--web-results", type=int, default=5, help="Number of web search results to use.")
    return parser.parse_args()


def clean_console_input(value):
    value = "".join(ch for ch in value if not 0xD800 <= ord(ch) <= 0xDFFF)
    return value.lstrip("﻿").strip()


def normalize_asv_ids(question):
    import re
    return re.sub(r"(?i)(?<![A-Za-z\d_])asv_?(\d+)(?![A-Za-z\d_])", lambda m: "ASV_" + m.group(1), question)

def looks_like_follow_up(question):
    normalized = question.lower().strip()
    follow_up_terms = [
        "これ",
        "それ",
        "この",
        "その",
        "この表",
        "その表",
        "次に",
        "最後に",
        "もとにして",
        "上の",
        "前の",
        "刚才",
        "上面",
        "这个",
        "那个",
        "继续",
        "it",
        "that",
        "this",
        "those",
        "them",
        "above",
        "previous",
        "next",
        "lastly",
    ]
    return len(normalized) <= 80 or any(term in normalized for term in follow_up_terms)


def make_standalone_question(question, history, chat_model):
    if not history or not looks_like_follow_up(question):
        return question

    previous = history[-1]
    if chat_model is None:
        return f"Previous question: {previous['question']}\nFollow-up question: {question}"

    prompt = (
        "Rewrite the follow-up question as a standalone search question. "
        "Keep concrete identifiers such as ASV IDs, sample names, COI, gPlant, rbcL, species names, and numbers. "
        "If the follow-up refers to a previous table or previous answer, explicitly carry over the sample ID, "
        "the data source, and the requested transformation of that table. "
        "Do not answer. Return only the rewritten question.\n\n"
        f"Previous question: {previous['question']}\n"
        f"Previous answer: {previous['answer'][:1200]}\n"
        f"Follow-up question: {question}"
    )
    try:
        response = chat_model.invoke(prompt)
        return response.content.strip() or question
    except Exception:
        return f"Previous question: {previous['question']}\nFollow-up question: {question}"


def answer_needs_web(answer):
    normalized = answer.lower()
    phrases = [
        "provided documents do not confirm",
        "does not contain enough evidence",
        "cannot be confirmed",
        "not confirm",
        "无法确认",
        "不能确认",
        "没有足够",
        "not enough evidence",
    ]
    return any(phrase in normalized for phrase in phrases)


def print_web_fallback(question, args, chat_model):
    if args.no_web:
        return None

    print("\nWeb fallback:")
    try:
        web_result = answer_from_web(question, chat_model, max_results=args.web_results)
    except Exception as exc:
        print(f"web search unavailable: {exc}")
        return None

    print(web_result["answer"])
    if web_result["sources"]:
        print("\nWeb sources:")
        for source in web_result["sources"]:
            print("-", source)
    return web_result


def answer_once(
    question,
    args,
    settings,
    documents,
    chat_model=None,
    embeddings=None,
    original_question=None,
    history=None,
):
    question = normalize_asv_ids(question)
    display_question = original_question or question

    if chat_model is None and settings.get("OPENAI_API_KEY"):
        chat_model = build_chat_model(settings)

    # 1. Gather structured evidence — every backend always tries; none short-circuits.
    print("[1/3] Searching tables & sequences...", flush=True)
    table_evidence = gather_table_data(question, DATA_DIR, chat_model=chat_model)
    sequence_evidence = gather_sequence_data(question, DATA_DIR, history=history, chat_model=chat_model)
    sample_evidence = gather_sample_data(question, DATA_DIR, chat_model=chat_model)

    # 2. Gather RAG chunks (always when LLM/index available).
    rag_evidence = None
    if settings.get("OPENAI_API_KEY") and documents:
        print("[2/3] Retrieving document chunks...", flush=True)
        if embeddings is None:
            embeddings = build_embedding_model(settings)
        rag_evidence = gather_rag_chunks(
            question,
            chat_model,
            embeddings,
            DATA_DIR,
            INDEX_DIR,
            k=args.k,
            rebuild_index=args.rebuild_index,
        )

    # 3. Merge into a single numbered evidence list.
    entries = []
    entries.extend(format_table_entries(table_evidence))
    entries.extend(format_sequence_entries(sequence_evidence))
    entries.extend(format_sample_entries(sample_evidence))
    if rag_evidence:
        entries.extend(format_rag_entries(rag_evidence))

    print("\nQuestion:")
    print(display_question)
    if display_question != question:
        print("\nInterpreted question:")
        print(question)

    # 4. Compose final answer.
    if not entries:
        print("\nNo local evidence found.")
        if chat_model is None:
            print("Missing OPENAI_API_KEY. Add it to .env first.")
            return None
        web_result = print_web_fallback(question, args, chat_model)
        if web_result:
            return {
                "question": display_question,
                "search_question": question,
                "answer": web_result["answer"],
                "web_result": web_result,
            }
        return None

    if chat_model is None:
        answer = "Missing OPENAI_API_KEY. Add it to .env first.\n\nGathered evidence:\n" + render_evidence_block(entries)
    else:
        print("[3/3] Composing answer...", flush=True)
        answer = compose_answer(question, entries, chat_model)

    print("\nEvidence sources:")
    for index, entry in enumerate(entries, start=1):
        print(f"  [{index}] {entry['kind']}: {entry['source']}")

    if rag_evidence:
        plan = rag_evidence["plan"]
        index_info = rag_evidence["index_info"]
        print("\nIndex:")
        print("rebuilt:", index_info["rebuilt"])
        print("documents:", index_info["documents_count"])
        if index_info["chunks_count"] is not None:
            print("chunks:", index_info["chunks_count"])
        print("\nQuery plan:")
        print("markers:", ", ".join(plan.markers))
        print("categories:", ", ".join(plan.categories))
        print("mode:", plan.mode)

    print("\nAnswer:")
    print(answer)

    if args.debug:
        print("\nFull evidence dump:")
        print(render_evidence_block(entries))

    final_answer = answer
    web_result = None
    if answer and answer_needs_web(answer):
        web_result = print_web_fallback(question, args, chat_model)
        if web_result:
            final_answer = web_result["answer"]

    sequence_context = None
    if sequence_evidence and sequence_evidence.get("samples"):
        sequence_context = {"sample_id": sequence_evidence["samples"][0]["requested_id"]}

    return {
        "question": display_question,
        "search_question": question,
        "answer": final_answer,
        "local_answer": answer,
        "web_result": web_result,
        "sequence_context": sequence_context,
    }


def main():
    configure_console_encoding()
    args = parse_args()
    settings = load_settings()
    show_env_status(settings)

    documents = load_documents(DATA_DIR)
    chunks = split_documents(documents) if documents else []
    print("Documents loaded:", len(documents))
    print("Chunks created:", len(chunks))
    print("Supported extensions:", ", ".join(sorted(SUPPORTED_EXTENSIONS)))

    if args.dry_run:
        return

    if args.question:
        answer_once(args.question, args, settings, documents, history=[])
        return

    chat_model = None
    embeddings = None
    if settings.get("OPENAI_API_KEY") and documents:
        chat_model = build_chat_model(settings)
        embeddings = build_embedding_model(settings)

    history = []
    print("\nEnter a question. Type '退出', 'exit', 'quit', or 'q' to stop.")
    while True:
        try:
            question = clean_console_input(input("\nQuestion: "))
        except EOFError:
            print("\nBye.")
            return
        if question.lower() in {"exit", "quit", "q"} or question == "退出":
            print("Bye.")
            return
        if not question:
            print("No question provided.")
            continue

        print("Thinking...", flush=True)
        search_question = make_standalone_question(question, history, chat_model)
        record = answer_once(
            search_question,
            args,
            settings,
            documents,
            chat_model,
            embeddings,
            original_question=question,
            history=history,
        )
        if record:
            history.append(record)
            history = history[-5:]
        args.rebuild_index = False


if __name__ == "__main__":
    main()
