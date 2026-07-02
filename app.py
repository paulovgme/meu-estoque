import streamlit as st
import pandas as pd

# CONFIGURAÇÃO DOS LINKS QUE VOCÊ COPIOU (COLE AQUI ENTRE AS ASPAS)
LINK_USUARIOS = "COLE_AQUI_O_LINK_CSV_DA_ABA_USUARIOS"
LINK_PRODUTOS = "COLE_AQUI_O_LINK_CSV_DA_ABA_PRODUTOS"

st.set_page_config(page_title="Sistema Tiercal", layout="wide")

# --- LOGIN ---
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

if not st.session_state['logged_in']:
    st.title("🔐 Login Ti Ercal")
    user = st.text_input("Usuário")
    pw = st.text_input("Senha", type="password")
    if st.button("Entrar"):
        try:
            # Lê os usuários direto do link público
            df_user = pd.read_csv(LINK_USUARIOS)
            # Verifica se bate com a planilha
            valido = df_user[(df_user['usuario'] == user) & (df_user['senha'].astype(str) == str(pw))]
            if not valido.empty:
                st.session_state['logged_in'] = True
                st.rerun()
            else:
                st.error("Usuário ou senha incorretos")
        except:
            st.error("Erro ao conectar com a planilha. Verifique se ela foi 'Publicada na Web' como CSV.")
else:
    # --- SISTEMA APÓS LOGIN ---
    st.sidebar.success("Conectado!")
    menu = st.sidebar.selectbox("Menu", ["📦 Estoque", "🚪 Sair"])

    if menu == "🚪 Sair":
        st.session_state['logged_in'] = False
        st.rerun()

    if menu == "📦 Estoque":
        st.header("📦 Controle de Estoque")
        try:
            df_prod = pd.read_csv(LINK_PRODUTOS)
            st.dataframe(df_prod, use_container_width=True)
            
            # Resumo visual
            st.divider()
            col1, col2 = st.columns(2)
            col1.metric("Total de Itens", len(df_prod))
            col2.info("Para editar, altere diretamente a Planilha do Google.")
        except:
            st.error("Erro ao carregar produtos.")
