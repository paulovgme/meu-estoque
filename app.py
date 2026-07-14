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

# --- TELA: ENTRADA / SAÍDA (COM BUSCA) ---
elif menu == "🔄 Entrada / Saída":
    st.title("🔄 Movimentação de Itens")
    df = buscar_dados("produtos")
    
    if not df.empty:
        # Adicionado Campo de Busca para filtrar o Selectbox
        termo_busca = st.text_input("🔍 Digite para pesquisar o produto (Nome, Marca ou Categoria)").lower()
        
        # Filtra o dataframe com base na busca
        df_filtrado_mov = df[
            df['nome'].str.lower().str.contains(termo_busca) | 
            df['marca'].str.lower().str.contains(termo_busca) |
            df['categoria'].str.lower().str.contains(termo_busca)
        ]

        if not df_filtrado_mov.empty:
            # Opções baseadas no filtro
            opcoes = {f"{p['nome']} - {p['marca']} ({p['categoria']}) | Qtd Atual: {p['quantidade']}": p for _, p in df_filtrado_mov.iterrows()}
            escolha = st.selectbox("Selecione o produto na lista", list(opcoes.keys()))
            item_sel = opcoes[escolha]
            
            st.divider()
            col1, col2 = st.columns(2)
            qtd_mov = col1.number_input(f"Quantidade para movimentar", min_value=1, step=1)
            tipo_op = col2.radio("Tipo de Operação", ["Entrada (Compra/Reposição)", "Saída (Baixa/Uso)"])
            
            if st.button("Confirmar Movimentação", use_container_width=True, type="primary"):
                # Cálculo da nova quantidade
                if "Entrada" in tipo_op:
                    nova_qtd = item_sel['quantidade'] + qtd_mov
                else:
                    nova_qtd = item_sel['quantidade'] - qtd_mov

                if nova_qtd < 0:
                    st.error(f"❌ Erro: A saída de {qtd_mov} unidades deixaria o estoque negativo (Atual: {item_sel['quantidade']}).")
                else:
                    try:
                        # Atualiza a tabela de produtos
                        supabase.table("produtos").update({"quantidade": int(nova_qtd)}).eq("id", item_sel['id']).execute()
                        
                        # Registra no histórico
                        supabase.table("historico").insert({
                            "operador": st.session_state.user, 
                            "acao": tipo_op, 
                            "produto": item_sel['nome'], 
                            "quantidade": int(qtd_mov), 
                            "data": datetime.now().isoformat()
                        }).execute()
                        
                        st.success(f"✅ Movimentação realizada! Novo estoque de {item_sel['nome']}: {nova_qtd}")
                        st.balloons()
                        # Pequeno delay para o usuário ver a mensagem antes de recarregar
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao processar: {e}")
        else:
            st.warning("Nenhum produto encontr
