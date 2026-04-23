import math, io, base64, re, json
import requests
from PIL import Image, ImageDraw
import streamlit as st
from streamlit_folium import st_folium
import folium
import anthropic

# ─────────────────────────────────────────────
# Конфигурация
# ─────────────────────────────────────────────
st.set_page_config(page_title="БГ Гео Анализатор", page_icon="🛰️", layout="wide", initial_sidebar_state="collapsed")

DEFAULT_LAT, DEFAULT_LON, DEFAULT_ZOOM = 42.8742, 25.3187, 14
MAF_URL         = "https://bg-imagery.openstreetmap.org/layer/maf-orthophoto-latest/{z}/{x}/{y}.png"
MAF_ATTRIBUTION = "© МЗХ България"
BUFFER_OPTIONS  = {"110м": 0.001, "220м": 0.002, "440м": 0.004, "880м": 0.008}
EXAMPLE_QUESTIONS = [
    "🌿 Какъв е доминиращият тип земно покритие?",
    "🛣️ Опиши видимата пътна мрежа.",
    "💧 Има ли водни обекти или влажни зони?",
    "🏗️ Какъв тип застрояване е видимо?",
    "🌡️ Оцени риска от горски пожар.",
    "📐 Оцени дела на непропускливите повърхности.",
]
SYSTEM_PROMPT = """Ти си експерт по дистанционни изследвания и геопространствен анализ с дълбоки познания за:
- Интерпретация на ортофото изображения (МЗХ ортофото, Sentinel, Landsat)
- Класификация на земеползването и земното покритие в България
- Разпознаване на градска, земеделска и горска инфраструктура
- Хидрология, релеф и геопространствен контекст за България

При анализ бъди конкретен — описвай типове покривност, инфраструктура, растителност, водни обекти и аномалии.
Когато споменаваш процентно разпределение на елементи (напр. 40% сгради, 30% зеленина, 20% пътища, 10% друго),
ВИНАГИ добавяй в края на отговора JSON блок в следния точен формат (без Markdown обвивка):
CHART_DATA:{"labels":["Елемент1","Елемент2"],"values":[40,30],"title":"Заглавие"}
Отговаряй изцяло на български."""

# ─────────────────────────────────────────────────────────────────────
# ТЕМИ
# ─────────────────────────────────────────────────────────────────────
THEMES = {
    "🌑 Тъмна": {
        "--bg-primary":    "#0a0e14",
        "--bg-secondary":  "#111720",
        "--bg-card":       "#151d28",
        "--bg-hover":      "#1c2736",
        "--accent":        "#00d4aa",
        "--accent-dim":    "#00a882",
        "--accent-glow":   "rgba(0,212,170,0.15)",
        "--text-primary":  "#e8edf5",
        "--text-secondary":"#7a8fa8",
        "--text-muted":    "#4a5a6e",
        "--border":        "#1e2d3d",
        "--border-accent": "#00d4aa44",
        "--danger":        "#ff4757",
        "--warning":       "#ffa502",
        "--input-bg":      "#1c2736",
        "--input-text":    "#e8edf5",
        "--input-placeholder": "#4a5a6e",
        "--chat-user-bg":  "#1c2736",
        "--chat-ai-bg":    "#151d28",
        "--radio-bg":      "#111720",
        "--radio-text":    "#e8edf5",
    },
    "☀️ Светла": {
        "--bg-primary":    "#f4f6f9",
        "--bg-secondary":  "#ffffff",
        "--bg-card":       "#ffffff",
        "--bg-hover":      "#e8edf5",
        "--accent":        "#0077cc",
        "--accent-dim":    "#005fa3",
        "--accent-glow":   "rgba(0,119,204,0.12)",
        "--text-primary":  "#1a2332",
        "--text-secondary":"#4a5a6e",
        "--text-muted":    "#8a9ab0",
        "--border":        "#d0dae8",
        "--border-accent": "#0077cc55",
        "--danger":        "#e03030",
        "--warning":       "#d97706",
        "--input-bg":      "#ffffff",
        "--input-text":    "#1a2332",
        "--input-placeholder": "#8a9ab0",
        "--chat-user-bg":  "#eef3fa",
        "--chat-ai-bg":    "#ffffff",
        "--radio-bg":      "#ffffff",
        "--radio-text":    "#1a2332",
    },
}

# ─────────────────────────────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────────────────────────────
def inject_css(theme: dict):
    vars_css = "\n".join(f"    {k}: {v};" for k, v in theme.items())
    st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Syne:wght@400;600;700;800&display=swap');
:root {{
{vars_css}
}}
html, body, [class*="css"] {{
    font-family: 'Syne', sans-serif !important;
    background-color: var(--bg-primary) !important;
    color: var(--text-primary) !important;
}}
.stApp {{ background-color: var(--bg-primary) !important; }}
header[data-testid="stHeader"] {{ background: transparent !important; border-bottom: none !important; }}

/* ── Хедър ── */
.geo-header {{ display:flex; align-items:center; gap:16px; padding:16px 0 20px 0;
    border-bottom:1px solid var(--border); margin-bottom:20px; }}
.geo-header-icon {{ width:42px; height:42px; background:var(--accent-glow);
    border:1px solid var(--border-accent); border-radius:10px;
    display:flex; align-items:center; justify-content:center; font-size:20px; }}
.geo-header-title {{ font-size:20px !important; font-weight:800 !important;
    color:var(--text-primary) !important; letter-spacing:-0.5px; margin:0 !important; }}
.geo-header-subtitle {{ font-family:'JetBrains Mono',monospace !important;
    font-size:10px !important; color:var(--accent) !important;
    letter-spacing:1.5px; text-transform:uppercase; }}
.geo-header-right {{ margin-left:auto; display:flex; align-items:center; gap:12px; }}

/* ── Стъпки ── */
.steps-bar {{ display:flex; gap:0; margin-bottom:20px; background:var(--bg-secondary);
    border:1px solid var(--border); border-radius:10px; padding:10px 20px; align-items:center; }}
.step-item {{ display:flex; align-items:center; gap:8px; flex:1; }}
.step-num {{ width:24px; height:24px; border-radius:50%; display:flex; align-items:center;
    justify-content:center; font-size:11px; font-weight:700;
    font-family:'JetBrains Mono',monospace !important; flex-shrink:0; }}
.step-num.done   {{ background:var(--accent); color:var(--bg-primary); }}
.step-num.active {{ background:var(--accent-glow); color:var(--accent); border:1px solid var(--accent); }}
.step-num.todo   {{ background:var(--bg-card); color:var(--text-muted); border:1px solid var(--border); }}
.step-label {{ font-size:12px; color:var(--text-secondary); }}
.step-label.active {{ color:var(--text-primary); font-weight:600; }}
.step-arrow {{ color:var(--text-muted); font-size:14px; margin:0 8px; }}

/* ── Section headers ── */
.geo-card-header {{ font-size:10px; font-family:'JetBrains Mono',monospace !important;
    color:var(--accent); letter-spacing:1.5px; text-transform:uppercase;
    margin-bottom:10px; display:flex; align-items:center; gap:8px; }}

/* ── Coord badge ── */
.coord-badge {{ background:var(--bg-secondary); border:1px solid var(--border-accent);
    border-radius:6px; padding:6px 10px; font-family:'JetBrains Mono',monospace !important;
    font-size:11px; color:var(--accent); display:inline-flex; align-items:center;
    gap:6px; margin-bottom:10px; }}

/* ── Status bar ── */
.status-bar {{ display:flex; align-items:center; gap:8px; padding:7px 12px;
    background:var(--bg-secondary); border-radius:6px; font-family:'JetBrains Mono',monospace !important;
    font-size:11px; color:var(--text-secondary); margin-bottom:10px; border:1px solid var(--border); }}
.status-dot {{ width:7px; height:7px; border-radius:50%; flex-shrink:0; }}
.status-dot.ready   {{ background:var(--accent); box-shadow:0 0 6px var(--accent); }}
.status-dot.waiting {{ background:var(--text-muted); }}
@keyframes pulse {{ 0%,100%{{opacity:1}} 50%{{opacity:0.3}} }}

/* ── Чат съобщения ── */
.chat-msg {{ padding:12px 14px; border-radius:10px; margin-bottom:10px;
    font-size:14px; line-height:1.7; color:var(--text-primary); }}
.chat-msg.user {{ background:var(--chat-user-bg); border:1px solid var(--border); margin-left:32px; }}
.chat-msg.assistant {{ background:var(--chat-ai-bg); border:1px solid var(--border-accent);
    border-left:3px solid var(--accent); }}
.chat-role {{ font-size:10px; font-family:'JetBrains Mono',monospace !important;
    letter-spacing:1px; text-transform:uppercase; margin-bottom:6px; font-weight:600; }}
.chat-role.user      {{ color:var(--text-muted); }}
.chat-role.assistant {{ color:var(--accent); }}

/* ── Бутони ── */
.stButton > button {{
    background:var(--accent) !important; color:var(--bg-primary) !important;
    border:none !important; border-radius:8px !important;
    font-family:'Syne',sans-serif !important; font-weight:700 !important;
    font-size:13px !important; width:100% !important;
    transition:all 0.2s !important; padding:10px 20px !important;
}}
.stButton > button:hover {{
    background:var(--accent-dim) !important; transform:translateY(-1px) !important;
    box-shadow:0 4px 16px var(--accent-glow) !important;
}}
.stButton > button:disabled {{
    background:var(--bg-hover) !important; color:var(--text-muted) !important;
    transform:none !important; box-shadow:none !important;
}}

/* ── Secondary бутони (буфери, теми) ── */
button[kind="secondary"] {{
    background:var(--bg-secondary) !important;
    color:var(--text-primary) !important;
    border:1px solid var(--border) !important;
    font-size:13px !important;
    font-weight:600 !important;
    padding:8px 12px !important;
    border-radius:8px !important;
    transition:all 0.2s !important;
}}
button[kind="secondary"]:hover {{
    border-color:var(--accent) !important;
    color:var(--accent) !important;
    background:var(--accent-glow) !important;
}}

/* ── Text input (въпрос) — ФИКСИРАНО ── */
div[data-testid="stTextInput"] input {{
    background:var(--input-bg) !important;
    color:var(--input-text) !important;
    border:1px solid var(--border) !important;
    border-radius:8px !important;
    font-family:'Syne',sans-serif !important;
    font-size:14px !important;
    padding:10px 14px !important;
    caret-color:var(--accent) !important;
}}
div[data-testid="stTextInput"] input::placeholder {{
    color:var(--input-placeholder) !important;
    opacity:1 !important;
}}
div[data-testid="stTextInput"] input:focus {{
    border-color:var(--accent) !important;
    box-shadow:0 0 0 2px var(--accent-glow) !important;
    outline:none !important;
}}

/* ── Chat input — ФИКСИРАНО ── */
div[data-testid="stChatInput"] textarea {{
    background:var(--input-bg) !important;
    color:var(--input-text) !important;
    font-family:'Syne',sans-serif !important;
    font-size:14px !important;
    border:1px solid var(--border) !important;
    border-radius:10px !important;
    caret-color:var(--accent) !important;
}}
div[data-testid="stChatInput"] textarea::placeholder {{
    color:var(--input-placeholder) !important;
    opacity:1 !important;
}}
div[data-testid="stChatInput"] > div {{
    background:var(--bg-card) !important;
    border:1px solid var(--border) !important;
    border-radius:10px !important;
}}

/* ── Sidebar ── */
[data-testid="stSidebar"] {{
    background:var(--bg-secondary) !important;
    border-right:1px solid var(--border) !important;
}}
[data-testid="stSidebar"] textarea, [data-testid="stSidebar"] input {{
    background:var(--bg-card) !important; border:1px solid var(--border) !important;
    border-radius:8px !important; color:var(--text-primary) !important;
    font-size:12px !important;
}}

/* ── Misc ── */
hr {{ border-color:var(--border) !important; }}
::-webkit-scrollbar {{ width:4px; height:4px; }}
::-webkit-scrollbar-track {{ background:var(--bg-primary); }}
::-webkit-scrollbar-thumb {{ background:var(--border); border-radius:2px; }}
#MainMenu, footer, .viewerBadge_container__1QSob {{ display:none !important; }}

/* ── Print шаблон ── */
@media print {{
    .no-print {{ display:none !important; }}
    body {{ background:white !important; color:black !important; }}
    .print-report {{ display:block !important; }}
}}
.print-report {{ display:none; }}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────
# ПОМОЩНИ ФУНКЦИИ
# ─────────────────────────────────────────────────────────────────────
def lat_lon_to_tile(lat, lon, zoom):
    n = 2 ** zoom
    x = int((lon + 180) / 360 * n)
    lat_rad = math.radians(lat)
    y = int((1 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2 * n)
    return x, y

def tile_to_lat_lon(x, y, zoom):
    n = 2 ** zoom
    lon = x / n * 360 - 180
    return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n)))), lon

def fetch_maf_tiles(lat, lon, buf, zoom=18):
    min_lon, max_lon = lon - buf, lon + buf
    min_lat, max_lat = lat - buf, lat + buf
    x_min, y_max = lat_lon_to_tile(min_lat, min_lon, zoom)
    x_max, y_min = lat_lon_to_tile(max_lat, max_lon, zoom)
    cols, rows, TS = x_max - x_min + 1, y_max - y_min + 1, 256
    canvas = Image.new("RGB", (cols * TS, rows * TS), (220, 225, 232))
    headers = {"User-Agent": "BGGeoChatbot/1.0 (gisbulgaria.bg)"}
    for row, ty in enumerate(range(y_min, y_max + 1)):
        for col, tx in enumerate(range(x_min, x_max + 1)):
            try:
                resp = requests.get(MAF_URL.format(z=zoom, x=tx, y=ty), timeout=10, headers=headers)
                if resp.status_code == 200:
                    canvas.paste(Image.open(io.BytesIO(resp.content)).convert("RGB"), (col * TS, row * TS))
            except Exception:
                pass
    nw_lat, nw_lon = tile_to_lat_lon(x_min, y_min, zoom)
    se_lat, se_lon = tile_to_lat_lon(x_max + 1, y_max + 1, zoom)
    tls, tls2 = se_lon - nw_lon, nw_lat - se_lat
    pw, ph = cols * TS, rows * TS
    l = max(0, int((min_lon - nw_lon) / tls * pw))
    t = max(0, int((nw_lat - max_lat) / tls2 * ph))
    r = min(pw, int((max_lon - nw_lon) / tls * pw))
    b = min(ph, int((nw_lat - min_lat) / tls2 * ph))
    cropped = canvas.crop((l, t, r, b))
    draw = ImageDraw.Draw(cropped)
    cx, cy, s = cropped.width // 2, cropped.height // 2, 14
    col_cross = (0, 180, 140)
    draw.line([(cx - s, cy), (cx + s, cy)], fill=col_cross, width=2)
    draw.line([(cx, cy - s), (cx, cy + s)], fill=col_cross, width=2)
    draw.ellipse([(cx - 5, cy - 5), (cx + 5, cy + 5)], outline=col_cross, width=2)
    return cropped

def img_to_b64(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()

def parse_chart_data(text: str):
    """Извлича CHART_DATA JSON от отговора на модела."""
    match = re.search(r'CHART_DATA:(\{.*?\})', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            return None
    return None

def clean_text(text: str) -> str:
    """Премахва CHART_DATA блока от текста за показване."""
    return re.sub(r'CHART_DATA:\{.*?\}', '', text, flags=re.DOTALL).strip()

def render_chart(chart_data: dict, theme_name: str):
    """Рендерира диаграма с plotly или fallback с st.bar_chart."""
    try:
        import plotly.graph_objects as go
        is_dark = "Тъмна" in theme_name
        bg      = "#151d28" if is_dark else "#ffffff"
        text_c  = "#e8edf5" if is_dark else "#1a2332"
        colors  = ["#00d4aa","#0077ff","#ffa502","#ff4757","#a29bfe","#fd79a8","#55efc4"]
        fig = go.Figure(go.Pie(
            labels=chart_data["labels"],
            values=chart_data["values"],
            hole=0.4,
            marker_colors=colors[:len(chart_data["values"])],
            textfont=dict(size=12, color=text_c),
        ))
        fig.update_layout(
            title=dict(text=chart_data.get("title",""), font=dict(color=text_c, size=14)),
            paper_bgcolor=bg, plot_bgcolor=bg,
            legend=dict(font=dict(color=text_c, size=11)),
            margin=dict(t=50, b=20, l=20, r=20),
            height=280,
        )
        st.plotly_chart(fig, use_container_width=True)
    except ImportError:
        import pandas as pd
        df = pd.DataFrame({"Стойност": chart_data["values"]}, index=chart_data["labels"])
        st.bar_chart(df)

def chart_to_png_b64(chart_data: dict) -> str:
    """Конвертира chart_data в base64 PNG за вграждане в HTML."""
    try:
        import plotly.graph_objects as go
        colors = ["#0077cc","#00b894","#fdcb6e","#e17055","#a29bfe","#fd79a8","#55efc4"]
        fig = go.Figure(go.Pie(
            labels=chart_data["labels"],
            values=chart_data["values"],
            hole=0.4,
            marker_colors=colors[:len(chart_data["values"])],
            textfont=dict(size=13, color="#1a2332"),
        ))
        fig.update_layout(
            title=dict(text=chart_data.get("title",""), font=dict(color="#1a2332", size=15)),
            paper_bgcolor="white", plot_bgcolor="white",
            legend=dict(font=dict(color="#1a2332", size=12)),
            margin=dict(t=60, b=20, l=20, r=20),
            height=320, width=480,
        )
        png_bytes = fig.to_image(format="png", scale=2)
        return base64.b64encode(png_bytes).decode()
    except Exception:
        return ""

def generate_print_report(ortho_img, messages, pin_lat, pin_lon, buf_key, model_name):
    """Генерира HTML отчет за печат с вградени диаграми."""
    ortho_b64 = img_to_b64(ortho_img) if ortho_img else ""
    chat_html = ""
    for msg in messages:
        role_bg  = "#eef3fa" if msg["role"] == "user" else "#f0fff8"
        role_lbl = "ВЪПРОС" if msg["role"] == "user" else "AI АНАЛИЗ"
        role_col = "#4a5a6e" if msg["role"] == "user" else "#0077cc"
        text     = clean_text(msg["content"]).replace("\n", "<br>")
        # Диаграма ако има chart данни
        chart_html_block = ""
        if msg["role"] == "assistant":
            cd = parse_chart_data(msg["content"])
            if cd:
                chart_b64 = chart_to_png_b64(cd)
                if chart_b64:
                    chart_html_block = f"""
                    <div style=\"margin-top:14px;text-align:center;\">
                        <img src=\"data:image/png;base64,{chart_b64}\"
                             style=\"max-width:480px;width:100%;border-radius:8px;
                                    border:1px solid #d0dae8;\">
                    </div>"""
        chat_html += f"""
        <div style="margin-bottom:16px; padding:14px; background:{role_bg};
            border-radius:8px; border-left:3px solid {role_col};">
            <div style="font-size:10px; font-weight:700; color:{role_col};
                letter-spacing:1px; margin-bottom:6px; font-family:monospace;">{role_lbl}</div>
            <div style="font-size:13px; line-height:1.7; color:#1a2332;">{text}</div>
            {chart_html_block}
        </div>"""
    from datetime import datetime
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    return f"""<!DOCTYPE html>
<html lang="bg">
<head>
<meta charset="UTF-8">
<title>Геопространствен анализ — {now}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;700;800&display=swap');
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{ font-family:'Syne',sans-serif; color:#1a2332; background:#fff; padding:32px; max-width:900px; margin:0 auto; }}
  .report-header {{ border-bottom:3px solid #0077cc; padding-bottom:20px; margin-bottom:24px; }}
  .report-title {{ font-size:26px; font-weight:800; color:#0a1628; }}
  .report-sub {{ font-size:12px; color:#4a5a6e; margin-top:4px; font-family:monospace; letter-spacing:1px; }}
  .meta-grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-bottom:24px; }}
  .meta-item {{ background:#f4f6f9; border-radius:8px; padding:12px; }}
  .meta-label {{ font-size:10px; color:#8a9ab0; font-family:monospace; letter-spacing:1px; margin-bottom:4px; }}
  .meta-value {{ font-size:14px; font-weight:700; color:#1a2332; }}
  .section-title {{ font-size:13px; font-weight:700; color:#0077cc; letter-spacing:1.5px;
      text-transform:uppercase; margin-bottom:12px; font-family:monospace; }}
  .ortho-img {{ width:100%; border-radius:10px; border:1px solid #d0dae8; margin-bottom:24px; }}
  .analysis-section {{ margin-bottom:24px; }}
  .footer {{ margin-top:32px; padding-top:16px; border-top:1px solid #d0dae8;
      font-size:11px; color:#8a9ab0; font-family:monospace; text-align:center; }}
  @media print {{ body {{ padding:16px; }} }}
</style>
</head>
<body>
  <div class="report-header">
    <div class="report-title">🛰️ Геопространствен анализ</div>
    <div class="report-sub">МЗХ ОРТОФОТО · AI VISION · {now}</div>
  </div>

  <div class="meta-grid">
    <div class="meta-item">
      <div class="meta-label">КООРДИНАТИ</div>
      <div class="meta-value" style="font-size:12px;">{pin_lat:.5f}, {pin_lon:.5f}</div>
    </div>
    <div class="meta-item">
      <div class="meta-label">ОБХВАТ</div>
      <div class="meta-value">{buf_key}</div>
    </div>
    <div class="meta-item">
      <div class="meta-label">МОДЕЛ</div>
      <div class="meta-value" style="font-size:11px;">{model_name}</div>
    </div>
    <div class="meta-item">
      <div class="meta-label">ВЪПРОСИ</div>
      <div class="meta-value">{len([m for m in messages if m['role']=='user'])}</div>
    </div>
  </div>

  <div class="analysis-section">
    <div class="section-title">📸 Ортофото на зоната</div>
    {'<img src="data:image/png;base64,' + ortho_b64 + '" class="ortho-img">' if ortho_b64 else ''}
  </div>

  <div class="analysis-section">
    <div class="section-title">💬 Анализ и заключения</div>
    {chat_html}
  </div>

  <div class="footer">
    Генерирано от БГ Гео Анализатор · АПТДИ към ТУ–Габрово · {MAF_ATTRIBUTION}
  </div>
</body>
</html>"""

# ─────────────────────────────────────────────────────────────────────
# LLM — чете от secrets.toml (локално) или env vars (Docker)
# ─────────────────────────────────────────────────────────────────────
import os
def get_secret(key: str, default: str = "") -> str:
    """Чете от st.secrets (локално) или os.environ (Docker)."""
    try:
        return st.secrets[key]
    except Exception:
        return os.environ.get(key, default)

ANTHROPIC_API_KEY = get_secret("ANTHROPIC_API_KEY")
MODEL = get_secret("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")

if not ANTHROPIC_API_KEY:
    st.error("❌ Липсва ANTHROPIC_API_KEY. Добави го в .streamlit/secrets.toml или като environment variable.")
    st.stop()

anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ─────────────────────────────────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────────────────────────────────
for key, val in [("messages",[]),("ortho_img",None),("ortho_b64",None),
                  ("pin_lat",None),("pin_lon",None),("map_center",[DEFAULT_LAT,DEFAULT_LON]),
                  ("map_zoom",DEFAULT_ZOOM),("buf_key","220м"),("theme_name","☀️ Светла")]:
    if key not in st.session_state:
        st.session_state[key] = val

theme = THEMES[st.session_state.theme_name]
inject_css(theme)

# ─────────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Разширени настройки")
    st.markdown("---")
    system_prompt_val = st.text_area("Системен промпт", height=300, value=SYSTEM_PROMPT)
    st.markdown("---")
    st.markdown(f"""<div style="font-family:monospace;font-size:11px;color:var(--text-muted);line-height:1.8;">
        <div>Модел: <span style="color:var(--accent)">{MODEL}</span></div>
        <div>Данни: <span style="color:var(--accent)">МЗХ Ортофото</span></div>
        <div>Zoom: <span style="color:var(--accent)">17</span></div>
        <div>Резолюция: <span style="color:var(--accent)">~0.5м/px</span></div>
    </div>""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────
# ХЕДЪР
# ─────────────────────────────────────────────────────────────────────
hdr_col1, hdr_col2 = st.columns([3, 1])
with hdr_col1:
    st.markdown("""
    <div class="geo-header">
        <div class="geo-header-icon">🛰️</div>
        <div>
            <div class="geo-header-title">БГ Гео Анализатор</div>
            <div class="geo-header-subtitle">МЗХ Ортофото · AI Vision · България</div>
        </div>
    </div>""", unsafe_allow_html=True)
with hdr_col2:
    t_cols = st.columns(len(THEMES))
    for ti, tname in enumerate(THEMES.keys()):
        is_active = st.session_state.theme_name == tname
        with t_cols[ti]:
            if st.button(tname, key=f"theme_{ti}",
                         use_container_width=True,
                         type="primary" if is_active else "secondary"):
                st.session_state.theme_name = tname
                st.rerun()

# ─────────────────────────────────────────────────────────────────────
# СТЪПКОВ ИНДИКАТОР
# ─────────────────────────────────────────────────────────────────────
has_pin   = st.session_state.pin_lat is not None
has_ortho = st.session_state.ortho_b64 is not None
has_chat  = len(st.session_state.messages) > 0

def sc(done, active):
    return "done" if done else ("active" if active else "todo")

s1, s2, s3 = sc(has_pin, True), sc(has_ortho, has_pin), sc(has_chat, has_ortho)
st.markdown(f"""
<div class="steps-bar">
    <div class="step-item">
        <div class="step-num {s1}">{'✓' if has_pin else '1'}</div>
        <span class="step-label {'active' if s1=='active' else ''}">Изберете зона</span>
    </div>
    <span class="step-arrow">›</span>
    <div class="step-item">
        <div class="step-num {s2}">{'✓' if has_ortho else '2'}</div>
        <span class="step-label {'active' if s2=='active' else ''}">Заредете ортофото</span>
    </div>
    <span class="step-arrow">›</span>
    <div class="step-item">
        <div class="step-num {s3}">{'✓' if has_chat else '3'}</div>
        <span class="step-label {'active' if s3=='active' else ''}">Анализирайте</span>
    </div>
</div>""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────
# MAIN LAYOUT — 3 КОЛОНИ
# ─────────────────────────────────────────────────────────────────────
col_map, col_ortho, col_chat = st.columns([1.1, 1, 1.4], gap="medium")

# ══ КОЛОНА 1: КАРТА ══════════════════════════════════════════════════
with col_map:
    st.markdown('<div class="geo-card-header">📍 ИЗБОР НА ЗОНА</div>', unsafe_allow_html=True)
    buf_cols = st.columns(len(BUFFER_OPTIONS))
    for bi, bname in enumerate(BUFFER_OPTIONS.keys()):
        is_active = st.session_state.buf_key == bname
        with buf_cols[bi]:
            if st.button(bname, key=f"buf_{bi}",
                         use_container_width=True,
                         type="primary" if is_active else "secondary"):
                st.session_state.buf_key = bname
                if st.session_state.ortho_img is not None:
                    st.session_state.ortho_img = None
                    st.session_state.ortho_b64 = None
                    st.session_state.messages  = []
                st.rerun()
    buf_key = st.session_state.buf_key
    buf_deg = BUFFER_OPTIONS[buf_key]

    if has_pin:
        st.markdown(f"""<div class="coord-badge">
            📍 {st.session_state.pin_lat:.5f}, {st.session_state.pin_lon:.5f}
            <span style="color:var(--text-muted)">·</span> {buf_key}
        </div>""", unsafe_allow_html=True)

    m = folium.Map(location=st.session_state.map_center, zoom_start=st.session_state.map_zoom, tiles=None)
    folium.TileLayer(tiles=MAF_URL, attr=MAF_ATTRIBUTION, name="МЗХ Ортофото", max_zoom=19).add_to(m)
    folium.TileLayer(tiles="OpenStreetMap", name="OpenStreetMap").add_to(m)
    folium.LayerControl(position="topright").add_to(m)

    if has_pin:
        folium.Marker([st.session_state.pin_lat, st.session_state.pin_lon],
                      tooltip=f"Зона: {buf_key}",
                      icon=folium.Icon(color="green", icon="crosshairs", prefix="fa")).add_to(m)
        folium.Rectangle(
            bounds=[[st.session_state.pin_lat - buf_deg, st.session_state.pin_lon - buf_deg],
                    [st.session_state.pin_lat + buf_deg, st.session_state.pin_lon + buf_deg]],
            color="#00d4aa", fill=True, fill_opacity=0.08, weight=2).add_to(m)

    map_data = st_folium(m, width="100%", height=360,
                         returned_objects=["last_clicked","center","zoom"], key="main_map")

    if map_data.get("center"):
        st.session_state.map_center = [map_data["center"]["lat"], map_data["center"]["lng"]]
    if map_data.get("zoom"):
        st.session_state.map_zoom = map_data["zoom"]
    if map_data.get("last_clicked"):
        nlat, nlon = map_data["last_clicked"]["lat"], map_data["last_clicked"]["lng"]
        if (nlat, nlon) != (st.session_state.pin_lat, st.session_state.pin_lon):
            st.session_state.pin_lat  = nlat
            st.session_state.pin_lon  = nlon
            st.session_state.ortho_img = None
            st.session_state.ortho_b64 = None
            st.session_state.messages  = []
            st.rerun()

    if st.button("🔍 Зареди ортофото" if not has_ortho else "🔄 Презареди",
                 disabled=not has_pin, use_container_width=True):
        with st.spinner(f"Зареждане ({buf_key})..."):
            try:
                img = fetch_maf_tiles(st.session_state.pin_lat, st.session_state.pin_lon, buf_deg)
                st.session_state.ortho_img = img
                st.session_state.ortho_b64 = img_to_b64(img)
                st.session_state.messages  = []
                st.success(f"✓ Заредено — {img.width}×{img.height}px")
            except Exception as e:
                st.error(f"Грешка: {e}")

    if not has_pin:
        st.markdown("""<div style="text-align:center;padding:10px;color:var(--text-muted);
            font-size:12px;font-family:monospace;">↑ кликнете върху картата</div>""",
            unsafe_allow_html=True)

# ══ КОЛОНА 2: ОРТОФОТО ═══════════════════════════════════════════════
with col_ortho:
    st.markdown('<div class="geo-card-header">🛰️ ОРТОФОТО</div>', unsafe_allow_html=True)
    if st.session_state.ortho_img:
        st.image(st.session_state.ortho_img,
                 caption=f"МЗХ · {buf_key} · zoom 17", use_container_width=True)
        img = st.session_state.ortho_img
        is_dark = "Тъмна" in st.session_state.theme_name
        bg_m = "#111720" if is_dark else "#f4f6f9"
        bd_m = "#1e2d3d" if is_dark else "#d0dae8"
        tx_m = "#4a5a6e"
        tx_v = "#e8edf5" if is_dark else "#1a2332"
        st.markdown(f"""
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:8px;">
            <div style="background:{bg_m};border:1px solid {bd_m};border-radius:6px;
                 padding:8px;font-family:monospace;font-size:11px;">
                <div style="color:{tx_m}">РАЗМЕР</div>
                <div style="color:{tx_v}">{img.width}×{img.height}px</div>
            </div>
            <div style="background:{bg_m};border:1px solid {bd_m};border-radius:6px;
                 padding:8px;font-family:monospace;font-size:11px;">
                <div style="color:{tx_m}">ОБХВАТ</div>
                <div style="color:{tx_v}">{buf_key}</div>
            </div>
        </div>""", unsafe_allow_html=True)

        # Бутон за печат
        st.markdown("---")
        if has_chat:
            if st.button("🖨️ Генерирай отчет за печат", use_container_width=True):
                html_report = generate_print_report(
                    st.session_state.ortho_img, st.session_state.messages,
                    st.session_state.pin_lat, st.session_state.pin_lon,
                    buf_key, MODEL
                )
                b64_html = base64.b64encode(html_report.encode()).decode()
                st.markdown(f"""
                <a href="data:text/html;base64,{b64_html}"
                   target="_blank"
                   style="display:block;text-align:center;padding:10px;
                          background:var(--accent);color:var(--bg-primary);
                          border-radius:8px;font-weight:700;font-size:13px;
                          text-decoration:none;margin-top:8px;">
                    🖨️ Отвори отчет в нов прозорец
                </a>""", unsafe_allow_html=True)
        else:
            st.markdown("""<div style="text-align:center;padding:10px;color:var(--text-muted);
                font-size:12px;font-family:monospace;">Задайте въпроси за да генерирате отчет</div>""",
                unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div style="height:360px;background:var(--bg-secondary);border:1px dashed var(--border);
             border-radius:12px;display:flex;flex-direction:column;
             align-items:center;justify-content:center;gap:12px;">
            <div style="font-size:36px;opacity:0.3">🛰️</div>
            <div style="color:var(--text-muted);font-size:13px;text-align:center;padding:0 20px;">
                {'Кликнете „Зареди ортофото"' if has_pin else 'Изберете зона на картата'}
            </div>
        </div>""", unsafe_allow_html=True)

# ══ КОЛОНА 3: ЧАТ ════════════════════════════════════════════════════
with col_chat:
    st.markdown('<div class="geo-card-header">💬 ГЕОПРОСТРАНСТВЕН АНАЛИЗ</div>', unsafe_allow_html=True)

    # Статус лента
    dot_c = "waiting" if not has_ortho else "ready"
    status_txt = ("Изчакване на ортофото..." if not has_ortho
                  else f"{'Готов' if not has_chat else str(len(st.session_state.messages)//2)+' въпроса'} · {MODEL.split('-')[1].upper()}")
    st.markdown(f"""<div class="status-bar">
        <div class="status-dot {dot_c}"></div><span>{status_txt}</span>
    </div>""", unsafe_allow_html=True)

    # 1. ПОЛЕ ЗА ВЪПРОСИ — най-отгоре
    inp_col, btn_col = st.columns([5, 1])
    with inp_col:
        user_input = st.text_input(
            label="въпрос",
            placeholder="Задайте въпрос за анализ..." if has_ortho else "Първо заредете ортофото...",
            disabled=not has_ortho,
            label_visibility="collapsed",
            key="chat_input_field",
        )
    with btn_col:
        send_clicked = st.button("➤", disabled=not has_ortho, use_container_width=True, key="send_btn")

    prompt = None
    if send_clicked and user_input.strip():
        prompt = user_input.strip()

    if hasattr(st.session_state, "_quick"):
        prompt = st.session_state._quick
        del st.session_state._quick

    # 2. ГЕОПРОСТРАНСТВЕН АНАЛИЗ — история на чата
    chat_area = st.container(height=300)
    with chat_area:
        if not st.session_state.messages:
            icon = "🔬" if has_ortho else "🗺️"
            txt  = "Ортофотото е заредено.<br>Задайте въпрос по-горе." if has_ortho else "Изберете зона и заредете<br>ортофото за начало."
            st.markdown(f"""<div style="text-align:center;padding:30px 20px;color:var(--text-muted);">
                <div style="font-size:28px;margin-bottom:8px;">{icon}</div>
                <div style="font-size:13px;">{txt}</div>
            </div>""", unsafe_allow_html=True)
        else:
            for msg in st.session_state.messages:
                role_lbl = "ВИЕ" if msg["role"] == "user" else "AI АНАЛИЗАТОР"
                display_text = clean_text(msg["content"]) if msg["role"] == "assistant" else msg["content"]
                display_text = display_text.replace("\n", "<br>")
                st.markdown(f"""<div class="chat-msg {msg['role']}">
                    <div class="chat-role {msg['role']}">{role_lbl}</div>
                    {display_text}
                </div>""", unsafe_allow_html=True)
                if msg["role"] == "assistant":
                    chart_data = parse_chart_data(msg["content"])
                    if chart_data:
                        render_chart(chart_data, st.session_state.theme_name)

    # 3. ИЗЧИСТИ ЧАТА
    if has_chat:
        if st.button("🗑️ Изчисти чата", use_container_width=True):
            st.session_state.messages = []
            st.rerun()

    # 4. ПРИМЕРНИ ВЪПРОСИ — най-отдолу
    if has_ortho:
        with st.expander("💡 Примерни въпроси", expanded=not has_chat):
            c1, c2 = st.columns(2)
            for i, q in enumerate(EXAMPLE_QUESTIONS):
                if (c1 if i % 2 == 0 else c2).button(q, key=f"ex_{i}", use_container_width=True):
                    st.session_state._quick = q
                    st.rerun()

    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        anthropic_msgs = []
        for i, m in enumerate(st.session_state.messages):
            if i == 0:
                anthropic_msgs.append({"role": "user", "content": [
                    {"type": "text", "text": m["content"]},
                    {"type": "image", "source": {"type": "base64",
                     "media_type": "image/png", "data": st.session_state.ortho_b64}}
                ]})
            else:
                anthropic_msgs.append({"role": m["role"], "content": m["content"]})

        with st.spinner("🔬 Анализиране..."):
            try:
                response = anthropic_client.messages.create(
                    model=MODEL, max_tokens=2048,
                    system=system_prompt_val, messages=anthropic_msgs,
                )
                full = response.content[0].text
                st.session_state.messages.append({"role": "assistant", "content": full})
            except Exception as e:
                st.error(f"Грешка: {e}")
        st.rerun()
