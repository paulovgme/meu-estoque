import streamlit as st
import pandas as pd
from st_supabase_connection import SupabaseConnection

# 1. Configuração básica
st.set_page_config(page_title="Ti - Estoque", page_icon="🔥")

# 2. Conexão (O Streamlit vai buscar sozinho em [connections.supabase])
conn = st.connection("supabase", type=SupabaseConnection)

# 3. Título da página
st.title("🔥 Sistema de Estoque")

# 4. Teste de Login Simples
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

if not st.session_state['logged_in']:
    u = st.text_input("Usuário")
    p = st.text_input("Senha", type="password")
    if st.button("Entrar"):
        # Busca no banco
        res = conn.query("*", table="usuarios").eq("usuario", u.lower()).eq("senha", p).execute()
        if res.data:
            st.session_state['logged_in'] = True
            st.rerun()
        else:
            st.error("Usuário ou senha incorretos")

else:
    st.success(f"Bem-vindo! Conexão com Supabase está ativa.")
    # Mostra os produtos para testar
    df = conn.query("*", table="produtos").execute()
    st.write("### Seus Produtos:")
    st.dataframe(pd.DataFrame(df.data))
    
    if st.button("Sair"):
        st.session_state['logged_in'] = False
        st.rerun()
