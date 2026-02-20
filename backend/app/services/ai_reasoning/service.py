"""AI Reasoning service — Groq (primary) + Gemini (fallback).

Provider-agnostic base class with two concrete implementations:
- GroqReasoningService:   Groq LPU, llama-3.1-8b-instant (~1.5s)
- GeminiReasoningService: Google Gemini, gemma-3-4b-it (~6s fallback)

Requirements: 1.1, 3.1, 3.2, 3.3, 3.4, 3.6, 3.7
- AI SHALL NOT generate coordinates, opening hours, or prices
- AI CAN suggest landmark NAMES which are then validated against real data
"""

import asyncio
import json
import logging
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

from dotenv import load_dotenv

from app.models import POI, Route
from app.services.place_validator import StructuredQuery
from app.utils.geo import haversine_distance

logger = logging.getLogger(__name__)

try:
    load_dotenv()
except Exception:
    pass  # Python 3.14+ compat

# ── System prompt: think like a local, suggest hidden gems ──
SYSTEM_PROMPT = (
    "You are a passionate local travel expert who has lived in cities around the world. "
    "Think like a local, not a tourist. You know the hidden gems — the quiet courtyard "
    "behind the cathedral, the tiny family-run trattoria that doesn't appear in guidebooks, "
    "the street art alley that only neighborhood residents know about. "
    "Mix iconic must-see landmarks with off-the-beaten-path spots that give travelers "
    "an authentic feel for the city. "
    "Respond ONLY with valid JSON. No explanations, no markdown, no extra text."
)


@dataclass
class RankedPOI:
    """A POI with relevance ranking information."""
    poi: POI
    relevance_score: float
    reasoning: str


@dataclass
class LandmarkSuggestion:
    """AI-suggested landmark (name only, no coordinates)."""
    name: str
    category: str
    why_visit: str
    visit_duration_hours: float = 1.0
    specialty: str = ""


class AIReasoningService(ABC):
    """Base class for AI reasoning services.

    All prompt construction, JSON parsing, and business logic lives here.
    Subclasses only implement ``_generate()`` for their specific API client.
    """

    _timeout: float

    @abstractmethod
    async def _generate(self, prompt: str, timeout: float | None = None) -> str:
        """Send prompt to the AI provider and return raw text."""
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable provider name for logging."""
        ...

    # ── Utilities ─────────────────────────────────────────────────────

    @staticmethod
    def _sanitize_input(text: str, max_length: int = 500) -> str:
        """Sanitize user input before passing to AI prompts.

        Strips control characters and limits length to prevent
        prompt injection and abuse.
        """
        # Remove control characters (keep newlines/tabs for readability)
        cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
        return cleaned[:max_length].strip()

    @staticmethod
    def _extract_json(text: str) -> str:
        if "```json" in text:
            return text.split("```json")[1].split("```")[0].strip()
        if "```" in text:
            return text.split("```")[1].split("```")[0].strip()
        return text

    @staticmethod
    def _normalize_landmark_name(name: str) -> str:
        if not name:
            return ""
        if name.startswith("The "):
            name = name[4:]
        if "(" in name:
            name = name.split("(")[0].strip()
        name = re.sub(r'([a-z])([A-Z])', r'\1 \2', name)
        name = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1 \2', name)
        return " ".join(name.split()).strip()

    @staticmethod
    def _get_suggestion_count(time_constraint: str | None) -> int:
        return {"6h": 10, "day": 18, "2days": 25, "3days": 35, "5days": 50}.get(
            time_constraint, 18
        )

    @staticmethod
    def _get_fallback_landmarks(city: str) -> list[LandmarkSuggestion]:
        return [
            LandmarkSuggestion(f"{city} Cathedral", "church", "Historic cathedral"),
            LandmarkSuggestion(f"{city} Castle", "landmark", "Historic castle", 1.5),
            LandmarkSuggestion(f"Old Town {city}", "landmark", "Historic old town", 2.0),
            LandmarkSuggestion(f"{city} City Hall", "landmark", "Historic city hall", 0.5),
            LandmarkSuggestion(f"{city} Main Square", "square", "Central square", 0.5),
            LandmarkSuggestion(f"{city} Museum", "museum", "City museum", 1.5),
            LandmarkSuggestion(f"{city} Park", "park", "City park"),
            LandmarkSuggestion(f"{city} Market", "market", "Local market"),
        ]

    # ── Shared implementations ────────────────────────────────────────

    async def interpret_user_input(
        self, location: str, interests: list[str] | None
    ) -> StructuredQuery:
        location = self._sanitize_input(location, max_length=200)
        interests_str = ", ".join(
            self._sanitize_input(i, max_length=50) for i in interests
        ) if interests else "general sightseeing"
        prompt = (
            f'Parse this travel request into a structured query.\n\n'
            f'User\'s location input: "{location}"\n'
            f'User\'s interests: {interests_str}\n\n'
            f'Respond ONLY with valid JSON:\n'
            f'{{"city": "city name", "area": "neighborhood or null", '
            f'"poi_types": ["types"], "keywords": ["keywords"]}}\n\n'
            f'Rules:\n- Extract city name from location\n'
            f'- Include area/neighborhood if mentioned\n'
            f'- Suggest POI types based on interests\n'
            f'- Do NOT include coordinates or addresses'
        )
        try:
            text = await self._generate(prompt)
            data = json.loads(self._extract_json(text))
            return StructuredQuery(
                city=data.get("city", location),
                area=data.get("area"),
                poi_types=data.get("poi_types", []),
                keywords=data.get("keywords", []),
            )
        except Exception:
            return StructuredQuery(city=location, keywords=interests or [])

    async def suggest_landmarks(
        self,
        city: str,
        interests: list[str] | None,
        transport_mode: str = "walking",
        time_constraint: str | None = None,
    ) -> list[LandmarkSuggestion]:
        city = self._sanitize_input(city, max_length=100)
        interests_str = ", ".join(
            self._sanitize_input(i, max_length=50) for i in interests
        ) if interests else "sightseeing, landmarks, culture"
        n = self._get_suggestion_count(time_constraint)

        prompt = (
            f"Suggest {n} places to visit in {city}.\n\n"
            f"Interests: {interests_str}\nTransport: {transport_mode}\n\n"
            f"Mix famous landmarks with hidden gems that only locals know about.\n"
            f"Include at least 30% lesser-known spots (quiet courtyards, "
            f"local-favorite viewpoints, neighborhood secrets).\n\n"
            f"Return ONLY a JSON array:\n"
            f'[{{"name": "Place Name", "category": "landmark|church|museum|park|'
            f'palace|square|market|viewpoint|hidden_gem", "why_visit": "One sentence", '
            f'"visit_duration_hours": 1.5}}]\n\n'
            f"Rules:\n- Only places WITHIN {city} city limits\n"
            f"- Use simple, searchable names (no \"The\", no parentheses)\n"
            f"- Start with most famous, then weave in hidden gems\n"
            f"- No coordinates or addresses"
        )

        try:
            text = await self._generate(prompt, timeout=20.0)
            data = json.loads(self._extract_json(text))
            suggestions: list[LandmarkSuggestion] = []
            seen: set[str] = set()
            for item in data[:n]:
                name = self._normalize_landmark_name(item.get("name", "").strip())
                if not name or name.lower() in seen:
                    continue
                try:
                    dur = float(item.get("visit_duration_hours", 1.0))
                except (ValueError, TypeError):
                    dur = 1.0
                suggestions.append(LandmarkSuggestion(
                    name=name,
                    category=item.get("category", "attraction"),
                    why_visit=item.get("why_visit", ""),
                    visit_duration_hours=dur,
                ))
                seen.add(name.lower())
            logger.info(f"[{self.provider_name}] Got {len(suggestions)} landmark suggestions")
            return suggestions
        except asyncio.TimeoutError:
            logger.info(f"[{self.provider_name}] Timeout getting landmarks for {city}")
            return self._get_fallback_landmarks(city)
        except Exception as e:
            logger.info(f"[{self.provider_name}] Landmark suggestion error: {e}")
            return self._get_fallback_landmarks(city)

    async def rank_pois(self, pois: list[POI], interests: list[str]) -> list[RankedPOI]:
        if not pois:
            return []
        if not interests:
            return [RankedPOI(p, 0.5, "No interests") for p in pois]

        summaries = [f"{i}: {p.name} ({', '.join(p.types or [])})" for i, p in enumerate(pois)]
        prompt = (
            f"Rank places by relevance to interests: {', '.join(interests)}\n\n"
            f"Places:\n{chr(10).join(summaries)}\n\n"
            f'Respond with JSON array: [{{"index": 0, "score": 0.8, "reasoning": "why"}}]\n'
            f"Score 0-1, higher = more relevant."
        )
        try:
            text = await self._generate(prompt)
            rankings = json.loads(self._extract_json(text))
            ranked = []
            for item in rankings:
                idx = item.get("index", 0)
                if 0 <= idx < len(pois):
                    ranked.append(RankedPOI(
                        pois[idx],
                        min(1.0, max(0.0, float(item.get("score", 0.5)))),
                        item.get("reasoning", ""),
                    ))
            ranked_indices = {item.get("index") for item in rankings}
            for i, poi in enumerate(pois):
                if i not in ranked_indices:
                    ranked.append(RankedPOI(poi, 0.5, "Not evaluated"))
            ranked.sort(key=lambda x: x.relevance_score, reverse=True)
            return ranked
        except Exception:
            return [RankedPOI(p, 0.5, "Unavailable") for p in pois]

    async def cluster_nearby_pois(self, pois: list[POI]) -> list[list[POI]]:
        if not pois:
            return []
        if len(pois) == 1:
            return [pois]
        clusters: list[list[POI]] = []
        assigned: set[int] = set()
        for i, poi in enumerate(pois):
            if i in assigned:
                continue
            cluster = [poi]
            assigned.add(i)
            for j, other in enumerate(pois):
                if j in assigned:
                    continue
                if haversine_distance(
                    poi.coordinates.lat, poi.coordinates.lng,
                    other.coordinates.lat, other.coordinates.lng,
                ) <= 1.0:
                    cluster.append(other)
                    assigned.add(j)
            clusters.append(cluster)
        return clusters

    async def explain_route(self, route: Route) -> str:
        if not route.ordered_pois:
            return "No places in this route."
        stops = [f"{i}. {p.name}" for i, p in enumerate(route.ordered_pois, 1)]
        km = route.total_distance / 1000
        mins = route.total_duration // 60
        prompt = (
            f"Write 2-3 sentences explaining this {route.transport_mode.value} route:\n"
            f"{chr(10).join(stops)}\nDistance: {km:.1f}km, Time: {mins}min\n\n"
            f"Be friendly and helpful. No specific times or prices."
        )
        try:
            return await self._generate(prompt)
        except Exception:
            return f"This {route.transport_mode.value} route covers {len(route.ordered_pois)} stops over {km:.1f}km (~{mins} min)."

    async def suggest_food_and_drinks(
        self, city: str, category: str = "cafes", limit: int = 10,
    ) -> list[LandmarkSuggestion]:
        city = self._sanitize_input(city, max_length=100)
        key = category if category in ("cafes", "restaurants", "bars", "parks") else "cafes"
        prompts = {
            "cafes": (
                f"Suggest {limit} FAMOUS historic cafes in {city} that tourists should visit.\n\n"
                f"Return ONLY a JSON array:\n"
                f'[{{"name": "Exact Cafe Name", "category": "cafe", "why_visit": "One sentence", '
                f'"visit_duration_hours": 0.75, "specialty": "What to order"}}]\n\n'
                f"RULES: Only ICONIC/HISTORIC cafes from travel guides. EXACT official names. "
                f"NO chains. NO closed places. WITHIN {city} city limits."
            ),
            "restaurants": (
                f"Suggest {limit} FAMOUS restaurants in {city} known for local cuisine.\n\n"
                f"Return ONLY a JSON array:\n"
                f'[{{"name": "Exact Restaurant Name", "category": "restaurant", "why_visit": "One sentence", '
                f'"visit_duration_hours": 1.5, "specialty": "Signature dish"}}]\n\n'
                f"RULES: Only ICONIC restaurants locals and tourists love. EXACT official names. "
                f"NO chains. NO closed places. WITHIN {city} city limits."
            ),
            "bars": (
                f"Suggest {limit} FAMOUS historic bars/pubs in {city}.\n\n"
                f"Return ONLY a JSON array:\n"
                f'[{{"name": "Exact Bar Name", "category": "bar", "why_visit": "One sentence", '
                f'"visit_duration_hours": 1.0, "specialty": "Signature drink"}}]\n\n'
                f"RULES: Only ICONIC/HISTORIC bars from travel guides. EXACT official names. "
                f"NO chains. NO closed places. WITHIN {city} city limits."
            ),
            "parks": (
                f"Suggest {limit} FAMOUS parks and gardens in {city}.\n\n"
                f"Return ONLY a JSON array:\n"
                f'[{{"name": "Exact Park Name", "category": "park", "why_visit": "One sentence", '
                f'"visit_duration_hours": 1.5, "specialty": "Best feature"}}]\n\n'
                f"RULES: Only NOTABLE parks. EXACT official names. WITHIN {city} city limits."
            ),
        }
        prompt = prompts[key]
        logger.info(f"[{self.provider_name}] Suggesting {key} for {city}")
        try:
            text = await self._generate(prompt, timeout=15.0)
            data = json.loads(self._extract_json(text))
            suggestions: list[LandmarkSuggestion] = []
            seen: set[str] = set()
            for item in data[:limit]:
                name = self._normalize_landmark_name(item.get("name", "").strip())
                if not name or name.lower() in seen:
                    continue
                try:
                    dur = float(item.get("visit_duration_hours", 1.0))
                except (ValueError, TypeError):
                    dur = 1.0
                suggestions.append(LandmarkSuggestion(
                    name=name,
                    category=item.get("category", category),
                    why_visit=item.get("why_visit", ""),
                    visit_duration_hours=dur,
                    specialty=item.get("specialty", ""),
                ))
                seen.add(name.lower())
            logger.info(f"[{self.provider_name}] Got {len(suggestions)} {key} suggestions for {city}")
            return suggestions
        except asyncio.TimeoutError:
            logger.info(f"[{self.provider_name}] Timeout getting {key} for {city}")
            return []
        except Exception as e:
            logger.info(f"[{self.provider_name}] Error getting {key} suggestions: {e}")
            return []


# ═══════════════════════════════════════════════════════════════════════
# Provider: Groq  (primary — fast LPU inference, ~1.5s)
# ═══════════════════════════════════════════════════════════════════════

class GroqReasoningService(AIReasoningService):
    """Groq LPU with Llama 3.1 8B Instant."""

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str | None = None,
        timeout_seconds: float = 15.0,
    ) -> None:
        from groq import AsyncGroq

        self._api_key = api_key or os.getenv("GROQ_API_KEY")
        if not self._api_key:
            raise ValueError("GROQ_API_KEY not provided")
        self._client = AsyncGroq(api_key=self._api_key)
        self._model_name = model_name or os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
        self._timeout = timeout_seconds
        logger.info(f"[AI] Groq ready: {self._model_name}")

    @property
    def provider_name(self) -> str:
        return "Groq"

    async def _generate(self, prompt: str, timeout: float | None = None) -> str:
        t = timeout or self._timeout
        try:
            resp = await asyncio.wait_for(
                self._client.chat.completions.create(
                    model=self._model_name,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.3,
                    max_tokens=4096,
                ),
                timeout=t,
            )
            return (resp.choices[0].message.content or "").strip()
        except asyncio.TimeoutError:
            logger.warning(f"[Groq] Timeout after {t}s")
            raise
        except Exception as e:
            logger.warning(f"[Groq] Error: {e}")
            raise


# ═══════════════════════════════════════════════════════════════════════
# Provider: Gemini  (fallback — reliable, ~6s)
# ═══════════════════════════════════════════════════════════════════════

class GeminiReasoningService(AIReasoningService):
    """Google Gemini with Gemma 3 4B."""

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        from google import genai

        self._api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self._api_key:
            raise ValueError("GEMINI_API_KEY not provided")
        self._client = genai.Client(api_key=self._api_key)
        self._model_name = model_name or os.getenv("GEMINI_MODEL", "gemma-3-4b-it")
        self._timeout = timeout_seconds
        logger.info(f"[AI] Gemini ready: {self._model_name}")

    @property
    def provider_name(self) -> str:
        return "Gemini"

    async def _generate(self, prompt: str, timeout: float | None = None) -> str:
        t = timeout or self._timeout
        try:
            # Prepend system prompt so Gemini gets the same "think like a local" context as Groq
            full_prompt = f"{SYSTEM_PROMPT}\n\n{prompt}"
            resp = await asyncio.wait_for(
                self._client.aio.models.generate_content(
                    model=self._model_name,
                    contents=full_prompt,
                ),
                timeout=t,
            )
            return (resp.text or "").strip()
        except asyncio.TimeoutError:
            logger.warning(f"[Gemini] Timeout after {t}s")
            raise
        except Exception as e:
            logger.warning(f"[Gemini] Error: {e}")
            raise


# ═══════════════════════════════════════════════════════════════════════
# Factory: Groq → Gemini
# ═══════════════════════════════════════════════════════════════════════

def create_ai_service() -> AIReasoningService:
    """Create the best available AI service.  Groq first, Gemini fallback."""
    if os.getenv("GROQ_API_KEY"):
        try:
            return GroqReasoningService()
        except Exception as e:
            logger.info(f"[AI] Groq init failed: {e}")

    if os.getenv("GEMINI_API_KEY"):
        try:
            return GeminiReasoningService()
        except Exception as e:
            logger.info(f"[AI] Gemini init failed: {e}")

    raise ValueError("No AI provider available. Set GROQ_API_KEY or GEMINI_API_KEY in .env")
