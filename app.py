import streamlit as st
import pandas as pd
from supabase import create_client, Client

# --- CONFIGURAÇÃO E CONEXÃO ---
st.set_page_config(page_title="Sistema Ti - Estoque", page_icon="📦", layout="wide")

@st.cache_resource
def get_supabase():
    return create_client(st.secrets["URL_BANCO"], st.secrets["CHAVE_BANCO"])

supabase = get_supabase()

# --- ESTADO DA SESSÃO ---
if 'logado' not in st.session_state:
    st.session_state.logado = False
    st.session_state.nivel = None
    st.session_state.usuario_nome = None

# --- TELA DE LOGIN ---
if not st.session_state.logado:
    st.title("🔐 Acesso ao Sistema")
    with st.form("login"):
        u = st.text_input("Usuário").strip().lower()
        p = st.text_input("Senha", type="password").strip()
        if st.form_submit_button("Entrar", use_container_width=True):
            res = supabase.table("usuarios").select("*").eq("usuario", u).eq("senha", p).execute()
            if res.data:
                st.session_state.logado = True
                st.session_state.usuario_nome = u
                st.session_state.nivel = res.data[0]['nivel'] # 'admin' ou 'comum'
                st.rerun()
            else:
                st.error("Dados incorretos.")
    st.stop()

# --- MENU LATERAL ---
st.sidebar.title(f"Olá, {st.session_state.usuario_nome.capitalize()}")
st.sidebar.info(f"Nível: {st.session_state.nivel.upper()}")

menu = st.sidebar.radio("Navegação", [
    "📊 Consultar Estoque", 
    "📥 Entrada / 📤 Saída", 
    "🆕 Cadastrar Produto",
    "🔧 Correção de Produto",
    "👥 Gerenciar Usuários"
])

if st.sidebar.button("Sair"):
    st.session_state.logado = False
    st.rerun()

# --- 1. CONSULTAR ESTOQUE ---
if menu == "📊 Consultar Estoque":
    st.title("📊 Consultar Estoque")
    
    # Alertas de Estoque Mínimo
    try:
        dados = supabase.table("produtos").select("*").execute()
        df = pd.DataFrame(dados.data)
        
        if not df.empty:
            # Lógica de Alerta
            alertas = df[df['quantidade'] <= df['estoque_minimo']]
            if not alertas.empty:
                for _, item in alertas.iterrows():
                    st.warning(f"🚨 **ALERTA:** O produto **{item['nome']}** está com estoque baixo ({item['quantidade']} un).")

            st.divider()
            busca = st.text_input("Filtrar por nome ou código")
            if busca:
                df = df[df['nome'].str.contains(busca, case=False) | df['codigo'].astype(str).str.contains(busca)]
            
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum produto cadastrado.")
    except Exception as e:
        st.error(f"Erro ao carregar: {e}")

# --- 2. ENTRADA / SAÍDA ---
elif menu == "📥 Entrada / 📤 Saída":
    st.title("🔄 Movimentação de Estoque")
    
    res = supabase.table("produtos").select("id, nome, quantidade").execute()
    produtos_lista = {f"{p['nome']} (Qtd: {p['quantidade']})": p for p in res.data}
    
    escolha = st.selectbox("Selecione o produto", list(produtos_lista.keys()))
    produto_sel = produtos_lista[escolha]
    
    col1, col2 = st.columns(2)
    with col1:
        qtd_mov = st.number_input("Quantidade", min_value=1, step=1)
    with col2:
        tipo = st.radio("Operação", ["Entrada (Compra)", "Saída (Uso)"])

    if st.button("Confirmar Movimentação"):
        nova_qtd = produto_sel['quantidade'] + qtd_mov if tipo == "Entrada (Compra)" else produto_sel['quantidade'] - qtd_mov
        
        if nova_qtd < 0:
            st.error("Erro: Estoque insuficiente para essa saída!")
        else:
            supabase.table("produtos").update({"quantidade": nova_qtd}).eq("id", produto_sel['id']).execute()
            st.success("Estoque atualizado com sucesso!")
            st.rerun()

# --- 3. CADASTRAR PRODUTO ---
elif menu == "🆕 Cadastrar Produto":
    st.title("🆕 Cadastrar Novo Produto")
    with st.form("form_cadastro"):
        cod = st.text_input("Código do Produto")
        nome = st.text_input("Nome")
        qtd_ini = st.number_input("Quantidade Inicial", min_value=0)
        est_min = st.number_input("Estoque Mínimo", min_value=1)
        
        if st.form_submit_button("Cadastrar"):
            if cod and nome:
                supabase.table("produtos").insert({
                    "codigo": cod, "nome": nome, "quantidade": qtd_ini, "estoque_minimo": est_min
                }).execute()
                st.success("Produto cadastrado!")
            else:
                st.error("Preencha os campos obrigatórios.")

# --- 4. CORREÇÃO DE PRODUTO (RESTRITO ADMIN) ---
elif menu == "🔧 Correção de Produto":
    st.title("🔧 Correção de Dados")
    if st.session_state.nivel != "admin":
        st.error("Apenas administradores podem corrigir nomes ou códigos.")
    else:
        res = supabase.table("produtos").select("*").execute()
        df_corr = pd.DataFrame(res.data)
        escolha = st.selectbox("Produto para editar", df_corr['nome'].tolist())
        prod_dados = df_corr[df_corr['nome'] == escolha].iloc[0]

        with st.form("form_edit"):
            novo_cod = st.text_input("Novo Código", value=str(prod_dados['codigo']))
            novo_nome = st.text_input("Novo Nome", value=prod_dados['nome'])
            novo_min = st.number_input("Novo Estoque Mínimo", value=int(prod_dados['estoque_minimo']))
            
            if st.form_submit_button("Salvar Alterações"):
                supabase.table("produtos").update({
                    "codigo": novo_cod, "nome": novo_nome, "estoque_minimo": novo_min
                }).eq("id", prod_dados['id']).execute()
                st.success("Dados corrigidos!")
                st.rerun()

# --- 5. GERENCIAR USUÁRIOS (RESTRITO ADMIN) ---
elif menu == "👥 Gerenciar Usuários":
    st.title("👥 Gestão de Usuários")
    if st.session_state.nivel != "admin":
        st.error("Acesso restrito ao Administrador.")
    else:
        with st.expander("➕ Adicionar Novo Usuário"):
            nu = st.text_input("Novo Usuário").strip().lower()
            ns = st.text_input("Senha", type="password")
            nv = st.selectbox("Nível", ["comum", "admin"])
            if st.button("Criar Usuário"):
                supabase.table("usuarios").insert({"usuario": nu, "senha": ns, "nivel": nv}).execute()
                st.success("Usuário criado!")

        st.subheader("Usuários Atuais")
        users = supabase.table("usuarios").select("id, usuario, nivel").execute()
        st.table(pd.DataFrame(users.data))
