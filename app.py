import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime

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
            # Busca na sua tabela 'usuarios'
            res = supabase.table("usuarios").select("*").eq("usuario", u).eq("senha", p).execute()
            if res.data:
                st.session_state.logado = True
                st.session_state.usuario_nome = u
                st.session_state.nivel = res.data[0]['nivel']
                st.rerun()
            else:
                st.error("Usuário ou senha incorretos.")
    st.stop()

# --- MENU LATERAL ---
st.sidebar.title(f"👋 Olá, {st.session_state.usuario_nome.capitalize()}")
st.sidebar.info(f"Nível: {st.session_state.nivel.upper()}")

menu = st.sidebar.radio("Navegação", [
    "📊 Consultar Estoque", 
    "🔄 Entrada / Saída", 
    "🆕 Cadastrar Produto",
    "🔧 Correção de Produto",
    "📜 Histórico",
    "👥 Gerenciar Usuários"
])

if st.sidebar.button("Sair"):
    st.session_state.logado = False
    st.rerun()

# --- 1. CONSULTAR ESTOQUE ---
if menu == "📊 Consultar Estoque":
    st.title("📊 Consultar Estoque")
    
    try:
        # Busca na sua tabela 'name'
        dados = supabase.table("name").select("*").execute()
        df = pd.DataFrame(dados.data)
        
        if not df.empty:
            # Alertas de Estoque Mínimo (coluna 'alerta')
            alertas = df[df['quantidade'] <= df['alerta']]
            if not alertas.empty:
                for _, item in alertas.iterrows():
                    st.warning(f"🚨 **ALERTA:** O produto **{item['nome']}** atingiu o nível crítico ({item['quantidade']} em estoque / Mínimo: {item['alerta']})")

            st.divider()
            busca = st.text_input("🔍 Buscar por nome ou categoria")
            if busca:
                df = df[df['nome'].str.contains(busca, case=False) | df['categoria'].str.contains(busca, case=False)]
            
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("O estoque está vazio.")
    except Exception as e:
        st.error(f"Erro ao carregar dados: {e}")

# --- 2. ENTRADA / SAÍDA (MOVIMENTAÇÃO) ---
elif menu == "🔄 Entrada / Saída":
    st.title("🔄 Movimentação de Estoque")
    
    res = supabase.table("name").select("id, nome, quantidade").execute()
    if res.data:
        produtos_lista = {f"{p['nome']} (Atual: {p['quantidade']})": p for p in res.data}
        escolha = st.selectbox("Selecione o produto", list(produtos_lista.keys()))
        prod_sel = produtos_lista[escolha]
        
        col1, col2 = st.columns(2)
        with col1:
            qtd_mov = st.number_input("Quantidade", min_value=1, step=1)
        with col2:
            tipo = st.radio("Operação", ["Entrada (Compra)", "Saída (Uso)"])

        if st.button("Confirmar Movimentação"):
            nova_qtd = prod_sel['quantidade'] + qtd_mov if tipo == "Entrada (Compra)" else prod_sel['quantidade'] - qtd_mov
            
            if nova_qtd < 0:
                st.error("❌ Erro: Saldo insuficiente para realizar esta saída!")
            else:
                # Atualiza estoque
                supabase.table("name").update({"quantidade": nova_qtd}).eq("id", prod_sel['id']).execute()
                
                # Registra na tabela 'historico' (conforme sua imagem)
                supabase.table("historico").insert({
                    "operador": st.session_state.usuario_nome,
                    "acao": tipo,
                    "produto": prod_sel['nome'],
                    "quantidade": qtd_mov,
                    "data": datetime.now().isoformat()
                }).execute()
                
                st.success(f"✅ Movimentação de {tipo} concluída!")
                st.rerun()
    else:
        st.warning("Cadastre produtos primeiro.")

# --- 3. CADASTRAR PRODUTO ---
elif menu == "🆕 Cadastrar Produto":
    st.title("🆕 Cadastrar Novo Produto")
    with st.form("form_cadastro"):
        nome = st.text_input("Nome do Produto")
        cat = st.text_input("Categoria")
        qtd = st.number_input("Quantidade Inicial", min_value=0)
        preco = st.number_input("Preço Unitário (R$)", min_value=0.0, format="%.2f")
        alerta = st.number_input("Estoque Mínimo (Alerta)", min_value=1)
        
        if st.form_submit_button("Salvar no Banco"):
            if nome:
                supabase.table("name").insert({
                    "nome": nome, "categoria": cat, "quantidade": qtd, "preco": preco, "alerta": alerta
                }).execute()
                st.success("✨ Produto cadastrado com sucesso!")
            else:
                st.error("O nome é obrigatório.")

# --- 4. CORREÇÃO DE PRODUTO (RESTRITO ADMIN) ---
elif menu == "🔧 Correção de Produto":
    st.title("🔧 Correção de Dados")
    if st.session_state.nivel != "admin":
        st.error("🚫 Acesso negado. Apenas Administradores podem corrigir dados cadastrais.")
    else:
        res = supabase.table("name").select("*").execute()
        if res.data:
            df_edit = pd.DataFrame(res.data)
            escolha = st.selectbox("Selecione o produto para editar", df_edit['nome'].tolist())
            item = df_edit[df_edit['nome'] == escolha].iloc[0]

            with st.form("edit_form"):
                n_nome = st.text_input("Nome", value=item['nome'])
                n_cat = st.text_input("Categoria", value=item['categoria'])
                n_preco = st.number_input("Preço", value=float(item['preco']))
                n_alerta = st.number_input("Alerta Mínimo", value=int(item['alerta']))
                
                if st.form_submit_button("Atualizar Cadastro"):
                    supabase.table("name").update({
                        "nome": n_nome, "categoria": n_cat, "preco": n_preco, "alerta": n_alerta
                    }).eq("id", item['id']).execute()
                    st.success("✅ Dados atualizados!")
                    st.rerun()

# --- 5. HISTÓRICO ---
elif menu == "📜 Histórico":
    st.title("📜 Histórico de Movimentações")
    res = supabase.table("historico").select("*").order("data", desc=True).execute()
    if res.data:
        st.dataframe(pd.DataFrame(res.data), use_container_width=True, hide_index=True)
    else:
        st.info("Nenhuma movimentação registrada ainda.")

# --- 6. GERENCIAR USUÁRIOS (RESTRITO ADMIN) ---
elif menu == "👥 Gerenciar Usuários":
    st.title("👥 Gestão de Usuários")
    if st.session_state.nivel != "admin":
        st.error("🚫 Acesso restrito ao Administrador.")
    else:
        with st.expander("➕ Adicionar Novo Usuário"):
            nu = st.text_input("Nome de Usuário").strip().lower()
            ns = st.text_input("Senha Provisória")
            nv = st.selectbox("Nível de Acesso", ["comum", "admin"])
            if st.button("Criar Conta"):
                supabase.table("usuarios").insert({"usuario": nu, "senha": ns, "nivel": nv}).execute()
                st.success("Usuário criado!")

        st.subheader("Usuários do Sistema")
        u_dados = supabase.table("usuarios").select("id, usuario, nivel").execute()
        st.table(pd.DataFrame(u_dados.data))
