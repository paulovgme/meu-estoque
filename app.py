import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime

# --- 1. CONFIGURAÇÕES INICIAIS ---
st.set_page_config(page_title="Sistema Ti - Estoque", page_icon="📦", layout="wide")

# --- 2. BLINDAGEM AGRESSIVA CONTRA GOOGLE TRANSLATE ---
st.markdown("""
    <style>
        .notranslate { translate: no !important; }
        #google-cache-hdr, .goog-te-banner-frame, .skiptranslate, .goog-te-menu-value { display: none !important; }
        body { top: 0px !important; }
    </style>
    <meta name="google" content="notranslate">
    <script>
        document.documentElement.lang = 'pt-br';
        document.documentElement.setAttribute('translate', 'no');
        const observer = new MutationObserver((mutations) => {
            if (document.documentElement.classList.contains('translated-ltr') || 
                document.documentElement.classList.contains('translated-rtl')) {
                window.location.reload();
            }
        });
        observer.observe(document.documentElement, { attributes: true });
    </script>
""", unsafe_allow_html=True)

st.markdown('<div class="notranslate">', unsafe_allow_html=True)

# --- 3. CONEXÃO COM SUPABASE ---
@st.cache_resource
def get_supabase() -> Client:
    return create_client(st.secrets["URL_BANCO"], st.secrets["CHAVE_BANCO"])

supabase = get_supabase()

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
    try:
        res = supabase.table("produtos").select("*").execute()
        df = pd.DataFrame(res.data)
        if not df.empty:
            alertas = df[df['quantidade'] <= df['alerta']]
            if not alertas.empty:
                for _, item in alertas.iterrows():
                    st.warning(f"🚨 **ALERTA:** {item['nome']} está baixo ({item['quantidade']} un).")
            st.divider()
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("Estoque vazio.")
    except Exception as e:
        st.error(f"Erro: {e}")

# --- 2. ENTRADA / SAÍDA ---
elif menu == "🔄 Entrada / Saída":
    st.title("🔄 Movimentação de Itens")
    try:
        res = supabase.table("produtos").select("id, nome, quantidade").execute()
        if res.data:
            prods = {f"{p['nome']} (Atual: {p['quantidade']})": p for p in res.data}
            escolha = st.selectbox("Selecione o produto", list(prods.keys()))
            item_sel = prods[escolha]
            col1, col2 = st.columns(2)
            qtd_mov = col1.number_input("Quantidade", min_value=1, step=1)
            tipo_op = col2.radio("Operação", ["Entrada (Compra)", "Saída (Baixa)"])
            if st.button("Confirmar Movimentação"):
                nova_qtd = item_sel['quantidade'] + qtd_mov if "Entrada" in tipo_op else item_sel['quantidade'] - qtd_mov
                if nova_qtd < 0:
                    st.error("❌ Saldo insuficiente!")
                else:
                    supabase.table("produtos").update({"quantidade": int(nova_qtd)}).eq("id", item_sel['id']).execute()
                    supabase.table("historico").insert({
                        "operador": st.session_state.user, "acao": tipo_op,
                        "produto": item_sel['nome'], "quantidade": int(qtd_mov),
                        "data": datetime.now().isoformat()
                    }).execute()
                    st.success("✅ Estoque atualizado!")
                    st.rerun()
    except Exception as e:
        st.error(f"Erro: {e}")

# --- 3. CADASTRAR PRODUTO ---
elif menu == "🆕 Cadastrar Produto":
    st.title("🆕 Cadastro de Novo Produto")
    with st.form("form_novo"):
        nome = st.text_input("Nome do Produto")
        categoria = st.text_input("Categoria")
        qtd = st.number_input("Quantidade Inicial", min_value=0)
        preco = st.number_input("Preço Unitário", min_value=0.0)
        alerta = st.number_input("Alerta Mínimo", min_value=1)
        if st.form_submit_button("Cadastrar"):
            if nome:
                supabase.table("produtos").insert({
                    "nome": nome, "categoria": categoria, "quantidade": int(qtd), 
                    "preco": float(preco), "alerta": int(alerta)
                }).execute()
                st.success("✨ Cadastrado!")
            else: st.error("Nome obrigatório!")

# --- 4. CORREÇÃO E EXCLUSÃO (ADMIN) ---
elif menu == "🔧 Correção e Exclusão (Admin)":
    st.title("🔧 Administração de Produtos")
    if st.session_state.nivel != "admin":
        st.error("🚫 Acesso restrito a Administradores.")
    else:
        res = supabase.table("produtos").select("*").execute()
        if res.data:
            df_edit = pd.DataFrame(res.data)
            
            # --- PARTE DE EDIÇÃO ---
            st.subheader("📝 Editar Dados")
            sel_prod = st.selectbox("Selecione para editar", df_edit['nome'].tolist(), key="edit_sel")
            dados_p = df_edit[df_edit['nome'] == sel_prod].iloc[0]
            with st.form("edit_form"):
                n_nome = st.text_input("Nome", value=dados_p['nome'])
                n_cat = st.text_input("Categoria", value=dados_p['categoria'])
                n_preco = st.number_input("Preço", value=float(dados_p['preco']))
                n_alerta = st.number_input("Alerta", value=int(dados_p['alerta']))
                if st.form_submit_button("Salvar Alterações"):
                    supabase.table("produtos").update({
                        "nome": n_nome, "categoria": n_cat, "preco": n_preco, "alerta": n_alerta
                    }).eq("id", dados_p['id']).execute()
                    st.success("✅ Atualizado!")
                    st.rerun()

            st.divider()

            # --- PARTE DE EXCLUSÃO ---
            st.subheader("🗑️ Excluir Produto")
            st.warning("Atenção: A exclusão é permanente e não pode ser desfeita.")
            sel_del = st.selectbox("Selecione o produto para EXCLUIR", df_edit['nome'].tolist(), key="del_sel")
            item_del = df_edit[df_edit['nome'] == sel_del].iloc[0]
            
            confirmar_del = st.checkbox(f"Eu confirmo que desejo excluir o produto: {sel_del}")
            if st.button("❌ EXCLUIR PERMANENTEMENTE"):
                if confirmar_del:
                    supabase.table("produtos").delete().eq("id", item_sel_id := item_del['id']).execute()
                    st.success(f"Produto {sel_del} removido do sistema.")
                    st.rerun()
                else:
                    st.error("Por favor, marque a caixa de confirmação para excluir.")

# --- 5. HISTÓRICO ---
elif menu == "📜 Histórico Geral":
    st.title("📜 Histórico de Movimentações")
    res = supabase.table("historico").select("*").order("data", desc=True).execute()
    if res.data:
        st.dataframe(pd.DataFrame(res.data), use_container_width=True, hide_index=True)

# --- 6. GERENCIAR USUÁRIOS (ADMIN) ---
elif menu == "👥 Gerenciar Usuários":
    st.title("👥 Gestão de Usuários")
    if st.session_state.nivel != "admin":
        st.error("🚫 Acesso restrito.")
    else:
        # Adicionar Usuário
        with st.expander("➕ Adicionar Novo Usuário"):
            nu = st.text_input("Nome de Usuário").lower()
            ns = st.text_input("Senha")
            nv = st.selectbox("Nível", ["comum", "admin"])
            if st.button("Criar Usuário"):
                supabase.table("usuarios").insert({"usuario": nu, "senha": ns, "nivel": nv}).execute()
                st.success("Criado!")
        
        st.divider()
        
        # Listar e Excluir Usuários
        st.subheader("👥 Usuários Atuais e Remoção")
        res_u = supabase.table("usuarios").select("id, usuario, nivel").execute()
        if res_u.data:
            df_u = pd.DataFrame(res_u.data)
            st.table(df_u)

            # Lógica de exclusão de usuário
            user_del_lista = df_u[df_u['usuario'] != st.session_state.user]['usuario'].tolist()
            if user_del_lista:
                u_para_remover = st.selectbox("Selecione um usuário para remover", user_del_lista)
                id_u_del = df_u[df_u['usuario'] == u_para_remover].iloc[0]['id']
                
                confirma_u = st.checkbox(f"Confirmar remoção do acesso de: {u_para_remover}")
                if st.button("🗑️ Remover Acesso"):
                    if confirma_u:
                        supabase.table("usuarios").delete().eq("id", id_u_del).execute()
                        st.success(f"Usuário {u_para_remover} excluído.")
                        st.rerun()
                    else:
                        st.error("Marque a confirmação para remover.")
            else:
                st.info("Não há outros usuários para remover além de você.")

st.markdown('</div>', unsafe_allow_html=True)
