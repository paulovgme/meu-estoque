import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime

# --- 1. CONFIGURAÇÕES DA PÁGINA ---
st.set_page_config(page_title="Sistema TI - Estoque Pro", page_icon="📦", layout="wide")

# --- 2. CONEXÃO COM SUPABASE ---
@st.cache_resource
def get_supabase() -> Client:
    url = st.secrets["URL_BANCO"]
    key = st.secrets["CHAVE_BANCO"]
    return create_client(url, key)

supabase = get_supabase()

# --- 3. FUNÇÕES AUXILIARES ---
def buscar_dados(tabela):
    try:
        res = supabase.table(tabela).select("*").execute()
        return pd.DataFrame(res.data)
    except Exception as e:
        st.error(f"Erro ao acessar {tabela}: {e}")
        return pd.DataFrame()

# --- 4. CONTROLE DE ACESSO (LOGIN) ---
if 'logado' not in st.session_state:
    st.session_state.logado = False
    st.session_state.perms = {}
    st.session_state.user = None

if not st.session_state.logado:
    st.title("🔐 Acesso ao Sistema")
    with st.form("login_form"):
        u = st.text_input("Usuário").strip().lower()
        p = st.text_input("Senha", type="password").strip()
        if st.form_submit_button("Entrar", use_container_width=True):
            try:
                res = supabase.table("usuarios").select("*").eq("usuario", u).eq("senha", p).execute()
                if res.data:
                    user_data = res.data[0]
                    st.session_state.logado = True
                    st.session_state.user = u
                    # Armazena todas as permissões no estado da sessão
                    st.session_state.perms = {
                        "nivel": user_data.get('nivel', 'user'),
                        "consultar": user_data.get('can_consultar', True),
                        "movimentar": user_data.get('can_movimentar', False),
                        "cadastrar": user_data.get('can_cadastrar', False),
                        "admin": user_data.get('can_admin', False),
                        "historico": user_data.get('can_historico', False),
                        "usuarios": user_data.get('can_usuarios', False)
                    }
                    st.rerun()
                else:
                    st.error("Usuário ou senha inválidos.")
            except Exception as e:
                st.error(f"Erro de conexão: {e}")
    st.stop()

# --- 5. MENU LATERAL DINÂMICO ---
st.sidebar.title(f"👋 Olá, {st.session_state.user.capitalize()}")
st.sidebar.write(f"Nível: **{st.session_state.perms['nivel'].upper()}**")

opcoes_menu = []
if st.session_state.perms['consultar']: opcoes_menu.append("📊 Consultar Estoque")
if st.session_state.perms['movimentar']: opcoes_menu.append("🔄 Entrada / Saída")
if st.session_state.perms['cadastrar']:  opcoes_menu.append("🆕 Cadastrar Produto")
if st.session_state.perms['admin']:      opcoes_menu.append("🔧 Administração (Admin)")
if st.session_state.perms['historico']:  opcoes_menu.append("📜 Histórico Geral")
if st.session_state.perms['usuarios']:   opcoes_menu.append("👥 Gerenciar Usuários")

menu = st.sidebar.radio("Navegação", opcoes_menu)

if st.sidebar.button("Sair / Logoff"):
    st.session_state.logado = False
    st.rerun()

# --- 6. TELAS DO SISTEMA ---

# --- TELA: CONSULTAR ESTOQUE ---
if menu == "📊 Consultar Estoque":
    st.title("📊 Consultar Estoque")
    df = buscar_dados("produtos")
    if not df.empty:
        termo = st.text_input("🔍 Pesquisar por nome, marca ou categoria").lower()
        df_filtrado = df[df['nome'].str.lower().str.contains(termo) | df['marca'].str.lower().str.contains(termo)]
        st.dataframe(df_filtrado, use_container_width=True, hide_index=True)

# --- TELA: ENTRADA / SAÍDA ---
elif menu == "🔄 Entrada / Saída":
    st.title("🔄 Movimentação")
    df = buscar_dados("produtos")
    if not df.empty:
        escolha = st.selectbox("Selecione o produto", df['nome'].tolist())
        item_sel = df[df['nome'] == escolha].iloc[0]
        
        qtd_mov = st.number_input("Quantidade", min_value=1)
        tipo_op = st.radio("Operação", ["Entrada (Compra)", "Saída (Baixa)"])
        
        if st.button("Confirmar"):
            nova_qtd = item_sel['quantidade'] + qtd_mov if "Entrada" in tipo_op else item_sel['quantidade'] - qtd_mov
            if nova_qtd < 0:
                st.error("Saldo insuficiente!")
            else:
                supabase.table("produtos").update({"quantidade": int(nova_qtd)}).eq("id", item_sel['id']).execute()
                supabase.table("historico").insert({"operador": st.session_state.user, "acao": tipo_op, "produto": item_sel['nome'], "quantidade": int(qtd_mov), "data": datetime.now().isoformat()}).execute()
                st.success("Feito!")
                st.rerun()

# --- TELA: CADASTRAR PRODUTO (COM VALIDAÇÃO DE DUPLICIDADE) ---
elif menu == "🆕 Cadastrar Produto":
    st.title("🆕 Novo Produto")
    with st.form("novo_p"):
        n = st.text_input("Nome do Produto").strip()
        m = st.text_input("Marca")
        cat = st.text_input("Categoria")
        q = st.number_input("Qtd Inicial", min_value=0)
        a = st.number_input("Alerta Mínimo", min_value=1)
        
        if st.form_submit_button("Cadastrar"):
            if n and m:
                # VERIFICAÇÃO DE DUPLICIDADE
                check = supabase.table("produtos").select("id").eq("nome", n).execute()
                if check.data:
                    st.error(f"❌ Erro: Já existe um produto cadastrado com o nome '{n}'.")
                else:
                    supabase.table("produtos").insert({"nome":n,"marca":m,"categoria":cat,"quantidade":int(q),"alerta":int(a)}).execute()
                    st.success("Produto cadastrado com sucesso!")
            else:
                st.error("Preencha os campos obrigatórios.")

# --- TELA: GERENCIAR USUÁRIOS (AVANÇADO) ---
elif menu == "👥 Gerenciar Usuários":
    st.title("👥 Gestão de Acessos")
    aba_list, aba_add, aba_edit = st.tabs(["Lista de Usuários", "➕ Novo Usuário", "✏️ Editar/Permissões"])
    
    df_u = buscar_dados("usuarios")

    with aba_list:
        st.dataframe(df_u.drop(columns=['senha']), use_container_width=True)

    with aba_add:
        with st.form("add_user"):
            new_u = st.text_input("Login").strip().lower()
            new_p = st.text_input("Senha", type="password")
            new_n = st.selectbox("Nível", ["user", "admin", "gerente"])
            st.write("--- Permissões de Tela ---")
            c1, c2, c3 = st.columns(3)
            p_con = c1.checkbox("Consultar", True)
            p_mov = c1.checkbox("Movimentar")
            p_cad = c2.checkbox("Cadastrar")
            p_adm = c2.checkbox("Administrar (Editar/Excluir)")
            p_his = c3.checkbox("Ver Histórico")
            p_usu = c3.checkbox("Gerenciar Usuários")
            
            if st.form_submit_button("Criar Usuário"):
                if new_u and new_p:
                    supabase.table("usuarios").insert({
                        "usuario": new_u, "senha": new_p, "nivel": new_n,
                        "can_consultar": p_con, "can_movimentar": p_mov,
                        "can_cadastrar": p_cad, "can_admin": p_adm,
                        "can_historico": p_his, "can_usuarios": p_usu
                    }).execute()
                    st.success("Usuário criado!")
                    st.rerun()

    with aba_edit:
        user_sel = st.selectbox("Selecione o usuário para alterar", df_u['usuario'].tolist())
        u_data = df_u[df_u['usuario'] == user_sel].iloc[0]
        
        with st.form("edit_user"):
            edit_p = st.text_input("Nova Senha (deixe em branco para manter)", type="password")
            edit_n = st.selectbox("Nível", ["user", "admin", "gerente"], index=["user", "admin", "gerente"].index(u_data['nivel']))
            
            st.write("--- Ajustar Permissões ---")
            col1, col2, col3 = st.columns(3)
            ec_con = col1.checkbox("Consultar", value=bool(u_data['can_consultar']))
            ec_mov = col1.checkbox("Movimentar", value=bool(u_data['can_movimentar']))
            ec_cad = col2.checkbox("Cadastrar", value=bool(u_data['can_cadastrar']))
            ec_adm = col2.checkbox("Administrar", value=bool(u_data['can_admin']))
            ec_his = col3.checkbox("Ver Histórico", value=bool(u_data['can_historico']))
            ec_usu = col3.checkbox("Gerenciar Usuários", value=bool(u_data['can_usuarios']))
            
            if st.form_submit_button("Salvar Alterações"):
                update_data = {
                    "nivel": edit_n,
                    "can_consultar": ec_con, "can_movimentar": ec_mov,
                    "can_cadastrar": ec_cad, "can_admin": ec_adm,
                    "can_historico": ec_his, "can_usuarios": ec_usu
                }
                if edit_p: update_data["senha"] = edit_p
                
                supabase.table("usuarios").update(update_data).eq("usuario", user_sel).execute()
                st.success("Usuário atualizado!")
                st.rerun()
