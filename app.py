import streamlit as st
import pandas as pd
from supabase import create_client, Client

# Configuração básica
st.set_page_config(page_title="Sistema Ti", page_icon="🔥")

# Conexão
@st.cache_resource
def get_supabase():
    return create_client(st.secrets["URL_BANCO"], st.secrets["CHAVE_BANCO"])

supabase = get_supabase()

if 'logado' not in st.session_state:
    st.session_state.logado = False

if not st.session_state.logado:
    st.title("🔥 Login")
    with st.form("login"):
        u = st.text_input("Usuário")
        p = st.text_input("Senha", type="password")
        if st.form_submit_button("Entrar"):
            res = supabase.table("usuarios").select("*").eq("usuario", u).eq("senha", p).execute()
            if res.data:
                st.session_state.logado = True
                st.session_state.user = u
                st.rerun()
            else:
                st.error("Erro!")
else:
    st.title(f"📦 Estoque - Olá {st.session_state.user}")
    if st.button("Sair"):
        st.session_state.logado = False
        st.rerun()
        
    try:
        dados = supabase.table("produtos").select("*").execute()
        if dados.data:
            df = pd.DataFrame(dados.data)
            # Versão mais segura da tabela para evitar crashes visuais
            st.table(df.head(20)) 
        else:
            st.write("Vazio")
    except Exception as e:
        st.error(f"Erro: {e}")
