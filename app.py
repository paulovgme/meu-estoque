import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime
import time
import io
import uuid
import requests
import json
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
    if pd.isna(data_iso) or not data_iso:
        return "N/A"
    try:
        dt = pd.to_datetime(data_iso)
        return dt.strftime("%d/%m/%Y %H:%M")
    except:
        return str(data_iso)

def upload_fotos_multiplas(files):
    """Sobe múltiplas fotos e retorna uma string com URLs separadas por vírgula"""
    urls = []
    for file in files:
        try:
            ext = file.name.split('.')[-1]
            nome_arquivo = f"{datetime.now().year}/{datetime.now().month:02d}/{uuid.uuid4()}.{ext}"
            
            img = Image.open(file)
            if img.mode in ("RGBA", "P"): img = img.convert("RGB")
            img.thumbnail((1200, 1200)) # Qualidade um pouco maior para PDF
            
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='JPEG', quality=85)
            
            supabase.storage.from_("descartes").upload(nome_arquivo, img_byte_arr.getvalue(), {"content-type": "image/jpeg"})
            url = supabase.storage.from_("descartes").get_public_url(nome_arquivo)
            urls.append(str(url))
        except Exception as e:
            st.error(f"Erro no upload de {file.name}: {e}")
    return ",".join(urls) if urls else None

# --- 4. CONTROLE DE ACESSO ---
if 'logado' not in st.session_state:
    st.session_state.logado = False
    st.session_state.perms = {}
    st.session_state.user = None
    st.session_state.nome_real = None

if not st.session_state.logado:
    st.title("🔐 Acesso ao Sistema")
    with st.form("login_form"):
        u = st.text_input("Usuário").strip().lower()
        p = st.text_input("Senha", type="password").strip()
        if st.form_submit_button("Entrar", use_container_width=True):
            try:
                res = supabase.table("usuarios").select("*").eq("usuario", u).eq("senha", p).execute()
                if res.data:
                    d = res.data[0]
                    st.session_state.logado = True
                    st.session_state.user = u
                    st.session_state.nome_real = d.get('nome', u)
                    st.session_state.perms = {
                        "nivel": d.get('nivel', 'comum'),
                        "consultar": d.get('can_consultar', True),
                        "movimentar": d.get('can_movimentar', False),
                        "cadastrar": d.get('can_cadastrar', False),
                        "admin": d.get('can_admin', False),
                        "historico": d.get('can_historico', False),
                        "usuarios": d.get('can_usuarios', False),
                        "descarte": d.get('can_descarte', False)
                    }
                    st.rerun()
                else: st.error("Incorreto")
            except Exception as e: st.error(f"Erro: {e}")
    st.stop()

# --- 5. MENU LATERAL (REORDENADO) ---
st.sidebar.title(f"👋 Olá, {st.session_state.nome_real}")
opcoes_menu = []
# Ordem solicitada: Consultar, Movimentação, Cadastrar, Correção, Histórico, Descarte e por ÚLTIMO Gerenciar Usuários
if st.session_state.perms.get('consultar'): opcoes_menu.append("📊 Consultar Estoque")
if st.session_state.perms.get('movimentar'): opcoes_menu.append("🔄 Entrada / Saída")
if st.session_state.perms.get('cadastrar'):  opcoes_menu.append("🆕 Cadastrar Produto")
if st.session_state.perms.get('admin'):      opcoes_menu.append("🔧 Correção de Produtos")
if st.session_state.perms.get('historico'):  opcoes_menu.append("📜 Histórico e Relatórios")
if st.session_state.perms.get('descarte') or st.session_state.perms.get('nivel') == 'administrador': 
    opcoes_menu.append("♻️ Descarte de Equipamentos")
if st.session_state.perms.get('usuarios'):   opcoes_menu.append("👥 Gerenciar Usuários")

menu = st.sidebar.radio("Navegação", opcoes_menu)
if st.sidebar.button("Sair / Logoff"):
    st.session_state.logado = False
    st.rerun()

# --- 6. TELAS PADRÃO (Preservadas) ---

if menu == "📊 Consultar Estoque":
    st.title("📊 Consultar Estoque")
    df = buscar_dados("produtos")
    if not df.empty:
        termo = st.text_input("🔍 Pesquisar").lower()
        df_f = df[df['nome'].str.lower().str.contains(termo, na=False)]
        st.dataframe(df_f, use_container_width=True, hide_index=True)

elif menu == "🔄 Entrada / Saída":
    st.title("🔄 Movimentação")
    df = buscar_dados("produtos")
    if not df.empty:
        op = {f"{p['id']} - {p['nome']}": p for _, p in df.iterrows()}
        escolha = st.selectbox("Selecione", list(op.keys()))
        item = op[escolha]
        col1, col2 = st.columns(2)
        qtd = col1.number_input("Qtd", min_value=1)
        tipo = col2.radio("Operação", ["Saída (Baixa)", "Entrada (Compra)"])
        cha = st.text_input("Chamado / Obs")
        if st.button("Confirmar", type="primary"):
            nq = item['quantidade'] + qtd if "Entrada" in tipo else item['quantidade'] - qtd
            if nq < 0: st.error("Sem saldo")
            else:
                supabase.table("produtos").update({"quantidade": int(nq)}).eq("id", item['id']).execute()
                supabase.table("historico").insert({"operador":st.session_state.nome_real,"acao":tipo,"produto":item['nome'],"quantidade":int(qtd),"chamado":cha,"data":datetime.now().isoformat()}).execute()
                st.success("Ok!"); time.sleep(1); st.rerun()

elif menu == "🆕 Cadastrar Produto":
    st.title("🆕 Cadastrar")
    with st.form("f_cad"):
        n = st.text_input("Nome*"); m = st.text_input("Marca"); mod = st.text_input("Modelo"); cat = st.text_input("Categoria")
        q = st.number_input("Qtd", min_value=0); a = st.number_input("Alerta", min_value=1)
        if st.form_submit_button("Salvar"):
            if n:
                supabase.table("produtos").insert({"nome":n,"marca":m,"modelo":mod,"categoria":cat,"quantidade":int(q),"alerta":int(a)}).execute()
                st.success("Cadastrado!"); time.sleep(1); st.rerun()

elif menu == "🔧 Correção de Produtos":
    st.title("🔧 Correção")
    df = buscar_dados("produtos")
    if not df.empty:
        aba_c, aba_e = st.tabs(["Editar", "Excluir"])
        with aba_c:
            sel = st.selectbox("Produto", df['nome'].tolist())
            p = df[df['nome'] == sel].iloc[0]
            with st.form("f_cor"):
                nn = st.text_input("Nome", value=p['nome'])
                if st.form_submit_button("Atualizar"):
                    supabase.table("produtos").update({"nome":nn}).eq("id", p['id']).execute()
                    st.rerun()
        with aba_e:
            ex_id = st.text_input("ID para exclusão")
            if st.button("Excluir Produto Permanentemente"):
                supabase.table("produtos").delete().eq("id", ex_id).execute()
                st.success("Excluído!"); time.sleep(1); st.rerun()

elif menu == "📜 Histórico e Relatórios":
    st.title("📜 Histórico")
    df_h = buscar_dados("historico")
    if not df_h.empty:
        df_h['data_f'] = df_h['data'].apply(formatar_data)
        st.dataframe(df_h[['data_f','produto','acao','quantidade','chamado','operador']], use_container_width=True)

# ==================================================
# 👥 GERENCIAR USUÁRIOS (COM EXCLUSÃO E PERMISSÕES)
# ==================================================
elif menu == "👥 Gerenciar Usuários":
    st.title("👥 Gestão de Usuários")
    aba_l, aba_a, aba_e = st.tabs(["📋 Lista", "➕ Novo Usuário", "✏️ Editar e Excluir"])
    df_u = buscar_dados("usuarios")

    with aba_l: st.dataframe(df_u[['nome', 'usuario', 'nivel']], use_container_width=True)

    with aba_a:
        with st.form("nu"):
            n = st.text_input("Nome"); u = st.text_input("Login"); s = st.text_input("Senha")
            ni = st.selectbox("Nível", ["comum", "administrador"])
            c1, c2 = st.columns(2)
            p1=c1.checkbox("Consultar"); p2=c1.checkbox("Movimentar"); p3=c1.checkbox("Cadastrar")
            p4=c2.checkbox("Correção"); p5=c2.checkbox("Histórico"); p6=c2.checkbox("Usuários"); p7=c2.checkbox("Descarte")
            if st.form_submit_button("Criar"):
                supabase.table("usuarios").insert({"nome":n,"usuario":u,"senha":s,"nivel":ni,"can_consultar":p1,"can_movimentar":p2,"can_cadastrar":p3,"can_admin":p4,"can_historico":p5,"can_usuarios":p6,"can_descarte":p7}).execute()
                st.success("Criado!"); st.rerun()

    with aba_e:
        if not df_u.empty:
            sel_u = st.selectbox("Selecione o usuário", df_u['usuario'].tolist())
            u_d = df_u[df_u['usuario'] == sel_u].iloc[0]
            with st.form("edit_u"):
                en = st.text_input("Nome", value=u_d['nome'])
                es = st.text_input("Nova Senha (vazio mantém)", type="password")
                st.write("Permissões:")
                c1, c2 = st.columns(2)
                e1=c1.checkbox("📊 Consultar", value=bool(u_d.get('can_consultar')))
                e2=c1.checkbox("🔄 Movimentar", value=bool(u_d.get('can_movimentar')))
                e3=c1.checkbox("🆕 Cadastrar", value=bool(u_d.get('can_cadastrar')))
                e4=c2.checkbox("🔧 Correção", value=bool(u_d.get('can_admin')))
                e5=c2.checkbox("📜 Histórico", value=bool(u_d.get('can_historico')))
                e6=c2.checkbox("👥 Gerenciar", value=bool(u_d.get('can_usuarios')))
                e7=c2.checkbox("♻️ Descarte", value=bool(u_d.get('can_descarte')))
                if st.form_submit_button("Salvar Alterações"):
                    up = {"nome":en, "can_consultar":e1,"can_movimentar":e2,"can_cadastrar":e3,"can_admin":e4,"can_historico":e5,"can_usuarios":e6,"can_descarte":e7}
                    if es: up["senha"] = es
                    supabase.table("usuarios").update(up).eq("usuario", sel_u).execute()
                    st.success("Salvo!"); time.sleep(1); st.rerun()
            
            st.divider()
            if st.button("🗑️ EXCLUIR USUÁRIO DEFINITIVAMENTE", type="primary"):
                if sel_u == st.session_state.user: st.error("Não pode excluir a si mesmo.")
                else:
                    supabase.table("usuarios").delete().eq("usuario", sel_u).execute()
                    st.success("Usuário removido!"); time.sleep(1); st.rerun()

# ==================================================
# ♻️ MÓDULO DE DESCARTE (MÚLTIPLAS FOTOS E EXCLUSÃO)
# ==================================================
elif menu == "♻️ Descarte de Equipamentos":
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
            f_arqs = st.file_uploader("Fotos (Pode selecionar várias)", type=["jpg","png","webp"], accept_multiple_files=True)
            if st.form_submit_button("Cadastrar para Descarte"):
                if p_n and def_p:
                    u_fotos = upload_fotos_multiplas(f_arqs)
                    supabase.table("descartes").insert({"produto":p_n,"categoria":cat,"marca":mar,"modelo":mod,"numero_serie":ser,"patrimonio":pat,"defeito":def_p,"foto_url":u_fotos,"responsavel":st.session_state.nome_real,"usuario_login":st.session_state.user}).execute()
                    st.success("Registrado!"); time.sleep(1); st.rerun()

    with aba_l:
        df_d = buscar_dados("descartes")
        if not df_d.empty:
            st.dataframe(df_d[['id','produto','status','responsavel']], use_container_width=True)
            sel_id = st.selectbox("Selecionar ID para Gerenciar/Excluir", df_d['id'].tolist())
            if sel_id:
                it = df_d[df_d['id'] == sel_id].iloc[0]
                c1, c2 = st.columns([1, 2])
                with c1:
                    if it['foto_url']:
                        urls = str(it['foto_url']).split(',')
                        for u in urls: st.image(u, use_container_width=True)
                    else: st.info("Sem fotos.")
                
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
                            st.success("Atualizado!"); st.rerun()
                    
                    if st.button("🗑️ EXCLUIR REGISTRO DE DESCARTE", type="primary"):
                        supabase.table("descartes").delete().eq("id", sel_id).execute()
                        st.success("Removido!"); time.sleep(1); st.rerun()

    with aba_p:
        st.subheader("Gerar Relatório PDF Professional")
        if st.button("Gerar PDF de todos os descartes"):
            df_pdf = buscar_dados("descartes")
            buffer = io.BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=letter)
            elements = []
            styles = getSampleStyleSheet()
            elements.append(Paragraph("RELATÓRIO DE DESCARTE DE EQUIPAMENTOS", styles['Title']))
            
            for _, r in df_pdf.iterrows():
                data = [[f"ID #{r['id']} - {r['produto']}", ""], ["Defeito:", r['defeito']], ["Status:", r['status']]]
                t = Table(data, colWidths=[1.5*cm*2.5, 10*cm]) # Ajuste largura
                t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.lightgrey),('GRID',(0,0),(-1,-1),0.5,colors.grey)]))
                elements.append(t)
                
                if r['foto_url']:
                    urls = str(r['foto_url']).split(',')
                    for u in urls:
                        try:
                            resp = requests.get(u)
                            img_io = io.BytesIO(resp.content)
                            # TAMANHO SOLICITADO: 10cm x 15cm
                            img = RLImage(img_io, width=10*cm, height=15*cm)
                            elements.append(Spacer(1, 10))
                            elements.append(img)
                        except: pass
                elements.append(Spacer(1, 30))
            
            doc.build(elements)
            st.download_button("📥 Baixar Relatório PDF", buffer.getvalue(), f"relatorio_descarte_{datetime.now().strftime('%d_%m')}.pdf", "application/pdf")
