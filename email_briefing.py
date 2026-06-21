#!/usr/bin/env python3
"""
Email Briefing Generator
Cron: 30 7 * * *   (mattino 07:30)
      30 23 * * *  (sera   23:30)

Reads Gmail inbox, builds an HTML summary grouped by priority,
and saves a draft "Briefing Mattutino – <date>" in the target mailbox.

Setup (one-time):
  1. Google Cloud Console → enable Gmail API → OAuth2 Desktop credentials
  2. Download credentials.json into this directory
  3. Run once manually: python email_briefing.py
     A browser opens for authorization; token.json is saved for future runs.

Install deps:
  pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client
"""

import base64
import html as _html
import os
import re
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# ── Config ────────────────────────────────────────────────────────────────────

TARGET_EMAIL    = "coletti.umberto.f@gmail.com"
CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), "credentials.json")
TOKEN_FILE       = os.path.join(os.path.dirname(__file__), "token.json")
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
]

MAX_THREADS = 40
HOURS_BACK  = 12   # 12h window: morning covers night, evening covers day

# (keyword-list, color-key) — first match wins
PRIORITY_RULES = [
    (["urgente", "contestazione", "distacco", "riattivazione",
      "win-back", "sw-out", "scadenza", "diffida"], "red"),
    (["pagamento", "fattura", "bonifico", "rata", "contabile",
      "cliente", "contratto", "preventivo"], "orange"),
    (["google", "verifica", "aggiorna", "profilo",
      "lavoro", "proposta", "calendario", "orario"], "blue"),
    (["ordine", "spedizione", "consegna", "tracking",
      "back market", "amazon", "dhl"], "green"),
]

COLORS = {
    "red":    ("🔴", "#e74c3c", "#fdf6f6", "Da gestire"),
    "orange": ("🟠", "#e67e22", "#fdf9f3", "Da leggere / verificare"),
    "blue":   ("🔵", "#3498db", "#f3f8fd", "Aggiornamenti"),
    "green":  ("🟢", "#27ae60", "#f4fdf6", "Ordini e spedizioni"),
    "grey":   ("⚪", "#95a5a6", "#f9f9f9", "Promozioni / altro"),
}

# ── Auth ──────────────────────────────────────────────────────────────────────

def get_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as fh:
            fh.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)

# ── Fetch ─────────────────────────────────────────────────────────────────────

def fetch_threads(service):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=HOURS_BACK)
    query  = f"in:inbox after:{cutoff.strftime('%Y/%m/%d')} -in:draft -in:sent"
    result = service.users().threads().list(
        userId="me", q=query, maxResults=MAX_THREADS
    ).execute()
    return result.get("threads", [])


def thread_detail(service, tid):
    t = service.users().threads().get(userId="me", threadId=tid, format="full").execute()
    msgs = t.get("messages", [])
    if not msgs:
        return None
    msg = msgs[-1]
    hdrs  = {h["name"].lower(): h["value"] for h in msg["payload"].get("headers", [])}
    labels = msg.get("labelIds", [])
    attachments = _attachments(msg["payload"])
    return {
        "subject":     hdrs.get("subject", "(nessun oggetto)"),
        "sender":      hdrs.get("from", "sconosciuto"),
        "date_raw":    hdrs.get("date", ""),
        "body":        _body(msg["payload"])[:400],
        "attachments": attachments,
        "unread":      "UNREAD" in labels,
        "important":   "IMPORTANT" in labels,
    }


def _body(payload):
    if "parts" in payload:
        for p in payload["parts"]:
            if p["mimeType"] == "text/plain":
                data = p["body"].get("data", "")
                if data:
                    return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace").strip()
            nested = _body(p)
            if nested:
                return nested
        # Fallback: try text/html parts when no plain-text is found
        for p in payload["parts"]:
            if p["mimeType"] == "text/html":
                data = p["body"].get("data", "")
                if data:
                    raw = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
                    return re.sub(r"<[^>]+>", " ", raw).strip()
    elif payload.get("mimeType") == "text/plain":
        data = payload["body"].get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace").strip()
    elif payload.get("mimeType") == "text/html":
        data = payload["body"].get("data", "")
        if data:
            raw = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
            return re.sub(r"<[^>]+>", " ", raw).strip()
    return ""


def _attachments(payload):
    names = []
    for p in payload.get("parts", []):
        if p.get("filename"):
            names.append(p["filename"])
        names.extend(_attachments(p))
    return names

# ── Priority ──────────────────────────────────────────────────────────────────

def priority(t):
    text = (t["subject"] + " " + t["sender"]).lower()
    for kws, color in PRIORITY_RULES:
        if any(k in text for k in kws):
            return color
    return "grey"

# ── HTML ──────────────────────────────────────────────────────────────────────

def _card(t):
    color = priority(t)
    icon, border, bg, _ = COLORS[color]
    attach_names = _html.escape(", ".join(t["attachments"][:3]))
    attach = f"<li>📎 {attach_names}</li>" if t["attachments"] else ""
    unread = " <span style='color:#e74c3c;font-size:11px;'>[NON LETTO]</span>" if t["unread"] else ""
    body_text    = t["body"].replace("\n", " ").replace("\r", "")
    preview      = _html.escape(body_text[:300])
    ellipsis     = "…" if len(body_text) > 300 else ""
    subject_safe = _html.escape(t["subject"])
    sender_safe  = _html.escape(t["sender"])
    date_safe    = _html.escape(t["date_raw"])
    return (color, f"""
<div style="margin-bottom:14px;padding:13px;border-left:4px solid {border};
            background:{bg};border-radius:4px;">
  <p style="margin:0 0 3px 0;"><strong>{icon} {subject_safe}</strong>{unread}</p>
  <p style="margin:0 0 5px 0;color:#666;font-size:12px;">
    Da: <strong>{sender_safe}</strong> — {date_safe}
  </p>
  <ul style="margin:4px 0;padding-left:16px;font-size:13px;">
    <li>{preview}{ellipsis}</li>
    {attach}
  </ul>
</div>""")


def build_html(threads, label, today_str):
    by_color: dict[str, list[str]] = {k: [] for k in COLORS}
    for t in threads:
        color, card = _card(t)
        by_color[color].append(card)

    sections = ""
    for color, (icon, border, _, title) in COLORS.items():
        cards = by_color[color]
        if not cards:
            continue
        sections += f"""
<h3 style="color:{border};margin:18px 0 8px 0;">{icon} {title}</h3>
{"".join(cards)}"""

    total  = len(threads)
    unread = sum(1 for t in threads if t["unread"])

    return f"""<html>
<body style="font-family:Arial,sans-serif;font-size:14px;color:#222;
             max-width:720px;margin:auto;padding:20px;">
<h2 style="border-bottom:3px solid #4A90D9;padding-bottom:10px;color:#1a3a5c;">
  📋 {label} — {today_str}
</h2>
<p style="color:#666;font-size:13px;margin-top:0;">
  Casella: <strong>{TARGET_EMAIL}</strong> &nbsp;|&nbsp;
  Email: <strong>{total}</strong> &nbsp;|&nbsp;
  Non lette: <strong>{unread}</strong>
</p>
<hr style="border:none;border-top:1px solid #ddd;margin:14px 0;">
{sections}
<hr style="border:none;border-top:1px solid #ddd;margin:20px 0;">
<p style="color:#bbb;font-size:11px;text-align:center;">
  Generato automaticamente — {today_str} | {TARGET_EMAIL}
</p>
</body></html>"""

# ── Draft ─────────────────────────────────────────────────────────────────────

def create_draft(service, html, subject):
    mime = MIMEMultipart("alternative")
    mime["to"]      = TARGET_EMAIL
    mime["from"]    = TARGET_EMAIL
    mime["subject"] = subject
    mime.attach(MIMEText(html, "html"))
    raw   = base64.urlsafe_b64encode(mime.as_bytes()).decode()
    draft = service.users().drafts().create(
        userId="me", body={"message": {"raw": raw}}
    ).execute()
    return draft["id"]

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    now       = datetime.now()
    today_str = now.strftime("%d %B %Y")
    label     = "Briefing Serale" if now.hour >= 12 else "Briefing Mattutino"
    subject   = f"{label} – {today_str}"

    print(f"[briefing] Avvio — {now.strftime('%d/%m/%Y %H:%M')}")

    service = get_service()
    print("[briefing] Autenticazione OK")

    raw = fetch_threads(service)
    print(f"[briefing] Thread trovati: {len(raw)}")

    threads = [d for t in raw if (d := thread_detail(service, t["id"]))]
    threads.sort(key=lambda t: (not t["important"], not t["unread"]))

    if not threads:
        print("[briefing] Nessuna email nel periodo — bozza non creata.")
        return

    html     = build_html(threads, label, today_str)
    draft_id = create_draft(service, html, subject)
    print(f"[briefing] Bozza creata — ID: {draft_id}")
    print(f"[briefing] Oggetto: {subject}")


if __name__ == "__main__":
    main()
