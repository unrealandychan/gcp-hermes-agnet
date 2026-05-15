"""
tools/search_tool.py

ADK FunctionTool wrapping Vertex AI RAG Engine retrieval from the knowledge corpus.
Used by all vertical agents to search enterprise documentation, runbooks, and policies.
"""
from google.adk.tools import FunctionTool
from vertexai.preview import rag

from config import Settings

_DEFAULT_TOP_K = 5
_DEFAULT_DISTANCE_THRESHOLD = 0.5


def make_search_tool(settings: Settings) -> FunctionTool:
    corpus_name = settings.knowledge_corpus_name

    def knowledge_search(
        query: str,
        top_k: int = _DEFAULT_TOP_K,
    ) -> dict:
        """
        Search the enterprise knowledge base for relevant documents.

        Args:
            query: Natural language search query.
            top_k: Number of results to return (default 5, max 20).

        Returns:
            dict with 'results': list of {text, source, score} dicts.
            On error: {'error': str}
        """
        if not corpus_name:
            return {"error": "KNOWLEDGE_CORPUS_NAME not configured."}

        top_k = min(max(1, top_k), 20)

        try:
            response = rag.retrieval_query(
                rag_resources=[rag.RagResource(rag_corpus=corpus_name)],
                text=query,
                similarity_top_k=top_k,
                vector_distance_threshold=_DEFAULT_DISTANCE_THRESHOLD,
            )
            results = [
                {
                    "text": ctx.text,
                    "source": ctx.source_uri,
                    "score": ctx.score,
                }
                for ctx in response.contexts.contexts
            ]
            return {"results": results}
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}

    return FunctionTool(func=knowledge_search)
