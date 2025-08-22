import streamlit as st
import pandas as pd
import requests
from io import BytesIO
import re, os, json
from datetime import datetime
from pathlib import Path

st.set_page_config(page_title="Programação de Obras", page_icon="🛣️", layout="wide")

# ========================= CONFIG =========================
# Você pode definir a URL do bases.json por (ordem de prioridade):
# 1) st.secrets["BASES_JSON_URL"]
# 2) variável de ambiente BASES_JSON_URL
# 3) arquivo local config.json { "BASES_JSON_URL": "https://..." }
# 4) constante abaixo (edite aqui se quiser fixar no código)
BASES_JSON_URL_FALLBACK = "https://grupoecorodovias-my.sharepoint.com/:u:/g/personal/leonardo_gomes_ecovias_com_br/EWd2C9GuYcpIhtR1mpajN0ABWz16fQsLJD-icy-_JkNUzA?download=1"

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
BASE_CSV = DATA_DIR / "base_atual.csv"
STATUS_JSON = DATA_DIR / "status.json"

REQUIRED_COLUMNS = ["Num Interv","Rodovia","Tipo","Inicio","DataFim","Sentido","Trecho","Executor"]

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

def safe_read_excel_from_url(url: str):
    if not url or not isinstance(url, str) or not url.strip():
        return None, None
    try:
        r = requests.get(url, timeout=30, allow_redirects=True)
        if r.status_code != 200:
            return None, None
        content = r.content
        fname = None
        cd = r.headers.get("Content-Disposition", "")
        m = re.search(r'filename="?([^"]+)"?', cd)
        if m:
            fname = m.group(1)
        else:
            fname = url.split("?")[0].split("/")[-1] or "arquivo.xlsx"

        lower = fname.lower()
        engine = "openpyxl"
        if lower.endswith(".xls") and not lower.endswith(".xlsx"):
            engine = "xlrd"
        df = pd.read_excel(BytesIO(content), engine=engine)
        return df, fname
    except Exception:
        return None, None

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
    st.markdown(f"""
    <div style="display:flex;align-items:center;gap:12px;margin:6px 0;padding:10px 12px;border:1px solid #e5e7eb;border-radius:12px;background:#f8fafc;">
        <div style="font-size:22px;font-weight:800;letter-spacing:0.2px;">{num}</div>
        {badge}
        <button onclick="navigator.clipboard.writeText('{num}')" style="margin-left:auto;padding:6px 12px;border:1px solid #0F766E;border-radius:10px;background:#0F766E;color:white;cursor:pointer;">
            Copiar
        </button>
    </div>
    """, unsafe_allow_html=True)

status_sidebar_lines = []
error_banner = None

df_local = load_local_base()
if df_local is None:
    url_json = get_bases_json_url()
    combined = []
    per_base_status = []
    json_problem = None
    try:
        rj = requests.get(url_json, timeout=30)
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
        json_problem = "Erro de conexão ao baixar o bases.json."

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
            per_base_status.append({"label": label, "status": "não configurada", "rows": 0, "filename": "-"})
            continue
        dfb, fname = safe_read_excel_from_url(url)
        if dfb is None:
            per_base_status.append({"label": label, "status": "indisponível", "rows": 0, "filename": fname or "-"})
            continue
        try:
            ensure_required_columns(dfb)
            dfb["Base"] = label
            combined.append(dfb)
            per_base_status.append({"label": label, "status": "ok", "rows": int(len(dfb)), "filename": fname or "-"})
        except Exception as e:
            per_base_status.append({"label": label, "status": f"erro colunas", "rows": 0, "filename": fname or "-"})

    if json_problem and not combined:
        error_banner = f"Erro ao carregar ponteiro (bases.json): {json_problem}"

    if combined:
        df_local = pd.concat(combined, ignore_index=True)
        total_rows = int(len(df_local))
        status_obj = {
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "bases": per_base_status,
            "total_rows": total_rows
        }
        try:
            df_local.to_csv("data/base_atual.csv", index=False, encoding="utf-8")
            Path("data/status.json").write_text(json.dumps(status_obj, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

st.sidebar.title("Status da Base")
st.sidebar.caption("Fonte: SharePoint (somente leitura)")

if error_banner:
    st.sidebar.error("Falha ao carregar o ponteiro (bases.json).")

def read_status():
    p = Path("data/status.json")
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None

status_info = read_status()

if status_info and "bases" in status_info:
    for item in status_info["bases"]:
        lab = item.get("label","(sem nome)")
        sts = item.get("status","-")
        rows = item.get("rows",0)
        fn = item.get("filename","-")
        st.sidebar.markdown(f"**{lab}**\n\n- Status: `{sts}`\n- Linhas: **{rows}**\n- Arquivo: `{fn}`")
    st.sidebar.markdown(f"**Total combinado:** {status_info.get('total_rows',0)}")
    st.sidebar.caption(f"Atualizado em: {status_info.get('updated_at','-')}")
else:
    if df_local is not None and not df_local.empty:
        st.sidebar.markdown(f"**Linhas (total):** {len(df_local)}")
        st.sidebar.caption("Status parcial (sem detalhes por base).")
    else:
        st.sidebar.warning("Nenhuma base disponível.")

st.title("🔎 Programação de Obras")

if error_banner and (df_local is None or df_local.empty):
    st.error(error_banner)
    st.stop()

if df_local is None or df_local.empty:
    st.warning("Nenhuma base disponível no momento. Verifique o bases.json no SharePoint.")
    st.stop()

df = (lambda d: (d.assign(
    Data=pd.to_datetime(d["Inicio"]).dt.date,
    Hora=pd.to_datetime(d["Inicio"]).dt.time,
    Periodo=pd.to_datetime(d["Inicio"]).dt.time.map(lambda h: "Diurno" if getattr(h, "hour", None)==7 else ("Noturno" if getattr(h, "hour", None)==22 else "Outro"))
)))(df_local.copy())

kms = df["Trecho"].apply(split_trecho_to_kms)
df["KM Inicial"] = kms.apply(lambda t: t[0])
df["KM Final"]   = kms.apply(lambda t: t[1])
df["KM_ini_num"] = kms.apply(lambda t: t[2])
df["KM_fim_num"] = kms.apply(lambda t: t[3])

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
            badge = f'<span style="margin-left:8px;padding:2px 8px;border-radius:999px;background:#e5e7eb;font-size:12px;">aparece {int(cnt)}×</span>' if int(cnt)>1 else ""
            st.markdown(f"""
            <div style="display:flex;align-items:center;gap:12px;margin:6px 0;padding:10px 12px;border:1px solid #e5e7eb;border-radius:12px;background:#f8fafc;">
                <div style="font-size:22px;font-weight:800;letter-spacing:0.2px;">{num}</div>
                {badge}
                <button onclick="navigator.clipboard.writeText('{num}')" style="margin-left:auto;padding:6px 12px;border:1px solid #0F766E;border-radius:10px;background:#0F766E;color:white;cursor:pointer;">
                    Copiar
                </button>
            </div>
            """, unsafe_allow_html=True)
        cols = ["Num Interv","Rodovia","KM Inicial","KM Final","Sentido","Tipo","Executor","Inicio","DataFim"]
        if "Base" in f.columns: cols.append("Base")
        st.dataframe(f[cols], use_container_width=True, hide_index=True)
