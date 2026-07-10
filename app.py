import streamlit as st
import pandas as pd
from st_supabase_connection import SupabaseConnection

# 1. Configuração da página (Primeira linha sempre)
st.set_page_config(page_title="Estoque", page_icon="🔥")

# 2. Conexão com o Banco (Cache para evitar reconexões travadas)
@st.cache_resource
def iniciar_conexao():
    return st.connection(
        "supabase", 
        type=SupabaseConnection, 
        url=st.secrets["URL_BANCO"], 
        key=st.secrets["CHAVE_BANCO"]
    )

conn = iniciar_conexao()

# 3. Inicialização do estado de login
if 'logado' not in st.session_state:
    st.session_state.logado = False

# --- ÁREA DE LOGIN (Simples e sem Forms) ---
if not st.session_state.logado:
    st.title("🔥 Acesso ao Sistema")
    
    # Usamos chaves (key) para o Streamlit não se perder
    user_input = st.text_input("Usuário", key="login_user").strip().lower()
    pass_input = st.text_input("Senha", type="password", key="login_pass").strip()
    
    if st.button("Entrar no Sistema", key="btn_entrar"):
        if user_input and pass_input:
            try:
                # Busca direta no banco
                res = conn.table("usuarios").select("*").eq("usuario", user_input).eq("senha", pass_input).execute()
                
                if res.data:
                    st.session_state.logado = True
                    st.session_state.usuario_nome = user_input
                    st.rerun() # Reinicia para carregar o sistema
                else:
                    st.error("Usuário ou senha incorretos.")
            except Exception as e:
                st.error(f"Erro de conexão: {e}")
        else:
            st.warning("Preencha os campos de acesso.")

# --- ÁREA DO SISTEMA (Após o Login) ---
else:
    st.sidebar.title(f"Olá, {st.session_state.usuario_nome.capitalize()}")
    
    if st.sidebar.button("Sair", key="btn_logout"):
        st.session_state.logado = False
        st.rerun()

    st.title("📦 Controle de Estoque")

    # Botão para recarregar manualmente se necessário
    if st.button("🔄 Atualizar Lista"):
        st.rerun()

    try:
        # Busca produtos
        resultado = conn.table("produtos").select("*").execute()
        df = pd.DataFrame(resultado.data)
        
        if not df.empty:
            st.write("### Itens Cadastrados")
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("O estoque está vazio.")
            
    except Exception as e:
        st.error(f"Não foi possível carregar os dados: {e}")
