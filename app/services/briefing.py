"""Morning briefing service - gathers weather, news, exchange rates, and a motivational quote."""
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from app.config import get_settings
from app.services.gemini import get_gemini

logger = logging.getLogger(__name__)

BERLIN_TZ = ZoneInfo("Europe/Berlin")


async def _get_weather() -> str:
    """Fetch weather for Falkensee, DE from OpenWeatherMap."""
    settings = get_settings()
    if not settings.openweather_api_key:
        return "Weather: unavailable"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.openweathermap.org/data/2.5/weather",
                params={
                    "q": "Falkensee,DE",
                    "appid": settings.openweather_api_key,
                    "units": "metric",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        temp = round(data["main"]["temp"])
        condition = data["weather"][0]["description"]
        humidity = data["main"]["humidity"]
        wind_kmh = round(data["wind"]["speed"] * 3.6)

        return (
            f"🌤️ Weather: Falkensee\n"
            f"{temp}°C, {condition}, humidity {humidity}%, wind {wind_kmh} km/h"
        )
    except Exception as e:
        logger.error(f"Weather fetch failed: {e}")
        return "Weather: unavailable"


async def _get_news() -> str:
    """Fetch top 3 German headlines from NewsAPI."""
    settings = get_settings()
    if not settings.newsapi_key:
        return "News: unavailable"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://newsapi.org/v2/top-headlines",
                params={
                    "country": "de",
                    "pageSize": 3,
                    "apiKey": settings.newsapi_key,
                },
            )
            resp.raise_for_status()
            articles = resp.json().get("articles", [])

        if not articles:
            return "News: no headlines available"

        lines = ["📰 Headlines"]
        for article in articles[:3]:
            lines.append(f"• {article['title']}")
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"News fetch failed: {e}")
        return "News: unavailable"


async def _get_exchange_rates() -> str:
    """Fetch EUR exchange rates from frankfurter.app."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.frankfurter.app/latest",
                params={"from": "EUR", "to": "USD,ILS,SEK"},
            )
            resp.raise_for_status()
            rates = resp.json().get("rates", {})

        usd = round(rates.get("USD", 0), 2)
        ils = round(rates.get("ILS", 0), 2)
        sek = round(rates.get("SEK", 0), 2)

        return f"💱 Exchange Rates\nEUR→USD: {usd} | EUR→ILS: {ils} | EUR→SEK: {sek}"
    except Exception as e:
        logger.error(f"Exchange rates fetch failed: {e}")
        return "Exchange rates: unavailable"


async def _get_motivation() -> str:
    """Get a personal, witty morning one-liner from the AI model."""
    now = datetime.now(BERLIN_TZ)
    day_name = now.strftime("%A")

    try:
        gemini = get_gemini()
        response, _ = await gemini.chat(
            f"It's {day_name} morning. Generate a short, witty, personal motivational "
            f"one-liner for Itzik to start his day. Be warm and funny — like a friend "
            f"texting him, not a fortune cookie. Reference the day of the week if it's "
            f"relevant (e.g. Monday blues, Friday energy, mid-week grind). "
            f"Just the line, no quotes, no attribution, max 15 words."
        )
        return f"💪 {response.strip()}"
    except Exception as e:
        logger.error(f"Motivation fetch failed: {e}")
        return "💪 Make today count!"


async def get_morning_briefing() -> str:
    """Assemble the full morning briefing message."""
    now = datetime.now(BERLIN_TZ)
    day_name = now.strftime("%A")
    date_str = now.strftime("%B %-d, %Y")

    header = f"🌅 Good morning Itzik! — {day_name}, {date_str}"

    weather = await _get_weather()
    news = await _get_news()
    rates = await _get_exchange_rates()
    motivation = await _get_motivation()

    parts = [header, "", weather, "", news, "", rates, "", motivation]
    return "\n".join(parts)
