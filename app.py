import streamlit as st
import pandas as pd
from st_supabase_connection import SupabaseConnection

# 1. Configuração da página
st.set_page_config(page_title="Ti - Estoque", page_icon="🔥")

# 2. Conexão MANUAL (Forçando o uso das chaves)
try:
    # Pegamos o que você colou nos Secrets
    minha_url = st.secrets["URL_BANCO"]
    minha_chave = st.secrets["CHAVE_BANCO"]
    
    # Criamos a conexão entregando os dados na mão do sistema
    conn = st.connection(
        "supabase",
        type=SupabaseConnection,
        url=minha_url,
        key=minha_chave
    )
except Exception as e:
    st.error(f"❌ Erro crítico de conexão: {e}")
    st.stop()

st.title("🔥 Sistema de Estoque")

# 3. Teste de Login
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

if not st.session_state['logged_in']:
    with st.form("login"):
        u = st.text_input("Usuário").strip().lower()
        p = st.text_input("Senha", type="password").strip()
        if st.form_submit_button("Entrar"):
            # Busca no banco usando a conexão que acabamos de testar
            res = conn.query("*", table="usuarios").eq("usuario", u).eq("senha", p).execute()
            if res.data:
                st.session_state['logged_in'] = True
                st.rerun()
            else:
                st.error("Login inválido!")
else:
    st.success("Conectado com sucesso ao Banco de Dados!")
    if st.button("Sair"):
        st.session_state['logged_in'] = False
        st.rerun()
        
    # Mostra os produtos para confirmar
    st.write("### Lista de Produtos no Banco:")
    dados = conn.query("*", table="produtos").execute()
    st.dataframe(pd.DataFrame(dados.data))
