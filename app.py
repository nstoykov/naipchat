import math
import io
import base64
import requests
from PIL import Image, ImageDraw
import streamlit as st
from streamlit_folium import st_folium
import folium
import anthropic

# ─────────────────────────────────────────────
# Конфигурация
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="БГ Гео Анализатор",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

DEFAULT_LAT  = 42.8742
DEFAULT_LON  = 25.3187
DEFAULT_ZOOM = 14

MAF_URL         = "https://bg-imagery.openstreetmap.org/layer/maf-orthophoto-latest/{z}/{x}/{y}.png"
MAF_ATTRIBUTION = "© МЗХ България"

BUFFER_OPTIONS = {
    "220м":  0.002,
    "440м":  0.004,
    "880м":  0.008,
}

SYSTEM_PROMPT = """Ти си експерт по дистанционни изследвания и геопространствен анализ с дълбоки познания за:
- Интерпретация на ортофото изображения (МЗХ ортофото, Sentinel, Landsat)
- Класификация на земеползването и земното покритие в България
- Разпознаване на градска, земеделска и горска инфраструктура
- Хидрология, релеф и геопространствен контекст за България

При анализ бъди конкретен — описвай типове покривност, инфраструктура, растителност, водни обекти и аномалии. Свързвай наблюденията с реален географски контекст за България. Отговаряй на български."""

EXAMPLE_QUESTIONS = [
    "🌿 Какъв е доминиращият тип земно покритие?",
    "🛣️ Опиши видимата пътна мрежа и достъпността.",
    "💧 Има ли водни обекти или влажни зони?",
    "🏗️ Какъв тип застрояване е видимо?",
    "🌡️ Оцени риска от горски пожар в зоната.",
    "📐 Оцени дела на непропускливите повърхности.",
]

# ─────────────────────────────────────────────
# CSS — Тъмен картографски интерфейс
# ─────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Syne:wght@400;600;700;800&display=swap');

:root {
    --bg-primary:    #0a0e14;
    --bg-secondary:  #111720;
    --bg-card:       #151d28;
    --bg-hover:      #1c2736;
    --accent:        #00d4aa;
    --accent-dim:    #00a882;
    --accent-glow:   rgba(0, 212, 170, 0.15);
    --text-primary:  #e8edf5;
    --text-secondary:#7a8fa8;
    --text-muted:    #4a5a6e;
    --border:        #1e2d3d;
    --border-accent: #00d4aa44;
    --danger:        #ff4757;
    --warning:       #ffa502;
    --mono:          'JetBrains Mono', monospace;
    --display:       'Syne', sans-serif;
}

/* Глобален reset */
html, body, [class*="css"] {
    font-family: var(--display) !important;
    background-color: var(--bg-primary) !important;
    color: var(--text-primary) !important;
}

.stApp {
    background-color: var(--bg-primary) !important;
}

/* Скрий default Streamlit header */
header[data-testid="stHeader"] {
    background: transparent !important;
    border-bottom: none !important;
}

/* Главен хедър */
.geo-header {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 20px 0 24px 0;
    border-bottom: 1px solid var(--border);
    margin-bottom: 24px;
}
.geo-header-icon {
    width: 44px;
    height: 44px;
    background: var(--accent-glow);
    border: 1px solid var(--border-accent);
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 22px;
}
.geo-header-title {
    font-family: var(--display) !important;
    font-size: 22px !important;
    font-weight: 800 !important;
    color: var(--text-primary) !important;
    letter-spacing: -0.5px;
    margin: 0 !important;
}
.geo-header-subtitle {
    font-family: var(--mono) !important;
    font-size: 11px !important;
    color: var(--accent) !important;
    letter-spacing: 1.5px;
    text-transform: uppercase;
}

/* Стъпков индикатор */
.steps-bar {
    display: flex;
    gap: 0;
    margin-bottom: 24px;
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 12px 20px;
    align-items: center;
}
.step-item {
    display: flex;
    align-items: center;
    gap: 8px;
    flex: 1;
}
.step-num {
    width: 26px;
    height: 26px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 12px;
    font-weight: 700;
    font-family: var(--mono) !important;
    flex-shrink: 0;
}
.step-num.done   { background: var(--accent); color: var(--bg-primary); }
.step-num.active { background: var(--accent-glow); color: var(--accent); border: 1px solid var(--accent); }
.step-num.todo   { background: var(--bg-card); color: var(--text-muted); border: 1px solid var(--border); }
.step-label {
    font-size: 12px;
    color: var(--text-secondary);
    font-family: var(--display) !important;
}
.step-label.active { color: var(--text-primary); font-weight: 600; }
.step-arrow {
    color: var(--text-muted);
    font-size: 14px;
    margin: 0 8px;
}

/* Карти / панели */
.geo-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 16px;
    margin-bottom: 16px;
}
.geo-card-header {
    font-size: 11px;
    font-family: var(--mono) !important;
    color: var(--accent);
    letter-spacing: 1.5px;
    text-transform: uppercase;
    margin-bottom: 12px;
    display: flex;
    align-items: center;
    gap: 8px;
}

/* Буфер бутони */
.buffer-grid {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 8px;
    margin-bottom: 16px;
}
.buffer-btn {
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 10px 8px;
    text-align: center;
    cursor: pointer;
    transition: all 0.2s;
    font-family: var(--display) !important;
}
.buffer-btn:hover { border-color: var(--accent); background: var(--accent-glow); }
.buffer-btn.active {
    border-color: var(--accent);
    background: var(--accent-glow);
    color: var(--accent);
}
.buffer-btn-size {
    font-size: 15px;
    font-weight: 700;
    color: var(--text-primary);
    display: block;
}
.buffer-btn-desc {
    font-size: 10px;
    color: var(--text-secondary);
    font-family: var(--mono) !important;
}

/* Координатен badge */
.coord-badge {
    background: var(--bg-secondary);
    border: 1px solid var(--border-accent);
    border-radius: 6px;
    padding: 8px 12px;
    font-family: var(--mono) !important;
    font-size: 12px;
    color: var(--accent);
    display: inline-flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 12px;
}

/* Примерни въпроси */
.examples-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
    margin-bottom: 16px;
}

/* Чат съобщения */
.chat-msg {
    padding: 12px 16px;
    border-radius: 10px;
    margin-bottom: 10px;
    font-size: 14px;
    line-height: 1.6;
}
.chat-msg.user {
    background: var(--bg-hover);
    border: 1px solid var(--border);
    margin-left: 40px;
}
.chat-msg.assistant {
    background: var(--bg-card);
    border: 1px solid var(--border-accent);
    border-left: 3px solid var(--accent);
}
.chat-role {
    font-size: 10px;
    font-family: var(--mono) !important;
    letter-spacing: 1px;
    text-transform: uppercase;
    margin-bottom: 6px;
}
.chat-role.user      { color: var(--text-muted); }
.chat-role.assistant { color: var(--accent); }

/* Статус лента */
.status-bar {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    background: var(--bg-secondary);
    border-radius: 6px;
    font-family: var(--mono) !important;
    font-size: 11px;
    color: var(--text-secondary);
    margin-bottom: 12px;
    border: 1px solid var(--border);
}
.status-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    flex-shrink: 0;
}
.status-dot.ready   { background: var(--accent); box-shadow: 0 0 6px var(--accent); }
.status-dot.waiting { background: var(--text-muted); }
.status-dot.loading { background: var(--warning); animation: pulse 1s infinite; }

@keyframes pulse {
    0%, 100% { opacity: 1; }
    50%       { opacity: 0.3; }
}

/* Streamlit компоненти — override */
.stButton > button {
    background: var(--accent) !important;
    color: var(--bg-primary) !important;
    border: none !important;
    border-radius: 8px !important;
    font-family: var(--display) !important;
    font-weight: 700 !important;
    font-size: 13px !important;
    letter-spacing: 0.3px !important;
    padding: 10px 20px !important;
    transition: all 0.2s !important;
    width: 100% !important;
}
.stButton > button:hover {
    background: var(--accent-dim) !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 16px var(--accent-glow) !important;
}
.stButton > button:disabled {
    background: var(--bg-hover) !important;
    color: var(--text-muted) !important;
    transform: none !important;
    box-shadow: none !important;
}

/* Secondary бутони */
button[kind="secondary"] {
    background: var(--bg-hover) !important;
    color: var(--text-secondary) !important;
    border: 1px solid var(--border) !important;
    font-size: 12px !important;
    padding: 8px 12px !important;
}
button[kind="secondary"]:hover {
    border-color: var(--accent) !important;
    color: var(--accent) !important;
    background: var(--accent-glow) !important;
}

/* Radio buttons */
.stRadio > div {
    display: flex !important;
    flex-direction: row !important;
    gap: 10px !important;
}
.stRadio label {
    background: var(--bg-secondary) !important;
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
    padding: 8px 14px !important;
    font-size: 13px !important;
    cursor: pointer !important;
    transition: all 0.2s !important;
    color: var(--text-secondary) !important;
}
.stRadio label:hover {
    border-color: var(--accent) !important;
    color: var(--text-primary) !important;
}

/* Chat input */
.stChatInput > div {
    background: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    border-radius: 10px !important;
}
.stChatInput textarea {
    background: transparent !important;
    color: var(--text-primary) !important;
    font-family: var(--display) !important;
    font-size: 14px !important;
}
.stChatInput textarea::placeholder {
    color: var(--text-muted) !important;
}

/* Spinner */
.stSpinner > div {
    border-top-color: var(--accent) !important;
}

/* Success/Error/Info */
.stSuccess {
    background: rgba(0, 212, 170, 0.1) !important;
    border: 1px solid var(--accent) !important;
    border-radius: 8px !important;
    color: var(--accent) !important;
}
.stError {
    background: rgba(255, 71, 87, 0.1) !important;
    border: 1px solid var(--danger) !important;
    border-radius: 8px !important;
}
.stInfo {
    background: var(--bg-secondary) !important;
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
    color: var(--text-secondary) !important;
}

/* Sidebar */
[data-testid="stSidebar"] {
    background: var(--bg-secondary) !important;
    border-right: 1px solid var(--border) !important;
}
[data-testid="stSidebar"] textarea {
    background: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
    color: var(--text-primary) !important;
    font-size: 12px !important;
}

/* Divider */
hr { border-color: var(--border) !important; }

/* Scrollbar */
::-webkit-scrollbar { width: 4px; height: 4px; }
::-webkit-scrollbar-track { background: var(--bg-primary); }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }
::-webkit-scrollbar-thumb:hover { background: var(--text-muted); }

/* Скрий Streamlit branding */
#MainMenu, footer, .viewerBadge_container__1QSob { display: none !important; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# LLM клиент
# ─────────────────────────────────────────────
anthropic_client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])
MODEL = st.secrets.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")

# ─────────────────────────────────────────────
# TMS функции
# ─────────────────────────────────────────────
def lat_lon_to_tile(lat, lon, zoom):
    n = 2 ** zoom
    x = int((lon + 180) / 360 * n)
    lat_rad = math.radians(lat)
    y = int((1 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2 * n)
    return x, y

def tile_to_lat_lon(x, y, zoom):
    n = 2 ** zoom
    lon = x / n * 360 - 180
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
    return math.degrees(lat_rad), lon

def fetch_maf_tiles(lat, lon, buf, zoom=17):
    min_lon, max_lon = lon - buf, lon + buf
    min_lat, max_lat = lat - buf, lat + buf
    x_min, y_max = lat_lon_to_tile(min_lat, min_lon, zoom)
    x_max, y_min = lat_lon_to_tile(max_lat, max_lon, zoom)
    cols = x_max - x_min + 1
    rows = y_max - y_min + 1
    TILE_SIZE = 256
    canvas = Image.new("RGB", (cols * TILE_SIZE, rows * TILE_SIZE), (15, 23, 36))
    headers = {"User-Agent": "BGGeoChatbot/1.0 (gisbulgaria.bg)"}
    for row, ty in enumerate(range(y_min, y_max + 1)):
        for col, tx in enumerate(range(x_min, x_max + 1)):
            url = MAF_URL.format(z=zoom, x=tx, y=ty)
            try:
                resp = requests.get(url, timeout=10, headers=headers)
                if resp.status_code == 200:
                    tile = Image.open(io.BytesIO(resp.content)).convert("RGB")
                    canvas.paste(tile, (col * TILE_SIZE, row * TILE_SIZE))
            except Exception:
                pass
    nw_lat, nw_lon = tile_to_lat_lon(x_min, y_min, zoom)
    se_lat, se_lon = tile_to_lat_lon(x_max + 1, y_max + 1, zoom)
    total_lon_span = se_lon - nw_lon
    total_lat_span = nw_lat - se_lat
    total_px_w = cols * TILE_SIZE
    total_px_h = rows * TILE_SIZE
    left   = max(0, int((min_lon - nw_lon) / total_lon_span * total_px_w))
    top    = max(0, int((nw_lat - max_lat) / total_lat_span * total_px_h))
    right  = min(total_px_w, int((max_lon - nw_lon) / total_lon_span * total_px_w))
    bottom = min(total_px_h, int((nw_lat - min_lat) / total_lat_span * total_px_h))
    cropped = canvas.crop((left, top, right, bottom))
    draw = ImageDraw.Draw(cropped)
    cx, cy = cropped.width // 2, cropped.height // 2
    s = 14
    draw.line([(cx - s, cy), (cx + s, cy)], fill=(0, 212, 170), width=2)
    draw.line([(cx, cy - s), (cx, cy + s)], fill=(0, 212, 170), width=2)
    draw.ellipse([(cx - 5, cy - 5), (cx + 5, cy + 5)], outline=(0, 212, 170), width=2)
    return cropped

def image_to_base64(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")

# ─────────────────────────────────────────────
# Session state
# ─────────────────────────────────────────────
for key, val in [
    ("messages", []),
    ("ortho_img", None),
    ("ortho_b64", None),
    ("pin_lat", None),
    ("pin_lon", None),
    ("map_center", [DEFAULT_LAT, DEFAULT_LON]),
    ("map_zoom", DEFAULT_ZOOM),
    ("buf_key", "440м"),
    ("is_loading", False),
]:
    if key not in st.session_state:
        st.session_state[key] = val

# ─────────────────────────────────────────────
# Sidebar — Системен промпт
# ─────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Разширени настройки")
    st.markdown("---")
    system_prompt = st.text_area(
        "Системен промпт",
        height=300,
        value=SYSTEM_PROMPT,
    )
    st.markdown("---")
    st.markdown(f"""
    <div style="font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #4a5a6e; line-height: 1.8;">
        <div>Модел: <span style="color: #00d4aa">{MODEL}</span></div>
        <div>Данни: <span style="color: #00d4aa">МЗХ Ортофото</span></div>
        <div>Zoom: <span style="color: #00d4aa">17</span></div>
        <div>Резолюция: <span style="color: #00d4aa">~0.5м/px</span></div>
    </div>
    """, unsafe_allow_html=True)

# ─────────────────────────────────────────────
# Главен хедър
# ─────────────────────────────────────────────
st.markdown("""
<div class="geo-header">
    <div class="geo-header-icon">🛰️</div>
    <div>
        <div class="geo-header-title">БГ Гео Анализатор</div>
        <div class="geo-header-subtitle">МЗХ Ортофото · AI Vision · България</div>
    </div>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# Стъпков индикатор
# ─────────────────────────────────────────────
has_pin    = st.session_state.pin_lat is not None
has_ortho  = st.session_state.ortho_b64 is not None
has_chat   = len(st.session_state.messages) > 0

def step_class(condition_done, condition_active):
    if condition_done:   return "done"
    if condition_active: return "active"
    return "todo"

s1 = step_class(has_pin,   True)
s2 = step_class(has_ortho, has_pin)
s3 = step_class(has_chat,  has_ortho)

st.markdown(f"""
<div class="steps-bar">
    <div class="step-item">
        <div class="step-num {s1}">{'✓' if has_pin else '1'}</div>
        <span class="step-label {'active' if s1 == 'active' else ''}">Изберете зона</span>
    </div>
    <span class="step-arrow">›</span>
    <div class="step-item">
        <div class="step-num {s2}">{'✓' if has_ortho else '2'}</div>
        <span class="step-label {'active' if s2 == 'active' else ''}">Заредете ортофото</span>
    </div>
    <span class="step-arrow">›</span>
    <div class="step-item">
        <div class="step-num {s3}">{'✓' if has_chat else '3'}</div>
        <span class="step-label {'active' if s3 == 'active' else ''}">Анализирайте</span>
    </div>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# Основен layout — 3 колони: карта | ортофото | чат
# ─────────────────────────────────────────────
col_map, col_ortho, col_chat = st.columns([1.2, 1, 1.3], gap="medium")

# ══════════════════════════════════════════════
# КОЛОНА 1: КАРТА
# ══════════════════════════════════════════════
with col_map:
    st.markdown('<div class="geo-card-header">📍 ИЗБОР НА ЗОНА</div>', unsafe_allow_html=True)

    # Буфер избор
    buf_key = st.radio(
        "Обхват:",
        options=list(BUFFER_OPTIONS.keys()),
        index=list(BUFFER_OPTIONS.keys()).index(st.session_state.buf_key),
        horizontal=True,
        label_visibility="collapsed",
    )
    st.session_state.buf_key = buf_key
    buf_deg = BUFFER_OPTIONS[buf_key]

    # Координати ако има пин
    if st.session_state.pin_lat:
        st.markdown(f"""
        <div class="coord-badge">
            <span>📍</span>
            <span>{st.session_state.pin_lat:.5f}, {st.session_state.pin_lon:.5f}</span>
            <span style="color: #4a5a6e">·</span>
            <span style="color: #7a8fa8">{buf_key}</span>
        </div>
        """, unsafe_allow_html=True)

    # Folium карта
    m = folium.Map(
        location=st.session_state.map_center,
        zoom_start=st.session_state.map_zoom,
        tiles=None,
    )
    folium.TileLayer(tiles=MAF_URL, attr=MAF_ATTRIBUTION, name="МЗХ Ортофото", max_zoom=19).add_to(m)
    folium.TileLayer(tiles="OpenStreetMap", name="OpenStreetMap").add_to(m)
    folium.LayerControl(position="topright").add_to(m)

    if st.session_state.pin_lat:
        folium.Marker(
            [st.session_state.pin_lat, st.session_state.pin_lon],
            tooltip=f"Зона: {buf_key}",
            icon=folium.Icon(color="green", icon="crosshairs", prefix="fa"),
        ).add_to(m)
        folium.Rectangle(
            bounds=[
                [st.session_state.pin_lat - buf_deg, st.session_state.pin_lon - buf_deg],
                [st.session_state.pin_lat + buf_deg, st.session_state.pin_lon + buf_deg],
            ],
            color="#00d4aa", fill=True, fill_opacity=0.08, weight=2,
        ).add_to(m)

    map_data = st_folium(
        m,
        width="100%",
        height=380,
        returned_objects=["last_clicked", "center", "zoom"],
        key="main_map",
    )

    if map_data.get("center"):
        st.session_state.map_center = [map_data["center"]["lat"], map_data["center"]["lng"]]
    if map_data.get("zoom"):
        st.session_state.map_zoom = map_data["zoom"]

    if map_data.get("last_clicked"):
        new_lat = map_data["last_clicked"]["lat"]
        new_lon = map_data["last_clicked"]["lng"]
        if (new_lat, new_lon) != (st.session_state.pin_lat, st.session_state.pin_lon):
            st.session_state.pin_lat   = new_lat
            st.session_state.pin_lon   = new_lon
            st.session_state.ortho_img = None
            st.session_state.ortho_b64 = None
            st.session_state.messages  = []
            st.rerun()

    # Бутон зареждане
    btn_label = "🔍 Зареди ортофото" if not has_ortho else "🔄 Презареди зона"
    btn_help   = "Първо кликнете на картата" if not has_pin else f"Ще заредите {buf_key} около пина"

    if st.button(btn_label, disabled=not has_pin, use_container_width=True, help=btn_help):
        with st.spinner(f"Зареждане на МЗХ ортофото ({buf_key})..."):
            try:
                img = fetch_maf_tiles(st.session_state.pin_lat, st.session_state.pin_lon, buf_deg)
                st.session_state.ortho_img = img
                st.session_state.ortho_b64 = image_to_base64(img)
                st.session_state.messages  = []
                st.success(f"✓ Заредено — {img.width}×{img.height}px")
            except Exception as e:
                st.error(f"Грешка: {e}")

    if not has_pin:
        st.markdown("""
        <div style="text-align:center; padding: 12px; color: #4a5a6e;
             font-size: 12px; font-family: 'JetBrains Mono', monospace;">
            ↑ кликнете върху картата
        </div>
        """, unsafe_allow_html=True)

# ══════════════════════════════════════════════
# КОЛОНА 2: ОРТОФОТО
# ══════════════════════════════════════════════
with col_ortho:
    st.markdown('<div class="geo-card-header">🛰️ ОРТОФОТО</div>', unsafe_allow_html=True)

    if st.session_state.ortho_img:
        st.image(
            st.session_state.ortho_img,
            caption=f"МЗХ · {buf_key} · zoom 17",
            use_container_width=True,
        )
        # Метаданни
        img = st.session_state.ortho_img
        st.markdown(f"""
        <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-top:8px;">
            <div style="background:#111720; border:1px solid #1e2d3d; border-radius:6px;
                 padding:8px; font-family:'JetBrains Mono',monospace; font-size:11px;">
                <div style="color:#4a5a6e">РАЗМЕР</div>
                <div style="color:#e8edf5">{img.width}×{img.height}px</div>
            </div>
            <div style="background:#111720; border:1px solid #1e2d3d; border-radius:6px;
                 padding:8px; font-family:'JetBrains Mono',monospace; font-size:11px;">
                <div style="color:#4a5a6e">ОБХВАТ</div>
                <div style="color:#e8edf5">{buf_key}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        # Placeholder
        st.markdown(f"""
        <div style="height:380px; background:#111720; border:1px dashed #1e2d3d;
             border-radius:12px; display:flex; flex-direction:column;
             align-items:center; justify-content:center; gap:12px;">
            <div style="font-size:40px; opacity:0.3">🛰️</div>
            <div style="color:#4a5a6e; font-size:13px; text-align:center; padding:0 20px;">
                {'Кликнете „Зареди ортофото"' if has_pin else 'Изберете зона на картата'}
            </div>
            <div style="color:#2a3a4e; font-family:\'JetBrains Mono\',monospace;
                 font-size:10px;">МЗХ ОРТОФОТО · ~0.5м/px</div>
        </div>
        """, unsafe_allow_html=True)

# ══════════════════════════════════════════════
# КОЛОНА 3: ЧАТ
# ══════════════════════════════════════════════
with col_chat:
    st.markdown('<div class="geo-card-header">💬 ГЕОПРОСТРАНСТВЕН АНАЛИЗ</div>', unsafe_allow_html=True)

    # Статус лента
    if not has_ortho:
        dot_class, status_text = "waiting", "Изчакване на ортофото..."
    elif not has_chat:
        dot_class, status_text = "ready", f"Готов за анализ · {MODEL.split('-')[1].upper()}"
    else:
        dot_class, status_text = "ready", f"{len(st.session_state.messages)//2} въпроса · {MODEL.split('-')[1].upper()}"

    st.markdown(f"""
    <div class="status-bar">
        <div class="status-dot {dot_class}"></div>
        <span>{status_text}</span>
    </div>
    """, unsafe_allow_html=True)

    # Чат история
    chat_area = st.container(height=340)
    with chat_area:
        if not st.session_state.messages:
            if has_ortho:
                st.markdown("""
                <div style="text-align:center; padding:30px 20px; color:#4a5a6e;">
                    <div style="font-size:28px; margin-bottom:8px;">🔬</div>
                    <div style="font-size:13px;">Ортофотото е заредено.<br>Задайте въпрос за анализ.</div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown("""
                <div style="text-align:center; padding:30px 20px; color:#4a5a6e;">
                    <div style="font-size:28px; margin-bottom:8px;">🗺️</div>
                    <div style="font-size:13px;">Изберете зона и заредете<br>ортофото за начало.</div>
                </div>
                """, unsafe_allow_html=True)
        else:
            for msg in st.session_state.messages:
                role_label = "ВИЕ" if msg["role"] == "user" else "AI АНАЛИЗАТОР"
                st.markdown(f"""
                <div class="chat-msg {msg['role']}">
                    <div class="chat-role {msg['role']}">{role_label}</div>
                    {msg['content']}
                </div>
                """, unsafe_allow_html=True)

    # Примерни въпроси
    if has_ortho:
        with st.expander("💡 Примерни въпроси", expanded=not has_chat):
            c1, c2 = st.columns(2)
            for i, q in enumerate(EXAMPLE_QUESTIONS):
                col = c1 if i % 2 == 0 else c2
                if col.button(q, key=f"ex_{i}", use_container_width=True):
                    st.session_state._quick = q
                    st.rerun()

    # Действия
    action_cols = st.columns([3, 1])
    with action_cols[1]:
        if has_chat and st.button("🗑️ Изчисти", use_container_width=True, help="Изчисти историята на чата"):
            st.session_state.messages = []
            st.rerun()

    # Чат вход
    prompt = st.chat_input(
        "Задайте въпрос за анализ..." if has_ortho else "Първо заредете ортофото...",
        disabled=not has_ortho,
    )

    if hasattr(st.session_state, "_quick"):
        prompt = st.session_state._quick
        del st.session_state._quick

    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})

        # Изгради Anthropic съобщения
        anthropic_msgs = []
        for i, m in enumerate(st.session_state.messages):
            if i == 0:
                anthropic_msgs.append({
                    "role": "user",
                    "content": [
                        {"type": "text", "text": m["content"]},
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": st.session_state.ortho_b64,
                            }
                        }
                    ]
                })
            else:
                anthropic_msgs.append({"role": m["role"], "content": m["content"]})

        with st.spinner("🔬 Анализиране..."):
            try:
                response = anthropic_client.messages.create(
                    model=MODEL,
                    max_tokens=2048,
                    system=system_prompt,
                    messages=anthropic_msgs,
                )
                full = response.content[0].text
                st.session_state.messages.append({"role": "assistant", "content": full})
            except Exception as e:
                st.error(f"Грешка: {e}")

        st.rerun()
