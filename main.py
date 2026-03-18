import streamlit as st
import pandas as pd
import datetime
import numpy as np
import plotly.express as px
from prophet import Prophet
from prophet.plot import plot_plotly
import plotly.graph_objects as go
from streamlit_gsheets import GSheetsConnection


# Configurar a página para sempre ser exibida em widescreen
st.set_page_config(
    page_title="BI - Beaver ERP", page_icon="assets/logo.png", layout="wide"
)

# ================== PALETA DE CORES ==================
CORES = {
    "primary": "#240eb3",
    "bg": "#e5e5e5",
    "surface": "#ffffff",
    "success": "#2e7d32",
    "danger": "#c62828",
    "warning": "#ed6c02",
    "info": "#3949ab",
    "text": "#1f1f1f",
    "muted": "#777777",
}

st.markdown(
    """
<style>
/* 1. Fundo Geral e Cabeçalho da Página */
.stApp {
    background-color: #e5e5e5;
}
header[data-testid="stHeader"] {
    display: none !important;
}
.block-container {
    padding-top: 1rem !important;
}

/* 2. REMOVER ESPAÇO DA SIDEBAR (O segredo está aqui) */

/* Esconde o cabeçalho da sidebar (onde fica o botão X) */
[data-testid="stSidebarHeader"] {
    display: none !important;
}

/* Zera o padding do topo da sidebar */
[data-testid="stSidebarContent"] {
    padding-top: 3rem !important;
}

/* Garante que o conteúdo interno suba tudo */
[data-testid="stSidebarUserContent"] {
    padding-top: 0rem !important;
    margin-top: -2.5rem !important; /* Ajuste esse valor se precisar subir mais */
}

/* 3. Estilos Visuais (Sidebar e Títulos) */
section[data-testid="stSidebar"] {
    background-color: #ffffff;
    border-right: 1px solid #dddddd;
}

h1, h2, h3, h4 {
    color: #240eb3;
}

.card {
    background-color: #ffffff;
    border-radius: 12px;
    padding: 16px;
    box-shadow: 0 2px 6px rgba(0,0,0,0.08);
}
</style>
""",
    unsafe_allow_html=True,
)

# --- FUNÇÕES EXISTENTES (Com pequenas adaptações) ---

conn = st.connection("gsheets", type=GSheetsConnection)
URL_PLANILHA = "https://docs.google.com/spreadsheets/d/16h7xSkJTfXDXm4VLdMQDU3LTsAdq4hzPTbllc4DuJZM/edit?gid=0#gid=0"  # Coloque o link do seu BI BEAVER aqui


# Esta função substitui a leitura local do Excel pela leitura da aba específica no Sheets
def carregar_planilha_metas_sheets(nome_aba):
    try:
        # Tenta ler a aba específica da meta (ex: "GERAL", "PAOLA", etc)
        df = conn.read(spreadsheet=URL_PLANILHA, worksheet=nome_aba)
        # Renomeia a primeira coluna para garantir compatibilidade
        df.rename(columns={df.columns[0]: "Categoria"}, inplace=True)
        return df
    except Exception as e:
        # Se der erro (ex: aba não existe), retorna DataFrame vazio
        st.error(f"Erro ao carregar meta da aba '{nome_aba}': {e}")
        return pd.DataFrame()


# @st.cache_data(ttl=600)  # Cache de 10 minutos para não travar o app
# @st.cache_data(ttl=60) # Para 1 minutoF:
# @st.cache_data(ttl=1800) # Para 30 minutos:
def carregar_dados_do_sheets():
    # Carrega Vendas
    df_vendas = conn.read(spreadsheet=URL_PLANILHA, worksheet="Vendas")

    # Carrega Financeiro
    df_receber = conn.read(spreadsheet=URL_PLANILHA, worksheet="Receber")
    df_pagar = conn.read(spreadsheet=URL_PLANILHA, worksheet="Pagar")

    # Carrega Feriados
    df_feriados = conn.read(
        spreadsheet=URL_PLANILHA, worksheet="Feriados", usecols=[0], header=None
    )

    return df_vendas, df_receber, df_pagar, df_feriados


def carregar_meta_vendedor_sheets(vendedor):
    # Se na sua planilha a aba geral chama "Meta - Geral"
    nome_aba = "Meta - Geral" if vendedor == "Todos" else vendedor

    try:
        df_meta = conn.read(spreadsheet=URL_PLANILHA, worksheet=nome_aba)
        df_meta.rename(columns={df_meta.columns[0]: "Categoria"}, inplace=True)
        return df_meta
    except:
        # Se não achar a aba do vendedor, carrega a geral por segurança
        return conn.read(spreadsheet=URL_PLANILHA, worksheet="Meta - Geral")


def gerar_analise_abc_clientes(df_vendas, com_cdp=True, nomes_cdp=None):
    """
    Calcula a Curva ABC de clientes com base no valor total de vendas.

    Parâmetros:
    - df_vendas: DataFrame com vendas.
    - com_cdp: Booleano, se True inclui vendas da Casa do Pedreiro.
    - nomes_cdp: lista com os nomes dos clientes da Casa do Pedreiro para filtro.
    """

    if df_vendas is None or df_vendas.empty:
        return None

    # Aplicar filtro para Casa do Pedreiro, se necessário
    if not com_cdp and nomes_cdp is not None:
        df_vendas = df_vendas[~df_vendas["CLI_RAZ"].isin(nomes_cdp)]
        if df_vendas.empty:
            # Opcional: aqui pode emitir um aviso, mas isso depende do contexto de uso
            print("⚠️ Nenhuma venda encontrada após filtro 'Casa do Pedreiro'.")

    # Agrupar vendas por cliente
    vendas_por_cliente = (
        df_vendas.groupby("CLI_RAZ")["PED_TOTAL"]
        .sum()
        .sort_values(ascending=False)
        .reset_index()
    )
    vendas_por_cliente.rename(columns={"PED_TOTAL": "Valor Total Vendas"}, inplace=True)

    # Calcular porcentagem de participação e acumulada
    vendas_por_cliente["% Participação"] = (
        vendas_por_cliente["Valor Total Vendas"]
        / vendas_por_cliente["Valor Total Vendas"].sum()
    )
    vendas_por_cliente["% Acumulada"] = vendas_por_cliente["% Participação"].cumsum()

    # Classificar clientes em A, B e C
    def classificar_abc(perc_acumulado):
        if perc_acumulado <= 0.8:
            return "A"  # 80% do faturamento
        elif perc_acumulado <= 0.95:
            return "B"  # Próximos 15% do faturamento
        else:
            return "C"  # Últimos 5% do faturamento

    vendas_por_cliente["Classe"] = vendas_por_cliente["% Acumulada"].apply(
        classificar_abc
    )

    return vendas_por_cliente


def preparar_dados_fluxo_caixa(
    df_receber, df_pagar, saldo_inicial, data_inicio_filtro, data_fim_filtro
):
    """
    Consolida e calcula o fluxo de caixa PREVISTO e REALIZADO com tratamento de erros de tipo.
    """
    # --- 1. TRATAMENTO DE TIPOS (Garantir que valores sejam números e datas sejam datetime) ---
    df_receber = df_receber.copy()
    df_pagar = df_pagar.copy()

    # Converter valores para numérico (o que não for número vira 0)
    df_receber["Valor"] = pd.to_numeric(df_receber["Valor"], errors="coerce").fillna(0)
    df_pagar["Valor"] = pd.to_numeric(df_pagar["Valor"], errors="coerce").fillna(0)
    if "VALOR_PAGO" in df_pagar.columns:
        df_pagar["VALOR_PAGO"] = pd.to_numeric(
            df_pagar["VALOR_PAGO"], errors="coerce"
        ).fillna(0)

    # Garantir que as colunas de data estejam no formato datetime do Pandas
    df_receber["Data Vencimento"] = pd.to_datetime(
        df_receber["Data Vencimento"], errors="coerce"
    )
    df_pagar["Data Vencimento"] = pd.to_datetime(
        df_pagar["Data Vencimento"], errors="coerce"
    )
    df_receber["Data_Baixa"] = pd.to_datetime(df_receber["Data_Baixa"], errors="coerce")
    df_pagar["Data_Baixa"] = pd.to_datetime(df_pagar["Data_Baixa"], errors="coerce")

    # --- 2. FLUXO PREVISTO (baseado em Data Vencimento de contas EM ABERTO) ---
    receber_previsto = df_receber[df_receber["Status"] == "EM ABERTO"].copy()
    pagar_previsto = df_pagar[df_pagar["Status"] == "EM ABERTO"].copy()

    entradas_prev = (
        receber_previsto.groupby("Data Vencimento")["Valor"]
        .sum()
        .rename("Entradas_Previstas")
    )
    saidas_prev = (
        pagar_previsto.groupby("Data Vencimento")["Valor"]
        .sum()
        .rename("Saídas_Previstas")
    )
    fluxo_prev_df = pd.concat([entradas_prev, saidas_prev], axis=1)

    # --- 3. FLUXO REALIZADO (baseado em Data Baixa de contas PAGAS) ---
    receber_real = df_receber[df_receber["Status"] == "PAGO"].copy()
    pagar_real = df_pagar[df_pagar["Status"] == "PAGO"].copy()

    entradas_real = (
        receber_real.groupby("Data_Baixa")["Valor"].sum().rename("Entradas_Realizadas")
    )
    saidas_real = (
        pagar_real.groupby("Data_Baixa")["VALOR_PAGO"].sum().rename("Saídas_Realizadas")
    )
    fluxo_real_df = pd.concat([entradas_real, saidas_real], axis=1)

    # --- 4. CONSOLIDAR TUDO ---
    fluxo_df = pd.concat([fluxo_prev_df, fluxo_real_df], axis=1).fillna(0)

    # Converter filtros de data para datetime para evitar erro de comparação
    dt_inicio = pd.to_datetime(data_inicio_filtro)
    dt_fim = pd.to_datetime(data_fim_filtro)

    idx_datas = pd.date_range(start=dt_inicio, end=dt_fim, freq="D")
    fluxo_df = fluxo_df.reindex(idx_datas, fill_value=0)

    # --- 5. CÁLCULOS FINAIS (Agora garantidos como numéricos) ---
    fluxo_df["Fluxo_Líquido_Previsto"] = (
        fluxo_df["Entradas_Previstas"] - fluxo_df["Saídas_Previstas"]
    )
    fluxo_df["Saldo_Acumulado_Previsto"] = (
        fluxo_df["Fluxo_Líquido_Previsto"].cumsum() + saldo_inicial
    )

    fluxo_df["Fluxo_Líquido_Realizado"] = (
        fluxo_df["Entradas_Realizadas"] - fluxo_df["Saídas_Realizadas"]
    )
    fluxo_df["Saldo_Acumulado_Realizado"] = (
        fluxo_df["Fluxo_Líquido_Realizado"].cumsum() + saldo_inicial
    )

    return fluxo_df.reset_index().rename(columns={"index": "Data"})


def criar_painel_financeiro_avancado(
    titulo,
    df_filtrado,
    coluna_valor,
    coluna_status,
    coluna_entidade,
    coluna_vencimento,
    coluna_inadimplencia=None,
):
    """
    Cria e exibe um painel financeiro avançado, com KPIs detalhados
    (Saldo, Atrasado, A Vencer, Pago) para ambas as abas.
    """
    import streamlit as st
    import plotly.express as px
    import datetime
    import numpy as np

    # Bloco do Título
    st.markdown(
        f"""
        <div style="
            background-color: #240eb3; padding: 15px; border-radius: 10px;
            text-align: center; margin-top: 10px; margin-bottom: 20px;
        ">
            <h3 style="color: #ffffff; margin: 0;">{titulo}</h3>
        </div>
    """,
        unsafe_allow_html=True,
    )

    if df_filtrado.empty:
        st.info(f"Não há dados de '{titulo}' para exibir com os filtros selecionados.")
        return

    # --- 1. CÁLCULOS DOS VALORES BASE ---
    valor_pago = df_filtrado[df_filtrado[coluna_status] == "PAGO"][coluna_valor].sum()
    df_em_aberto_original = df_filtrado[
        df_filtrado[coluna_status] == "EM ABERTO"
    ].copy()
    valor_em_aberto_total = df_em_aberto_original[coluna_valor].sum()

    # --- 2. LÓGICA UNIFICADA PARA CALCULAR ATRASADOS E A VENCER ---
    hoje = pd.to_datetime(datetime.date.today())

    # Criar status dinâmico para análise em todas as contas em aberto
    df_em_aberto_original["Status_Detalhado"] = np.where(
        df_em_aberto_original[coluna_vencimento] < hoje, "Atrasado", "A Vencer"
    )

    valor_atrasado = df_em_aberto_original[
        df_em_aberto_original["Status_Detalhado"] == "Atrasado"
    ][coluna_valor].sum()
    valor_a_vencer = df_em_aberto_original[
        df_em_aberto_original["Status_Detalhado"] == "A Vencer"
    ][coluna_valor].sum()

    # --- 3. CUSTOMIZAÇÃO DOS TEXTOS DOS KPIs ---
    if "Receber" in titulo:
        label_saldo = "💰 A Receber"
        label_atrasado = "🚨 Atrasado"
        label_a_vencer = "📂 A Vencer"
        label_pago = "✅ Recebido"
        status_grafico_pago = "Recebido"
    else:  # Para 'Pagar'
        label_saldo = "💰 A Pagar"
        label_atrasado = "🚨 Atrasado"
        label_a_vencer = "📂 A Vencer"
        label_pago = "✅ Pago"
        status_grafico_pago = "Pago"

    # --- 4. MONTAGEM E EXIBIÇÃO DOS KPIs ---
    bloco_saldo = f"""<div style="background-color: #240eb3; padding: 13px; border-radius: 10px; text-align: center; flex: 1; min-width: 150px;"><h4 style="color: #ffffff; margin: 3px; font-weight: 400;">{label_saldo}</h4><p style="color: #ffffff; font-size: 1.6rem; margin: 0; font-weight: 700;">R$ {valor_em_aberto_total:,.2f}</p></div>"""
    bloco_atrasado = f"""<div style="background-color: #c62828; padding: 13px; border-radius: 10px; text-align: center; flex: 1; min-width: 150px;"><h4 style="color: #ffffff; margin: 3px; font-weight: 400;">{label_atrasado}</h4><p style="color: #ffffff; font-size: 1.6rem; margin: 0; font-weight: 700;">R$ {valor_atrasado:,.2f}</p></div>"""
    bloco_a_vencer = f"""<div style="background-color: #ed6c02; padding: 13px; border-radius: 10px; text-align: center; flex: 1; min-width: 150px;"><h4 style="color: #ffffff; margin: 3px; font-weight: 400;">{label_a_vencer}</h4><p style="color: #ffffff; font-size: 1.6rem; margin: 0; font-weight: 700;">R$ {valor_a_vencer:,.2f}</p></div>"""
    bloco_pago = f"""<div style="background-color: #2e7d32; padding: 13px; border-radius: 10px; text-align: center; flex: 1; min-width: 150px;"><h4 style="color: #ffffff; margin: 3px; font-weight: 400;">{label_pago}</h4><p style="color: #ffffff; font-size: 1.6rem; margin: 0; font-weight: 700;">R$ {valor_pago:,.2f}</p></div>"""

    st.markdown(
        f"""<div style="display: flex; gap: 10px; justify-content: space-between; margin-bottom: 20px; flex-wrap: wrap;">{bloco_saldo}{bloco_atrasado}{bloco_a_vencer}{bloco_pago}</div>""",
        unsafe_allow_html=True,
    )

    # --- 5. GRÁFICOS E TABELAS ---
    df_donut = pd.DataFrame(
        [
            {"Status_Grafico": status_grafico_pago, "Valor": valor_pago},
            {"Status_Grafico": "Atrasado", "Valor": valor_atrasado},
            {"Status_Grafico": "A Vencer", "Valor": valor_a_vencer},
        ]
    )
    df_donut = df_donut[df_donut["Valor"] > 0]

    fig_donut = px.pie(
        df_donut,
        names="Status_Grafico",
        values="Valor",
        hole=0.4,
        color="Status_Grafico",
        color_discrete_map={
            status_grafico_pago: CORES["success"],
            "Atrasado": CORES["danger"],
            "A Vencer": CORES["warning"],
        },
    )

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("##### 📊 Composição por Status")
        fig_donut.update_layout(
            showlegend=True, height=350, margin=dict(l=10, r=10, t=40, b=10)
        )
        st.plotly_chart(fig_donut, use_container_width=True)
    with col2:
        st.markdown(f"##### 🏆 Top 5 Contas - Em Aberto")
        df_em_aberto = df_filtrado[df_filtrado[coluna_status] == "EM ABERTO"]

        if not df_em_aberto.empty:
            top_5 = (
                df_em_aberto.groupby(coluna_entidade)[coluna_valor]
                .sum()
                .nlargest(5)
                .sort_values(ascending=True)
                .reset_index()
            )
            top_5["nome_limpo"] = top_5[coluna_entidade].apply(
                lambda x: x.split(" - ", 1)[-1].strip()
            )
            limite = 25
            top_5["nome_resumido"] = top_5["nome_limpo"].apply(
                lambda x: x if len(x) <= limite else x[:limite] + "..."
            )

            fig_top5 = px.bar(
                top_5,
                y="nome_resumido",
                x=coluna_valor,
                orientation="h",
                text_auto=True,
                hover_data={"nome_limpo": True, coluna_valor: ":.2f"},
            )
            fig_top5.update_traces(marker_color="#240eb3", texttemplate="R$ %{x:,.2f}")
            fig_top5.update_layout(
                height=400,
                yaxis_title=None,
                xaxis_title="Valor (R$)",
                margin=dict(l=10, r=10, t=40, b=10),
                yaxis=dict(tickfont=dict(size=10)),
            )
            st.plotly_chart(fig_top5, use_container_width=True, key=f"top5_{titulo}")

        else:
            st.info("Não há contas em aberto para exibir no Top 5.")

    # Adicionar detalhamento para Contas a Pagar
    if "Pagar" in titulo:
        with st.expander("Ver detalhamento completo de Contas a Pagar"):
            df_filtrado = (
                df_filtrado.copy()
            )  # ou df_pagar.copy() se for esse o nome certo

            # --- Filtro por status ---
            status_opcoes = df_filtrado["Status"].dropna().unique().tolist()
            status_escolhido = st.multiselect(
                "Filtrar por status", status_opcoes, default=status_opcoes
            )
            df_filtrado = df_filtrado[df_filtrado["Status"].isin(status_escolhido)]

            # --- Filtro por fornecedor ---
            nome_opcoes = df_filtrado["Fornecedor"].dropna().unique().tolist()
            nome_escolhido = st.multiselect("Filtrar por fornecedor", nome_opcoes)
            if nome_escolhido:
                df_filtrado = df_filtrado[
                    df_filtrado["Fornecedor"].isin(nome_escolhido)
                ]

            # --- Ordenação ---
            colunas_ordenar = ["Valor", "Fornecedor", "Data Emissao", "Data_Vencimento"]
            ordenar_por = st.selectbox("Ordenar por", colunas_ordenar)
            crescente = st.checkbox("Ordem crescente", value=True)
            df_filtrado = df_filtrado.sort_values(by=ordenar_por, ascending=crescente)

            # --- Exibição da tabela formatada ---
            st.dataframe(
                df_filtrado.style.format(
                    {
                        "Valor": "R$ {:,.2f}",
                        "Data Emissao": "{:%d/%m/%Y}",
                        "Data_Vencimento": "{:%d/%m/%Y}",
                        "Data_Baixa": "{:%d/%m/%Y}",
                    },
                    na_rep="-",
                ),
                use_container_width=True,
            )

    # Análise de Inadimplência (continua funcionando apenas para Receber)
    if coluna_inadimplencia and coluna_inadimplencia in df_filtrado.columns:
        st.markdown("---")
        st.markdown(f"##### 🚨 Análise de Inadimplência")

        df_inadimplentes = df_filtrado[
            df_filtrado[coluna_inadimplencia] == "INADIMPLENTE"
        ].copy()

        if not df_inadimplentes.empty:

            # --- KPIs Específicos de Inadimplência ---
            total_inadimplente = df_inadimplentes[coluna_valor].sum()
            num_clientes_inadimplentes = df_inadimplentes[coluna_entidade].nunique()
            media_inadimplencia = (
                total_inadimplente / num_clientes_inadimplentes
                if num_clientes_inadimplentes > 0
                else 0
            )

            kpi1, kpi2, kpi3 = st.columns(3)
            with kpi1:
                st.metric("Valor Total Inadimplente", f"R$ {total_inadimplente:,.2f}")
            with kpi2:
                st.metric("Nº de Clientes Inadimplentes", num_clientes_inadimplentes)
            with kpi3:
                st.metric(
                    "Ticket Médio da Inadimplência", f"R$ {media_inadimplencia:,.2f}"
                )

            st.markdown("---")

            # --- Gráfico de Barras Aprimorado: Top 10 ---
            st.markdown(f"##### 🏆 Top 10 Clientes Inadimplentes")
            top_10_inadimplentes = (
                df_inadimplentes.groupby(coluna_entidade)[coluna_valor]
                .sum()
                .nlargest(10)
                .sort_values(ascending=True)
                .reset_index()
            )

            fig_top_inadimplencia = px.bar(
                top_10_inadimplentes,
                y=coluna_entidade,
                x=coluna_valor,
                orientation="h",
                text_auto=True,
                height=400,
            )
            fig_top_inadimplencia.update_traces(
                marker_color="#240eb3",  # Vermelho de alerta
                texttemplate="R$ %{x:,.2f}",
            )
            fig_top_inadimplencia.update_layout(
                yaxis_title=None,
                xaxis_title="Valor Inadimplente (R$)",
                margin=dict(l=10, r=10, t=30, b=10),
            )
            st.plotly_chart(fig_top_inadimplencia, use_container_width=True)

            # --- Tabela Expansível com Todos os Detalhes ---
            with st.expander("Ver lista completa de todos os clientes inadimplentes"):
                colunas_exibir = [
                    coluna_entidade,
                    coluna_valor,
                    "Data Vencimento",
                    "Data Emissao",
                ]

                df_inad = df_inadimplentes[colunas_exibir].copy()

                # --- Filtro por cliente ---
                clientes = df_inad[coluna_entidade].dropna().unique().tolist()
                clientes_escolhidos = st.multiselect("Filtrar por cliente", clientes)
                if clientes_escolhidos:
                    df_inad = df_inad[
                        df_inad[coluna_entidade].isin(clientes_escolhidos)
                    ]

                # --- Ordenação ---
                colunas_ordenar = [
                    coluna_valor,
                    coluna_entidade,
                    "Data Vencimento",
                    "Data Emissao",
                ]
                ordenar_por = st.selectbox("Ordenar por", colunas_ordenar)
                crescente = st.checkbox("Ordem crescente", value=False)
                df_inad = df_inad.sort_values(by=ordenar_por, ascending=crescente)

                # --- Exibir tabela formatada ---
                st.dataframe(
                    df_inad.style.format(
                        {
                            coluna_valor: "R$ {:,.2f}",
                            "Data Vencimento": "{:%d/%m/%Y}",
                            "Data Emissao": "{:%d/%m/%Y}",
                        },
                        na_rep="-",
                    ),
                    use_container_width=True,
                )

        else:
            st.success(
                "✅ Ótima notícia! Não há clientes inadimplentes no período selecionado."
            )


def carregar_dados_financeiros(df_receber, df_pagar):
    if df_receber is None or df_pagar is None:
        return None, None

    df_receber = df_receber.copy()
    df_pagar = df_pagar.copy()

    # --- CONTAS A RECEBER ---
    for col in ["Data Emissao", "Data Vencimento", "Data_Baixa"]:
        if col in df_receber.columns:
            df_receber[col] = pd.to_datetime(
                df_receber[col], dayfirst=True, errors="coerce"
            )

    df_receber["Valor"] = pd.to_numeric(df_receber["Valor"], errors="coerce").fillna(0)

    if "Cliente" in df_receber.columns:
        df_receber["Cliente"] = df_receber["Cliente"].astype(str).str.strip()
    if "Status" in df_receber.columns:
        df_receber["Status"] = df_receber["Status"].astype(str).str.strip()

    if "Inadimplência" in df_receber.columns:
        df_receber["Inadimplência"] = (
            df_receber["Inadimplência"].astype(str).str.strip().fillna("N/A")
        )
    else:
        df_receber["Inadimplência"] = "N/A"

    # --- CONTAS A PAGAR ---
    for col in ["Data Emissao", "Data Vencimento", "Data_Baixa"]:
        if col in df_pagar.columns:
            df_pagar[col] = pd.to_datetime(
                df_pagar[col], dayfirst=True, errors="coerce"
            )

    df_pagar["Valor"] = pd.to_numeric(df_pagar["Valor"], errors="coerce").fillna(0)

    if "Fornecedor" in df_pagar.columns:
        df_pagar["Fornecedor"] = df_pagar["Fornecedor"].astype(str).str.strip()
    if "Status" in df_pagar.columns:
        df_pagar["Status"] = df_pagar["Status"].astype(str).str.strip()

    return df_receber, df_pagar


def carregar_feriados(df_feriados_raw):
    if df_feriados_raw is None or df_feriados_raw.empty:
        return []

    df = df_feriados_raw.copy()
    # Assume que a data está na primeira coluna (índice 0)
    col_data = df.columns[0]

    df[col_data] = pd.to_datetime(df[col_data], dayfirst=True, errors="coerce")
    feriados = df[col_data].dt.date.tolist()
    return feriados


def filtrar_vendas(
    df_vendas_raw,
    mes_referencia=None,
    vendedor_selecionado=None,
    empresa_selecionada=None,  # <-- NOVO PARÂMETRO AQUI
    data_inicial=None,
    data_final=None,
    com_cdp=False,
):
    if df_vendas_raw is None or df_vendas_raw.empty:
        st.error("❌ Dados de vendas não encontrados no Google Sheets.")
        return pd.DataFrame()

    # Cria uma cópia para não alterar o original
    df_vendas = df_vendas_raw.copy()

    # --- INÍCIO DO TRATAMENTO ---
    df_vendas["DAT_CAD"] = pd.to_datetime(
        df_vendas["DAT_CAD"], dayfirst=True, errors="coerce"
    )

    # Remover espaços em branco das colunas de texto (incluindo EMPRESA se existir)
    cols_texto = [
        "VEN_NOME",
        "CLI_RAZ",
        "PED_OBS_INT",
        "PED_TIPO",
        "PED_STATUS",
        "EMPRESA",
    ]

    for col in cols_texto:
        if col in df_vendas.columns:
            df_vendas[col] = (
                df_vendas[col]
                .astype(str)
                .str.replace("\u00a0", " ", regex=False)
                .str.strip()
                .str.upper()
            )

    df_vendas["PED_TOTAL"] = pd.to_numeric(
        df_vendas["PED_TOTAL"], errors="coerce"
    ).fillna(0)

    # --- FILTROS DE DATA ---
    df_vendas["DAT_CAD_DATE"] = df_vendas["DAT_CAD"].dt.date

    if data_inicial and data_final:
        d_ini = (
            data_inicial
            if isinstance(data_inicial, datetime.date)
            else data_inicial.date()
        )
        d_fim = (
            data_final if isinstance(data_final, datetime.date) else data_final.date()
        )
        df_vendas = df_vendas[
            (df_vendas["DAT_CAD_DATE"] >= d_ini) & (df_vendas["DAT_CAD_DATE"] <= d_fim)
        ]
    elif mes_referencia:
        df_vendas = df_vendas[df_vendas["DAT_CAD"].dt.month == mes_referencia]
        ano_atual = datetime.date.today().year
        df_vendas = df_vendas[df_vendas["DAT_CAD"].dt.year == ano_atual]

    # --- FILTRO DE EMPRESA (NOVO) ---
    if empresa_selecionada and empresa_selecionada != "Todas":
        if "EMPRESA" in df_vendas.columns:
            df_vendas = df_vendas[df_vendas["EMPRESA"] == empresa_selecionada.upper()]

    # --- FILTRO DE VENDEDOR ---
    if vendedor_selecionado and vendedor_selecionado != "Todos":
        df_vendas = df_vendas[df_vendas["VEN_NOME"] == vendedor_selecionado]

    # --- FILTRO TIPO DE PEDIDO (Apenas 'V') ---
    if "PED_TIPO" in df_vendas.columns:
        df_vendas = df_vendas[df_vendas["PED_TIPO"].str.upper() == "V"]

    # --- FILTRO CASA DO PEDREIRO ---
    nomes_cdp = [
        "DO PEDREIRO DO LITORAL COMERC DE MATERIAIS DE CONSTRUCAO LTD",
        "DO PEDREIRO DO LITORAL COMERCIO DE MATERIAIS DE CONSTRUCAO",
    ]
    if not com_cdp:
        df_vendas = df_vendas[~df_vendas["CLI_RAZ"].isin(nomes_cdp)]

    return df_vendas


# --- FUNÇÃO PROCESSAR_VENDAS (Agora usa filtrar_vendas) ---
def processar_vendas(df_vendas_filtrado):
    if df_vendas_filtrado is None or df_vendas_filtrado.empty:
        return 0.0, 0.0

    df = df_vendas_filtrado.copy()

    # Identifica se é cliente DIGITAL
    cond_digital = df["CLI_RAZ"].str.contains("DIGITAL", na=False)

    # --- Lógica para OPD ---
    # Se não for DIGITAL: busca "OPD" em PED_OBS_INT
    # Se for DIGITAL: busca "E-COMMERCE" em PED_OBS_INFO (ou PED_OBS_INT se preferir)
    filtro_opd = (
        (~cond_digital) & (df["PED_OBS_INT"] == "OPD") & (df["PED_STATUS"] == "F")
    ) | (
        (cond_digital) & (df["PED_OBS_INT"] == "E-COMMERCE") & (df["PED_STATUS"] == "F")
    )
    total_opd = df[filtro_opd]["PED_TOTAL"].sum()

    # --- Lógica para DISTRIBUIÇÃO (AMC) ---
    # Se não for DIGITAL: busca termos de distribuição em PED_OBS_INT
    # Se for DIGITAL: busca "VENDA DIRETA" em PED_OBS_INFO
    termos_dist = [
        "DISTRIBICAO",
        "DISTRIBUICAO",
        "DISTRIBUIÇÃO",
        "DIATRIBUICAO",
        "LOJA",
    ]

    filtro_distribuicao = (
        (~cond_digital)
        & (df["PED_OBS_INT"].isin(termos_dist))
        & (df["PED_STATUS"].isin(["F", "N"]))
    ) | (
        (cond_digital)
        & (df["PED_OBS_INT"] == "VENDA DIRETA")
        & (df["PED_STATUS"].isin(["F", "N"]))
    )
    total_amc = df[filtro_distribuicao]["PED_TOTAL"].sum()

    return float(total_opd), float(total_amc)


# --- FUNÇÕES EXISTENTES (calcular_status, comparar_com_metas, gerar_grafico, calcular_dias_uteis) ---
def calcular_status(realizado, metas, mes_referencia, feriados):
    status = ""
    sobra = realizado
    dias_uteis_restantes = calcular_dias_uteis_restantes(
        mes_referencia, feriados=feriados, incluir_hoje=True  # Inclui hoje no cálculo
    )
    hoje = datetime.date.today()

    meses_portugues = [
        "janeiro",
        "fevereiro",
        "março",
        "abril",
        "maio",
        "junho",
        "julho",
        "agosto",
        "setembro",
        "outubro",
        "novembro",
        "dezembro",
    ]
    mes_nome = meses_portugues[mes_referencia - 1]

    for nome_meta, valor_meta in metas.items():
        if sobra >= valor_meta:
            diferenca = sobra - valor_meta
            status += f"✅ Bateu a {nome_meta} (Meta: R$ {valor_meta:,.2f}) com uma diferença de R$ {diferenca:,.2f}\n"
            sobra -= valor_meta
        else:
            status += f"➡️ Falta R$ {valor_meta - sobra:,.2f} para {nome_meta}\n"
            if dias_uteis_restantes > 0:
                venda_diaria = (valor_meta - sobra) / dias_uteis_restantes
                status += f"📅 Considerando hoje ({hoje.strftime('%d/%m')}), precisamos vender R$ {venda_diaria:,.2f} por dia.\n"
            else:
                status += f"📅 Não há mais dias úteis neste mês para vender.\n"
            break
    return status


def comparar_com_metas(planilha_metas, mes_referencia, total_opd, total_amc):
    # 1. Mapeamento dos meses (exatamente como você tinha)
    meses = [
        "jan",
        "fev",
        "mar",
        "abr",
        "mai",
        "jun",
        "jul",
        "ago",
        "set",
        "out",
        "nov",
        "dez",
    ]

    # Prevenção: Garante que o índice do mês seja válido
    if not (1 <= mes_referencia <= 12):
        return {}

    mes_coluna = meses[mes_referencia - 1]

    try:
        # 2. Limpeza de segurança: Remove espaços extras dos nomes das colunas e das categorias
        # Isso evita que "jan " (com espaço) seja diferente de "jan"
        planilha_metas.columns = [
            str(c).strip().lower() for c in planilha_metas.columns
        ]
        mes_coluna = mes_coluna.strip().lower()

        if "categoria" in planilha_metas.columns:
            planilha_metas["categoria"] = (
                planilha_metas["categoria"].astype(str).str.strip()
            )
        else:
            # Se a primeira coluna não se chamar 'Categoria', tentamos renomear a primeira
            planilha_metas.rename(
                columns={planilha_metas.columns[0]: "categoria"}, inplace=True
            )

        # 3. Função interna para buscar valores sem travar o código
        def buscar_v(nome_categoria):
            try:
                # Busca a linha onde a categoria bate (ignorando maiúsculas/minúsculas)
                filtro = planilha_metas[
                    planilha_metas["categoria"].str.upper() == nome_categoria.upper()
                ]

                if filtro.empty or mes_coluna not in planilha_metas.columns:
                    return 0.0

                valor = filtro[mes_coluna].values[0]

                # Se o valor for uma string (ex: "1.500,00"), limpa para virar número
                if isinstance(valor, str):
                    valor = (
                        valor.replace("R$", "")
                        .replace(".", "")
                        .replace(",", ".")
                        .strip()
                    )

                return float(valor) if pd.notnull(valor) and valor != "" else 0.0
            except:
                return 0.0

        # 4. Busca os valores usando a proteção
        meta_opd = buscar_v("META AN OPD")
        meta_desaf_opd = buscar_v("META DESAF OPD")
        meta_distri = buscar_v("META AN DISTRI")
        meta_desaf_distri = buscar_v("META DESAF DISTRI")
        super_meta_distri = buscar_v("SUPER META DISTRI")

        # 5. Retorna o dicionário no formato que o seu código espera
        return {
            "OPD": {
                "Realizado": total_opd,
                "Meta Mensal": meta_opd,
                "Meta Desafio": meta_desaf_opd,
            },
            "AMC": {
                "Realizado": total_amc,
                "Meta Mensal": meta_distri,
                "Meta Desafio": meta_desaf_distri,
                "Super Meta": super_meta_distri,
            },
        }

    except Exception as e:
        st.error(f"❌ Erro ao processar metas: {e}")
        return {}


def gerar_grafico(categoria, dados, titulo):
    df = pd.DataFrame({"Tipo": list(dados.keys()), "Valor": list(dados.values())})
    fig = px.bar(
        df,
        x="Tipo",
        y="Valor",
        color="Tipo",
        color_discrete_sequence=["#313334 ", "#240eb3", "#5c6bc0 ", "#9fa8da "],
        title=titulo,
        text_auto=True,  # Mostra valores nas barras
    )
    fig.update_traces(texttemplate="R$ %{y:,.2f}", textposition="outside")
    fig.update_layout(yaxis_title="Valor (R$)")
    return fig


def calcular_dias_uteis_restantes(mes_referencia, incluir_hoje=True, feriados=None):
    hoje = datetime.date.today()
    ano = hoje.year

    if ano > hoje.year or (ano == hoje.year and mes_referencia < hoje.month):
        return 0

    if mes_referencia == hoje.month:
        data_inicio = hoje
    else:
        data_inicio = datetime.date(ano, mes_referencia, 1)

    if mes_referencia == 12:
        ultimo_dia = datetime.date(ano, 12, 31)
    else:
        ultimo_dia = datetime.date(ano, mes_referencia + 1, 1) - datetime.timedelta(
            days=1
        )

    dias = pd.date_range(data_inicio, ultimo_dia).to_list()
    feriados = feriados or []

    dias_uteis_count = 0
    for dia in dias:
        dia_date = dia.date()
        if dia.weekday() < 5 and dia_date not in feriados:
            if incluir_hoje:
                dias_uteis_count += 1
            elif dia_date > hoje:
                dias_uteis_count += 1
    return dias_uteis_count


def calcular_dias_uteis_passados(mes_referencia, incluir_hoje=False, feriados=None):
    hoje = datetime.date.today()
    ano = hoje.year
    feriados = feriados or []

    primeiro_dia = datetime.date(ano, mes_referencia, 1)
    dia_final = min(
        hoje,
        (
            datetime.date(ano, mes_referencia + 1, 1) - datetime.timedelta(days=1)
            if mes_referencia < 12
            else datetime.date(ano, 12, 31)
        ),
    )

    dias = pd.date_range(primeiro_dia, dia_final).to_list()
    dias_uteis_count = 0
    for dia in dias:
        dia_date = dia.date()
        if dia.weekday() < 5 and dia_date not in feriados:
            if incluir_hoje or dia_date < hoje:
                dias_uteis_count += 1
    return dias_uteis_count


# --- NOVAS FUNÇÕES PARA TABELAS ---


def gerar_tabela_diaria_empresa(df_vendas_filtrado):
    if df_vendas_filtrado is None or df_vendas_filtrado.empty:
        st.info("Nenhuma venda encontrada para gerar o relatório diário da empresa.")
        return pd.DataFrame()

    df = df_vendas_filtrado.copy()

    # CÓDIGO NOVO E CORRIGIDO
    # Condição para OPD: Observação é OPD E status é F
    cond_digital = df["CLI_RAZ"].str.contains("DIGITAL", na=False)

    # -------------------
    # OPD
    # -------------------
    cond_opd = (
        # REGRA NORMAL
        ((df["PED_OBS_INT"] == "OPD") & (df["PED_STATUS"] == "F") & ~cond_digital)
        |
        # REGRA DIGITAL
        (
            cond_digital
            & df["PED_OBS_INT"].isin(["E-COMMERCE"])
            & (df["PED_STATUS"] == "F")
        )
    )

    # -------------------
    # DISTRIBUIÇÃO
    # -------------------
    cond_dist = (
        # REGRA NORMAL
        (
            df["PED_OBS_INT"].isin(
                ["DISTRIBICAO", "DISTRIBUICAO", "DISTRIBUIÇÃO", "LOJA"]
            )
            & df["PED_STATUS"].isin(["F", "N"])
            & ~cond_digital
        )
        |
        # REGRA DIGITAL
        (
            cond_digital
            & df["PED_OBS_INT"].isin(["VENDA DIRETA"])
            & df["PED_STATUS"].isin(["F", "N"])
        )
    )

    # Aplicar as condições usando np.select para criar a coluna 'Tipo Venda'
    df["Tipo Venda"] = np.select(
        [cond_opd, cond_dist],  # Lista de condições a serem checadas
        ["OPD", "Distribuição"],  # Lista de valores correspondentes
        default="Outros",  # Valor padrão se nenhuma condição for atendida
    )
    df_validos = df[df["Tipo Venda"].isin(["OPD", "Distribuição"])]

    tabela = pd.pivot_table(
        df_validos,
        values="PED_TOTAL",
        index=df_validos["DAT_CAD"].dt.date,
        columns="Tipo Venda",
        aggfunc=np.sum,
        fill_value=0,
    )

    if "OPD" not in tabela.columns:
        tabela["OPD"] = 0
    if "Distribuição" not in tabela.columns:
        tabela["Distribuição"] = 0

    tabela["Total Dia"] = tabela["OPD"] + tabela["Distribuição"]
    tabela = tabela.sort_index(ascending=True)

    total_geral = tabela.sum().to_frame().T
    total_geral.index = ["**TOTAL GERAL**"]
    tabela = pd.concat([tabela, total_geral])

    tabela.index = [
        idx.strftime("%d/%m/%Y") if isinstance(idx, datetime.date) else idx
        for idx in tabela.index
    ]
    tabela = tabela.reset_index().rename(columns={"index": "Data"})

    for col in ["OPD", "Distribuição", "Total Dia"]:
        tabela[col] = tabela[col].apply(lambda x: f"R$ {x:,.2f}")
    return tabela


def gerar_tabela_geral(df_vendas_filtrado):
    if df_vendas_filtrado is None or df_vendas_filtrado.empty:
        st.info("Nenhuma venda encontrada para gerar o relatório geral.")
        return pd.DataFrame()

    df = df_vendas_filtrado.copy()

    # CÓDIGO NOVO E CORRIGIDO
    # Condição para OPD: Observação é OPD E status é F
    cond_digital = df["CLI_RAZ"].str.contains("DIGITAL", na=False)

    # -------------------
    # OPD
    # -------------------
    cond_opd = (
        # REGRA NORMAL
        ((df["PED_OBS_INT"] == "OPD") & (df["PED_STATUS"] == "F") & ~cond_digital)
        |
        # REGRA DIGITAL
        (
            cond_digital
            & df["PED_OBS_INT"].isin(["E-COMMERCE"])
            & (df["PED_STATUS"] == "F")
        )
    )

    # -------------------
    # DISTRIBUIÇÃO
    # -------------------
    cond_dist = (
        # REGRA NORMAL
        (
            df["PED_OBS_INT"].isin(
                ["DISTRIBICAO", "DISTRIBUICAO", "DISTRIBUIÇÃO", "LOJA"]
            )
            & df["PED_STATUS"].isin(["F", "N"])
            & ~cond_digital
        )
        |
        # REGRA DIGITAL
        (
            cond_digital
            & df["PED_OBS_INT"].isin(["VENDA DIRETA"])
            & df["PED_STATUS"].isin(["F", "N"])
        )
    )

    # Aplicar as condições usando np.select para criar a coluna 'Tipo Venda'
    df["Tipo Venda"] = np.select(
        [cond_opd, cond_dist],  # Lista de condições a serem checadas
        ["OPD", "Distribuição"],  # Lista de valores correspondentes
        default="Outros",  # Valor padrão se nenhuma condição for atendida
    )
    df_validos = df[df["Tipo Venda"].isin(["OPD", "Distribuição"])]

    tabela = pd.pivot_table(
        df_validos,
        values="PED_TOTAL",
        index="VEN_NOME",
        columns="Tipo Venda",
        aggfunc=np.sum,
        fill_value=0,
    )

    if "OPD" not in tabela.columns:
        tabela["OPD"] = 0
    if "Distribuição" not in tabela.columns:
        tabela["Distribuição"] = 0

    tabela["Total Vendedor"] = tabela["OPD"] + tabela["Distribuição"]
    tabela = tabela.sort_values(by="Total Vendedor", ascending=False)

    total_geral = tabela.sum().to_frame().T
    total_geral.index = ["**TOTAL GERAL**"]
    tabela = pd.concat([tabela, total_geral])

    for col in ["OPD", "Distribuição", "Total Vendedor"]:
        tabela[col] = tabela[col].apply(lambda x: f"R$ {x:,.2f}")
    return tabela.reset_index().rename(columns={"VEN_NOME": "Vendedor"})


def gerar_tabela_vendedor(df_vendas_filtrado):
    if df_vendas_filtrado is None or df_vendas_filtrado.empty:
        st.info("Nenhuma venda encontrada para este vendedor no período.")
        return pd.DataFrame(), {}

    df = df_vendas_filtrado.copy()

    # CÓDIGO NOVO E CORRIGIDO
    # Condição para OPD: Observação é OPD E status é F
    cond_digital = df["CLI_RAZ"].str.contains("DIGITAL", na=False)

    # -------------------
    # OPD
    # -------------------
    cond_opd = (
        # REGRA NORMAL
        ((df["PED_OBS_INT"] == "OPD") & (df["PED_STATUS"] == "F") & ~cond_digital)
        |
        # REGRA DIGITAL
        (
            cond_digital
            & df["PED_OBS_INT"].isin(["E-COMMERCE"])
            & (df["PED_STATUS"] == "F")
        )
    )

    # -------------------
    # DISTRIBUIÇÃO
    # -------------------
    cond_dist = (
        # REGRA NORMAL
        (
            df["PED_OBS_INT"].isin(
                ["DISTRIBICAO", "DISTRIBUICAO", "DISTRIBUIÇÃO", "LOJA"]
            )
            & df["PED_STATUS"].isin(["F", "N"])
            & ~cond_digital
        )
        |
        # REGRA DIGITAL
        (
            cond_digital
            & df["PED_OBS_INT"].isin(["VENDA DIRETA"])
            & df["PED_STATUS"].isin(["F", "N"])
        )
    )

    # Aplicar as condições usando np.select para criar a coluna 'Tipo Venda'
    df["Tipo Venda"] = np.select(
        [cond_opd, cond_dist],  # Lista de condições a serem checadas
        ["OPD", "Distribuição"],  # Lista de valores correspondentes
        default="Outros",  # Valor padrão se nenhuma condição for atendida
    )
    df_validos = df[df["Tipo Venda"].isin(["OPD", "Distribuição"])]

    total_opd = df_validos[df_validos["Tipo Venda"] == "OPD"]["PED_TOTAL"].sum()
    total_dist = df_validos[df_validos["Tipo Venda"] == "Distribuição"][
        "PED_TOTAL"
    ].sum()
    totais = {
        "OPD": total_opd,
        "Distribuição": total_dist,
        "Total": total_opd + total_dist,
    }

    tabela = df_validos[
        ["DAT_CAD", "VEN_NOME", "CLI_RAZ", "PED_TOTAL", "Tipo Venda"]
    ].copy()

    tabela.rename(
        columns={
            "VEN_NOME": "Vendedor",
            "CLI_RAZ": "Cliente",
            "PED_TOTAL": "Valor",
        },
        inplace=True,
    )

    tabela = tabela.sort_values(by="DAT_CAD", ascending=True)
    tabela["Data"] = tabela["DAT_CAD"].dt.strftime("%d/%m/%Y")
    tabela["Valor"] = tabela["Valor"].apply(lambda x: f"R$ {x:,.2f}")

    tabela_final = tabela[["Data", "Vendedor", "Cliente", "Valor", "Tipo Venda"]]
    return tabela_final, totais


def gerar_dados_ranking(df_vendas_filtrado):
    """
    Prepara os dados para o ranking de vendedores, mantendo os valores numéricos.
    """
    if df_vendas_filtrado is None or df_vendas_filtrado.empty:
        return pd.DataFrame()

    df = df_vendas_filtrado.copy()
    # CÓDIGO NOVO E CORRIGIDO
    # Condição para OPD: Observação é OPD E status é F
    cond_digital = df["CLI_RAZ"].str.contains("DIGITAL", na=False)

    # -------------------
    # OPD
    # -------------------
    cond_opd = (
        # REGRA NORMAL
        ((df["PED_OBS_INT"] == "OPD") & (df["PED_STATUS"] == "F") & ~cond_digital)
        |
        # REGRA DIGITAL
        (
            cond_digital
            & df["PED_OBS_INT"].isin(["E-COMMERCE"])
            & (df["PED_STATUS"] == "F")
        )
    )

    # -------------------
    # DISTRIBUIÇÃO
    # -------------------
    cond_dist = (
        # REGRA NORMAL
        (
            df["PED_OBS_INT"].isin(
                ["DISTRIBICAO", "DISTRIBUICAO", "DISTRIBUIÇÃO", "LOJA"]
            )
            & df["PED_STATUS"].isin(["F", "N"])
            & ~cond_digital
        )
        |
        # REGRA DIGITAL
        (
            cond_digital
            & df["PED_OBS_INT"].isin(["VENDA DIRETA"])
            & df["PED_STATUS"].isin(["F", "N"])
        )
    )

    # Aplicar as condições usando np.select para criar a coluna 'Tipo Venda'
    df["Tipo Venda"] = np.select(
        [cond_opd, cond_dist],  # Lista de condições a serem checadas
        ["OPD", "Distribuição"],  # Lista de valores correspondentes
        default="Outros",  # Valor padrão se nenhuma condição for atendida
    )
    df_validos = df[df["Tipo Venda"].isin(["OPD", "Distribuição"])]

    tabela = pd.pivot_table(
        df_validos,
        values="PED_TOTAL",
        index="VEN_NOME",
        columns="Tipo Venda",
        aggfunc="sum",
        fill_value=0,
    )

    if "OPD" not in tabela.columns:
        tabela["OPD"] = 0
    if "Distribuição" not in tabela.columns:
        tabela["Distribuição"] = 0

    return tabela.reset_index().rename(columns={"VEN_NOME": "Vendedor"})


# --- CARREGAMENTO INICIAL DOS DADOS (NO INÍCIO DO SCRIPT) ---
try:
    with st.spinner("Carregando dados do BI BEAVER..."):
        # Chama a função que busca tudo do Sheets de uma vez
        vendas_raw, df_receber, df_pagar, feriados_raw = carregar_dados_do_sheets()
        df_receber, df_pagar = carregar_dados_financeiros(df_receber, df_pagar)

        # Processa a lista de feriados
        feriados_list = carregar_feriados(feriados_raw)
except Exception as e:
    st.error(f"Erro ao conectar com o Google Sheets: {e}")
    st.stop()


# ================= SIDEBAR ORGANIZADA =================
with st.sidebar:

    # ===== HEADER =====
    st.markdown("# 🦫 BI BEAVER")

    # ===== NAVEGAÇÃO =====
    st.subheader("📍 Navegação")
    pagina_selecionada = st.radio(
        "Escolha a visualização:",
        ["Painel de Vendas", "Painel Financeiro"],
    )

    st.markdown(
        "<hr style='margin:8px 0; border:0.5px solid rgba(0,0,0,0.1);'>",
        unsafe_allow_html=True,
    )

    # ===== PERÍODO =====
    st.subheader("📅 Período")

    filtro_tipo = st.radio(
        "Tipo de filtro:", ["Mês", "Período Personalizado"], horizontal=True
    )

    mes_selecionado = None
    data_inicial, data_final = None, None

    if filtro_tipo == "Mês":
        mes_selecionado = st.selectbox(
            "Mês de referência",
            range(1, 13),
            format_func=lambda x: [
                "Janeiro",
                "Fevereiro",
                "Março",
                "Abril",
                "Maio",
                "Junho",
                "Julho",
                "Agosto",
                "Setembro",
                "Outubro",
                "Novembro",
                "Dezembro",
            ][x - 1],
            index=datetime.date.today().month - 1,
        )

        ano_atual = datetime.date.today().year
        data_inicial = datetime.date(ano_atual, mes_selecionado, 1)

        if mes_selecionado == 12:
            data_final = datetime.date(ano_atual, 12, 31)
        else:
            data_final = datetime.date(
                ano_atual, mes_selecionado + 1, 1
            ) - datetime.timedelta(days=1)

        st.caption(
            f"{data_inicial.strftime('%d/%m/%Y')} → {data_final.strftime('%d/%m/%Y')}"
        )

    else:
        data_intervalo = st.date_input(
            "Selecione o período",
            value=[datetime.date.today().replace(day=1), datetime.date.today()],
        )

        if len(data_intervalo) == 2:
            data_inicial, data_final = data_intervalo

            if data_inicial > data_final:
                st.error("⚠️ A data inicial não pode ser maior que a data final!")
                st.stop()

            mes_selecionado = data_final.month
        else:
            st.error("⚠️ Selecione uma data inicial e uma data final!")
            st.stop()

    st.markdown(
        "<hr style='margin:8px 0; border:0.5px solid rgba(0,0,0,0.1);'>",
        unsafe_allow_html=True,
    )

    # ===== EMPRESA =====
    st.subheader("🏢 Filtros")

    empresas_vendas = (
        vendas_raw["EMPRESA"]
        .dropna()
        .astype(str)
        .str.strip()
        .str.upper()
        .unique()
        .tolist()
        if vendas_raw is not None and "EMPRESA" in vendas_raw.columns
        else []
    )

    empresas_receber = (
        df_receber["EMPRESA"]
        .dropna()
        .astype(str)
        .str.strip()
        .str.upper()
        .unique()
        .tolist()
        if df_receber is not None and "EMPRESA" in df_receber.columns
        else []
    )

    empresas_pagar = (
        df_pagar["EMPRESA"]
        .dropna()
        .astype(str)
        .str.strip()
        .str.upper()
        .unique()
        .tolist()
        if df_pagar is not None and "EMPRESA" in df_pagar.columns
        else []
    )

    todas_empresas = sorted(
        [
            emp
            for emp in list(set(empresas_vendas + empresas_receber + empresas_pagar))
            if emp != "NAN"
        ]
    )

    empresa_selecionada = st.selectbox("Empresa", ["Todas"] + todas_empresas)

    # ===== FILTROS AVANÇADOS =====
    with st.expander("⚙️ Filtros Avançados"):

        vendedor_selecionado = "Todos"

        if pagina_selecionada != "Relatórios Financeiros":
            if vendas_raw is not None and not vendas_raw.empty:

                df_vendas_bruto = vendas_raw

                if (
                    empresa_selecionada != "Todas"
                    and "EMPRESA" in df_vendas_bruto.columns
                ):
                    df_vendedores_empresa = df_vendas_bruto[
                        df_vendas_bruto["EMPRESA"].astype(str).str.upper()
                        == empresa_selecionada
                    ]
                else:
                    df_vendedores_empresa = df_vendas_bruto

                vendedores_unicos_stripped = sorted(
                    list(
                        df_vendedores_empresa["VEN_NOME"]
                        .dropna()
                        .astype(str)
                        .str.strip()
                        .unique()
                    )
                )

                vendedores = ["Todos"] + vendedores_unicos_stripped

                vendedor_selecionado = st.selectbox("Vendedor", vendedores)

            else:
                st.error("❌ Dados de vendas não carregados.")
                st.stop()

        com_cdp = st.checkbox("Incluir Casa do Pedreiro", value=True)

# ================= TÍTULO =================
st.title(f"📈 {pagina_selecionada}")

# ================= VARIÁVEIS =================
feriados = feriados_list
df_vendas_bruto = vendas_raw

# ================= LÓGICA DE METAS =================
rose_loja = ["ROSESILVESTRE"]
paola_loja = ["PAOLA"]
jemine_loja = ["JEMINE OLIVEIRA"]
danilima_d = ["DANILIMA"]
renato_d = ["JOSE RENATO MAULER"]

vendedor_selecionado_upper = vendedor_selecionado.upper()

if vendedor_selecionado == "Todos":
    aba_meta_calculada = "GERAL"

elif vendedor_selecionado_upper in paola_loja:
    aba_meta_calculada = "PAOLA"

elif vendedor_selecionado_upper in jemine_loja:
    aba_meta_calculada = "JEMINE"

elif vendedor_selecionado_upper in danilima_d:
    aba_meta_calculada = "DANILIMA"

elif vendedor_selecionado_upper in renato_d:
    aba_meta_calculada = "RENATO"

elif vendedor_selecionado_upper in rose_loja:
    aba_meta_calculada = "ROSE"

else:
    aba_meta_calculada = "GERAL"

if st.sidebar.button("🔄 Processar Dados", use_container_width=True):
    with st.spinner("🔄 Processando dados do Google Sheets..."):

        # 1. FILTRAR VENDAS (Passamos vendas_raw, NÃO um caminho de arquivo)
        df_filtrado = filtrar_vendas(
            vendas_raw,  # <--- MUDANÇA IMPORTANTE: Passa o DF do Sheets
            mes_referencia=mes_selecionado if filtro_tipo == "Mês" else None,
            vendedor_selecionado=vendedor_selecionado,
            empresa_selecionada=empresa_selecionada,  # <-- ADICIONE ESTA LINHA AQUI
            data_inicial=data_inicial,
            data_final=data_final,
            com_cdp=com_cdp,
        )

        # 2. CARREGAR METAS (Usando a nova função conectada ao Sheets)
        planilha_metas = None

        # Define o nome da aba corretamente baseado na lógica que você já criou
        # Se for "GERAL", certifique-se que o nome na planilha é "Meta - Geral" ou só "GERAL"
        # Vou assumir que sua planilha tem abas com nomes como "PAOLA", "JEMINE", etc.
        # E uma aba geral chamada "Meta - Geral" (ajuste o nome abaixo se necessário)

        nome_aba_sheet = aba_meta_calculada
        if aba_meta_calculada == "GERAL":
            nome_aba_sheet = (
                "Meta - Geral"  # Ajuste aqui se o nome da aba for diferente no Sheets
            )

        planilha_metas = carregar_planilha_metas_sheets(nome_aba_sheet)

        if planilha_metas.empty:
            st.sidebar.warning(
                f"⚠️ Não foi possível ler as metas da aba '{nome_aba_sheet}'."
            )

        # 3. PROCESSAR TOTAIS
        if df_filtrado is not None and not df_filtrado.empty:
            total_opd, total_amc = processar_vendas(df_filtrado)
        else:
            total_opd, total_amc = 0.0, 0.0

        # 4. COMPARAR COM METAS
        comparacao = {}
        if planilha_metas is not None and not planilha_metas.empty and mes_selecionado:
            comparacao = comparar_com_metas(
                planilha_metas, mes_selecionado, total_opd, total_amc
            )
            if not comparacao:
                st.sidebar.warning("⚠️ Estrutura da aba de metas diferente do esperado.")

        # SALVAR NO SESSION STATE
        st.session_state["df_filtrado"] = df_filtrado
        st.session_state["total_opd"] = total_opd
        st.session_state["total_amc"] = total_amc
        st.session_state["comparacao"] = comparacao
        st.session_state["mes_selecionado"] = mes_selecionado
        st.session_state["feriados"] = feriados
        st.session_state["vendedor_selecionado"] = vendedor_selecionado
        st.session_state["empresa_selecionada"] = (
            empresa_selecionada  # <-- ADICIONE ESTA LINHA AQUI
        )


if "df_filtrado" not in st.session_state:
    st.info("📂 Selecione os filtros na barra lateral e clique em 'Processar Dados'.")
else:
    df_filtrado = st.session_state["df_filtrado"]
    total_opd = st.session_state["total_opd"]
    total_amc = st.session_state["total_amc"]
    comparacao = st.session_state["comparacao"]
    mes = st.session_state["mes_selecionado"]
    feriados_sess = st.session_state[
        "feriados"
    ]  # Renomeado para evitar conflito com a variável global
    vendedor_selecionado_sess = st.session_state["vendedor_selecionado"]  # Renomeado

    if pagina_selecionada == "Painel de Vendas":
        tab1, tab2, tab3 = st.tabs(
            [
                "📊 Visão Geral",
                "📋 Relatórios Detalhados",
                "🔮 Previsão de Vendas (Em Teste)",
            ]
        )
        with tab1:
            if df_filtrado is None or df_filtrado.empty:
                st.warning(
                    "Nenhum dado para exibir no Painel Principal com os filtros atuais."
                )
            elif not comparacao:
                st.warning(
                    "Metas não carregadas ou não encontradas para os filtros. O painel será exibido sem comparações."
                )
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("📈 Vendas OPD", f"R$ {total_opd:,.2f}")
                with col2:
                    st.metric("📊 Vendas Distribuição", f"R$ {total_amc:,.2f}")
            else:
                dias_uteis_passados = calcular_dias_uteis_passados(
                    mes, incluir_hoje=False, feriados=feriados_sess
                )
                dias_uteis_restantes = calcular_dias_uteis_restantes(
                    mes, incluir_hoje=True, feriados=feriados_sess
                )
                # Evita divisão por zero se não houver dias passados/restantes no mês (ex: primeiro/último dia)
                dias_uteis_passados_calc = max(1, dias_uteis_passados)
                dias_uteis_restantes_calc = max(1, dias_uteis_restantes)

                def format_valor(valor):
                    return (
                        f"R$ {valor:,.2f}".replace(",", "X")
                        .replace(".", ",")
                        .replace("X", ".")
                    )

                def calcular_tendencia(realizado, dias_passados, dias_futuros):
                    if (
                        dias_passados == 0
                    ):  # Se não houve dias úteis passados no período filtrado
                        media_diaria = 0
                        tendencia_total = (
                            realizado  # A tendência é apenas o que já foi realizado
                        )
                    else:
                        media_diaria = realizado / dias_passados
                        tendencia_total = realizado + (media_diaria * dias_futuros)
                    return tendencia_total, media_diaria

                if vendedor_selecionado_sess == "Todos":
                    soma_total = total_opd + total_amc
                    realizado_geral = soma_total
                    meta_geral = comparacao.get("OPD", {}).get(
                        "Meta Mensal", 0
                    ) + comparacao.get("AMC", {}).get("Meta Mensal", 0)
                    meta_desafio = comparacao.get("OPD", {}).get(
                        "Meta Desafio", 0
                    ) + comparacao.get("AMC", {}).get("Meta Desafio", 0)
                    super_meta = comparacao.get("AMC", {}).get(
                        "Super Meta", 0
                    ) + comparacao.get("OPD", {}).get("Meta Desafio", 0)

                    def gerar_bloco_meta(titulo, meta_valor):
                        tendencia, media_diaria = calcular_tendencia(
                            realizado_geral,
                            dias_uteis_passados_calc,
                            dias_uteis_restantes_calc,
                        )
                        necessario_por_dia = (
                            max(
                                0,
                                (meta_valor - realizado_geral)
                                / dias_uteis_restantes_calc,
                            )
                            if dias_uteis_restantes_calc > 0
                            else (meta_valor - realizado_geral)
                        )

                        html = (
                            f"<div style='background-color:#180785; padding:10px; border-radius:10px; width:33%; text-align:center; margin-bottom:10px;'>"
                            f"<h4 style='color:#ffffff;'>{titulo}: {format_valor(meta_valor)}</h4>"
                            f"<p style='color:#cccccc; margin:4px;'>📈 Tendência: {format_valor(tendencia)}</p>"
                            f"<p style='color:#cccccc; margin:4px;'>📊 Média Diária Realizada: {format_valor(media_diaria)}</p>"
                            f"<p style='color:#cccccc; margin:4px;'>🎯 Necessário/dia (restante): {format_valor(necessario_por_dia)}</p>"
                            f"</div>"
                        )
                        return html

                    bloco_mensal = gerar_bloco_meta("Meta Mensal", meta_geral)
                    bloco_desafio = gerar_bloco_meta("Meta Desafio", meta_desafio)
                    bloco_super = gerar_bloco_meta("Super Meta", super_meta)

                    st.markdown(
                        f"<div style='background-color:#240eb3; padding:20px; border-radius:10px; text-align:center; margin-top:10px; margin-bottom:10px;'><h3 style='color:#ffffff;'>💰 Total Geral da Empresa: {format_valor(soma_total)}</h3></div>",
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        f"<div style='display: flex; justify-content: space-between; gap: 10px; margin-top:0px;'>{bloco_mensal}{bloco_desafio}{bloco_super}</div>",
                        unsafe_allow_html=True,
                    )

                col1_chart, col2_chart = st.columns(2)
                with col1_chart:
                    st.markdown(
                        f"<div style='background-color:#240eb3; padding:10px; border-radius:10px; text-align:center;'><h4 style='color:#ffff;'>📈 Vendas OPD: R$ {total_opd:,.2f}</h4></div>",
                        unsafe_allow_html=True,
                    )
                    if "OPD" in comparacao and comparacao["OPD"]:
                        st.plotly_chart(
                            gerar_grafico("OPD", comparacao["OPD"], "Relação de OPD"),
                            use_container_width=True,
                        )
                    else:
                        st.info("Dados de OPD não disponíveis para o gráfico.")
                with col2_chart:
                    st.markdown(
                        f"<div style='background-color:#240eb3; padding:10px; border-radius:10px; text-align:center;'><h4 style='color:#ffff;'>📊 Vendas Distribuição: R$ {total_amc:,.2f}</h4></div>",
                        unsafe_allow_html=True,
                    )
                    if "AMC" in comparacao and comparacao["AMC"]:
                        st.plotly_chart(
                            gerar_grafico(
                                "AMC", comparacao["AMC"], "Relação de Distribuição"
                            ),
                            use_container_width=True,
                        )
                    else:
                        st.info(
                            "Dados de Distribuição (AMC) não disponíveis para o gráfico."
                        )

                st.markdown(
                    "<h2 style='text-align: center; margin-top: 30px;'>📢 Status Detalhado das Metas</h2>",
                    unsafe_allow_html=True,
                )
                col1_m, col2_m = st.columns(2)

                def exibir_metricas(coluna, titulo, metas_cat, realizado_cat):
                    with coluna:
                        st.markdown(
                            f"<div style='text-align: center; font-size: 25px; font-weight: bold; margin-bottom: 15px;'>{titulo}</div>",
                            unsafe_allow_html=True,
                        )
                        tendencia, media_diaria = calcular_tendencia(
                            realizado_cat,
                            dias_uteis_passados_calc,
                            dias_uteis_restantes_calc,
                        )

                        for nome_meta, valor_meta in metas_cat.items():
                            if nome_meta == "Realizado" or valor_meta <= 0:
                                continue

                            necessario = (
                                max(
                                    0,
                                    (valor_meta - realizado_cat)
                                    / dias_uteis_restantes_calc,
                                )
                                if dias_uteis_restantes_calc > 0
                                else (valor_meta - realizado_cat)
                            )
                            delta_color = "normal"  # Default to normal (red for negative delta in st.metric)
                            diferenca_tendencia_meta = tendencia - valor_meta
                            percentual_tendencia = (
                                (diferenca_tendencia_meta / valor_meta) * 100
                                if valor_meta > 0
                                else 0
                            )

                            st.metric(
                                label=f"🎯 {nome_meta}",
                                value=format_valor(valor_meta),
                                delta=f"Necessário vender por dia: {format_valor(necessario)}",
                                delta_color="off",  # Let the custom HTML handle colors based on trend
                            )

                            if tendencia >= valor_meta:
                                cor_borda = "#28a745"  # Verde
                                sinal = "+"
                                texto_status = (
                                    f"📈 Tendência positiva para <u>{nome_meta}</u>"
                                )
                                texto_rodape = f"Projeção de ultrapassar a meta em {sinal}{format_valor(abs(diferenca_tendencia_meta))}."
                            else:
                                cor_borda = "#ff1500"  # Vermelho
                                sinal = "-"
                                texto_status = (
                                    f"📉 Risco de não atingir <u>{nome_meta}</u>"
                                )
                                texto_rodape = f"Projeção de ficar abaixo da meta em {sinal}{format_valor(abs(diferenca_tendencia_meta))}."

                            texto_html = f"""
                            <div style="background-color:#ffffff; padding:16px; border-radius:12px; margin-bottom:15px;
                                        box-shadow:0 2px 6px rgba(0,0,0,0.1); border-left:6px solid {cor_borda};">
                                <div style="font-size:16px; font-weight:bold;">{texto_status}</div>
                                <div style="font-size:22px; font-weight:bold; color:{cor_borda}; margin-top:6px;">
                                    {sinal}{format_valor(abs(diferenca_tendencia_meta))} ({sinal}{abs(percentual_tendencia):.1f}%)
                                </div>
                                <div style="font-size:14px; color:#313334;">{texto_rodape}</div>
                                <div style="font-size:14px; color:#313334; margin-top:5px;">
                                    <i>Tendência Total: {format_valor(tendencia)} | Média Diária Realizada: {format_valor(media_diaria)}</i>
                                </div>
                            </div>
                            """
                            st.markdown(texto_html, unsafe_allow_html=True)
                            st.markdown("---")

                if "OPD" in comparacao and comparacao["OPD"]:
                    metas_opd_validas = {
                        k: v
                        for k, v in comparacao["OPD"].items()
                        if v > 0 and k != "Realizado"
                    }
                    exibir_metricas(col1_m, "📦 OPD", metas_opd_validas, total_opd)
                else:
                    with col1_m:
                        st.info("Dados de metas OPD não disponíveis.")

                if "AMC" in comparacao and comparacao["AMC"]:
                    metas_amc_validas = {
                        k: v
                        for k, v in comparacao["AMC"].items()
                        if v > 0 and k != "Realizado"
                    }
                    exibir_metricas(
                        col2_m, "🚚 Distribuição", metas_amc_validas, total_amc
                    )
                else:
                    with col2_m:
                        st.info("Dados de metas Distribuição (AMC) não disponíveis.")

        with tab2:
            if df_filtrado is None or df_filtrado.empty:
                st.warning(
                    "Nenhum dado para exibir nos Relatórios com os filtros atuais."
                )
            else:
                tab_vendas, tab_abc = st.tabs(
                    ["📋 Visão de Vendas", "📊 Análise de Clientes (ABC)"]
                )

                with tab_vendas:
                    if vendedor_selecionado_sess == "Todos":
                        st.subheader("📋 Visão Geral da Empresa")
                        tipo_visao_geral = st.radio(
                            "Escolha como visualizar os dados gerais:",
                            ["Resumo por Vendedor", "Resumo Dia a Dia (Empresa)"],
                            horizontal=True,
                        )
                        if tipo_visao_geral == "Resumo por Vendedor":
                            st.markdown("##### Total de Vendas por Vendedor")
                            tabela_geral_df = gerar_tabela_geral(df_filtrado)
                            st.dataframe(tabela_geral_df, use_container_width=True)
                        elif tipo_visao_geral == "Resumo Dia a Dia (Empresa)":
                            st.markdown("##### Vendas Resumidas da Empresa (Dia a Dia)")
                            tabela_resumo_dia_df = gerar_tabela_diaria_empresa(
                                df_filtrado
                            )
                            st.dataframe(tabela_resumo_dia_df, use_container_width=True)

                        st.markdown("---")
                        st.subheader("🏆 Ranking de Vendedores no Período")
                        df_ranking = gerar_dados_ranking(df_filtrado)

                        if not df_ranking.empty:
                            col1, col2 = st.columns(2)
                            for tipo_rank, col in zip(
                                ["OPD", "Distribuição"], [col1, col2]
                            ):
                                if (
                                    tipo_rank in df_ranking.columns
                                    and df_ranking[tipo_rank].sum() > 0
                                ):
                                    with col:
                                        st.markdown(f"##### {tipo_rank}")
                                        df_sorted = df_ranking.sort_values(
                                            by=tipo_rank, ascending=False
                                        )
                                        df_top3 = df_sorted.head(3).copy()
                                        cores = [
                                            "#240eb3",
                                            "#5c6bc0",
                                            "#9fa8da ",
                                        ]  # e02500C
                                        df_top3["Cor"] = cores[: len(df_top3)]

                                        fig = px.bar(
                                            df_top3.sort_values(
                                                by=tipo_rank, ascending=True
                                            ),
                                            x=tipo_rank,
                                            y="Vendedor",
                                            orientation="h",
                                            text_auto=True,
                                            color="Cor",
                                            color_discrete_map={c: c for c in cores},
                                        )
                                        fig.update_traces(texttemplate="R$ %{x:,.2f}")
                                        fig.update_layout(height=300, showlegend=False)
                                        st.plotly_chart(fig, use_container_width=True)
                                else:
                                    with col:
                                        st.info(
                                            f"Nenhuma venda '{tipo_rank}' encontrada."
                                        )
                        else:
                            st.info("Ranking não pôde ser gerado. Verifique os dados.")
                    else:
                        st.subheader(
                            f"📋 Detalhe de Vendas - {vendedor_selecionado_sess}"
                        )
                        tabela_detalhada, totais_vendedor = gerar_tabela_vendedor(
                            df_filtrado
                        )
                        if not tabela_detalhada.empty:
                            st.dataframe(tabela_detalhada, use_container_width=True)
                            st.markdown("---")
                            st.subheader("Resumo do Vendedor no Período")
                            col1_vend, col2_vend, col3_vend = st.columns(3)
                            col1_vend.metric(
                                "🔹 Total OPD",
                                f"R$ {totais_vendedor.get('OPD', 0):,.2f}",
                            )
                            col2_vend.metric(
                                "🔸 Total Distribuição",
                                f"R$ {totais_vendedor.get('Distribuição', 0):,.2f}",
                            )
                            col3_vend.metric(
                                "💰 Total Geral Vendedor",
                                f"R$ {totais_vendedor.get('Total', 0):,.2f}",
                            )

                with tab_abc:
                    st.subheader("🔍 Análise de Clientes por Curva ABC")
                    st.markdown(
                        "Esta análise classifica seus clientes em três categorias com base no faturamento, ajudando a focar os esforços de vendas."
                    )

                    df_abc = gerar_analise_abc_clientes(df_filtrado)

                    if df_abc is not None:
                        total_clientes = df_abc["CLI_RAZ"].nunique()
                        clientes_a = df_abc[df_abc["Classe"] == "A"][
                            "CLI_RAZ"
                        ].nunique()
                        perc_a = (
                            (clientes_a / total_clientes) * 100
                            if total_clientes > 0
                            else 0
                        )

                        st.info(
                            f"💡 **{clientes_a} clientes (ou {perc_a:.1f}% do total)** correspondem a **80%** do seu faturamento no período. Estes são seus clientes **Classe A**."
                        )

                        fig_abc = px.pie(
                            df_abc,
                            names="Classe",
                            title="Distribuição de Clientes por Classe ABC",
                            color="Classe",
                            color_discrete_map={
                                "A": "#240eb3",
                                "B": "#5c6bc0 ",
                                "C": "#9fa8da",
                            },
                        )
                        st.plotly_chart(fig_abc, use_container_width=True)

                        with st.expander("Ver detalhamento completo da Curva ABC"):
                            st.dataframe(
                                df_abc.style.format(
                                    {
                                        "Valor Total Vendas": "R$ {:,.2f}",
                                        "% Participação": "{:.2%}",
                                        "% Acumulada": "{:.2%}",
                                    }
                                ),
                                use_container_width=True,
                            )
                    else:
                        st.warning("Não foi possível gerar a análise ABC.")

        with tab3:
            st.subheader("🔮 Previsão de Vendas - Próximos 30 dias")

            # 1. Verificação inicial: se há dados no filtro
            if df_filtrado is None or df_filtrado.empty:
                st.warning("⚠️ Não há dados suficientes para gerar uma previsão.")
            else:
                # --- Preparar os dados ---
                df_forecast = df_filtrado.copy()

                # Garante que a data está correta (evita erro de formato do Sheets)
                df_forecast["DAT_CAD_DATE"] = pd.to_datetime(
                    df_forecast["DAT_CAD_DATE"], errors="coerce"
                )

                # Remove linhas sem data ou sem valor de pedido
                df_forecast = df_forecast.dropna(subset=["DAT_CAD_DATE", "PED_TOTAL"])

                # Seleciona e renomeia para o padrão do Prophet (ds e y)
                df_forecast = df_forecast[["DAT_CAD_DATE", "PED_TOTAL"]].rename(
                    columns={"DAT_CAD_DATE": "ds", "PED_TOTAL": "y"}
                )

                # Agrupa por dia (O Prophet precisa de dados diários)
                df_forecast = (
                    df_forecast.groupby("ds").sum().reset_index().sort_values("ds")
                )

                # --- TRAVA DE SEGURANÇA: O Prophet exige no mínimo 2 dias de dados ---
                if len(df_forecast) < 2:
                    st.warning(
                        "⚠️ Dados insuficientes para gerar previsão. Selecione um período maior ou com mais dias de venda."
                    )
                else:
                    try:
                        # --- Criar e treinar o modelo ---
                        modelo = Prophet(
                            daily_seasonality=False,
                            weekly_seasonality=True,
                            yearly_seasonality=True,
                            changepoint_prior_scale=0.1,
                        )
                        modelo.fit(df_forecast)

                        # --- Criar datas futuras e gerar previsão ---
                        futuro = modelo.make_future_dataframe(periods=30)
                        previsao = modelo.predict(futuro)

                        # --- KPIs principais ---
                        ultima_data = df_forecast["ds"].max()
                        previsao_futura = previsao[previsao["ds"] > ultima_data].copy()
                        total_previsto = previsao_futura["yhat"].sum()
                        total_realizado = df_forecast["y"].sum()

                        # Métricas Estatísticas
                        media_historica = df_forecast["y"].mean()
                        std_historica = df_forecast["y"].std()
                        media_prevista = previsao_futura["yhat"].mean()
                        std_prevista = previsao_futura["yhat"].std()

                        # Crescimento esperado
                        crescimento_percentual = (
                            ((total_previsto - total_realizado) / total_realizado) * 100
                            if total_realizado > 0
                            else 0
                        )

                        # Exibição dos Cartões (KPIs)
                        col1, col2, col3, col4 = st.columns(4)
                        col1.metric(
                            "📅 Previsto (Próx. 30 dias)",
                            f"R$ {total_previsto:,.2f}",
                            delta=f"{crescimento_percentual:.2f}%",
                        )
                        col2.metric(
                            "📈 Histórico no Período", f"R$ {total_realizado:,.2f}"
                        )
                        col3.metric(
                            "📊 Média Diária Histórica",
                            f"R$ {media_historica:,.2f}",
                            delta=f"Desvio: {std_historica:,.2f}",
                            delta_color="off",
                        )
                        col4.metric(
                            "📊 Média Diária Prevista",
                            f"R$ {media_prevista:,.2f}",
                            delta=f"Desvio: {std_prevista:,.2f}",
                            delta_color="off",
                        )

                        # --- Gráfico principal: previsão com faixa de confiança ---
                        fig_forecast = plot_plotly(modelo, previsao)

                        # Ajuste visual das cores do gráfico
                        for trace in fig_forecast.data:
                            if trace.name is not None and (
                                "yhat_lower" in trace.name
                                or "yhat_upper" in trace.name
                                or "cap" in trace.name
                            ):
                                trace.update(
                                    opacity=0.15, fillcolor="rgba(200, 200, 200, 0.3)"
                                )

                        fig_forecast.update_layout(
                            title="📈 Previsão de Vendas Diárias (Próximos 30 dias)",
                            xaxis_title="Data",
                            yaxis_title="Valor das Vendas (R$)",
                            plot_bgcolor="rgba(0,0,0,0)",
                            paper_bgcolor="rgba(0,0,0,0)",
                            font=dict(color="white", size=14),
                            height=550,
                        )
                        st.plotly_chart(fig_forecast, use_container_width=True)

                        # --- Gráfico extra 1: Real vs Previsão ---
                        df_comparacao = pd.merge(
                            df_forecast[["ds", "y"]],
                            previsao[["ds", "yhat"]],
                            on="ds",
                            how="outer",
                        )
                        # Filtra apenas o mês atual e o futuro para não poluir o gráfico
                        df_comparacao = df_comparacao[
                            df_comparacao["ds"] > (ultima_data - pd.Timedelta(days=30))
                        ]

                        fig_comparacao = go.Figure()
                        fig_comparacao.add_trace(
                            go.Bar(
                                x=df_comparacao["ds"],
                                y=df_comparacao["y"],
                                name="Vendas Reais",
                                marker_color="#00ced1",
                                opacity=0.7,
                            )
                        )
                        fig_comparacao.add_trace(
                            go.Scatter(
                                x=df_comparacao["ds"],
                                y=df_comparacao["yhat"],
                                mode="lines+markers",
                                name="Tendência Prevista",
                                line=dict(color="#ff8c00", width=3),
                            )
                        )
                        fig_comparacao.update_layout(
                            title="📊 Últimos 30 dias: Vendas Reais vs Tendência",
                            xaxis_title="Data",
                            yaxis_title="R$",
                            plot_bgcolor="rgba(0,0,0,0)",
                            paper_bgcolor="rgba(0,0,0,0)",
                            font=dict(color="white"),
                            height=400,
                        )
                        st.plotly_chart(fig_comparacao, use_container_width=True)

                        # --- Gráfico extra 2: Sazonalidade ---
                        st.markdown("### 📉 Decomposição da Tendência")
                        fig_comp = modelo.plot_components(previsao)
                        st.pyplot(fig_comp)

                    except Exception as e:
                        st.error(
                            f"Não foi possível calcular a previsão para este filtro. Detalhe técnico: {e}"
                        )

                # --- Explicações detalhadas (Expander) ---
                with st.expander("ℹ️ Como interpretar a previsão"):
                    st.markdown(
                        """
                            **Como funciona?** O modelo analisa suas vendas passadas, identifica padrões (como vendas maiores em fins de semana ou em certos meses) e projeta isso para o futuro.
                            
                            - **Faixa de Confiança:** A sombra cinza no gráfico representa a margem de erro. Quanto mais larga a sombra, mais incerta é a previsão.
                            - **Sazonalidade:** No gráfico de decomposição, você pode ver quais dias da semana costumam vender mais no seu BI.
                            - **Limitação:** Se o vendedor for novo ou o período tiver poucas vendas, a previsão será menos precisa.
                            """
                    )

    # --------------------------------------------------------------------------------
    # NOVA PÁGINA: RELATÓRIOS FINANCEIROS
    # --------------------------------------------------------------------------------
    elif pagina_selecionada == "Painel Financeiro":

        # NÃO carregamos arquivo local. Usamos os dados que já vieram do Sheets no início do script.
        # vendas_raw, receber_raw, pagar_raw foram carregados na linha 763

        if df_receber is not None and df_pagar is not None:
            # Processa os dados brutos do Sheets
            df_receber, df_pagar = carregar_dados_financeiros(df_receber, df_pagar)
        else:
            st.error("Dados financeiros não encontrados no Google Sheets.")
            st.stop()

        if df_receber is not None and df_pagar is not None:

            saldo_inicial = st.sidebar.number_input(
                "💰 Informe o Saldo Inicial em Caixa (R$)",
                # Sem min_value, ele aceita números negativos
                value=10000.0,
                step=1000.0,
                format="%.2f",
                help="Você pode inserir valores negativos se o caixa começou o período devedor.",
            )

            # Unir todas as entidades únicas (Cliente + Fornecedor)
            entidades_unicas = sorted(
                pd.concat([df_receber["Cliente"], df_pagar["Fornecedor"]])
                .dropna()
                .unique()
            )

            entidade_escolhida = st.sidebar.selectbox(
                "Selecionar Cliente/Fornecedor", options=["Todos"] + entidades_unicas
            )

            # Aplicando filtros
            df_receber_filtrado = df_receber[
                (df_receber["Data Vencimento"] >= pd.to_datetime(data_inicial))
                & (df_receber["Data Vencimento"] <= pd.to_datetime(data_final))
            ]

            if entidade_escolhida != "Todos":
                df_receber_filtrado = df_receber_filtrado[
                    df_receber_filtrado["Cliente"] == entidade_escolhida
                ]

            df_pagar_filtrado = df_pagar[
                (df_pagar["Data Vencimento"] >= pd.to_datetime(data_inicial))
                & (df_pagar["Data Vencimento"] <= pd.to_datetime(data_final))
            ]

            if entidade_escolhida != "Todos":
                df_pagar_filtrado = df_pagar_filtrado[
                    df_pagar_filtrado["Fornecedor"] == entidade_escolhida
                ]

            # --- NOVO: FILTRO DE EMPRESA NO FINANCEIRO ---
            if empresa_selecionada != "Todas":
                if "EMPRESA" in df_receber_filtrado.columns:
                    # Padroniza para maiúsculo antes de comparar para evitar erros de digitação na planilha
                    df_receber_filtrado = df_receber_filtrado[
                        df_receber_filtrado["EMPRESA"]
                        .astype(str)
                        .str.strip()
                        .str.upper()
                        == empresa_selecionada
                    ]

                if "EMPRESA" in df_pagar_filtrado.columns:
                    df_pagar_filtrado = df_pagar_filtrado[
                        df_pagar_filtrado["EMPRESA"].astype(str).str.strip().str.upper()
                        == empresa_selecionada
                    ]

            # --- ABAS PARA VISUALIZAÇÃO ---
            tab1, tab2, tab3, tab4 = st.tabs(
                [
                    "📊 Contas a Receber",
                    "💸 Contas a Pagar",
                    "📦 Fluxo de Caixa",
                    "📈 Análise de Resultados (DRE)",
                ]
            )

            with tab1:
                criar_painel_financeiro_avancado(
                    "📊 Visão Geral de Contas a Receber",
                    df_receber_filtrado,
                    coluna_valor="Valor",
                    coluna_status="Status",
                    coluna_entidade="Cliente",
                    coluna_vencimento="Data Vencimento",
                    coluna_inadimplencia="Inadimplência",  # <-- ATIVANDO A NOVA FUNCIONALIDADE
                )
            with tab2:
                criar_painel_financeiro_avancado(
                    "💸 Visão Geral de Contas a Pagar",
                    df_pagar_filtrado,
                    coluna_valor="Valor",
                    coluna_status="Status",
                    coluna_entidade="Fornecedor",
                    coluna_vencimento="Data Vencimento",
                )

            with tab3:
                # st.subheader("🌊 Projeção de Fluxo de Caixa")
                # st.markdown("Esta análise projeta o saldo futuro em caixa com base nas contas em aberto e no saldo inicial informado.")

                # --- SIMULADOR DE CENÁRIOS (recolhível) ---
                with st.expander("🔬 Abrir Simulador de Cenários (What-If)"):
                    st.markdown(
                        "Ajuste abaixo receitas e despesas simuladas para observar os impactos no fluxo de caixa."
                    )

                    col_sim1, col_sim2, col_sim3 = st.columns(3)
                    with col_sim1:
                        sim_receita_valor = st.number_input(
                            "Simular nova receita (R$)",
                            value=0.0,
                            step=100.0,
                            key="sim_receita_valor",
                        )
                    with col_sim2:
                        sim_receita_data = st.date_input(
                            "Data da nova receita",
                            value=datetime.date.today(),
                            key="sim_receita_data",
                        )
                    with col_sim3:
                        st.write("")
                        st.write("")
                        aplicar_receita = st.button("Aplicar Receita")

                    col_sim_d1, col_sim_d2, col_sim_d3 = st.columns(3)
                    with col_sim_d1:
                        sim_despesa_valor = st.number_input(
                            "Simular nova despesa (R$)",
                            value=0.0,
                            step=100.0,
                            key="sim_despesa_valor",
                        )
                    with col_sim_d2:
                        sim_despesa_data = st.date_input(
                            "Data da nova despesa",
                            value=datetime.date.today(),
                            key="sim_despesa_data",
                        )
                    with col_sim_d3:
                        st.write("")
                        st.write("")
                        aplicar_despesa = st.button("Aplicar Despesa")

                # --- APLICAR SIMULAÇÕES ---
                df_receber_simulado = df_receber.copy()
                df_pagar_simulado = df_pagar.copy()

                if aplicar_receita and sim_receita_valor > 0:
                    nova_receita = pd.DataFrame(
                        [
                            {
                                "Cliente": "RECEITA SIMULADA",
                                "Data Vencimento": pd.to_datetime(sim_receita_data),
                                "Valor": sim_receita_valor,
                                "Status": "EM ABERTO",
                            }
                        ]
                    )
                    df_receber_simulado = pd.concat(
                        [df_receber_simulado, nova_receita], ignore_index=True
                    )
                    st.success(
                        f"✅ Receita de R$ {sim_receita_valor:,.2f} simulada para {sim_receita_data.strftime('%d/%m/%Y')}."
                    )

                if aplicar_despesa and sim_despesa_valor > 0:
                    nova_despesa = pd.DataFrame(
                        [
                            {
                                "Fornecedor": "DESPESA SIMULADA",
                                "Data Vencimento": pd.to_datetime(sim_despesa_data),
                                "Valor": sim_despesa_valor,
                                "Status": "EM ABERTO",
                            }
                        ]
                    )
                    df_pagar_simulado = pd.concat(
                        [df_pagar_simulado, nova_despesa], ignore_index=True
                    )
                    st.success(
                        f"✅ Despesa de R$ {sim_despesa_valor:,.2f} simulada para {sim_despesa_data.strftime('%d/%m/%Y')}."
                    )

                # --- LÓGICA DE PREPARAÇÃO DOS DADOS ---
                tem_simulacao = aplicar_receita or aplicar_despesa
                if tem_simulacao:
                    st.info("🧪 Projeção considerando valores simulados.")
                    df_fluxo = preparar_dados_fluxo_caixa(
                        df_receber_simulado,
                        df_pagar_simulado,
                        saldo_inicial,
                        data_inicial,
                        data_final,
                    )
                    despesas_base = df_pagar_simulado
                else:
                    df_fluxo = preparar_dados_fluxo_caixa(
                        df_receber, df_pagar, saldo_inicial, data_inicial, data_final
                    )
                    despesas_base = df_pagar

                # --- RESULTADOS DA PROJEÇÃO ---
                if df_fluxo.empty:
                    st.warning(
                        "⚠️ Não há dados suficientes para gerar a projeção de fluxo de caixa."
                    )
                else:
                    # --- KPIs ---
                    # CORREÇÃO: Usar o novo nome da coluna 'Saldo_Acumulado_Previsto'
                    menor_saldo_previsto = df_fluxo["Saldo_Acumulado_Previsto"].min()
                    dia_menor_saldo = df_fluxo.loc[
                        df_fluxo["Saldo_Acumulado_Previsto"].idxmin(), "Data"
                    ].strftime("%d/%m/%Y")
                    maior_saldo_previsto = df_fluxo["Saldo_Acumulado_Previsto"].max()
                    dias_fluxo_negativo = df_fluxo[
                        df_fluxo["Fluxo_Líquido_Previsto"] < 0
                    ].shape[0]

                    kpi1, kpi2, kpi3 = st.columns(3)
                    kpi1.metric(
                        "📉 Menor Saldo Previsto",
                        f"R$ {menor_saldo_previsto:,.2f}",
                        help=f"Pior saldo em {dia_menor_saldo}.",
                    )
                    kpi2.metric(
                        "📈 Maior Saldo Previsto", f"R$ {maior_saldo_previsto:,.2f}"
                    )
                    kpi3.metric(
                        "🔻 Dias com Fluxo Negativo", f"{dias_fluxo_negativo} dias"
                    )

                    st.markdown("---")

                    from plotly.subplots import make_subplots
                    import plotly.graph_objects as go

                    # Criar dois subgráficos lado a lado
                    fig = make_subplots(
                        rows=1,
                        cols=2,
                        specs=[[{"secondary_y": True}, {"secondary_y": True}]],
                        subplot_titles=("Previsto", "Realizado"),
                    )

                    # --- GRÁFICO 1: PREVISTO ---
                    fig.add_trace(
                        go.Bar(
                            x=df_fluxo["Data"],
                            y=df_fluxo["Fluxo_Líquido_Previsto"],
                            name="Fluxo Líquido Previsto",
                            marker_color=[
                                "#c0392b" if v < 0 else "#0f13ff"
                                for v in df_fluxo["Fluxo_Líquido_Previsto"]
                            ],
                        ),
                        row=1,
                        col=1,
                        secondary_y=False,
                    )

                    fig.add_trace(
                        go.Scatter(
                            x=df_fluxo["Data"],
                            y=df_fluxo["Saldo_Acumulado_Previsto"],
                            name="Saldo Previsto",
                            mode="lines+markers",
                            line=dict(color="#ff4500"),
                        ),
                        row=1,
                        col=1,
                        secondary_y=True,
                    )

                    # --- GRÁFICO 2: REALIZADO ---
                    fig.add_trace(
                        go.Bar(
                            x=df_fluxo["Data"],
                            y=df_fluxo["Fluxo_Líquido_Realizado"],
                            name="Fluxo Líquido Realizado",
                            marker_color=[
                                "#9597eb" if v < 0 else "#6263c7"
                                for v in df_fluxo["Fluxo_Líquido_Realizado"]
                            ],
                        ),
                        row=1,
                        col=2,
                        secondary_y=False,
                    )

                    fig.add_trace(
                        go.Scatter(
                            x=df_fluxo["Data"],
                            y=df_fluxo["Saldo_Acumulado_Realizado"],
                            name="Saldo Realizado",
                            mode="lines",
                            line=dict(color="#ff4500", dash="dot"),
                        ),
                        row=1,
                        col=2,
                        secondary_y=True,
                    )

                    # Linha horizontal em Y=0 nos dois gráficos
                    fig.add_hline(
                        y=0,
                        line_dash="dash",
                        line_color="red",
                        row=1,
                        col=1,
                        secondary_y=True,
                    )
                    fig.add_hline(
                        y=0,
                        line_dash="dash",
                        line_color="red",
                        row=1,
                        col=2,
                        secondary_y=True,
                    )

                    # Layout
                    fig.update_layout(
                        title_text="📊 Projeção de Saldo: Previsto vs Realizado (Lado a Lado)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        margin=dict(l=20, r=20, t=60, b=20),
                        legend=dict(
                            orientation="h",
                            yanchor="bottom",
                            y=1.12,
                            xanchor="right",
                            x=1,
                        ),
                        showlegend=False,
                    )

                    # Eixos Y
                    fig.update_yaxes(
                        title_text="Fluxo Líquido (R$)", secondary_y=False, row=1, col=1
                    )
                    fig.update_yaxes(
                        title_text="Saldo Acumulado (R$)",
                        secondary_y=True,
                        row=1,
                        col=1,
                    )

                    fig.update_yaxes(
                        title_text="Fluxo Líquido (R$)", secondary_y=False, row=1, col=2
                    )
                    fig.update_yaxes(
                        title_text="Saldo Acumulado (R$)",
                        secondary_y=True,
                        row=1,
                        col=2,
                    )

                    # Renderizar no Streamlit SEM BARRA DE FERRAMENTAS
                    st.plotly_chart(
                        fig, use_container_width=True, config={"displayModeBar": False}
                    )

                    # --- TABELA DETALHADA (com previsão vs. realizado) ---
                    with st.expander("📋 Ver detalhamento diário do fluxo de caixa"):
                        colunas_tabela = [
                            "Data",
                            "Entradas_Realizadas",
                            "Saídas_Realizadas",
                            "Fluxo_Líquido_Realizado",
                            "Saldo_Acumulado_Realizado",
                            "Entradas_Previstas",
                            "Saídas_Previstas",
                            "Fluxo_Líquido_Previsto",
                            "Saldo_Acumulado_Previsto",
                        ]
                        st.dataframe(
                            df_fluxo[colunas_tabela].style.format(
                                {
                                    "Entradas_Realizadas": "R$ {:,.2f}",
                                    "Saídas_Realizadas": "R$ {:,.2f}",
                                    "Fluxo_Líquido_Realizado": "R$ {:,.2f}",
                                    "Saldo_Acumulado_Realizado": "R$ {:,.2f}",
                                    "Entradas_Previstas": "R$ {:,.2f}",
                                    "Saídas_Previstas": "R$ {:,.2f}",
                                    "Fluxo_Líquido_Previsto": "R$ {:,.2f}",
                                    "Saldo_Acumulado_Previsto": "R$ {:,.2f}",
                                    "Data": "{:%d/%m/%Y}",
                                },
                                na_rep="-",
                            ),
                            use_container_width=True,
                        )

                    # --- ANÁLISES ADICIONAIS ---
                    st.markdown("---")
                    st.subheader("🔎 Análises Adicionais")
                    col1, col2 = st.columns(2)

                    with col1:
                        st.markdown("##### ⛽ Maiores Despesas no Período (Realizado)")

                        # --- INÍCIO DA CORREÇÃO ---
                        # 1. Aplicar o filtro de data à base de despesas (original ou simulada)
                        # Garante que a análise respeite o período selecionado na sidebar.
                        despesas_no_periodo = despesas_base[
                            (
                                despesas_base["Data Vencimento"]
                                >= pd.to_datetime(data_inicial)
                            )
                            & (
                                despesas_base["Data Vencimento"]
                                <= pd.to_datetime(data_final)
                            )
                        ]

                        # 2. Filtrar apenas as despesas "EM ABERTO" do período
                        despesas_aberto = despesas_no_periodo[
                            despesas_no_periodo["Status"] == "PAGO"
                        ].copy()
                        # --- FIM DA CORREÇÃO ---

                        if not despesas_aberto.empty:
                            top_10_despesas = (
                                despesas_aberto.groupby("Fornecedor")["Valor"]
                                .sum()
                                .nlargest(10)
                                .sort_values(ascending=True)
                                .reset_index()
                            )

                            fig_despesas = px.bar(
                                top_10_despesas,
                                y="Fornecedor",
                                x="Valor",
                                orientation="h",
                                text_auto=True,
                                height=400,
                            )
                            fig_despesas.update_traces(
                                marker_color="#240eb3", texttemplate="R$ %{x:,.2f}"
                            )
                            fig_despesas.update_layout(
                                xaxis_title="Valor a Pagar (R$)",
                                yaxis_title=None,
                                margin=dict(l=10, r=10, t=30, b=10),
                            )
                            st.plotly_chart(fig_despesas, use_container_width=True)
                        else:
                            st.info(
                                "Não há despesas em aberto para analisar no período selecionado."
                            )
                    with col2:
                        st.markdown("##### ⚖️ Receitas vs. Despesas (Realizado)")
                        periodo_agregacao = st.radio(
                            "Visualizar por:",
                            ["Diário", "Semanal", "Mensal"],
                            horizontal=True,
                            key="agregacao_receita_despesa",
                        )

                        # CORREÇÃO: Usar as novas colunas 'Entradas_Previstas' e 'Saídas_Previstas'
                        df_fluxo_agregado = df_fluxo.set_index("Data")
                        if periodo_agregacao == "Semanal":
                            df_plot = (
                                df_fluxo_agregado[
                                    ["Entradas_Realizadas", "Saídas_Realizadas"]
                                ]
                                .resample("W-MON")
                                .sum()
                                .reset_index()
                            )
                            df_plot["Data"] = df_plot["Data"].dt.strftime("%d/%m (Sem)")
                        elif periodo_agregacao == "Mensal":
                            df_plot = (
                                df_fluxo_agregado[
                                    ["Entradas_Realizadas", "Saídas_Realizadas"]
                                ]
                                .resample("M")
                                .sum()
                                .reset_index()
                            )
                            df_plot["Data"] = df_plot["Data"].dt.strftime("%b/%Y")
                        else:  # Diário
                            df_plot = df_fluxo[
                                ["Data", "Entradas_Realizadas", "Saídas_Realizadas"]
                            ]
                            df_plot["Data"] = df_plot["Data"].dt.strftime("%d/%m")

                        fig_entradas_saidas = px.bar(
                            df_plot,
                            x="Data",
                            y=["Entradas_Realizadas", "Saídas_Realizadas"],
                            barmode="group",
                            height=400,
                            color_discrete_map={
                                "Entradas_Realizadas": "#28a745",
                                "Saídas_Realizadas": "#dc3545",
                            },
                            labels={"value": "Valor (R$)", "variable": "Legenda"},
                        )
                        fig_entradas_saidas.update_layout(
                            xaxis_title=None,
                            yaxis_title="Valor (R$)",
                            margin=dict(l=10, r=10, t=30, b=10),
                        )
                        st.plotly_chart(fig_entradas_saidas, use_container_width=True)

            with tab4:
                import pandas as pd
                from datetime import datetime
                import plotly.express as px
                import streamlit as st

                # st.subheader("📈 Demonstrativo de resultado no exercício")

                tipo_analise = st.radio(
                    "Selecione o critério de análise:",
                    ("Regime Previsto", "Regime Realizado"),
                    horizontal=True,
                    help="""
                                - **Regime Previsto:** Mostra a lucratividade com base nas datas de venda e vencimento (visão econômica).
                                - **Regime Realizado:** Mostra o resultado financeiro com base no que foi efetivamente pago e recebido (visão de caixa).
                                """,
                )

                df_resultados = pd.DataFrame()

                # --- REGIME DE COMPETÊNCIA (PREVISTO) ---
                if tipo_analise == "Regime Previsto":
                    st.markdown(
                        "Compare suas **vendas faturadas** com suas **despesas por vencimento**."
                    )
                    if (
                        df_filtrado is not None
                        and not df_filtrado.empty
                        and df_pagar is not None
                    ):
                        # --- TRATAMENTO VENDAS ---
                        df_vendas_limpo = df_filtrado.copy()
                        # Garante que é data e remove nulos
                        df_vendas_limpo["DAT_CAD"] = pd.to_datetime(
                            df_vendas_limpo["DAT_CAD"], errors="coerce"
                        )
                        df_vendas_limpo = df_vendas_limpo.dropna(subset=["DAT_CAD"])
                        # Garante que o valor é número
                        df_vendas_limpo["PED_TOTAL"] = pd.to_numeric(
                            df_vendas_limpo["PED_TOTAL"], errors="coerce"
                        ).fillna(0)

                        vendas_mensais = (
                            df_vendas_limpo.set_index("DAT_CAD")
                            .resample("M")["PED_TOTAL"]
                            .sum()
                            .rename("Receita (Competência)")
                        )

                        # --- TRATAMENTO DESPESAS ---
                        df_pagar_limpo = df_pagar.copy()
                        # Garante que é data e remove nulos
                        df_pagar_limpo["Data Vencimento"] = pd.to_datetime(
                            df_pagar_limpo["Data Vencimento"], errors="coerce"
                        )
                        df_pagar_limpo = df_pagar_limpo.dropna(
                            subset=["Data Vencimento"]
                        )
                        # Garante que o valor é número
                        df_pagar_limpo["Valor"] = pd.to_numeric(
                            df_pagar_limpo["Valor"], errors="coerce"
                        ).fillna(0)

                        despesas_mensais = (
                            df_pagar_limpo.set_index("Data Vencimento")
                            .resample("M")["Valor"]
                            .sum()
                            .rename("Despesa (Competência)")
                        )

                        # Concatenar e calcular resultado
                        df_resultados = pd.concat(
                            [vendas_mensais, despesas_mensais], axis=1
                        ).fillna(0)

                        df_resultados["Resultado"] = (
                            df_resultados["Receita (Competência)"]
                            - df_resultados["Despesa (Competência)"]
                        )

                        df_resultados.rename(
                            columns={
                                "Receita (Competência)": "Receitas",
                                "Despesa (Competência)": "Despesas",
                            },
                            inplace=True,
                        )

                    # --- REGIME REALIZADO (Aqui você deve aplicar a mesma lógica de limpeza para Data_Baixa) ---
                    elif tipo_analise == "Regime Realizado":
                        # Certifique-se de aplicar o .dropna(subset=["Data_Baixa"]) aqui também quando fizer o código
                        pass

                # --- EXIBIÇÃO FINAL ---
                if not df_resultados.empty:
                    df_resultados.index = pd.to_datetime(df_resultados.index)

                    if (
                        "start_date" in st.session_state
                        and "end_date" in st.session_state
                    ):
                        start_date_resample = pd.to_datetime(
                            st.session_state.start_date
                        )
                        end_date_resample = pd.to_datetime(st.session_state.end_date)
                        df_resultados = df_resultados[
                            (df_resultados.index >= start_date_resample)
                            & (df_resultados.index <= end_date_resample)
                        ]

                    df_resultados.index = df_resultados.index.strftime("%b/%Y")

                    resultado_total = df_resultados["Resultado"].sum()
                    cor_delta = "normal" if resultado_total >= 0 else "inverse"
                    st.metric(
                        "Resultado Final no Período",
                        f"R$ {resultado_total:,.2f}",
                        delta_color=cor_delta,
                    )

                    fig_dre = px.bar(
                        df_resultados,
                        y=["Receitas", "Despesas", "Resultado"],
                        barmode="group",
                        title=f"Análise Mensal - {tipo_analise}",
                        labels={"value": "Valor (R$)", "variable": "Métrica"},
                        color_discrete_map={
                            "Receitas": "#28a745",
                            "Despesas": "#dc3545",
                            "Resultado": "#007bff",
                        },
                    )
                    st.plotly_chart(fig_dre, use_container_width=True)

                    with st.expander("Ver tabela de resultados detalhada"):
                        st.dataframe(
                            df_resultados.style.format("R$ {:,.2f}"),
                            use_container_width=True,
                        )
                else:
                    st.warning(
                        "Não há dados suficientes no período selecionado para gerar esta análise."
                    )
