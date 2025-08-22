import streamlit as st
import pandas as pd
import requests
from io import BytesIO
import re, os, json
from datetime import datetime
from pathlib import Path

st.set_page_config(page_title="Programação de Obras", page_icon="🛣️", layout="wide")

# ========================= CONFIG =========================
BASES_JSON_URL_FALLBACK = "https://grupoecorodovias-my.sharepoint.com/:u:/g/personal/leonardo_gomes_ecovias_com_br/EWd2C9GuYcpIhtR1mpajN0ABWz16fQsLJD-icy-_JkNUzA?download=1"

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
BASE_CSV = DATA_DIR / "base_atual.csv"
STATUS_JSON = DATA_DIR / "status.json"

REQUIRED_COLUMNS = ["Num Interv","Rodovia","Tipo","Inicio","DataFim","Sentido","Trecho","Executor"]

# ========================= HELPERS =========================
def get_bases_json_url():
    try:
        if "BASES_JSON_URL" in st.secrets:
            return st.secrets["BASES_JSON_URL"]
    except Exception:
        pass
    if os.getenv("BASES_JSON_URL"):
        return os.getenv("BASES_JSON_URL")
    cfg_path = Path("config.json")
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            if isinstance(cfg, dict) and "BASES_JSON_URL" in cfg:
                return cfg["BASES_JSON_URL"]
        except Exception:
            pass
    return BASES_JSON_URL_FALLBACK

def parse_km_token(token: str):
    if pd.isna(token):
        return None
    s = str(token).strip()
    m = re.match(r"^\s*(\d+)\s*\+\s*(\d+)\s*$", s)
    if m:
        km = int(m.group(1)); mtrs = int(m.group(2))
        return km + mtrs/1000.0
    s2 = s.replace(",", ".")
    try:
        return float(s2)
    except:
        return None

def split_trecho_to_kms(trecho: str):
    if pd.isna(trecho):
        return None, None, None, None
    s = str(trecho)
    parts = s.split("-")
    if len(parts) == 2:
        left = parts[0].strip()
        right = parts[1].strip()
    else:
        left = s.strip(); right = s.strip()

    def fmt_disp(tok):
        m = re.match(r"^\s*(\d+)\s*\+\s*(\d+)\s*$", tok)
        if m:
            return f"{int(m.group(1)):03d}+{int(m.group(2)):03d}"
        t = tok.replace(",", ".")
        try:
            val = float(t)
            km = int(val)
            mtrs = int(round((val - km)*1000))
            return f"{km:03d}+{mtrs:03d}"
        except:
            return tok

    disp_ini = fmt_disp(left)
    disp_fim = fmt_disp(right)
    num_ini = parse_km_token(left)
    num_fim = parse_km_token(right)
    return disp_ini, disp_fim, num_ini, num_fim

def detect_excel_engine(content: bytes, filename_hint: str):
    # PK\x03\x04 -> XLSX (zip),  D0 CF 11 E0 -> XLS (OLE2)
    if content[:4] == b"PK\x03\x04":
        return "openpyxl"
    if content[:8] == b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1" or content[:4] == b"\xD0\xCF\x11\xE0":
        return "xlrd"
    # fallback by filename
    lf = filename_hint.lower()
    if lf.endswith(".xls") and not lf.endswith(".xlsx"):
        return "xlrd"
    return "openpyxl"

def safe_read_excel_from_url(url: str):
    '''Baixa um Excel e tenta ler com engine apropriado.
    Retorna (df, filename_hint, info), onde info traz http_status, content_type, engine e mensagens de erro.
    '''
    info = {"url": url, "http_status": None, "content_type": None, "filename": None, "engine": None, "error": None}
    if not url or not isinstance(url, str) or not url.strip():
        info["error"] = "URL vazia"
        return None, None, info
    try:
        r = requests.get(url, timeout=40, allow_redirects=True)
        info["http_status"] = r.status_code
        info["content_type"] = r.headers.get("Content-Type", "")
        if r.status_code != 200:
            info["error"] = f"HTTP {r.status_code}"
            return None, None, info
        content = r.content
        # nome do arquivo (Content-Disposition) ou final da URL
        fname = None
        cd = r.headers.get("Content-Disposition", "")
        m = re.search(r'filename="?([^"]+)"?', cd)
        if m:
            fname = m.group(1)
        else:
            fname = url.split("?")[0].split("/")[-1] or "arquivo.xlsx"
        info["filename"] = fname

        # detectar engine pelo magic bytes
        engine = detect_excel_engine(content, fname)
        info["engine"] = engine
        try:
            df = pd.read_excel(BytesIO(content), engine=engine)
            return df, fname, info
        except Exception as e1:
            # tenta engine alternativo por garantia
            alt = "xlrd" if engine == "openpyxl" else "openpyxl"
            info["engine"] = f"fallback:{alt}"
            try:
                df = pd.read_excel(BytesIO(content), engine=alt)
                return df, fname, info
            except Exception as e2:
                info["error"] = f"Erro lendo Excel com {engine}: {e1} | fallback {alt}: {e2}"
                return None, fname, info
    except Exception as e:
        info["error"] = f"Exceção de rede: {e}"
        return None, None, info

def ensure_required_columns(df: pd.DataFrame):
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Colunas obrigatórias ausentes: {missing}")

def publish_combined_base(df: pd.DataFrame, status: dict):
    df.to_csv(BASE_CSV, index=False, encoding="utf-8")
    STATUS_JSON.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")

def load_local_base():
    if BASE_CSV.exists():
        try:
            df = pd.read_csv(BASE_CSV, parse_dates=["Inicio","DataFim"], dayfirst=True)
            return df
        except Exception:
            return None
    return None

def enrich_dataframe(df: pd.DataFrame):
    df = df.copy()
    df["Data"] = pd.to_datetime(df["Inicio"]).dt.date
    df["Hora"] = pd.to_datetime(df["Inicio"]).dt.time
    df["Periodo"] = df["Hora"].apply(lambda h: "Diurno" if getattr(h, "hour", None)==7 else ("Noturno" if getattr(h, "hour", None)==22 else "Outro"))
    kms = df["Trecho"].apply(split_trecho_to_kms)
    df["KM Inicial"] = kms.apply(lambda t: t[0])
    df["KM Final"]   = kms.apply(lambda t: t[1])
    df["KM_ini_num"] = kms.apply(lambda t: t[2])
    df["KM_fim_num"] = kms.apply(lambda t: t[3])
    return df

def render_copy_card(num: str, count: int = 1):
    badge = f'<span style="margin-left:8px;padding:2px 8px;border-radius:999px;background:#e5e7eb;font-size:12px;">aparece {count}×</span>' if count>1 else ""
    st.markdown('''
    <div style="display:flex;align-items:center;gap:12px;margin:6px 0;padding:10px 12px;border:1px solid #e5e7eb;border-radius:12px;background:#f8fafc;">
        <div style="font-size:22px;font-weight:800;letter-spacing:0.2px;">''' + num + '''</div>
        ''' + badge + '''
        <button onclick="navigator.clipboard.writeText(\'''' + num + '''\')" style="margin-left:auto;padding:6px 12px;border:1px solid #0F766E;border-radius:10px;background:#0F766E;color:white;cursor:pointer;">
            Copiar
        </button>
    </div>
    ''', unsafe_allow_html=True)

# ========================= DATA LOADING =========================
error_banner = None
df_local = load_local_base()

if df_local is None:
    url_json = get_bases_json_url()
    combined = []
    per_base_status = []
    json_problem = None
    json_http = None

    try:
        rj = requests.get(url_json, timeout=40)
        json_http = rj.status_code
        if rj.status_code != 200:
            json_problem = f"Não consegui baixar o bases.json (HTTP {rj.status_code})."
        else:
            try:
                j = rj.json()
            except Exception:
                try:
                    j = json.loads(rj.text)
                except Exception:
                    json_problem = "O conteúdo do bases.json não é um JSON válido."
                    j = {}
    except Exception as e:
        json_problem = f"Erro de conexão ao baixar o bases.json: {e}"

    bases_defs = []
    if not json_problem and isinstance(j, dict):
        for key in ["semana_atual","proxima_semana"]:
            item = j.get(key, {})
            url = (item or {}).get("url", "")
            label = (item or {}).get("label", key.replace("_"," ").title())
            bases_defs.append({"key": key, "url": url, "label": label})

    for bd in bases_defs:
        url = (bd["url"] or "").strip()
        label = bd["label"] or "(sem nome)"
        if not url:
            per_base_status.append({"label": label, "status": "não configurada", "rows": 0, "filename": "-", "detail": "URL vazia"})
            continue
        dfb, fname, info = safe_read_excel_from_url(url)
        if dfb is None:
            per_base_status.append({
                "label": label, "status": "indisponível", "rows": 0,
                "filename": info.get("filename") or "-", "detail": f"HTTP={info.get('http_status')}; CT={info.get('content_type')}; eng={info.get('engine')}; err={info.get('error')}"
            })
            continue
        try:
            ensure_required_columns(dfb)
            dfb["Base"] = label
            combined.append(dfb)
            per_base_status.append({"label": label, "status": "ok", "rows": int(len(dfb)), "filename": fname or "-", "detail": f"eng={info.get('engine')}"})
        except Exception as e:
            per_base_status.append({"label": label, "status": "erro colunas", "rows": 0, "filename": fname or "-", "detail": str(e)})

    if json_problem and not combined:
        error_banner = f"Erro ao carregar ponteiro (bases.json): {json_problem}"
        if json_http:
            error_banner += f" (HTTP {json_http})"

    if combined:
        df_local = pd.concat(combined, ignore_index=True)
        total_rows = int(len(df_local))
        status_obj = {
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "bases": per_base_status,
            "total_rows": total_rows
        }
        try:
            publish_combined_base(df_local, status_obj)
        except Exception:
            pass
    else:
        status_obj = {
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "bases": per_base_status,
            "total_rows": 0
        }
        try:
            STATUS_JSON.write_text(json.dumps(status_obj, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

# ========================= SIDEBAR (STATUS) =========================
st.sidebar.title("Status da Base")
st.sidebar.caption("Fonte: SharePoint (somente leitura)")

def read_status():
    if STATUS_JSON.exists():
        try:
            return json.loads(STATUS_JSON.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None

status_info = read_status()

if error_banner and (df_local is None or df_local.empty):
    st.sidebar.error("Falha ao carregar o ponteiro (bases.json).")

if status_info and "bases" in status_info:
    for item in status_info["bases"]:
        lab = item.get("label","(sem nome)")
        sts = item.get("status","-")
        rows = item.get("rows",0)
        fn = item.get("filename","-")
        detail = item.get("detail","")
        st.sidebar.markdown(f"**{lab}**\n\n- Status: `{sts}`\n- Linhas: **{rows}**\n- Arquivo: `{fn}`")
        if sts != "ok" and detail:
            with st.sidebar.expander("Detalhes", expanded=False):
                st.code(detail, language="text")
    st.sidebar.markdown(f"**Total combinado:** {status_info.get('total_rows',0)}")
    st.sidebar.caption(f"Atualizado em: {status_info.get('updated_at','-')}")
else:
    st.sidebar.warning("Nenhuma base disponível.")

# ========================= MAIN =========================
st.title("🔎 Programação de Obras")

if error_banner and (df_local is None or df_local.empty):
    st.error(error_banner)
    st.stop()

if df_local is None or df_local.empty:
    st.warning("Nenhuma base disponível no momento. Verifique o bases.json no SharePoint.")
    st.stop()

# Enriquecer dados e filtros
df = enrich_dataframe(df_local)

def with_placeholder(series):
    opts = [str(x) for x in series.dropna().astype(str).unique() if str(x).strip()!=""]
    return ["— Selecione —"] + sorted(opts)

rodovia = st.selectbox("Rodovia", with_placeholder(df["Rodovia"]), index=0)
tipo    = st.selectbox("Tipo (Serviço)", with_placeholder(df["Tipo"]), index=0)

datas   = ["— Selecione —"] + [str(d) for d in sorted(df["Data"].dropna().unique().tolist())]
data_sel_str = st.selectbox("Data (de Início)", datas, index=0)

c1, c2 = st.columns(2)
with c1:
    periodo = st.selectbox("Período", ["— Selecione —","Diurno","Noturno"], index=0)
with c2:
    sentido = st.selectbox("Sentido", with_placeholder(df["Sentido"]), index=0)

executor = st.selectbox("Executor", with_placeholder(df["Executor"]), index=0)

all_filled = all([
    rodovia != "— Selecione —",
    tipo != "— Selecione —",
    data_sel_str != "— Selecione —",
    periodo != "— Selecione —",
    sentido != "— Selecione —",
    executor != "— Selecione —",
])
btn = st.button("Buscar", type="primary", disabled=(not all_filled))

if btn:
    data_sel = pd.to_datetime(data_sel_str).date()
    f = df[
        (df["Rodovia"].astype(str)==rodovia) &
        (df["Tipo"].astype(str)==tipo) &
        (df["Data"]==data_sel) &
        (df["Sentido"].astype(str)==sentido) &
        (df["Executor"].astype(str)==executor)
    ].copy()
    if periodo == "Diurno":
        f = f[f["Periodo"]=="Diurno"]
    elif periodo == "Noturno":
        f = f[f["Periodo"]=="Noturno"]

    f = f.sort_values(["Rodovia","KM_ini_num","KM_fim_num","Sentido","Inicio"], na_position="last")

    if f.empty:
        st.error("Nenhum registro encontrado para os filtros informados.")
    else:
        st.subheader("Números de Programação encontrados")
        counts = f["Num Interv"].astype(str).value_counts()
        for num, cnt in counts.items():
            render_copy_card(num, int(cnt))

        cols = ["Num Interv","Rodovia","KM Inicial","KM Final","Sentido","Tipo","Executor","Inicio","DataFim"]
        if "Base" in f.columns:
            cols.append("Base")
        st.dataframe(f[cols], use_container_width=True, hide_index=True)
