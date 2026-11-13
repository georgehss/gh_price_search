import sys
from pathlib import Path
import streamlit as st
import pandas as pd
from datetime import datetime

# Garante que a raiz do projeto esteja no sys.path (necessário no Streamlit Cloud)
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    import plotly.express as px
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

from src.config import Config
from src.database.db import init_db
from src.database.models import DatabaseManager
from src.scrapers.search_engine import UnifiedSearchEngine
from src.ai.analyzer import DealAIAnalyzer
from src.notifier.callmebot import CallMeBotNotifier
from src.scheduler.monitor import (
    init_scheduler,
    check_single_product,
    run_monitoring_cycle,
    update_scheduler_interval,
    get_scheduler_status
)

# Configuração da página Streamlit
st.set_page_config(
    page_title="GH Price Search & Deal Bot",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inicializar banco de dados SQLite
init_db()

# Inicialização do agendador como recurso compartilhado persistente (singleton)
@st.cache_resource
def get_or_start_scheduler():
    return init_scheduler()

scheduler_instance = get_or_start_scheduler()

# --- BARRA LATERAL (SIDEBAR) ---
with st.sidebar:
    st.title("🤖 GH Price Search")
    st.caption("Varredura em tempo real em toda a internet, cupons ativos e análise IA de custo-benefício.")

    st.markdown("---")
    st.subheader("📡 Status dos Serviços")

    # Status Gemini
    if Config.GEMINI_API_KEY:
        st.success("🧠 Gemini AI: **Ativo** (3.8 Flash)")
    else:
        st.warning("⚠️ Gemini AI: **Sem chave (.env)**")

    # Status CallMeBot
    if Config.CALLMEBOT_API_KEY:
        st.success("📱 CallMeBot: **Ativo**")
    else:
        st.warning("⚠️ CallMeBot: **Sem chave (.env)**")

    # Status Armazenamento Google Drive / Sheets
    if Config.get_gsheets_credentials():
        st.success("📁 Google Sheets: **Conectado (Drive)**")
    else:
        st.info("💾 Armazenamento: **SQLite Local**")

    # Status Agendador
    sched_info = get_scheduler_status()
    if sched_info["is_running"]:
        st.info(f"⏱️ Monitoramento: **Ativo**\n\nPróxima execução: `{sched_info['next_run']}`")
    else:
        st.error("⏹️ Monitoramento: **Parado**")

    st.markdown("---")
    # Telefone de Alerta Rápido
    saved_phone = DatabaseManager.get_setting("user_phone", Config.DEFAULT_PHONE)
    new_phone = st.text_input("📞 Telefone WhatsApp (Alertas):", value=saved_phone, placeholder="+5511999999999")
    if new_phone != saved_phone:
        DatabaseManager.set_setting("user_phone", new_phone)
        Config.save_env_var("DEFAULT_PHONE", new_phone)
        st.toast("Telefone atualizado com sucesso!", icon="✅")

    st.markdown("---")
    st.caption("Desenvolvido para George Harrison")

# --- ABAS PRINCIPAIS ---
tab_search, tab_monitored, tab_history, tab_settings = st.tabs([
    "🔎 Busca Imediata",
    "🎯 Produtos Monitorados",
    "📈 Histórico & Gráficos",
    "⚙️ Configurações & Alertas"
])

# ==========================================
# ABA 1: BUSCA IMEDIATA
# ==========================================
with tab_search:
    st.header("🔎 Pesquisa Detalhada em Toda a Internet")
    st.write("Varre simultaneamente KaBuM!, Carrefour, Buscapé, Zoom, Bondfaro, Mercado Livre, Google Shopping e Cuponomia.")

    # Termos de busca rápidos / recentes para facilitar edição e reexecução
    recent_kw = DatabaseManager.get_recent_search_keywords(limit=6)
    if recent_kw:
        st.markdown("**💡 Buscas recentes (clique para carregar e editar):**")
        cols_rec = st.columns(min(len(recent_kw), 6))
        for idx, rk in enumerate(recent_kw[:6]):
            with cols_rec[idx]:
                if st.button(f"🔍 {rk[:18]}", key=f"quick_search_{idx}", use_container_width=True, help=f"Carregar '{rk}' para pesquisa"):
                    st.session_state["input_search_query"] = rk
                    st.rerun()

    col_q, col_btn = st.columns([4, 1])
    with col_q:
        current_query_val = st.session_state.get("input_search_query", "")
        search_query = st.text_input(
            "Digite o nome do produto ou modelo que deseja pesquisar:",
            value=current_query_val,
            placeholder="Ex: PlayStation 5 Slim, Kindle 11 Geração, RTX 4060, Smart TV 55 LG",
            key="input_search_query"
        )
    with col_btn:
        st.write("")
        st.write("")
        btn_search = st.button("🚀 Buscar Agora", use_container_width=True, type="primary")

    send_whatsapp_on_search = st.checkbox("📱 Enviar relatório deste produto para o WhatsApp via CallMeBot", value=True)

    # Execução da Busca
    if btn_search and search_query:
        with st.spinner(f"Varrendo lojas e cupons para '{search_query}'..."):
            results = UnifiedSearchEngine.search_all(search_query)
            best_deal = results.get("best_deal")
            top_offers = results.get("top_offers", [])
            coupons = results.get("coupons", [])
            brand_alternatives = results.get("brand_alternatives", [])

            # Análise de Custo-Benefício com IA
            hist_min = DatabaseManager.get_historical_min_price(search_query)
            ai_analysis = DealAIAnalyzer.analyze_deals(
                query=search_query,
                best_deal=best_deal,
                top_offers=top_offers,
                coupons=coupons,
                historical_min=hist_min,
                brand_alternatives=brand_alternatives
            )

            # Salva no session_state para manter persistência durante navegação
            st.session_state["last_search_query"] = search_query
            st.session_state["last_search_results"] = results
            st.session_state["last_ai_analysis"] = ai_analysis

            # Envia WhatsApp se marcado
            if send_whatsapp_on_search:
                with st.spinner("Enviando relatório executivo para o seu WhatsApp..."):
                    send_res = CallMeBotNotifier.send_deal_report(
                        keyword=search_query,
                        best_deal=best_deal,
                        top_offers=top_offers,
                        coupons=coupons,
                        gemini_verdict=ai_analysis.get("verdict", ""),
                        brand_alternatives=brand_alternatives
                    )
                    if send_res.get("success"):
                        st.success("📲 Relatório enviado com sucesso para o seu WhatsApp!")
                    else:
                        st.warning(f"Não foi possível enviar WhatsApp: {send_res.get('error')}")

            # Registra no histórico de preços apenas se for uma oferta válida real
            if best_deal and best_deal.get("price", 0) > 0:
                DatabaseManager.record_price(
                    product_id=None,
                    keyword=search_query,
                    price=best_deal["price"],
                    store=best_deal.get("store", "Loja"),
                    title=best_deal.get("title", search_query),
                    link=best_deal.get("link", "")
                )

    # Exibição dos resultados persistidos no session_state
    if "last_search_results" in st.session_state and st.session_state["last_search_results"]:
        results = st.session_state["last_search_results"]
        query_saved = st.session_state.get("last_search_query", "")
        best_deal = results.get("best_deal")
        top_offers = results.get("top_offers", [])
        coupons = results.get("coupons", [])
        brand_alternatives = results.get("brand_alternatives", [])
        rejected_count = results.get("rejected_count", 0)
        rejections = results.get("rejections", [])
        ai_analysis = st.session_state.get("last_ai_analysis", {})
        verdict = ai_analysis.get("verdict", "")

        st.markdown("---")
        # Painel Superior de Auditoria e Detalhes da Varredura Web
        source_status = results.get("source_status", {})
        with st.container(border=True):
            st.markdown(f"### 📋 Detalhes da Varredura Web: **{query_saved}**")
            d1, d2, d3, d4 = st.columns(4)
            with d1:
                st.markdown(f"**🔍 Termo Pesquisado:**\n`{query_saved}`")
            with d2:
                consulted_str = ", ".join(source_status.keys()) if source_status else "KaBuM!, Carrefour, Buscapé, Zoom, Bondfaro, ML, Google"
                st.markdown(f"**🏬 Lojas Consultadas:**\n{consulted_str}")
            with d3:
                st.metric("Ofertas Validadas", len(top_offers))
            with d4:
                st.metric("Itens Descartados (Filtro)", rejected_count)

            if source_status:
                status_badges = " | ".join([f"**{k}:** `{v}`" for k, v in source_status.items()])
                st.caption(f"📡 **Status por fonte:** {status_badges}")

            # Expander de auditoria detalhada dos itens descartados
            if rejections:
                with st.expander(f"🛡️ Ver auditoria do Filtro Anti-Divergência ({len(rejections)} itens descartados)"):
                    df_rej = pd.DataFrame(rejections)
                    if not df_rej.empty:
                        df_rej_show = df_rej[["title", "store", "price", "reason"]].copy()
                        df_rej_show["price"] = df_rej_show["price"].apply(lambda p: f"R$ {p:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                        df_rej_show.columns = ["Título Retornado pela Loja", "Loja", "Preço", "Motivo do Descarte"]
                        st.dataframe(df_rej_show, use_container_width=True, hide_index=True)

        if not top_offers:
            st.warning(f"⚠️ **Nenhuma oferta exata em estoque encontrada para '{query_saved}'.**")
            if rejected_count > 0:
                st.info(f"🛡️ **Filtro Anti-Divergência Ativo:** {rejected_count} resultados de modelos diferentes ou acessórios retornados pelos buscadores foram descartados automaticamente para garantir que você não compre o produto errado.")

            # Links diretos para busca manual em fontes protegidas por login/JS
            import urllib.parse
            q_enc = urllib.parse.quote_plus(query_saved)
            q_slug = "-".join(query_saved.lower().split())
            st.markdown("**🔗 Buscar diretamente nos marketplaces:**")
            l1, l2, l3, l4 = st.columns(4)
            with l1:
                st.link_button("🛒 Google Shopping", f"https://www.google.com/search?tbm=shop&q={q_enc}", use_container_width=True)
            with l2:
                st.link_button("🤝 Mercado Livre", f"https://lista.mercadolivre.com.br/{urllib.parse.quote(q_slug)}", use_container_width=True)
            with l3:
                st.link_button("📦 Amazon", f"https://www.amazon.com.br/s?k={q_enc}", use_container_width=True)
            with l4:
                st.link_button("🧡 Shopee", f"https://shopee.com.br/search?keyword={q_enc}", use_container_width=True)

            if verdict:
                st.subheader("🧠 Análise do Assistente IA")
                st.info(verdict)

            if brand_alternatives:
                st.subheader("📦 Modelos Alternativos Encontrados da Mesma Marca")
                cols_alt = st.columns(min(len(brand_alternatives), 3))
                for idx, alt in enumerate(brand_alternatives[:6]):
                    target_col = cols_alt[idx % len(cols_alt)]
                    with target_col:
                        with st.container(border=True):
                            img_src = alt.get("image_url")
                            if img_src:
                                st.image(img_src, use_container_width=True)
                            p_val = f"R$ {alt['price']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                            st.markdown(f"**{alt.get('store', 'Loja')}**")
                            st.subheader(p_val)
                            st.write(f"_{alt.get('title', '')[:65]}_")
                            if alt.get("link"):
                                st.link_button("🛒 Ver Oferta", alt["link"], use_container_width=True)
        else:
            st.markdown("---")
            # 1. Métricas Principais
            m1, m2, m3, m4 = st.columns(4)
            with m1:
                price_val = f"R$ {best_deal['price']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                st.metric("🏆 Menor Preço", price_val)
            with m2:
                st.metric("🏪 Loja Campeã", best_deal.get("store", "N/A"))
            with m3:
                st.metric("🎟️ Cupons Ativos", len(coupons))
            with m4:
                st.metric("📊 Lojas Comparadas", len(top_offers))

            # 2. Veredito da Inteligência Artificial
            st.subheader("🧠 Veredito de Custo-Benefício & Fraude (IA)")
            st.info(verdict)

            # 3. Cupons de Desconto Identificados
            if coupons:
                st.subheader("🎟️ Cupons de Desconto Ativos")
                cols_c = st.columns(min(len(coupons), 3))
                for idx, c in enumerate(coupons[:6]):
                    target_col = cols_c[idx % len(cols_c)]
                    with target_col:
                        with st.container(border=True):
                            st.markdown(f"🏷️ **Loja:** {c.get('store', 'Geral')}")
                            st.code(c.get("code", "ATIVAR NO SITE"))
                            st.caption(c.get("description", ""))
                            if c.get("link"):
                                st.link_button("Ativar Cupom", c["link"], use_container_width=True)

            # 4. Galeria de Destaque das Melhores Ofertas (Cards Visuais com Foto)
            st.subheader("🌟 Ofertas em Destaque")
            cards_cols = st.columns(min(len(top_offers), 4))
            for idx, offer in enumerate(top_offers[:4]):
                target_col = cards_cols[idx % len(cards_cols)]
                with target_col:
                    with st.container(border=True):
                        img_src = offer.get("image_url")
                        if img_src:
                            st.image(img_src, use_container_width=True)
                        else:
                            st.markdown("📦 *Sem imagem*")
                        p_val = f"R$ {offer['price']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                        st.markdown(f"**{offer.get('store', 'Loja')}**")
                        st.subheader(p_val)
                        if offer.get("installments"):
                            st.caption(f"💳 {offer['installments']}")
                        st.write(f"_{offer.get('title', '')[:55]}..._")
                        if offer.get("link"):
                            st.link_button("🛒 Ver Oferta", offer["link"], use_container_width=True)

            # 5. Tabela Completa com Filtros e Exportação
            st.subheader("🛒 Todas as Ofertas Encontradas")

            # Filtros dinâmicos
            df_offers = pd.DataFrame(top_offers)
            available_stores = sorted(list(df_offers["store"].unique()))
            col_f1, col_f2 = st.columns([2, 2])
            with col_f1:
                selected_stores = st.multiselect("Filtrar por loja:", available_stores, default=available_stores)
            with col_f2:
                sort_order = st.selectbox("Ordenar por:", ["Menor Preço", "Maior Preço"])

            filtered_df = df_offers[df_offers["store"].isin(selected_stores)].copy()
            if sort_order == "Maior Preço":
                filtered_df = filtered_df.sort_values("price", ascending=False)
            else:
                filtered_df = filtered_df.sort_values("price", ascending=True)

            if not filtered_df.empty:
                display_df = filtered_df[["price", "store", "title", "source", "link"]].copy()
                display_df["price"] = display_df["price"].apply(lambda p: f"R$ {p:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                display_df.columns = ["Preço", "Loja", "Título do Produto", "Origem", "Link Direto"]

                st.dataframe(
                    display_df,
                    column_config={
                        "Link Direto": st.column_config.LinkColumn("Comprar / Ver Oferta")
                    },
                    use_container_width=True,
                    hide_index=True
                )

                # Botão de Exportação CSV
                csv_data = filtered_df.to_csv(index=False).encode("utf-8")
                st.download_button(
                    label="📥 Baixar Ofertas em CSV",
                    data=csv_data,
                    file_name=f"ofertas_{query_saved.replace(' ', '_')}.csv",
                    mime="text/csv"
                )

            # 6. Adicionar ao Monitoramento Contínuo
            st.markdown("---")
            st.subheader("🎯 Monitorar este Produto")
            col_mon1, col_mon2 = st.columns([3, 1])
            with col_mon1:
                suggested_target = float(best_deal["price"] * 0.95) if best_deal else 0.0
                target_p_suggest = st.number_input(
                    f"Definir preço-alvo em R$ para receber alerta silencioso no WhatsApp caso caia mais:",
                    value=suggested_target,
                    step=10.0,
                    key="input_target_price_search"
                )
            with col_mon2:
                st.write("")
                st.write("")
                if st.button("➕ Monitorar Preço", use_container_width=True, type="primary"):
                    DatabaseManager.add_monitored_product(query_saved, target_p_suggest)
                    st.success(f"'{query_saved}' adicionado com sucesso aos produtos monitorados!")

# ==========================================
# ABA 2: PRODUTOS MONITORADOS
# ==========================================
with tab_monitored:
    st.header("🎯 Gerenciamento de Produtos Monitorados")
    st.write("O robô verifica esses itens periodicamente e envia mensagens automáticas no WhatsApp quando o preço-alvo ou o menor preço histórico é atingido.")

    col_add, col_check_all = st.columns([3, 1])
    with col_add:
        with st.expander("➕ Cadastrar Novo Produto para Monitorar", expanded=False):
            with st.form("form_add_product"):
                new_keyword = st.text_input("Nome exato ou modelo do produto:", placeholder="Ex: Sony PlayStation 5 Slim")
                new_target = st.number_input("Preço-alvo desejado em R$ (0 para alertar em qualquer menor histórico):", min_value=0.0, value=0.0, step=50.0)
                submitted = st.form_submit_button("Cadastrar Produto")
                if submitted and new_keyword:
                    DatabaseManager.add_monitored_product(new_keyword, new_target)
                    st.success(f"Produto '{new_keyword}' cadastrado com sucesso!")
                    st.rerun()

    with col_check_all:
        if st.button("⚡ Checar Todos Agora", use_container_width=True, type="secondary"):
            with st.spinner("Executando ciclo completo de checagem para todos os produtos ativos..."):
                cycle_results = run_monitoring_cycle()
                st.success(f"Ciclo concluído! {len(cycle_results)} produto(s) verificado(s).")
                st.rerun()

    products = DatabaseManager.get_monitored_products()
    if not products:
        st.info("Nenhum produto cadastrado para monitoramento ainda. Adicione um acima ou pesquise na aba 'Busca Imediata'.")
    else:
        for p in products:
            with st.container(border=True):
                # Modo de Edição Ativo para este Produto
                if st.session_state.get(f"editing_monitored_{p['id']}", False):
                    with st.form(key=f"form_edit_prod_{p['id']}"):
                        st.markdown(f"### ✏️ Editar Busca: **{p['keyword']}**")
                        e_col1, e_col2 = st.columns([3, 2])
                        with e_col1:
                            edit_kw = st.text_input("Novo termo de busca / modelo do produto:", value=p["keyword"])
                        with e_col2:
                            edit_target = st.number_input(
                                "Novo Preço-Alvo em R$:",
                                min_value=0.0,
                                value=float(p.get("target_price") or 0.0),
                                step=25.0
                            )
                        sync_hist = st.checkbox("Sincronizar também os registros anteriores desta busca no histórico", value=True)

                        btn_c1, btn_c2 = st.columns([1, 1])
                        with btn_c1:
                            if st.form_submit_button("💾 Salvar Alterações", type="primary", use_container_width=True):
                                if edit_kw.strip():
                                    DatabaseManager.edit_monitored_product(
                                        p["id"], edit_kw.strip(), edit_target, update_history=sync_hist
                                    )
                                    st.session_state[f"editing_monitored_{p['id']}"] = False
                                    st.success(f"Busca atualizada para '{edit_kw.strip()}' com sucesso!")
                                    st.rerun()
                        with btn_c2:
                            if st.form_submit_button("❌ Cancelar", use_container_width=True):
                                st.session_state[f"editing_monitored_{p['id']}"] = False
                                st.rerun()
                else:
                    c_title, c_curr, c_target, c_actions = st.columns([3, 2, 2, 3])
                    with c_title:
                        status_badge = "🟢 Ativo" if p["is_active"] else "⚪ Pausado"
                        st.markdown(f"### {p['keyword']}")
                        st.caption(f"Status: {status_badge} | Última checagem: {p['last_checked_at'] or 'Pendente'}")
                    with c_curr:
                        curr_p = p.get("current_lowest_price")
                        if curr_p is not None and curr_p > 0:
                            curr_str = f"R$ {curr_p:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                        else:
                            curr_str = "Aguardando checagem"
                        store_info = p.get("lowest_store") or "Aguardando checagem"
                        st.metric("Menor Preço Atual", curr_str, help=f"Loja: {store_info}")
                    with c_target:
                        target_p = p.get("target_price")
                        if target_p is not None and target_p > 0:
                            target_str = f"R$ {target_p:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                        else:
                            target_str = "Qualquer queda"
                        st.metric("Preço-Alvo", target_str)

                    with c_actions:
                        st.write("")
                        col_btn1, col_btn2, col_btn3, col_btn4 = st.columns(4)
                        with col_btn1:
                            if st.button("⚡ Checar", key=f"check_{p['id']}", help="Verificar preço e notificar WhatsApp agora"):
                                with st.spinner(f"Consultando '{p['keyword']}'..."):
                                    check_single_product(p, force_notify=True)
                                    st.success("Verificado e notificado!")
                                    st.rerun()
                        with col_btn2:
                            if st.button("✏️ Editar", key=f"edit_{p['id']}", help="Editar termo de busca e preço-alvo"):
                                st.session_state[f"editing_monitored_{p['id']}"] = True
                                st.rerun()
                        with col_btn3:
                            toggle_lbl = "Pausar" if p["is_active"] else "Ativar"
                            if st.button(toggle_lbl, key=f"toggle_{p['id']}"):
                                DatabaseManager.toggle_product_active(p["id"], not p["is_active"])
                                st.rerun()
                        with col_btn4:
                            if st.button("🗑️ Excluir", key=f"del_{p['id']}"):
                                DatabaseManager.delete_monitored_product(p["id"])
                                st.rerun()

                    # Detalhes da Busca e da Oferta no Layout Web
                    with st.expander("🔍 Detalhes da Busca & Última Oferta"):
                        d_col1, d_col2 = st.columns([3, 2])
                        with d_col1:
                            last_title = p.get("last_title") or (p.get("lowest_store") and f"Oferta em {p.get('lowest_store')}") or "Nenhum título registrado ainda"
                            st.markdown(f"**📦 Produto Identificado:** {last_title}")
                            st.markdown(f"**🏪 Loja Campeã:** {p.get('lowest_store') or 'Pendente de checagem'}")
                            if p.get("lowest_link"):
                                st.markdown(f"[🔗 **Abrir Produto na Loja Oficial**]({p['lowest_link']})")
                        with d_col2:
                            st.markdown(f"**📅 Última Varredura:** `{p.get('last_checked_at') or 'Pendente'}`")
                            if curr_p and target_p and target_p > 0:
                                diff = curr_p - target_p
                                if diff <= 0:
                                    st.success(f"🎯 **Preço-alvo atingido!** Economia de R$ {abs(diff):,.2f}")
                                else:
                                    st.info(f"⏳ **Faltam R$ {diff:,.2f}** para alcançar o preço-alvo.")

# ==========================================
# ABA 3: HISTÓRICO & GRÁFICOS
# ==========================================
with tab_history:
    st.header("📈 Histórico e Variação de Preços")
    st.write("Acompanhe como o preço dos produtos evoluiu ao longo do tempo para certificar se a promoção é real ou 'metade do dobro'.")

    history_data = DatabaseManager.get_price_history()
    if not history_data:
        st.info("Ainda não há registros de preços no histórico. Realize uma busca para começar a alimentar os gráficos.")
    else:
        df_hist = pd.DataFrame(history_data)
        products_list = sorted(list(df_hist["keyword"].unique()))
        col_sel, col_act = st.columns([3, 1])
        with col_sel:
            selected_prod = st.selectbox("Selecione o produto para visualizar a evolução:", products_list)
        with col_act:
            st.write("")
            st.write("")
            show_edit_hist = st.button("✏️ Editar Busca", key="btn_show_edit_hist", use_container_width=True, help="Renomear ou gerenciar esta busca no histórico")

        if show_edit_hist or st.session_state.get("show_edit_hist_active", False):
            st.session_state["show_edit_hist_active"] = True
            with st.container(border=True):
                st.markdown(f"### ✏️ Renomear / Editar Busca: **{selected_prod}**")
                col_e1, col_e2, col_e3 = st.columns([3, 1, 1])
                with col_e1:
                    new_hist_kw = st.text_input("Novo nome / termo de busca para este produto:", value=selected_prod, key="input_edit_hist_kw")
                with col_e2:
                    st.write("")
                    st.write("")
                    if st.button("💾 Salvar Nome", type="primary", use_container_width=True):
                        if new_hist_kw and new_hist_kw.strip() != selected_prod:
                            count = DatabaseManager.rename_history_keyword(selected_prod, new_hist_kw.strip())
                            st.session_state["show_edit_hist_active"] = False
                            st.success(f"Busca renomeada para '{new_hist_kw.strip()}' ({count} registros atualizados)!")
                            st.rerun()
                with col_e3:
                    st.write("")
                    st.write("")
                    if st.button("❌ Fechar", use_container_width=True):
                        st.session_state["show_edit_hist_active"] = False
                        st.rerun()

                with st.expander("🗑️ Excluir todos os registros desta busca do histórico"):
                    st.warning(f"Isso apagará permanentemente todos os registros de preço de '{selected_prod}'.")
                    if st.button(f"Confirmar Exclusão de '{selected_prod}'", type="secondary"):
                        DatabaseManager.delete_history_by_keyword(selected_prod)
                        st.session_state["show_edit_hist_active"] = False
                        st.success(f"Registros de '{selected_prod}' excluídos com sucesso!")
                        st.rerun()

        # Estatísticas do Produto Selecionado
        stats = DatabaseManager.get_product_stats(selected_prod)
        s1, s2, s3, s4 = st.columns(4)
        with s1:
            st.metric("🏆 Menor Preço Já Visto", f"R$ {stats['min_price']:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        with s2:
            st.metric("📈 Maior Preço Já Visto", f"R$ {stats['max_price']:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        with s3:
            st.metric("📊 Preço Médio", f"R$ {stats['avg_price']:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        with s4:
            st.metric("📉 Variação Recente", f"{stats['diff_percent']}%", delta=f"{stats['diff_percent']}%", delta_color="inverse")

        df_filtered = df_hist[df_hist["keyword"] == selected_prod].copy()
        df_filtered["recorded_at"] = pd.to_datetime(df_filtered["recorded_at"])
        df_filtered = df_filtered.sort_values("recorded_at")

        # Detalhes da Busca e do Produto Registrado no Layout Web
        latest_record = df_filtered.iloc[-1] if not df_filtered.empty else None

        with st.container(border=True):
            st.subheader(f"🔍 Detalhes da Busca: {selected_prod}")
            d_col1, d_col2 = st.columns([3, 2])
            with d_col1:
                st.markdown(f"**Termo Pesquisado:** `{selected_prod}`")
                if latest_record is not None:
                    st.markdown(f"**📦 Produto Real Capturado:** {latest_record.get('title', 'N/A')}")
                    st.markdown(f"**🏪 Loja da Captura:** {latest_record.get('store', 'N/A')}")
            with d_col2:
                if latest_record is not None:
                    st.markdown(f"**📅 Data/Hora da Última Varredura:** `{str(latest_record.get('recorded_at'))[:19]}`")
                    p_reg = latest_record.get("price", 0)
                    st.markdown(f"**💰 Preço Capturado:** `R$ {p_reg:,.2f}`".replace(",", "X").replace(".", ",").replace("X", "."))
                    if latest_record.get("link"):
                        st.markdown(f"[🔗 **Abrir Oferta Original na Loja**]({latest_record['link']})")

        # Gráfico interativo com Plotly
        if HAS_PLOTLY:
            fig = px.line(
                df_filtered,
                x="recorded_at",
                y="price",
                markers=True,
                title=f"Evolução Temporal do Preço: {selected_prod}",
                labels={"price": "Preço (R$)", "recorded_at": "Data/Hora", "store": "Loja"},
                hover_data=["store", "title"]
            )
            fig.update_layout(xaxis_title="Data/Hora", yaxis_title="Preço (R$)", template="plotly_white")
            st.plotly_chart(fig, use_container_width=True)
        else:
            chart_df = df_filtered.set_index("recorded_at")[["price"]]
            st.subheader(f"Evolução de Preço: {selected_prod}")
            st.line_chart(chart_df)

        st.subheader("📋 Registros Detalhados no Banco de Dados")
        df_hist_table = df_filtered[["recorded_at", "price", "store", "title", "link"]].copy()
        df_hist_table["price"] = df_hist_table["price"].apply(lambda p: f"R$ {p:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        df_hist_table.columns = ["Data/Hora", "Preço", "Loja", "Título", "Link"]
        st.dataframe(
            df_hist_table,
            column_config={
                "Link": st.column_config.LinkColumn("Comprar / Ver Oferta")
            },
            use_container_width=True,
            hide_index=True
        )

        # Download do histórico do produto
        csv_hist = df_filtered.to_csv(index=False).encode("utf-8")
        st.download_button(
            label=f"📥 Baixar Histórico de '{selected_prod}' em CSV",
            data=csv_hist,
            file_name=f"historico_{selected_prod.replace(' ', '_')}.csv",
            mime="text/csv"
        )

# ==========================================
# ABA 4: CONFIGURAÇÕES & ALERTAS
# ==========================================
with tab_settings:
    st.header("⚙️ Configurações & Teste de Conexão")

    col_cfg1, col_cfg2 = st.columns(2)
    with col_cfg1:
        st.subheader("📱 Teste de Envio do CallMeBot (WhatsApp)")
        st.write("Dispare uma mensagem de teste imediata para verificar se o seu WhatsApp está recebendo notificações do bot com sucesso.")
        test_phone = st.text_input("Número para teste (com DDD e país):", value=saved_phone, placeholder="+5511999999999")
        if st.button("📲 Disparar Teste no WhatsApp"):
            with st.spinner("Enviando mensagem de teste via CallMeBot..."):
                res = CallMeBotNotifier.send_message(
                    message="🤖 *GH Price Search Bot Conectado!*\n\nSeu robô de monitoramento de preços, cupons e inteligência de custo-benefício está operando perfeitamente.",
                    phone=test_phone
                )
                if res.get("success"):
                    st.success("✅ Mensagem enviada com sucesso! Verifique seu WhatsApp.")
                    if res.get("warning"):
                        st.info(f"💡 {res['warning']}")
                    st.rerun()
                else:
                    st.error(f"❌ Falha no envio: {res.get('error')}")

    with col_cfg2:
        st.subheader("🔑 Chaves de API & Monitoramento")
        st.write("Gerencie os parâmetros de execução e chaves locais armazenadas com segurança no `.env`.")

        st.markdown(f"""
        - **Google Gemini AI:** `{'Configurada ✅' if Config.GEMINI_API_KEY else 'Ausente ❌'}`
        - **Serper.dev (Google Shopping):** `{'Configurada ✅' if Config.SERPER_API_KEY else 'Opcional (Não configurada) ⚪'}`
        - **Mercado Livre Token:** `{'Configurada ✅' if Config.MELI_ACCESS_TOKEN else 'Opcional (Não configurada) ⚪'}`
        - **CallMeBot API:** `{'Configurada ✅' if Config.CALLMEBOT_API_KEY else 'Ausente ❌'}`
        - **Banco Google Sheets (Drive):** `{'Conectado ✅' if Config.get_gsheets_credentials() else 'Não configurado (Usando SQLite Local) 💾'}`
        - **Frequência de Checagem Atual:** `{Config.CHECK_INTERVAL_MINUTES} minutos`
        """)

        if Config.get_gsheets_credentials():
            if st.button("🔄 Forçar Sincronização com Google Sheets"):
                with st.spinner("Sincronizando produtos com Google Sheets no Drive..."):
                    from src.database.gsheets_sync import GoogleSheetsSync
                    GoogleSheetsSync.sync_monitored_products()
                    st.success("Planilha no Google Drive atualizada com sucesso!")

        # Alteração dinâmica do intervalo
        with st.expander("⏱️ Ajustar Frequência de Monitoramento"):
            new_interval = st.number_input(
                "Intervalo entre checagens automáticas (em minutos):",
                min_value=5,
                max_value=1440,
                value=int(Config.CHECK_INTERVAL_MINUTES),
                step=15
            )
            if st.button("Salvar Novo Intervalo"):
                update_scheduler_interval(int(new_interval))
                st.success(f"Frequência atualizada para a cada {new_interval} minutos!")
                st.rerun()

        with st.expander("🔑 Atualizar Chaves de API no .env"):
            gemini_in = st.text_input("Nova Chave Gemini API:", type="password")
            serper_in = st.text_input("Nova Chave Serper.dev (Google Shopping):", type="password")
            meli_in = st.text_input("Novo Token Mercado Livre (MELI_ACCESS_TOKEN):", type="password")
            callmebot_in = st.text_input("Nova Chave CallMeBot API:", type="password")
            if st.button("Salvar Chaves"):
                if gemini_in:
                    Config.save_env_var("GEMINI_API_KEY", gemini_in)
                if serper_in:
                    Config.save_env_var("SERPER_API_KEY", serper_in)
                if meli_in:
                    Config.save_env_var("MELI_ACCESS_TOKEN", meli_in)
                if callmebot_in:
                    Config.save_env_var("CALLMEBOT_API_KEY", callmebot_in)
                st.success("Chaves atualizadas no arquivo .env!")
                st.rerun()

    st.markdown("---")
    st.subheader("📜 Log dos Últimos Alertas Disparados")
    alert_logs = DatabaseManager.get_alert_logs(limit=40)
    if not alert_logs:
        st.info("Nenhum alerta disparado ainda.")
    else:
        df_logs = pd.DataFrame(alert_logs)
        df_logs = df_logs[["sent_at", "phone", "status", "message"]]
        df_logs.columns = ["Data/Hora", "Telefone", "Status", "Mensagem"]
        st.dataframe(df_logs, use_container_width=True, hide_index=True)
