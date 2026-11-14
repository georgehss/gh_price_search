import requests
import random
import re
import urllib.parse
from typing import List, Optional
from bs4 import BeautifulSoup
from src.config import Config
from src.scrapers.base import ProductOffer, USER_AGENTS, parse_br_price


class MercadoLivreScraper:
    API_URL = "https://api.mercadolibre.com/sites/MLB/search"
    last_status: str = "ok"

    @classmethod
    def search(cls, query: str, limit: int = 15) -> List[ProductOffer]:
        """
        Busca produtos no Mercado Livre via API oficial (com token opcional) ou HTML scraping.
        """
        offers: List[ProductOffer] = []
        cls.last_status = "ok"
        if not query:
            return offers

        session = requests.Session()
        session.headers.update({
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8",
            "Sec-Ch-Ua": '"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1"
        })

        # 1. Tentativa via API pública / autenticada
        api_blocked = False
        try:
            params = {"q": query, "limit": min(limit, 20)}
            api_headers = {}
            if Config.MELI_ACCESS_TOKEN:
                api_headers["Authorization"] = f"Bearer {Config.MELI_ACCESS_TOKEN}"
            response = session.get(cls.API_URL, params=params, headers=api_headers, timeout=8)
            if response.status_code == 200:
                data = response.json()
                results = data.get("results", [])
                for item in results:
                    price = float(item.get("price", 0.0) or 0.0)
                    original_price = float(item.get("original_price", 0.0)) if item.get("original_price") else None
                    title = item.get("title", "")
                    link = item.get("permalink", "")
                    thumb = item.get("thumbnail", "")

                    seller_info = item.get("seller", {})
                    seller_name = item.get("official_store_name") or seller_info.get("nickname") or "Mercado Livre"

                    if price > 0 and title:
                        offers.append(
                            ProductOffer(
                                title=title,
                                price=round(price, 2),
                                original_price=round(original_price, 2) if original_price else None,
                                store=f"ML: {seller_name}",
                                link=link,
                                image_url=thumb,
                                source="mercado_livre"
                            )
                        )
                if offers:
                    cls.last_status = "ok"
                    return offers
            elif response.status_code in (401, 403):
                api_blocked = True
        except Exception:
            pass

        # 2. Fallback via HTML scraping (slug com hífen exigido pelo ML)
        try:
            slug = re.sub(r"[^a-zA-Z0-9]+", "-", query.strip().lower()).strip("-")
            url = f"https://lista.mercadolivre.com.br/{urllib.parse.quote(slug)}"
            resp = session.get(url, timeout=10)
            if resp.status_code == 200:
                resp_lower = resp.text.lower()
                if (
                    "account-verification" in resp.url.lower()
                    or "suspicious-traffic" in resp_lower
                    or "acesse sua conta" in resp_lower
                    or "sou novo" in resp_lower
                ):
                    cls.last_status = "blocked_login"
                    return offers

                soup = BeautifulSoup(resp.text, "html.parser")
                items = soup.select(".poly-card, .ui-search-layout__item, .ui-search-result__wrapper")
                for it in items[:limit]:
                    title_elem = it.select_one(".poly-component__title, .ui-search-item__title, a.poly-component__title")
                    link_elem = it.select_one("a.poly-component__title, a.ui-search-link, a[href*='mercadolivre.com.br']")
                    fraction_elem = it.select_one(".andes-money-amount__fraction")
                    cents_elem = it.select_one(".andes-money-amount__cents")

                    if title_elem and fraction_elem:
                        title = title_elem.get_text(strip=True)
                        fraction = fraction_elem.get_text(strip=True)
                        cents = cents_elem.get_text(strip=True) if cents_elem else "00"
                        price_str = f"{fraction},{cents}"
                        price = parse_br_price(price_str)

                        link = link_elem["href"] if link_elem and "href" in link_elem.attrs else ""

                        store_elem = it.select_one(".poly-component__seller, .ui-search-official-store-label, .ui-search-item__brand-discoverability")
                        store_name = store_elem.get_text(strip=True) if store_elem else "Mercado Livre"
                        store_name = store_name.replace("Por ", "").replace("por ", "").strip()

                        img_elem = it.select_one("img")
                        img_url = img_elem.get("src") or img_elem.get("data-src") if img_elem else None

                        if price > 0 and title:
                            offers.append(
                                ProductOffer(
                                    title=title,
                                    price=price,
                                    store=f"ML: {store_name}",
                                    link=link,
                                    image_url=img_url,
                                    source="mercado_livre"
                                )
                            )
            elif api_blocked or resp.status_code in (401, 403):
                cls.last_status = f"http_{resp.status_code}"
        except Exception:
            if api_blocked:
                cls.last_status = "blocked_403"

        if not offers and api_blocked and cls.last_status == "ok":
            cls.last_status = "blocked_403"

        return offers
