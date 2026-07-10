import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime

# 1. CONFIGURAÇÕES INICIAIS
st.set_page_config(page_title="Sistema Ti - Estoque", page_icon="📦", layout="wide")

# Força o HTML a não ser traduzido (evita o erro removeChild)
st.markdown('<html lang="pt-br"></html>', unsafe_allow_html=True)

# 2. CONEXÃO COM SUPABASE
@st.cache_resource
def get_supabase() -> Client:
    url = st.secrets["URL_BANCO"]
    key = st.secrets["CHAVE_BANCO"]
    return create_client(url, key)

supabase = get_supabase()

# 3. GERENCIAMENTO DE ESTADO
if 'logado' not in st.session_state:
    st.session_state.logado = False
    st.session_state.nivel = None
    st.session_state.user = None

# --- TELA DE LOGIN ---
if not st.session_state.logado:
    st.title("🔐 Acesso ao Sistema")
    with st.form("login_form"):
        u = st.text_input("Usuário").strip().lower()
        p = st.text_input("Senha", type="password").strip()
        if st.form_submit_button("Entrar", use_container_width=True):
            try:
                # Tabela: usuarios
                res = supabase.table("usuarios").select("*").eq("usuario", u).eq("senha", p).execute()
                if res.data:
                    st.session_state.logado = True
                    st.session_state.user = u
                    st.session_state.nivel = res.data[0]['nivel']
                    st.rerun()
                else:
                    st.error("Usuário ou senha inválidos.")
            except Exception as e:
                st.error(f"Erro de conexão: {e}")
    st.stop()

# --- MENU LATERAL ---
st.sidebar.title(f"👋 Olá, {st.session_state.user.capitalize()}")
menu = st.sidebar.radio("Navegação", [
    "📊 Consultar Estoque", 
    "🔄 Entrada / Saída", 
    "🆕 Cadastrar Produto",
    "🔧 Correção (Admin)",
    "📜 Histórico",
    "👥 Gerenciar Usuários"
])

if st.sidebar.button("Sair"):
    st.session_state.logado = False
    st.rerun()

# --- 1. CONSULTAR ESTOQUE ---
if menu == "📊 Consultar Estoque":
    st.title("📊 Consultar Estoque")
    try:
        # Tabela: produtos
        dados = supabase.table("produtos").select("*").execute()
        df = pd.DataFrame(dados.data)
        
        if not df.empty:
            # Alertas baseados na coluna 'alerta'
            alertas = df[df['quantidade'] <= df['alerta']]
            if not alertas.empty:
                for _, item in alertas.iterrows():
                    st.warning(f"🚨 **ESTOQUE BAIXO:** {item['nome']} (Qtd: {item['quantidade']} | Mínimo: {item['alerta']})")

            st.divider()
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("O estoque está vazio.")
    except Exception as e:
        st.error(f"Erro ao carregar dados: {e}")

# --- 2. ENTRADA / SAÍDA ---
elif menu == "🔄 Entrada / Saída":
    st.title("🔄 Movimentação de Estoque")
    try:
        res = supabase.table("produtos").select("id, nome, quantidade").execute()
        if res.data:
            prods = {f"{p['nome']} (Atual: {p['quantidade']})": p for p in res.data}
            escolha = st.selectbox("Escolha o produto", list(prods.keys()))
            item_sel = prods[escolha]
            
            col1, col2 = st.columns(2)
            with col1:
                qtd_mov = st.number_input("Quantidade", min_value=1, step=1)
            with col2:
                operacao = st.radio("Tipo", ["Entrada", "Saída"])

            if st.button("Confirmar"):
                nova_qtd = item_sel['quantidade'] + qtd_mov if operacao == "Entrada" else item_sel['quantidade'] - qtd_mov
                
                if nova_qtd < 0:
                    st.error("Erro: Saldo insuficiente!")
                else:
                    # Atualiza estoque na tabela 'produtos'
                    supabase.table("produtos").update({"quantidade": int(nova_qtd)}).eq("id", item_sel['id']).execute()
                    
                    # Salva no 'historico' (conforme as colunas da sua foto)
                    supabase.table("historico").insert({
                        "operador": st.session_state.user,
                        "acao": operacao,
                        "produto": item_sel['nome'],
                        "quantidade": int(qtd_mov)
                    }).execute()
                    
                    st.success("Estoque atualizado!")
                    st.rerun()
    except Exception as e:
        st.error(f"Erro: {e}")

# --- 3. CADASTRAR PRODUTO ---
elif menu == "🆕 Cadastrar Produto":
    st.title("🆕 Novo Cadastro")
    with st.form("form_add"):
        n = st.text_input("Nome")
        c = st.text_input("Categoria")
        q = st.number_input("Qtd Inicial", min_value=0, step=1)
        p = st.number_input("Preço", min_value=0.0)
        a = st.number_input("Alerta Mínimo", min_value=1, step=1)
        
        if st.form_submit_button("Cadastrar"):
            if n:
                try:
                    # Tabela: produtos (substituindo 'name')
                    supabase.table("produtos").insert({
                        "nome": n, 
                        "categoria": c, 
                        "quantidade": int(q), 
                        "preco": float(p), 
                        "alerta": int(a)
                    }).execute()
                    st.success("Cadastrado com sucesso!")
                except Exception as e:
                    st.error(f"Erro no banco: {e}")
            else:
                st.warning("O nome é obrigatório.")

# --- 5. HISTÓRICO ---
elif menu == "📜 Histórico":
    st.title("📜 Histórico Geral")
    try:
        res = supabase.table("historico").select("*").order("data", desc=True).execute()
        if res.data:
            st.dataframe(pd.DataFrame(res.data), use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Erro ao carregar histórico: {e}")

# --- 6. GERENCIAR USUÁRIOS (ADMIN) ---
elif menu == "👥 Gerenciar Usuários":
    st.title("👥 Gestão de Usuários")
    if st.session_state.nivel != "admin":
        st.error("Acesso restrito.")
    else:
        with st.expander("➕ Adicionar Usuário"):
            nu = st.text_input("Novo Usuário").lower()
            ns = st.text_input("Senha")
            nv = st.selectbox("Nível", ["comum", "admin"])
            if st.button("Salvar"):
                supabase.table("usuarios").insert({"usuario": nu, "senha": ns, "nivel": nv}).execute()
                st.success("Usuário criado!")
