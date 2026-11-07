import requests
import random
import re
import urllib.parse
from bs4 import BeautifulSoup
from typing import List, Optional
from src.scrapers.base import ProductOffer, USER_AGENTS, parse_br_price

class BuscapeScraper:
    """Scraper robusto para Buscapé com extração de loja real, fotos e parcelamento."""
    SEARCH_URL = "https://www.buscape.com.br/search"

    @classmethod
    def search(cls, query: str, limit: int = 15) -> List[ProductOffer]:
        offers: List[ProductOffer] = []
        if not query:
            return offers

        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8",
        }
        params = {"q": query}

        try:
            resp = requests.get(cls.SEARCH_URL, params=params, headers=headers, timeout=12)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                cards = soup.select("[data-testid='product-card'], div[class*='SearchCard_ProductCard']")
                for card in cards[:limit]:
                    # Título
                    title_elem = card.select_one("[data-testid='product-card::name'], h2")
                    # Preço
                    price_elem = card.select_one("[data-testid='product-card::price'], [class*='Price_Value']")
                    # Link
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
                        if href.startswith("/"):
                            link = f"https://www.buscape.com.br{href}"
                        else:
                            link = href

                    # Extração da loja real (ex: "Via Amazon", "Via KaBuM!")
                    store = "Buscapé"
                    via_el = card.find(string=re.compile(r"Via\s+", re.IGNORECASE))
                    if via_el:
                        store_name = via_el.strip().replace("Via ", "").strip()
                        if store_name:
                            store = store_name
                    else:
                        multi_store = card.find(string=re.compile(r"Compare em\s+\d+\s+lojas", re.IGNORECASE))
                        if multi_store:
                            store = f"Buscapé ({multi_store.strip()})"

                    # Imagem do Produto
                    img_elem = card.select_one("img")
                    img_url = img_elem.get("src") if img_elem else None

                    # Parcelamento
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
                            source="buscape"
                        )
                    )
        except Exception:
            pass

        return offers


class ZoomScraper:
    """Scraper complementar para o comparador Zoom."""
    SEARCH_URL = "https://www.zoom.com.br/search"

    @classmethod
    def search(cls, query: str, limit: int = 15) -> List[ProductOffer]:
        offers: List[ProductOffer] = []
        if not query:
            return offers

        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8",
        }
        params = {"q": query}

        try:
            resp = requests.get(cls.SEARCH_URL, params=params, headers=headers, timeout=12)
            if resp.status_code == 200:
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
                        if href.startswith("/"):
                            link = f"https://www.zoom.com.br{href}"
                        else:
                            link = href

                    store = "Zoom"
                    via_el = card.find(string=re.compile(r"Via\s+", re.IGNORECASE))
                    if via_el:
                        store_name = via_el.strip().replace("Via ", "").strip()
                        if store_name:
                            store = store_name

                    img_elem = card.select_one("img")
                    img_url = img_elem.get("src") if img_elem else None

                    offers.append(
                        ProductOffer(
                            title=title,
                            price=price,
                            store=store,
                            link=link,
                            image_url=img_url,
                            source="zoom"
                        )
                    )
        except Exception:
            pass

        return offers


# Compatibilidade retroativa
ZoomBuscapeScraper = BuscapeScraper


class GoogleShoppingScraper:
    SEARCH_URL = "https://www.google.com/search"

    @classmethod
    def search(cls, query: str, limit: int = 15) -> List[ProductOffer]:
        """
        Tenta buscar produtos no Google Shopping (udm=28 e tbm=shop).
        """
        offers: List[ProductOffer] = []
        if not query:
            return offers

        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        params = {
            "q": query,
            "hl": "pt-BR",
            "gl": "br",
            "udm": "28",
        }

        try:
            resp = requests.get(cls.SEARCH_URL, params=params, headers=headers, timeout=12)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                cards = soup.select(".sh-dgr__grid-result, .sh-dgr__content, .sh-np__click-target, div[data-docid]")
                for card in cards[:limit]:
                    title_elem = card.select_one("h3, .tAxLfb, .EI11Pd, .Xjkr3b")
                    title = title_elem.get_text(strip=True) if title_elem else ""

                    price_elem = card.select_one(".a8Pemb, .OFFNJ, .hn9baf, span.kHxwFf")
                    price_text = price_elem.get_text(strip=True) if price_elem else ""
                    price = parse_br_price(price_text)

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
                                source="google_shopping"
                            )
                        )
        except Exception:
            pass

        return offers
