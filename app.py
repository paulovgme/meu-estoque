import streamlit as st
import pandas as pd
import requests
import plotly.express as px

# --- 1. CONFIGURAÇÃO DOS LINKS (ATUALIZE AQUI) ---
# Certifique-se de que todos os links terminam em 'output=csv'
LINK_USUARIOS = "https://docs.google.com/spreadsheets/d/e/2PACX-1vR66hMMGy2uGkRwwHAAW_UL9tEq33eJe4gvY-RiI7BUuQMg2-Pmk7L8z6Jv17rQ5DvVEq0CtTPBPdnP/pub?gid=0&single=true&output=csv"
LINK_PRODUTOS = "https://docs.google.com/spreadsheets/d/e/2PACX-1vR66hMMGy2uGkRwwHAAW_UL9tEq33eJe4gvY-RiI7BUuQMg2-Pmk7L8z6Jv17rQ5DvVEq0CtTPBPdnP/pub?gid=622782364&single=true&output=csv"
LINK_HISTORICO = "https://docs.google.com/spreadsheets/d/e/2PACX-1vR66hMMGy2uGkRwwHAAW_UL9tEq33eJe4gvY-RiI7BUuQMg2-Pmk7L8z6Jv17rQ5DvVEq0CtTPBPdnP/pub?gid=289837026&single=true&output=csv" 
URL_SCRIPTS = "https://script.google.com/macros/s/AKfycbySCqqo0cAYYCy2nNvdKPG-OsrGvz_youwQQmxWt0GRNOmRxeUrwDaMhrNnXv67MQ5l/exec"

# Configuração da Página
st.set_page_config(page_title="Ti Ercal - Gestão", page_icon="🧡", layout="wide")

# --- 2. ESTILO VISUAL (LARANJA E BRANCO) ---
st.markdown("""
    <style>
    .stApp { background-color: white; }
    .stButton>button { background-color: #FF8C00; color: white; border-radius: 8px; width: 100%; font-weight: bold; height: 3em; }
    .stMetric { background-color: #FFF5EE; padding: 15px; border-radius: 10px; border-left: 5px solid #FF8C00; }
    h1, h2, h3 { color: #FF8C00 !important; }
    div[data-testid="stExpander"] { border: 1px solid #FF8C00; background-color: #FFF9F5; }
    .stDataFrame { border: 1px solid #FF8C00; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

# Função para carregar dados
@st.cache_data(ttl=10)
def carregar_dados(url):
    try:
        df = pd.read_csv(url)
        df.columns = df.columns.str.strip().str.lower()
        return df
    except:
        return pd.DataFrame()

# Inicialização de variáveis de sessão
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
    st.session_state['user'] = ""
    st.session_state['nivel'] = ""

# --- 3. TELA DE LOGIN ---
if not st.session_state['logged_in']:
    st.title("🧡 Ti Ercal - Sistema de Gestão")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("form_login"):
            u = st.text_input("Usuário").strip().lower()
            p = st.text_input("Senha", type="password").strip()
            if st.form_submit_button("Entrar no Sistema"):
                df_u = carregar_dados(LINK_USUARIOS)
                if not df_u.empty:
                    valido = df_u[(df_u['usuario'].astype(str) == u) & (df_u['senha'].astype(str) == p)]
                    if not valido.empty:
                        st.session_state['logged_in'] = True
                        st.session_state['user'] = u
                        st.session_state['nivel'] = valido.iloc[0]['nivel'].strip().lower()
                        st.rerun()
                    else:
                        st.error("login invalido")
                else:
                    st.error("Erro ao carregar banco de usuários.")

# --- 4. SISTEMA LOGADO ---
else:
    # Definição do Menu Lateral com base no Nível
    if st.session_state['nivel'] == 'admin':
        opcoes = ["📊 Estatísticas", "📦 Estoque Atual", "🔄 Movimentação", "➕ Novo Produto", "👥 Gerenciar Usuários", "🚪 Sair"]
    else:
        opcoes = ["📊 Estatísticas", "📦 Estoque Atual", "🔄 Movimentação", "➕ Novo Produto", "🚪 Sair"]
    
    menu = st.sidebar.radio(f"Olá, {st.session_state['user'].capitalize()}", opcoes)

    if menu == "🚪 Sair":
        st.session_state['logged_in'] = False
        st.rerun()

    # --- ABA ESTATÍSTICAS ---
    if menu == "📊 Estatísticas":
        st.title("📊 Desempenho de Saídas")
        df_h = carregar_dados(LINK_HISTORICO)
        if not df_h.empty and 'acao' in df_h.columns:
            saidas = df_h[df_h['acao'].str.upper() == 'SAIDA']
            if not saidas.empty:
                estat = saidas.groupby('produto')['quantidade'].sum().reset_index()
                fig = px.bar(estat, x='produto', y='quantidade', title="Equipamentos com mais Saídas", color_discrete_sequence=['#FF8C00'])
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Nenhuma saída registrada para gerar gráficos.")
        else:
            st.warning("Histórico não encontrado ou aba não publicada.")

    # --- ABA ESTOQUE ---
    elif menu == "📦 Estoque Atual":
        st.title("📦 Controle de Estoque")
        df_p = carregar_dados(LINK_PRODUTOS)
        if not df_p.empty:
            # Lógica de Alerta
            if 'quantidade' in df_p.columns and 'alerta' in df_p.columns:
                df_p['quantidade'] = pd.to_numeric(df_p['quantidade'], errors='coerce').fillna(0)
                df_p['alerta'] = pd.to_numeric(df_p['alerta'], errors='coerce').fillna(0)
                baixo = df_p[df_p['quantidade'] <= df_p['alerta']]
                if not baixo.empty:
                    st.error(f"🚨 ALERTA: {len(baixo)} itens com estoque crítico!")
                    st.table(baixo[['nome', 'quantidade', 'alerta']])
            
            st.divider()
            st.dataframe(df_p, use_container_width=True, hide_index=True)
            if st.button("🔄 Sincronizar Agora"):
                st.cache_data.clear()
                st.rerun()

    # --- ABA MOVIMENTAÇÃO ---
    elif menu == "🔄 Movimentação":
        st.title("🔄 Registro de Entrada/Saída")
        df_p = carregar_dados(LINK_PRODUTOS)
        if not df_p.empty:
            with st.form("mov_form"):
                prod = st.selectbox("Selecione o Produto", df_p['nome'].unique())
                tipo = st.radio("Operação", ["ENTRADA", "SAIDA"])
                qtd = st.number_input("Quantidade", min_value=1, step=1)
                if st.form_submit_button("Confirmar"):
                    payload = {"tipo": "MOVIMENTACAO", "nome": prod, "acao": tipo, "valor": qtd, "operador": st.session_state['user']}
                    requests.post(URL_SCRIPTS, json=payload)
                    st.success("Registrado com sucesso!")
                    st.balloons()

    # --- ABA NOVO PRODUTO ---
    elif menu == "➕ Novo Produto":
        st.title("➕ Cadastrar Equipamento")
        with st.form("cad_form"):
            n = st.text_input("Nome")
            c = st.selectbox("Categoria", ["TI", "Infra", "Redes", "Outros"])
            q = st.number_input("Estoque Inicial", min_value=0)
            p = st.number_input("Preço", min_value=0.0)
            a = st.number_input("Alerta Mínimo", min_value=1)
            if st.form_submit_button("Salvar"):
                payload = {"tipo": "PRODUTO", "id": 0, "nome": n, "categoria": c, "quantidade": q, "preco": p, "alerta": a, "operador": st.session_state['user']}
                requests.post(URL_SCRIPTS, json=payload)
                st.success("Enviado para a planilha!")

    # --- ABA USUÁRIOS (SÓ ADMIN) ---
    elif menu == "👥 Gerenciar Usuários":
        st.title("👥 Gestão de Acessos")
        with st.expander("➕ Criar Novo Usuário"):
            with st.form("new_user"):
                new_u = st.text_input("Usuário").lower().strip()
                new_p = st.text_input("Senha")
                new_l = st.selectbox("Nível", ["operador", "admin"])
                if st.form_submit_button("Cadastrar"):
                    requests.post(URL_SCRIPTS, json={"tipo": "USUARIO", "usuario": new_u, "senha": new_p, "nivel": new_l})
                    st.success(f"Usuário {new_u} criado!")

        st.divider()
        st.subheader("🗑️ Remover Usuários")
        df_u = carregar_dados(LINK_USUARIOS)
        if not df_u.empty:
            st.dataframe(df_u[['usuario', 'nivel']], use_container_width=True, hide_index=True)
            u_del = st.selectbox("Selecione para remover", df_u['usuario'].unique())
            if st.button("❌ Excluir Usuário"):
                if u_del == st.session_state['user']:
                    st.error("Você não pode apagar seu próprio acesso!")
                else:
                    requests.post(URL_SCRIPTS, json={"tipo": "DELETAR_USUARIO", "usuario": u_del})
                    st.success(f"Usuário {u_del} removido!")
                    st.rerun()
