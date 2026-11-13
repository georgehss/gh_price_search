import json
import random
import re
import urllib.parse
from typing import List, Optional
import requests
from bs4 import BeautifulSoup
from src.config import Config
from src.scrapers.base import ProductOffer, USER_AGENTS, parse_br_price


class _MosaicoComparatorBase:
    """Base compartilhada para comparadores da família Mosaico (Buscapé, Zoom, Bondfaro)."""

    BASE_URL: str = ""
    SEARCH_URL: str = ""
    DEFAULT_STORE: str = ""
    SOURCE_KEY: str = ""
    last_status: str = "ok"

    @classmethod
    def search(cls, query: str, limit: int = 15) -> List[ProductOffer]:
        offers: List[ProductOffer] = []
        cls.last_status = "ok"
        if not query:
            return offers

        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8",
        }

        try:
            resp = requests.get(cls.SEARCH_URL, params={"q": query}, headers=headers, timeout=12)
            if resp.status_code != 200:
                cls.last_status = f"http_{resp.status_code}"
                return offers

            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.select("[data-testid='product-card'], div[class*='SearchCard_ProductCard']")
            for card in cards[:limit]:
                title_elem = card.select_one("[data-testid='product-card::name'], h2")
                price_elem = card.select_one("[data-testid='product-card::price'], [class*='Price_Value']")
                link_elem = card.select_one("a")

                if not (title_elem and price_elem):
                    continue

                title = title_elem.get_text(strip=True)
                price = parse_br_price(price_elem.get_text(strip=True))
                if price <= 0:
                    continue

                link = ""
                if link_elem and "href" in link_elem.attrs:
                    href = link_elem["href"]
                    link = f"{cls.BASE_URL}{href}" if href.startswith("/") else href

                store = cls.DEFAULT_STORE
                via_el = card.find(string=re.compile(r"Via\s+", re.IGNORECASE))
                if via_el:
                    store_name = via_el.strip().replace("Via ", "").strip()
                    if store_name:
                        store = store_name
                else:
                    multi_store = card.find(string=re.compile(r"Compare em\s+\d+\s+lojas", re.IGNORECASE))
                    if multi_store:
                        store = f"{cls.DEFAULT_STORE} ({multi_store.strip()})"

                img_elem = card.select_one("img")
                img_url = img_elem.get("src") if img_elem else None

                installments = None
                inst_el = card.find(string=re.compile(r"\d+x de\s+R\$", re.IGNORECASE))
                if inst_el:
                    installments = inst_el.strip()

                offers.append(
                    ProductOffer(
                        title=title,
                        price=price,
                        store=store,
                        link=link,
                        image_url=img_url,
                        installments=installments,
                        source=cls.SOURCE_KEY,
                    )
                )
        except Exception:
            cls.last_status = "error"

        return offers


class BuscapeScraper(_MosaicoComparatorBase):
    """Scraper robusto para Buscapé com extração de loja real, fotos e parcelamento."""
    BASE_URL = "https://www.buscape.com.br"
    SEARCH_URL = "https://www.buscape.com.br/search"
    DEFAULT_STORE = "Buscapé"
    SOURCE_KEY = "buscape"


class ZoomScraper(_MosaicoComparatorBase):
    """Scraper complementar para o comparador Zoom."""
    BASE_URL = "https://www.zoom.com.br"
    SEARCH_URL = "https://www.zoom.com.br/search"
    DEFAULT_STORE = "Zoom"
    SOURCE_KEY = "zoom"


class BondfaroScraper(_MosaicoComparatorBase):
    """Scraper complementar para o comparador Bondfaro."""
    BASE_URL = "https://www.bondfaro.com.br"
    SEARCH_URL = "https://www.bondfaro.com.br/search"
    DEFAULT_STORE = "Bondfaro"
    SOURCE_KEY = "bondfaro"


# Compatibilidade retroativa
ZoomBuscapeScraper = BuscapeScraper


class GoogleShoppingScraper:
    SEARCH_URL = "https://www.google.com/search"
    SERPER_SHOPPING_URL = "https://google.serper.dev/shopping"
    last_status: str = "ok"

    @classmethod
    def search(cls, query: str, limit: int = 15) -> List[ProductOffer]:
        """
        Busca produtos no Google Shopping usando:
        1. Serper.dev Shopping API (se SERPER_API_KEY estiver configurada — mais confiável).
        2. Scraping direto (udm=28).
        3. Fallback opcional via Gemini Google Search Grounding (se GEMINI_API_KEY ativa).
        """
        cls.last_status = "ok"
        if not query:
            return []

        if Config.SERPER_API_KEY:
            serper_offers = cls._search_via_serper(query, limit)
            if serper_offers:
                cls.last_status = "ok (serper)"
                return serper_offers

        direct_offers, blocked_js = cls._search_direct(query, limit)
        if direct_offers:
            cls.last_status = "ok"
            return direct_offers

        if blocked_js:
            cls.last_status = "blocked_js"
            if Config.GEMINI_API_KEY:
                gemini_offers = cls._search_via_gemini_grounding(query, limit)
                if gemini_offers:
                    cls.last_status = "ok (gemini_search)"
                    return gemini_offers

        return []

    @classmethod
    def _search_via_serper(cls, query: str, limit: int) -> List[ProductOffer]:
        offers: List[ProductOffer] = []
        try:
            resp = requests.post(
                cls.SERPER_SHOPPING_URL,
                headers={
                    "X-API-KEY": Config.SERPER_API_KEY,
                    "Content-Type": "application/json",
                },
                json={"q": query, "gl": "br", "hl": "pt-br", "num": min(limit, 20)},
                timeout=10,
            )
            if resp.status_code != 200:
                return offers

            for item in resp.json().get("shopping", [])[:limit]:
                title = (item.get("title") or "").strip()
                price = parse_br_price(item.get("price"))
                store = (item.get("source") or "Google Shopping").strip()
                link = item.get("link") or ""
                img_url = item.get("imageUrl")
                rating = item.get("rating")
                if title and price > 0:
                    offers.append(
                        ProductOffer(
                            title=title,
                            price=price,
                            store=store,
                            link=link,
                            image_url=img_url,
                            rating=float(rating) if rating else None,
                            source="google_shopping",
                        )
                    )
        except Exception:
            pass
        return offers

    @classmethod
    def _search_direct(cls, query: str, limit: int) -> tuple[List[ProductOffer], bool]:
        offers: List[ProductOffer] = []
        blocked_js = False
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        params = {"q": query, "hl": "pt-BR", "gl": "br", "udm": "28"}

        try:
            resp = requests.get(cls.SEARCH_URL, params=params, headers=headers, timeout=10)
            if resp.status_code != 200:
                return offers, False

            if "enablejs" in resp.text.lower() or "httpservice/retry/enablejs" in resp.text.lower():
                return offers, True

            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.select(".sh-dgr__grid-result, .sh-dgr__content, .sh-np__click-target, div[data-docid]")
            for card in cards[:limit]:
                title_elem = card.select_one("h3, .tAxLfb, .EI11Pd, .Xjkr3b")
                title = title_elem.get_text(strip=True) if title_elem else ""

                price_elem = card.select_one(".a8Pemb, .OFFNJ, .hn9baf, span.kHxwFf")
                price = parse_br_price(price_elem.get_text(strip=True) if price_elem else "")

                store_elem = card.select_one(".aULzUe, .IuHnof, .eaLbx, .sh-np__seller-container")
                store = store_elem.get_text(strip=True).replace("De ", "").strip() if store_elem else "Google Shopping"

                link_elem = card.select_one("a[href*='/url?'], a[href*='google.com/shopping/product/'], a.shntl")
                link = ""
                if link_elem and "href" in link_elem.attrs:
                    href = link_elem["href"]
                    if href.startswith("/url?"):
                        parsed = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                        link = parsed.get("url", [href])[0]
                    elif href.startswith("/"):
                        link = f"https://www.google.com{href}"
                    else:
                        link = href

                img_elem = card.select_one("img")
                img_url = img_elem.get("src") if img_elem else None

                if title and price > 0:
                    offers.append(
                        ProductOffer(
                            title=title,
                            price=price,
                            store=store,
                            link=link,
                            image_url=img_url,
                            source="google_shopping",
                        )
                    )
        except Exception:
            pass

        return offers, blocked_js

    @classmethod
    def _search_via_gemini_grounding(cls, query: str, limit: int) -> List[ProductOffer]:
        """Fallback usando Gemini Google Search Grounding quando disponível e dentro da cota."""
        offers: List[ProductOffer] = []
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=Config.GEMINI_API_KEY)
            prompt = (
                f"Pesquise ofertas reais atuais no Brasil (Mercado Livre, Amazon, Shopee, Magazine Luiza, etc.) "
                f"para o produto exato: '{query}'. "
                f"Responda EXCLUSIVAMENTE com um JSON válido no formato de lista: "
                f'[{{"title": "...", "price": 123.45, "store": "...", "link": "https://..."}}]. '
                f"Inclua apenas anúncios com preço numérico confirmado e URL real."
            )
            res = client.models.generate_content(
                model="gemini-3.8-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())]
                ),
            )
            text = (res.text or "").strip()
            match = re.search(r"\[.*\]", text, re.DOTALL)
            if not match:
                return offers
            items = json.loads(match.group(0))
            for it in items[:limit]:
                title = str(it.get("title") or "").strip()
                price = parse_br_price(it.get("price"))
                store = str(it.get("store") or "Google Search").strip()
                link = str(it.get("link") or "").strip()
                if title and price > 0 and link.startswith("http"):
                    offers.append(
                        ProductOffer(
                            title=title,
                            price=price,
                            store=store,
                            link=link,
                            source="google_shopping",
                        )
                    )
        except Exception:
            pass
        return offers
