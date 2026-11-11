#!/usr/bin/env python3
"""
Prüft im Terminportal der Stadt Neuss (TEVIS), ob ein Termin für
"Abgabe einer Verpflichtungserklärung" vor einem Stichtag frei ist.

Ablauf (wie im Browser):
  1. select2?md=2           -> Anliegen-Seite (liefert Session-Cookie, mdt und Anliegen-ID)
  2. location?...&cnc-ID=1  -> Standort-Seite, zeigt "Nächster Termin: ab TT.MM.JJJJ, HH:MM Uhr"

Nur Python-Standardbibliothek, keine Abhängigkeiten.

Benachrichtigung per Telegram (optional) über Umgebungsvariablen:
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

Beispiele:
  python3 check_termin.py                 # einmal prüfen (z.B. für cron / GitHub Actions)
  python3 check_termin.py --loop 300      # alle 5 Minuten prüfen, endlos
  python3 check_termin.py --before 12.12.2026 --loop 180
"""

import argparse
import html
import http.cookiejar
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime

BASE = "https://termine.serviceportal-neuss.de"
SELECT_URL = f"{BASE}/select2?md=2"
SERVICE_NAME = "Verpflichtungserklärung"
FALLBACK_CNC_ID = "1590"  # "Abgabe einer Verpflichtungserklärung" (Stand 11/2026)
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


def log(msg: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def fetch(opener, url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with opener.open(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def find_cnc_id(page: str) -> str:
    """Sucht die ID des Anliegens anhand des Namens (falls sich die ID ändert)."""
    for m in re.finditer(r'data-tevis-cncname="([^"]*)"[^>]*?data-tevis-cncid="(\d+)"', page, re.S):
        if SERVICE_NAME.lower() in html.unescape(m.group(1)).lower():
            return m.group(2)
    return FALLBACK_CNC_ID


def find_mdt(page: str) -> str:
    m = re.search(r'name="mdt"\s+value="(\d+)"|value="(\d+)"\s+name="mdt"', page)
    if not m:
        raise RuntimeError("Parameter 'mdt' nicht gefunden - Seitenaufbau geändert?")
    return m.group(1) or m.group(2)


def get_next_appointments():
    """Liefert Liste von (Standortname, datetime) mit dem jeweils nächsten freien Termin."""
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
    )
    select_page = fetch(opener, SELECT_URL)
    mdt = find_mdt(select_page)
    cnc_id = find_cnc_id(select_page)

    query = urllib.parse.urlencode({"mdt": mdt, "select_cnc": 1, f"cnc-{cnc_id}": 1})
    location_page = fetch(opener, f"{BASE}/location?{query}")

    results = []
    # Jeder Standort steht in einem eigenen <form>; daraus Name + "Nächster Termin" lesen.
    for block in re.findall(r"<form method=\"post\">(.*?)</form>", location_page, re.S):
        term = re.search(
            r"Nächster Termin</dt>\s*<dd>\s*(?:ab\s*)?(\d{2}\.\d{2}\.\d{4})(?:,\s*(\d{1,2}:\d{2}))?",
            block,
        )
        if not term:
            continue
        name = re.search(r"<dt>Name</dt>\s*<dd[^>]*>(.*?)</dd>", block, re.S)
        name = html.unescape(re.sub(r"<[^>]+>", "", name.group(1))).strip() if name else "?"
        when = datetime.strptime(f"{term.group(1)} {term.group(2) or '00:00'}", "%d.%m.%Y %H:%M")
        results.append((name, when))

    if not results and "Nächster Termin" not in location_page:
        # Keine Termine bzw. unerwarteter Seiteninhalt – Hinweis ausgeben
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", location_page))
        if "Fehler" in text:
            raise RuntimeError("Portal meldet einen Fehler auf der Standortseite.")
    return results


def send_telegram(text: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
    try:
        with urllib.request.urlopen(
            f"https://api.telegram.org/bot{token}/sendMessage", data=data, timeout=30
        ) as resp:
            json.load(resp)
    except Exception as e:  # noqa: BLE001
        log(f"Telegram-Versand fehlgeschlagen: {e}")


def check_once(before: datetime, last_notified: set) -> bool:
    """Gibt True zurück, wenn ein früherer Termin gefunden wurde."""
    appointments = get_next_appointments()
    if not appointments:
        log("Kein freier Termin angezeigt.")
        return False

    found = False
    for name, when in appointments:
        if when < before:
            found = True
            msg = (
                f"🎉 Früher Termin für Verpflichtungserklärung frei!\n"
                f"{when:%d.%m.%Y %H:%M} Uhr – {name}\n"
                f"Jetzt buchen: {SELECT_URL}"
            )
            log(msg.replace("\n", " | "))
            key = (name, when)
            if key not in last_notified:
                send_telegram(msg)
                last_notified.add(key)
        else:
            log(f"Nächster Termin {when:%d.%m.%Y %H:%M} ({name}) – nicht vor {before:%d.%m.%Y}.")
    return found


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--before", default="12.12.2026", help="Stichtag TT.MM.JJJJ (Standard: 12.12.2026)")
    p.add_argument("--loop", type=int, metavar="SEKUNDEN", help="wiederholt prüfen, z.B. 300 = alle 5 Min.")
    args = p.parse_args()

    before = datetime.strptime(args.before, "%d.%m.%Y")
    notified: set = set()

    if not args.loop:
        try:
            return 0 if not check_once(before, notified) else 10
        except Exception as e:  # noqa: BLE001
            log(f"Fehler: {e}")
            return 1

    log(f"Starte Überwachung alle {args.loop}s, Stichtag {before:%d.%m.%Y}. Abbrechen mit Strg+C.")
    while True:
        try:
            check_once(before, notified)
        except Exception as e:  # noqa: BLE001
            log(f"Fehler: {e}")
        time.sleep(args.loop)


if __name__ == "__main__":
    sys.exit(main())
