import asyncio
import aiohttp
from typing import List, Dict, Any
import logging
from cachetools import TTLCache

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

class ApiSportsClient:
    def __init__(self, base_url: str, headers: Dict[str, str]):
        self.base_url = base_url.rstrip("/")
        self.headers = headers
        self.session: aiohttp.ClientSession | None = None
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
                result = await resp.json()
                logger.debug("GET %s params=%s → %s", url, params, result)
                return result

    async def get_fixtures(self, date: str) -> List[Dict[str, Any]]:
        from main import LIGA_FILTER, TZ
        if date in self.fixtures_cache:
            logger.info("Returning cached fixtures for %s", date)
            return self.fixtures_cache[date]

        all_fixtures: List[Dict[str, Any]] = []
        limit, offset = 50, 0
        tz_str = getattr(TZ, "zone", str(TZ))

        while True:
            params = {
                "date": date,
                "status": "NS",
                "timezone": tz_str,
                "limit": limit,
                "offset": offset
            }
            data = await self.fetch_json("fixtures", params)
            resp = data.get("response", [])
            paging = data.get("paging", {})
            all_fixtures.extend(resp)

            total = paging.get("total", 0)
            logger.info("Fetched %d/%d fixtures (offset %d)", len(all_fixtures), total, offset)
            if not resp or len(all_fixtures) >= total:
                break
            offset += limit

        logger.info("Total NS fixtures fetched: %d", len(all_fixtures))
        # Debug daftar sebelum filter
        for f in all_fixtures:
            logger.debug(" Fixture id=%s, league=%s", f["fixture"]["id"], f["league"]["id"])

        filtered = [f for f in all_fixtures if f["league"]["id"] in LIGA_FILTER]
        logger.info("Fixtures after LIGA_FILTER (%s): %d", LIGA_FILTER, len(filtered))

        result = await self._attach_predictions(filtered)
        self.fixtures_cache[date] = result
        return result

    async def _attach_predictions(self, fixtures: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return await asyncio.gather(*(self._attach(f) for f in fixtures))

    async def _attach(self, fixture: Dict[str, Any]) -> Dict[str, Any]:
        fid = fixture['fixture']['id']
        if fid in self.fixture_prediction_cache:
            logger.debug("Using cached prediction for fixture %s", fid)
            fixture['prediction'] = self.fixture_prediction_cache[fid]
            return fixture

        try:
            data = await self.fetch_json("predictions", {"fixture": fid})
            logger.debug("Raw prediction data for %s: %s", fid, data)
            response = data.get('response', [])
            fixture['prediction'] = response or []
            if response:
                self.fixture_prediction_cache[fid] = response
            else:
                logger.warning("Empty prediction list for fixture %s", fid)
        except Exception as e:
            logger.warning("Failed fetching prediction for %s: %s", fid, e)
            fixture['prediction'] = []

        return fixture
