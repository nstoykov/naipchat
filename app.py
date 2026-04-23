import math
import io
import base64
import requests
from PIL import Image, ImageDraw
import streamlit as st
from streamlit_folium import st_folium
import folium
from openai import OpenAI

# ─────────────────────────────────────────────
# Конфигурация
# ─────────────────────────────────────────────
st.set_page_config(page_title="БГ Гео Чатбот", layout="wide")
st.title("🛰️ БГ Гео Чатбот — МЗХ Ортофото")

DEFAULT_LAT  = 42.8742
DEFAULT_LON  = 25.3187
DEFAULT_ZOOM = 14

MAF_URL         = "https://bg-imagery.openstreetmap.org/layer/maf-orthophoto-latest/{z}/{x}/{y}.png"
MAF_ATTRIBUTION = "© Министерство на земеделието и храните"

BUFFER_OPTIONS = {
    "🔍 Малък — 220м":  0.002,
    "📍 Среден — 440м": 0.004,
    "🗺️ Голям — 880м":  0.008,
}

# ─────────────────────────────────────────────
# LLM клиент
# ─────────────────────────────────────────────
client = OpenAI(
    base_url=f"{st.secrets['OLLAMA_HOST']}/v1",
    api_key=st.secrets["OLLAMA_API_KEY"]
)
MODEL = st.secrets["OLLAMA_MODEL"]

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
    canvas = Image.new("RGB", (cols * TILE_SIZE, rows * TILE_SIZE), (200, 200, 200))
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
    s = 12
    draw.line([(cx - s, cy), (cx + s, cy)], fill=(255, 50, 50), width=2)
    draw.line([(cx, cy - s), (cx, cy + s)], fill=(255, 50, 50), width=2)
    draw.ellipse([(cx - 4, cy - 4), (cx + 4, cy + 4)], outline=(255, 50, 50), width=2)

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
]:
    if key not in st.session_state:
        st.session_state[key] = val

# ─────────────────────────────────────────────
# Странична лента
# ─────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Настройки")
    st.subheader("📐 Зона на анализ")
    buf_label = st.radio("Изберете обхват:", list(BUFFER_OPTIONS.keys()), index=1)
    buf_deg = BUFFER_OPTIONS[buf_label]

    st.divider()
    st.subheader("🧠 Системен промпт")
    system_prompt = st.text_area(
        "Роля на AI анализатора",
        height=220,
        value="""Ти си експерт по дистанционни изследвания и геопространствен анализ с дълбоки познания за:
- Интерпретация на ортофото изображения (МЗХ ортофото, Sentinel, Landsat)
- Класификация на земеползването и земното покритие в България
- Разпознаване на градска, земеделска и горска инфраструктура
- Хидрология, релеф и геопространствен контекст за България

При анализ бъди конкретен — описвай типове покривност, инфраструктура, растителност, водни обекти и аномалии. Свързвай наблюденията с реален географски контекст за България."""
    )

    st.divider()
    st.caption(MAF_ATTRIBUTION)
    if st.session_state.pin_lat:
        st.caption(f"📍 {st.session_state.pin_lat:.5f}, {st.session_state.pin_lon:.5f}")

# ─────────────────────────────────────────────
# Основен layout
# ─────────────────────────────────────────────
col_map, col_chat = st.columns([1, 1])

# ── Лява колона: карта ───────────────────────
with col_map:
    st.subheader("🗺️ Изберете зона")
    st.caption("Кликнете върху картата за поставяне на пин")

    m = folium.Map(location=st.session_state.map_center, zoom_start=st.session_state.map_zoom, tiles=None)

    folium.TileLayer(tiles=MAF_URL, attr=MAF_ATTRIBUTION, name="МЗХ Ортофото", max_zoom=19).add_to(m)
    folium.TileLayer(tiles="OpenStreetMap", name="OpenStreetMap").add_to(m)
    folium.LayerControl().add_to(m)

    if st.session_state.pin_lat:
        folium.Marker(
            [st.session_state.pin_lat, st.session_state.pin_lon],
            tooltip="Зона на анализ",
            icon=folium.Icon(color="red", icon="crosshairs", prefix="fa"),
        ).add_to(m)
        folium.Rectangle(
            bounds=[
                [st.session_state.pin_lat - buf_deg, st.session_state.pin_lon - buf_deg],
                [st.session_state.pin_lat + buf_deg, st.session_state.pin_lon + buf_deg],
            ],
            color="#e63946", fill=True, fill_opacity=0.08, weight=2,
        ).add_to(m)

    map_data = st_folium(m, width="100%", height=420, returned_objects=["last_clicked", "center", "zoom"])

    if map_data.get("center"):
        st.session_state.map_center = [map_data["center"]["lat"], map_data["center"]["lng"]]
    if map_data.get("zoom"):
        st.session_state.map_zoom = map_data["zoom"]

    if map_data.get("last_clicked"):
        new_lat = map_data["last_clicked"]["lat"]
        new_lon = map_data["last_clicked"]["lng"]
        if (new_lat, new_lon) != (st.session_state.pin_lat, st.session_state.pin_lon):
            st.session_state.pin_lat     = new_lat
            st.session_state.pin_lon     = new_lon
            st.session_state.ortho_img   = None
            st.session_state.ortho_b64   = None
            st.session_state.messages    = []
            st.rerun()

    if st.button(
        "🔍 Зареди ортофото за избраната зона",
        disabled=st.session_state.pin_lat is None,
        use_container_width=True,
        type="primary",
    ):
        with st.spinner(f"Зареждане ({buf_label.split('—')[1].strip()})..."):
            try:
                img = fetch_maf_tiles(st.session_state.pin_lat, st.session_state.pin_lon, buf_deg)
                st.session_state.ortho_img   = img
                st.session_state.ortho_b64   = image_to_base64(img)
                st.session_state.messages    = []
                st.success(f"Заредено — {img.width}×{img.height} px")
            except Exception as e:
                st.error(f"Грешка: {e}")

    if st.session_state.ortho_img:
        st.image(st.session_state.ortho_img, caption=f"МЗХ Ортофото · {buf_label}", use_container_width=True)
    elif st.session_state.pin_lat is None:
        st.info("👆 Кликнете върху картата за поставяне на пин.")

# ── Дясна колона: чат ────────────────────────
with col_chat:
    st.subheader("💬 Геопространствен анализ")

    chat_container = st.container(height=480)
    with chat_container:
        if not st.session_state.messages:
            st.info("Заредете ортофото и задайте въпрос.")
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    if st.session_state.ortho_b64 and not st.session_state.messages:
        st.caption("💡 Примерни въпроси:")
        examples = [
            "Какъв е доминиращият тип земно покритие?",
            "Опиши видимата пътна мрежа.",
            "Има ли водни обекти или влажни зони?",
            "Оцени дела на непропускливите повърхности.",
            "Градско, крайградско или селско застрояване?",
        ]
        c1, c2 = st.columns(2)
        for i, q in enumerate(examples):
            if (c1 if i % 2 == 0 else c2).button(q, key=f"ex_{i}", use_container_width=True):
                st.session_state._quick = q
                st.rerun()

    prompt = st.chat_input("Задайте въпрос за заредената зона...", disabled=st.session_state.ortho_b64 is None)

    if hasattr(st.session_state, "_quick"):
        prompt = st.session_state._quick
        del st.session_state._quick

    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        openai_messages = [{"role": "system", "content": system_prompt}]
        for i, m in enumerate(st.session_state.messages):
            if i == 0:
                openai_messages.append({
                    "role": "user",
                    "content": [
                        {"type": "text", "text": m["content"]},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{st.session_state.ortho_b64}"}}
                    ]
                })
            else:
                openai_messages.append({"role": m["role"], "content": m["content"]})

        with chat_container:
            with st.chat_message("assistant"):
                box = st.empty()
                full = ""
                try:
                    stream = client.chat.completions.create(model=MODEL, messages=openai_messages, stream=True)
                    for chunk in stream:
                        delta = chunk.choices[0].delta.content or ""
                        full += delta
                        box.markdown(full + "▌")
                    box.markdown(full)
                except Exception as e:
                    st.error(f"Грешка на модела: {e}")

        st.session_state.messages.append({"role": "assistant", "content": full})
        st.rerun()
