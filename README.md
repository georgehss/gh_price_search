# 🔍 GH Price Search & Deal Bot

Sistema inteligente de busca de produtos, menor preço, cupons ativos e avaliação de custo-benefício em toda a internet, com notificações estratégicas no WhatsApp via **CallMeBot** e análise via **Google Gemini AI**.

---

## 🚀 Principais Recursos

1. **Varredura Completa na Internet**:
   - **KaBuM!** (integração via API oficial de catálogo com preços à vista no Pix e fotos).
   - **Buscapé & Zoom** (agregando Amazon, Americanas, Casas Bahia, Magalu e centenas de lojas com nomes reais).
   - **Mercado Livre & Google Shopping** (integração paralela resiliente com fallbacks).
   - **Cuponomia & Promobit** (busca automatizada de cupons ativos por loja parceira e destaques da comunidade).
2. **Inteligência de Custo-Benefício com Gemini AI**:
   - Analisa as ofertas encontradas, reputação da loja e descontos.
   - Filtra ofertas duvidosas, acessórios falsos ou potenciais fraudes ("metade do dobro").
   - Gera um veredito executivo objetivo pronto para leitura no WhatsApp.
3. **Alertas Inteligentes no WhatsApp (CallMeBot)**:
   - Envia relatório instantâneo quando você pesquisa um produto.
   - Notifica silenciosamente no WhatsApp quando um produto monitorado bate seu **preço-alvo** ou atinge o **menor preço histórico**.
   - Evita mensagens de spam ou notificações repetitivas com controle de frequência.
4. **Painel Web Moderno (Streamlit)**:
   - **Busca Imediata**: pesquise qualquer produto sob demanda com 1 clique, cards visuais com fotos, persistência de resultados e exportação para CSV.
   - **Produtos Monitorados**: adicione itens, ajuste metas de preço e execute "Checar Todos Agora".
   - **Histórico & Gráficos**: visualização da evolução do preço ao longo do tempo com métricas de mínima, máxima e média.
   - **Configurações**: ajuste do intervalo de monitoramento em tempo real, teste imediato de envio para o WhatsApp e gestão de chaves.

---

## 🛠️ Como Configurar

### 1. Obter a Chave Gratuita do CallMeBot (WhatsApp)
1. Adicione o contato do CallMeBot no WhatsApp:
   - Número: `+34 644 44 49 43` ou `+34 644 20 82 14`
2. Envie exatamente esta mensagem de texto para ele:
   ```text
   I allow callmebot to send me messages
   ```
3. O bot responderá com a sua chave:
   ```text
   CallMeBot API Activated! Your API Key is: 123456
   ```

### 2. Obter a Chave do Google Gemini (Opcional, mas Recomendado)
1. Acesse o [Google AI Studio](https://aistudio.google.com/).
2. Clique em **Get API Key** e copie sua chave gratuita.

### 3. Configurar o arquivo `.env`
No diretório do projeto, abra o arquivo `.env` e preencha suas chaves:
```env
GEMINI_API_KEY=sua_chave_gemini_aqui
CALLMEBOT_API_KEY=sua_apikey_callmebot_aqui
DEFAULT_PHONE=+5511999999999
CHECK_INTERVAL_MINUTES=60
```
> *Nota: O número de WhatsApp também pode ser alterado a qualquer momento diretamente pelo Painel Web.*

---

## ▶️ Como Executar

### Opção 1: Com 1 Clique no Windows
Basta dar duplo clique no arquivo **`run_app.bat`**. O navegador abrirá automaticamente com o painel web.

### Opção 2: Pelo Terminal
```powershell
python -m streamlit run src/ui/app.py
```

---

## 📂 Estrutura de Arquivos

```
GH Price Search/
├── .env                      # Chaves de API e configurações locais
├── .env.example              # Modelo de configuração
├── requirements.txt          # Dependências Python
├── run_app.bat               # Atalho de execução para Windows
├── README.md                 # Guia completo do projeto
└── src/
    ├── config.py             # Gerenciamento de variáveis e recarga
    ├── database/
    │   ├── db.py             # Inicialização do banco SQLite
    │   └── models.py         # CRUD de produtos, histórico e alertas
    ├── scrapers/
    │   ├── base.py           # Modelos de dados e tratamento de preços
    │   ├── search_engine.py  # Coordenador de busca unificada paralela
    │   ├── kabum.py          # API oficial de catálogo KaBuM! (Pix, fotos, estoque)
    │   ├── google_shopping.py# Raspador de Google Shopping, Buscapé e Zoom
    │   ├── mercado_livre.py  # Raspador do Mercado Livre
    │   └── coupons.py        # Coletor dinâmico de cupons (Cuponomia por loja e Promobit)
    ├── ai/
    │   └── analyzer.py       # Avaliação de custo-benefício via Gemini AI
    ├── notifier/
    │   └── callmebot.py      # Formatador e despachador WhatsApp
    ├── scheduler/
    │   └── monitor.py        # Agendador contínuo em segundo plano (APScheduler)
    └── ui/
        └── app.py            # Dashboard completo Streamlit
```
