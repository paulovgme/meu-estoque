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
