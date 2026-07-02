import streamlit as st
import sqlite3
import pandas as pd

# Conectar ao banco de dados (será criado automaticamente)
conn = sqlite3.connect('estoque.db', check_same_thread=False)
c = conn.cursor()

# Criar a tabela
c.execute('''
    CREATE TABLE IF NOT EXISTS produtos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        quantidade INTEGER NOT NULL,
        preco REAL NOT NULL
    )
''')
conn.commit()

# --- INTERFACE ---
st.set_page_config(page_title="Meu Estoque", page_icon="📦")
st.title("📦 Controle de Estoque Simples")

# Menu Lateral
st.sidebar.header("Novo Produto")
nome = st.sidebar.text_input("Nome")
qtd = st.sidebar.number_input("Quantidade", min_value=0, step=1)
preco = st.sidebar.number_input("Preço", min_value=0.0, step=0.1)

if st.sidebar.button("Salvar"):
    if nome:
        c.execute("INSERT INTO produtos (nome, quantidade, preco) VALUES (?, ?, ?)", (nome, qtd, preco))
        conn.commit()
        st.toast(f"Produto {nome} salvo!")
        st.rerun()
    else:
        st.error("O nome é obrigatório.")

# --- EXIBIÇÃO ---
st.subheader("Produtos Cadastrados")
df = pd.read_sql_query("SELECT * FROM produtos", conn)

if not df.empty:
    # Mostra a tabela
    st.dataframe(df, use_container_width=True, hide_index=True)
    
    # Opção para deletar
    st.divider()
    id_deletar = st.number_input("Digite o ID para excluir", min_value=1, step=1)
    if st.button("Excluir Produto"):
        c.execute("DELETE FROM produtos WHERE id = ?", (id_deletar,))
        conn.commit()
        st.rerun()
else:
    st.info("Nenhum produto no estoque ainda.")