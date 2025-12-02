import os
import time
import json
import threading

import requests
from bs4 import BeautifulSoup
from flask import Flask

# ==========================
# VARIÁVEIS DE AMBIENTE
# ==========================

DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()

PROXY_HOST = os.environ.get("PROXY_HOST", "").strip()
PROXY_PORT = os.environ.get("PROXY_PORT", "").strip()
PROXY_USER = os.environ.get("PROXY_USER", "").strip()
PROXY_PASS = os.environ.get("PROXY_PASS", "").strip()

_raw_players = os.environ.get("WATCHED_PLAYERS", "")

WATCHED_PLAYERS = [
    p.strip() for p in _raw_players.replace(";", ",").split(",") if p.strip()
]

ONLINE_URL = "https://ntotenkai.com.br/online"
CHECK_INTERVAL = 60  # segundos
STATE_FILE = "last_levels.json"

# ==========================
# CONFIG DO PROXY
# ==========================

def build_proxy_dict():
    if not (PROXY_HOST and PROXY_PORT and PROXY_USER and PROXY_PASS):
        print("[AVISO] Proxy não configurado completamente. Acesso direto será usado (pode dar 403).")
        return None

    proxy_url = f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}:{PROXY_PORT}"
    print(f"[INFO] Usando proxy: {PROXY_HOST}:{PROXY_PORT}")
    return {
