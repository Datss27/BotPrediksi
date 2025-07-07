import asyncio
import aiohttp
from typing import List, Dict, Any
import logging
from cachetools import TTLCache
from main import LIGA_FILTER, TZ

logger = logging.getLogger(__name__)

class ApiSportsClient:
    def __init__(self, base_url: str, headers: Dict[str, str]):
        self.base_url = base_url
        self.headers = headers
        self.session = None
        self.sem = asyncio.Semaphore(10)
        self.fixtures_cache = TTLCache(maxsize=1000, ttl=21600)
        self.fixture_prediction_cache = TTLCache(maxsize=500, ttl=3600)
        
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

        # Cek cache
        if date in self.fixtures_cache:
            return self.fixtures_cache[date]

        all_fixtures = []
        limit = 50
        offset = 0
        tz = TZ.zone if hasattr(TZ, 'zone') else str(TZ)

        while True:
            params = {
                "date": date,
                "status": "NS",
                "timezone": tz,
                "limit": limit,
                "offset": offset
            }
            data = await self.fetch_json("fixtures", params)
            resp = data.get("response", [])
            paging = data.get("paging", {})
            all_fixtures.extend(resp)

            total = paging.get("total", 0)
            logger.debug("Offset %d: fetched %d/%d", offset, len(all_fixtures), total)

            if len(all_fixtures) >= total or not resp:
                break
            offset += limit

        logger.info("Total NS fixtures fetched: %d", len(all_fixtures))

        # Filter berdasarkan liga
        filtered = [f for f in all_fixtures if f["league"]["id"] in LIGA_FILTER]
        logger.info("Fixtures after filtering: %d", len(filtered))

        # Tambahkan prediksi
        result = await self._attach_predictions(filtered)
        self.fixtures_cache[date] = result
        return result

    async def _attach_predictions(self, fixtures: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        tasks = [self._attach(f) for f in fixtures]
        return await asyncio.gather(*tasks)

    async def _attach(self, fixture: Dict[str, Any]) -> Dict[str, Any]:
        fid = fixture['fixture']['id']
        
        # Cek apakah prediksi untuk fixture ini sudah ada di cache
        if fid in self.fixture_prediction_cache:
            fixture['prediction'] = self.fixture_prediction_cache[fid]
            return fixture

        try:
            # Panggil API untuk ambil prediksi
            data = await self.fetch_json("predictions", {"fixture": fid})
            response = data.get('response', [])

            # Simpan hasil ke dalam fixture dan cache
            fixture['prediction'] = response        
            if response:
                self.fixture_prediction_cache[fid] = response

        except Exception as e:
            logger.warning("Failed prediction for %s: %s", fid, e)
            fixture['prediction'] = []

        return fixture
