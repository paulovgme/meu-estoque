import streamlit as st
import pandas as pd
from st_supabase_connection import SupabaseConnection

# 1. Configuração de página
st.set_page_config(page_title="Sistema Ti", page_icon="🔥")

# 2. Conexão com Cache
@st.cache_resource
def iniciar_conexao():
    return st.connection(
        "supabase", 
        type=SupabaseConnection, 
        url=st.secrets["URL_BANCO"], 
        key=st.secrets["CHAVE_BANCO"]
    )

conn = iniciar_conexao()

# 3. Estado de Login
if 'logado' not in st.session_state:
    st.session_state.logado = False

# Criamos um "espaço vazio" que ocupará a tela toda
container_principal = st.empty()

# --- LÓGICA DE TROCA DE TELAS ---

if not st.session_state.logado:
    # Desenhamos o login DENTRO do container vazio
    with container_principal.container():
        st.title("🔥 Acesso ao Sistema")
        
        user = st.text_input("Usuário", key="u_login").strip().lower()
        senha = st.text_input("Senha", type="password", key="p_login").strip()
        
        if st.button("Entrar", key="btn_entrar"):
            try:
                res = conn.table("usuarios").select("*").eq("usuario", user).eq("senha", senha).execute()
                
                if res.data:
                    # Antes de qualquer coisa, limpamos o container
                    container_principal.empty()
                    # Mudamos o estado e reiniciamos
                    st.session_state.logado = True
                    st.session_state.usuario_nome = user
                    st.rerun()
                else:
                    st.error("Dados incorretos.")
            except Exception as e:
                st.error(f"Erro: {e}")

else:
    # Se estiver logado, o container principal fica com o conteúdo do sistema
    with container_principal.container():
        st.sidebar.title(f"Olá, {st.session_state.usuario_nome}")
        if st.sidebar.button("Sair"):
            st.session_state.logado = False
            st.rerun()

        st.title("📦 Estoque Atual")
        
        try:
            resultado = conn.table("produtos").select("*").execute()
            df = pd.DataFrame(resultado.data)
            
            if not df.empty:
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info("Estoque vazio.")
        except Exception as e:
            st.error(f"Erro ao carregar: {e}")
