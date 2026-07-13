import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime

# --- 1. CONFIGURAÇÕES INICIAIS ---
st.set_page_config(page_title="Sistema Ti - Estoque", page_icon="📦", layout="wide")

# --- 2. CONEXÃO COM SUPABASE (COM CACHE) ---
@st.cache_resource
def get_supabase() -> Client:
    # Busca das secrets do Streamlit
    return create_client(st.secrets["URL_BANCO"], st.secrets["CHAVE_BANCO"])

supabase = get_supabase()

# --- Funções de Dados (Para evitar consultas repetitivas) ---
@st.cache_data(ttl=60) # Atualiza os dados a cada 60 segundos
def listar_produtos():
    res = supabase.table("produtos").select("*").execute()
    return pd.DataFrame(res.data)

@st.cache_data(ttl=600) # Cache de usuários por 10 minutos
def verificar_login(u, p):
    try:
        res = supabase.table("usuarios").select("*").eq("usuario", u).eq("senha", p).execute()
        return res.data
    except:
        return None

# --- 3. ESTADO DA SESSÃO ---
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
            dados_usuario = verificar_login(u, p)
            if dados_usuario:
                st.session_state.logado = True
                st.session_state.user = u
                st.session_state.nivel = dados_usuario[0]['nivel']
                st.rerun()
            else:
                st.error("Usuário ou senha inválidos.")
    st.stop()

# --- MENU LATERAL ---
st.sidebar.title(f"👋 Olá, {st.session_state.user.capitalize()}")
st.sidebar.write(f"**Nível:** {st.session_state.nivel.upper()}")

menu = st.sidebar.radio("Navegação", [
    "📊 Consultar Estoque", 
    "🔄 Entrada / Saída", 
    "🆕 Cadastrar Produto",
    "🔧 Correção e Exclusão (Admin)",
    "📜 Histórico Geral",
    "👥 Gerenciar Usuários"
])

if st.sidebar.button("Sair / Logoff"):
    st.session_state.logado = False
    st.rerun()

# --- 1. CONSULTAR ESTOQUE ---
if menu == "📊 Consultar Estoque":
    st.title("📊 Consultar Estoque")
    df = listar_produtos()
    if not df.empty:
        # Lógica de Alerta
        alertas = df[df['quantidade'] <= df['alerta']]
        if not alertas.empty:
            for _, item in alertas.iterrows():
                st.warning(f"🚨 **ALERTA:** {item['nome']} ({item['marca']}) está baixo!")
        
        st.divider()
        st.dataframe(df, use_container_width=True, hide_index=True)
        if st.button("🔄 Atualizar Dados"):
            st.cache_data.clear() # Limpa o cache para forçar nova busca
            st.rerun()
    else:
        st.info("Estoque vazio.")

# --- 2. ENTRADA / SAÍDA ---
elif menu == "🔄 Entrada / Saída":
    st.title("🔄 Movimentação de Itens")
    df = listar_produtos()
    if not df.empty:
        # Criamos uma lista formatada para o selectbox
        opcoes = {f"{r['nome']} - {r['marca']} (Qtd: {r['quantidade']})": r for _, r in df.iterrows()}
        escolha = st.selectbox("Selecione o produto", list(opcoes.keys()))
        item_sel = opcoes[escolha]
        
        col1, col2 = st.columns(2)
        qtd_mov = col1.number_input("Quantidade", min_value=1, step=1)
        tipo_op = col2.radio("Operação", ["Entrada (Compra)", "Saída (Baixa)"])
        
        if st.button("Confirmar Movimentação"):
            nova_qtd = item_sel['quantidade'] + qtd_mov if "Entrada" in tipo_op else item_sel['quantidade'] - qtd_mov
            
            if nova_qtd < 0:
                st.error("❌ Saldo insuficiente!")
            else:
                try:
                    # Atualiza estoque
                    supabase.table("produtos").update({"quantidade": int(nova_qtd)}).eq("id", item_sel['id']).execute()
                    # Registra histórico
                    supabase.table("historico").insert({
                        "operador": st.session_state.user, 
                        "acao": tipo_op,
                        "produto": f"{item_sel['nome']} ({item_sel['marca']})", 
                        "quantidade": int(qtd_mov),
                        "data": datetime.now().isoformat()
                    }).execute()
                    
                    st.cache_data.clear() # Limpa o cache para refletir a mudança
                    st.success("✅ Sucesso!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao processar: {e}")

# --- 3. CADASTRAR PRODUTO ---
elif menu == "🆕 Cadastrar Produto":
    st.title("🆕 Cadastro de Novo Produto")
    with st.form("form_novo"):
        nome = st.text_input("Nome do Produto")
        marca = st.text_input("Marca")
        modelo = st.text_input("Modelo")
        categoria = st.text_input("Categoria")
        qtd = st.number_input("Quantidade Inicial", min_value=0)
        alerta = st.number_input("Estoque Mínimo", min_value=1)
        
        if st.form_submit_button("Cadastrar"):
            if nome and marca:
                supabase.table("produtos").insert({
                    "nome": nome, "marca": marca, "modelo": modelo, 
                    "categoria": categoria, "quantidade": int(qtd), "alerta": int(alerta)
                }).execute()
                st.cache_data.clear()
                st.success("Cadastrado!")
            else:
                st.error("Nome e Marca são obrigatórios!")

# --- 4. CORREÇÃO (ADMIN) ---
elif menu == "🔧 Correção e Exclusão (Admin)":
    if st.session_state.nivel != "admin":
        st.error("Acesso restrito")
    else:
        df = listar_produtos()
        sel_prod = st.selectbox("Escolha o produto", df['nome'].tolist())
        dados_p = df[df['nome'] == sel_prod].iloc[0]
        
        with st.form("edit"):
            n_nome = st.text_input("Nome", value=dados_p['nome'])
            if st.form_submit_button("Salvar"):
                supabase.table("produtos").update({"nome": n_nome}).eq("id", dados_p['id']).execute()
                st.cache_data.clear()
                st.rerun()

# --- 5. HISTÓRICO ---
elif menu == "📜 Histórico Geral":
    st.title("📜 Histórico")
    res = supabase.table("historico").select("*").order("data", desc=True).limit(100).execute()
    st.dataframe(pd.DataFrame(res.data), use_container_width=True)

# --- 6. USUÁRIOS ---
elif menu == "👥 Gerenciar Usuários":
    if st.session_state.nivel == "admin":
        st.write("Área do Admin para gerenciar usuários")
        # Aqui você pode manter o seu código original de usuários
