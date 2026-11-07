import requests
import random
import re
from typing import List, Optional
from src.scrapers.base import ProductOffer, USER_AGENTS, parse_br_price
from bs4 import BeautifulSoup

class MercadoLivreScraper:
    API_URL = "https://api.mercadolibre.com/sites/MLB/search"

    @classmethod
    def search(cls, query: str, limit: int = 15) -> List[ProductOffer]:
        """
        Busca produtos no Mercado Livre via API oficial / HTML com tratamento de frações e centavos.
        """
        offers: List[ProductOffer] = []
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

        # 1. Tentativa via API pública (se aberta pelo IP)
        try:
            params = {"q": query, "limit": min(limit, 20)}
            response = session.get(cls.API_URL, params=params, timeout=8)
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
                    return offers
        except Exception:
            pass

        # 2. Fallback via HTML scraping
        try:
            formatted_query = urllib_quote(query.strip())
            url = f"https://lista.mercadolivre.com.br/{formatted_query}"
            resp = session.get(url, timeout=10)
            if resp.status_code == 200:
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
        except Exception:
            pass

        return offers

def urllib_quote(q: str) -> str:
    import urllib.parse
    return urllib.parse.quote_plus(q)
