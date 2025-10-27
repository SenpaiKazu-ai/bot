from flask import Flask, request
import requests
import google.generativeai as genai
import shelve
import logging
import re

# --- Logging ---
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

# --- Tokens ---
PAGE_ACCESS_TOKEN = "EAAV2ZCNDNgv0BP7YbKo6HoxtWGDeXDrr0sKqJ3qbtPN3sxoLW13ujIjp4dMTwxuoUBNWCrw0ZAwgzFxxYxk6X4TiNAWcaap3hxhZCZCmBqTAXXEG0XdGxQJOmggPX60Dwqls9xc88tyYV9cQH6wbeQZBCxFxc5VGZA5gcAIYUkXNyqa7Tfbv2q6S9TKfPYjfiZBZCZAONnZAwF"
VERIFY_TOKEN = "chatgptbot_verify_key"
GEMINI_API_KEY = "AIzaSyBjNO2w7BAyOIKQ7REiDqnT8cSI6witaeI"

# --- Conversation store ---
CONVERSATIONS_DB = "conversations.db"
MAX_HISTORY = 12

try:
    db = shelve.open(CONVERSATIONS_DB, writeback=True)
except Exception:
    db = {}

def load_history(user_id):
    return db.get(str(user_id), []).copy()

def save_history(user_id, history):
    db[str(user_id)] = history
    if hasattr(db, "sync"):
        db.sync()

def clear_history(user_id):
    save_history(user_id, [])

# --- Configure Gemini ---
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(
    "models/gemini-2.0-flash",
    system_instruction="You are a friendly Messenger chatbot that gives short, natural, and helpful replies."
)

# --- Webhook verification ---
@app.route("/webhook", methods=["GET"])
def verify():
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if token == VERIFY_TOKEN:
        return challenge
    return "Invalid verification token", 403

# --- Webhook to receive messages ---
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    logging.info("Incoming webhook data: %s", data)

    if data.get("object") == "page":
        for entry in data.get("entry", []):
            for event in entry.get("messaging", []):
                if "message" in event:
                    sender_id = event["sender"]["id"]
                    message_text = event["message"].get("text", "")
                    handle_message(sender_id, message_text)
    return "ok", 200

# --- Handle message ---
def handle_message(sender_id, message_text):
    text_lower = message_text.lower().strip()

    # Reset conversation
    if text_lower in ["reset", "start over", "clear"]:
        clear_history(sender_id)
        send_message(sender_id, "✅ Conversation reset. How can I help you now?")
        return

    # Greeting
    if re.search(r'\b(hi|hello|hey)\b', text_lower) and len(text_lower) < 30:
        greeting = "👋 Hi! This bot is made by *Jhun Mark Premacio*.\nHow can I help you today?"
        send_message(sender_id, greeting)
        return

    # Conversation-aware Gemini reply
    history = load_history(sender_id)
    history.append({"role": "user", "text": message_text})
    if len(history) > MAX_HISTORY:
        history = history[-MAX_HISTORY:]

    reply = gemini_reply(history)
    send_message(sender_id, reply)

    # Save assistant reply
    history.append({"role": "assistant", "text": reply})
    if len(history) > MAX_HISTORY:
        history = history[-MAX_HISTORY:]
    save_history(sender_id, history)

# --- Gemini reply ---
def gemini_reply(history):
    try:
        # Convert history into Gemini-compatible format
        messages = [{"role": item["role"], "parts": [{"text": item["text"]}]} for item in history]

        response = model.generate_content(
            messages,
            generation_config={"temperature": 0.8, "max_output_tokens": 300},
            safety_settings=[
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ]
        )

        # Extract reply text
        reply = getattr(response, "text", None)
        if not reply and hasattr(response, "candidates") and len(response.candidates) > 0:
            candidate = response.candidates[0]
            if hasattr(candidate, "content") and len(candidate.content.parts) > 0:
                reply = candidate.content.parts[0].text

        return reply or "I couldn’t think of a reply right now."
    except Exception as e:
        logging.error("Gemini Error: %s", e)
        return "Sorry, I couldn’t process that right now."


# --- Send message via Facebook Messenger ---
def send_message(recipient_id, text):
    url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    payload = {"recipient": {"id": recipient_id}, "message": {"text": text}}
    try:
        r = requests.post(url, json=payload)
        logging.info("Sent message status: %s, response: %s", r.status_code, r.text)
    except Exception as e:
        logging.error("Send message error: %s", e)


# --- Run Flask app ---
if __name__ == "__main__":
    app.run(port=5000)
