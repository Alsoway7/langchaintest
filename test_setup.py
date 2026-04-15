from config import load_settings
from llm_factory import build_chat_model, build_embedding_model


# 简单测试 OpenAI chat 和 embedding 是否能正常调用。
def main():
    settings = load_settings()

    if not settings.get("OPENAI_API_KEY"):
        print("No OPENAI_API_KEY found. Add it to .env first.")
        return

    chat_model = build_chat_model(settings)
    embedding_model = build_embedding_model(settings)

    try:
        resp = chat_model.invoke("Reply with exactly: chat ok")
        print("[chat]")
        print(resp.content)
    except Exception as exc:
        print("[chat] call failed:", exc)

    try:
        vector = embedding_model.embed_query("embedding ok")
        print("[embedding]")
        print("dimension:", len(vector))
    except Exception as exc:
        print("[embedding] call failed:", exc)


if __name__ == "__main__":
    main()
