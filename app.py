import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime

# --- 1. CONFIGURAÇÕES INICIAIS (DEVE SER A PRIMEIRA LINHA) ---
st.set_page_config(page_title="Sistema Ti - Estoque", page_icon="📦", layout="wide")

# --- 2. BLINDAGEM AGRESSIVA CONTRA GOOGLE TRANSLATE ---
# Isso evita o erro "removeChild" impedindo que o navegador traduza a página
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
        
        // Recarrega se detectar tentativa de tradução externa
        const observer = new MutationObserver((mutations) => {
            if (document.documentElement.classList.contains('translated-ltr') || 
                document.documentElement.classList.contains('translated-rtl')) {
                window.location.reload();
            }
        });
        observer.observe(document.documentElement, { attributes: true });
    </script>
""", unsafe_allow_html=True)

# Abre uma div geral que engloba o app todo para proteção extra
st.markdown('<div class="notranslate">', unsafe_allow_html=True)

# --- 3. CONEXÃO COM SUPABASE ---
@st.cache_resource
def get_supabase() -> Client:
    return create_client(st.secrets["URL_BANCO"], st.secrets["CHAVE_BANCO"])

supabase = get_supabase()

# --- 4. GERENCIAMENTO DE ESTADO ---
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
                    st.session_state.nivel = res.data[0]['nivel'] # 'admin' ou 'comum'
                    st.rerun()
                else:
                    st.error("Usuário ou senha inválidos.")
            except Exception as e:
                st.error(f"Erro de conexão: {e}")
    st.stop()

# --- MENU LATERAL ---
st.sidebar.title(f"👋 Olá, {st.session_state.user.capitalize()}")
st.sidebar.write(f"**Nível de Acesso:** {st.session_state.nivel.upper()}")

menu = st.sidebar.radio("Navegação", [
    "📊 Consultar Estoque", 
    "🔄 Entrada / Saída", 
    "🆕 Cadastrar Produto",
    "🔧 Correção (Admin)",
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
            # Alerta de Estoque Mínimo (coluna 'alerta')
            alertas = df[df['quantidade'] <= df['alerta']]
            if not alertas.empty:
                for _, item in alertas.iterrows():
                    st.warning(f"🚨 **ALERTA DE ESTOQUE:** O produto **{item['nome']}** está com {item['quantidade']} unidades (Mínimo: {item['alerta']})")

            st.divider()
            busca = st.text_input("🔍 Filtrar por nome ou categoria")
            if busca:
                df = df[df['nome'].str.contains(busca, case=False) | df['categoria'].str.contains(busca, case=False)]
            
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("O estoque está vazio.")
    except Exception as e:
        st.error(f"Erro ao carregar dados: {e}")

# --- 2. ENTRADA / SAÍDA (MOVIMENTAÇÃO) ---
elif menu == "🔄 Entrada / Saída":
    st.title("🔄 Movimentação de Itens")
    try:
        res = supabase.table("produtos").select("id, nome, quantidade").execute()
        if res.data:
            lista_prods = {f"{p['nome']} (Atual: {p['quantidade']})": p for p in res.data}
            escolha = st.selectbox("Selecione o produto", list(lista_prods.keys()))
            item_sel = lista_prods[escolha]
            
            col1, col2 = st.columns(2)
            with col1:
                qtd_mov = st.number_input("Quantidade da Operação", min_value=1, step=1)
            with col2:
                tipo_op = st.radio("Tipo de Operação", ["Entrada (Compra)", "Saída (Baixa)"])

            if st.button("Confirmar Movimentação"):
                nova_qtd = item_sel['quantidade'] + qtd_mov if "Entrada" in tipo_op else item_sel['quantidade'] - qtd_mov
                
                if nova_qtd < 0:
                    st.error("❌ Erro: Saldo insuficiente para realizar esta saída!")
                else:
                    # 1. Atualiza o estoque na tabela 'produtos'
                    supabase.table("produtos").update({"quantidade": int(nova_qtd)}).eq("id", item_sel['id']).execute()
                    
                    # 2. Registra na tabela 'historico'
                    supabase.table("historico").insert({
                        "operador": st.session_state.user,
                        "acao": tipo_op,
                        "produto": item_sel['nome'],
                        "quantidade": int(qtd_mov),
                        "data": datetime.now().isoformat()
                    }).execute()
                    
                    st.success(f"✅ Sucesso! Nova quantidade de {item_sel['nome']}: {nova_qtd}")
                    st.rerun()
        else:
            st.warning("Nenhum produto cadastrado para movimentar.")
    except Exception as e:
        st.error(f"Erro na movimentação: {e}")

# --- 3. CADASTRAR NOVO PRODUTO ---
elif menu == "🆕 Cadastrar Produto":
    st.title("🆕 Cadastro de Novo Produto")
    with st.form("form_novo"):
        nome = st.text_input("Nome do Produto")
        categoria = st.text_input("Categoria")
        qtd_inicial = st.number_input("Quantidade Inicial", min_value=0, step=1)
        preco = st.number_input("Preço Unitário (R$)", min_value=0.0, format="%.2f")
        alerta = st.number_input("Ponto de Alerta (Mínimo)", min_value=1, step=1)
        
        if st.form_submit_button("Cadastrar Produto"):
            if nome:
                try:
                    supabase.table("produtos").insert({
                        "nome": nome, "categoria": categoria, 
                        "quantidade": int(qtd_inicial), "preco": float(preco), "alerta": int(alerta)
                    }).execute()
                    st.success("✨ Produto cadastrado com sucesso!")
                except Exception as e:
                    st.error(f"Erro no banco de dados: {e}")
            else:
                st.error("O nome do produto é obrigatório!")

# --- 4. CORREÇÃO (ADMIN) ---
elif menu == "🔧 Correção (Admin)":
    st.title("🔧 Correção de Dados Cadastrais")
    if st.session_state.nivel != "admin":
        st.error("🚫 Acesso Restrito. Apenas administradores podem corrigir nomes ou categorias.")
    else:
        try:
            res = supabase.table("produtos").select("*").execute()
            if res.data:
                df_corr = pd.DataFrame(res.data)
                sel_corr = st.selectbox("Selecione o item para corrigir", df_corr['nome'].tolist())
                dados_prod = df_corr[df_corr['nome'] == sel_corr].iloc[0]

                with st.form("edit_form"):
                    novo_nome = st.text_input("Nome", value=dados_prod['nome'])
                    nova_cat = st.text_input("Categoria", value=dados_prod['categoria'])
                    novo_preco = st.number_input("Preço", value=float(dados_prod['preco']))
                    novo_alerta = st.number_input("Alerta Mínimo", value=int(dados_prod['alerta']))
                    
                    if st.form_submit_button("Salvar Alterações"):
                        supabase.table("produtos").update({
                            "nome": novo_nome, "categoria": nova_cat, 
                            "preco": novo_preco, "alerta": novo_alerta
                        }).eq("id", dados_prod['id']).execute()
                        st.success("✅ Cadastro atualizado!")
                        st.rerun()
        except Exception as e:
            st.error(f"Erro: {e}")

# --- 5. HISTÓRICO GERAL ---
elif menu == "📜 Histórico Geral":
    st.title("📜 Histórico de Movimentações")
    try:
        res = supabase.table("historico").select("*").order("data", desc=True).execute()
        if res.data:
            st.dataframe(pd.DataFrame(res.data), use_container_width=True, hide_index=True)
        else:
            st.info("Nenhuma movimentação registrada.")
    except Exception as e:
        st.error(f"Erro ao carregar histórico: {e}")

# --- 6. GERENCIAR USUÁRIOS (ADMIN) ---
elif menu == "👥 Gerenciar Usuários":
    st.title("👥 Gestão de Usuários")
    if st.session_state.nivel != "admin":
        st.error("🚫 Acesso restrito ao administrador.")
    else:
        with st.expander("➕ Adicionar Novo Usuário"):
            nu = st.text_input("Nome de Usuário").strip().lower()
            ns = st.text_input("Senha")
            nv = st.selectbox("Nível de Acesso", ["comum", "admin"])
            if st.button("Salvar Novo Usuário"):
                try:
                    supabase.table("usuarios").insert({"usuario": nu, "senha": ns, "nivel": nv}).execute()
                    st.success("✅ Usuário criado!")
                except Exception as e:
                    st.error(f"Erro: {e}")

        st.subheader("Usuários Atuais")
        try:
            u_dados = supabase.table("usuarios").select("id, usuario, nivel").execute()
            st.table(pd.DataFrame(u_dados.data))
        except:
            st.write("Erro ao listar usuários.")

# Fecha a div de blindagem
st.markdown('</div>', unsafe_allow_html=True)
