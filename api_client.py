import asyncio
import aiohttp
from typing import List, Dict, Any, Optional
import logging
from cachetools import TTLCache
from datetime import date
from zoneinfo import ZoneInfo
import json
import os

logger = logging.getLogger(__name__)

class ApiSportsClient:
    """
    Asynchronous client for sports APIs with caching (memory + persistent file) 
    and timezone-aware date handling. Optimized for low daily request limits.
    """
    def __init__(
        self,
        base_url: str,
        headers: Dict[str, str],
        timezone: Optional[ZoneInfo] = None,
        max_fixtures_cache: int = 1000,
        fixtures_ttl: int = 6 * 3600,
        max_prediction_cache: int = 500,
        prediction_ttl: int = 3600,
        cache_file: str = "api_cache.json"
    ):
        self.base_url = base_url.rstrip('/')
        self.headers = headers
        self.timezone = timezone or ZoneInfo('UTC')

        # In-memory cache
        self.fixtures_cache: TTLCache = TTLCache(maxsize=max_fixtures_cache, ttl=fixtures_ttl)
        self.prediction_cache: TTLCache = TTLCache(maxsize=max_prediction_cache, ttl=prediction_ttl)

        # Persistent cache
        self.cache_file = cache_file
        self.persistent_cache = self._load_cache_file()

        self.session: Optional[aiohttp.ClientSession] = None

    def _load_cache_file(self) -> Dict[str, Any]:
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    logger.info("Loaded persistent cache from %s", self.cache_file)
                    return json.load(f)
            except Exception as e:
                logger.warning("Failed to load cache file: %s", e)
        return {"fixtures": {}, "predictions": {}}

    def _save_cache_file(self) -> None:
        try:
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self.persistent_cache, f, ensure_ascii=False, indent=2)
            logger.debug("Saved persistent cache to %s", self.cache_file)
        except Exception as e:
            logger.warning("Failed to save cache file: %s", e)

    async def init_session(self) -> None:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(headers=self.headers)
            logger.info("Initialized new aiohttp session")

    async def close(self) -> None:
        if self.session and not self.session.closed:
            await self.session.close()
            logger.info("Closed aiohttp session")
        self._save_cache_file()  # Save cache on close

    async def fetch_json(self, path: str, params: Dict[str, Any]) -> Any:
        await self.init_session()
        url = f"{self.base_url}/{path.lstrip('/')}"
        async with self.session.get(url, params=params) as resp:
            resp.raise_for_status()
            return await resp.json()

    def _format_date(self, dt: date) -> str:
        return dt.strftime('%Y-%m-%d')

    async def get_fixtures(self, target_date: date) -> List[Dict[str, Any]]:
        if not isinstance(target_date, date):
            raise TypeError(f"Expected datetime.date, got {type(target_date)}")

        date_str = self._format_date(target_date)

        # Check persistent cache first
        if date_str in self.persistent_cache["fixtures"]:
            logger.debug("Persistent cache hit for fixtures %s", date_str)
            return self.persistent_cache["fixtures"][date_str]

        # Check in-memory cache
        if date_str in self.fixtures_cache:
            logger.debug("Memory cache hit for fixtures %s", date_str)
            return self.fixtures_cache[date_str]

        from main import LIGA_FILTER  # noqa: F401

        payload = {
            'date': date_str,
            'status': 'NS',
            'timezone': str(self.timezone)
        }
        data = await self.fetch_json('fixtures', payload)
        raw = data.get('response', [])
        filtered = [f for f in raw if f['league']['id'] in LIGA_FILTER]
        logger.info("Fetched %d fixtures, %d after filter", len(raw), len(filtered))

        fixtures_with_preds = await self._attach_predictions(filtered)

        # Save to cache
        self.fixtures_cache[date_str] = fixtures_with_preds
        self.persistent_cache["fixtures"][date_str] = fixtures_with_preds
        self._save_cache_file()

        return fixtures_with_preds

    async def _attach_predictions(self, fixtures: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        tasks = [self._attach(f) for f in fixtures]
        return await asyncio.gather(*tasks)

    async def _attach(self, fixture: Dict[str, Any]) -> Dict[str, Any]:
        fid = str(fixture['fixture']['id'])

        # Check persistent cache first
        if fid in self.persistent_cache["predictions"]:
            fixture['prediction'] = self.persistent_cache["predictions"][fid]
            logger.debug("Persistent cache hit for prediction %s", fid)
            return fixture

        # Check in-memory cache
        if fid in self.prediction_cache:
            fixture['prediction'] = self.prediction_cache[fid]
            logger.debug("Memory cache hit for prediction %s", fid)
            return fixture

        try:
            data = await self.fetch_json('predictions', {'fixture': fid})
            pred = data.get('response', [])
            fixture['prediction'] = pred

            # Only cache non-empty responses
            if pred:
                self.prediction_cache[fid] = pred
                self.persistent_cache["predictions"][fid] = pred
                self._save_cache_file()
                logger.debug("Cached prediction for %s", fid)
        except Exception as e:
            logger.warning("Error fetching prediction for %s: %s", fid, e)
            fixture['prediction'] = []

        return fixture

    def clear_caches(self) -> None:
        self.fixtures_cache.clear()
        self.prediction_cache.clear()
        self.persistent_cache = {"fixtures": {}, "predictions": {}}
        self._save_cache_file()
        logger.info("Cleared fixtures and prediction caches")

    def update_timezone(self, tz_str: str) -> None:
        self.timezone = ZoneInfo(tz_str)
        logger.info("Timezone updated to %s", tz_str)
