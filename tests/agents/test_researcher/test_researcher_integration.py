import asyncio

from agents.researcher import ResearcherAgent


class _Resp:
    def __init__(self, text: str) -> None:
        self.text = text


class _Router:
    async def query(self, prompt: str, system_prompt: str):
        _ = (prompt, system_prompt)
        return _Resp('{"facts":[{"text":"Бетон B30","applicability":"высокая","confidence":0.8,"source_ids":["rag-0"]}],"gaps":[]}')


class _Rag:
    async def search(self, query: str, n_results: int = 5, filter_scope: str | None = None):
        _ = (query, n_results, filter_scope)
        return [{"source": "СП", "page": 1, "text": "Бетон B30", "score": 0.9}]


class _Web:
    async def run(self, query: str, max_results: int = 5):
        _ = (query, max_results)
        return []


def test_researcher_integration_flow() -> None:
    agent = ResearcherAgent(_Router(), rag_engine=_Rag(), web_search_tool=_Web())  # type: ignore[arg-type]
    result = asyncio.run(agent.run({"message": "бетон", "history": []}))
    payload = result["research_payload"]
    assert payload["query"] == "бетон"
    assert "research_facts" in result
