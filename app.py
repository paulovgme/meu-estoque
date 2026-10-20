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
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage, Table, TableStyle
from reportlab.lib.units import cm
from xml.sax.saxutils import escape as xml_escape

# --- 1. CONFIGURAÇÕES DA PÁGINA ---
st.set_page_config(page_title="Évora Gestão", page_icon="📦", layout="wide")

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

def eh_administrador():
    """Exclusão exige perfil administrativo E permissão administrativa."""
    nivel = str(st.session_state.perms.get("nivel") or "").strip().lower()
    return nivel in ("admin", "administrador") and permissao("admin")


def painel_exclusao_registro(tipo, registro):
    """Exclusão definitiva com confirmação explícita, apenas para administrador."""
    if not eh_administrador():
        return
    tabela = "chamados" if tipo == "chamado" else "ordens_servico"
    rotulo = "chamado" if tipo == "chamado" else "ordem de serviço"
    numero = registro["numero"]
    with st.expander(f"🗑️ Excluir {rotulo} nº {numero} — somente administrador"):
        st.warning(
            "Esta exclusão é permanente e também remove os eventos e materiais "
            "vinculados ao registro. Movimentações já lançadas no estoque e no "
            "histórico não serão revertidas."
        )
        with st.form(f"excluir_{tipo}_{registro['id']}"):
            confirmacao = st.text_input(
                f"Digite EXCLUIR {numero} para confirmar",
                key=f"confirmar_exclusao_{tipo}_{registro['id']}",
            )
            excluir = st.form_submit_button(f"Excluir {rotulo} definitivamente")
        if excluir:
            if not eh_administrador():
                st.error("Apenas o administrador pode excluir registros.")
            elif confirmacao.strip() != f"EXCLUIR {numero}":
                st.error("Confirmação incorreta. Nenhum registro foi excluído.")
            else:
                try:
                    # Verifica o registro exato antes da exclusão.
                    existente = supabase.table(tabela).select("id").eq("id", registro["id"]).limit(1).execute().data
                    if not existente:
                        st.error("Registro não encontrado. Atualize a página.")
                        return
                    apagados = supabase.table(tabela).delete().eq("id", registro["id"]).execute()
                    if not apagados.data:
                        st.error("A exclusão não foi confirmada pelo banco de dados.")
                        return
                    st.success(f"{rotulo.capitalize()} nº {numero} excluído com sucesso.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Não foi possível excluir {rotulo}: {exc}")

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
    st.title("🔐 Acesso ao Évora Gestão")
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
opcoes_menu = ["🏠 Início"]
if permissao("ver_chamados") or permissao("gerenciar_os") or eh_administrador(): opcoes_menu.append("📋 Chamados e O.S.")
if permissao("consultar"): opcoes_menu.append("📊 Consultar Estoque")
if permissao("abrir_chamado"): opcoes_menu.append("🎫 Abrir Chamados / O.S")
if permissao("movimentar"): opcoes_menu.append("🔄 Entrada / Saída")
if permissao("cadastrar"): opcoes_menu.append("🆕 Cadastrar Produto")
if permissao("admin"): opcoes_menu.append("🔧 Correção de Produtos")
if permissao("historico"): opcoes_menu.append("📜 Histórico e Relatórios")
if permissao("descarte"): opcoes_menu.append("♻️ Descarte de Equipamentos")
if permissao("usuarios"): opcoes_menu.append("👥 Gerenciar Usuários")
menu = st.sidebar.radio("Navegação", opcoes_menu, key="menu_principal")
if st.sidebar.button("Sair / Logoff"):
    for k in ("logado", "user", "nome_real", "perms", "menu_principal"):
        st.session_state.pop(k, None)
    st.rerun()

# Chamados e ordens de serviço são registros independentes, em tabelas diferentes.
STATUS_OS = ["Aberta", "Em andamento", "Aguardando peças", "Concluída", "Encerrada", "Cancelada"]
PRIORIDADES = ["Baixa", "Normal", "Alta", "Crítica"]

def buscar_registros(tabela):
    return supabase.table(tabela).select("*").order("numero", desc=True).limit(1000).execute().data or []

def criar_pdf_os(os_dados):
    arquivo = io.BytesIO()
    doc = SimpleDocTemplate(arquivo, pagesize=A4, rightMargin=1.7*cm, leftMargin=1.7*cm,
                            topMargin=1.6*cm, bottomMargin=1.6*cm)
    estilos = getSampleStyleSheet()
    titulo = ParagraphStyle("TituloOS", parent=estilos["Heading1"], fontSize=17, leading=22,
                             textColor=colors.HexColor("#17345C"), spaceAfter=14)
    corpo = ParagraphStyle("CorpoOS", parent=estilos["Normal"], fontSize=10, leading=15, spaceAfter=7)
    def campo(nome, valor):
        return Paragraph(f"<b>{xml_escape(nome)}:</b> {xml_escape(str(valor or '—'))}", corpo)
    historia = [Paragraph("ORDEM DE SERVIÇO — ÉVORA TECNOLOGIA", titulo)]
    historia += [campo("Nº da O.S.", os_dados.get("numero")),
                 campo("Abertura", formatar_data(os_dados.get("created_at"))),
                 campo("Status", os_dados.get("status")),
                 campo("Prioridade", os_dados.get("prioridade")),
                 campo("Solicitante", os_dados.get("solicitante")),
                 campo("Setor / Local", os_dados.get("local_setor")),
                 campo("Equipamento / Patrimônio", os_dados.get("equipamento")),
                 campo("Técnico responsável", os_dados.get("tecnico")), Spacer(1, 0.4*cm),
                 campo("Serviço solicitado", os_dados.get("titulo")),
                 campo("Descrição", os_dados.get("descricao")), Spacer(1, 0.3*cm),
                 campo("Diagnóstico técnico", os_dados.get("diagnostico")),
                 campo("Serviço executado / Solução", os_dados.get("solucao")),
                 Spacer(1, 1.4*cm)]
    assinatura = Table([["_________________________________", "_________________________________"],
                        ["Assinatura do técnico", "Assinatura do solicitante"]], colWidths=[8.3*cm, 8.3*cm])
    assinatura.setStyle(TableStyle([("ALIGN", (0,0), (-1,-1), "CENTER"),
                                   ("FONTSIZE", (0,0), (-1,-1), 9), ("BOTTOMPADDING", (0,0), (-1,0), 9)]))
    historia.append(assinatura)
    doc.build(historia)
    return arquivo.getvalue()

def painel_os(os_dados, chave):
    """Pré-visualização legível antes de baixar/imprimir o PDF."""
    st.markdown("#### Pré-visualização da O.S.")
    with st.container(border=True):
        st.markdown("### ORDEM DE SERVIÇO — ÉVORA TECNOLOGIA")
        st.markdown(f"**O.S. nº {os_dados.get('numero', '—')}** | **Status:** {os_dados.get('status', 'Aberta')} | **Prioridade:** {os_dados.get('prioridade', 'Normal')}")
        for nome, campo in [("Solicitante", "solicitante"), ("Setor / Local", "local_setor"),
                            ("Equipamento / Patrimônio", "equipamento"), ("Técnico", "tecnico"),
                            ("Serviço solicitado", "titulo"), ("Descrição", "descricao"),
                            ("Diagnóstico", "diagnostico"), ("Serviço realizado", "solucao")]:
            st.write(f"**{nome}:** {os_dados.get(campo) or '—'}")
        st.caption("Assinatura do técnico: _____________________     Assinatura do solicitante: _____________________")
    st.download_button("🖨️ Baixar PDF para visualizar e imprimir", data=criar_pdf_os(os_dados),
                       file_name=f"OS_{os_dados.get('numero', 'rascunho')}.pdf", mime="application/pdf", key=chave)
    st.caption("Abra o PDF baixado no navegador para usar a pré-impressão e escolher a impressora.")

# --- 6. TELAS DO SISTEMA ---

# --- CONSULTA ---
if menu == "🏠 Início":
    st.title("🏠 Painel Inicial — T.I.")
    st.caption("Resumo dos chamados, ordens de serviço e equipamentos cadastrados")
    try:
        chamados_painel = buscar_registros("chamados") if (permissao("ver_chamados") or permissao("gerenciar_os")) else []
        os_painel = buscar_registros("ordens_servico") if permissao("gerenciar_os") else []
        if not permissao("gerenciar_os"):
            chamados_painel = [r for r in chamados_painel if r.get("solicitante") == st.session_state.user]
        produtos_painel = buscar_dados("produtos") if permissao("consultar") else pd.DataFrame()
        chamados_abertos = sum(r.get("status") in ("Aberto", "Em atendimento") for r in chamados_painel)
        chamados_pendentes = sum(r.get("status") in ("Em triagem", "Aguardando peças") for r in chamados_painel)
        chamados_encerrados = sum(r.get("status") in ("Resolvido", "Fechado", "Cancelado") for r in chamados_painel)
        os_abertas = sum(r.get("status") not in ("Encerrada", "Concluída", "Cancelada") for r in os_painel)
        os_encerradas = sum(r.get("status") in ("Encerrada", "Concluída", "Cancelada") for r in os_painel)
        a,b,c = st.columns(3)
        a.metric("Chamados abertos", chamados_abertos)
        b.metric("Chamados pendentes", chamados_pendentes)
        c.metric("Chamados encerrados", chamados_encerrados)
        d,e,f = st.columns(3)
        d.metric("O.S. abertas", os_abertas)
        e.metric("O.S. encerradas", os_encerradas)
        f.metric("Produtos cadastrados", len(produtos_painel))
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Distribuição dos chamados")
            dados_pizza = pd.DataFrame({"Situação": ["Abertos", "Pendentes", "Encerrados"],
                                        "Quantidade": [chamados_abertos, chamados_pendentes, chamados_encerrados]})
            if dados_pizza["Quantidade"].sum():
                st.vega_lite_chart(dados_pizza, {"mark": {"type": "arc", "innerRadius": 35},
                    "encoding": {"theta": {"field": "Quantidade", "type": "quantitative"},
                                 "color": {"field": "Situação", "type": "nominal"},
                                 "tooltip": [{"field": "Situação"}, {"field": "Quantidade"}]}}, use_container_width=True)
            else: st.info("Sem chamados para exibir.")
        with c2:
            st.subheader("Ordens de serviço")
            st.bar_chart(pd.DataFrame({"Quantidade": [os_abertas, os_encerradas]},
                                      index=["Abertas", "Encerradas"]))
        if not produtos_painel.empty:
            st.subheader("Equipamentos / produtos por categoria")
            agrupados = produtos_painel.assign(categoria=produtos_painel["categoria"].fillna("Sem categoria").replace("", "Sem categoria"))
            st.bar_chart(agrupados.groupby("categoria").size().rename("Cadastros"))
            st.caption("O gráfico representa cadastros por categoria, não a soma das quantidades em estoque.")
    except Exception as e:
        st.error(f"Não foi possível carregar o painel: {e}. Execute a migração SQL desta atualização.")

elif menu == "🎫 Abrir Chamados / O.S":
    exigir("abrir_chamado")
    st.title("🎫 Abrir Chamados / O.S")
    aba_ch, aba_os = st.tabs(["🎫 Abrir Chamado", "🛠️ Abrir Ordem de Serviço"])
    with aba_ch:
        with st.form("novo_chamado", clear_on_submit=True):
            titulo = st.text_input("Título do problema*")
            descricao = st.text_area("Descrição detalhada*")
            prioridade = st.selectbox("Prioridade", PRIORIDADES, index=1)
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
                            "equipamento": equipamento.strip(), "solicitante": st.session_state.user,
                            "status": "Aberto"}).execute().data[0]
                        registrar_evento(row["id"], "ABERTURA", "Chamado aberto pelo solicitante")
                        st.success(f"Chamado #{row['numero']} aberto com sucesso!")
                    except Exception as e: st.error(f"Erro ao abrir chamado: {e}")
    with aba_os:
        st.caption("Uma O.S. é um documento técnico independente de chamado, com numeração e impressão próprias.")
        with st.form("nova_os", clear_on_submit=False):
            servico = st.text_input("Serviço solicitado*")
            descricao_os = st.text_area("Descrição do serviço*")
            prioridade_os = st.selectbox("Prioridade da O.S.", PRIORIDADES, index=1)
            local_os = st.text_input("Setor / Local de atendimento")
            equipamento_os = st.text_input("Equipamento / Patrimônio")
            tecnico_os = st.text_input("Técnico responsável")
            diagnostico_os = st.text_area("Diagnóstico inicial")
            if st.form_submit_button("Criar Ordem de Serviço", type="primary"):
                if not servico.strip() or not descricao_os.strip():
                    st.error("Preencha o serviço solicitado e sua descrição.")
                else:
                    try:
                        nova = supabase.table("ordens_servico").insert({
                            "titulo": servico.strip(), "descricao": descricao_os.strip(),
                            "prioridade": prioridade_os, "local_setor": local_os.strip(),
                            "equipamento": equipamento_os.strip(), "tecnico": tecnico_os.strip(),
                            "diagnostico": diagnostico_os.strip(), "solicitante": st.session_state.user,
                            "status": "Aberta"}).execute().data[0]
                        st.session_state["os_criada_id"] = nova["id"]
                        st.success(f"O.S. nº {nova['numero']} criada! Confira a pré-visualização abaixo.")
                    except Exception as e: st.error(f"Não foi possível criar a O.S.: {e}")
        if st.session_state.get("os_criada_id"):
            resultado = supabase.table("ordens_servico").select("*").eq("id", st.session_state["os_criada_id"]).limit(1).execute().data
            if resultado: painel_os(resultado[0], "pdf_os_nova")

elif menu == "📋 Chamados e O.S.":
    if not (permissao("ver_chamados") or permissao("gerenciar_os") or eh_administrador()):
        st.error("Acesso não autorizado."); st.stop()
    st.title("📋 Chamados e Ordens de Serviço")
    tab_ch, tab_os = st.tabs(["🎫 Chamados", "🛠️ Ordens de Serviço"])
    with tab_ch:
        try:
            rows = buscar_registros("chamados")
            if not (permissao("gerenciar_os") or eh_administrador()):
                rows = [r for r in rows if r.get("solicitante") == st.session_state.user]
            if not rows: st.info("Nenhum chamado encontrado.")
            else:
                df_ch = pd.DataFrame(rows)
                colunas = [c for c in ("numero", "titulo", "solicitante", "prioridade", "status", "tecnico", "created_at") if c in df_ch]
                st.dataframe(df_ch[colunas], use_container_width=True, hide_index=True)
                idx = st.selectbox("Selecionar chamado", range(len(rows)), format_func=lambda i: f"#{rows[i]['numero']} - {rows[i]['titulo']}")
                selecionado = rows[idx]
                st.write("**Descrição:**", selecionado.get("descricao") or "—")
                st.write("**Local:**", selecionado.get("local_setor") or "—")
                st.write("**Equipamento:**", selecionado.get("equipamento") or "—")
                if permissao("gerenciar_os"):
                    with st.form("editar_chamado"):
                        estados = ["Aberto", "Em triagem", "Em atendimento", "Aguardando peças", "Resolvido", "Fechado", "Cancelado"]
                        status = st.selectbox("Status do chamado", estados, index=estados.index(selecionado.get("status")) if selecionado.get("status") in estados else 0)
                        tecnico = st.text_input("Técnico responsável", value=selecionado.get("tecnico") or "")
                        diagnostico = st.text_area("Diagnóstico", value=selecionado.get("diagnostico") or "")
                        solucao = st.text_area("Solução", value=selecionado.get("solucao") or "")
                        if st.form_submit_button("Salvar chamado"):
                            atualizacao = {"status": status, "tecnico": tecnico, "diagnostico": diagnostico,
                                           "solucao": solucao, "updated_at": datetime.now().astimezone().isoformat()}
                            if status in ("Resolvido", "Fechado") and not selecionado.get("resolvido_em"):
                                atualizacao["resolvido_em"] = datetime.now().astimezone().isoformat()
                            supabase.table("chamados").update(atualizacao).eq("id", selecionado["id"]).execute()
                            registrar_evento(selecionado["id"], "ATUALIZACAO", f"Status: {status}")
                            st.success("Chamado atualizado."); st.rerun()
                eventos = supabase.table("chamados_eventos").select("created_at,usuario,acao,detalhe").eq("chamado_id", selecionado["id"]).order("created_at", desc=True).execute().data
                if eventos:
                    st.subheader("Histórico do chamado")
                    st.dataframe(pd.DataFrame(eventos), use_container_width=True, hide_index=True)
                painel_exclusao_registro("chamado", selecionado)
        except Exception as e: st.error(f"Erro ao consultar chamados: {e}")
    with tab_os:
        try:
            registros_os = buscar_registros("ordens_servico")
            if not (permissao("gerenciar_os") or eh_administrador()):
                registros_os = [r for r in registros_os if r.get("solicitante") == st.session_state.user]
            if not registros_os: st.info("Nenhuma ordem de serviço encontrada.")
            else:
                df_os = pd.DataFrame(registros_os)
                colunas = [c for c in ("numero", "titulo", "solicitante", "prioridade", "status", "tecnico", "created_at") if c in df_os]
                st.dataframe(df_os[colunas], use_container_width=True, hide_index=True)
                idx_os = st.selectbox("Selecionar O.S.", range(len(registros_os)),
                                     format_func=lambda i: f"O.S. nº {registros_os[i]['numero']} - {registros_os[i]['titulo']}")
                selecionada_os = registros_os[idx_os]
                if permissao("gerenciar_os"):
                    with st.form("atualizar_os"):
                        status = st.selectbox("Status da O.S.", STATUS_OS,
                            index=STATUS_OS.index(selecionada_os.get("status")) if selecionada_os.get("status") in STATUS_OS else 0)
                        prioridade = st.selectbox("Prioridade", PRIORIDADES,
                            index=PRIORIDADES.index(selecionada_os.get("prioridade")) if selecionada_os.get("prioridade") in PRIORIDADES else 1)
                        tecnico = st.text_input("Técnico", value=selecionada_os.get("tecnico") or "")
                        diagnostico = st.text_area("Diagnóstico", value=selecionada_os.get("diagnostico") or "")
                        solucao = st.text_area("Serviço executado / Solução", value=selecionada_os.get("solucao") or "")
                        if st.form_submit_button("Salvar O.S.", type="primary"):
                            atualizacao = {"status": status, "prioridade": prioridade, "tecnico": tecnico,
                                           "diagnostico": diagnostico, "solucao": solucao,
                                           "updated_at": datetime.now().astimezone().isoformat()}
                            if status in ("Concluída", "Encerrada") and not selecionada_os.get("resolvido_em"):
                                atualizacao["resolvido_em"] = datetime.now().astimezone().isoformat()
                            supabase.table("ordens_servico").update(atualizacao).eq("id", selecionada_os["id"]).execute()
                            st.success("O.S. atualizada."); st.rerun()
                    st.subheader("Materiais utilizados na O.S.")
                    produtos_os = buscar_dados("produtos")
                    if not produtos_os.empty:
                        escolhas = {f"#{r['id']} - {r['nome']} (saldo {r['quantidade']})": r for _, r in produtos_os.iterrows()}
                        with st.form("material_os"):
                            item = escolhas[st.selectbox("Produto", list(escolhas))]
                            quantidade = st.number_input("Quantidade utilizada", min_value=1, step=1)
                            if st.form_submit_button("Registrar saída para O.S."):
                                try:
                                    supabase.rpc("consumir_material_ordem_servico", {
                                        "p_os_id": selecionada_os["id"], "p_produto_id": int(item["id"]),
                                        "p_quantidade": int(quantidade), "p_operador": st.session_state.user}).execute()
                                    st.success("Material baixado e vinculado à O.S."); st.rerun()
                                except Exception as e: st.error(f"Falha ao registrar material: {e}")
                    materiais = supabase.table("os_materiais").select("produto_nome,quantidade,operador,created_at").eq("os_id", selecionada_os["id"]).execute().data
                    if materiais:
                        st.subheader("Materiais utilizados")
                        st.dataframe(pd.DataFrame(materiais), use_container_width=True, hide_index=True)
                painel_os(selecionada_os, "pdf_os_consulta")
                painel_exclusao_registro("os", selecionada_os)
        except Exception as e: st.error(f"Erro ao consultar ordens de serviço: {e}")

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
        busca_id = st.text_input("🔎 Buscar produto pelo ID", placeholder="Digite o ID do produto (ex.: 5)",
                                  help="A busca é feita exclusivamente pelo ID cadastrado do produto.")
        chaves = list(op.keys())
        if busca_id.strip():
            chaves = [chave for chave, prod in op.items() if str(prod["id"]) == busca_id.strip()]
            if not chaves:
                st.warning("Nenhum produto encontrado com esse ID.")
                st.stop()
        escolha = st.selectbox("Selecione o Produto", chaves)
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
