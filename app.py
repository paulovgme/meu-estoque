import streamlit as st
import pandas as pd
import requests
import plotly.express as px

# --- CONFIGURAÇÃO DOS LINKS (COLE OS SEUS AQUI) ---
LINK_USUARIOS = "https://docs.google.com/spreadsheets/d/e/2PACX-1vR66hMMGy2uGkRwwHAAW_UL9tEq33eJe4gvY-RiI7BUuQMg2-Pmk7L8z6Jv17rQ5DvVEq0CtTPBPdnP/pub?gid=0&single=true&output=csv"
LINK_PRODUTOS = "https://docs.google.com/spreadsheets/d/e/2PACX-1vR66hMMGy2uGkRwwHAAW_UL9tEq33eJe4gvY-RiI7BUuQMg2-Pmk7L8z6Jv17rQ5DvVEq0CtTPBPdnP/pub?gid=622782364&single=true&output=csv"
LINK_HISTORICO = "COLE_AQUI_O_LINK_CSV_DA_ABA_HISTORICO"
URL_SCRIPTS = "COLE_AQUI_O_LINK_DO_PASSO_1"

st.set_page_config(page_title="Ti Ercal - Gestão", page_icon="🧡", layout="wide")

# --- ESTILO LARANJA E BRANCO ---
st.markdown(f"""
    <style>
    .stApp {{ background-color: white; }}
    .stButton>button {{ background-color: #FF8C00; color: white; border-radius: 10px; }}
    .sidebar .sidebar-content {{ background-color: #FFF5EE; }}
    h1, h2, h3 {{ color: #FF8C00; }}
    </style>
    """, unsafe_allow_html=True)

if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
    st.session_state['user'] = ""
    st.session_state['nivel'] = ""

def carregar(url):
    df = pd.read_csv(url)
    df.columns = df.columns.str.strip().str.lower()
    return df

# --- LOGIN ---
if not st.session_state['logged_in']:
    st.title("🧡 Ti Ercal - Acesso")
    with st.form("login"):
        u = st.text_input("Usuário").lower()
        p = st.text_input("Senha", type="password")
        if st.form_submit_button("Entrar"):
            df_u = carregar(LINK_USUARIOS)
            valido = df_u[(df_u['usuario'] == u) & (df_u['senha'].astype(str) == str(p))]
            if not valido.empty:
                st.session_state['logged_in'] = True
                st.session_state['user'] = u
                st.session_state['nivel'] = valido.iloc[0]['nivel']
                st.rerun()
            else:
                st.error("login invalido")

# --- SISTEMA ---
else:
    menu = st.sidebar.radio("Ti Ercal Menu", ["📊 Estatísticas", "📦 Estoque", "🔄 Movimentação", "➕ Novo Produto", "👥 Usuários", "🚪 Sair"])

    if menu == "Sair":
        st.session_state['logged_in'] = False
        st.rerun()

    # 📊 ESTATÍSTICAS
    if menu == "📊 Estatísticas":
        st.title("📊 Painel de Performance")
        df_h = carregar(LINK_HISTORICO)
        saidas = df_h[df_h['acao'] == 'SAIDA']
        if not saidas.empty:
            top_saidas = saidas.groupby('produto')['quantidade'].sum().reset_index()
            fig = px.bar(top_saidas, x='produto', y='quantidade', title="Equipamentos com mais Saída", color_discrete_sequence=['#FF8C00'])
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Ainda não há dados de saídas para gerar estatísticas.")

    # 📦 ESTOQUE
    elif menu == "📦 Estoque":
        st.title("📦 Estoque Atual")
        df_p = carregar(LINK_PRODUTOS)
        # Alerta de Estoque Baixo
        baixo = df_p[df_p['quantidade'] <= df_p['alerta']]
        if not baixo.empty:
            st.warning(f"Atenção! {len(baixo)} itens estão com estoque crítico!")
        st.dataframe(df_p.style.highlight_between(left=0, right=5, subset=['quantidade'], color='#FFDAB9'), use_container_width=True)

    # 🔄 MOVIMENTAÇÃO (Entrada/Saída)
    elif menu == "🔄 Movimentação":
        st.title("🔄 Entrada e Saída de Itens")
        df_p = carregar(LINK_PRODUTOS)
        prod_selecionado = st.selectbox("Selecione o Produto", df_p['nome'])
        tipo_mov = st.radio("Tipo", ["ENTRADA", "SAIDA"])
        qtd_mov = st.number_input("Quantidade", min_value=1)
        if st.button("Confirmar Movimentação"):
            payload = {"tipo": "MOVIMENTACAO", "nome": prod_selecionado, "acao": tipo_mov, "valor": qtd_mov, "operador": st.session_state['user']}
            requests.post(URL_SCRIPTS, json=payload)
            st.success("Movimentação registrada!")
            st.rerun()

    # ➕ NOVO PRODUTO
    elif menu == "➕ Novo Produto":
        st.title("➕ Cadastrar Equipamento")
        nome = st.text_input("Nome")
        cat = st.selectbox("Categoria", ["Hardware", "Redes", "Periféricos", "Outros"])
        qtd = st.number_input("Qtd Inicial", min_value=0)
        pre = st.number_input("Preço Unitário", min_value=0.0)
        ale = st.number_input("Alerta Mínimo", min_value=1)
        if st.button("Salvar Produto"):
            payload = {"tipo": "PRODUTO", "id": 0, "nome": nome, "categoria": cat, "quantidade": qtd, "preco": pre, "alerta": ale, "operador": st.session_state['user']}
            requests.post(URL_SCRIPTS, json=payload)
            st.success("Cadastrado com sucesso!")

    # 👥 USUÁRIOS
    elif menu == "👥 Usuários":
        if st.session_state['nivel'] == 'admin':
            st.title("👥 Gerenciar Acessos")
            u_nome = st.text_input("Nome do Usuário")
            u_senha = st.text_input("Senha")
            u_nivel = st.selectbox("Nível", ["operador", "admin"])
            if st.button("Criar Usuário"):
                payload = {"tipo": "USUARIO", "usuario": u_nome.lower(), "senha": u_senha, "nivel": u_nivel}
                requests.post(URL_SCRIPTS, json=payload)
                st.success("Usuário criado!")
        else:
            st.error("Acesso restrito ao Administrador.")
