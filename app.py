import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime

# 1. CONFIGURAÇÕES INICIAIS
st.set_page_config(page_title="Sistema Ti - Estoque", page_icon="📦", layout="wide")

# Trava para evitar que o Google Tradutor quebre o React do Streamlit
st.markdown('<html lang="pt-br"></html>', unsafe_allow_html=True)

# 2. CONEXÃO COM SUPABASE
@st.cache_resource
def get_supabase() -> Client:
    url = st.secrets["URL_BANCO"]
    key = st.secrets["CHAVE_BANCO"]
    return create_client(url, key)

supabase = get_supabase()

# 3. GERENCIAMENTO DE ESTADO (LOGIN)
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
                res = supabase.table("usuarios").select("*").eq("usuario", u).eq("senha", p).execute()
                if res.data:
                    st.session_state.logado = True
                    st.session_state.user = u
                    st.session_state.nivel = res.data[0]['nivel'] # 'admin' ou 'comum'
                    st.rerun()
                else:
                    st.error("Usuário ou senha inválidos.")
            except Exception as e:
                st.error(f"Erro de conexão: {e}")
    st.stop()

# --- MENU LATERAL ---
st.sidebar.title(f"👋 Olá, {st.session_state.user.capitalize()}")
st.sidebar.write(f"**Nível:** {st.session_state.nivel.upper()}")

menu = st.sidebar.radio("Menu", [
    "📊 Consultar Estoque", 
    "🔄 Entrada / Saída", 
    "🆕 Cadastrar Produto",
    "🔧 Correção (Admin)",
    "📜 Histórico",
    "👥 Gerenciar Usuários"
])

if st.sidebar.button("Sair / Logoff"):
    st.session_state.logado = False
    st.rerun()

# --- 1. CONSULTAR ESTOQUE ---
if menu == "📊 Consultar Estoque":
    st.title("📊 Consultar Estoque")
    try:
        dados = supabase.table("name").select("*").execute()
        df = pd.DataFrame(dados.data)
        
        if not df.empty:
            # Alertas de Estoque Mínimo (baseado na coluna 'alerta')
            alertas = df[df['quantidade'] <= df['alerta']]
            if not alertas.empty:
                for _, item in alertas.iterrows():
                    st.warning(f"🚨 **ESTOQUE BAIXO:** {item['nome']} (Qtd: {item['quantidade']} | Mínimo: {item['alerta']})")

            st.divider()
            busca = st.text_input("🔍 Buscar por nome ou categoria")
            if busca:
                df = df[df['nome'].str.contains(busca, case=False) | df['categoria'].str.contains(busca, case=False)]
            
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum produto cadastrado.")
    except Exception as e:
        st.error(f"Erro ao carregar dados: {e}")

# --- 2. ENTRADA / SAÍDA ---
elif menu == "🔄 Entrada / Saída":
    st.title("🔄 Movimentação de Estoque")
    try:
        res = supabase.table("name").select("id, nome, quantidade").execute()
        if res.data:
            prods = {f"{p['nome']} (Atual: {p['quantidade']})": p for p in res.data}
            escolha = st.selectbox("Escolha o produto", list(prods.keys()))
            item_sel = prods[escolha]
            
            col1, col2 = st.columns(2)
            with col1:
                qtd_mov = st.number_input("Quantidade", min_value=1, step=1)
            with col2:
                operacao = st.radio("Tipo", ["Entrada", "Saída"])

            if st.button("Confirmar Movimentação"):
                nova_qtd = item_sel['quantidade'] + qtd_mov if operacao == "Entrada" else item_sel['quantidade'] - qtd_mov
                
                if nova_qtd < 0:
                    st.error("Erro: Saldo insuficiente!")
                else:
                    # Atualiza o estoque
                    supabase.table("name").update({"quantidade": int(nova_qtd)}).eq("id", item_sel['id']).execute()
                    
                    # Registra no Histórico
                    supabase.table("historico").insert({
                        "data": datetime.now().isoformat(),
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
    with st.form("add_form"):
        n = st.text_input("Nome")
        c = st.text_input("Categoria")
        q = st.number_input("Qtd Inicial", min_value=0, step=1)
        p = st.number_input("Preço", min_value=0.0)
        a = st.number_input("Alerta Mínimo", min_value=1, step=1)
        
        if st.form_submit_button("Cadastrar"):
            if n:
                try:
                    supabase.table("name").insert({
                        "nome": n, "categoria": c, "quantidade": int(q), "preco": float(p), "alerta": int(a)
                    }).execute()
                    st.success("Cadastrado!")
                except Exception as e:
                    st.error(f"Erro no banco: {e}")
            else:
                st.warning("O nome é obrigatório.")

# --- 4. CORREÇÃO (ADMIN) ---
elif menu == "🔧 Correção (Admin)":
    st.title("🔧 Correção de Dados")
    if st.session_state.nivel != "admin":
        st.error("Acesso restrito a Administradores.")
    else:
        res = supabase.table("name").select("*").execute()
        if res.data:
            df_edit = pd.DataFrame(res.data)
            escolha = st.selectbox("Produto para editar", df_edit['nome'].tolist())
            p_sel = df_edit[df_edit['nome'] == escolha].iloc[0]

            with st.form("edit_f"):
                novo_n = st.text_input("Nome", value=p_sel['nome'])
                novo_c = st.text_input("Categoria", value=p_sel['categoria'])
                novo_p = st.number_input("Preço", value=float(p_sel['preco']))
                novo_a = st.number_input("Alerta", value=int(p_sel['alerta']))
                if st.form_submit_button("Salvar Alterações"):
                    supabase.table("name").update({
                        "nome": novo_n, "categoria": novo_c, "preco": novo_p, "alerta": novo_a
                    }).eq("id", p_sel['id']).execute()
                    st.success("Atualizado!")
                    st.rerun()

# --- 5. HISTÓRICO ---
elif menu == "📜 Histórico":
    st.title("📜 Histórico Geral")
    res = supabase.table("historico").select("*").order("data", desc=True).execute()
    if res.data:
        st.dataframe(pd.DataFrame(res.data), use_container_width=True, hide_index=True)

# --- 6. GERENCIAR USUÁRIOS (ADMIN) ---
elif menu == "👥 Gerenciar Usuários":
    st.title("👥 Gestão de Usuários")
    if st.session_state.nivel != "admin":
        st.error("Acesso restrito.")
    else:
        with st.expander("➕ Criar Novo Usuário"):
            nu = st.text_input("Usuário").strip().lower()
            ns = st.text_input("Senha")
            nv = st.selectbox("Nível", ["comum", "admin"])
            if st.button("Salvar Usuário"):
                supabase.table("usuarios").insert({"usuario": nu, "senha": ns, "nivel": nv}).execute()
                st.success("Criado!")
        
        st.subheader("Lista de Acessos")
        u_list = supabase.table("usuarios").select("id, usuario, nivel").execute()
        st.table(pd.DataFrame(u_list.data))
