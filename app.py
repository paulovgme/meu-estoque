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
