#!/usr/bin/env python3
"""
Kufar Telegram Bot — бот для отслеживания объявлений на kufar.by
Команды:
/start — приветствие и список доступных команд
/add <url> — добавить новую ссылку для отслеживания
/list — показать все добавленные ссылки
/remove <номер> — удалить ссылку по номеру
"""

import os
import re
import time
import sqlite3
import requests
import random
import logging
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from telegram.ext import Updater, CommandHandler, CallbackContext
from telegram import Update

# --- настройки Telegram ---
TELEGRAM_BOT_TOKEN = "8342529464:AAGw9ngsU0SD-W1keIHdv_eQiN3wutAK58U"   # токен от BotFather
TELEGRAM_CHAT_ID   = 584233853                  # твой chat_id

# --- настройки базы ---
DB_PATH = "kufar_bot.db"
CHECK_INTERVAL = 60  # секунд между проверками

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# --- БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("CREATE TABLE IF NOT EXISTS links (id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS seen_ads (id TEXT PRIMARY KEY, url TEXT, first_seen_ts INTEGER)")
    conn.commit()
    return conn

# --- ПАРСИНГ ---
def ad_id_from_url(href: str):
    m = re.search(r"/vi/(\\d+)", href)
    return m.group(1) if m else None

def parse_ads(html: str, base_url: str):
    soup = BeautifulSoup(html, "lxml")
    anchors = soup.select('a[href*="/vi/"]')
    ads = []
    seen = set()
    for a in anchors:
        href = a.get("href")
        if not href:
            continue
        full = urljoin(base_url, href)
        adid = ad_id_from_url(full)
        if not adid or adid in seen:
            continue
        seen.add(adid)
        title = a.get("title") or a.get_text(" ", strip=True)
        ads.append({"id": adid, "title": title, "url": full})
    return ads

def fetch(url: str):
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    return r.text

def send_to_telegram(text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text}, timeout=20)

# --- КОМАНДЫ БОТА ---
def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "Привет! Я бот для отслеживания объявлений на Куфар 🚀\n\n"
        "Команды:\n"
        "/add <url> — добавить поиск\n"
        "/list — показать все поиски\n"
        "/remove <номер> — удалить поиск"
    )

def add_url(update: Update, context: CallbackContext):
    if not context.args:
        update.message.reply_text("Нужно указать ссылку. Пример: /add https://kufar.by/l/minsk/...")
        return
    url = context.args[0]
    conn.execute("INSERT INTO links(url) VALUES (?)", (url,))
    conn.commit()
    update.message.reply_text(f"✅ Ссылка добавлена: {url}")

def list_urls(update: Update, context: CallbackContext):
    cur = conn.execute("SELECT id, url FROM links ORDER BY id")
    rows = cur.fetchall()
    if not rows:
        update.message.reply_text("Список пуст.")
        return
    text = "\n".join([f"{row[0]}. {row[1]}" for row in rows])
    update.message.reply_text(f"Текущие поиски:\n{text}")

def remove_url(update: Update, context: CallbackContext):
    if not context.args:
        update.message.reply_text("Укажи номер поиска. Пример: /remove 1")
        return
    try:
        idx = int(context.args[0])
        conn.execute("DELETE FROM links WHERE id=?", (idx,))
        conn.commit()
        update.message.reply_text(f"🗑 Поиск {idx} удалён")
    except:
        update.message.reply_text("Ошибка: неправильный номер.")

# --- ОСНОВНОЙ ЦИКЛ ---
def check_ads():
    cur = conn.execute("SELECT url FROM links")
    urls = [row[0] for row in cur.fetchall()]
    for url in urls:
        logging.info("Проверяю %s", url)
        try:
            html = fetch(url)
        except Exception as e:
            logging.warning("Ошибка загрузки: %s", e)
            continue
        ads = parse_ads(html, url)
        for ad in ads:
            cur = conn.execute("SELECT 1 FROM seen_ads WHERE id=?", (ad["id"],))
            if cur.fetchone():
                continue
            conn.execute("INSERT INTO seen_ads (id, url, first_seen_ts) VALUES (?, ?, ?)",
                         (ad["id"], ad["url"], int(time.time())))
            conn.commit()
            send_to_telegram(f"{ad['title']}\n{ad['url']}")
            time.sleep(random.uniform(0.5, 1.5))

def run_checker():
    while True:
        check_ads()
        logging.info("Пауза %s сек", CHECK_INTERVAL)
        time.sleep(CHECK_INTERVAL)

# --- MAIN ---
if __name__ == "__main__":
    conn = init_db()

    updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("add", add_url))
    dp.add_handler(CommandHandler("list", list_urls))
    dp.add_handler(CommandHandler("remove", remove_url))

    # Запускаем проверку объявлений в отдельном потоке
    import threading
    threading.Thread(target=run_checker, daemon=True).start()

    updater.start_polling()
    updater.idle()

