import streamlit as st
import pandas as pd
import plotly.express as px
from st_supabase_connection import SupabaseConnection

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Ti - Estoque", page_icon="🔥", layout="wide")

# --- CONEXÃO DIRETA (FORÇADA) ---
try:
    # Pegamos os dados do segredo mas entregamos na mão do sistema
    url_banco = st.secrets["connections"]["supabase"]["url"]
    key_banco = st.secrets["connections"]["supabase"]["key"]
    
    conn = st.connection(
        "supabase", 
        type=SupabaseConnection,
        url=url_banco,
        key=key_banco
    )
except Exception as e:
    st.error(f"❌ Erro de Leitura: {e}")
    st.info("Dica: Verifique se você salvou os Secrets corretamente.")
    st.stop()
