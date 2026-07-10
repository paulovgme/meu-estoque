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

# --- LÓGICA DE TROCA DE TELAS ---

if not st.session_state.logado:
    # --- TELA DE LOGIN ---
    st.title("🔥 Acesso ao Sistema")
    
    # Usamos um form para evitar que o app recarregue a cada letra digitada
    with st.form("login_form"):
        user = st.text_input("Usuário").strip().lower()
        senha = st.text_input("Senha", type="password").strip()
        botao_entrar = st.form_submit_button("Entrar")
        
        if botao_entrar:
            try:
                res = conn.table("usuarios").select("*").eq("usuario", user).eq("senha", senha).execute()
                
                if res.data:
                    st.session_state.logado = True
                    st.session_state.usuario_nome = user
                    st.rerun() # O rerun sozinho já limpa a tela de login
                else:
                    st.error("Dados incorretos.")
            except Exception as e:
                st.error(f"Erro de conexão: {e}")

else:
    # --- TELA DO SISTEMA ---
    st.sidebar.title(f"Olá, {st.session_state.usuario_nome}")
    if st.sidebar.button("Sair"):
        st.session_state.logado = False
        st.rerun()

    st.title("📦 Estoque Atual")
    
    try:
        # Busca os dados do Supabase
        resultado = conn.table("produtos").select("*").execute()
        
        if resultado.data:
            df = pd.DataFrame(resultado.data)
            # Mostra a tabela
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("Estoque vazio ou tabela não encontrada.")
            
    except Exception as e:
        st.error(f"Erro ao carregar dados do Supabase: {e}")
