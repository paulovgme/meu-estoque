import streamlit as st
import pandas as pd
import requests
import plotly.express as px

# --- 1. CONFIGURAÇÃO DOS LINKS (MANTENHA OS SEUS) ---
LINK_USUARIOS = "https://docs.google.com/spreadsheets/d/e/2PACX-1vR66hMMGy2uGkRwwHAAW_UL9tEq33eJe4gvY-RiI7BUuQMg2-Pmk7L8z6Jv17rQ5DvVEq0CtTPBPdnP/pub?gid=0&single=true&output=csv"
LINK_PRODUTOS = "https://docs.google.com/spreadsheets/d/e/2PACX-1vR66hMMGy2uGkRwwHAAW_UL9tEq33eJe4gvY-RiI7BUuQMg2-Pmk7L8z6Jv17rQ5DvVEq0CtTPBPdnP/pub?gid=622782364&single=true&output=csv"
LINK_HISTORICO = "https://docs.google.com/spreadsheets/d/e/2PACX-1vR66hMMGy2uGkRwwHAAW_UL9tEq33eJe4gvY-RiI7BUuQMg2-Pmk7L8z6Jv17rQ5DvVEq0CtTPBPdnP/pub?gid=289837026&single=true&output=csv"
URL_SCRIPTS = "https://script.google.com/macros/s/AKfycbySCqqo0cAYYCy2nNvdKPG-OsrGvz_youwQQmxWt0GRNOmRxeUrwDaMhrNnXv67MQ5l/exec"

st.set_page_config(page_title="Ti - Estoque", page_icon="🔥", layout="wide")

# --- ESTILO VISUAL ---
st.markdown("""
    <style>
    .stApp { background-color: white; }
    .stButton>button { background-color: #FF8C00; color: white; border-radius: 8px; width: 100%; font-weight: bold; }
    h1, h2, h3 { color: #FF8C00 !important; }
    .stMetric { background-color: #FFF5EE; padding: 15px; border-radius: 10px; border-left: 5px solid #FF8C00; }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=5)
def carregar_dados(url):
    try:
        df = pd.read_csv(url)
        df.columns = df.columns.str.strip().str.lower()
        return df
    except:
        return pd.DataFrame()

if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

# --- LOGIN ---
if not st.session_state['logged_in']:
    st.title("🔥 Ti - Sistema de Gestão")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("form_login"):
            u = st.text_input("Usuário").strip().lower()
            p = st.text_input("Senha", type="password").strip()
            if st.form_submit_button("Acessar Sistema"):
                df_u = carregar_dados(LINK_USUARIOS)
                valido = df_u[(df_u['usuario'].astype(str) == u) & (df_u['senha'].astype(str) == p)]
                if not valido.empty:
                    st.session_state['logged_in'] = True
                    st.session_state['user'] = u
                    st.session_state['nivel'] = valido.iloc[0]['nivel'].strip().lower()
                    st.rerun()
                else:
                    st.error("login invalido")

# --- SISTEMA ---
else:
    # DEFINIÇÃO DO MENU POR NÍVEL
    if st.session_state['nivel'] == 'admin':
        opcoes = ["📊 Estatísticas", "📦 Estoque Atual", "🔄 Movimentação", "➕ Novo Produto", "🛠️ Ajustar Produto", "👥 Gerenciar Usuários", "🚪 Sair"]
    else:
        opcoes = ["📊 Estatísticas", "📦 Estoque Atual", "🔄 Movimentação", "➕ Novo Produto", "🚪 Sair"]
    
    menu = st.sidebar.radio(f"Olá, {st.session_state['user'].capitalize()}", opcoes)

    if menu == "🚪 Sair":
        st.session_state['logged_in'] = False
        st.rerun()

    # --- ABA ESTATÍSTICAS ---
    if menu == "📊 Estatísticas":
        st.title("📊 Desempenho")
        df_h = carregar_dados(LINK_HISTORICO)
        if not df_h.empty:
            saidas = df_h[df_h['acao'].str.upper() == 'SAIDA']
            if not saidas.empty:
                estat = saidas.groupby('produto')['quantidade'].sum().reset_index()
                st.plotly_chart(px.bar(estat, x='produto', y='quantidade', color_discrete_sequence=['#FF8C00']), use_container_width=True)
            else: st.info("Sem dados de saída.")

    # --- ABA ESTOQUE ---
    elif menu == "📦 Estoque Atual":
        st.title("📦 Controle de Estoque")
        df_p = carregar_dados(LINK_PRODUTOS)
        if not df_p.empty:
            # Alertas
            baixo = df_p[df_p['quantidade'] <= df_p['alerta']]
            if not baixo.empty:
                st.error(f"🚨 ESTOQUE CRÍTICO EM {len(baixo)} ITENS")
            st.dataframe(df_p, use_container_width=True, hide_index=True)
            if st.button("🔄 Sincronizar"):
                st.cache_data.clear()
                st.rerun()

    # --- ABA MOVIMENTAÇÃO ---
    elif menu == "🔄 Movimentação":
        st.title("🔄 Registro de Entrada/Saída")
        df_p = carregar_dados(LINK_PRODUTOS)
        with st.form("mov"):
            prod = st.selectbox("Equipamento", df_p['nome'].unique())
            tipo = st.radio("Operação", ["ENTRADA", "SAIDA"])
            qtd = st.number_input("Quantidade", min_value=1)
            if st.form_submit_button("Confirmar"):
                requests.post(URL_SCRIPTS, json={"tipo": "MOVIMENTACAO", "nome": prod, "acao": tipo, "valor": qtd, "operador": st.session_state['user']})
                st.success("Registrado!")

    # --- ABA NOVO PRODUTO ---
    elif menu == "➕ Novo Produto":
        st.title("➕ Cadastrar Equipamento")
        with st.form("cad"):
            n = st.text_input("Nome")
            c = st.selectbox("Categoria", ["TI", "Infra", "Redes", "Outros"])
            q = st.number_input("Estoque Inicial", min_value=0)
            p = st.number_input("Preço", min_value=0.0)
            a = st.number_input("Alerta", min_value=1)
            if st.form_submit_button("Salvar"):
                requests.post(URL_SCRIPTS, json={"tipo": "PRODUTO", "id": 0, "nome": n, "categoria": c, "quantidade": q, "preco": p, "alerta": a, "operador": st.session_state['user']})
                st.success("Cadastrado!")

    # --- ABA AJUSTAR PRODUTO (SÓ ADMIN) ---
    elif menu == "🛠️ Ajustar Produto":
        st.title("🛠️ Corrigir Nome de Produto")
        st.warning("Use esta função apenas para corrigir erros de grafia. O histórico registrará a mudança.")
        df_p = carregar_dados(LINK_PRODUTOS)
        nome_errado = st.selectbox("Selecione o produto com nome errado", df_p['nome'].unique())
        nome_certo = st.text_input("Digite o nome correto")
        if st.button("Aplicar Correção"):
            if nome_certo:
                requests.post(URL_SCRIPTS, json={"tipo": "EDITAR_PRODUTO", "nome_antigo": nome_errado, "nome_novo": nome_certo, "operador": st.session_state['user']})
                st.success(f"Nome alterado de '{nome_errado}' para '{nome_certo}'!")
                st.cache_data.clear()
            else: st.error("Digite o nome correto.")

    # --- ABA USUÁRIOS (SÓ ADMIN) ---
    elif menu == "👥 Gerenciar Usuários":
        st.title("👥 Gestão de Acessos")
        with st.expander("➕ Novo Usuário"):
            with st.form("u"):
                nu = st.text_input("Usuário").lower()
                ns = st.text_input("Senha")
                nl = st.selectbox("Nível", ["operador", "admin"])
                if st.form_submit_button("Criar"):
                    requests.post(URL_SCRIPTS, json={"tipo": "USUARIO", "usuario": nu, "senha": ns, "nivel": nl})
                    st.success("Criado!")
        
        st.divider()
        df_u = carregar_dados(LINK_USUARIOS)
        u_del = st.selectbox("Remover Usuário", df_u['usuario'].unique())
        if st.button("❌ Excluir"):
            if u_del != st.session_state['user']:
                requests.post(URL_SCRIPTS, json={"tipo": "DELETAR_USUARIO", "usuario": u_del})
                st.success("Removido!")
                st.rerun()
            else: st.error("Você não pode se apagar.")
