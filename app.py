import streamlit as st
import pandas as pd
from st_supabase_connection import SupabaseConnection

# 1. Configuração da página
st.set_page_config(page_title="Ti - Estoque", page_icon="🔥")

# 2. Conexão (Já sabemos que as chaves estão funcionando!)
try:
    minha_url = st.secrets["URL_BANCO"]
    minha_chave = st.secrets["CHAVE_BANCO"]
    
    conn = st.connection(
        "supabase",
        type=SupabaseConnection,
        url=minha_url,
        key=minha_chave
    )
except Exception as e:
    st.error(f"❌ Erro na conexão: {e}")
    st.stop()

st.title("🔥 Sistema de Estoque")

# 3. Controle de Login
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

if not st.session_state['logged_in']:
    with st.form("login"):
        u = st.text_input("Usuário").strip().lower()
        p = st.text_input("Senha", type="password").strip()
        if st.form_submit_button("Entrar"):
            # COMANDO CORRIGIDO: Usando .table(...).select("*")
            res = conn.table("usuarios").select("*").eq("usuario", u).eq("senha", p).execute()
            
            if res.data:
                st.session_state['logged_in'] = True
                st.session_state['user'] = u
                st.session_state['nivel'] = res.data[0]['nivel']
                st.rerun()
            else:
                st.error("Login inválido!")
else:
    st.success(f"Conectado! Olá, {st.session_state['user']}")
    
    if st.button("Sair"):
        st.session_state['logged_in'] = False
        st.rerun()
        
    # 4. Mostrar Produtos (COMANDO CORRIGIDO)
    st.write("### Lista de Produtos:")
    try:
        dados = conn.table("produtos").select("*").execute()
        if dados.data:
            st.dataframe(pd.DataFrame(dados.data), use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum produto cadastrado ainda.")
    except Exception as e:
        st.error(f"Erro ao ler produtos: {e}")
