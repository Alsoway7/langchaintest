import argparse

from config import DATA_DIR, INDEX_DIR, load_settings, show_env_status
from llm_factory import build_chat_model, build_embedding_model
from rag import SUPPORTED_EXTENSIONS, load_documents, split_documents, answer_question
from table_query import answer_table_query, format_table_answer


# 解析命令行参数，支持交互提问、dry-run、debug 和检索数量配置。
def parse_args():
    parser = argparse.ArgumentParser(description="Local document RAG demo with LangChain and OpenAI.")
    parser.add_argument("question", nargs="?", help="Question to ask about files under data/.")
    parser.add_argument("--dry-run", action="store_true", help="Check config and documents without calling OpenAI.")
    parser.add_argument("--rebuild-index", action="store_true", help="Force rebuilding the local vector index.")
    parser.add_argument("--debug", action="store_true", help="Print retrieved chunks used as answer context.")
    parser.add_argument("--k", type=int, default=8, help="Number of chunks to retrieve.")
    return parser.parse_args()


# 程序入口：优先处理精确表格查询，否则执行 RAG 检索问答。
def main():
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

    question = args.question
    if not question:
        question = input("\n请输入你的问题: ").strip()

    if not question:
        print("No question provided.")
        return

    table_result = answer_table_query(question, DATA_DIR)
    if table_result:
        print("\nQuestion:")
        print(question)
        print("\nAnswer:")
        print(format_table_answer(table_result))
        return

    if not settings.get("OPENAI_API_KEY"):
        print("Missing OPENAI_API_KEY. Add it to .env first.")
        return

    if not documents:
        print("No documents found. Add supported files under data/.")
        return

    chat_model = build_chat_model(settings)
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


if __name__ == "__main__":
    main()
