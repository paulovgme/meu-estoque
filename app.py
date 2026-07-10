import streamlit as st
import pandas as pd
from st_supabase_connection import SupabaseConnection

# 1. Configuração da página (Deve ser a primeira coisa sempre)
st.set_page_config(page_title="Sistema de Estoque", page_icon="🔥")

# 2. Conexão com o Banco
@st.cache_resource
def conectar_banco():
    url = st.secrets["URL_BANCO"]
    key = st.secrets["CHAVE_BANCO"]
    return st.connection("supabase", type=SupabaseConnection, url=url, key=key)

conn = conectar_banco()

# 3. Inicialização do Estado (Garante que as variáveis existam)
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'user_name' not in st.session_state:
    st.session_state.user_name = ""

# --- FUNÇÃO DE LOGIN ---
def realizar_login(u, p):
    try:
        res = conn.table("usuarios").select("*").eq("usuario", u.lower()).eq("senha", p).execute()
        if res.data:
            st.session_state.logged_in = True
            st.session_state.user_name = u
            st.rerun()
        else:
            st.error("Usuário ou senha incorretos.")
    except Exception as e:
        st.error(f"Erro de conexão com o banco: {e}")

# --- INTERFACE ---

# Se NÃO estiver logado, mostra APENAS a tela de login
if not st.session_state.logged_in:
    st.title("🔥 Acesso ao Sistema")
    
    # Usamos chaves (key) únicas para o navegador não se perder
    usuario_input = st.text_input("Usuário", key="input_user").strip()
    senha_input = st.text_input("Senha", type="password", key="input_pass").strip()
    
    if st.button("Entrar", key="btn_login"):
        if usuario_input and senha_input:
            realizar_login(usuario_input, senha_input)
        else:
            st.warning("Preencha todos os campos.")

# Se ESTIVER logado, mostra o sistema
else:
    st.sidebar.title(f"Olá, {st.session_state.user_name.capitalize()}")
    if st.sidebar.button("Sair", key="btn_logout"):
        st.session_state.logged_in = False
        st.rerun()

    st.title("📦 Estoque Atual")
    
    # Carrega os dados
    try:
        dados = conn.table("produtos").select("*").execute()
        df = pd.DataFrame(dados.data)
        
        if not df.empty:
            st.write("Dados carregados do Supabase:")
            st.dataframe(df, use_container_width=True)
        else:
            st.info("Nenhum produto cadastrado no banco.")
            
    except Exception as e:
        st.error(f"Erro ao carregar produtos: {e}")
