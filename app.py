import streamlit as st
import pandas as pd
from supabase import create_client, Client

# Configuração de página
st.set_page_config(page_title="Sistema Ti", page_icon="🔥")

# 1. Conexão direta com Supabase (mais estável)
@st.cache_resource
def get_supabase() -> Client:
    url = st.secrets["URL_BANCO"]
    key = st.secrets["CHAVE_BANCO"]
    return create_client(url, key)

supabase = get_supabase()

# 2. Estado de Login
if 'logado' not in st.session_state:
    st.session_state.logado = False

# --- LÓGICA DE TELAS ---

if not st.session_state.logado:
    st.title("🔥 Acesso ao Sistema")
    
    with st.form("login_form"):
        user = st.text_input("Usuário").strip().lower()
        senha = st.text_input("Senha", type="password").strip()
        if st.form_submit_button("Entrar"):
            try:
                # Busca usuário
                res = supabase.table("usuarios").select("*").eq("usuario", user).eq("senha", senha).execute()
                
                if res.data:
                    st.session_state.logado = True
                    st.session_state.usuario_nome = user
                    st.rerun()
                else:
                    st.error("Usuário ou senha inválidos.")
            except Exception as e:
                st.error(f"Erro de conexão: {e}")

else:
    st.sidebar.title(f"Olá, {st.session_state.usuario_nome}")
    if st.sidebar.button("Sair"):
        st.session_state.logado = False
        st.rerun()

    st.title("📦 Estoque Atual")
    
    try:
        # Busca dados
        resultado = supabase.table("produtos").select("*").execute()
        
        if resultado.data:
            df = pd.DataFrame(resultado.data)
            
            # Ajustado conforme o seu Log sugeriu (width='stretch' em vez de use_container_width)
            st.dataframe(df, width=None, hide_index=True)
            
        else:
            st.info("Nenhum produto encontrado no banco de dados.")
            
    except Exception as e:
        st.error(f"Erro ao carregar dados: {e}")
