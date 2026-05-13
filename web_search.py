from html import unescape
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote_plus, unquote, urlparse
from urllib.request import Request, urlopen

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate


def is_blast_only_question(question: str) -> bool:
    """Return True only when the question explicitly asks to use external NCBI BLAST.
    Questions about local BLAST results (学名/植物種 via Excel) should NOT be blocked here —
    those are handled by the table/sequence backends before web_search is even called.
    """
    normalized = question.lower()
    explicit_external = [
        "ncbi blast",
        "blast.ncbi",
        "ncbi に",
        "ncbi で",
        "ncbiで",
        "ncbiに",
        "online blast",
        "ウェブblast",
        "web blast",
    ]
    return any(term in normalized for term in explicit_external)


class DuckDuckGoHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.results = []
        self._in_title = False
        self._in_snippet = False
        self._current_title = []
        self._current_snippet = []
        self._current_url = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = attrs.get("class", "")
        if tag == "a" and "result__a" in classes:
            self._flush()
            self._in_title = True
            self._current_url = attrs.get("href")
            self._current_title = []
            self._current_snippet = []
        elif tag in {"a", "div"} and "result__snippet" in classes:
            self._in_snippet = True

    def handle_endtag(self, tag):
        if tag == "a" and self._in_title:
            self._in_title = False
        elif tag in {"a", "div"} and self._in_snippet:
            self._in_snippet = False
            self._flush()

    def handle_data(self, data):
        if self._in_title:
            self._current_title.append(data)
        elif self._in_snippet:
            self._current_snippet.append(data)

    def close(self):
        super().close()
        self._flush()

    def _flush(self):
        title = " ".join(part.strip() for part in self._current_title if part.strip())
        snippet = " ".join(part.strip() for part in self._current_snippet if part.strip())
        if title and self._current_url:
            result = {
                "title": unescape(title),
                "url": unescape(self._current_url),
                "snippet": unescape(snippet),
            }
            if result not in self.results:
                self.results.append(result)
        self._current_title = []
        self._current_snippet = []
        self._current_url = None


def search_web(query: str, max_results: int = 5) -> list[dict]:
    url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; local-rag-search/1.0)",
        },
    )
    try:
        with urlopen(request, timeout=15) as response:
            html = response.read().decode("utf-8", errors="ignore")
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"web search failed: {exc}") from exc

    parser = DuckDuckGoHTMLParser()
    parser.feed(html)
    parser.close()
    return parser.results[:max_results]


def clean_result_url(url: str) -> str:
    if url.startswith("//"):
        url = "https:" + url
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    if "uddg" in params and params["uddg"]:
        return unquote(params["uddg"][0])
    return url


def format_search_context(results: list[dict]) -> str:
    parts = []
    for index, result in enumerate(results, start=1):
        parts.append(
            f"[W{index}] {result['title']}\n"
            f"URL: {result['url']}\n"
            f"Snippet: {result['snippet']}"
        )
    return "\n\n".join(parts)


def build_web_answer_chain(chat_model):
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "Answer using only the web search snippets provided. "
                "If the snippets are insufficient, say so. "
                "Answer in the same language as the user's question. "
                "Cite web snippets with [W1], [W2], etc.",
            ),
            (
                "human",
                "Web search snippets:\n{context}\n\nQuestion: {question}",
            ),
        ]
    )
    return prompt | chat_model | StrOutputParser()


def answer_from_web(question: str, chat_model, max_results: int = 5) -> dict:
    if is_blast_only_question(question):
        return {
            "answer": (
                "This question is restricted to the NCBI BLASTN site "
                "(https://blast.ncbi.nlm.nih.gov/Blast.cgi?PROGRAM=blastn&PAGE_TYPE=BlastSearch&LINK_LOC=blasthome). "
                "Generic web search is disabled for this query."
            ),
            "sources": [
                "https://blast.ncbi.nlm.nih.gov/Blast.cgi?PROGRAM=blastn&PAGE_TYPE=BlastSearch&LINK_LOC=blasthome"
            ],
            "results": [],
        }

    results = search_web(question, max_results=max_results)
    for result in results:
        result["url"] = clean_result_url(result["url"])
    if not results:
        return {
            "answer": "No web search results were found.",
            "sources": [],
            "results": [],
        }

    chain = build_web_answer_chain(chat_model)
    answer = chain.invoke(
        {
            "context": format_search_context(results),
            "question": question,
        }
    )
    return {
        "answer": answer,
        "sources": [result["url"] for result in results],
        "results": results,
    }
