import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection

# Configuração da página
st.set_page_config(page_title="Sistema Tiercal", page_icon="🔐", layout="wide")

# --- CSS PARA MELHORAR O VISUAL ---
st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stButton>button { width: 100%; border-radius: 5px; height: 3em; background-color: #007bff; color: white; }
    .stDataFrame { border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

# Conexão com Google Sheets (Configuraremos as chaves depois)
conn = st.connection("gsheets", type=GSheetsConnection)

# --- SISTEMA DE LOGIN ---
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
    st.session_state['user_name'] = ""
    st.session_state['user_level'] = ""

def login():
    st.title("🔐 Login - Sistema Tiercal")
    with st.form("login_form"):
        user = st.text_input("Usuário")
        pw = st.text_input("Senha", type="password")
        submit = st.form_submit_button("Entrar")
        
        if submit:
            # Busca usuários na planilha
            usuarios_df = conn.read(worksheet="usuarios")
            valid_user = usuarios_df[(usuarios_df['usuario'] == user) & (usuarios_df['senha'] == str(pw))]
            
            if not valid_user.empty:
                st.session_state['logged_in'] = True
                st.session_state['user_name'] = user
                st.session_state['user_level'] = valid_user.iloc[0]['nivel']
                st.rerun()
            else:
                st.error("Usuário ou senha incorretos")

if not st.session_state['logged_in']:
    login()
else:
    # --- SISTEMA APÓS LOGIN ---
    st.sidebar.title(f"Bem-vindo, {st.session_state['user_name']}")
    menu = st.sidebar.radio("Navegação", ["📦 Estoque", "➕ Adicionar Produto", "👥 Gerenciar Usuários", "🚪 Sair"])

    if menu == "🚪 Sair":
        st.session_state['logged_in'] = False
        st.rerun()

    # --- ABA ESTOQUE ---
    if menu == "📦 Estoque":
        st.header("📦 Dashboard de Estoque")
        dados = conn.read(worksheet="produtos")
        
        # Métricas visuais (Cartões)
        col1, col2, col3 = st.columns(3)
        col1.metric("Total de Itens", len(dados))
        col2.metric("Estoque Baixo", len(dados[dados['quantidade'] < 5]))
        col3.metric("Valor Total", f"R$ { (dados['quantidade'] * dados['preco']).sum():.2f}")

        st.divider()
        st.dataframe(dados, use_container_width=True, hide_index=True)

    # --- ABA ADICIONAR PRODUTO ---
    elif menu == "➕ Adicionar Produto":
        st.header("➕ Cadastrar Novo Item")
        with st.form("add_form"):
            nome = st.text_input("Nome do Produto")
            qtd = st.number_input("Quantidade", min_value=0)
            preco = st.number_input("Preço Unitário", min_value=0.0)
            if st.form_submit_button("Salvar no Google Sheets"):
                # Lógica para salvar na planilha (Próximo passo)
                st.success("Produto enviado para a planilha!")

    # --- ABA GERENCIAR USUÁRIOS (SÓ PARA ADMIN) ---
    elif menu == "👥 Gerenciar Usuários":
        if st.session_state['user_level'] == 'admin':
            st.header("👥 Gestão de Acessos")
            usuarios_df = conn.read(worksheet="usuarios")
            st.table(usuarios_df[['usuario', 'nivel']])
            
            with st.expander("Criar Novo Usuário"):
                novo_u = st.text_input("Novo Usuário")
                nova_s = st.text_input("Senha")
                novo_n = st.selectbox("Nível", ["operador", "admin"])
                if st.button("Cadastrar Usuário"):
                    st.info("Funcionalidade de escrita sendo liberada...")
        else:
            st.error("Você não tem permissão de Administrador.")
