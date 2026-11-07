import time
import threading
from datetime import datetime, timedelta
from typing import Optional, Any
from src.database.models import DatabaseManager
from src.scrapers.search_engine import UnifiedSearchEngine
from src.ai.analyzer import DealAIAnalyzer
from src.notifier.callmebot import CallMeBotNotifier
from src.config import Config

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    HAS_APSCHEDULER = True
except ImportError:
    HAS_APSCHEDULER = False
    BackgroundScheduler = Any  # type: ignore

class ThreadedFallbackScheduler:
    """Agendador nativo baseado em threads padrão do Python caso APScheduler falhe."""
    def __init__(self, interval_seconds: int = 3600):
        self.interval = interval_seconds
        self.running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self):
        if self.running:
            return
        self.running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False
        self._stop_event.set()

    def _run_loop(self):
        while self.running and not self._stop_event.is_set():
            self._stop_event.wait(self.interval)
            if self.running and not self._stop_event.is_set():
                try:
                    run_monitoring_cycle()
                except Exception:
                    pass

    def get_jobs(self):
        return [self] if self.running else []

scheduler: Any = None

def check_single_product(product: dict, force_notify: bool = False) -> dict:
    """
    Executa a verificação de preço de um produto e envia notificação caso atinja o critério de alerta.
    Retorna resumo do resultado da checagem.
    """
    keyword = product["keyword"]
    target_price = float(product.get("target_price", 0.0) or 0.0)
    product_id = product["id"]

    historical_min = DatabaseManager.get_historical_min_price(keyword)

    # Executa busca unificada
    search_res = UnifiedSearchEngine.search_all(keyword)
    best_deal = search_res.get("best_deal")
    top_offers = search_res.get("top_offers", [])
    coupons = search_res.get("coupons", [])

    if not best_deal or best_deal.get("price", 0) <= 0:
        return {"status": "no_results", "product": keyword}

    current_price = float(best_deal["price"])
    store = best_deal.get("store", "Loja Online")
    title = best_deal.get("title", keyword)
    link = best_deal.get("link", "")

    # Gravar no histórico
    DatabaseManager.record_price(
        product_id=product_id,
        keyword=keyword,
        price=current_price,
        store=store,
        title=title,
        link=link
    )

    # Atualizar estado do produto
    DatabaseManager.update_product_lowest(product_id, current_price, store, link, title=title)

    # Critérios de disparo de alerta inteligente:
    # 1. Se atingiu o preço-alvo definido pelo usuário
    # 2. Se bateu o menor preço histórico registrado (com pelo menos 1% de queda)
    # 3. Se for forçado (ex: clique no botão 'Checar' na interface)
    should_alert = False
    alert_reason = ""

    if force_notify:
        should_alert = True
        alert_reason = "manual_trigger"
    elif target_price > 0 and current_price <= target_price:
        should_alert = True
        alert_reason = "target_reached"
    elif historical_min and historical_min > 0 and current_price < (historical_min * 0.99):
        should_alert = True
        alert_reason = "historical_low"

    # Anti-spam: se não for manual, verificar se já alertamos sobre este mesmo patamar de preço recentemente (últimas 6h)
    if should_alert and not force_notify:
        last_alert = DatabaseManager.get_last_successful_alert(product_id)
        if last_alert and last_alert.get("sent_at"):
            try:
                sent_time = datetime.strptime(str(last_alert["sent_at"])[:19], "%Y-%m-%d %H:%M:%S")
                if datetime.now() - sent_time < timedelta(hours=6):
                    # Se o preço não caiu mais de 2% em relação ao último alerta, suprime para evitar spam
                    if str(current_price) in last_alert.get("message", ""):
                        should_alert = False
            except Exception:
                pass

    notify_res = None
    if should_alert:
        # Gerar análise da IA
        ai_res = DealAIAnalyzer.analyze_deals(
            query=keyword,
            best_deal=best_deal,
            top_offers=top_offers,
            coupons=coupons,
            historical_min=historical_min
        )
        verdict = ai_res.get("verdict", "")

        # Enviar WhatsApp
        notify_res = CallMeBotNotifier.send_deal_report(
            keyword=keyword,
            best_deal=best_deal,
            top_offers=top_offers,
            coupons=coupons,
            gemini_verdict=verdict,
            product_id=product_id
        )

    return {
        "status": "success",
        "product": keyword,
        "lowest_price": current_price,
        "store": store,
        "alert_sent": should_alert,
        "alert_result": notify_res
    }

def run_monitoring_cycle() -> list:
    """Ciclo completo executado pelo agendador para todos os produtos ativos."""
    active_products = DatabaseManager.get_monitored_products(active_only=True)
    results = []
    for prod in active_products:
        try:
            res = check_single_product(prod)
            results.append(res)
            time.sleep(2)  # Pausa de cortesia entre requisições
        except Exception as e:
            results.append({"status": "error", "product": prod.get("keyword"), "error": str(e)})
    return results

def init_scheduler(interval_minutes: Optional[int] = None) -> Any:
    """Inicializa e inicia o agendador em segundo plano como singleton."""
    global scheduler
    if scheduler is not None and getattr(scheduler, "running", False):
        return scheduler

    minutes = interval_minutes or Config.CHECK_INTERVAL_MINUTES or 60

    if HAS_APSCHEDULER:
        try:
            sched = BackgroundScheduler(daemon=True)
            sched.add_job(
                run_monitoring_cycle,
                "interval",
                minutes=minutes,
                id="price_monitor_job",
                replace_existing=True
            )
            sched.start()
            scheduler = sched
            return scheduler
        except Exception:
            pass

    # Fallback nativo
    fallback_sched = ThreadedFallbackScheduler(interval_seconds=minutes * 60)
    fallback_sched.start()
    scheduler = fallback_sched
    return scheduler

def update_scheduler_interval(minutes: int):
    """Atualiza a frequência de execução do agendador em tempo real."""
    global scheduler
    if minutes <= 0:
        minutes = 60
    Config.CHECK_INTERVAL_MINUTES = minutes
    Config.save_env_var("CHECK_INTERVAL_MINUTES", str(minutes))

    if scheduler is not None and getattr(scheduler, "running", False):
        if HAS_APSCHEDULER and hasattr(scheduler, "reschedule_job"):
            try:
                scheduler.reschedule_job("price_monitor_job", trigger="interval", minutes=minutes)
                return True
            except Exception:
                pass
        # Reinicia
        try:
            if hasattr(scheduler, "shutdown"):
                scheduler.shutdown(wait=False)
            elif hasattr(scheduler, "stop"):
                scheduler.stop()
        except Exception:
            pass
        scheduler = None
        init_scheduler(interval_minutes=minutes)
        return True
    return False

def get_scheduler_status() -> dict:
    global scheduler
    is_running = scheduler is not None and getattr(scheduler, "running", False)
    jobs_count = len(scheduler.get_jobs()) if is_running else 0
    next_run = None
    if is_running and HAS_APSCHEDULER and hasattr(scheduler, "get_job"):
        job = scheduler.get_job("price_monitor_job")
        if job and hasattr(job, "next_run_time") and job.next_run_time:
            next_run = job.next_run_time.strftime("%d/%m/%Y %H:%M:%S")

    return {
        "is_running": is_running,
        "jobs_count": jobs_count,
        "interval_minutes": Config.CHECK_INTERVAL_MINUTES,
        "next_run": next_run or (f"A cada {Config.CHECK_INTERVAL_MINUTES} min" if is_running else "Inativo")
    }
