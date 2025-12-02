from flask import Flask
import threading
import time
import requests
from bs4 import BeautifulSoup
import os
import json

# === CONFIGURAÇÕES ===
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK_URL")  # webhook do Discord
WATCHED_PLAYERS = os.environ.get("WATCHED_PLAYERS", "").split(",")  # jogadores separados por vírgula
CHECK_INTERVAL = 60  # intervalo de checagem em segundos
MIN_LEVEL = 690  # nível mínimo para considerar up/morte

STATE_FILE = "last_levels.json"

# === SERVIDOR FLASK PARA MANTER ONLINE ===
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Bot Tenkai está rodando!", 200

# === FUNÇÕES ===

def get_online_players():
    url = 'https://ntotenkai.com.br/online'
    headers = {
        "User-Agent": "Mozilla/5.0"
    }
    try:
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
    except Exception as e:
        print(f"[ERRO] Falha ao acessar o site: {e}")
        return []

    soup = BeautifulSoup(r.text, 'html.parser')
    players = []

    for row in soup.select('tr'):
        cols = row.find_all('td')
        if len(cols) >= 2 and cols[1].text.strip().isdigit():
            name = cols[0].text.strip()
            level = int(cols[1].text.strip())
            players.append((name, level))
    return players


def send_embed_to_discord(jogador, old_level, new_level):
    embed = {
        "title": "☠️ UPOU PARA MORRER",
        "description": f"**{jogador}** subiu de nível e já vai morrer kkkk xd ☠️🔪",
        "color": 0x00ff00,
        "fields": [
            {"name": "💩 Jogador", "value": jogador, "inline": True},
            {"name": "📈 Level", "value": f"{old_level} → {new_level}", "inline": True}
        ],
        "footer": {"text": "🔥 JOHTTO HACKER DEUS"}
    }
    payload = {"embeds": [embed]}

    try:
        response = requests.post(DISCORD_WEBHOOK, json=payload)
        if response.status_code not in [200, 204]:
            print(f"[ERRO] Webhook falhou com status {response.status_code}")
            print(f"[RESPOSTA] {response.text}")
        else:
            print("[OK] Mensagem de UP enviada ao Discord.")
    except Exception as e:
        print(f"[ERRO] Falha ao enviar embed de UP: {e}")


def send_death_embed_to_discord(jogador, old_level, new_level):
    embed = {
        "title": "💀 XIIII MORREU NOOB",
        "description": f"☠️ **{jogador}** já morreu noobasso",
        "color": 0xff0000,
        "fields": [
            {"name": "💩 Jogador", "value": jogador, "inline": True},
            {"name": "📉 Level", "value": f"{old_level} → {new_level}", "inline": True}
        ],
        "footer": {"text": "🔥 JOHTTO HACKER DEUS"}
    }
    payload = {"embeds": [embed]}

    try:
        response = requests.post(DISCORD_WEBHOOK, json=payload)
        if response.status_code not in [200, 204]:
            print(f"[ERRO] Webhook falhou com status {response.status_code}")
            print(f"[RESPOSTA] {response.text}")
        else:
            print("[OK] Mensagem de MORTE enviada ao Discord.")
    except Exception as e:
        print(f"[ERRO] Falha ao enviar embed de MORTE: {e}")


def load_last_levels():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    else:
        return {}


def save_last_levels(levels):
    with open(STATE_FILE, "w") as f:
        json.dump(levels, f)


def monitor():
    last_levels = load_last_levels()

    while True:
        print("🔍 Verificando jogadores online...")
        players_online = get_online_players()
        online_dict = {name: level for name, level in players_online}

        for player in WATCHED_PLAYERS:
            player = player.strip()
            current_level = online_dict.get(player)
            last_level = last_levels.get(player)

            if current_level is not None and current_level >= MIN_LEVEL:
                if last_level is None:
                    print(f"🔸 Primeiro registro de {player}: nível {current_level}")
                    last_levels[player] = current_level

                elif current_level > last_level:
                    print(f"🚀 {player} upou! {last_level} → {current_level} 🎉")
                    send_embed_to_discord(player, last_level, current_level)
                    last_levels[player] = current_level

                elif current_level < last_level:
                    print(f"💀 {player} morreu ou perdeu XP! {last_level} → {current_level}")
                    send_death_embed_to_discord(player, last_level, current_level)
                    last_levels[player] = current_level

                else:
                    print(f"✅ {player} está no nível {current_level} (sem up ou down).")

            elif current_level is not None and current_level < MIN_LEVEL:
                print(f"⚠️ {player} está no nível {current_level}, abaixo do mínimo ({MIN_LEVEL}). Ignorado.")

            else:
                print(f"❌ {player} está offline.")

        save_last_levels(last_levels)
        print(f"🕒 Aguardando {CHECK_INTERVAL} segundos...\n")
        time.sleep(CHECK_INTERVAL)

# === EXECUÇÃO ===
if __name__ == "__main__":
    t = threading.Thread(target=monitor)
    t.daemon = True
    t.start()

    app.run(host="0.0.0.0", port=8080)
