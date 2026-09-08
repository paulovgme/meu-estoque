import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime
import time
import io
import uuid
import requests
from PIL import Image
# Imports para PDF
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage, Table, TableStyle, PageBreak
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
    """Processa e sobe a foto para o bucket 'descartes'"""
    try:
        ext = file.name.split('.')[-1]
        nome_arquivo = f"{datetime.now().year}/{datetime.now().month:02d}/{uuid.uuid4()}.{ext}"
        
        # Redimensionar com Pillow para não sobrecarregar
        img = Image.open(file)
        if img.mode in ("RGBA", "P"): img = img.convert("RGB")
        img.thumbnail((800, 800))
        
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='JPEG', quality=85)
        img_bytes = img_byte_arr.getvalue()

        # Upload para o bucket
        supabase.storage.from_("descartes").upload(nome_arquivo, img_bytes, {"content-type": "image/jpeg"})
        
        # Retorna URL pública
        return supabase.storage.from_("descartes").get_public_url(nome_arquivo)
    except Exception as e:
        st.error(f"Erro ao fazer upload da foto: {e}")
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
                        "descarte": user_data.get('can_descarte', False) # NOVA PERMISSÃO
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
if st.session_state.perms.get('descarte') or st.session_state.perms.get('nivel') == 'administrador': 
    opcoes_menu.append("♻️ Descarte de Equipamentos")

menu = st.sidebar.radio("Navegação", opcoes_menu)

if st.sidebar.button("Sair / Logoff"):
    st.session_state.logado = False
    st.rerun()

# --- 6. TELAS DO SISTEMA ---

# [TELAS EXISTENTES PRESERVADAS]
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
        num_chamado = st.text_input("🎫 Chamado / Obs", placeholder="Chamado ou NF").strip()

        if st.button("Confirmar Movimentação", type="primary", use_container_width=True):
            if "Saída" in tipo_op and not num_chamado:
                st.error("Informe o chamado para saídas.")
            else:
                nova_qtd = item_sel['quantidade'] + qtd_mov if "Entrada" in tipo_op else item_sel['quantidade'] - qtd_mov
                if nova_qtd < 0: st.error("Saldo insuficiente!")
                else:
                    supabase.table("produtos").update({"quantidade": int(nova_qtd)}).eq("id", item_sel['id']).execute()
                    supabase.table("historico").insert({"operador": st.session_state.nome_real,"acao": tipo_op,"produto": item_sel['nome'],"quantidade": int(qtd_mov),"chamado": num_chamado,"data": datetime.now().isoformat()}).execute()
                    st.success("Movimentação realizada!")
                    time.sleep(1)
                    st.rerun()

elif menu == "🆕 Cadastrar Produto":
    st.title("🆕 Novo Produto")
    with st.form("novo_p", clear_on_submit=True):
        n = st.text_input("Nome do Produto").strip()
        m = st.text_input("Marca"); mod = st.text_input("Modelo"); cat = st.text_input("Categoria")
        q = st.number_input("Qtd Inicial", min_value=0); a = st.number_input("Alerta Mínimo", min_value=1)
        if st.form_submit_button("Cadastrar"):
            if n:
                supabase.table("produtos").insert({"nome":n, "marca":m, "modelo":mod, "categoria":cat, "quantidade":int(q), "alerta":int(a)}).execute()
                st.success("Cadastrado!")
                time.sleep(1); st.rerun()
            else: st.error("Nome obrigatório")

elif menu == "🔧 Correção de Produtos":
    st.title("🔧 Correção e Exclusão")
    df = buscar_dados("produtos")
    if not df.empty:
        aba_c, aba_e = st.tabs(["📝 Corrigir", "🚨 Excluir"])
        with aba_c:
            dic_id = {f"ID: {r['id']} - {r['nome']}": r['id'] for _, r in df.iterrows()}
            sel_id = dic_id[st.selectbox("Selecione para Corrigir", list(dic_id.keys()))]
            p = df[df['id'] == sel_id].iloc[0]
            with st.form("f_corr"):
                nc = st.text_input("Nome", value=p['nome'])
                mc = st.text_input("Marca", value=p['marca'])
                if st.form_submit_button("Salvar"):
                    supabase.table("produtos").update({"nome": nc, "marca": mc}).eq("id", sel_id).execute()
                    st.success("Corrigido!"); time.sleep(1); st.rerun()
        with aba_e:
            bid = st.text_input("ID para excluir")
            if st.button("Confirmar Exclusão Irreversível", type="primary"):
                supabase.table("produtos").delete().eq("id", bid).execute()
                st.success("Excluído!"); time.sleep(1); st.rerun()

elif menu == "📜 Histórico e Relatórios":
    st.title("📜 Histórico")
    df_h = buscar_dados("historico")
    if not df_h.empty:
        df_h['data_f'] = df_h['data'].apply(formatar_data)
        st.dataframe(df_h[['data_f', 'produto', 'acao', 'quantidade', 'chamado', 'operador']], use_container_width=True, hide_index=True)

elif menu == "👥 Gerenciar Usuários":
    st.title("👥 Gestão de Usuários")
    aba_l, aba_a, aba_e = st.tabs(["📋 Lista", "➕ Novo", "✏️ Editar"])
    df_u = buscar_dados("usuarios")
    with aba_l: st.dataframe(df_u[['nome', 'usuario', 'nivel']], use_container_width=True)
    with aba_a:
        with st.form("new_u"):
            no = st.text_input("Nome"); lo = st.text_input("Login"); se = st.text_input("Senha", type="password")
            col1, col2 = st.columns(2)
            p1 = col1.checkbox("Consultar", True); p2 = col1.checkbox("Movimentar"); p3 = col1.checkbox("Cadastrar")
            p4 = col2.checkbox("Admin"); p5 = col2.checkbox("Histórico"); p6 = col2.checkbox("Usuários")
            p7 = col2.checkbox("♻️ Descarte") # CHECKBOX NOVO
            if st.form_submit_button("Criar"):
                supabase.table("usuarios").insert({"nome":no, "usuario":lo, "senha":se, "can_consultar":p1, "can_movimentar":p2, "can_cadastrar":p3, "can_admin":p4, "can_historico":p5, "can_usuarios":p6, "can_descarte":p7}).execute()
                st.success("Usuário Criado!"); time.sleep(1); st.rerun()
    with aba_e:
        if not df_u.empty:
            usel = st.selectbox("Editar usuário", df_u['usuario'].tolist())
            u_data = df_u[df_u['usuario'] == usel].iloc[0]
            with st.form("edit_u"):
                en = st.text_input("Nome", value=u_data['nome'])
                ed = st.checkbox("♻️ Descarte", value=bool(u_data.get('can_descarte', False)))
                if st.form_submit_button("Atualizar"):
                    supabase.table("usuarios").update({"nome": en, "can_descarte": ed}).eq("usuario", usel).execute()
                    st.success("Atualizado!"); time.sleep(1); st.rerun()

# ==================================================
# ♻️ NOVO MÓDULO: DESCARTE DE EQUIPAMENTOS
# ==================================================
elif menu == "♻️ Descarte de Equipamentos":
    st.title("♻️ Descarte de Equipamentos")
    
    aba_novo, aba_lista, aba_pdf = st.tabs(["➕ Novo Descarte", "📋 Equipamentos para Descarte", "📄 Relatório PDF"])

    # --- ABA: NOVO DESCARTE ---
    with aba_novo:
        with st.form("form_descarte", clear_on_submit=True):
            st.subheader("Informações do Equipamento")
            col1, col2 = st.columns(2)
            prod_nome = col1.text_input("Produto*", placeholder="Ex: Monitor Dell 24")
            categoria = col1.selectbox("Categoria", ["Periférico", "Monitor", "Computador", "Notebook", "Celular", "Impressora", "Rede", "Armazenamento", "Outros"])
            marca = col2.text_input("Marca")
            modelo = col2.text_input("Modelo")
            
            col3, col4 = st.columns(2)
            serie = col3.text_input("Número de Série")
            patrimonio = col4.text_input("Patrimônio")
            
            defeito = st.text_area("Defeito / Problema*", placeholder="Descreva o problema técnico...")
            
            motivo = st.selectbox("Motivo do Descarte", [
                "Defeito irreparável", "Danificado", "Obsoleto", 
                "Custo de reparo elevado", "Sem peças de reposição", 
                "Fim de vida útil", "Outros"
            ])
            
            obs = st.text_area("Observação Livre")
            
            foto_file = st.file_uploader("Foto do Equipamento (JPG, PNG, WEBP)", type=["jpg", "jpeg", "png", "webp"])
            if foto_file:
                st.image(foto_file, width=250, caption="Prévia da foto")
            
            st.divider()
            vincular = st.checkbox("☑ Equipamento pertence ao estoque")
            id_estoque = None
            if vincular:
                df_p = buscar_dados("produtos")
                if not df_p.empty:
                    prods_dict = {f"ID {r['id']} | {r['nome']} ({r['quantidade']} un)": r['id'] for _, r in df_p.iterrows()}
                    sel_p = st.selectbox("Selecione o produto correspondente no estoque", list(prods_dict.keys()))
                    id_estoque = prods_dict[sel_p]
            
            if st.form_submit_button("Cadastrar para Descarte", use_container_width=True):
                if not prod_nome or not defeito:
                    st.error("Preencha os campos obrigatórios (*)")
                else:
                    url_img = upload_foto_supabase(foto_file) if foto_file else None
                    
                    dados_d = {
                        "produto": prod_nome, "categoria": categoria, "marca": marca, "modelo": modelo,
                        "numero_serie": serie, "patrimonio": patrimonio, "defeito": defeito,
                        "motivo_descarte": motivo, "observacao": obs, "foto_url": url_img,
                        "status": "🟡 Aguardando descarte", "responsavel": st.session_state.nome_real,
                        "usuario_login": st.session_state.user, "produto_id_estoque": id_estoque
                    }
                    
                    try:
                        supabase.table("descartes").insert(dados_d).execute()
                        st.success("Equipamento registrado com sucesso!")
                        time.sleep(1.5); st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao salvar: {e}")

    # --- ABA: LISTA DE DESCARTES ---
    with aba_lista:
        df_d = buscar_dados("descartes")
        if not df_d.empty:
            # Filtros
            c_f1, c_f2, c_f3 = st.columns(3)
            f_status = c_f1.multiselect("Status", df_d['status'].unique())
            f_cat = c_f2.multiselect("Categoria", df_d['categoria'].unique())
            f_busca = c_f3.text_input("Buscar (Série/Patrimônio/Nome)").lower()
            
            df_df = df_d.copy()
            if f_status: df_df = df_df[df_df['status'].isin(f_status)]
            if f_cat: df_df = df_df[df_df['categoria'].isin(f_cat)]
            if f_busca:
                df_df = df_df[df_df['produto'].str.lower().str.contains(f_busca) | 
                              df_df['numero_serie'].str.lower().str.contains(f_busca) |
                              df_df['patrimonio'].str.lower().str.contains(f_busca)]
            
            st.dataframe(df_df[['id', 'produto', 'marca', 'numero_serie', 'status', 'responsavel']], use_container_width=True, hide_index=True)
            
            st.divider()
            sel_view = st.selectbox("Selecione um ID para ver Detalhes e Gerenciar", df_df['id'].tolist() if not df_df.empty else [])
            
            if sel_view:
                item = df_d[df_d['id'] == sel_view].iloc[0]
                col_i1, col_i2 = st.columns([1, 2])
                
                with col_i1:
                    if item['foto_url']:
                        st.image(item['foto_url'], caption=f"Foto do {item['produto']}")
                    else:
                        st.info("Sem foto cadastrada")
                
                with col_i2:
                    st.subheader(f"Equipamento #{item['id']} - {item['produto']}")
                    st.write(f"**Marca/Modelo:** {item['marca']} / {item['modelo']}")
                    st.write(f"**Série/Patrimônio:** {item['numero_serie']} / {item['patrimonio']}")
                    st.write(f"**Defeito:** {item['defeito']}")
                    st.write(f"**Status Atual:** :blue[{item['status']}]")
                    
                    novo_st = st.selectbox("Alterar Status", ["🟡 Aguardando descarte", "🔵 Em avaliação", "🟢 Aprovado para descarte", "🔴 Descartado"])
                    
                    if st.button("Atualizar Status"):
                        upd_d = {"status": novo_st}
                        if novo_st == "🔴 Descartado": upd_d["data_descarte"] = datetime.now().isoformat()
                        supabase.table("descartes").update(upd_d).eq("id", item['id']).execute()
                        st.success("Status atualizado!")
                        time.sleep(1); st.rerun()
                    
                    # LOGICA DE BAIXA NO ESTOQUE
                    if item['status'] == "🟢 Aprovado para descarte" and item['produto_id_estoque']:
                        st.warning("⚠️ Este item está vinculado ao estoque principal.")
                        if st.button("♻️ EFETIVAR DESCARTE E BAIXAR ESTOQUE"):
                            # Buscar qtd atual
                            res_p = supabase.table("produtos").select("quantidade, nome").eq("id", item['produto_id_estoque']).execute()
                            if res_p.data:
                                q_atual = res_p.data[0]['quantidade']
                                if q_atual > 0:
                                    # Baixa estoque
                                    supabase.table("produtos").update({"quantidade": q_atual - 1}).eq("id", item['produto_id_estoque']).execute()
                                    # Update Descarte
                                    supabase.table("descartes").update({"status": "🔴 Descartado", "data_descarte": datetime.now().isoformat()}).eq("id", item['id']).execute()
                                    # Histórico
                                    supabase.table("historico").insert({"operador": st.session_state.nome_real,"acao": "Saída (Descarte)","produto": res_p.data[0]['nome'],"quantidade": 1,"chamado": f"Descarte #{item['id']}","data": datetime.now().isoformat()}).execute()
                                    st.success("Baixa realizada e item marcado como Descartado!")
                                    time.sleep(1.5); st.rerun()
                                else:
                                    st.error("Erro: Estoque insuficiente (0) para realizar a baixa.")
        else:
            st.info("Nenhum equipamento em processo de descarte.")

    # --- ABA: RELATÓRIO PDF (REPORTLAB) ---
    with aba_pdf:
        st.subheader("📄 Geração de Relatório de Descartes")
        df_pdf = buscar_dados("descartes")
        if not df_pdf.empty:
            # Filtros do PDF
            f_pdf_status = st.selectbox("Filtrar Status para PDF", ["Todos"] + df_pdf['status'].unique().tolist())
            
            if st.button("Gerar Relatório em PDF Professional", type="primary"):
                with st.spinner("Gerando PDF..."):
                    df_final_pdf = df_pdf.copy()
                    if f_pdf_status != "Todos": df_final_pdf = df_final_pdf[df_final_pdf['status'] == f_pdf_status]
                    
                    # Lógica ReportLab
                    buffer = io.BytesIO()
                    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
                    elements = []
                    styles = getSampleStyleSheet()
                    
                    # Estilos customizados
                    style_header = ParagraphStyle('Header', parent=styles['Normal'], fontSize=14, leading=16, spaceAfter=10, textColor=colors.HexColor("#1F4E79"), alignment=1, fontName='Helvetica-Bold')
                    style_item = ParagraphStyle('Item', parent=styles['Normal'], fontSize=10, leading=12, spaceBefore=5)

                    # Cabeçalho
                    elements.append(Paragraph("SISTEMA TI - ESTOQUE PRO", style_header))
                    elements.append(Paragraph("RELATÓRIO DE EQUIPAMENTOS PARA DESCARTE", style_header))
                    elements.append(Paragraph(f"Data de Geração: {datetime.now().strftime('%d/%m/%Y %H:%M')} | Responsável: {st.session_state.nome_real}", styles['Normal']))
                    elements.append(Paragraph(f"Total de itens: {len(df_final_pdf)}", styles['Normal']))
                    elements.append(Spacer(1, 0.2*inch))

                    for _, row in df_final_pdf.iterrows():
                        # Caixa de dados
                        data = [
                            [f"EQUIPAMENTO #{row['id']}", ""],
                            ["Produto:", row['produto']],
                            ["Categoria:", row['categoria']],
                            ["Marca/Modelo:", f"{row['marca']} / {row['modelo']}"],
                            ["Série/Patrimônio:", f"{row['numero_serie']} / {row['patrimonio']}"],
                            ["Defeito:", row['defeito']],
                            ["Status:", row['status']],
                            ["Data Cadastro:", formatar_data(row['data_cadastro'])]
                        ]
                        t = Table(data, colWidths=[1.5*inch, 4.5*inch])
                        t.setStyle(TableStyle([
                            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#D9E1F2")),
                            ('TEXTCOLOR', (0,0), (-1,0), colors.black),
                            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
                            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                            ('LEFTPADDING', (0,0), (-1,-1), 6),
                        ]))
                        elements.append(t)
                        
                        # Inserir Foto se existir
                        if row['foto_url']:
                            try:
                                response = requests.get(row['foto_url'])
                                img_io = io.BytesIO(response.content)
                                img_rl = RLImage(img_io, width=2.5*inch, height=1.8*inch)
                                img_rl.hAlign = 'LEFT'
                                elements.append(Spacer(1, 5))
                                elements.append(img_rl)
                            except:
                                elements.append(Paragraph("[Erro ao carregar imagem]", styles['Italic']))
                        else:
                            elements.append(Paragraph("Sem foto cadastrada", styles['Italic']))
                        
                        elements.append(Spacer(1, 0.3*inch))

                    # Footer simplificado
                    def add_footer(canvas, doc):
                        canvas.saveState()
                        canvas.setFont('Helvetica', 8)
                        canvas.drawString(inch, 0.5*inch, f"Página {doc.page}")
                        canvas.drawRightString(7.5*inch, 0.5*inch, f"Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')}")
                        canvas.restoreState()

                    doc.build(elements, onFirstPage=add_footer, onLaterPages=add_footer)
                    
                    st.download_button(
                        label="📥 Baixar Relatório em PDF",
                        data=buffer.getvalue(),
                        file_name=f"relatorio_descartes_{datetime.now().strftime('%d_%m_%Y_%H%M')}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
