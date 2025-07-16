import asyncio
import aiohttp
from typing import List, Dict, Any, Optional
import logging
from cachetools import TTLCache, cached
from datetime import datetime, date
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

class ApiSportsClient:
    """
    Asynchronous client for sports APIs with built-in caching and timezone-aware date handling.
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
        max_concurrency: int = 10,
    ):
        self.base_url = base_url.rstrip('/')
        self.headers = headers
        self.timezone = timezone or ZoneInfo('UTC')
        self.sem = asyncio.Semaphore(max_concurrency)
        # Cache for fixtures by ISO date string
        self.fixtures_cache: TTLCache = TTLCache(maxsize=max_fixtures_cache, ttl=fixtures_ttl)
        # Cache for predictions by fixture ID
        self.prediction_cache: TTLCache = TTLCache(maxsize=max_prediction_cache, ttl=prediction_ttl)
        self.session: Optional[aiohttp.ClientSession] = None

    async def init_session(self) -> None:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(headers=self.headers)
            logger.info("Initialized new aiohttp session")

    async def close(self) -> None:
        if self.session and not self.session.closed:
            await self.session.close()
            logger.info("Closed aiohttp session")

    async def fetch_json(self, path: str, params: Dict[str, Any]) -> Any:
        await self.init_session()
        url = f"{self.base_url}/{path.lstrip('/')}"
        async with self.sem:
            async with self.session.get(url, params=params) as resp:
                resp.raise_for_status()
                return await resp.json()

    def _format_date(self, dt: date) -> str:
        # Format date in ISO format, using timezone if needed
        return dt.strftime('%Y-%m-%d')

    async def get_fixtures(self, target_date: date) -> List[Dict[str, Any]]:
        """
        Fetch fixtures for a given date (timezone-aware) with caching.

        :param target_date: Date object for which to fetch fixtures.
        :return: List of fixtures with attached predictions.
        """
        date_str = self._format_date(target_date)

        if date_str in self.fixtures_cache:
            logger.debug("Cache hit for fixtures %s", date_str)
            return self.fixtures_cache[date_str]

        # Import league filter dynamically to avoid circular import
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

        # Attach predictions concurrently
        fixtures_with_preds = await self._attach_predictions(filtered)
        self.fixtures_cache[date_str] = fixtures_with_preds

        return fixtures_with_preds

    async def _attach_predictions(self, fixtures: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        tasks = [self._attach(f) for f in fixtures]
        return await asyncio.gather(*tasks)

    async def _attach(self, fixture: Dict[str, Any]) -> Dict[str, Any]:
        fid = fixture['fixture']['id']
        if fid in self.prediction_cache:
            fixture['prediction'] = self.prediction_cache[fid]
            logger.debug("Cache hit for prediction %s", fid)
            return fixture

        try:
            data = await self.fetch_json('predictions', {'fixture': fid})
            pred = data.get('response', [])
            fixture['prediction'] = pred
            # Only cache non-empty responses
            if pred:
                self.prediction_cache[fid] = pred
                logger.debug("Cached prediction for %s", fid)
        except Exception as e:
            logger.warning("Error fetching prediction for %s: %s", fid, e)
            fixture['prediction'] = []

        return fixture

    def clear_caches(self) -> None:
        """
        Clears both fixtures and predictions caches.
        """
        self.fixtures_cache.clear()
        self.prediction_cache.clear()
        logger.info("Cleared fixtures and prediction caches")

    def update_timezone(self, tz_str: str) -> None:
        """
        Update client timezone for future requests.
        :param tz_str: IANA timezone name (e.g., 'Asia/Jakarta')
        """
        self.timezone = ZoneInfo(tz_str)
        logger.info("Timezone updated to %s", tz_str)
