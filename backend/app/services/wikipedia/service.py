"""Wikipedia/Wikimedia API service for free POI images and descriptions.

Provides images from Wikipedia and Wikimedia Commons (completely free, 90M+ images).
No API key required.

Architecture:
- Shared httpx client with connection pooling (singleton pattern)
- Semaphore-based rate limiting (max 3 concurrent requests)
- Retry with backoff on transient failures
- Fallback: Wikipedia → Commons → REST API summary image
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional
import httpx

logger = logging.getLogger(__name__)


@dataclass
class WikipediaPlace:
    """Place data enriched from Wikipedia/Wikimedia."""
    title: str
    description: Optional[str] = None
    image_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    wikipedia_url: Optional[str] = None


class WikipediaService:
    """Wikipedia/Wikimedia API client for POI enrichment.

    Uses a shared httpx client with connection pooling.
    Semaphore limits concurrent requests to avoid rate-limiting.
    Retry logic handles transient failures.
    """

    WIKIPEDIA_ACTION_API = "https://en.wikipedia.org/w/api.php"
    WIKIPEDIA_REST_API = "https://en.wikipedia.org/api/rest_v1/page/summary"
    COMMONS_API = "https://commons.wikimedia.org/w/api.php"

    HEADERS = {
        "User-Agent": "CityWalker/1.0 (https://citywalker.app; contact@citywalker.app)",
        "Accept": "application/json",
    }

    def __init__(self) -> None:
        self._timeout = 8.0
        self._client: httpx.AsyncClient | None = None
        # Max 3 concurrent requests to Wikipedia/Commons
        self._semaphore = asyncio.Semaphore(3)

    def _get_client(self) -> httpx.AsyncClient:
        """Get or create the shared HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self._timeout,
                headers=self.HEADERS,
                limits=httpx.Limits(max_connections=8, max_keepalive_connections=4),
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def _request_with_retry(
        self, client: httpx.AsyncClient, url: str, params: dict, max_retries: int = 1
    ) -> dict | None:
        """Make a GET request with retry on transient failures.
        
        Only 1 retry to avoid long hangs when Wikipedia is unreachable.
        """
        for attempt in range(max_retries + 1):
            try:
                async with self._semaphore:
                    response = await client.get(url, params=params)
                    response.raise_for_status()
                    return response.json()
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                if attempt < max_retries:
                    wait = 1.5
                    logger.info(f"[WIKI] Retry {attempt+1}/{max_retries} for {params.get('gsrsearch', url)}: {type(e).__name__}")
                    await asyncio.sleep(wait)
                else:
                    # Don't log every failure — just return None quickly
                    return None
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429 and attempt < max_retries:
                    await asyncio.sleep(2.0)
                else:
                    return None
            except Exception:
                return None
        return None

    async def get_images_for_landmark(self, name: str, city: str, count: int = 3) -> list[str]:
        """Get multiple images for a landmark.

        Pipeline (parallel where possible):
        1. Wikipedia Action API (page thumbnail)
        2. Wikimedia Commons (multiple images)
        3. Fallback: Wikipedia REST API (summary image) — if both above fail
        """
        client = self._get_client()
        images: list[str] = []

        try:
            # Stage 1: Wikipedia + Commons in parallel
            wiki_task = self._get_wikipedia_image(client, name, city)
            commons_task = self._get_commons_images(client, name, city, count)

            results = await asyncio.gather(wiki_task, commons_task, return_exceptions=True)
            wiki_image = results[0] if isinstance(results[0], str) else None
            commons_images = results[1] if isinstance(results[1], list) else []

            if wiki_image:
                images.append(wiki_image)

            for img in commons_images:
                if img and img not in images and len(images) < count:
                    images.append(img)

            # Stage 2: Fallback to REST API if we got nothing
            if len(images) == 0:
                rest_image = await self._get_rest_api_image(client, name, city)
                if rest_image:
                    images.append(rest_image)

            logger.info(f"[WIKI] {name}: {len(images)} images found")
            return images[:count]

        except Exception as e:
            logger.info(f"[WIKI] {name}: pipeline error: {type(e).__name__}: {e}")
            return images

    async def _get_wikipedia_image(self, client: httpx.AsyncClient, name: str, city: str) -> Optional[str]:
        """Get main image from Wikipedia Action API."""
        params = {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": f"{name} {city}",
            "gsrlimit": 1,
            "prop": "pageimages",
            "piprop": "thumbnail",
            "pithumbsize": 800,
        }

        data = await self._request_with_retry(client, self.WIKIPEDIA_ACTION_API, params)
        if not data:
            return None

        pages = data.get("query", {}).get("pages", {})
        if pages:
            page = next(iter(pages.values()))
            thumb = page.get("thumbnail", {})
            if thumb.get("source"):
                return thumb["source"]
        return None

    async def _get_commons_images(self, client: httpx.AsyncClient, name: str, city: str, count: int) -> list[str]:
        """Get images from Wikimedia Commons."""
        params = {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": f"{name} {city}",
            "gsrnamespace": 6,  # File namespace
            "gsrlimit": count + 3,  # Extra to filter
            "prop": "imageinfo",
            "iiprop": "url|mime",
            "iiurlwidth": 800,
        }

        data = await self._request_with_retry(client, self.COMMONS_API, params)
        if not data:
            return []

        images: list[str] = []
        pages = data.get("query", {}).get("pages", {})
        if pages:
            for page in pages.values():
                imageinfo = page.get("imageinfo", [{}])[0]
                mime = imageinfo.get("mime", "")
                if mime.startswith("image/") and "svg" not in mime:
                    url = imageinfo.get("thumburl") or imageinfo.get("url")
                    if url and url not in images:
                        images.append(url)
                        if len(images) >= count:
                            break
        return images

    async def _get_rest_api_image(self, client: httpx.AsyncClient, name: str, city: str) -> Optional[str]:
        """Fallback: Get image from Wikipedia REST API (page summary).

        This is a different endpoint that sometimes works when the Action API fails.
        Tries multiple query variations.
        """
        queries = [name, f"{name} ({city})", f"{name} {city}"]

        for query in queries:
            try:
                url = f"{self.WIKIPEDIA_REST_API}/{query.replace(' ', '_')}"
                async with self._semaphore:
                    response = await client.get(url)
                    if response.status_code == 200:
                        data = response.json()
                        # Try thumbnail first (resized), then original
                        thumb = data.get("thumbnail", {}).get("source")
                        if thumb:
                            # Upscale thumbnail to 800px
                            return thumb.replace("/50px-", "/800px-").replace("/60px-", "/800px-")
                        original = data.get("originalimage", {}).get("source")
                        if original:
                            return original
            except Exception:
                continue
        return None

    async def get_image_for_landmark(self, name: str, city: str) -> Optional[str]:
        """Quick method to get a single image URL."""
        images = await self.get_images_for_landmark(name, city, count=1)
        return images[0] if images else None

    async def search_place(self, name: str, city: str) -> Optional[WikipediaPlace]:
        """Search Wikipedia for a place and get its image + description."""
        client = self._get_client()
        params = {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": f"{name} {city}",
            "gsrlimit": 1,
            "prop": "pageimages|extracts|info",
            "piprop": "thumbnail",
            "pithumbsize": 800,
            "exintro": True,
            "explaintext": True,
            "exsentences": 2,
            "inprop": "url",
        }

        data = await self._request_with_retry(client, self.WIKIPEDIA_ACTION_API, params)
        if not data:
            return None

        pages = data.get("query", {}).get("pages", {})
        if not pages:
            return None

        page = next(iter(pages.values()))
        if page.get("missing"):
            return None

        thumbnail_url = page.get("thumbnail", {}).get("source")

        return WikipediaPlace(
            title=page.get("title", name),
            description=page.get("extract"),
            image_url=thumbnail_url,
            thumbnail_url=thumbnail_url,
            wikipedia_url=page.get("fullurl"),
        )
