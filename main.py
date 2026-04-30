import argparse
import sys

from config import DATA_DIR, INDEX_DIR, load_settings, show_env_status
from llm_factory import build_chat_model, build_embedding_model
from rag import SUPPORTED_EXTENSIONS, load_documents, split_documents, answer_question
from sample_query import answer_sample_query, format_sample_answer
from table_query import answer_table_query, format_table_answer
from web_search import answer_from_web


def configure_console_encoding():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


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
    return value.lstrip("\ufeffï»¿ｻｿ").strip()


def looks_like_follow_up(question):
    normalized = question.lower().strip()
    follow_up_terms = [
        "它",
        "这个",
        "那个",
        "上面",
        "刚才",
        "继续",
        "呢",
        "これ",
        "それ",
        "その",
        "上",
        "続き",
        "it",
        "that",
        "this",
        "those",
        "them",
        "above",
        "previous",
    ]
    return len(normalized) <= 40 or any(term in normalized for term in follow_up_terms)


def make_standalone_question(question, history, chat_model):
    if not history or not looks_like_follow_up(question):
        return question

    previous = history[-1]
    if chat_model is None:
        return f"Previous question: {previous['question']}\nFollow-up question: {question}"

    prompt = (
        "Rewrite the follow-up question as a standalone search question. "
        "Keep concrete identifiers such as ASV IDs, sample names, COI, gPlant, rbcL, species names, and numbers. "
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
        "確認できません",
        "提示されていない",
        "无法确认",
        "不能确认",
        "没有足够",
        "未提供",
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


def answer_once(question, args, settings, documents, chat_model=None, embeddings=None, original_question=None):
    display_question = original_question or question

    sample_result = answer_sample_query(question, DATA_DIR)
    if sample_result:
        answer = format_sample_answer(sample_result)
        print("\nQuestion:")
        print(display_question)
        if display_question != question:
            print("\nInterpreted question:")
            print(question)
        print("\nAnswer:")
        print(answer)
        return {"question": display_question, "search_question": question, "answer": answer}

    table_result = answer_table_query(question, DATA_DIR)
    if table_result:
        answer = format_table_answer(table_result)
        print("\nQuestion:")
        print(display_question)
        if display_question != question:
            print("\nInterpreted question:")
            print(question)
        print("\nAnswer:")
        print(answer)
        return {"question": display_question, "search_question": question, "answer": answer}

    if not settings.get("OPENAI_API_KEY"):
        print("Missing OPENAI_API_KEY. Add it to .env first.")
        return None

    if not documents:
        print("No documents found. Add supported files under data/.")
        if chat_model is None:
            chat_model = build_chat_model(settings)
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
        chat_model = build_chat_model(settings)
    if embeddings is None:
        embeddings = build_embedding_model(settings)

    result = answer_question(
        question,
        chat_model,
        embeddings,
        DATA_DIR,
        INDEX_DIR,
        k=args.k,
        rebuild_index=args.rebuild_index,
    )

    print("\nQuestion:")
    print(display_question)
    if display_question != question:
        print("\nInterpreted question:")
        print(question)
    print("\nIndex:")
    print("rebuilt:", result["index_rebuilt"])
    print("documents:", result["documents_count"])
    if result["chunks_count"] is not None:
        print("chunks:", result["chunks_count"])
    print("\nQuery plan:")
    print("markers:", ", ".join(result["query_plan"]["markers"]))
    print("categories:", ", ".join(result["query_plan"]["categories"]))
    print("mode:", result["query_plan"]["mode"])
    print("\nAnswer:")
    print(result["answer"])
    print("\nSources:")
    for source in result["sources"]:
        print("-", source)

    if args.debug:
        print("\nRetrieved chunks:")
        for index, document in enumerate(result["retrieved_documents"], start=1):
            content = document["content"].replace("\n", " ")
            preview = content[:700] + ("..." if len(content) > 700 else "")
            print(f"\n[{index}] {document['source']}")
            if document.get("marker") or document.get("category"):
                print("marker/category:", document.get("marker"), "/", document.get("category"))
            if document["chunk_start"] is not None:
                print("chunk_start:", document["chunk_start"])
            print(preview)

    final_answer = result["answer"]
    web_result = None
    if answer_needs_web(result["answer"]):
        web_result = print_web_fallback(question, args, chat_model)
        if web_result:
            final_answer = web_result["answer"]

    return {
        "question": display_question,
        "search_question": question,
        "answer": final_answer,
        "local_answer": result["answer"],
        "web_result": web_result,
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
        answer_once(args.question, args, settings, documents)
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

        search_question = make_standalone_question(question, history, chat_model)
        record = answer_once(
            search_question,
            args,
            settings,
            documents,
            chat_model,
            embeddings,
            original_question=question,
        )
        if record:
            history.append(record)
            history = history[-5:]
        args.rebuild_index = False


if __name__ == "__main__":
    main()
