import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime
import time
import io

# --- 1. CONFIGURAÇÕES DA PÁGINA ---
st.set_page_config(page_title="Sistema TI - Estoque Pro", page_icon="📦", layout="wide")

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
        res = supabase.table(tabela).select("*").execute()
        return pd.DataFrame(res.data)
    except Exception as e:
        st.error(f"Erro ao acessar {tabela}: {e}")
        return pd.DataFrame()

def formatar_data(data_iso):
    """Converte datas do banco para o padrão brasileiro DD/MM/AAAA HH:MM"""
    if pd.isna(data_iso) or not data_iso:
        return "N/A"
    try:
        # Trata formato ISO (ex: 2024-05-10T14:30:00)
        dt = pd.to_datetime(data_iso)
        return dt.strftime("%d/%m/%Y %H:%M")
    except:
        return str(data_iso)

# --- 4. CONTROLE DE ACESSO (LOGIN) ---
if 'logado' not in st.session_state:
    st.session_state.logado = False
    st.session_state.perms = {}
    st.session_state.user = None
    st.session_state.nome_real = None

if not st.session_state.logado:
    st.title("🔐 Acesso ao Sistema")
    with st.form("login_form"):
        u = st.text_input("Usuário (Login)").strip().lower()
        p = st.text_input("Senha", type="password").strip()
        if st.form_submit_button("Entrar", use_container_width=True):
            try:
                res = supabase.table("usuarios").select("*").eq("usuario", u).eq("senha", p).execute()
                if res.data:
                    user_data = res.data[0]
                    st.session_state.logado = True
                    st.session_state.user = u
                    st.session_state.nome_real = user_data.get('nome', u.capitalize())
                    st.session_state.perms = {
                        "nivel": user_data.get('nivel', 'comum'),
                        "consultar": user_data.get('can_consultar', True),
                        "movimentar": user_data.get('can_movimentar', False),
                        "cadastrar": user_data.get('can_cadastrar', False),
                        "admin": user_data.get('can_admin', False),
                        "historico": user_data.get('can_historico', False),
                        "usuarios": user_data.get('can_usuarios', False)
                    }
                    st.rerun()
                else:
                    st.error("Usuário ou senha inválidos.")
            except Exception as e:
                st.error(f"Erro de conexão: {e}")
    st.stop()

# --- 5. MENU LATERAL ---
st.sidebar.title(f"👋 Olá, {st.session_state.nome_real}")
st.sidebar.write(f"Nível: **{st.session_state.perms.get('nivel', 'comum').upper()}**")

opcoes_menu = []
if st.session_state.perms.get('consultar'): opcoes_menu.append("📊 Consultar Estoque")
if st.session_state.perms.get('movimentar'): opcoes_menu.append("🔄 Entrada / Saída")
if st.session_state.perms.get('cadastrar'):  opcoes_menu.append("🆕 Cadastrar Produto")
if st.session_state.perms.get('admin'):      opcoes_menu.append("🔧 Correção de Produtos")
if st.session_state.perms.get('historico'):  opcoes_menu.append("📜 Histórico e Relatórios")
if st.session_state.perms.get('usuarios'):   opcoes_menu.append("👥 Gerenciar Usuários")

menu = st.sidebar.radio("Navegação", opcoes_menu)

if st.sidebar.button("Sair / Logoff"):
    st.session_state.logado = False
    st.rerun()

# --- 6. TELAS DO SISTEMA ---

# --- CONSULTA DE ESTOQUE ---
if menu == "📊 Consultar Estoque":
    st.title("📊 Consultar Estoque")
    df = buscar_dados("produtos")
    if not df.empty:
        termo = st.text_input("🔍 Pesquisar por ID, Nome, Marca ou Modelo").lower()
        df_filtrado = df[
            df['nome'].str.lower().str.contains(termo, na=False) | 
            df['marca'].str.lower().str.contains(termo, na=False) |
            df['id'].astype(str).str.contains(termo, na=False) |
            df['modelo'].astype(str).str.lower().str.contains(termo, na=False)
        ]
        st.dataframe(df_filtrado, use_container_width=True, hide_index=True)

        if st.session_state.perms.get('admin'):
            st.divider()
            with st.expander("✏️ Edição Rápida de Produto"):
                lista_opcoes = {f"ID: {row['id']} | {row['nome']}": row['id'] for _, row in df_filtrado.iterrows()}
                if lista_opcoes:
                    sel_label = st.selectbox("Selecione o produto", list(lista_opcoes.keys()))
                    id_sel = lista_opcoes[sel_label]
                    p_dados = df[df['id'] == id_sel].iloc[0]
                    with st.form("quick_edit"):
                        c1, c2 = st.columns(2)
                        n_n = c1.text_input("Nome", value=p_dados['nome'])
                        n_m = c1.text_input("Marca", value=p_dados['marca'])
                        n_mod = c2.text_input("Modelo", value=str(p_dados.get('modelo', '')) if p_dados.get('modelo') else "")
                        n_cat = c2.text_input("Categoria", value=p_dados['categoria'])
                        if st.form_submit_button("Salvar Correção"):
                            supabase.table("produtos").update({"nome": n_n, "marca": n_m, "modelo": n_mod, "categoria": n_cat}).eq("id", id_sel).execute()
                            st.success("Produto corrigido com sucesso!")
                            time.sleep(1.5)
                            st.rerun()

# --- MOVIMENTAÇÃO (ENTRADA / SAÍDA COM CAMPO DE CHAMADO) ---
elif menu == "🔄 Entrada / Saída":
    st.title("🔄 Movimentação de Estoque")
    df = buscar_dados("produtos")
    if not df.empty:
        opcoes_mov = {f"ID: {p['id']} | {p['nome']} (Saldo atual: {p['quantidade']})": p for _, p in df.iterrows()}
        escolha = st.selectbox("Selecione o produto", list(opcoes_mov.keys()))
        item_sel = opcoes_mov[escolha]
        
        col1, col2 = st.columns(2)
        qtd_mov = col1.number_input("Quantidade", min_value=1, step=1)
        tipo_op = col2.radio("Tipo de Operação", ["Saída (Baixa)", "Entrada (Compra)"])
        
        # Campo de chamado é exibido obrigatoriamente quando for Saída
        num_chamado = ""
        if "Saída" in tipo_op:
            st.info("ℹ️ Para saídas de produtos, informe o número do chamado correspondente.")
            num_chamado = st.text_input("🎫 Número / Identificador do Chamado *", placeholder="Ex: #10452, INC-9932, OS 45").strip()
        else:
            num_chamado = st.text_input("📝 Observação / Nota de Entrada (Opcional)", placeholder="Ex: Compra NF-1234, Reposição").strip()

        st.write("")
        if st.button("Confirmar Movimentação", type="primary", use_container_width=True):
            # Validação para não permitir saída sem chamado
            if "Saída" in tipo_op and not num_chamado:
                st.error("⚠️ Atenção: Por favor, informe o número do chamado para realizar a saída do produto.")
            else:
                nova_qtd = item_sel['quantidade'] + qtd_mov if "Entrada" in tipo_op else item_sel['quantidade'] - qtd_mov
                
                if nova_qtd < 0:
                    st.error(f"Saldo insuficiente! Saldo atual é de apenas {item_sel['quantidade']} unidades.")
                else:
                    try:
                        # 1. Atualiza quantidade no produto
                        supabase.table("produtos").update({"quantidade": int(nova_qtd)}).eq("id", item_sel['id']).execute()
                        
                        # 2. Registra histórico detalhado com o chamado
                        dados_historico = {
                            "operador": st.session_state.nome_real,
                            "acao": tipo_op,
                            "produto": item_sel['nome'],
                            "quantidade": int(qtd_mov),
                            "chamado": num_chamado if num_chamado else ("Entrada / Compra" if "Entrada" in tipo_op else "Não informado"),
                            "data": datetime.now().isoformat()
                        }
                        supabase.table("historico").insert(dados_historico).execute()
                        
                        st.success(f"✅ Movimentação de {tipo_op} realizada com sucesso!")
                        time.sleep(1.5)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao registrar movimentação: {e}")

# --- CADASTRO DE PRODUTO ---
elif menu == "🆕 Cadastrar Produto":
    st.title("🆕 Novo Produto")
    with st.form("novo_p", clear_on_submit=True):
        n = st.text_input("Nome do Produto").strip()
        m = st.text_input("Marca")
        mod = st.text_input("Modelo")
        cat = st.text_input("Categoria")
        q = st.number_input("Qtd Inicial", min_value=0)
        a = st.number_input("Alerta Mínimo", min_value=1)
        if st.form_submit_button("Cadastrar"):
            if n:
                check = supabase.table("produtos").select("id").eq("nome", n).execute()
                if check.data: st.error("Produto já existe!")
                else:
                    supabase.table("produtos").insert({"nome":n, "marca":m, "modelo":mod, "categoria":cat, "quantidade":int(q), "alerta":int(a)}).execute()
                    st.success(f"Produto '{n}' cadastrado com sucesso!")
                    time.sleep(2)
                    st.rerun()
            else: st.error("Nome obrigatório")

# --- CORREÇÃO DE PRODUTOS ---
elif menu == "🔧 Correção de Produtos":
    st.title("🔧 Correção de Produtos")
    df = buscar_dados("produtos")
    if not df.empty:
        aba_c, aba_e = st.tabs(["📝 Corrigir Dados", "🚨 Excluir Produto"])
        
        with aba_c:
            dic_id = {f"ID: {r['id']} - {r['nome']}": r['id'] for _, r in df.iterrows()}
            sel_id = dic_id[st.selectbox("Selecione o ID para Corrigir", list(dic_id.keys()))]
            p = df[df['id'] == sel_id].iloc[0]
            with st.form("f_corr"):
                c1, c2 = st.columns(2)
                nc = c1.text_input("Nome", value=p['nome'])
                mc = c1.text_input("Marca", value=p['marca'])
                moc = c2.text_input("Modelo", value=str(p.get('modelo','')) if p.get('modelo') else "")
                cac = c2.text_input("Categoria", value=p['categoria'])
                alc = st.number_input("Alerta", value=int(p['alerta']))
                if st.form_submit_button("Salvar Alterações"):
                    supabase.table("produtos").update({"nome": nc, "marca": mc, "modelo": moc, "categoria": cac, "alerta": int(alc)}).eq("id", sel_id).execute()
                    st.success("Produto corrigido com sucesso!")
                    time.sleep(1.5)
                    st.rerun()
        
        with aba_e:
            st.subheader("Excluir Produto por ID")
            col_id, col_btn = st.columns([1, 4])
            busca_id = col_id.text_input("Digite a ID que deseja excluir").strip()
            buscar_click = col_btn.button("🔍 Buscar Produto")

            if buscar_click and busca_id:
                df_item = df[df['id'].astype(str) == busca_id]
                if not df_item.empty:
                    st.session_state.item_para_excluir = df_item.iloc[0]
                else:
                    st.session_state.item_para_excluir = None
                    st.error("Nenhum produto encontrado com este ID.")

            if 'item_para_excluir' in st.session_state and st.session_state.item_para_excluir is not None:
                item = st.session_state.item_para_excluir
                st.divider()
                st.markdown("""
                    <p style='color: #FF0000; font-size: 40px; font-weight: bold; text-align: center; line-height: 1.2; border: 4px solid #FF0000; padding: 15px; border-radius: 8px;'>
                        ESTA FUNÇÃO É IRREVERSÍVEL,<br>
                        FAVOR VERIFICAR COM ATENÇÃO ANTES DE EXCLUIR!
                    </p>
                """, unsafe_allow_html=True)
                
                st.subheader("📋 Conferência de Dados do Produto")
                c1, c2, c3 = st.columns(3)
                c1.write(f"**ID:** {item['id']}")
                c1.write(f"**Nome:** {item['nome']}")
                c2.write(f"**Marca:** {item['marca']}")
                c2.write(f"**Modelo:** {item.get('modelo', 'N/A')}")
                c3.write(f"**Categoria:** {item['categoria']}")
                c3.write(f"**Quantidade:** {item['quantidade']}")

                if st.button(f"⚠️ SIM, CONFIRMO A EXCLUSÃO DEFINITIVA DO ID {item['id']}", type="primary", use_container_width=True):
                    try:
                        supabase.table("produtos").delete().eq("id", item['id']).execute()
                        st.success(f"Produto ID {item['id']} excluído com sucesso!")
                        st.session_state.item_para_excluir = None
                        time.sleep(2)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao excluir: {e}")

# --- HISTÓRICO GERAL E RELATÓRIO DE SAÍDAS EM EXCEL ---
elif menu == "📜 Histórico e Relatórios":
    st.title("📜 Histórico e Relatórios")
    
    aba_hist, aba_relatorio = st.tabs(["📋 Histórico Completo", "📊 Relatório de Saídas (Excel)"])
    
    df_h = buscar_dados("historico")
    
    if not df_h.empty:
        # Garante que a coluna 'chamado' exista no DataFrame mesmo se houver registros antigos
        if 'chamado' not in df_h.columns:
            df_h['chamado'] = "N/A"
        df_h['chamado'] = df_h['chamado'].fillna("N/A")
        
        # Cria uma coluna de Data/Hora formatada bonita para o usuário
        df_h['data_formatada'] = df_h['data'].apply(formatar_data)
        
        # --- ABA 1: HISTÓRICO GERAL ---
        with aba_hist:
            st.subheader("Visão Geral das Movimentações")
            # Ordena por data decrescente
            df_exibicao = df_h.sort_values("data", ascending=False).copy()
            
            # Renomeia colunas para ficar amigável na tela
            df_tabela = df_exibicao[['data_formatada', 'produto', 'acao', 'quantidade', 'chamado', 'operador']].copy()
            df_tabela.columns = ['Data e Hora', 'Produto', 'Operação', 'Quantidade', 'Chamado / Ref', 'Operador']
            
            st.dataframe(df_tabela, use_container_width=True, hide_index=True)
            st.caption(f"Total de registros: {len(df_tabela)}")

        # --- ABA 2: RELATÓRIO DE SAÍDAS (EXCEL) ---
        with aba_relatorio:
            st.subheader("📊 Gerador de Relatório de Saídas por Produto e Chamado")
            st.write("Filtre as saídas para saber exatamente qual produto foi utilizado em qual chamado e gere o arquivo Excel:")
            
            # Filtra apenas saídas
            df_saidas = df_h[df_h['acao'].str.contains("Saída", na=False)].copy()
            
            if df_saidas.empty:
                st.warning("Nenhuma saída registrada até o momento.")
            else:
                # Filtros
                col_f1, col_f2 = st.columns(2)
                
                lista_produtos = ["Todos os Produtos"] + sorted(df_saidas['produto'].dropna().unique().tolist())
                produto_escolhido = col_f1.selectbox("Filtrar por Produto", lista_produtos)
                
                busca_chamado = col_f2.text_input("Filtrar por Número de Chamado (opcional)", placeholder="Digite parte do número do chamado").strip()
                
                # Aplicação dos filtros
                df_rel = df_saidas.copy()
                if produto_escolhido != "Todos os Produtos":
                    df_rel = df_rel[df_rel['produto'] == produto_escolhido]
                
                if busca_chamado:
                    df_rel = df_rel[df_rel['chamado'].astype(str).str.lower().str.contains(busca_chamado.lower(), na=False)]
                
                # Ordena por data mais recente
                df_rel = df_rel.sort_values("data", ascending=False)
                
                # Monta tabela final do relatório
                df_rel_final = pd.DataFrame({
                    "Produto": df_rel['produto'],
                    "Data e Hora da Saída": df_rel['data_formatada'],
                    "Quantidade": df_rel['quantidade'],
                    "Quem deu a Saída (Operador)": df_rel['operador'],
                    "Para qual Chamado foi a Saída": df_rel['chamado'],
                    "Operação": df_rel['acao']
                })
                
                st.dataframe(df_rel_final, use_container_width=True, hide_index=True)
                st.info(f"Total de saídas encontradas: **{len(df_rel_final)}**")
                
                # --- BOTÃO PARA BAIXAR EM EXCEL ---
                if not df_rel_final.empty:
                    # Gera o arquivo Excel em memória
                    buffer_excel = io.BytesIO()
                    with pd.ExcelWriter(buffer_excel, engine='openpyxl') as writer:
                        df_rel_final.to_excel(writer, index=False, sheet_name="Relatorio_Saidas")
                    
                    dados_excel = buffer_excel.getvalue()
                    
                    nome_arquivo = f"relatorio_saidas_{datetime.now().strftime('%d_%m_%Y_%H%M')}.xlsx"
                    
                    st.download_button(
                        label="📥 Baixar Relatório em Excel (.xlsx)",
                        data=dados_excel,
                        file_name=nome_arquivo,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        type="primary",
                        use_container_width=True
                    )
    else:
        st.info("Nenhuma movimentação registrada no histórico ainda.")

# --- USUÁRIOS ---
elif menu == "👥 Gerenciar Usuários":
    st.title("👥 Gestão de Usuários")
    aba_l, aba_a, aba_e, aba_d = st.tabs(["📋 Lista de Usuários", "➕ Novo Usuário", "✏️ Editar Usuário", "🗑️ Excluir Usuário"])
    df_u = buscar_dados("usuarios")

    with aba_l:
        if not df_u.empty:
            st.dataframe(df_u[['nome', 'usuario', 'nivel']], use_container_width=True, hide_index=True)

    with aba_a:
        with st.form("form_novo_usuario", clear_on_submit=True):
            new_nome = st.text_input("Nome Completo").strip()
            new_login = st.text_input("Login").lower().strip()
            new_senha = st.text_input("Senha", type="password")
            new_nivel = st.selectbox("Nível", ["comum", "administrador"])
            st.write("--- Permissões ---")
            col1, col2 = st.columns(2)
            p1 = col1.checkbox("Consultar", value=True)
            p2 = col1.checkbox("Movimentar")
            p3 = col1.checkbox("Cadastrar")
            p4 = col2.checkbox("Correção (Admin)")
            p5 = col2.checkbox("Histórico")
            p6 = col2.checkbox("Gerir Usuários")
            if st.form_submit_button("Criar Usuário"):
                if new_nome and new_login and new_senha:
                    supabase.table("usuarios").insert({
                        "nome": new_nome, "usuario": new_login, "senha": new_senha, "nivel": new_nivel,
                        "can_consultar": p1, "can_movimentar": p2, "can_cadastrar": p3,
                        "can_admin": p4, "can_historico": p5, "can_usuarios": p6
                    }).execute()
                    st.success(f"Usuário '{new_nome}' cadastrado com sucesso!")
                    time.sleep(2)
                    st.rerun()
                else: st.error("Preencha todos os campos!")

    with aba_e:
        if not df_u.empty:
            user_edit = st.selectbox("Escolha o usuário", df_u['usuario'].tolist(), format_func=lambda x: f"{x} ({df_u[df_u['usuario']==x]['nome'].values[0]})")
            u_sel = df_u[df_u['usuario'] == user_edit].iloc[0]
            with st.form("edit_u"):
                edit_nome = st.text_input("Nome Completo", value=u_sel.get('nome', ''))
                edit_senha = st.text_input("Nova Senha (vazio mantém)", type="password")
                niveis = ["comum", "administrador"]
                idx = 1 if u_sel['nivel'] == 'administrador' else 0
                edit_nivel = st.selectbox("Nível", niveis, index=idx)
                col1, col2 = st.columns(2)
                e1 = col1.checkbox("Consultar", value=bool(u_sel.get('can_consultar', True)))
                e2 = col1.checkbox("Movimentar", value=bool(u_sel.get('can_movimentar', False)))
                e3 = col1.checkbox("Cadastrar", value=bool(u_sel.get('can_cadastrar', False)))
                e4 = col2.checkbox("Correção (Admin)", value=bool(u_sel.get('can_admin', False)))
                e5 = col2.checkbox("Histórico", value=bool(u_sel.get('can_historico', False)))
                e6 = col2.checkbox("Gerir Usuários", value=bool(u_sel.get('can_usuarios', False)))
                if st.form_submit_button("Salvar Alterações"):
                    upd = {"nome": edit_nome, "nivel": edit_nivel, "can_consultar": e1, "can_movimentar": e2, "can_cadastrar": e3, "can_admin": e4, "can_historico": e5, "can_usuarios": e6}
                    if edit_senha: upd["senha"] = edit_senha
                    supabase.table("usuarios").update(upd).eq("usuario", user_edit).execute()
                    st.success("Dados atualizados com sucesso!")
                    time.sleep(1)
                    st.rerun()

    with aba_d:
        if not df_u.empty:
            st.warning("A exclusão de um usuário é permanente.")
            user_del = st.selectbox("Selecione o usuário para EXCLUIR", df_u['usuario'].tolist(), key="del_u_select")
            if user_del == st.session_state.user:
                st.error("Você não pode excluir a si mesmo.")
            else:
                if st.button(f"Confirmar Exclusão de {user_del}", type="primary"):
                    supabase.table("usuarios").delete().eq("usuario", user_del).execute()
                    st.success("Usuário excluído com sucesso!")
                    time.sleep(2)
                    st.rerun()
