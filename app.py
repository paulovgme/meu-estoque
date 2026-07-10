import streamlit as st
import pandas as pd
import plotly.express as px
from st_supabase_connection import SupabaseConnection
import time

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Ti - Estoque Profissional", page_icon="🔥", layout="wide")

# --- 2. CONEXÃO COM O BANCO ---
try:
    url_banco = st.secrets["URL_BANCO"]
    key_banco = st.secrets["CHAVE_BANCO"]
    
    conn = st.connection(
        "supabase",
        type=SupabaseConnection,
        url=url_banco,
        key=key_banco
    )
except Exception as e:
    st.error(f"❌ Erro na conexão: {e}")
    st.stop()

# --- 3. ESTILO VISUAL ---
st.markdown("""
    <style>
    .stApp { background-color: white; }
    .stButton>button { background-color: #FF8C00; color: white; border-radius: 8px; width: 100%; font-weight: bold; }
    h1, h2, h3 { color: #FF8C00 !important; }
    .stMetric { background-color: #FFF5EE; padding: 15px; border-radius: 10px; border-left: 5px solid #FF8C00; }
    </style>
    """, unsafe_allow_html=True)

# Função para carregar dados
def carregar_dados(tabela):
    try:
        res = conn.table(tabela).select("*").execute()
        return pd.DataFrame(res.data)
    except:
        return pd.DataFrame()

if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

# --- 4. LOGIN ---
if not st.session_state['logged_in']:
    st.title("🔥 Ti - Sistema de Gestão")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("form_login"):
            u = st.text_input("Usuário").strip().lower()
            p = st.text_input("Senha", type="password").strip()
            if st.form_submit_button("Acessar Sistema"):
                res = conn.table("usuarios").select("*").eq("usuario", u).eq("senha", p).execute()
                if res.data:
                    st.session_state['logged_in'] = True
                    st.session_state['user'] = u
                    st.session_state['nivel'] = res.data[0]['nivel'].strip().lower()
                    st.rerun()
                else:
                    st.error("Login inválido")

# --- 5. SISTEMA LOGADO ---
else:
    opcoes = ["📊 Estatísticas", "📦 Estoque Atual", "🔄 Movimentação", "➕ Novo Produto", "🚪 Sair"]
    if st.session_state['nivel'] == 'admin':
        opcoes.insert(4, "🛠️ Ajustar Produto")
        opcoes.insert(5, "👥 Usuários")
    
    menu = st.sidebar.radio(f"Olá, {st.session_state['user'].capitalize()}", opcoes)

    if menu == "🚪 Sair":
        st.session_state['logged_in'] = False
        st.rerun()

    # --- ABA ESTATÍSTICAS ---
    elif menu == "📊 Estatísticas":
        st.title("📊 Desempenho de Saídas")
        df_h = carregar_dados("historico")
        if not df_h.empty:
            saidas = df_h[df_h['acao'].str.upper() == 'SAIDA']
            if not saidas.empty:
                estat = saidas.groupby('produto')['quantidade'].sum().reset_index()
                st.plotly_chart(px.bar(estat, x='produto', y='quantidade', color_discrete_sequence=['#FF8C00']), use_container_width=True)
            else: st.info("Ainda não há registros de saída.")

    # --- ABA ESTOQUE ---
    elif menu == "📦 Estoque Atual":
        st.title("📦 Controle de Estoque")
        df_p = carregar_dados("produtos")
        if not df_p.empty:
            baixo = df_p[df_p['quantidade'] <= df_p['alerta']]
            if not baixo.empty:
                st.error(f"🚨 ESTOQUE CRÍTICO EM {len(baixo)} ITENS")
            st.dataframe(df_p, use_container_width=True, hide_index=True)
            if st.button("🔄 Atualizar"):
                st.rerun()

    # --- ABA MOVIMENTAÇÃO ---
    elif menu == "🔄 Movimentação":
        st.title("🔄 Registro de Entrada/Saída")
        df_p = carregar_dados("produtos")
        if not df_p.empty:
            with st.form("mov", clear_on_submit=True):
                prod = st.selectbox("Selecione o Equipamento", df_p['nome'].unique())
                tipo = st.radio("Operação", ["ENTRADA", "SAIDA"])
                qtd = st.number_input("Quantidade", min_value=1)
                if st.form_submit_button("Confirmar Movimentação"):
                    item = df_p[df_p['nome'] == prod].iloc[0]
                    nova_qtd = (int(item['quantidade']) + qtd) if tipo == "ENTRADA" else (int(item['quantidade']) - qtd)
                    conn.table("produtos").update({"quantidade": nova_qtd}).eq("nome", prod).execute()
                    conn.table("historico").insert({"operador": st.session_state['user'], "acao": tipo, "produto": prod, "quantidade": qtd}).execute()
                    st.success("Registrado com sucesso!")
                    time.sleep(1) # Espera 1 segundo para evitar erro de 'Node'
                    st.rerun()

    # --- ABA NOVO PRODUTO ---
    elif menu == "➕ Novo Produto":
        st.title("➕ Cadastrar Equipamento")
        with st.form("cad", clear_on_submit=True):
            n = st.text_input("Nome")
            c = st.selectbox("Categoria", ["TI", "Infra", "Redes", "Outros"])
            q = st.number_input("Estoque Inicial", min_value=0)
            p = st.number_input("Preço", min_value=0.0)
            a = st.number_input("Alerta", min_value=1)
            if st.form_submit_button("Salvar"):
                conn.table("produtos").insert({"nome": n, "categoria": c, "quantidade": q, "preco": p, "alerta": a}).execute()
                st.success("Cadastrado!")
                time.sleep(1)
                st.rerun()

    # --- ABA AJUSTAR PRODUTO ---
    elif menu == "🛠️ Ajustar Produto":
        st.title("🛠️ Editar Produto")
        df_p = carregar_dados("produtos")
        if not df_p.empty:
            item_edit = st.selectbox("Selecione", df_p['nome'].unique())
            novo_nome = st.text_input("Novo nome")
            nova_cat = st.selectbox("Nova Categoria", ["TI", "Infra", "Redes", "Outros"])
            if st.button("Salvar Alterações"):
                conn.table("produtos").update({"nome": novo_nome if novo_nome else item_edit, "categoria": nova_cat}).eq("nome", item_edit).execute()
                st.success("Atualizado!")
                time.sleep(1)
                st.rerun()

    # --- ABA USUÁRIOS ---
    elif menu == "👥 Usuários":
        st.title("👥 Gestão de Acessos")
        with st.form("u", clear_on_submit=True):
            nu = st.text_input("Usuário").lower()
            ns = st.text_input("Senha")
            nl = st.selectbox("Nível", ["operador", "admin"])
            if st.form_submit_button("Criar"):
                conn.table("usuarios").insert({"usuario": nu, "senha": ns, "nivel": nl}).execute()
                st.success("Criado!")
                time.sleep(1)
                st.rerun()
