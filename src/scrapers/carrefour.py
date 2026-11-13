import random
from typing import List
import requests
from src.scrapers.base import ProductOffer, USER_AGENTS


class CarrefourScraper:
    """Scraper para o catálogo do Carrefour Brasil via API pública VTEX Intelligent Search."""

    API_URL = "https://www.carrefour.com.br/api/io/_v/api/intelligent-search/product_search/trade-policy/1"
    last_status: str = "ok"

    @classmethod
    def search(cls, query: str, limit: int = 12) -> List[ProductOffer]:
        offers: List[ProductOffer] = []
        cls.last_status = "ok"
        if not query:
            return offers

        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "application/json",
            "Accept-Language": "pt-BR,pt;q=0.9",
        }
        params = {
            "query": query.strip(),
            "page": 1,
            "count": min(limit, 20),
        }

        try:
            resp = requests.get(cls.API_URL, params=params, headers=headers, timeout=10)
            if resp.status_code != 200:
                cls.last_status = f"http_{resp.status_code}"
                return offers

            products = resp.json().get("products", [])
            for prod in products[:limit]:
                title = (prod.get("productName") or "").strip()
                if not title:
                    continue

                price = 0.0
                list_price = None
                img_url = None
                seller_name = "Carrefour"

                items = prod.get("items") or []
                if items:
                    first_item = items[0]
                    images = first_item.get("images") or []
                    if images:
                        img_url = images[0].get("imageUrl")

                    sellers = first_item.get("sellers") or []
                    for seller in sellers:
                        comm = seller.get("commertialOffer") or {}
                        p_val = float(comm.get("Price") or 0.0)
                        if p_val > 0 and (price == 0.0 or p_val < price):
                            price = p_val
                            lp = float(comm.get("ListPrice") or 0.0)
                            list_price = lp if lp > p_val else None
                            s_name = (seller.get("sellerName") or "").strip()
                            if s_name and s_name.lower() != "carrefour":
                                seller_name = f"Carrefour ({s_name})"
                            else:
                                seller_name = "Carrefour"

                if price <= 0:
                    continue

                link_path = prod.get("link") or ""
                link = f"https://www.carrefour.com.br{link_path}" if link_path.startswith("/") else link_path

                offers.append(
                    ProductOffer(
                        title=title,
                        price=round(price, 2),
                        original_price=round(list_price, 2) if list_price else None,
                        store=seller_name,
                        link=link,
                        image_url=img_url,
                        source="carrefour",
                    )
                )
        except Exception:
            cls.last_status = "error"

        return offers
