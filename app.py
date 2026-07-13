import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime

# --- 1. CONFIGURAÇÕES DA PÁGINA ---
st.set_page_config(page_title="Sistema TI - Estoque", page_icon="📦", layout="wide")

# --- 2. CONEXÃO COM SUPABASE (COM PROTEÇÃO) ---
@st.cache_resource
def get_supabase() -> Client:
    # Busca as credenciais das 'Secrets' do Streamlit
    url = st.secrets["URL_BANCO"]
    key = st.secrets["CHAVE_BANCO"]
    return create_client(url, key)

supabase = get_supabase()

# --- 3. FUNÇÕES AUXILIARES (PARA EVITAR TRAVAMENTOS) ---
def buscar_dados(tabela):
    """Tenta buscar dados de uma tabela e retorna um DataFrame"""
    try:
        # Limitamos a 100 para não estourar a memória
        res = supabase.table(tabela).select("*").limit(100).execute()
        return pd.DataFrame(res.data)
    except Exception as e:
        st.error(f"Erro ao acessar a tabela {tabela}: {e}")
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
        # Verifica alertas de estoque baixo
        alertas = df[df['quantidade'] <= df['alerta']]
        if not alertas.empty:
            for _, item in alertas.iterrows():
                st.warning(f"🚨 **ALERTA:** {item['nome']} está com apenas {item['quantidade']} unidades.")
        
        st.divider()
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("Nenhum produto encontrado.")

# --- TELA: ENTRADA / SAÍDA ---
elif menu == "🔄 Entrada / Saída":
    st.title("🔄 Movimentação de Itens")
    df = buscar_dados("produtos")
    
    if not df.empty:
        # Criamos uma lista formatada para seleção
        opcoes = {f"{p['nome']} - {p['marca']} (Qtd: {p['quantidade']})": p for _, p in df.iterrows()}
        escolha = st.selectbox("Selecione o produto", list(opcoes.keys()))
        item_sel = opcoes[escolha]
        
        col1, col2 = st.columns(2)
        qtd_mov = col1.number_input("Quantidade", min_value=1, step=1)
        tipo_op = col2.radio("Operação", ["Entrada (Compra)", "Saída (Baixa)"])
        
        if st.button("Confirmar Movimentação", use_container_width=True):
            nova_qtd = item_sel['quantidade'] + qtd_mov if "Entrada" in tipo_op else item_sel['quantidade'] - qtd_mov
            
            if nova_qtd < 0:
                st.error("❌ Saldo insuficiente no estoque!")
            else:
                try:
                    # Atualiza estoque
                    supabase.table("produtos").update({"quantidade": int(nova_qtd)}).eq("id", item_sel['id']).execute()
                    # Registra no histórico
                    supabase.table("historico").insert({
                        "operador": st.session_state.user,
                        "acao": tipo_op,
                        "produto": f"{item_sel['nome']} ({item_sel['marca']})",
                        "quantidade": int(qtd_mov),
                        "data": datetime.now().isoformat()
                    }).execute()
                    
                    st.success("✅ Estoque atualizado com sucesso!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao salvar: {e}")

# --- TELA: CADASTRAR PRODUTO ---
elif menu == "🆕 Cadastrar Produto":
    st.title("🆕 Cadastro de Produto")
    with st.form("novo_produto"):
        n = st.text_input("Nome do Produto")
        m = st.text_input("Marca")
        mod = st.text_input("Modelo")
        cat = st.text_input("Categoria")
        q = st.number_input("Quantidade Inicial", min_value=0)
        a = st.number_input("Alerta Estoque Mínimo", min_value=1)
        
        if st.form_submit_button("Cadastrar"):
            if n and m:
                try:
                    supabase.table("produtos").insert({
                        "nome": n, "marca": m, "modelo": mod, 
                        "categoria": cat, "quantidade": int(q), "alerta": int(a)
                    }).execute()
                    st.success("Produto cadastrado!")
                except Exception as e:
                    st.error(f"Erro: {e}")
            else:
                st.error("Preencha Nome e Marca.")

# --- TELA: ADMINISTRAÇÃO ---
elif menu == "🔧 Administração (Admin)":
    st.title("🔧 Administração")
    if st.session_state.nivel != "admin":
        st.error("Acesso negado.")
    else:
        df = buscar_dados("produtos")
        if not df.empty:
            sel = st.selectbox("Escolha um produto para EXCLUIR", df['nome'].tolist())
            id_del = df[df['nome'] == sel]['id'].values[0]
            if st.button(f"Excluir {sel}"):
                try:
                    supabase.table("produtos").delete().eq("id", id_del).execute()
                    st.success("Excluído.")
                    st.rerun()
                except Exception as e:
                    st.error(e)

# --- TELA: HISTÓRICO (SOLUÇÃO PARA O CRASH) ---
elif menu == "📜 Histórico Geral":
    st.title("📜 Histórico de Movimentações")
    try:
        # Buscamos as últimas 50 para evitar o erro de 'Segmentation Fault'
        res = supabase.table("historico").select("*").order("data", desc=True).limit(50).execute()
        if res.data:
            df_h = pd.DataFrame(res.data)
            # Exibição simples (st.table é mais estável que st.dataframe para muitos dados)
            st.write("Últimas 50 movimentações:")
            st.table(df_h) 
        else:
            st.info("Histórico vazio.")
    except Exception as e:
        st.error(f"Erro ao carregar histórico: {e}")

# --- TELA: GERENCIAR USUÁRIOS ---
elif menu == "👥 Gerenciar Usuários":
    st.title("👥 Usuários")
    if st.session_state.nivel != "admin":
        st.error("Acesso negado.")
    else:
        df_u = buscar_dados("usuarios")
        st.write("Usuários cadastrados:")
        st.table(df_u[['usuario', 'nivel']]) # Mostra apenas colunas seguras
