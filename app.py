# --- TELA: HISTÓRICO GERAL ---
elif menu == "📜 Histórico Geral":
    st.title("📜 Histórico de Movimentações")
    try:
        res = supabase.table("historico").select("*").order("data", desc=True).limit(100).execute()
        if res.data:
            df_h = pd.DataFrame(res.data)
            
            # Botão de exportar histórico
            csv_h = df_h.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Baixar Histórico (CSV)", csv_h, "historico_ti.csv", "text/csv")
            
            st.write("Últimas movimentações:")
            st.dataframe(df_h, use_container_width=True) 
        else:
            st.info("Histórico vazio.")
    except Exception as e:
        st.error(f"Erro ao carregar histórico: {e}")
