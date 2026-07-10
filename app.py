import streamlit as st
import pandas as pd
import plotly.express as px
from st_supabase_connection import SupabaseConnection
import time

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Ti - Estoque Profissional", page_icon="🔥", layout="wide")

# --- 2. CONEXÃO COM O BANCO ---
try:
    url_banco = st.secrets["URL_BANCO"]
    key_banco = st.secrets["CHAVE_BANCO"]
    
    conn = st.connection(
        "supabase",
        type=SupabaseConnection,
        url=url_banco,
        key=key_banco
    )
except Exception as e:
    st.error(f"❌ Erro na conexão: {e}")
    st.stop()

# --- 3. ESTILO VISUAL ---
st.markdown("""
    <style>
    .stApp { background-color: white; }
    .stButton>button { background-color: #FF8C00; color: white; border-radius: 8px; width: 100%; font-weight: bold; }
    h1, h2, h3 { color: #FF8C00 !important; }
    .stMetric { background-color: #FFF5EE; padding: 15px; border-radius: 10px; border-left: 5px solid #FF8C00; }
    </style>
    """, unsafe_allow_html=True)

# Função para carregar dados
def carregar_dados(tabela):
    try:
        res = conn.table(tabela).select("*").execute()
        return pd.DataFrame(res.data)
    except:
        return pd.DataFrame()

# --- 4. VERIFICAÇÃO DE LOGIN ---
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

if not st.session_state['logged_in']:
    st.title("🔥 Ti - Sistema de Gestão")
    col1, col2, col3 = st.columns([1, 2, 1])
