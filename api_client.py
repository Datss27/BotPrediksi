import asyncio
import aiohttp
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)

class ApiSportsClient:
    def __init__(self, base_url: str, headers: Dict[str, str]):
        self.base_url = base_url
        self.headers = headers
        self.session = None
        self.sem = asyncio.Semaphore(10)

    async def init_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(headers=self.headers)
            logger.info("aiohttp session initialized.")

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
            logger.info("aiohttp session closed.")

    async def fetch_json(self, path: str, params: Dict[str, Any]) -> Any:
        await self.init_session()
        url = f"{self.base_url}/{path}"
        async with self.sem:
            async with self.session.get(url, params=params) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def get_fixtures(self, date: str) -> List[Dict[str, Any]]:
        from main import LIGA_FILTER, TZ  # Hindari circular import
        data = await self.fetch_json("fixtures", {
            "date": date,
            "status": "NS",
            "timezone": str(TZ)
        })
        fixtures = data.get("response", [])
        filtered = [f for f in fixtures if f["league"]["id"] in LIGA_FILTER]
        logger.info("Fixtures fetched %d, after filter %d", date, len(fixtures), len(filtered))
        return await self._attach_predictions(filtered)

    async def _attach_predictions(self, fixtures: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        tasks = [self._attach(f) for f in fixtures]
        return await asyncio.gather(*tasks)

    async def _attach(self, fixture: Dict[str, Any]) -> Dict[str, Any]:
        fid = fixture['fixture']['id']
        try:
            data = await self.fetch_json("predictions", {"fixture": fid})
            fixture['prediction'] = data.get('response', [])
        except Exception as e:
            logger.warning("Failed prediction for %s: %s", fid, e)
            fixture['prediction'] = []
        return fixture
