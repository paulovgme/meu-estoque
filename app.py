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
if st.session_state.perms.get('admin'):      opcoes_menu.append("🔧 Correção de Produtos")
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
        termo = st.text_input("🔍 Pesquisar por ID, Nome, Marca ou Modelo").lower()
        
        # Filtro corrigido com .str.contains()
        df_filtrado = df[
            df['nome'].str.lower().str.contains(termo, na=False) | 
            df['marca'].str.lower().str.contains(termo, na=False) |
            df['id'].astype(str).str.contains(termo, na=False) |
            df['modelo'].astype(str).str.lower().str.contains(termo, na=False)
        ]
        
        st.dataframe(df_filtrado, use_container_width=True, hide_index=True)

        # Edição rápida para Admins via ID
        if st.session_state.perms.get('admin'):
            st.divider()
            with st.expander("✏️ Corrigir produto selecionando pelo ID"):
                lista_opcoes = {f"ID: {row['id']} | {row['nome']}": row['id'] for _, row in df_filtrado.iterrows()}
                if lista_opcoes:
                    sel_label = st.selectbox("Selecione o ID do produto", list(lista_opcoes.keys()))
                    id_selecionado = lista_opcoes[sel_label]
                    p_dados = df[df['id'] == id_selecionado].iloc[0]
                    
                    with st.form("quick_edit"):
                        c1, c2 = st.columns(2)
                        new_n = c1.text_input("Nome", value=p_dados['nome'])
                        new_m = c1.text_input("Marca", value=p_dados['marca'])
                        new_mod = c2.text_input("Modelo", value=str(p_dados.get('modelo', '')) if p_dados.get('modelo') else "")
                        new_cat = c2.text_input("Categoria", value=p_dados['categoria'])
                        
                        if st.form_submit_button("Salvar Correção"):
                            supabase.table("produtos").update({
                                "nome": new_n, "marca": new_m, "modelo": new_mod, "categoria": new_cat
                            }).eq("id", id_selecionado).execute()
                            st.success(f"Produto ID {id_selecionado} atualizado!")
                            st.rerun()
                else:
                    st.warning("Nenhum produto encontrado para editar.")
    else:
        st.info("Nenhum produto cadastrado.")

# --- TELA: ENTRADA / SAÍDA ---
elif menu == "🔄 Entrada / Saída":
    st.title("🔄 Movimentação")
    df = buscar_dados("produtos")
    if not df.empty:
        opcoes_mov = {f"ID: {p['id']} | {p['nome']}": p for _, p in df.iterrows()}
        escolha = st.selectbox("Selecione o produto (ID | Nome)", list(opcoes_mov.keys()))
        item_sel = opcoes_mov[escolha]
        
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
                st.success("Movimentação registrada!")
                st.rerun()

# --- TELA: CADASTRAR PRODUTO ---
elif menu == "🆕 Cadastrar Produto":
    st.title("🆕 Novo Produto")
    with st.form("novo_p"):
        n = st.text_input("Nome do Produto").strip()
        m = st.text_input("Marca")
        mod = st.text_input("Modelo")
        cat = st.text_input("Categoria")
        q = st.number_input("Qtd Inicial", min_value=0)
        a = st.number_input("Alerta Estoque Mínimo", min_value=1)
        if st.form_submit_button("Cadastrar"):
            if n:
                check = supabase.table("produtos").select("id").eq("nome", n).execute()
                if check.data:
                    st.error("Já existe um produto com este nome!")
                else:
                    supabase.table("produtos").insert({
                        "nome":n, "marca":m, "modelo":mod, "categoria":cat, 
                        "quantidade":int(q), "alerta":int(a)
                    }).execute()
                    st.success("Cadastrado!")
                    st.rerun()
            else: st.error("O campo Nome é obrigatório")

# --- TELA: CORREÇÃO DE PRODUTOS ---
elif menu == "🔧 Correção de Produtos":
    st.title("🔧 Correção de Produtos")
    df = buscar_dados("produtos")
    if not df.empty:
        aba_corr, aba_excl = st.tabs(["📝 Corrigir Dados", "🚨 Excluir Produto"])
        
        with aba_corr:
            dic_id = {f"ID: {row['id']} - {row['nome']}": row['id'] for _, row in df.iterrows()}
            sel_id_label = st.selectbox("Selecione o ID do produto para corrigir", list(dic_id.keys()))
            id_atual = dic_id[sel_id_label]
            p = df[df['id'] == id_atual].iloc[0]
            
            with st.form("form_correcao_completa"):
                st.write(f"Editando informações do **ID {id_atual}**")
                col_a, col_b = st.columns(2)
                nome_c = col_a.text_input("Nome", value=p['nome'])
                marca_c = col_a.text_input("Marca", value=p['marca'])
                modelo_c = col_b.text_input("Modelo", value=str(p.get('modelo', '')) if p.get('modelo') else "")
                cat_c = col_b.text_input("Categoria", value=p['categoria'])
                alerta_c = st.number_input("Alerta de Estoque", value=int(p['alerta']))
                
                if st.form_submit_button("Salvar Alterações"):
                    supabase.table("produtos").update({
                        "nome": nome_c, "marca": marca_c, "modelo": modelo_c, "categoria": cat_c, "alerta": int(alerta_c)
                    }).eq("id", id_atual).execute()
                    st.success("Produto corrigido!")
                    st.rerun()

        with aba_excl:
            if st.button(f"CONFIRMAR EXCLUSÃO DO ID: {id_atual}", type="primary"):
                supabase.table("produtos").delete().eq("id", id_atual).execute()
                st.success("Produto excluído.")
                st.rerun()

# --- TELA: HISTÓRICO ---
elif menu == "📜 Histórico Geral":
    st.title("📜 Histórico")
    df_h = buscar_dados("historico")
    if not df_h.empty:
        st.dataframe(df_h.sort_values("data", ascending=False), use_container_width=True, hide_index=True)

# --- TELA: GERENCIAR USUÁRIOS ---
elif menu == "👥 Gerenciar Usuários":
    st.title("👥 Gestão de Usuários")
    aba_l, aba_a, aba_e = st.tabs(["📋 Lista de Usuários", "➕ Novo Usuário", "✏️ Editar Permissões"])
    df_u = buscar_dados("usuarios")

    with aba_l:
        if not df_u.empty:
            st.dataframe(df_u[['usuario', 'nivel']], use_container_width=True, hide_index=True)

    with aba_a:
        with st.form("form_novo_usuario"):
            nu = st.text_input("Login").lower().strip()
            ns = st.text_input("Senha", type="password")
            nv = st.selectbox("Nível", ["comum", "administrador"])
            c1, c2 = st.columns(2)
            p1 = c1.checkbox("Consultar", value=True)
            p2 = c1.checkbox("Movimentar")
            p3 = c1.checkbox("Cadastrar")
            p4 = c2.checkbox("Correção (Admin)")
            p5 = c2.checkbox("Histórico")
            p6 = c2.checkbox("Gerir Usuários")
            if st.form_submit_button("Criar"):
                if nu and ns:
                    supabase.table("usuarios").insert({
                        "usuario": nu, "senha": ns, "nivel": nv,
                        "can_consultar": p1, "can_movimentar": p2, "can_cadastrar": p3,
                        "can_admin": p4, "can_historico": p5, "can_usuarios": p6
                    }).execute()
                    st.success("Usuário criado!")
                    st.rerun()

    with aba_e:
        if not df_u.empty:
            user_edit = st.selectbox("Usuário", df_u['usuario'].tolist())
            u_sel = df_u[df_u['usuario'] == user_edit].iloc[0]
            with st.form("edit_u"):
                nova_s = st.text_input("Nova Senha (vazio mantém)", type="password")
                niveis = ["comum", "administrador"]
                idx = 1 if u_sel['nivel'] == 'administrador' else 0
                novo_n = st.selectbox("Nível", niveis, index=idx)
                col1, col2 = st.columns(2)
                e1 = col1.checkbox("Consultar", value=bool(u_sel.get('can_consultar', True)))
                e2 = col1.checkbox("Movimentar", value=bool(u_sel.get('can_movimentar', False)))
                e3 = col1.checkbox("Cadastrar", value=bool(u_sel.get('can_cadastrar', False)))
                e4 = col2.checkbox("Correção (Admin)", value=bool(u_sel.get('can_admin', False)))
                e5 = col2.checkbox("Histórico", value=bool(u_sel.get('can_historico', False)))
                e6 = col2.checkbox("Gerir Usuários", value=bool(u_sel.get('can_usuarios', False)))
                if st.form_submit_button("Atualizar"):
                    upd = {"nivel": novo_n, "can_consultar": e1, "can_movimentar": e2, "can_cadastrar": e3, "can_admin": e4, "can_historico": e5, "can_usuarios": e6}
                    if nova_s: upd["senha"] = nova_s
                    supabase.table("usuarios").update(upd).eq("usuario", user_edit).execute()
                    st.success("Usuário atualizado!")
                    st.rerun()
