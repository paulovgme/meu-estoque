import streamlit as st
import pandas as pd
import plotly.express as px
from st_supabase_connection import SupabaseConnection

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Ti - Estoque", page_icon="🔥", layout="wide")

# --- CONEXÃO COM O BANCO ---
try:
    # Tentativa de conexão
    conn = st.connection("supabase", type=SupabaseConnection)
except Exception as e:
    st.error(f"❌ Erro ao ler os Secrets: {e}")
    st.stop()

# --- ESTILO VISUAL ---
st.markdown("""
    <style>
    .stApp { background-color: white; }
    .stButton>button { background-color: #FF8C00; color: white; border-radius: 8px; width: 100%; font-weight: bold; }
    h1, h2, h3 { color: #FF8C00 !important; }
    .stMetric { background-color: #FFF5EE; padding: 15px; border-radius: 10px; border-left: 5px solid #FF8C00; }
    </style>
    """, unsafe_allow_html=True)

# Função para carregar dados com tratamento de erro detalhado
def carregar_dados(tabela):
    try:
        res = conn.query("*", table=tabela).execute()
        return pd.DataFrame(res.data)
    except Exception as e:
        st.error(f"❌ Erro ao acessar a tabela '{tabela}': {e}")
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
                try:
                    res = conn.query("*", table="usuarios").eq("usuario", u).eq("senha", p).execute()
                    if res.data:
                        st.session_state['logged_in'] = True
                        st.session_state['user'] = u
                        st.session_state['nivel'] = res.data[0]['nivel'].strip().lower()
                        st.rerun()
                    else:
                        st.error("Usuário ou senha incorretos")
                except Exception as login_error:
                    st.error(f"Erro na verificação de login: {login_error}")

# --- SISTEMA APÓS LOGIN ---
else:
    opcoes = ["📊 Estatísticas", "📦 Estoque Atual", "🔄 Movimentação", "➕ Novo Produto", "🚪 Sair"]
    if st.session_state['nivel'] == 'admin':
        opcoes.insert(4, "🛠️ Ajustar Produto")
        opcoes.insert(5, "👥 Usuários")
    
    menu = st.sidebar.radio(f"Olá, {st.session_state['user'].capitalize()}", opcoes)

    if menu == "🚪 Sair":
        st.session_state['logged_in'] = False
        st.rerun()

    elif menu == "📦 Estoque Atual":
        st.title("📦 Controle de Estoque")
        df_p = carregar_dados("produtos")
        if not df_p.empty:
            st.dataframe(df_p, use_container_width=True, hide_index=True)

    elif menu == "➕ Novo Produto":
        st.title("➕ Cadastrar Equipamento")
        with st.form("cad"):
            n = st.text_input("Nome")
            c = st.selectbox("Categoria", ["TI", "Infra", "Redes", "Outros"])
            q = st.number_input("Estoque Inicial", min_value=0)
            p = st.number_input("Preço", min_value=0.0)
            a = st.number_input("Alerta", min_value=1)
            if st.form_submit_button("Salvar"):
                try:
                    conn.table("produtos").insert({"nome": n, "categoria": c, "quantidade": q, "preco": p, "alerta": a}).execute()
                    st.success("Cadastrado com sucesso!")
                except Exception as cad_error:
                    st.error(f"Erro ao salvar: {cad_error}")
