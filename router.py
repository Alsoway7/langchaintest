def choose_provider(task_type: str, openai_available: bool) -> str:
    if task_type in ["code", "reasoning"] and openai_available:
        return "openai"
    return "gemini"


def invoke_with_fallback(models, prompt: str, task_type: str = "general"):
    gemini_available = models.get("gemini") is not None
    openai_available = models.get("openai") is not None

    if not gemini_available and not openai_available:
        return {
            "provider": "none",
            "content": "",
            "ok": False,
            "error": "没有可用模型，请检查 .env 中的 API key。",
        }

    provider = choose_provider(task_type, openai_available)

    if models.get(provider) is None:
        provider = "gemini" if gemini_available else "openai"

    try:
        result = models[provider].invoke(prompt)
        return {
            "provider": provider,
            "content": result.content,
            "ok": True,
        }
    except Exception as e:
        if provider == "openai" and gemini_available:
            try:
                result = models["gemini"].invoke(prompt)
                return {
                    "provider": "gemini(fallback)",
                    "content": result.content,
                    "ok": True,
                    "error": str(e),
                }
            except Exception as e2:
                return {
                    "provider": "none",
                    "content": "",
                    "ok": False,
                    "error": f"OpenAI失败: {e}; Gemini回退也失败: {e2}",
                }

        return {
            "provider": provider,
            "content": "",
            "ok": False,
            "error": str(e),
        }