import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from src.database.db import init_db, get_db
from src.database.models import DatabaseManager
from src.notifier.callmebot import CallMeBotNotifier
from src.scrapers.search_engine import UnifiedSearchEngine
from src.scrapers.kabum import KabumScraper
from src.scrapers.coupons import CouponScraper
from src.ai.analyzer import DealAIAnalyzer
from src.scheduler.monitor import init_scheduler, get_scheduler_status, update_scheduler_interval

def test_all():
    print("=" * 65)
    print("INICIANDO BATERIA DE TESTES DE INTEGRAÇÃO DO GH PRICE SEARCH")
    print("=" * 65)

    print("\n1. TESTANDO INICIALIZAÇÃO E INTEGRIDADE DO BANCO (SQLite WAL)...")
    init_db()
    with get_db() as conn:
        journal_mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
        fk = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
        print(f"   -> Modo SQLite Journal: {journal_mode.upper()} | Foreign Keys: {fk}")
        assert fk == 1, "Foreign keys devem estar ativas"

    DatabaseManager.set_setting("test_verification_key", "active_ok")
    assert DatabaseManager.get_setting("test_verification_key") == "active_ok"
    print("   -> Configurações e conexões seguras validadas com sucesso!")

    print("\n2. TESTANDO PRODUTOS MONITORADOS E ESTATÍSTICAS (CRUD)...")
    pid = DatabaseManager.add_monitored_product("PlayStation 5 Slim", 3600.0)
    assert pid > 0, "ID do produto deve ser um inteiro positivo"
    DatabaseManager.update_target_price(pid, 3500.0)

    # Simular histórico de preços para cálculo de estatísticas
    DatabaseManager.record_price(pid, "PlayStation 5 Slim", 3799.0, "Amazon", "PS5 Slim 1TB", "http://amazon.com")
    DatabaseManager.record_price(pid, "PlayStation 5 Slim", 3499.0, "KaBuM!", "PS5 Slim 1TB", "http://kabum.com")

    stats = DatabaseManager.get_product_stats("PlayStation 5 Slim")
    assert stats["total_records"] >= 2, "Estatísticas devem conter registros"
    assert stats["min_price"] == 3499.0, f"Menor preço incorreto: {stats['min_price']}"
    print(f"   -> Produto ID {pid} cadastrado. Min: R$ {stats['min_price']} | Média: R$ {stats['avg_price']} | Variação: {stats['diff_percent']}%")
    DatabaseManager.delete_monitored_product(pid)

    print("\n3. TESTANDO NOTIFICADOR CALLMEBOT...")
    clean_num = CallMeBotNotifier.clean_phone("11 99999-8888")
    assert clean_num == "+5511999998888", f"Falha na sanitização: {clean_num}"
    clean_empty = CallMeBotNotifier.clean_phone("")
    assert clean_empty == "", "Telefone vazio deve retornar string vazia"
    print("   -> Sanitização de telefone e formatação: OK")

    print("\n4. TESTANDO SCRAPER DIRETO DA KABUM! (API Catálogo)...")
    kabum_offers = KabumScraper.search("Kindle", limit=5)
    print(f"   -> Ofertas retornadas pela KaBuM!: {len(kabum_offers)}")
    if kabum_offers:
        k = kabum_offers[0]
        print(f"      Item: {k.title[:45]}... | R$ {k.price} | Foto: {bool(k.image_url)}")
        assert k.price > 0, "Preço deve ser positivo"

    print("\n5. TESTANDO MOTOR DE CUPONS DINÂMICOS (Cuponomia + Promobit)...")
    coupons = CouponScraper.search_all_relevant_coupons("Kindle", stores_found=["Amazon", "KaBuM!"], limit=4)
    print(f"   -> Cupons ativos encontrados: {len(coupons)}")
    for c in coupons[:2]:
        print(f"      [{c.code}] {c.store}: {c.description[:50]}")
    assert len(coupons) > 0, "Deve encontrar cupons para lojas parceiras"

    print("\n6. TESTANDO MOTOR DE BUSCA UNIFICADO (Buscapé, Zoom, KaBuM!)...")
    search_res = UnifiedSearchEngine.search_all("Kindle")
    print(f"   -> Query: '{search_res['query']}'")
    print(f"   -> Total de ofertas unificadas: {search_res['total_found']}")
    print(f"   -> Total de cupons anexados: {len(search_res['coupons'])}")
    assert search_res["total_found"] > 0, "Busca unificada deve retornar ofertas"
    best = search_res["best_deal"]
    assert best is not None, "Deve haver uma melhor oferta"
    print(f"   -> Campeão de Preço: R$ {best['price']} na loja '{best['store']}'")
    print(f"   -> Imagem capturada: {bool(best.get('image_url'))}")

    print("\n7. TESTANDO ANÁLISE DE CUSTO-BENEFÍCIO COM GEMINI AI...")
    ai_res = DealAIAnalyzer.analyze_deals(
        query="Kindle",
        best_deal=search_res["best_deal"],
        top_offers=search_res["top_offers"],
        coupons=search_res["coupons"]
    )
    assert "verdict" in ai_res and len(ai_res["verdict"]) > 0, "Falha na geração do veredito"
    print(f"   -> Fonte da análise: {ai_res.get('source')}")
    print(f"   -> Veredito gerado:\n      {ai_res['verdict'][:200]}...")

    print("\n8. TESTANDO AGENDADOR E ATUALIZAÇÃO DINÂMICA DE INTERVALO...")
    sched = init_scheduler(interval_minutes=30)
    status_before = get_scheduler_status()
    assert status_before["is_running"], "Agendador deve estar rodando"
    print(f"   -> Agendador ativo! Intervalo inicial: {status_before['interval_minutes']} min")

    update_scheduler_interval(45)
    status_after = get_scheduler_status()
    assert status_after["interval_minutes"] == 45, "Intervalo deve ser atualizado"
    print(f"   -> Intervalo atualizado dinamicamente para: {status_after['interval_minutes']} min")

    print("\n" + "=" * 65)
    print("TODOS OS TESTES PASSARAM COM 100% DE SUCESSO!")
    print("=" * 65)

if __name__ == "__main__":
    test_all()
