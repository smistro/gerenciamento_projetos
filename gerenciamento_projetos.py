import streamlit as st
import pandas as pd
from datetime import date, datetime
import plotly.express as px
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials

# =========================================================
# SISTEMA COLABORATIVO DE GERENCIAMENTO DE PROJETOS
# Streamlit + Google Sheets
# =========================================================

st.set_page_config(
    page_title="Gerenciamento de Projetos",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =========================================================
# CONFIGURAÇÕES
# =========================================================

# Nome da planilha Google exatamente como aparece no Google Drive
NOME_PLANILHA = "gerenciamento_projetos"

ABA_PROJETOS = "projetos"
ABA_USUARIOS = "usuarios"
ABA_ACOES = "acoes"
ABA_CONFIG = "configuracoes"

COLUNAS_PROJETOS = [
    "Projeto",
    "Descrição",
    "Data_inicio",
    "Data_termino_prevista",
    "Coordenador_email",
    "Ativo"
]

COLUNAS_USUARIOS = [
    "Nome",
    "Email",
    "Senha",
    "Perfil",
    "Ativo"
]

COLUNAS_ACOES = [
    "ID",
    "Projeto",
    "Ação",
    "Responsável",
    "Responsável_email",
    "Data_inicio",
    "Data_termino_prevista",
    "Data_conclusao",
    "Status_informado",
    "Prioridade",
    "Percentual_conclusao",
    "Observações",
    "Criado_em",
    "Atualizado_em",
    "Atualizado_por"
]

STATUS_PADRAO = [
    "Não iniciada",
    "Em andamento",
    "Concluída",
    "Suspensa",
    "Cancelada"
]

PRIORIDADES = ["Baixa", "Média", "Alta", "Crítica"]

# =========================================================
# ESTILO VISUAL
# =========================================================

st.markdown(
    """
    <style>
    .main {background-color: #f7f8fb;}
    .block-container {padding-top: 1.5rem; padding-bottom: 2rem;}
    div[data-testid="stMetricValue"] {font-size: 1.8rem;}
    .card {
        background: white;
        padding: 18px;
        border-radius: 18px;
        box-shadow: 0 3px 14px rgba(0,0,0,0.08);
        border: 1px solid #ececec;
    }
    .small-muted {color: #6b7280; font-size: 0.9rem;}
    </style>
    """,
    unsafe_allow_html=True
)

# =========================================================
# GOOGLE SHEETS
# =========================================================

@st.cache_resource
def conectar_google_sheets():
    try:
        escopos = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]

        credenciais = Credentials.from_service_account_info(
            st.secrets["gcp_service_account"],
            scopes=escopos
        )

        cliente = gspread.authorize(credenciais)
        planilha = cliente.open(NOME_PLANILHA)
        return planilha

    except Exception as e:
        st.error("Não foi possível conectar ao Google Sheets.")
        st.warning(
            "Verifique se a planilha existe, se o secrets.toml está correto "
            "e se a planilha foi compartilhada com o e-mail da conta de serviço."
        )
        st.exception(e)
        st.stop()


def obter_aba(planilha, nome_aba, colunas):
    try:
        aba = planilha.worksheet(nome_aba)
    except gspread.WorksheetNotFound:
        aba = planilha.add_worksheet(title=nome_aba, rows=1000, cols=max(len(colunas), 10))
        aba.append_row(colunas)
    return aba


def ler_aba_com_cabecalho_padrao(aba, colunas):
    valores = aba.get_all_values()

    if not valores:
        aba.update([colunas])
        return pd.DataFrame(columns=colunas)

    primeira_linha = [str(x).strip() for x in valores[0]]

    if primeira_linha[:len(colunas)] != colunas:
        aba.update("A1", [colunas])
        valores = aba.get_all_values()

    dados = valores[1:]

    if not dados:
        return pd.DataFrame(columns=colunas)

    dados_ajustados = []
    for linha in dados:
        linha = linha[:len(colunas)]
        linha = linha + [""] * (len(colunas) - len(linha))
        dados_ajustados.append(linha)

    return pd.DataFrame(dados_ajustados, columns=colunas)


@st.cache_data(ttl=20)
def carregar_dados():
    planilha = conectar_google_sheets()

    aba_projetos = obter_aba(planilha, ABA_PROJETOS, COLUNAS_PROJETOS)
    aba_usuarios = obter_aba(planilha, ABA_USUARIOS, COLUNAS_USUARIOS)
    aba_acoes = obter_aba(planilha, ABA_ACOES, COLUNAS_ACOES)
    aba_config = obter_aba(planilha, ABA_CONFIG, ["Tipo", "Valor"])

    projetos = ler_aba_com_cabecalho_padrao(aba_projetos, COLUNAS_PROJETOS)
    usuarios = ler_aba_com_cabecalho_padrao(aba_usuarios, COLUNAS_USUARIOS)
    acoes = ler_aba_com_cabecalho_padrao(aba_acoes, COLUNAS_ACOES)
    config = ler_aba_com_cabecalho_padrao(aba_config, ["Tipo", "Valor"])

    projetos["Ativo"] = projetos["Ativo"].replace("", "Sim")
    usuarios["Ativo"] = usuarios["Ativo"].replace("", "Sim")

    for col in ["Data_inicio", "Data_termino_prevista"]:
        projetos[col] = pd.to_datetime(projetos[col], errors="coerce").dt.date

    for col in ["Data_inicio", "Data_termino_prevista", "Data_conclusao", "Criado_em", "Atualizado_em"]:
        acoes[col] = pd.to_datetime(acoes[col], errors="coerce")

    acoes["Percentual_conclusao"] = pd.to_numeric(acoes["Percentual_conclusao"], errors="coerce").fillna(0)

    status = STATUS_PADRAO
    if not config.empty and {"Tipo", "Valor"}.issubset(config.columns):
        status_config = config.loc[config["Tipo"] == "Status", "Valor"].dropna().astype(str).tolist()
        if status_config:
            status = status_config

    return projetos, usuarios, acoes, status


def salvar_tabela(nome_aba, colunas, df):
    planilha = conectar_google_sheets()
    aba = obter_aba(planilha, nome_aba, colunas)

    df = df.copy()
    for col in colunas:
        if col not in df.columns:
            df[col] = ""

    df = df[colunas].fillna("")

    for col in df.columns:
        df[col] = df[col].astype(str)

    aba.clear()
    aba.update([colunas] + df.values.tolist())
    st.cache_data.clear()


def adicionar_acao(nova_acao):
    planilha = conectar_google_sheets()
    aba = obter_aba(planilha, ABA_ACOES, COLUNAS_ACOES)
    linha = [nova_acao.get(col, "") for col in COLUNAS_ACOES]
    aba.append_row(linha, value_input_option="USER_ENTERED")
    st.cache_data.clear()

# =========================================================
# FUNÇÕES AUXILIARES
# =========================================================

def normalizar_email(email):
    if pd.isna(email):
        return ""
    return str(email).strip().lower()


def usuario_ativo(valor):
    return str(valor).strip().lower() in ["sim", "s", "yes", "1", "true"]


def calcular_status_automatico(row):
    status = str(row.get("Status_informado", "")).strip()
    conclusao = row.get("Data_conclusao")
    prazo = row.get("Data_termino_prevista")
    percentual = row.get("Percentual_conclusao", 0)

    hoje = pd.Timestamp(date.today())

    if status in ["Cancelada", "Suspensa"]:
        return status

    if status == "Concluída" or pd.notna(conclusao) or percentual >= 100:
        if pd.notna(conclusao) and pd.notna(prazo) and conclusao > prazo:
            return "Concluída com atraso"
        return "Concluída"

    if pd.notna(prazo) and prazo < hoje:
        return "Atrasada"

    if pd.notna(prazo):
        dias = (prazo - hoje).days
        if dias <= 7:
            return "Próxima do prazo"

    if status:
        return status

    return "Não iniciada"


def calcular_dias_atraso(row):
    status_auto = row.get("Status_automatico", "")
    prazo = row.get("Data_termino_prevista")
    conclusao = row.get("Data_conclusao")
    hoje = pd.Timestamp(date.today())

    if pd.isna(prazo):
        return 0

    if status_auto == "Atrasada":
        return max((hoje - prazo).days, 0)

    if status_auto == "Concluída com atraso" and pd.notna(conclusao):
        return max((conclusao - prazo).days, 0)

    return 0


def preparar_acoes(df_acoes):
    df = df_acoes.copy()

    if df.empty:
        df["Status_automatico"] = []
        df["Dias_atraso"] = []
        return df

    df["Status_automatico"] = df.apply(calcular_status_automatico, axis=1)
    df["Dias_atraso"] = df.apply(calcular_dias_atraso, axis=1)

    return df


def gerar_id_acao(df_acoes):
    if df_acoes.empty or "ID" not in df_acoes.columns:
        return "ACAO-0001"

    nums = []
    for valor in df_acoes["ID"].dropna().astype(str):
        if valor.startswith("ACAO-"):
            try:
                nums.append(int(valor.replace("ACAO-", "")))
            except ValueError:
                pass

    proximo = max(nums) + 1 if nums else 1
    return f"ACAO-{proximo:04d}"

# =========================================================
# CARREGAMENTO
# =========================================================

df_projetos, df_usuarios, df_acoes_raw, STATUS_DISPONIVEIS = carregar_dados()
df_acoes = preparar_acoes(df_acoes_raw)

# =========================================================
# LOGIN SIMPLES
# =========================================================

st.sidebar.title("📊 Projetos")

modo_acesso = st.sidebar.radio(
    "Tipo de acesso",
    ["Usuário", "Administrador"],
    help="Usuários registram e acompanham suas ações. O administrador visualiza e edita tudo."
)

email_usuario = st.sidebar.text_input("Seu e-mail", placeholder="nome@email.com").strip().lower()

senha_admin = ""
if modo_acesso == "Administrador":
    senha_admin = st.sidebar.text_input("Senha do administrador", type="password")

SENHA_ADMIN = st.secrets.get("SENHA_ADMIN", "admin123")

if not email_usuario:
    st.title("Gerenciamento de Projetos")
    st.info("Informe seu e-mail na barra lateral para acessar o sistema.")
    st.stop()

if modo_acesso == "Administrador":
    if senha_admin != SENHA_ADMIN:
        st.title("Gerenciamento de Projetos")
        st.warning("Informe a senha do administrador para acessar o painel completo.")
        st.stop()
    acesso_admin = True
else:
    acesso_admin = False

if not df_usuarios.empty:
    df_usuarios["Email_normalizado"] = df_usuarios["Email"].apply(normalizar_email)
else:
    df_usuarios["Email_normalizado"] = []

usuario_logado = df_usuarios[df_usuarios["Email_normalizado"] == email_usuario]

if not acesso_admin:
    if usuario_logado.empty:
        st.title("Gerenciamento de Projetos")
        st.error("E-mail não encontrado no cadastro de usuários.")
        st.info("Peça ao administrador para cadastrar seu e-mail na aba usuarios da planilha Google.")
        st.stop()

    if not usuario_ativo(usuario_logado.iloc[0]["Ativo"]):
        st.title("Gerenciamento de Projetos")
        st.error("Usuário inativo.")
        st.stop()

# =========================================================
# FILTROS E MENU
# =========================================================

if acesso_admin:
    paginas = [
        "Painel geral",
        "Nova ação",
        "Minhas ações",
        "Todas as ações",
        "Cadastro de projetos",
        "Cadastro de usuários",
        "Exportar dados"
    ]
else:
    paginas = [
        "Meu painel",
        "Nova ação",
        "Minhas ações"
    ]

pagina = st.sidebar.radio("Menu", paginas)

st.sidebar.divider()
st.sidebar.caption("Filtros")

projetos_ativos = df_projetos[df_projetos["Ativo"].apply(usuario_ativo)].copy() if not df_projetos.empty else df_projetos
lista_projetos = sorted(projetos_ativos["Projeto"].dropna().unique()) if not projetos_ativos.empty else []

filtro_projeto = st.sidebar.multiselect("Projeto", lista_projetos, default=lista_projetos)

if not df_acoes.empty:
    df_acoes_filtrado = df_acoes[df_acoes["Projeto"].isin(filtro_projeto)].copy() if filtro_projeto else df_acoes.copy()
else:
    df_acoes_filtrado = df_acoes.copy()

if not acesso_admin:
    df_acoes_filtrado = df_acoes_filtrado[
        df_acoes_filtrado["Responsável_email"].apply(normalizar_email) == email_usuario
    ].copy()

# =========================================================
# PAINEL GERAL
# =========================================================

if pagina in ["Painel geral", "Meu painel"]:
    st.title("Painel de Gerenciamento de Projetos")
    st.caption("Acompanhamento de ações, prazos, atrasos e evolução dos projetos.")

    total_acoes = len(df_acoes_filtrado)
    concluidas = int(df_acoes_filtrado["Status_automatico"].isin(["Concluída", "Concluída com atraso"]).sum()) if not df_acoes_filtrado.empty else 0
    atrasadas = int((df_acoes_filtrado["Status_automatico"] == "Atrasada").sum()) if not df_acoes_filtrado.empty else 0
    media_conclusao = float(df_acoes_filtrado["Percentual_conclusao"].mean()) if not df_acoes_filtrado.empty else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Ações", total_acoes)
    col2.metric("Concluídas", concluidas)
    col3.metric("Atrasadas", atrasadas)
    col4.metric("Conclusão média", f"{media_conclusao:.1f}%")

    st.divider()

    col_a, col_b = st.columns([2.1, 1])

    with col_a:
        st.subheader("Mapa das ações")
        if df_acoes_filtrado.empty:
            st.info("Ainda não há ações registradas.")
        else:
            tabela = df_acoes_filtrado[
                [
                    "ID",
                    "Projeto",
                    "Ação",
                    "Responsável",
                    "Data_inicio",
                    "Data_termino_prevista",
                    "Data_conclusao",
                    "Status_automatico",
                    "Prioridade",
                    "Percentual_conclusao",
                    "Dias_atraso"
                ]
            ].sort_values(["Status_automatico", "Data_termino_prevista"])

            st.dataframe(tabela, use_container_width=True, hide_index=True, height=580)

    with col_b:
        st.subheader("Status das ações")
        if not df_acoes_filtrado.empty:
            status_contagem = df_acoes_filtrado["Status_automatico"].value_counts().reset_index()
            status_contagem.columns = ["Status", "Total"]
            fig_status = px.pie(status_contagem, names="Status", values="Total", hole=0.45)
            st.plotly_chart(fig_status, use_container_width=True)

        st.subheader("Prioridade")
        if not df_acoes_filtrado.empty:
            prioridade_contagem = df_acoes_filtrado["Prioridade"].value_counts().reset_index()
            prioridade_contagem.columns = ["Prioridade", "Total"]
            fig_pri = px.bar(prioridade_contagem, x="Total", y="Prioridade", orientation="h")
            st.plotly_chart(fig_pri, use_container_width=True)

    st.divider()
    st.subheader("Evolução e cronograma")

    if df_acoes_filtrado.empty:
        st.info("Sem dados suficientes para gerar gráficos.")
    else:
        col_g1, col_g2 = st.columns(2)

        with col_g1:
            df_evolucao = df_acoes_filtrado.copy()
            df_evolucao["Mês"] = pd.to_datetime(df_evolucao["Data_termino_prevista"], errors="coerce").dt.to_period("M").astype(str)
            df_evolucao = df_evolucao.dropna(subset=["Mês"])

            if not df_evolucao.empty:
                evolucao = (
                    df_evolucao.groupby("Mês")
                    .agg(
                        Acoes=("ID", "count"),
                        Concluidas=("Status_automatico", lambda x: x.isin(["Concluída", "Concluída com atraso"]).sum()),
                        Atrasadas=("Status_automatico", lambda x: (x == "Atrasada").sum())
                    )
                    .reset_index()
                )
                fig_evo = go.Figure()
                fig_evo.add_trace(go.Scatter(x=evolucao["Mês"], y=evolucao["Acoes"], mode="lines+markers", name="Ações previstas"))
                fig_evo.add_trace(go.Scatter(x=evolucao["Mês"], y=evolucao["Concluidas"], mode="lines+markers", name="Concluídas"))
                fig_evo.add_trace(go.Scatter(x=evolucao["Mês"], y=evolucao["Atrasadas"], mode="lines+markers", name="Atrasadas"))
                fig_evo.update_layout(title="Evolução mensal", xaxis_title="Mês", yaxis_title="Número de ações")
                st.plotly_chart(fig_evo, use_container_width=True)
            else:
                st.info("Informe datas previstas para gerar a evolução mensal.")

        with col_g2:
            df_gantt = df_acoes_filtrado.dropna(subset=["Data_inicio", "Data_termino_prevista"]).copy()

            if not df_gantt.empty:
                df_gantt["Data_inicio"] = pd.to_datetime(df_gantt["Data_inicio"])
                df_gantt["Data_termino_prevista"] = pd.to_datetime(df_gantt["Data_termino_prevista"])
                df_gantt["Rotulo"] = df_gantt["Projeto"] + " | " + df_gantt["Ação"].astype(str).str[:35]

                fig_gantt = px.timeline(
                    df_gantt,
                    x_start="Data_inicio",
                    x_end="Data_termino_prevista",
                    y="Rotulo",
                    color="Status_automatico",
                    hover_data=["Responsável", "Prioridade", "Percentual_conclusao"]
                )
                fig_gantt.update_yaxes(autorange="reversed")
                fig_gantt.update_layout(title="Cronograma das ações")
                st.plotly_chart(fig_gantt, use_container_width=True)
            else:
                st.info("Informe data de início e término previsto para gerar o cronograma.")

    st.divider()
    st.subheader("Alertas")

    if df_acoes_filtrado.empty:
        st.info("Nenhum alerta disponível.")
    else:
        col_al1, col_al2 = st.columns(2)

        with col_al1:
            st.markdown("### Ações atrasadas")
            atrasos = df_acoes_filtrado[df_acoes_filtrado["Status_automatico"] == "Atrasada"]
            if atrasos.empty:
                st.success("Nenhuma ação atrasada.")
            else:
                st.dataframe(
                    atrasos[["ID", "Projeto", "Ação", "Responsável", "Data_termino_prevista", "Dias_atraso"]],
                    use_container_width=True,
                    hide_index=True
                )

        with col_al2:
            st.markdown("### Próximas do prazo")
            proximas = df_acoes_filtrado[df_acoes_filtrado["Status_automatico"] == "Próxima do prazo"]
            if proximas.empty:
                st.success("Nenhuma ação próxima do prazo.")
            else:
                st.dataframe(
                    proximas[["ID", "Projeto", "Ação", "Responsável", "Data_termino_prevista"]],
                    use_container_width=True,
                    hide_index=True
                )

# =========================================================
# NOVA AÇÃO
# =========================================================

elif pagina == "Nova ação":
    st.title("Nova ação")
    st.caption("Cadastre uma ação, responsável, datas, prioridade e percentual de conclusão.")

    if not acesso_admin:
        usuario_nome = usuario_logado.iloc[0]["Nome"]
        usuario_email = usuario_logado.iloc[0]["Email"]
    else:
        usuario_nome = ""
        usuario_email = email_usuario

    if projetos_ativos.empty:
        st.warning("Cadastre pelo menos um projeto ativo antes de registrar ações.")
        st.stop()

    usuarios_ativos = df_usuarios[df_usuarios["Ativo"].apply(usuario_ativo)].copy() if not df_usuarios.empty else pd.DataFrame(columns=COLUNAS_USUARIOS)
    usuarios_ativos["Usuario_label"] = usuarios_ativos["Nome"].astype(str) + " — " + usuarios_ativos["Email"].astype(str)

    with st.form("form_nova_acao", clear_on_submit=True):
        col1, col2 = st.columns(2)

        with col1:
            projeto = st.selectbox("Projeto", projetos_ativos["Projeto"].dropna().unique())
            acao = st.text_area("Ação", height=100, placeholder="Descreva objetivamente a ação a ser realizada.")

            if acesso_admin and not usuarios_ativos.empty:
                resp_label = st.selectbox("Responsável", usuarios_ativos["Usuario_label"].tolist())
                resp_linha = usuarios_ativos[usuarios_ativos["Usuario_label"] == resp_label].iloc[0]
                responsavel = resp_linha["Nome"]
                responsavel_email = resp_linha["Email"]
            else:
                responsavel = usuario_nome
                responsavel_email = usuario_email
                st.text_input("Responsável", value=responsavel, disabled=True)

            prioridade = st.selectbox("Prioridade", PRIORIDADES, index=1)

        with col2:
            data_inicio = st.date_input("Data de início", value=date.today())
            data_termino = st.date_input("Data prevista de término", value=date.today())
            data_conclusao = st.date_input("Data de conclusão", value=None)
            status = st.selectbox("Status informado", STATUS_DISPONIVEIS)
            percentual = st.slider("Percentual de conclusão", min_value=0, max_value=100, value=0, step=5)

        observacoes = st.text_area("Observações", height=120)

        enviar = st.form_submit_button("Salvar ação", type="primary")

    if enviar:
        if not acao.strip():
            st.warning("Descreva a ação antes de salvar.")
        else:
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            nova = {
                "ID": gerar_id_acao(df_acoes_raw),
                "Projeto": projeto,
                "Ação": acao.strip(),
                "Responsável": responsavel,
                "Responsável_email": normalizar_email(responsavel_email),
                "Data_inicio": data_inicio.strftime("%Y-%m-%d"),
                "Data_termino_prevista": data_termino.strftime("%Y-%m-%d"),
                "Data_conclusao": data_conclusao.strftime("%Y-%m-%d") if data_conclusao else "",
                "Status_informado": status,
                "Prioridade": prioridade,
                "Percentual_conclusao": percentual,
                "Observações": observacoes,
                "Criado_em": agora,
                "Atualizado_em": agora,
                "Atualizado_por": email_usuario
            }
            adicionar_acao(nova)
            st.success("Ação salva com sucesso.")

# =========================================================
# MINHAS/TODAS AS AÇÕES
# =========================================================

elif pagina in ["Minhas ações", "Todas as ações"]:
    st.title("Ações")

    df_lista = df_acoes.copy()

    if pagina == "Minhas ações" or not acesso_admin:
        df_lista = df_lista[df_lista["Responsável_email"].apply(normalizar_email) == email_usuario].copy()

    if filtro_projeto:
        df_lista = df_lista[df_lista["Projeto"].isin(filtro_projeto)].copy()

    if df_lista.empty:
        st.info("Nenhuma ação encontrada.")
    else:
        status_filtro = st.multiselect(
            "Filtrar por status automático",
            sorted(df_lista["Status_automatico"].dropna().unique()),
            default=sorted(df_lista["Status_automatico"].dropna().unique())
        )

        df_lista = df_lista[df_lista["Status_automatico"].isin(status_filtro)].copy()

        st.dataframe(
            df_lista[
                [
                    "ID",
                    "Projeto",
                    "Ação",
                    "Responsável",
                    "Data_inicio",
                    "Data_termino_prevista",
                    "Data_conclusao",
                    "Status_informado",
                    "Status_automatico",
                    "Prioridade",
                    "Percentual_conclusao",
                    "Dias_atraso",
                    "Observações"
                ]
            ].sort_values(["Status_automatico", "Data_termino_prevista"]),
            use_container_width=True,
            hide_index=True,
            height=650
        )

        st.subheader("Atualizar ação existente")
        id_acao = st.selectbox("Selecione o ID da ação", df_lista["ID"].tolist())
        linha = df_lista[df_lista["ID"] == id_acao].iloc[0]

        pode_editar = acesso_admin or normalizar_email(linha["Responsável_email"]) == email_usuario

        if not pode_editar:
            st.warning("Você não tem permissão para editar esta ação.")
        else:
            with st.form("form_editar_acao"):
                col1, col2 = st.columns(2)

                with col1:
                    novo_status = st.selectbox(
                        "Status informado",
                        STATUS_DISPONIVEIS,
                        index=STATUS_DISPONIVEIS.index(linha["Status_informado"]) if linha["Status_informado"] in STATUS_DISPONIVEIS else 0
                    )
                    novo_percentual = st.slider(
                        "Percentual de conclusão",
                        min_value=0,
                        max_value=100,
                        value=int(linha["Percentual_conclusao"]),
                        step=5
                    )
                    nova_prioridade = st.selectbox(
                        "Prioridade",
                        PRIORIDADES,
                        index=PRIORIDADES.index(linha["Prioridade"]) if linha["Prioridade"] in PRIORIDADES else 1
                    )

                with col2:
                    nova_data_conclusao = st.date_input(
                        "Data de conclusão",
                        value=linha["Data_conclusao"].date() if pd.notna(linha["Data_conclusao"]) else None
                    )
                    nova_data_termino = st.date_input(
                        "Data prevista de término",
                        value=linha["Data_termino_prevista"].date() if pd.notna(linha["Data_termino_prevista"]) else date.today()
                    )

                novas_obs = st.text_area("Observações", value=str(linha["Observações"]), height=120)

                salvar_edicao = st.form_submit_button("Salvar atualização", type="primary")

            if salvar_edicao:
                df_editado = df_acoes_raw.copy()
                idx = df_editado[df_editado["ID"] == id_acao].index

                if len(idx) == 0:
                    st.error("ID não encontrado na base original.")
                else:
                    i = idx[0]
                    df_editado.loc[i, "Status_informado"] = novo_status
                    df_editado.loc[i, "Percentual_conclusao"] = novo_percentual
                    df_editado.loc[i, "Prioridade"] = nova_prioridade
                    df_editado.loc[i, "Data_termino_prevista"] = nova_data_termino.strftime("%Y-%m-%d") if nova_data_termino else ""
                    df_editado.loc[i, "Data_conclusao"] = nova_data_conclusao.strftime("%Y-%m-%d") if nova_data_conclusao else ""
                    df_editado.loc[i, "Observações"] = novas_obs
                    df_editado.loc[i, "Atualizado_em"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    df_editado.loc[i, "Atualizado_por"] = email_usuario

                    salvar_tabela(ABA_ACOES, COLUNAS_ACOES, df_editado)
                    st.success("Ação atualizada com sucesso.")

# =========================================================
# CADASTRO DE PROJETOS
# =========================================================

elif pagina == "Cadastro de projetos":
    st.title("Cadastro de projetos")

    with st.form("form_projeto"):
        col1, col2 = st.columns(2)

        with col1:
            novo_projeto = st.text_input("Nome do projeto")
            descricao = st.text_area("Descrição", height=100)
            coordenador_email = st.text_input("E-mail do coordenador")

        with col2:
            data_inicio = st.date_input("Data de início", value=date.today())
            data_termino = st.date_input("Data prevista de término", value=date.today())
            ativo = st.selectbox("Ativo", ["Sim", "Não"])

        cadastrar = st.form_submit_button("Adicionar projeto", type="primary")

    if cadastrar:
        if not novo_projeto.strip():
            st.warning("Informe o nome do projeto.")
        else:
            novo = pd.DataFrame([
                {
                    "Projeto": novo_projeto.strip(),
                    "Descrição": descricao,
                    "Data_inicio": data_inicio.strftime("%Y-%m-%d"),
                    "Data_termino_prevista": data_termino.strftime("%Y-%m-%d"),
                    "Coordenador_email": normalizar_email(coordenador_email),
                    "Ativo": ativo
                }
            ])
            df_final = pd.concat([df_projetos[COLUNAS_PROJETOS], novo], ignore_index=True)
            salvar_tabela(ABA_PROJETOS, COLUNAS_PROJETOS, df_final)
            st.success("Projeto cadastrado com sucesso.")

    st.subheader("Projetos cadastrados")
    editado = st.data_editor(
        df_projetos[COLUNAS_PROJETOS],
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic"
    )

    if st.button("Salvar alterações nos projetos"):
        salvar_tabela(ABA_PROJETOS, COLUNAS_PROJETOS, editado)
        st.success("Projetos atualizados.")

# =========================================================
# CADASTRO DE USUÁRIOS
# =========================================================

elif pagina == "Cadastro de usuários":
    st.title("Cadastro de usuários")

    with st.form("form_usuario"):
        col1, col2, col3 = st.columns(3)

        with col1:
            nome = st.text_input("Nome")
            email = st.text_input("E-mail")
            senha = st.text_input("Senha", type="password")

        with col2:
            perfil = st.selectbox("Perfil", ["Membro", "Coordenador", "Administrador"])

        with col3:
            ativo = st.selectbox("Ativo", ["Sim", "Não"])

        cadastrar = st.form_submit_button("Adicionar usuário", type="primary")

    if cadastrar:
        if not nome.strip():
            st.warning("Informe o nome.")
        elif not email.strip():
            st.warning("Informe o e-mail.")
        else:
            novo = pd.DataFrame([
                {
                    "Nome": nome.strip(),
                    "Email": normalizar_email(email),
                    "Senha": senha,
                    "Perfil": perfil,
                    "Ativo": ativo
                }
            ])
            df_final = pd.concat([df_usuarios[COLUNAS_USUARIOS], novo], ignore_index=True)
            salvar_tabela(ABA_USUARIOS, COLUNAS_USUARIOS, df_final)
            st.success("Usuário cadastrado com sucesso.")

    st.subheader("Usuários cadastrados")
    editado = st.data_editor(
        df_usuarios[COLUNAS_USUARIOS],
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic"
    )

    if st.button("Salvar alterações nos usuários"):
        salvar_tabela(ABA_USUARIOS, COLUNAS_USUARIOS, editado)
        st.success("Usuários atualizados.")

# =========================================================
# EXPORTAR
# =========================================================

elif pagina == "Exportar dados":
    st.title("Exportar dados")

    projetos_export = df_projetos.to_csv(index=False).encode("utf-8-sig")
    usuarios_export = df_usuarios.to_csv(index=False).encode("utf-8-sig")
    acoes_export = df_acoes.to_csv(index=False).encode("utf-8-sig")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.download_button(
            "Baixar projetos",
            data=projetos_export,
            file_name="projetos.csv",
            mime="text/csv"
        )

    with col2:
        st.download_button(
            "Baixar usuários",
            data=usuarios_export,
            file_name="usuarios.csv",
            mime="text/csv"
        )

    with col3:
        st.download_button(
            "Baixar ações",
            data=acoes_export,
            file_name="acoes.csv",
            mime="text/csv"
        )

    st.info("Os dados principais ficam salvos na Planilha Google vinculada ao aplicativo.")
