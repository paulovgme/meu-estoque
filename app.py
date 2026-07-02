import streamlit as st
import pandas as pd
import requests
import plotly.express as px

# --- CONFIGURAÇÃO DOS LINKS (SUBSTITUA PELOS SEUS) ---
# Certifique-se de que os links abaixo terminam com 'output=csv'
LINK_USUARIOS = "https://docs.google.com/spreadsheets/d/e/2PACX-1vR66hMMGy2uGkRwwHAAW_UL9tEq33eJe4gvY-RiI7BUuQMg2-Pmk7L8z6Jv17rQ5DvVEq0CtTPBPdnP/pub?gid=0&single=true&output=csv"
LINK_PRODUTOS = "https://docs.google.com/spreadsheets/d/e/2PACX-1vR66hMMGy2uGkRwwHAAW_UL9tEq33eJe4gvY-RiI7BUuQMg2-Pmk7L8z6Jv17rQ5DvVEq0CtTPBPdnP/pub?gid=622782364&single=true&output=csv"
LINK_HISTORICO = "https://docs.google.com/spreadsheets/d/e/2PACX-1vR66hMMGy2uGkRwwHAAW_UL9tEq33eJe4gvY-RiI7BUuQMg2-Pmk7L8z6Jv17rQ5DvVEq0CtTPBPdnP/pub?gid=289837026&single=true&output=csv"
URL_SCRIPTS = "https://script.google.com/macros/s/AKfycbySCqqo0cAYYCy2nNvdKPG-OsrGvz_youwQQmxWt0GRNOMRxeUrwDaMhrNnXv67MQ5l/exec"

# Configurações Iniciais
st.set_page_config(page_title="Ti Ercal - Gestão", page_icon="🧡", layout="wide")

# --- ESTILO VISUAL (LARANJA E BRANCO) ---
st.markdown("""
    <style>
    .stApp { background-color: white; }
    .stButton>button { background-color: #FF8C00; color: white; border-radius: 8px; width: 100%; font-weight: bold; }
    .stMetric { background-color: #FFF5EE; padding: 15px; border-radius: 10px; border-left: 5px solid #FF8C00; }
    h1, h2, h3 { color: #FF8C00 !important; }
    div[data-testid="stExpander"] { border: 1px solid #FF8C00; }
    </style>
    """, unsafe_allow_html=True)

# Função para carregar dados de forma limpa
@st.cache_data(ttl=10) # Atualiza a cada 10 segundos
def carregar_dados(url):
    df = pd.read_csv(url)
    df.columns = df.columns.str.strip().str.lower()
    return df

# Inicialização de variáveis de sessão
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

# --- TELA DE LOGIN ---
if not st.session_state['logged_in']:
    st.title("🧡 Ti Ercal - Sistema de Gestão")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("form_login"):
            u = st.text_input("Usuário").strip().lower()
            p = st.text_input("Senha", type="password").strip()
            if st.form_submit_button("Acessar Sistema"):
                try:
                    df_u = carregar_dados(LINK_USUARIOS)
                    valido = df_u[(df_u['usuario'].astype(str) == u) & (df_u['senha'].astype(str) == p)]
                    if not valido.empty:
                        st.session_state['logged_in'] = True
                        st.session_state['user'] = u
                        st.session_state['nivel'] = valido.iloc[0]['nivel']
                        st.rerun()
                    else:
                        st.error("login invalido")
                except Exception as e:
                    st.error(f"Erro ao conectar ao banco de usuários: {e}")

# --- SISTEMA APÓS LOGIN ---
else:
    st.sidebar.header(f"Olá, {st.session_state['user'].capitalize()}")
    menu = st.sidebar.radio("Navegação", ["📊 Estatísticas", "📦 Estoque Atual", "🔄 Movimentação", "➕ Novo Produto", "👥 Usuários", "🚪 Sair"])

    if menu == "🚪 Sair":
        st.session_state['logged_in'] = False
        st.rerun()

    # --- ABA ESTATÍSTICAS ---
    if menu == "📊 Estatísticas":
        st.title("📊 Desempenho de Saídas")
        try:
            df_h = carregar_dados(LINK_HISTORICO)
            saidas = df_h[df_h['acao'] == 'SAIDA']
            if not saidas.empty:
                # Soma as saídas por produto
                estat = saidas.groupby('produto')['quantidade'].sum().reset_index()
                fig = px.bar(estat, x='produto', y='quantidade', title="Equipamentos com mais Saídas", color_discrete_sequence=['#FF8C00'])
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Nenhuma saída registrada no histórico ainda.")
        except:
            st.warning("Publique a aba 'historico' como CSV para ver os gráficos.")

    # --- ABA ESTOQUE ---
    elif menu == "📦 Estoque Atual":
        st.title("📦 Controle de Estoque Atual")
        try:
            df_p = carregar_dados(LINK_PRODUTOS)
            
            # Ajuste de segurança para colunas de alerta
            if 'quantidade' in df_p.columns and 'alerta' in df_p.columns:
                df_p['quantidade'] = pd.to_numeric(df_p['quantidade'], errors='coerce').fillna(0)
                df_p['alerta'] = pd.to_numeric(df_p['alerta'], errors='coerce').fillna(0)
                
                baixo = df_p[df_p['quantidade'] <= df_p['alerta']]
                if not baixo.empty:
                    st.error(f"🚨 ALERTA: {len(baixo)} itens com estoque crítico!")
                    st.dataframe(baixo[['nome', 'quantidade', 'alerta']], hide_index=True)

            st.divider()
            st.dataframe(df_p, use_container_width=True, hide_index=True)
            
            if st.button("🔄 Sincronizar Agora"):
                st.cache_data.clear()
                st.rerun()
        except Exception as e:
            st.error(f"Erro ao carregar estoque: {e}")

    # --- ABA MOVIMENTAÇÃO ---
    elif menu == "🔄 Movimentação":
        st.title("🔄 Registro de Entrada/Saída")
        df_p = carregar_dados(LINK_PRODUTOS)
        with st.form("mov_form"):
            prod = st.selectbox("Selecione o Equipamento", df_p['nome'].unique())
            tipo = st.radio("Operação", ["ENTRADA", "SAIDA"])
            qtd = st.number_input("Quantidade", min_value=1, step=1)
            if st.form_submit_button("Confirmar Registro"):
                payload = {"tipo": "MOVIMENTACAO", "nome": prod, "acao": tipo, "valor": qtd, "operador": st.session_state['user']}
                r = requests.post(URL_SCRIPTS, json=payload)
                st.success("Registrado com sucesso na Planilha!")
                st.balloons()

    # --- ABA NOVO PRODUTO ---
    elif menu == "➕ Novo Produto":
        st.title("➕ Cadastrar Novo Equipamento")
        with st.form("cad_form"):
            n = st.text_input("Nome do Equipamento")
            c = st.selectbox("Categoria", ["Hardware", "Redes", "Periféricos", "Outros"])
            q = st.number_input("Estoque Inicial", min_value=0)
            p = st.number_input("Preço Unitário", min_value=0.0)
            a = st.number_input("Alerta Mínimo", min_value=1)
            if st.form_submit_button("Cadastrar no Sistema"):
                payload = {"tipo": "PRODUTO", "id": 0, "nome": n, "categoria": c, "quantidade": q, "preco": p, "alerta": a, "operador": st.session_state['user']}
                requests.post(URL_SCRIPTS, json=payload)
                st.success(f"O produto {n} foi enviado para a planilha!")

    # --- ABA USUÁRIOS ---
    elif menu == "👥 Usuários":
        if st.session_state['nivel'] == 'admin':
            st.title("👥 Gerenciar Acessos")
            with st.form("user_form"):
                new_u = st.text_input("Novo Usuário").lower()
                new_p = st.text_input("Senha")
                new_l = st.selectbox("Nível", ["operador", "admin"])
                if st.form_submit_button("Criar Usuário"):
                    requests.post(URL_SCRIPTS, json={"tipo": "USUARIO", "usuario": new_u, "senha": new_p, "nivel": new_l})
                    st.success("Usuário criado com sucesso!")
        else:
            st.error("Acesso restrito ao Administrador.")
