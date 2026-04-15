from langchain_openai import ChatOpenAI, OpenAIEmbeddings


# 构建用于最终回答的 OpenAI 聊天模型。
def build_chat_model(settings: dict):
    openai_key = settings.get("OPENAI_API_KEY")
    if not openai_key:
        return None

    return ChatOpenAI(
        model=settings.get("OPENAI_MODEL") or "gpt-5.4-mini",
        temperature=0,
        api_key=openai_key,
    )


# 构建用于文档向量化和问题向量化的 OpenAI Embedding 模型。
def build_embedding_model(settings: dict):
    openai_key = settings.get("OPENAI_API_KEY")
    if not openai_key:
        return None

    return OpenAIEmbeddings(
        model=settings.get("OPENAI_EMBEDDING_MODEL") or "text-embedding-3-small",
        api_key=openai_key,
    )
