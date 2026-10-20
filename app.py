import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime
import time
import io
import uuid
import hashlib
import hmac
import secrets
import re
import requests
from PIL import Image

# Imports para PDF (ReportLab)
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage, Table, TableStyle
from reportlab.lib.units import cm

# --- 1. CONFIGURAÇÕES DA PÁGINA ---
st.set_page_config(page_title="Sistema TI - Estoque Pro", page_icon="📦", layout="wide")

# --- 2. CONEXÃO COM SUPABASE ---
@st.cache_resource
def get_supabase() -> Client:
    url = st.secrets["URL_BANCO"]
    key = st.secrets.get("SUPABASE_SERVICE_ROLE_KEY")
    if not key:
        raise RuntimeError("Configure SUPABASE_SERVICE_ROLE_KEY nos Secrets do Streamlit.")
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
    if pd.isna(data_iso) or not data_iso:
        return "N/A"
    try:
        dt = pd.to_datetime(data_iso)
        return dt.strftime("%d/%m/%Y %H:%M")
    except:
        return str(data_iso)

def upload_fotos_multiplas(files):
    urls = []
    for file in files:
        try:
            ext = file.name.split('.')[-1]
            nome_arquivo = f"{datetime.now().year}/{datetime.now().month:02d}/{uuid.uuid4()}.{ext}"
            img = Image.open(file)
            if img.mode in ("RGBA", "P"): img = img.convert("RGB")
            img.thumbnail((1200, 1200))
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='JPEG', quality=85)
            supabase.storage.from_("descartes").upload(nome_arquivo, img_byte_arr.getvalue(), {"content-type": "image/jpeg"})
            url = supabase.storage.from_("descartes").get_public_url(nome_arquivo)
            urls.append(str(url))
        except Exception as e:
            st.error(f"Erro no upload de {file.name}: {e}")
    return ",".join(urls) if urls else None

# --- 4. LOGIN E PERMISSOES ---
# A chave service_role fica exclusivamente nos Secrets do servidor Streamlit.
# O banco nunca deve ser acessado diretamente do navegador com essa chave.
PERMISSOES = {
    "consultar": "can_consultar", "movimentar": "can_movimentar",
    "cadastrar": "can_cadastrar", "admin": "can_admin",
    "historico": "can_historico", "usuarios": "can_usuarios",
    "descarte": "can_descarte", "abrir_chamado": "can_abrir_chamado",
    "ver_chamados": "can_ver_chamados", "gerenciar_os": "can_gerenciar_os",
}

def hash_senha(senha):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", senha.encode(), salt, 260000)
    return "pbkdf2_sha256$260000$" + salt.hex() + "$" + digest.hex()

def verificar_senha(senha, armazenada):
    if not isinstance(armazenada, str):
        return False, False
    if armazenada.startswith("pbkdf2_sha256$"):
        try:
            _, rounds, salt, digest = armazenada.split("$")
            calculado = hashlib.pbkdf2_hmac("sha256", senha.encode(), bytes.fromhex(salt), int(rounds))
            return hmac.compare_digest(calculado, bytes.fromhex(digest)), False
        except (ValueError, TypeError):
            return False, False
    # Migra a senha antiga para hash no primeiro login bem-sucedido.
    return hmac.compare_digest(senha, armazenada), True

def carregar_usuario(login):
    rows = supabase.table("usuarios").select("*").eq("usuario", login).limit(1).execute().data
    return rows[0] if rows else None

def permissao(chave):
    return bool(st.session_state.perms.get(chave, False))

def exigir(chave):
    if not permissao(chave):
        st.error("Acesso não autorizado.")
        st.stop()

def registrar_evento(chamado_id, acao, detalhe=""):
    supabase.table("chamados_eventos").insert({
        "chamado_id": chamado_id, "acao": acao, "detalhe": detalhe,
        "usuario": st.session_state.user
    }).execute()

if "logado" not in st.session_state:
    st.session_state.logado = False
    st.session_state.user = None
    st.session_state.nome_real = None
    st.session_state.perms = {}

if not st.session_state.logado:
    st.title("🔐 Acesso ao Sistema TI")
    with st.form("login_form"):
        u = st.text_input("Usuário").strip().lower()
        p = st.text_input("Senha", type="password")
        if st.form_submit_button("Entrar", use_container_width=True):
            try:
                d = carregar_usuario(u)
                ok, legacy = verificar_senha(p, d.get("senha") if d else None)
                if not ok:
                    st.error("Login ou senha incorretos.")
                else:
                    if legacy:
                        supabase.table("usuarios").update({"senha": hash_senha(p)}).eq("usuario", u).execute()
                    st.session_state.logado = True
                    st.session_state.user = u
                    st.session_state.nome_real = d.get("nome", u)
                    st.session_state.perms = {k: bool(d.get(col, False)) for k, col in PERMISSOES.items()}
                    st.session_state.perms["nivel"] = d.get("nivel", "comum")
                    st.rerun()
            except Exception as e:
                st.error(f"Falha no login: {e}")
    st.stop()

# Permissoes atualizadas do banco a cada rerun; nao confiar apenas na sessao.
usuario_atual = carregar_usuario(st.session_state.user)
if not usuario_atual:
    st.session_state.logado = False
    st.rerun()
st.session_state.nome_real = usuario_atual.get("nome", st.session_state.user)
st.session_state.perms = {k: bool(usuario_atual.get(col, False)) for k, col in PERMISSOES.items()}
st.session_state.perms["nivel"] = usuario_atual.get("nivel", "comum")

st.sidebar.title(f"👋 Olá, {st.session_state.nome_real}")
opcoes_menu = []
if permissao("abrir_chamado"): opcoes_menu.append("🎫 Abrir Chamado")
if permissao("ver_chamados") or permissao("gerenciar_os"): opcoes_menu.append("📋 Chamados e O.S.")
if permissao("consultar"): opcoes_menu.append("📊 Consultar Estoque")
if permissao("movimentar"): opcoes_menu.append("🔄 Entrada / Saída")
if permissao("cadastrar"): opcoes_menu.append("🆕 Cadastrar Produto")
if permissao("admin"): opcoes_menu.append("🔧 Correção de Produtos")
if permissao("historico"): opcoes_menu.append("📜 Histórico e Relatórios")
if permissao("descarte"): opcoes_menu.append("♻️ Descarte de Equipamentos")
if permissao("usuarios"): opcoes_menu.append("👥 Gerenciar Usuários")
if not opcoes_menu:
    st.error("Sua conta não possui funcionalidades liberadas.")
    st.stop()
menu = st.sidebar.radio("Navegação", opcoes_menu)
if st.sidebar.button("Sair / Logoff"):
    for k in ("logado", "user", "nome_real", "perms"):
        st.session_state.pop(k, None)
    st.rerun()

# --- 6. TELAS DO SISTEMA ---

# --- CONSULTA ---
if menu == "🎫 Abrir Chamado":
    exigir("abrir_chamado")
    st.title("🎫 Abrir Chamado")
    with st.form("novo_chamado", clear_on_submit=True):
        titulo = st.text_input("Título do problema*")
        descricao = st.text_area("Descrição detalhada*")
        prioridade = st.selectbox("Prioridade", ["Baixa", "Normal", "Alta", "Crítica"], index=1)
        local = st.text_input("Local / Setor")
        equipamento = st.text_input("Equipamento / Patrimônio")
        if st.form_submit_button("Abrir chamado", type="primary"):
            if not titulo.strip() or not descricao.strip():
                st.error("Preencha título e descrição.")
            else:
                try:
                    row = supabase.table("chamados").insert({
                        "titulo": titulo.strip(), "descricao": descricao.strip(),
                        "prioridade": prioridade, "local_setor": local.strip(),
                        "equipamento": equipamento.strip(),
                        "solicitante": st.session_state.user,
                        "status": "Aberto"
                    }).execute().data[0]
                    registrar_evento(row["id"], "ABERTURA", "Chamado aberto pelo solicitante")
                    st.success(f"Chamado #{row['numero']} aberto com sucesso!")
                except Exception as e:
                    st.error(f"Não foi possível abrir o chamado: {e}")

elif menu == "📋 Chamados e O.S.":
    if not (permissao("ver_chamados") or permissao("gerenciar_os")):
        st.error("Acesso não autorizado."); st.stop()
    st.title("📋 Chamados e Ordens de Serviço")
    try:
        rows = supabase.table("chamados").select("*").order("numero", desc=True).limit(1000).execute().data
        if not permissao("gerenciar_os"):
            rows = [r for r in rows if r.get("solicitante") == st.session_state.user]
        if not rows:
            st.info("Nenhum chamado encontrado.")
        else:
            df_ch = pd.DataFrame(rows)
            visiveis = [c for c in ("numero", "titulo", "solicitante", "prioridade", "status", "tecnico", "created_at") if c in df_ch.columns]
            st.dataframe(df_ch[visiveis], use_container_width=True, hide_index=True)
            labels = {f"#{r['numero']} - {r['titulo']}": r for r in rows}
            selecionado = labels[st.selectbox("Selecionar chamado / O.S.", list(labels))]
            st.write("**Descrição:**", selecionado.get("descricao", ""))
            st.write("**Local:**", selecionado.get("local_setor", ""))
            st.write("**Equipamento:**", selecionado.get("equipamento", ""))
            if permissao("gerenciar_os"):
                with st.form("atender_os"):
                    status_op = ["Aberto", "Em triagem", "Em atendimento", "Aguardando peças", "Resolvido", "Fechado", "Cancelado"]
                    prioridade_op = ["Baixa", "Normal", "Alta", "Crítica"]
                    status = st.selectbox("Status", status_op, index=status_op.index(selecionado.get("status")) if selecionado.get("status") in status_op else 0)
                    prioridade = st.selectbox("Prioridade", prioridade_op, index=prioridade_op.index(selecionado.get("prioridade")) if selecionado.get("prioridade") in prioridade_op else 1)
                    tecnico = st.text_input("Técnico responsável", value=selecionado.get("tecnico") or "")
                    diagnostico = st.text_area("Diagnóstico", value=selecionado.get("diagnostico") or "")
                    solucao = st.text_area("Solução / Serviço realizado", value=selecionado.get("solucao") or "")
                    observacao = st.text_area("Observação do atendimento")
                    if st.form_submit_button("Salvar O.S.", type="primary"):
                        update = {"status": status, "prioridade": prioridade, "tecnico": tecnico.strip(),
                                  "diagnostico": diagnostico.strip(), "solucao": solucao.strip(),
                                  "updated_at": datetime.now().astimezone().isoformat()}
                        if status in ("Resolvido", "Fechado") and not selecionado.get("resolvido_em"):
                            update["resolvido_em"] = datetime.now().astimezone().isoformat()
                        supabase.table("chamados").update(update).eq("id", selecionado["id"]).execute()
                        registrar_evento(selecionado["id"], "ATUALIZACAO_OS", f"Status: {status}. {observacao.strip()}")
                        st.success("O.S. atualizada."); st.rerun()
                st.subheader("Materiais utilizados na O.S.")
                produtos = buscar_dados("produtos")
                if not produtos.empty:
                    escolhas = {f"#{int(r['id'])} - {r['nome']} (saldo {r['quantidade']})": r for _, r in produtos.iterrows()}
                    with st.form("material_os"):
                        item = escolhas[st.selectbox("Produto", list(escolhas))]
                        quantidade = st.number_input("Quantidade utilizada", min_value=1, step=1)
                        if st.form_submit_button("Registrar saída para O.S."):
                            try:
                                supabase.rpc("consumir_material_os", {
                                    "p_chamado_id": selecionado["id"],
                                    "p_produto_id": int(item["id"]),
                                    "p_quantidade": int(quantidade),
                                    "p_operador": st.session_state.user
                                }).execute()
                                st.success("Material baixado do estoque e associado à O.S."); st.rerun()
                            except Exception as e:
                                st.error(f"Não foi possível registrar material: {e}")
            eventos = supabase.table("chamados_eventos").select("created_at,usuario,acao,detalhe").eq("chamado_id", selecionado["id"]).order("created_at", desc=True).execute().data
            if eventos:
                st.subheader("Histórico do atendimento")
                st.dataframe(pd.DataFrame(eventos), use_container_width=True, hide_index=True)
            materiais = supabase.table("chamados_materiais").select("produto_nome,quantidade,operador,created_at").eq("chamado_id", selecionado["id"]).execute().data
            if materiais:
                st.subheader("Materiais utilizados")
                st.dataframe(pd.DataFrame(materiais), use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Erro ao consultar chamados: {e}")

if menu == "📊 Consultar Estoque":
    st.title("📊 Consultar Estoque")
    df = buscar_dados("produtos")
    if not df.empty:
        termo = st.text_input("🔍 Pesquisar por Nome ou Marca").lower()
        df_f = df[df['nome'].str.lower().str.contains(termo, na=False) | df['marca'].str.lower().str.contains(termo, na=False)]
        st.dataframe(df_f, use_container_width=True, hide_index=True)

# --- MOVIMENTAÇÃO ---
elif menu == "🔄 Entrada / Saída":
    exigir("movimentar")
    st.title("🔄 Movimentação de Estoque")
    df = buscar_dados("produtos")
    if not df.empty:
        op = {f"ID: {p['id']} | {p['nome']}": p for _, p in df.iterrows()}
        escolha = st.selectbox("Selecione o Produto", list(op.keys()))
        item = op[escolha]
        col1, col2 = st.columns(2)
        qtd = col1.number_input("Quantidade", min_value=1)
        tipo = col2.radio("Operação", ["Saída (Baixa)", "Entrada (Compra)"])
        cha = st.text_input("Chamado / Observação").strip()
        if st.button("Confirmar Movimentação", type="primary"):
            nq = item['quantidade'] + qtd if "Entrada" in tipo else item['quantidade'] - qtd
            if nq < 0: st.error("Saldo insuficiente no estoque!")
            else:
                supabase.table("produtos").update({"quantidade": int(nq)}).eq("id", item['id']).execute()
                supabase.table("historico").insert({"operador":st.session_state.nome_real,"acao":tipo,"produto":item['nome'],"quantidade":int(qtd),"chamado":cha,"data":datetime.now().isoformat()}).execute()
                st.success("Movimentação realizada com sucesso!"); time.sleep(1); st.rerun()

# --- CADASTRO PRODUTO ---
elif menu == "🆕 Cadastrar Produto":
    exigir("cadastrar")
    st.title("🆕 Cadastrar Novo Produto")
    with st.form("f_cad"):
        n = st.text_input("Nome do Produto*")
        m = st.text_input("Marca"); mod = st.text_input("Modelo"); cat = st.text_input("Categoria")
        q = st.number_input("Quantidade Inicial", min_value=0)
        a = st.number_input("Alerta Mínimo", min_value=1)
        if st.form_submit_button("Salvar Produto"):
            if n:
                supabase.table("produtos").insert({"nome":n,"marca":m,"modelo":mod,"categoria":cat,"quantidade":int(q),"alerta":int(a)}).execute()
                st.success("Produto cadastrado!"); time.sleep(1); st.rerun()
            else: st.error("O nome do produto é obrigatório.")

# --- CORREÇÃO PRODUTO ---
elif menu == "🔧 Correção de Produtos":
    exigir("admin")
    st.title("🔧 Correção e Exclusão")
    df = buscar_dados("produtos")
    if not df.empty:
        aba_c, aba_e = st.tabs(["Editar Dados", "Excluir"])
        with aba_c:
            sel = st.selectbox("Produto para editar", df['nome'].tolist())
            p = df[df['nome'] == sel].iloc[0]
            with st.form("f_cor"):
                nn = st.text_input("Nome", value=p['nome'])
                if st.form_submit_button("Atualizar Dados"):
                    supabase.table("produtos").update({"nome":nn}).eq("id", p['id']).execute()
                    st.success("Atualizado!"); st.rerun()
        with aba_e:
            ex_id = st.text_input("ID do Produto para excluir")
            if st.button("EXCLUIR PRODUTO PERMANENTEMENTE", type="primary"):
                if ex_id:
                    supabase.table("produtos").delete().eq("id", ex_id).execute()
                    st.success("Produto removido!"); time.sleep(1); st.rerun()

# --- HISTÓRICO ---
elif menu == "📜 Histórico e Relatórios":
    exigir("historico")
    st.title("📜 Histórico de Movimentações")
    df_h = buscar_dados("historico")
    if not df_h.empty:
        df_h['data_f'] = df_h['data'].apply(formatar_data)
        st.dataframe(df_h[['data_f','produto','acao','quantidade','chamado','operador']], use_container_width=True, hide_index=True)

# ==================================================
# 👥 GERENCIAR USUÁRIOS (COM TRAVA DE DUPLICIDADE)
# ==================================================
elif menu == "👥 Gerenciar Usuários":
    exigir("usuarios")
    st.title("👥 Gestão de Usuários")
    abas = st.tabs(["📋 Lista", "➕ Novo usuário", "✏️ Editar / Excluir"])
    df_u = buscar_dados("usuarios")
    with abas[0]:
        if not df_u.empty:
            st.dataframe(df_u[[c for c in ("nome", "usuario", "nivel") if c in df_u]], use_container_width=True, hide_index=True)
    with abas[1]:
        with st.form("criar_usuario"):
            nome = st.text_input("Nome completo*").strip()
            login = st.text_input("Login*").strip().lower()
            senha = st.text_input("Senha*", type="password")
            perfil = st.selectbox("Perfil inicial", ["Somente abrir chamado", "Técnico", "Administrador", "Personalizado"])
            st.caption("No perfil Personalizado, selecione as permissões abaixo.")
            marcadas = {k: st.checkbox(k.replace("_", " ").title(), value=False, key="new_"+k) for k in PERMISSOES} if perfil == "Personalizado" else {}
            if st.form_submit_button("Criar usuário"):
                if not nome or not re.fullmatch(r"[a-z0-9_.-]{3,40}", login) or len(senha) < 8:
                    st.error("Informe nome, login válido (mínimo 3 caracteres) e senha com pelo menos 8 caracteres.")
                elif carregar_usuario(login):
                    st.error("Login já cadastrado.")
                else:
                    grants = {k: False for k in PERMISSOES}
                    if perfil == "Somente abrir chamado":
                        grants["abrir_chamado"] = True
                    elif perfil == "Técnico":
                        grants.update({"abrir_chamado": True, "ver_chamados": True, "gerenciar_os": True, "consultar": True})
                    elif perfil == "Administrador":
                        grants = {k: True for k in PERMISSOES}
                    else:
                        grants = marcadas
                    dados = {"nome": nome, "usuario": login, "senha": hash_senha(senha),
                             "nivel": "administrador" if perfil == "Administrador" else "comum"}
                    dados.update({col: grants[k] for k, col in PERMISSOES.items()})
                    try:
                        supabase.table("usuarios").insert(dados).execute()
                        st.success("Usuário criado com sucesso.")
                    except Exception as e:
                        st.error(f"Falha ao criar usuário: {e}")
    with abas[2]:
        if not df_u.empty:
            login = st.selectbox("Usuário", df_u["usuario"].tolist())
            dados = df_u[df_u["usuario"] == login].iloc[0]
            with st.form("editar_usuario"):
                nome = st.text_input("Nome", value=str(dados.get("nome") or ""))
                senha = st.text_input("Nova senha (deixe vazio para manter)", type="password")
                nivel = st.selectbox("Nível", ["comum", "administrador"], index=1 if dados.get("nivel") == "administrador" else 0)
                grants = {k: st.checkbox(k.replace("_", " ").title(), value=bool(dados.get(col, False)), key="edit_"+k) for k, col in PERMISSOES.items()}
                if st.form_submit_button("Salvar alterações"):
                    if senha and len(senha) < 8:
                        st.error("A nova senha precisa ter pelo menos 8 caracteres.")
                    elif not nome.strip():
                        st.error("Informe o nome.")
                    elif login == st.session_state.user and not grants["usuarios"]:
                        st.error("Você não pode remover sua própria permissão de gerenciar usuários.")
                    else:
                        update = {"nome": nome.strip(), "nivel": nivel}
                        update.update({col: grants[k] for k, col in PERMISSOES.items()})
                        if senha:
                            update["senha"] = hash_senha(senha)
                        supabase.table("usuarios").update(update).eq("usuario", login).execute()
                        st.success("Usuário atualizado."); st.rerun()
            if login != st.session_state.user:
                with st.expander("Excluir usuário"):
                    confirmacao = st.checkbox(f"Confirmo a exclusão de {login}")
                    if st.button("Excluir usuário", disabled=not confirmacao):
                        supabase.table("usuarios").delete().eq("usuario", login).execute()
                        st.success("Usuário excluído."); st.rerun()

# ==================================================
# ♻️ MÓDULO DE DESCARTE (MÚLTIPLAS FOTOS E EXCLUSÃO)
# ==================================================
elif menu == "♻️ Descarte de Equipamentos":
    exigir("descarte")
    st.title("♻️ Descarte de Equipamentos")
    aba_n, aba_l, aba_p = st.tabs(["➕ Novo Descarte", "📋 Lista de Descartes", "📄 Relatório PDF"])

    with aba_n:
        with st.form("f_desc", clear_on_submit=True):
            p_n = st.text_input("Produto*")
            col1, col2 = st.columns(2)
            cat = col1.selectbox("Categoria", ["Periférico", "Monitor", "Computador", "Notebook", "Celular", "Impressora", "Rede", "Outros"])
            mar = col1.text_input("Marca"); mod = col2.text_input("Modelo")
            ser = col1.text_input("Série"); pat = col2.text_input("Patrimônio")
            def_p = st.text_area("Defeito*")
            f_arqs = st.file_uploader("Fotos do Equipamento", type=["jpg","png","webp"], accept_multiple_files=True)
            if st.form_submit_button("Cadastrar para Descarte"):
                if p_n and def_p:
                    u_fotos = upload_fotos_multiplas(f_arqs)
                    supabase.table("descartes").insert({"produto":p_n,"categoria":cat,"marca":mar,"modelo":mod,"numero_serie":ser,"patrimonio":pat,"defeito":def_p,"foto_url":u_fotos,"responsavel":st.session_state.nome_real,"usuario_login":st.session_state.user}).execute()
                    st.success("Equipamento registrado para descarte!"); time.sleep(1); st.rerun()
                else: st.error("Produto e Defeito são obrigatórios.")

    with aba_l:
        df_d = buscar_dados("descartes")
        if not df_d.empty:
            st.dataframe(df_d[['id','produto','status','responsavel']], use_container_width=True, hide_index=True)
            sel_id = st.selectbox("Selecionar Equipamento (ID)", df_d['id'].tolist())
            if sel_id:
                it = df_d[df_d['id'] == sel_id].iloc[0]
                c1, c2 = st.columns([1, 2])
                with c1:
                    if it['foto_url']:
                        urls = str(it['foto_url']).split(',')
                        for u in urls: st.image(u, use_container_width=True)
                    else: st.info("Sem fotos cadastradas.")
                
                with c2:
                    with st.form(f"ed_desc_{sel_id}"):
                        en_p = st.text_input("Produto", value=it['produto'])
                        en_st = st.selectbox("Status", ["🟡 Aguardando descarte", "🔵 Em avaliação", "🟢 Aprovado para descarte", "🔴 Descartado"], index=["🟡 Aguardando descarte", "🔵 Em avaliação", "🟢 Aprovado para descarte", "🔴 Descartado"].index(it['status']))
                        en_de = st.text_area("Defeito", value=it['defeito'])
                        novas_f = st.file_uploader("Adicionar mais fotos", type=["jpg","png","webp"], accept_multiple_files=True)
                        if st.form_submit_button("Salvar Edição"):
                            u_novas = upload_fotos_multiplas(novas_f)
                            u_final = (it['foto_url'] + "," + u_novas) if (it['foto_url'] and u_novas) else (u_novas or it['foto_url'])
                            upd = {"produto":en_p, "status":en_st, "defeito":en_de, "foto_url":u_final}
                            if en_st == "🔴 Descartado": upd["data_descarte"] = datetime.now().isoformat()
                            supabase.table("descartes").update(upd).eq("id", sel_id).execute()
                            st.success("Atualizado com sucesso!"); time.sleep(1); st.rerun()
                    
                    if st.button("🗑️ EXCLUIR REGISTRO DE DESCARTE", type="primary"):
                        supabase.table("descartes").delete().eq("id", sel_id).execute()
                        st.success("Registro removido!"); time.sleep(1); st.rerun()

    with aba_p:
        st.subheader("Gerar Relatório PDF")
        if st.button("Gerar PDF de todos os itens cadastrados"):
            df_pdf = buscar_dados("descartes")
            if not df_pdf.empty:
                buffer = io.BytesIO()
                doc = SimpleDocTemplate(buffer, pagesize=letter)
                elements = []
                styles = getSampleStyleSheet()
                elements.append(Paragraph("RELATÓRIO DE DESCARTE DE EQUIPAMENTOS", styles['Title']))
                
                for _, r in df_pdf.iterrows():
                    data = [[f"ID #{r['id']} - {r['produto']}", ""], ["Defeito:", r['defeito']], ["Status:", r['status']]]
                    t = Table(data, colWidths=[3.75*cm, 11*cm])
                    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.lightgrey),('GRID',(0,0),(-1,-1),0.5,colors.grey)]))
                    elements.append(t)
                    
                    if r['foto_url']:
                        urls = str(r['foto_url']).split(',')
                        for u in urls:
                            try:
                                resp = requests.get(u, timeout=5)
                                img_io = io.BytesIO(resp.content)
                                img = RLImage(img_io, width=10*cm, height=15*cm) # Tamanho 10x15cm
                                elements.append(Spacer(1, 10))
                                elements.append(img)
                            except: pass
                    elements.append(Spacer(1, 30))
                
                doc.build(elements)
                st.download_button("📥 Baixar Relatório PDF", buffer.getvalue(), f"relatorio_descarte.pdf", "application/pdf")
