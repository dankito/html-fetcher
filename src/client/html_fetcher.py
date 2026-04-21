from typing import Protocol

from src.api.dto.fetch_dto import FetchRequest
from src.model.fetch_result import FetchResult


class HtmlFetcher(Protocol):
    async def fetch(self, request: FetchRequest) -> FetchResult: ...
