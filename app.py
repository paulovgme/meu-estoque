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
                    st.session_state.perms = {
                        "nivel": user_data.get('nivel', 'comum'),
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
st.sidebar.write(f"Nível: **{st.session_state.perms.get('nivel', 'comum').upper()}**")

opcoes_menu = []
if st.session_state.perms.get('consultar'): opcoes_menu.append("📊 Consultar Estoque")
if st.session_state.perms.get('movimentar'): opcoes_menu.append("🔄 Entrada / Saída")
if st.session_state.perms.get('cadastrar'):  opcoes_menu.append("🆕 Cadastrar Produto")
if st.session_state.perms.get('admin'):      opcoes_menu.append("🔧 Administração (Admin)")
if st.session_state.perms.get('historico'):  opcoes_menu.append("📜 Histórico Geral")
if st.session_state.perms.get('usuarios'):   opcoes_menu.append("👥 Gerenciar Usuários")

menu = st.sidebar.radio("Navegação", opcoes_menu)

if st.sidebar.button("Sair / Logoff"):
    st.session_state.logado = False
    st.rerun()

# --- 6. TELAS DO SISTEMA ---

if menu == "📊 Consultar Estoque":
    st.title("📊 Consultar Estoque")
    df = buscar_dados("produtos")
    if not df.empty:
        termo = st.text_input("🔍 Pesquisar por nome ou marca").lower()
        df_filtrado = df[df['nome'].str.lower().str.contains(termo) | df['marca'].str.lower().str.contains(termo)]
        st.dataframe(df_filtrado, use_container_width=True, hide_index=True)

elif menu == "🔄 Entrada / Saída":
    st.title("🔄 Movimentação")
    df = buscar_dados("produtos")
    if not df.empty:
        opcoes = {f"{p['nome']} (Qtd: {p['quantidade']})": p for _, p in df.iterrows()}
        escolha = st.selectbox("Selecione o produto", list(opcoes.keys()))
        item_sel = opcoes[escolha]
        
        qtd_mov = st.number_input("Quantidade", min_value=1)
        tipo_op = st.radio("Operação", ["Entrada (Compra)", "Saída (Baixa)"])
        
        if st.button("Confirmar"):
            nova_qtd = item_sel['quantidade'] + qtd_mov if "Entrada" in tipo_op else item_sel['quantidade'] - qtd_mov
            if nova_qtd < 0:
                st.error("Saldo insuficiente!")
            else:
                supabase.table("produtos").update({"quantidade": int(nova_qtd)}).eq("id", item_sel['id']).execute()
                supabase.table("historico").insert({
                    "operador": st.session_state.user, "acao": tipo_op, 
                    "produto": item_sel['nome'], "quantidade": int(qtd_mov), 
                    "data": datetime.now().isoformat()
                }).execute()
                st.success("Feito!")
                st.rerun()

elif menu == "🆕 Cadastrar Produto":
    st.title("🆕 Novo Produto")
    with st.form("novo_p"):
        n = st.text_input("Nome do Produto").strip()
        m = st.text_input("Marca")
        cat = st.text_input("Categoria")
        q = st.number_input("Qtd Inicial", min_value=0)
        a = st.number_input("Alerta Mínimo", min_value=1)
        if st.form_submit_button("Cadastrar"):
            if n:
                check = supabase.table("produtos").select("id").eq("nome", n).execute()
                if check.data:
                    st.error(f"O produto '{n}' já está cadastrado!")
                else:
                    supabase.table("produtos").insert({"nome":n,"marca":m,"categoria":cat,"quantidade":int(q),"alerta":int(a)}).execute()
                    st.success("Cadastrado com sucesso!")
            else: st.error("Nome é obrigatório")

elif menu == "🔧 Administração (Admin)":
    st.title("🔧 Administração")
    df = buscar_dados("produtos")
    if not df.empty:
        sel = st.selectbox("Selecione o produto", df['nome'].tolist())
        p = df[df['nome'] == sel].iloc[0]
        with st.form("edit_prod"):
            en = st.text_input("Nome", value=p['nome'])
            em = st.text_input("Marca", value=p['marca'])
            if st.form_submit_button("Atualizar Dados"):
                supabase.table("produtos").update({"nome":en, "marca":em}).eq("id", p['id']).execute()
                st.success("Dados atualizados!")
                st.rerun()
        if st.button("🚨 EXCLUIR PRODUTO", type="primary"):
            supabase.table("produtos").delete().eq("id", p['id']).execute()
            st.rerun()

elif menu == "📜 Histórico Geral":
    st.title("📜 Histórico")
    df_h = buscar_dados("historico")
    if not df_h.empty:
        st.dataframe(df_h.sort_values("data", ascending=False), use_container_width=True)

elif menu == "👥 Gerenciar Usuários":
    st.title("👥 Gestão de Usuários")
    aba_l, aba_a, aba_e = st.tabs(["📋 Lista de Usuários", "➕ Novo Usuário", "✏️ Editar Permissões"])
    df_u = buscar_dados("usuarios")

    # 1. ABA LISTA (Exibe apenas usuario e nivel)
    with aba_l:
        if not df_u.empty:
            st.dataframe(df_u[['usuario', 'nivel']], use_container_width=True, hide_index=True)

    # 2. ABA NOVO (Com 2 níveis: comum e administrador)
    with aba_a:
        with st.form("form_novo_usuario"):
            nu = st.text_input("Login (Usuário)").lower().strip()
            ns = st.text_input("Senha", type="password")
            # Nível alterado para as duas opções solicitadas
            nv = st.selectbox("Nível", ["comum", "administrador"])
            
            st.write("--- Atribuir Permissões de Tela ---")
            col1, col2 = st.columns(2)
            c_con = col1.checkbox("Pode Consultar Estoque", value=True)
            c_mov = col1.checkbox("Pode Realizar Movimentações")
            c_cad = col1.checkbox("Pode Cadastrar Produtos")
            c_adm = col2.checkbox("Acesso à Administração (Editar/Excluir)")
            c_his = col2.checkbox("Ver Histórico Geral")
            c_usu = col2.checkbox("Gerenciar Outros Usuários")
            
            if st.form_submit_button("Criar Usuário"):
                if nu and ns:
                    try:
                        supabase.table("usuarios").insert({
                            "usuario": nu, "senha": ns, "nivel": nv,
                            "can_consultar": c_con, "can_movimentar": c_mov,
                            "can_cadastrar": c_cad, "can_admin": c_adm,
                            "can_historico": c_his, "can_usuarios": c_usu
                        }).execute()
                        st.success(f"Usuário {nu} criado!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro: {e}")
                else:
                    st.warning("Preencha Login e Senha.")

    # 3. ABA EDITAR
    with aba_e:
        if not df_u.empty:
            user_edit = st.selectbox("Selecione o usuário para alterar", df_u['usuario'].tolist())
            u_sel = df_u[df_u['usuario'] == user_edit].iloc[0]
            
            with st.form("form_edit_usuario"):
                nova_s = st.text_input("Nova Senha (deixe vazio para não alterar)", type="password")
                
                niveis = ["comum", "administrador"]
                # Lógica para converter nomes antigos para os novos na visualização
                nivel_banco = str(u_sel.get('nivel', 'comum')).lower()
                if nivel_banco in ['admin', 'administrador']:
                    nivel_atual = 'administrador'
                else:
                    nivel_atual = 'comum'
                
                idx = niveis.index(nivel_atual)
                novo_n = st.selectbox("Nível de Acesso", niveis, index=idx)
                
                st.write("--- Ajustar Permissões ---")
                col1, col2 = st.columns(2)
                p1 = col1.checkbox("Consultar", value=bool(u_sel.get('can_consultar', True)))
                p2 = col1.checkbox("Movimentar", value=bool(u_sel.get('can_movimentar', False)))
                p3 = col1.checkbox("Cadastrar", value=bool(u_sel.get('can_cadastrar', False)))
                p4 = col2.checkbox("Administrar", value=bool(u_sel.get('can_admin', False)))
                p5 = col2.checkbox("Histórico", value=bool(u_sel.get('can_historico', False)))
                p6 = col2.checkbox("Gerir Usuários", value=bool(u_sel.get('can_usuarios', False)))
                
                if st.form_submit_button("Salvar Alterações"):
                    upd = {
                        "nivel": novo_n, 
                        "can_consultar": p1, "can_movimentar": p2, "can_cadastrar": p3,
                        "can_admin": p4, "can_historico": p5, "can_usuarios": p6
                    }
                    if nova_s: upd["senha"] = nova_s
                    
                    supabase.table("usuarios").update(upd).eq("usuario", user_edit).execute()
                    st.success("Dados atualizados!")
                    st.rerun()
