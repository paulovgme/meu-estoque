import streamlit as st
import pandas as pd
from st_supabase_connection import SupabaseConnection

# 1. Configuração simples
st.set_page_config(page_title="Sistema de Estoque", page_icon="🔥")

# 2. Conexão (direta nos segredos)
try:
    url = st.secrets["URL_BANCO"]
    key = st.secrets["CHAVE_BANCO"]
    conn = st.connection("supabase", type=SupabaseConnection, url=url, key=key)
except Exception as e:
    st.error(f"Erro de conexão: {e}")
    st.stop()

# 3. Estado do login
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

# 4. Interface
st.title("🔥 Ti - Sistema de Gestão")

if not st.session_state['logged_in']:
    st.info("Por favor, faça o login para continuar.")
    
    # Login simples sem colunas para evitar erro de carregamento
    u = st.text_input("Usuário").strip().lower()
    p = st.text_input("Senha", type="password").strip()
    
    if st.button("Acessar Sistema"):
        try:
            # Busca no banco
            res = conn.table("usuarios").select("*").eq("usuario", u).eq("senha", p).execute()
            if res.data:
                st.session_state['logged_in'] = True
                st.session_state['user'] = u
                st.session_state['nivel'] = res.data[0]['nivel'].strip().lower()
                st.rerun()
            else:
                st.error("Login inválido!")
        except Exception as e:
            st.error(f"Erro ao consultar banco: {e}")

else:
    st.sidebar.write(f"Logado como: {st.session_state['user']}")
    if st.sidebar.button("Sair"):
        st.session_state['logged_in'] = False
        st.rerun()

    # Mostra os produtos logo de cara para testar
    st.write("### Itens no Estoque")
    try:
        dados = conn.table("produtos").select("*").execute()
        df = pd.DataFrame(dados.data)
        if not df.empty:
            st.dataframe(df, use_container_width=True)
        else:
            st.warning("Nenhum produto encontrado.")
    except Exception as e:
        st.error(f"Erro ao carregar produtos: {e}")
