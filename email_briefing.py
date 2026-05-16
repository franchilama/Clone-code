#!/usr/bin/env python3
"""
Email Morning Briefing Generator

Reads emails from the last 24 hours via Gmail API (OAuth2),
builds an HTML summary, and saves it as a draft with subject
"Briefing Mattutino – <date>" in the target mailbox.

Usage:
    python email_briefing.py

Requirements:
    pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client

Setup:
    1. Go to https://console.cloud.google.com/
    2. Create a project, enable Gmail API
    3. Create OAuth 2.0 credentials (Desktop app)
    4. Download credentials.json into this directory
    5. On first run, a browser window opens for authorization
       The token is saved in token.json for subsequent runs.
"""

import base64
import json
import os
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# ── Configuration ────────────────────────────────────────────────────────────

TARGET_EMAIL = "coletti.umberto.f@gmail.com"
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
]
MAX_THREADS = 30   # max threads to fetch per run
HOURS_BACK = 24    # look back window in hours

# Priority keywords (subject/sender → badge color)
PRIORITY_RULES = [
    (["urgente", "contestazione", "distacco", "riattivazione", "scadenza"], "red"),
    (["pagamento", "fattura", "bonifico", "rata", "contabile"], "orange"),
    (["google", "verifica", "aggiorna", "profilo"], "blue"),
    (["ordine", "spedizione", "consegna", "tracking"], "green"),
]

BADGE_STYLE = {
    "red":    ("🔴", "#e74c3c", "#fdf6f6"),
    "orange": ("🟠", "#e67e22", "#fdf9f3"),
    "blue":   ("🔵", "#3498db", "#f3f8fd"),
    "green":  ("🟢", "#27ae60", "#f4fdf6"),
    "grey":   ("⚪", "#95a5a6", "#f9f9f9"),
}

# ── Gmail Auth ────────────────────────────────────────────────────────────────

def get_gmail_service():
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


# ── Email Fetching ────────────────────────────────────────────────────────────

def fetch_threads(service, hours_back=HOURS_BACK):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    date_str = cutoff.strftime("%Y/%m/%d")
    query = f"in:inbox after:{date_str} -in:draft"
    result = service.users().threads().list(
        userId="me", q=query, maxResults=MAX_THREADS
    ).execute()
    return result.get("threads", [])


def get_thread_detail(service, thread_id):
    thread = service.users().threads().get(
        userId="me", threadId=thread_id, format="full"
    ).execute()
    messages = thread.get("messages", [])
    if not messages:
        return None

    msg = messages[-1]  # latest message in thread
    headers = {h["name"].lower(): h["value"] for h in msg["payload"]["headers"]}

    subject = headers.get("subject", "(nessun oggetto)")
    sender = headers.get("from", "sconosciuto")
    to = headers.get("to", "")
    date_raw = headers.get("date", "")
    label_ids = msg.get("labelIds", [])

    body = extract_body(msg["payload"])
    attachments = extract_attachment_names(msg["payload"])

    return {
        "thread_id": thread_id,
        "subject": subject,
        "sender": sender,
        "to": to,
        "date_raw": date_raw,
        "body": body[:800],   # truncate for summary
        "attachments": attachments,
        "unread": "UNREAD" in label_ids,
        "important": "IMPORTANT" in label_ids,
    }


def extract_body(payload):
    body = ""
    if "parts" in payload:
        for part in payload["parts"]:
            if part["mimeType"] == "text/plain":
                data = part["body"].get("data", "")
                if data:
                    body = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
                    break
            elif "parts" in part:
                body = extract_body(part)
                if body:
                    break
    elif payload["mimeType"] == "text/plain":
        data = payload["body"].get("data", "")
        if data:
            body = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
    return body.strip()


def extract_attachment_names(payload):
    names = []
    for part in payload.get("parts", []):
        filename = part.get("filename", "")
        if filename:
            names.append(filename)
        names.extend(extract_attachment_names(part))
    return names


# ── Priority Detection ────────────────────────────────────────────────────────

def detect_priority(thread):
    text = (thread["subject"] + " " + thread["sender"]).lower()
    for keywords, color in PRIORITY_RULES:
        if any(k in text for k in keywords):
            return color
    if thread["unread"] or thread["important"]:
        return "blue"
    return "grey"


# ── HTML Generation ───────────────────────────────────────────────────────────

def build_thread_card(thread):
    color = detect_priority(thread)
    icon, border, bg = BADGE_STYLE[color]

    attach_line = ""
    if thread["attachments"]:
        names = ", ".join(thread["attachments"][:3])
        attach_line = f"<li>📎 <strong>Allegati:</strong> {names}</li>"

    unread_badge = " <span style='color:#e74c3c;font-size:11px;'>[NON LETTO]</span>" if thread["unread"] else ""
    body_preview = thread["body"].replace("\n", " ").replace("\r", "")[:300]

    return f"""
<div style="margin-bottom:18px; padding:14px; border-left:4px solid {border};
            background:{bg}; border-radius:4px;">
  <p style="margin:0 0 4px 0;">
    <strong>{icon} {thread['subject']}</strong>{unread_badge}
  </p>
  <p style="margin:0 0 4px 0; color:#555; font-size:12px;">
    Da: <strong>{thread['sender']}</strong> — {thread['date_raw']}
  </p>
  <ul style="margin:8px 0 0 0; padding-left:18px; font-size:13px;">
    <li>{body_preview}…</li>
    {attach_line}
  </ul>
</div>"""


def build_html(threads, today_str):
    cards = "\n".join(build_thread_card(t) for t in threads)
    count = len(threads)
    unread = sum(1 for t in threads if t["unread"])

    return f"""<html>
<body style="font-family:Arial,sans-serif; font-size:14px; color:#222;
             max-width:700px; margin:auto; padding:20px;">

<h2 style="border-bottom:2px solid #4A90D9; padding-bottom:8px; color:#1a3a5c;">
  📋 Briefing Mattutino — {today_str}
</h2>
<p style="color:#555; font-size:13px;">
  Casella: <strong>{TARGET_EMAIL}</strong> &nbsp;|&nbsp;
  Email totali: <strong>{count}</strong> &nbsp;|&nbsp;
  Non lette: <strong>{unread}</strong>
</p>

<hr style="border:none; border-top:1px solid #ddd; margin:16px 0;">

{cards}

<hr style="border:none; border-top:1px solid #ddd; margin:20px 0;">
<p style="color:#999; font-size:12px; text-align:center;">
  Briefing generato automaticamente — {today_str} | {TARGET_EMAIL}
</p>
</body>
</html>"""


# ── Draft Creation ────────────────────────────────────────────────────────────

def create_draft(service, html_body, today_str):
    subject = f"Briefing Mattutino – {today_str}"

    mime = MIMEMultipart("alternative")
    mime["to"] = TARGET_EMAIL
    mime["from"] = TARGET_EMAIL
    mime["subject"] = subject
    mime.attach(MIMEText(html_body, "html"))

    raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
    draft = service.users().drafts().create(
        userId="me", body={"message": {"raw": raw}}
    ).execute()
    return draft["id"]


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    today_str = datetime.now().strftime("%d %B %Y")
    print(f"[briefing] Avvio — {today_str}")

    service = get_gmail_service()
    print("[briefing] Autenticazione Gmail OK")

    raw_threads = fetch_threads(service)
    print(f"[briefing] Trovati {len(raw_threads)} thread nell'ultima finestra")

    threads = []
    for rt in raw_threads:
        detail = get_thread_detail(service, rt["id"])
        if detail:
            threads.append(detail)

    if not threads:
        print("[briefing] Nessuna email trovata — bozza non creata.")
        return

    threads.sort(key=lambda t: (not t["important"], not t["unread"]))

    html = build_html(threads, today_str)
    draft_id = create_draft(service, html, today_str)
    print(f"[briefing] Bozza creata con successo — ID: {draft_id}")
    print(f"[briefing] Oggetto: 'Briefing Mattutino – {today_str}'")
    print(f"[briefing] Destinatario: {TARGET_EMAIL}")


if __name__ == "__main__":
    main()
