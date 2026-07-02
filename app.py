import streamlit as st
import pandas as pd

# LINKS QUE VOCÊ GEROU (Já inseridos)
LINK_USUARIOS = "https://docs.google.com/spreadsheets/d/e/2PACX-1vR66hMMGy2uGkRwwHAAW_UL9tEq33eJe4gvY-RiI7BUuQMg2-Pmk7L8z6Jv17rQ5DvVEq0CtTPBPdnP/pub?gid=0&single=true&output=csv"
LINK_PRODUTOS = "https://docs.google.com/spreadsheets/d/e/2PACX-1vR66hMMGy2uGkRwwHAAW_UL9tEq33eJe4gvY-RiI7BUuQMg2-Pmk7L8z6Jv17rQ5DvVEq0CtTPBPdnP/pub?gid=622782364&single=true&output=csv"

# Configuração visual
st.set_page_config(page_title="Tiercal Estoque", page_icon="📦", layout="wide")

# CSS para deixar bonito
st.markdown("""
    <style>
    .stApp { background-color: #f0f2f6; }
    .stButton>button { background-color: #007bff; color: white; border-radius: 8px; width: 100%; }
    </style>
    """, unsafe_allow_html=True)

if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

# Função para ler os dados e limpar os nomes das colunas
def ler_planilha(url):
    df = pd.read_csv(url)
    df.columns = df.columns.str.strip().str.lower() # Remove espaços e deixa minúsculo
    return df

# --- TELA DE LOGIN ---
if not st.session_state['logged_in']:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.write("# 🔐 Login Sistema Tiercal")
        user_input = st.text_input("Usuário").strip().lower()
        pass_input = st.text_input("Senha", type="password").strip()
        
        if st.button("Acessar Sistema"):
            try:
                df_u = ler_planilha(LINK_USUARIOS)
                # Verifica se o usuário e senha batem
                usuario_valido = df_u[
                    (df_u['usuario'].astype(str).str.lower() == user_input) & 
                    (df_u['senha'].astype(str) == pass_input)
                ]
                
                if not usuario_valido.empty:
                    st.session_state['logged_in'] = True
                    st.rerun()
                else:
                    st.error("Usuário ou senha não encontrados na planilha.")
            except Exception as e:
                st.error(f"Erro ao ler banco de dados: {e}")

# --- SISTEMA APÓS LOGIN ---
else:
    st.sidebar.title("📦 Menu Tiercal")
    opcao = st.sidebar.radio("Navegação", ["Visualizar Estoque", "Sair"])

    if opcao == "Sair":
        st.session_state['logged_in'] = False
        st.rerun()

    if opcao == "Visualizar Estoque":
        st.title("📦 Painel de Controle de Estoque")
        
        try:
            df_p = ler_planilha(LINK_PRODUTOS)
            
            # Cartões de Resumo
            c1, c2, c3 = st.columns(3)
            c1.metric("Total de Produtos", len(df_p))
            c2.warning("Edite os valores na Planilha do Google")
            c3.success("Sincronizado em tempo real")

            st.divider()
            # Mostra a tabela de produtos
            st.dataframe(df_p, use_container_width=True, hide_index=True)
            
        except Exception as e:
            st.error(f"Erro ao carregar lista de produtos: {e}")

    st.sidebar.divider()
    st.sidebar.info("Para adicionar ou remover itens, use a sua Planilha do Google.")
