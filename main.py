from flask import Flask
import threading
import time
import requests
from bs4 import BeautifulSoup
import os
import json
from urllib.parse import quote_plus

# =========================
# VARIÁVEIS (IGUAL TAIKAI)
# =========================

DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK_URL")

_raw_players = os.environ.get("WATCHED_PLAYERS", "")
WATCHED_PLAYERS = [
    p.strip() for p in _raw_players.replace(";", ",").split(",") if p.strip()
]

CHECK_INTERVAL = 60        # padrão igual Taikai
MIN_LEVEL = 1              # padrão igual Taikai
STATE_FILE = "last_levels.json"

# URL fixa (igual Taikai usa interna no código)
def build_profile_url(name):
    encoded = quote_plus(name)
    return f"https://ntotenkai.com.br/?characters/{encoded}"

# =========================
# FLASK KEEP ALIVE
# =========================

app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Bot Tenkai rodando! Monitora: " + ", ".join(WATCHED_PLAYERS), 200

# =========================
# ARQUIVO DE ESTADO
# =========================

def load_last_levels():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_last_levels(data):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# =========================
# EMBEDS DISCORD
# =========================

def send_up_embed(player, old, new):
    diff = new - old
    embed = {
        "title": "☠️ UPOU PARA MORRER",
        "description": f"**{player}** subiu de nível e já vai morrer kkkk xd ☠️🔪",
        "color": 0x00FF00,
        "fields": [
            {"name": "💩 Jogador", "value": player, "inline": True},
            {"name": "📈 Level", "value": f"{old} → {new} (+{diff})", "inline": True},
        ],
        "footer": {"text": "🔥 JOHTTO HACKER DEUS"},
    }
    requests.post(DISCORD_WEBHOOK, json={"embeds": [embed]})


def send_death_embed(player, old, new):
    embed = {
        "title": "💀 XIIII MORREU NOOB",
        "description": f"☠️ **{player}** já morreu noobasso",
        "color": 0xFF0000,
        "fields": [
            {"name": "💩 Jogador", "value": player, "inline": True},
            {"name": "📉 Level", "value": f"{old} → {new}", "inline": True},
        ],
        "footer": {"text": "🔥 JOHTTO HACKER DEUS"},
    }
    requests.post(DISCORD_WEBHOOK, json={"embeds": [embed]})

# =========================
# RASPAGEM DE LEVEL
# =========================

def get_level_from_profile(name):
    url = build_profile_url(name)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/142.0.0.0 Safari/537.36"
        )
    }

    try:
        r = requests.get(url, headers=headers, timeout=10)
    except Exception as e:
        print(f"[ERRO] Falha ao acessar {name}: {e}")
        return None

    if r.status_code != 200:
        print(f"[ERRO] Perfil de {name} retornou {r.status_code}")
        return None

    soup = BeautifulSoup(r.text, "html.parser")

    td_level = soup.find("td", string=lambda s: s and s.strip().lower() == "level:")
    if not td_level:
        print(f"[ERRO] Level não encontrado em {name}")
        return None

    value = td_level.find_next("td").text.strip()

    if not value.isdigit():
        print(f"[ERRO] Level inválido para {name}: {value}")
        return None

    return int(value)

# =========================
# LOOP PRINCIPAL
# =========================

def monitor_loop():
    print("▶ Monitorando:", WATCHED_PLAYERS)
    print("Intervalo:", CHECK_INTERVAL)

    last_levels = load_last_levels()

    while True:
        for player in WATCHED_PLAYERS:
            level = get_level_from_profile(player)
            if level is None:
                print(f"❌ {player}: falha no perfil")
                continue

            old = last_levels.get(player)

            if level < MIN_LEVEL:
                print(f"⚠️ {player} ({level}) < MIN_LEVEL")
                last_levels[player] = level
                continue

            if old is None:
                print(f"🟦 Primeiro registro: {player} = {level}")
                last_levels[player] = level

            elif level > old:
                print(f"🚀 UP: {player} {old} → {level}")
                send_up_embed(player, old, level)
                last_levels[player] = level

            elif level < old:
                print(f"💀 DOWN: {player} {old} → {level}")
                send_death_embed(player, old, level)
                last_levels[player] = level

            else:
                print(f"✔ {player}: {level}")

        save_last_levels(last_levels)
        print(f"⏳ Aguardando {CHECK_INTERVAL}s...\n")
        time.sleep(CHECK_INTERVAL)

# =========================
# MAIN
# =========================

if __name__ == "__main__":
    t = threading.Thread(target=monitor_loop, daemon=True)
    t.start()

    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
