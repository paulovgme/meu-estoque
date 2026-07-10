import streamlit as st
import pandas as pd
import plotly.express as px
from st_supabase_connection import SupabaseConnection

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Ti - Estoque Profissional", page_icon="🔥", layout="wide")

# Conecta ao Supabase (usa as chaves que você colocou nos Secrets do Streamlit)
conn = st.connection("supabase", type=SupabaseConnection)

# --- 2. ESTILO VISUAL (MANTENDO O SEU PADRÃO) ---
st.markdown("""
    <style>
    .stApp { background-color: white; }
    .stButton>button { background-color: #FF8C00; color: white; border-radius: 8px; width: 100%; font-weight: bold; }
    h1, h2, h3 { color: #FF8C00 !important; }
    .stMetric { background-color: #FFF5EE; padding: 15px; border-radius: 10px; border-left: 5px solid #FF8C00; }
    </style>
    """, unsafe_allow_html=True)

# Função para carregar dados do banco de forma rápida
def carregar_dados(tabela):
    res = conn.query("*", table=tabela).execute()
    return pd.DataFrame(res.data)

if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

# --- 3. LOGIN ---
if not st.session_state['logged_in']:
    st.title("🔥 Ti - Sistema de Gestão")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("form_login"):
            u = st.text_input("Usuário").strip().lower()
            p = st.text_input("Senha", type="password").strip()
            if st.form_submit_button("Acessar Sistema"):
                # Busca o usuário diretamente no Banco de Dados
                res = conn.query("*", table="usuarios").eq("usuario", u).eq("senha", p).execute()
                
                if res.data: # Se encontrou alguém com esse login e senha
                    st.session_state['logged_in'] = True
                    st.session_state['user'] = u
                    st.session_state['nivel'] = res.data[0]['nivel'].strip().lower()
                    st.rerun()
                else:
                    st.error("Usuário ou senha incorretos")

# --- 4. SISTEMA LOGADO ---
else:
    # Menu baseado no nível de acesso
    if st.session_state['nivel'] == 'admin':
        opcoes = ["📊 Estatísticas", "📦 Estoque Atual", "🔄 Movimentação", "➕ Novo Produto", "🛠️ Ajustar Produto", "👥 Usuários", "🚪 Sair"]
    else:
        opcoes = ["📊 Estatísticas", "📦 Estoque Atual", "🔄 Movimentação", "➕ Novo Produto", "🚪 Sair"]
    
    menu = st.sidebar.radio(f"Olá, {st.session_state['user'].capitalize()}", opcoes)

    if menu == "🚪 Sair":
        st.session_state['logged_in'] = False
        st.rerun()

    # --- ABA ESTATÍSTICAS ---
    if menu == "📊 Estatísticas":
        st.title("📊 Desempenho de Saídas")
        df_h = carregar_dados("historico")
        if not df_h.empty:
            saidas = df_h[df_h['acao'].str.upper() == 'SAIDA']
            if not saidas.empty:
                estat = saidas.groupby('produto')['quantidade'].sum().reset_index()
                st.plotly_chart(px.bar(estat, x='produto', y='quantidade', color_discrete_sequence=['#FF8C00']), use_container_width=True)
            else: st.info("Ainda não há registros de saída no histórico.")

    # --- ABA ESTOQUE ---
    elif menu == "📦 Estoque Atual":
        st.title("📦 Controle de Estoque")
        df_p = carregar_dados("produtos")
        if not df_p.empty:
            # Verifica Alertas
            baixo = df_p[df_p['quantidade'] <= df_p['alerta']]
            if not baixo.empty:
                st.error(f"🚨 ATENÇÃO: {len(baixo)} itens estão com estoque crítico!")
            
            st.dataframe(df_p, use_container_width=True, hide_index=True)
            if st.button("🔄 Atualizar Dados"):
                st.rerun()

    # --- ABA MOVIMENTAÇÃO ---
    elif menu == "🔄 Movimentação":
        st.title("🔄 Registro de Entrada/Saída")
        df_p = carregar_dados("produtos")
        
        if not df_p.empty:
            with st.form("mov"):
                prod = st.selectbox("Equipamento", df_p['nome'].unique())
                tipo = st.radio("Operação", ["ENTRADA", "SAIDA"])
                qtd = st.number_input("Quantidade", min_value=1)
                
                if st.form_submit_button("Confirmar"):
                    # 1. Pega a quantidade atual do banco
                    item_atual = df_p[df_p['nome'] == prod].iloc[0]
                    qtd_atual = int(item_atual['quantidade'])
                    
                    # 2. Calcula nova quantidade
                    nova_qtd = (qtd_atual + qtd) if tipo == "ENTRADA" else (qtd_atual - qtd)
                    
                    # 3. Atualiza no Banco (Tabela Produtos)
                    conn.table("produtos").update({"quantidade": nova_qtd}).eq("nome", prod).execute()
                    
                    # 4. Grava no Histórico
                    conn.table("historico").insert({
                        "operador": st.session_state['user'],
                        "acao": tipo,
                        "produto": prod,
                        "quantidade": qtd
                    }).execute()
                    
                    st.success(f"Movimentação de {prod} realizada com sucesso!")
                    st.rerun()
        else:
            st.warning("Nenhum produto cadastrado para movimentar.")

    # --- ABA NOVO PRODUTO ---
    elif menu == "➕ Novo Produto":
        st.title("➕ Cadastrar Equipamento")
        with st.form("cad"):
            n = st.text_input("Nome do Produto")
            c = st.selectbox("Categoria", ["TI", "Infra", "Redes", "Outros"])
            q = st.number_input("Estoque Inicial", min_value=0)
            p = st.number_input("Preço", min_value=0.0)
            a = st.number_input("Ponto de Alerta (Mínimo)", min_value=1)
            
            if st.form_submit_button("Salvar no Banco"):
                if n:
                    conn.table("produtos").insert({
                        "nome": n, "categoria": c, "quantidade": q, "preco": p, "alerta": a
                    }).execute()
                    st.success(f"Produto '{n}' cadastrado com sucesso!")
                else:
                    st.error("O nome do produto é obrigatório.")

    # --- ABA AJUSTAR PRODUTO (SÓ ADMIN) ---
    elif menu == "🛠️ Ajustar Produto":
        st.title("🛠️ Editar Produto Existente")
        df_p = carregar_dados("produtos")
        
        if not df_p.empty:
            prod_edit = st.selectbox("Selecione o produto", df_p['nome'].unique())
            novo_nome = st.text_input("Novo nome (ou mantenha o atual)")
            nova_cat = st.selectbox("Nova Categoria", ["TI", "Infra", "Redes", "Outros"])
            
            if st.button("Aplicar Alterações"):
                conn.table("produtos").update({
                    "nome": novo_nome if novo_nome else prod_edit,
                    "categoria": nova_cat
                }).eq("nome", prod_edit).execute()
                st.success("Produto atualizado!")
                st.rerun()

    # --- ABA USUÁRIOS (SÓ ADMIN) ---
    elif menu == "👥 Usuários":
        st.title("👥 Gestão de Acessos")
        
        with st.expander("➕ Criar Novo Usuário"):
            with st.form("u"):
                nu = st.text_input("Nome de Usuário").lower()
                ns = st.text_input("Senha")
                nl = st.selectbox("Nível", ["operador", "admin"])
                if st.form_submit_button("Salvar Usuário"):
                    conn.table("usuarios").insert({"usuario": nu, "senha": ns, "nivel": nl}).execute()
                    st.success("Novo usuário criado!")
        
        st.divider()
        st.subheader("Usuários Atuais")
        df_u = carregar_dados("usuarios")
        st.table(df_u[['usuario', 'nivel']])
