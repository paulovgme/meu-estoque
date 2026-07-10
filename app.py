import streamlit as st
import pandas as pd
from supabase import create_client, Client

# 1. Configurações Iniciais
st.set_page_config(page_title="Sistema de Estoque", page_icon="📦", layout="wide")

# 2. Conexão com Supabase
@st.cache_resource
def get_supabase():
    return create_client(st.secrets["URL_BANCO"], st.secrets["CHAVE_BANCO"])

supabase = get_supabase()

# 3. Gerenciamento de Estado
if 'logado' not in st.session_state:
    st.session_state.logado = False

# --- TELA DE LOGIN ---
if not st.session_state.logado:
    cols = st.columns([1, 2, 1]) # Centraliza o formulário
    with cols[1]:
        st.title("🔐 Acesso ao Sistema")
        with st.form("login"):
            u = st.text_input("Usuário").strip().lower()
            p = st.text_input("Senha", type="password").strip()
            if st.form_submit_button("Entrar", use_container_width=True):
                res = supabase.table("usuarios").select("*").eq("usuario", u).eq("senha", p).execute()
                if res.data:
                    st.session_state.logado = True
                    st.session_state.user = u
                    st.rerun()
                else:
                    st.error("Usuário ou senha incorretos.")

# --- TELA PRINCIPAL (ESTOQUE) ---
else:
    # Sidebar lateral
    st.sidebar.title(f"👋 Olá, {st.session_state.user.capitalize()}")
    if st.sidebar.button("Sair / Logoff"):
        st.session_state.logado = False
        st.rerun()

    st.title("📦 Gerenciamento de Estoque")

    # Criamos abas para organizar o app
    tab1, tab2 = st.tabs(["📋 Visualizar Estoque", "➕ Cadastrar Produto"])

    # --- ABA 1: VISUALIZAR ---
    with tab1:
        st.subheader("Produtos em Estoque")
        
        # Campo de busca
        busca = st.text_input("🔍 Buscar produto pelo nome...")

        try:
            # Busca dados do Supabase
            query = supabase.table("produtos").select("*")
            if busca:
                query = query.ilike("nome", f"%{busca}%")
            
            resultado = query.execute()
            
            if resultado.data:
                df = pd.DataFrame(resultado.data)
                
                # Reorganiza as colunas se necessário (ajuste conforme seu banco)
                # df = df[['id', 'nome', 'quantidade', 'preco']] 
                
                # Exibe a tabela de forma bonita
                st.dataframe(df, use_container_width=True, hide_index=True)
                
                # Botão para deletar (exemplo simples)
                with st.expander("🗑️ Excluir um produto"):
                    id_deletar = st.number_input("Digite o ID do produto para excluir", step=1)
                    if st.button("Confirmar Exclusão"):
                        supabase.table("produtos").delete().eq("id", id_deletar).execute()
                        st.success("Produto excluído!")
                        st.rerun()
            else:
                st.info("Nenhum produto encontrado.")
        except Exception as e:
            st.error(f"Erro ao carregar dados: {e}")

    # --- ABA 2: CADASTRAR ---
    with tab2:
        st.subheader("Novo Cadastro")
        with st.form("cadastro_produto", clear_on_submit=True):
            nome_prod = st.text_input("Nome do Produto")
            qtd_prod = st.number_input("Quantidade", min_value=0, step=1)
            preco_prod = st.number_input("Preço (R$)", min_value=0.0, format="%.2f")
            
            if st.form_submit_button("Salvar no Banco"):
                if nome_prod:
                    novo_item = {
                        "nome": nome_prod,
                        "quantidade": qtd_prod,
                        "preco": preco_prod
                    }
                    try:
                        supabase.table("produtos").insert(novo_item).execute()
                        st.success(f"Sucesso! {nome_prod} adicionado.")
                    except Exception as e:
                        st.error(f"Erro ao salvar: {e}")
                else:
                    st.warning("O nome do produto é obrigatório.")
