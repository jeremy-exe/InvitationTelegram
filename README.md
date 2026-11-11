# Termin-Checker Verpflichtungserklärung (Neuss)

`check_termin.py` ruft das Terminportal
<https://termine.serviceportal-neuss.de/select2?md=2> auf, wählt das Anliegen
**„Abgabe einer Verpflichtungserklärung“** und liest auf der Standortseite den
„Nächsten Termin“ aus. Liegt er **vor dem 12.12.2026** (einstellbar), gibt es eine Meldung.

Nur Python 3 nötig, keine zusätzlichen Pakete.

## Lokal laufen lassen (alle 5 Minuten)

```bash
python3 check_termin.py --loop 300
```

Anderer Stichtag / kürzeres Intervall:

```bash
python3 check_termin.py --before 12.12.2026 --loop 180
```

Einmaliger Check (Exit-Code `10` = früher Termin gefunden, `0` = keiner, `1` = Fehler),
z.B. per cron:

```
*/5 * * * * cd /pfad/zum/repo && /usr/bin/python3 check_termin.py >> termin.log 2>&1
```

## Telegram-Benachrichtigung

1. Bei [@BotFather](https://t.me/BotFather) einen Bot anlegen → Token.
2. Dem Bot eine Nachricht schreiben, dann `https://api.telegram.org/bot<TOKEN>/getUpdates`
   öffnen und `chat.id` ablesen.
3. Umgebungsvariablen setzen:

```bash
export TELEGRAM_BOT_TOKEN="123456:ABC..."
```

```bash
export TELEGRAM_CHAT_ID="123456789"
```

Im `--loop`-Modus wird jeder gefundene Termin nur einmal gemeldet.

## Automatisch über GitHub Actions

`.github/workflows/check-termin.yml` läuft alle 5 Minuten (GitHub verzögert geplante
Läufe teils um einige Minuten). Dafür im Repo unter *Settings → Secrets and variables →
Actions* `TELEGRAM_BOT_TOKEN` und `TELEGRAM_CHAT_ID` anlegen. Ohne Telegram wird der Job
bei einem Treffer rot und GitHub schickt eine E-Mail. Geplante Workflows laufen nur
auf dem Default-Branch.
