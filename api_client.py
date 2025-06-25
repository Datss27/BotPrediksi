import asyncio
import aiohttp
import logging
from typing import Dict, Any, List
from settings import settings

logger = logging.getLogger(__name__)

class ApiSportsClient:
    def __init__(self):
        self.base_url = "https://v3.football.api-sports.io"
        self.headers = {"x-apisports-key": settings.api_key}
        self.sem = asyncio.Semaphore(10)
        self.session = aiohttp.ClientSession(headers=self.headers)

    async def fetch_json(self, path: str, params: Dict[str, Any]) -> Any:
        url = f"{self.base_url}/{path}"
        async with self.sem, self.session.get(url, params=params) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def get_fixtures(self, date: str, liga_filter: List[int]) -> List[Dict[str, Any]]:
        resp = await self.fetch_json(
            'fixtures',
            {'date': date, 'status': 'NS', 'timezone': settings.timezone}
        )
        fixtures = resp.get('response', [])
        filtered = [f for f in fixtures if f['league']['id'] in liga_filter]
        logger.info("Fixtures fetched %d → after filter %d", len(fixtures), len(filtered))

        tasks = [self._attach(f) for f in filtered]
        return await asyncio.gather(*tasks)

    async def _attach(self, fixture: Dict[str, Any]) -> Dict[str, Any]:
        fid = fixture['fixture']['id']
        try:
            data = await self.fetch_json('predictions', {'fixture': fid})
            fixture['prediction'] = data.get('response', [])
        except Exception as e:
            logger.warning("Prediction failed for %s: %s", fid, e)
            fixture['prediction'] = []
        return fixture

    async def close(self):
        await self.session.close()
