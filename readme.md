# 🛰️ БГ Гео Анализатор

AI-базиран геопространствен анализатор на МЗХ ортофото за България.

**АПТДИ към ТУ–Габрово**

---

## Функционалности

- 🗺️ Интерактивна карта с МЗХ ортофото (zoom 18, ~0.25м/px)
- 📍 Кликване за избор на зона с 4 буфера: 110м / 220м / 440м / 880м
- 🤖 AI vision анализ чрез Claude (Anthropic)
- 📊 Автоматични диаграми при процентен анализ
- 🖨️ HTML отчет за печат с ортофото + анализ + диаграми
- 🌑☀️ Тъмна и светла тема

---

## Стартиране

### Вариант 1 — Директно с Python

```bash
# Клонирай
git clone https://github.com/nstoykov/naipchat.git
cd naipchat

# Инсталирай зависимости
pip install -r requirements.txt

# Конфигурирай API ключ
mkdir -p .streamlit
cat > .streamlit/secrets.toml << 'TOML'
ANTHROPIC_API_KEY = "sk-ant-api03-..."
ANTHROPIC_MODEL   = "claude-haiku-4-5-20251001"
TOML

# Стартирай
streamlit run app.py
```

Отвори: **http://localhost:8501**

---

### Вариант 2 — Docker Compose (препоръчително)

```bash
# Клонирай
git clone https://github.com/nstoykov/naipchat.git
cd naipchat

# Конфигурирай secrets
mkdir -p .streamlit
cat > .streamlit/secrets.toml << 'TOML'
ANTHROPIC_API_KEY = "sk-ant-api03-..."
ANTHROPIC_MODEL   = "claude-haiku-4-5-20251001"
TOML

# Build и стартиране
docker compose up -d --build

# Провери логовете
docker compose logs -f naipchat
```

Отвори: **http://localhost:8501**

#### Полезни Docker команди

```bash
# Спиране
docker compose down

# Рестартиране
docker compose restart naipchat

# Ъпдейт
git pull && docker compose up -d --build

# Логове
docker compose logs -f naipchat
```

---

## Конфигурация

### `.streamlit/secrets.toml` (локално и Docker)

```toml
ANTHROPIC_API_KEY = "sk-ant-api03-..."
ANTHROPIC_MODEL   = "claude-haiku-4-5-20251001"
```

### Поддържани модели

| Модел | Качество | Цена |
|-------|----------|------|
| `claude-haiku-4-5-20251001` | Добро | Ниска |
| `claude-sonnet-4-5` | Отлично | Средна |
| `claude-opus-4-5` | Най-добро | Висока |

---

## Данни

- **Ортофото:** МЗХ България — `bg-imagery.openstreetmap.org`
- **Лиценз:** © Министерство на земеделието и храните
- **Покритие:** Цяла България (39.52°N–46.45°N, 21.84°E–28.91°E)
- **Резолюция:** ~0.25м/px при zoom 18

---

## Структура

```
naipchat/
├── app.py                    # Основно приложение
├── requirements.txt          # Python зависимости
├── Dockerfile                # Docker образ
├── docker-compose.yml        # Docker Compose конфигурация
├── .env.example              # Примерни environment variables
├── .dockerignore
├── .gitignore
└── .streamlit/
    ├── config.toml           # Streamlit конфигурация
    └── secrets.toml          # API ключове (НЕ commit-вай!)
```

---

> ⚠️ **Никога не commit-вай `.streamlit/secrets.toml` или `.env`!**
