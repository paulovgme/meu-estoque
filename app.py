import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime

# --- 1. CONFIGURAÇÕES DA PÁGINA ---
st.set_page_config(page_title="Sistema TI - Estoque", page_icon="📦", layout="wide")

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
        res = supabase.table(tabela).select("*").limit(500).execute()
        return pd.DataFrame(res.data)
    except Exception as e:
        st.error(f"Erro ao acessar {tabela}: {e}")
        return pd.DataFrame()

# --- 4. CONTROLE DE ACESSO (LOGIN) ---
if 'logado' not in st.session_state:
    st.session_state.logado = False
    st.session_state.nivel = None
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
                    st.session_state.logado = True
                    st.session_state.user = u
                    st.session_state.nivel = res.data[0]['nivel']
                    st.rerun()
                else:
                    st.error("Usuário ou senha inválidos.")
            except Exception as e:
                st.error(f"Erro de conexão: {e}")
    st.stop()

# --- 5. MENU LATERAL ---
st.sidebar.title(f"👋 Olá, {st.session_state.user.capitalize()}")
st.sidebar.write(f"Nível: **{st.session_state.nivel.upper()}**")

menu = st.sidebar.radio("Navegação", [
    "📊 Consultar Estoque", 
    "🔄 Entrada / Saída", 
    "🆕 Cadastrar Produto",
    "🔧 Administração (Admin)",
    "📜 Histórico Geral",
    "👥 Gerenciar Usuários"
])

if st.sidebar.button("Sair / Logoff"):
    st.session_state.logado = False
    st.rerun()

# --- 6. TELAS DO SISTEMA ---

# --- TELA: CONSULTAR ESTOQUE ---
if menu == "📊 Consultar Estoque":
    st.title("📊 Consultar Estoque")
    df = buscar_dados("produtos")
    
    if not df.empty:
        col_busca, col_exp = st.columns([3, 1])
        termo = col_busca.text_input("🔍 Pesquisar por nome, marca ou categoria").lower()
        
        df_filtrado = df[
            df['nome'].str.lower().str.contains(termo) | 
            df['marca'].str.lower().str.contains(termo) |
            df['categoria'].str.lower().str.contains(termo)
        ]

        csv = df_filtrado.to_csv(index=False).encode('utf-8')
        col_exp.download_button("📥 Baixar Planilha CSV", csv, "estoque.csv", "text/csv")

        alertas = df[df['quantidade'] <= df['alerta']]
        if not alertas.empty:
            with st.expander(f"🚨 Existem {len(alertas)} itens com estoque baixo!", expanded=False):
                for _, item in alertas.iterrows():
                    st.warning(f"**{item['nome']}** (Mín: {item['alerta']} | Atual: {item['quantidade']})")
        
        st.divider()
        st.dataframe(df_filtrado, use_container_width=True, hide_index=True)
    else:
        st.info("Nenhum produto encontrado.")

# --- TELA: ENTRADA / SAÍDA ---
elif menu == "🔄 Entrada / Saída":
    st.title("🔄 Movimentação de Itens")
    df = buscar_dados("produtos")
    
    if not df.empty:
        # Busca para filtrar o selectbox
        busca_mov = st.text_input("🔍 Digite para filtrar (Nome, Marca ou Categoria)").lower()
        
        df_filtrado_mov = df[
            df['nome'].str.lower().str.contains(busca_mov) | 
            df['marca'].str.lower().str.contains(busca_mov) |
            df['categoria'].str.lower().str.contains(busca_mov)
        ]

        if not df_filtrado_mov.empty:
            opcoes = {f"{p['nome']} - {p['marca']} ({p['categoria']}) | Qtd: {p['quantidade']}": p for _, p in df_filtrado_mov.iterrows()}
            escolha = st.selectbox("Selecione o produto", list(opcoes.keys()))
            item_sel = opcoes[escolha]
            
            st.divider()
            col1, col2 = st.columns(2)
            qtd_mov = col1.number_input("Quantidade", min_value=1, step=1)
            tipo_op = col2.radio("Operação", ["Entrada (Compra)", "Saída (Baixa)"])
            
            if st.button("Confirmar Movimentação", use_container_width=True, type="primary"):
                nova_qtd = item_sel['quantidade'] + qtd_mov if "Entrada" in tipo_op else item_sel['quantidade'] - qtd_mov
                
                if nova_qtd < 0:
                    st.error("❌ Saldo insuficiente para realizar essa saída!")
                else:
                    try:
                        supabase.table("produtos").update({"quantidade": int(nova_qtd)}).eq("id", item_sel['id']).execute()
                        supabase.table("historico").insert({
                            "operador": st.session_state.user, "acao": tipo_op, 
                            "produto": item_sel['nome'], "quantidade": int(qtd_mov), 
                            "data": datetime.now().isoformat()
                        }).execute()
                        st.success(f"✅ Movimentação de {item_sel['nome']} realizada!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro: {e}")
        else:
            st.warning("Nenhum produto encontrado com este termo.")

# --- TELA: CADASTRAR PRODUTO ---
elif menu == "🆕 Cadastrar Produto":
    st.title("🆕 Novo Produto")
    with st.form("novo_p"):
        n = st.text_input("Nome")
        m = st.text_input("Marca")
        cat = st.text_input("Categoria")
        q = st.number_input("Qtd Inicial", min_value=0)
        a = st.number_input("Alerta Mínimo", min_value=1)
        if st.form_submit_button("Cadastrar"):
            if n and m:
                supabase.table("produtos").insert({"nome":n,"marca":m,"categoria":cat,"quantidade":int(q),"alerta":int(a)}).execute()
                st.success("Produto cadastrado!")
            else: st.error("Preencha Nome e Marca")

# --- TELA: ADMINISTRAÇÃO ---
elif menu == "🔧 Administração (Admin)":
    st.title("🔧 Painel Administrativo")
    if st.session_state.nivel != "admin":
        st.error("Acesso negado.")
    else:
        df = buscar_dados("produtos")
        if not df.empty:
            aba_edit, aba_del = st.tabs(["✏️ Editar Produto", "🗑️ Excluir Produto"])
            
            with aba_edit:
                # Busca para filtrar o selectbox de edição
                busca_edit = st.text_input("🔍 Buscar item para editar").lower()
                df_filtrado_edit = df[
                    df['nome'].str.lower().str.contains(busca_edit) | 
                    df['categoria'].str.lower().str.contains(busca_edit)
                ]

                if not df_filtrado_edit.empty:
                    opcoes_edit = {f"{r['nome']} ({r['marca']})": r for _, r in df_filtrado_edit.iterrows()}
                    sel_item = st.selectbox("Selecione o item", list(opcoes_edit.keys()))
                    p = opcoes_edit[sel_item]

                    with st.form("edit_f"):
                        en = st.text_input("Nome", value=p['nome'])
                        em = st.text_input("Marca", value=p['marca'])
                        ec = st.text_input("Categoria", value=p['categoria'])
                        ea = st.number_input("Alerta", value=int(p['alerta']))
                        if st.form_submit_button("Salvar Alterações"):
                            supabase.table("produtos").update({"nome":en,"marca":em,"categoria":ec,"alerta":int(ea)}).eq("id", p['id']).execute()
                            st.success("Atualizado!")
                            st.rerun()
                else:
                    st.warning("Nenhum produto encontrado para editar.")
            
            with aba_del:
                sel_d = st.selectbox("Selecione para EXCLUIR", df['nome'].tolist())
                if st.button(f"Confirmar Exclusão de {sel_d}", type="primary"):
                    id_d = df[df['nome'] == sel_d]['id'].values[0]
                    supabase.table("produtos").delete().eq("id", id_d).execute()
                    st.success("Excluído com sucesso!")
                    st.rerun()

# --- TELA: HISTÓRICO ---
elif menu == "📜 Histórico Geral":
    st.title("📜 Histórico")
    res = supabase.table("historico").select("*").order("data", desc=True).limit(200).execute()
    if res.data:
        df_h = pd.DataFrame(res.data)
        st.dataframe(df_h, use_container_width=True, hide_index=True)

# --- TELA: GERENCIAR USUÁRIOS ---
elif menu == "👥 Gerenciar Usuários":
    st.title("👥 Usuários")
    if st.session_state.nivel == "admin":
        df_u = buscar_dados("usuarios")
        st.table(df_u[['usuario', 'nivel']])
