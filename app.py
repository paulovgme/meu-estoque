import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime
import time
import io
import uuid
import requests
from PIL import Image

# Imports para PDF (ReportLab)
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage, Table, TableStyle
from reportlab.lib.units import inch

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

def upload_foto_supabase(file):
    """Processa e sobe a foto para o bucket 'descartes' com tratamento de erro"""
    try:
        ext = file.name.split('.')[-1]
        nome_arquivo = f"{datetime.now().year}/{datetime.now().month:02d}/{uuid.uuid4()}.{ext}"
        
        img = Image.open(file)
        if img.mode in ("RGBA", "P"): img = img.convert("RGB")
        img.thumbnail((800, 800))
        
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='JPEG', quality=85)
        img_bytes = img_byte_arr.getvalue()

        supabase.storage.from_("descartes").upload(nome_arquivo, img_bytes, {"content-type": "image/jpeg"})
        url = supabase.storage.from_("descartes").get_public_url(nome_arquivo)
        
        return str(url) # Garante que retorna apenas a string da URL
    except Exception as e:
        st.error(f"Erro no upload: {e}")
        return None

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
                        "usuarios": user_data.get('can_usuarios', False),
                        "descarte": user_data.get('can_descarte', False)
                    }
                    st.rerun()
                else:
                    st.error("Usuário ou senha inválidos.")
            except Exception as e:
                st.error(f"Erro de conexão: {e}")
    st.stop()

# --- 5. MENU LATERAL ---
st.sidebar.title(f"👋 Olá, {st.session_state.nome_real}")
opcoes_menu = []
if st.session_state.perms.get('consultar'): opcoes_menu.append("📊 Consultar Estoque")
if st.session_state.perms.get('movimentar'): opcoes_menu.append("🔄 Entrada / Saída")
if st.session_state.perms.get('cadastrar'):  opcoes_menu.append("🆕 Cadastrar Produto")
if st.session_state.perms.get('admin'):      opcoes_menu.append("🔧 Correção de Produtos")
if st.session_state.perms.get('historico'):  opcoes_menu.append("📜 Histórico e Relatórios")
if st.session_state.perms.get('usuarios'):   opcoes_menu.append("👥 Gerenciar Usuários")
if st.session_state.perms.get('descarte') or st.session_state.perms.get('nivel') == 'administrador': 
    opcoes_menu.append("♻️ Descarte de Equipamentos")

menu = st.sidebar.radio("Navegação", opcoes_menu)
if st.sidebar.button("Sair / Logoff"):
    st.session_state.logado = False
    st.rerun()

# --- 6. TELAS DO SISTEMA ---

if menu == "📊 Consultar Estoque":
    st.title("📊 Consultar Estoque")
    df = buscar_dados("produtos")
    if not df.empty:
        termo = st.text_input("🔍 Pesquisar por ID, Nome, Marca ou Modelo").lower()
        df_f = df[df['nome'].str.lower().str.contains(termo, na=False) | df['marca'].str.lower().str.contains(termo, na=False)]
        st.dataframe(df_f, use_container_width=True, hide_index=True)

elif menu == "🔄 Entrada / Saída":
    st.title("🔄 Movimentação")
    df = buscar_dados("produtos")
    if not df.empty:
        opcoes = {f"ID: {p['id']} | {p['nome']}": p for _, p in df.iterrows()}
        escolha = st.selectbox("Produto", list(opcoes.keys()))
        item = opcoes[escolha]
        col1, col2 = st.columns(2)
        qtd = col1.number_input("Quantidade", min_value=1)
        tipo = col2.radio("Tipo", ["Saída (Baixa)", "Entrada (Compra)"])
        chamado = st.text_input("🎫 Chamado / Obs").strip()
        if st.button("Confirmar"):
            nova_q = item['quantidade'] + qtd if "Entrada" in tipo else item['quantidade'] - qtd
            if nova_q < 0: st.error("Saldo insuficiente")
            else:
                supabase.table("produtos").update({"quantidade": int(nova_q)}).eq("id", item['id']).execute()
                supabase.table("historico").insert({"operador": st.session_state.nome_real, "acao": tipo, "produto": item['nome'], "quantidade": int(qtd), "chamado": chamado, "data": datetime.now().isoformat()}).execute()
                st.success("Sucesso!"); time.sleep(1); st.rerun()

elif menu == "🆕 Cadastrar Produto":
    st.title("🆕 Novo Produto")
    with st.form("f_novo"):
        n = st.text_input("Nome*"); m = st.text_input("Marca"); mod = st.text_input("Modelo"); cat = st.text_input("Categoria")
        q = st.number_input("Qtd", min_value=0); a = st.number_input("Alerta", min_value=1)
        if st.form_submit_button("Cadastrar"):
            if n:
                supabase.table("produtos").insert({"nome":n, "marca":m, "modelo":mod, "categoria":cat, "quantidade":int(q), "alerta":int(a)}).execute()
                st.success("Cadastrado!"); time.sleep(1); st.rerun()

elif menu == "🔧 Correção de Produtos":
    st.title("🔧 Correção")
    df = buscar_dados("produtos")
    if not df.empty:
        aba_c, aba_e = st.tabs(["Editar", "Excluir"])
        with aba_c:
            sel = st.selectbox("Escolha o Produto", df['nome'].tolist())
            p = df[df['nome'] == sel].iloc[0]
            with st.form("f_edit"):
                nn = st.text_input("Nome", value=p['nome'])
                if st.form_submit_button("Salvar"):
                    supabase.table("produtos").update({"nome": nn}).eq("id", p['id']).execute()
                    st.success("Ok!"); st.rerun()
        with aba_e:
            ex_id = st.text_input("ID para excluir")
            if st.button("Excluir Definitivamente"):
                supabase.table("produtos").delete().eq("id", ex_id).execute()
                st.success("Excluído!"); st.rerun()

elif menu == "📜 Histórico e Relatórios":
    st.title("📜 Histórico")
    df_h = buscar_dados("historico")
    if not df_h.empty:
        df_h['data_f'] = df_h['data'].apply(formatar_data)
        st.dataframe(df_h[['data_f', 'produto', 'acao', 'quantidade', 'chamado', 'operador']], use_container_width=True)

# ==================================================
# 👥 GERENCIAR USUÁRIOS (COM CORREÇÃO DE CHECKBOXES)
# ==================================================
elif menu == "👥 Gerenciar Usuários":
    st.title("👥 Gestão de Usuários")
    aba_l, aba_a, aba_e = st.tabs(["📋 Lista", "➕ Novo", "✏️ Editar"])
    df_u = buscar_dados("usuarios")

    with aba_l: st.dataframe(df_u[['nome', 'usuario', 'nivel']], use_container_width=True)

    with aba_a:
        with st.form("novo_u"):
            no = st.text_input("Nome"); lo = st.text_input("Login"); se = st.text_input("Senha")
            ni = st.selectbox("Nível", ["comum", "administrador"])
            c1, c2 = st.columns(2)
            p1 = c1.checkbox("Consultar"); p2 = c1.checkbox("Movimentar"); p3 = c1.checkbox("Cadastrar")
            p4 = c2.checkbox("Correção"); p5 = c2.checkbox("Histórico"); p6 = c2.checkbox("Usuários"); p7 = c2.checkbox("♻️ Descarte")
            if st.form_submit_button("Criar"):
                supabase.table("usuarios").insert({"nome":no,"usuario":lo,"senha":se,"nivel":ni,"can_consultar":p1,"can_movimentar":p2,"can_cadastrar":p3,"can_admin":p4,"can_historico":p5,"can_usuarios":p6,"can_descarte":p7}).execute()
                st.success("Criado!"); st.rerun()

    with aba_e:
        if not df_u.empty:
            sel_u = st.selectbox("Selecione o usuário para editar", df_u['usuario'].tolist())
            u_atu = df_u[df_u['usuario'] == sel_u].iloc[0]
            with st.form("edit_u_completo"):
                enome = st.text_input("Nome Completo", value=u_atu['nome'])
                esenha = st.text_input("Nova Senha (vazio mantém)", type="password")
                enivel = st.selectbox("Nível", ["comum", "administrador"], index=0 if u_atu['nivel']=='comum' else 1)
                st.write("--- Permissões de Acesso ---")
                col1, col2 = st.columns(2)
                e1 = col1.checkbox("📊 Consultar estoque", value=bool(u_atu.get('can_consultar', False)))
                e2 = col1.checkbox("🔄 Entrada / Saída", value=bool(u_atu.get('can_movimentar', False)))
                e3 = col1.checkbox("🆕 Cadastrar Produto", value=bool(u_atu.get('can_cadastrar', False)))
                e4 = col2.checkbox("🔧 Correção de produtos", value=bool(u_atu.get('can_admin', False)))
                e5 = col2.checkbox("📜 Histórico e Relatórios", value=bool(u_atu.get('can_historico', False)))
                e6 = col2.checkbox("👥 Gerenciar usuários", value=bool(u_atu.get('can_usuarios', False)))
                e7 = col2.checkbox("♻️ Descarte de equipamentos", value=bool(u_atu.get('can_descarte', False)))
                
                if st.form_submit_button("Atualizar Usuário"):
                    upd = {"nome": enome, "nivel": enivel, "can_consultar": e1, "can_movimentar": e2, "can_cadastrar": e3, "can_admin": e4, "can_historico": e5, "can_usuarios": e6, "can_descarte": e7}
                    if esenha: upd["senha"] = esenha
                    supabase.table("usuarios").update(upd).eq("usuario", sel_u).execute()
                    st.success("Usuário atualizado!"); time.sleep(1); st.rerun()

# ==================================================
# ♻️ MÓDULO DE DESCARTE (COM EDIÇÃO E CORREÇÃO DE FOTO)
# ==================================================
elif menu == "♻️ Descarte de Equipamentos":
    st.title("♻️ Descarte de Equipamentos")
    aba_n, aba_l, aba_p = st.tabs(["➕ Novo Descarte", "📋 Lista de Descartes", "📄 Relatório PDF"])

    with aba_n:
        with st.form("f_desc", clear_on_submit=True):
            p_n = st.text_input("Produto*")
            cat = st.selectbox("Categoria", ["Periférico", "Monitor", "Computador", "Notebook", "Celular", "Impressora", "Rede", "Outros"])
            mar = st.text_input("Marca"); mod = st.text_input("Modelo")
            ser = st.text_input("Série"); pat = st.text_input("Patrimônio")
            def_p = st.text_area("Defeito*")
            mot = st.selectbox("Motivo", ["Defeito irreparável", "Danificado", "Obsoleto", "Outros"])
            obs = st.text_area("Observações")
            f_arq = st.file_uploader("Foto", type=["jpg","png","webp"])
            vin = st.checkbox("Pertence ao estoque")
            id_e = None
            if vin:
                df_prods = buscar_dados("produtos")
                if not df_prods.empty:
                    d_p = {f"{r['id']} - {r['nome']}": r['id'] for _, r in df_prods.iterrows()}
                    sel_p = st.selectbox("Vincular a:", list(d_p.keys()))
                    id_e = d_p[sel_p]

            if st.form_submit_button("Cadastrar"):
                if p_n and def_p:
                    u_foto = upload_foto_supabase(f_arq) if f_arq else None
                    supabase.table("descartes").insert({"produto":p_n,"categoria":cat,"marca":mar,"modelo":mod,"numero_serie":ser,"patrimonio":pat,"defeito":def_p,"motivo_descarte":mot,"observacao":obs,"foto_url":u_foto,"responsavel":st.session_state.nome_real,"usuario_login":st.session_state.user,"produto_id_estoque":id_e}).execute()
                    st.success("Registrado!"); time.sleep(1); st.rerun()

    with aba_l:
        df_d = buscar_dados("descartes")
        if not df_d.empty:
            st.dataframe(df_d[['id','produto','status','responsavel']], use_container_width=True)
            sel_d = st.selectbox("Gerenciar ID:", df_d['id'].tolist())
            if sel_d:
                it = df_d[df_d['id'] == sel_d].iloc[0]
                col1, col2 = st.columns([1, 2])
                with col1:
                    # CORREÇÃO DO BUG DA FOTO
                    if it['foto_url'] and str(it['foto_url']) != "None":
                        try: st.image(str(it['foto_url']), use_container_width=True)
                        except: st.warning("Erro ao carregar imagem.")
                    else: st.info("Sem foto.")
                
                with col2:
                    st.write(f"**{it['produto']}** ({it['status']})")
                    st.write(f"Defeito: {it['defeito']}")
                    
                    with st.expander("📝 Editar Informações / Adicionar Foto"):
                        with st.form(f"edit_desc_{sel_d}"):
                            en_p = st.text_input("Produto", value=it['produto'])
                            en_m = st.text_input("Marca", value=it['marca'])
                            en_mo = st.text_input("Modelo", value=it['modelo'])
                            en_se = st.text_input("Série", value=it['numero_serie'])
                            en_pa = st.text_input("Patrimônio", value=it['patrimonio'])
                            en_de = st.text_area("Defeito", value=it['defeito'])
                            en_ob = st.text_area("Obs", value=it['observacao'])
                            en_fo = st.file_uploader("Nova Foto", type=["jpg","png","webp"])
                            if st.form_submit_button("Salvar Alterações"):
                                d_up = {"produto":en_p,"marca":en_m,"modelo":en_mo,"numero_serie":en_se,"patrimonio":en_pa,"defeito":en_de,"observacao":en_ob}
                                if en_fo: d_up["foto_url"] = upload_foto_supabase(en_fo)
                                supabase.table("descartes").update(d_up).eq("id", sel_d).execute()
                                st.success("Atualizado!"); time.sleep(1); st.rerun()

                    n_st = st.selectbox("Mudar Status", ["🟡 Aguardando descarte", "🔵 Em avaliação", "🟢 Aprovado para descarte", "🔴 Descartado"])
                    if st.button("Atualizar Status"):
                        d_st = {"status": n_st}
                        if n_st == "🔴 Descartado": d_st["data_descarte"] = datetime.now().isoformat()
                        supabase.table("descartes").update(d_st).eq("id", sel_d).execute()
                        st.success("Status Ok!"); st.rerun()

                    if it['status'] == "🟢 Aprovado para descarte" and it['produto_id_estoque']:
                        if st.button("♻️ EFETIVAR DESCARTE (BAIXA NO ESTOQUE)"):
                            res_p = supabase.table("produtos").select("quantidade, nome").eq("id", it['produto_id_estoque']).execute()
                            if res_p.data and res_p.data[0]['quantidade'] > 0:
                                supabase.table("produtos").update({"quantidade": res_p.data[0]['quantidade'] - 1}).eq("id", it['produto_id_estoque']).execute()
                                supabase.table("descartes").update({"status": "🔴 Descartado", "data_descarte": datetime.now().isoformat()}).eq("id", sel_d).execute()
                                st.success("Estoque baixado!"); time.sleep(1); st.rerun()

    with aba_p:
        st.subheader("Gerar PDF Profissional")
        df_pdf = buscar_dados("descartes")
        if not df_pdf.empty:
            f_st = st.selectbox("Filtro Status", ["Todos"] + df_pdf['status'].unique().tolist())
            if st.button("Gerar PDF"):
                df_f = df_pdf if f_st == "Todos" else df_pdf[df_pdf['status'] == f_st]
                buffer = io.BytesIO()
                doc = SimpleDocTemplate(buffer, pagesize=letter)
                elements = []
                styles = getSampleStyleSheet()
                elements.append(Paragraph("RELATÓRIO DE DESCARTE DE EQUIPAMENTOS", styles['Title']))
                elements.append(Paragraph(f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}", styles['Normal']))
                elements.append(Spacer(1, 12))

                for _, r in df_f.iterrows():
                    data = [[f"ID #{r['id']} - {r['produto']}", ""], ["Defeito:", r['defeito']], ["Status:", r['status']], ["Resp:", r['responsavel']]]
                    t = Table(data, colWidths=[1.5*inch, 4.5*inch])
                    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.lightgrey),('GRID',(0,0),(-1,-1),0.5,colors.grey)]))
                    elements.append(t)
                    if r['foto_url']:
                        try:
                            resp = requests.get(r['foto_url']); img_io = io.BytesIO(resp.content)
                            img = RLImage(img_io, width=2*inch, height=1.5*inch)
                            elements.append(img)
                        except: pass
                    elements.append(Spacer(1, 20))
                
                doc.build(elements)
                st.download_button("📥 Baixar PDF", buffer.getvalue(), "relatorio.pdf", "application/pdf")
