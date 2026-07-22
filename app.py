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
        # Usamos aspas para tabelas com acento no Supabase
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
                # Busca na tabela 'usuários'
                res = supabase.table("usuários").select("*").eq("usuario", u).eq("senha", p).execute()
                if res.data:
                    user_data = res.data[0]
                    st.session_state.logado = True
                    st.session_state.user = u
                    # Mapeia as permissões do banco para a sessão
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

# Constrói o menu baseado nas permissões do usuário
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

# --- TELA: CONSULTAR ESTOQUE ---
if menu == "📊 Consultar Estoque":
    st.title("📊 Consultar Estoque")
    df = buscar_dados("produtos")
    if not df.empty:
        termo = st.text_input("🔍 Pesquisar por nome, marca ou categoria").lower()
        df_filtrado = df[
            df['nome'].str.lower().str.contains(termo) | 
            df['marca'].str.lower().str.contains(termo) |
            df['categoria'].str.lower().str.contains(termo)
        ]
        st.dataframe(df_filtrado, use_container_width=True, hide_index=True)
    else:
        st.info("Nenhum produto cadastrado.")

# --- TELA: ENTRADA / SAÍDA ---
elif menu == "🔄 Entrada / Saída":
    st.title("🔄 Movimentação de Itens")
    df = buscar_dados("produtos")
    if not df.empty:
        opcoes = {f"{p['nome']} - {p['marca']} | Qtd Atual: {p['quantidade']}": p for _, p in df.iterrows()}
        escolha = st.selectbox("Selecione o produto", list(opcoes.keys()))
        item_sel = opcoes[escolha]
        
        col1, col2 = st.columns(2)
        qtd_mov = col1.number_input("Quantidade", min_value=1, step=1)
        tipo_op = col2.radio("Operação", ["Entrada (Compra)", "Saída (Baixa)"])
        
        if st.button("Confirmar Movimentação", use_container_width=True, type="primary"):
            nova_qtd = item_sel['quantidade'] + qtd_mov if "Entrada" in tipo_op else item_sel['quantidade'] - qtd_mov
            
            if nova_qtd < 0:
                st.error("❌ Saldo insuficiente!")
            else:
                try:
                    supabase.table("produtos").update({"quantidade": int(nova_qtd)}).eq("id", item_sel['id']).execute()
                    # Salva no histórico (tabela com acento)
                    supabase.table("histórico").insert({
                        "operador": st.session_state.user, 
                        "acao": tipo_op, 
                        "produto": item_sel['nome'], 
                        "quantidade": int(qtd_mov), 
                        "data": datetime.now().isoformat()
                    }).execute()
                    st.success(f"✅ Movimentação realizada!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro: {e}")

# --- TELA: CADASTRAR PRODUTO (COM TRAVA DE DUPLICIDADE) ---
elif menu == "🆕 Cadastrar Produto":
    st.title("🆕 Novo Produto")
    with st.form("novo_p"):
        n = st.text_input("Nome do Produto").strip()
        m = st.text_input("Marca")
        cat = st.text_input("Categoria")
        q = st.number_input("Qtd Inicial", min_value=0)
        a = st.number_input("Alerta Estoque Baixo", min_value=1)
        
        if st.form_submit_button("Cadastrar Produto"):
            if n and m:
                # Verifica se já existe um produto com o mesmo nome
                check = supabase.table("produtos").select("id").eq("nome", n).execute()
                if check.data:
                    st.error(f"❌ O produto '{n}' já existe no sistema!")
                else:
                    supabase.table("produtos").insert({
                        "nome": n, "marca": m, "categoria": cat, 
                        "quantidade": int(q), "alerta": int(a)
                    }).execute()
                    st.success("✅ Produto cadastrado com sucesso!")
            else:
                st.error("Nome e Marca são obrigatórios.")

# --- TELA: ADMINISTRAÇÃO (EDITAR/EXCLUIR PRODUTOS) ---
elif menu == "🔧 Administração (Admin)":
    st.title("🔧 Painel Administrativo")
    df = buscar_dados("produtos")
    if not df.empty:
        aba_e, aba_d = st.tabs(["✏️ Editar Produto", "🗑️ Excluir Produto"])
        with aba_e:
            sel = st.selectbox("Selecione para editar", df['nome'].tolist())
            p = df[df['nome'] == sel].iloc[0]
            with st.form("edit_p"):
                en = st.text_input("Nome", value=p['nome'])
                em = st.text_input("Marca", value=p['marca'])
                ec = st.text_input("Categoria", value=p['categoria'])
                ea = st.number_input("Alerta", value=int(p['alerta']))
                if st.form_submit_button("Salvar Alterações"):
                    supabase.table("produtos").update({"nome":en, "marca":em, "categoria":ec, "alerta":int(ea)}).eq("id", p['id']).execute()
                    st.success("Atualizado!")
                    st.rerun()
        with aba_d:
            sel_del = st.selectbox("Selecione para EXCLUIR", df['nome'].tolist(), key="del")
            if st.button(f"CONFIRMAR EXCLUSÃO DE {sel_del}", type="primary"):
                id_del = df[df['nome'] == sel_del]['id'].values[0]
                supabase.table("produtos").delete().eq("id", id_del).execute()
                st.warning("Produto removido.")
                st.rerun()

# --- TELA: HISTÓRICO ---
elif menu == "📜 Histórico Geral":
    st.title("📜 Histórico de Atividades")
    df_h = buscar_dados("histórico")
    if not df_h.empty:
        st.dataframe(df_h.sort_values("data", ascending=False), use_container_width=True, hide_index=True)

# --- TELA: GERENCIAR USUÁRIOS (VERSÃO CORRIGIDA) ---
elif menu == "👥 Gerenciar Usuários":
    st.title("👥 Gestão de Acessos")
    aba_l, aba_a, aba_e = st.tabs(["Lista", "➕ Novo Usuário", "✏️ Editar / Senha"])
    
    # 1. Lista
    with aba_l:
        df_u = buscar_dados("usuários")
        if not df_u.empty:
            st.dataframe(df_u.drop(columns=['senha'], errors='ignore'), use_container_width=True)

    # 2. Adicionar Novo
    with aba_a:
        with st.form("add_user_form"):
            new_u = st.text_input("Login").strip().lower()
            new_s = st.text_input("Senha", type="password")
            new_n = st.selectbox("Nível", ["user", "gerente", "admin"])
            st.write("--- Permissões de Telas ---")
            c1, c2 = st.columns(2)
            p1 = c1.checkbox("Consultar Estoque", True)
            p2 = c1.checkbox("Realizar Movimentações")
            p3 = c1.checkbox("Cadastrar Produtos")
            p4 = c2.checkbox("Administração (Editar/Excluir)")
            p5 = c2.checkbox("Ver Histórico")
            p6 = c2.checkbox("Gerenciar Usuários")
            
            if st.form_submit_button("Criar Usuário"):
                if new_u and new_s:
                    supabase.table("usuários").insert({
                        "usuario": new_u, "senha": new_s, "nivel": new_n,
                        "can_consultar": p1, "can_movimentar": p2, "can_cadastrar": p3,
                        "can_admin": p4, "can_historico": p5, "can_usuarios": p6
                    }).execute()
                    st.success("Usuário criado!")
                    st.rerun()
                else:
                    st.error("Preencha todos os campos.")

    # 3. Editar Usuário (Correção do ValueError)
    with aba_e:
        df_u = buscar_dados("usuários")
        if not df_u.empty:
            user_edit = st.selectbox("Usuário para alterar", df_u['usuario'].tolist())
            u_data = df_u[df_u['usuario'] == user_edit].iloc[0]
            
            with st.form("edit_user_form"):
                nova_senha = st.text_input("Nova Senha (vazio mantém)", type="password")
                
                # Tratamento seguro do Nível
                niveis = ["user", "gerente", "admin"]
                nivel_atual = str(u_data.get('nivel', 'user')).lower()
                idx = niveis.index(nivel_atual) if nivel_atual in niveis else 0
                
                edit_n = st.selectbox("Nível", niveis, index=idx)
                
                st.write("--- Ajustar Permissões ---")
                col1, col2 = st.columns(2)
                e1 = col1.checkbox("Consultar", value=bool(u_data.get('can_consultar', True)))
                e2 = col1.checkbox("Movimentar", value=bool(u_data.get('can_movimentar', False)))
                e3 = col1.checkbox("Cadastrar", value=bool(u_data.get('can_cadastrar', False)))
                e4 = col2.checkbox("Administrar", value=bool(u_data.get('can_admin', False)))
                e5 = col2.checkbox("Histórico", value=bool(u_data.get('can_historico', False)))
                e6 = col2.checkbox("Gerenciar Usuários", value=bool(u_data.get('can_usuarios', False)))
                
                if st.form_submit_button("Salvar Alterações"):
                    upd = {
                        "nivel": edit_n, "can_consultar": e1, "can_movimentar": e2,
                        "can_cadastrar": e3, "can_admin": e4, "can_historico": e5, "can_usuarios": e6
                    }
                    if nova_senha: upd["senha"] = nova_senha
                    
                    supabase.table("usuários").update(upd).eq("usuario", user_edit).execute()
                    st.success("Usuário atualizado!")
                    st.rerun()
