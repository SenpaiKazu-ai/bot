from flask import Flask, request
import requests
import google.generativeai as genai
import shelve

app = Flask(__name__)

# Replace these with your own tokens
PAGE_ACCESS_TOKEN = "EAAV2ZCNDNgv0BP38JFnsFXVOc5XIJ7rYBiOZAXSqNbVZBmrMgQvDCKXTzwz9umUDH6sRRtqZBOlGBkVGtWxZCr9gilya4ng84bgDmHOjr8lAGnPICn3kMidNqKLZAY5kJtuoldWwbZCISU38pwXn8T2T7TcNhZAFdhrsgXxF7e68RrkvlbQZAXedtZBypz3tN0gXCgT86iHmYIEnToVbNsuu9yuZCRzYoSDFSZAeJWIBANUZD"
VERIFY_TOKEN = "chatgptbot_verify_key"
GEMINI_API_KEY = "AIzaSyBjNO2w7BAyOIKQ7REiDqnT8cSI6witaeI"

# --- Conversation store (persisted) ---
CONVERSATIONS_DB = "conversations.db"  # file used by shelve
MAX_HISTORY = 12  # max messages to keep (user+assistant entries)

try:
    db = shelve.open(CONVERSATIONS_DB, writeback=True)
except Exception:
    # fallback to in-memory dict if shelve fails
    db = {}

def load_history(user_id):
    try:
        return db.get(str(user_id), []).copy()
    except Exception:
        return []

def save_history(user_id, history):
    try:
        db[str(user_id)] = history
        if hasattr(db, "sync"):
            db.sync()
    except Exception:
        pass

def clear_history(user_id):
    save_history(user_id, [])

# --- Configure Gemini ---
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(
    "models/gemini-2.0-flash",
    system_instruction="You are a friendly Messenger chatbot that gives short, natural, and helpful replies."
)

@app.route("/webhook", methods=["GET"])
def verify():
    if request.args.get("hub.verify_token") == VERIFY_TOKEN:
        return request.args.get("hub.challenge")
    return "Invalid verification token", 403


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    if data.get("object") == "page":
        for entry in data.get("entry", []):
            for event in entry.get("messaging", []):
                if "message" in event:
                    sender_id = event["sender"]["id"]
                    message_text = event["message"].get("text", "")
                    message_text_lower = message_text.lower().strip()

                    # --- Reset conversation ---
                    if message_text_lower in ["reset", "start over", "clear"]:
                        clear_history(sender_id)
                        send_message(sender_id, "✅ Conversation reset. How can I help you now?")
                        continue

                    # --- Greeting check ---
                    if any(word in message_text_lower for word in ["hi", "hello", "hey"]) and len(message_text_lower) < 20:
                        greeting = "👋 Hi! This bot is made by *Jhun Mark Premacio*.\nHow can I help you today?"
                        send_message(sender_id, greeting)
                        continue  # stop here, don’t send to Gemini yet

                    # --- Conversation-aware flow (Gemini reply) ---
                    history = load_history(sender_id)

                    # Append user's incoming message to history
                    history.append({"role": "user", "text": message_text})

                    # Trim history to keep size bounded
                    if len(history) > MAX_HISTORY:
                        history = history[-MAX_HISTORY:]

                    reply = gemini_reply(history)  # send full history
                    send_message(sender_id, reply)

                    # Save assistant reply back to history
                    history.append({"role": "assistant", "text": reply})
                    if len(history) > MAX_HISTORY:
                        history = history[-MAX_HISTORY:]
                    save_history(sender_id, history)
    return "ok", 200

def gemini_reply(history):
    try:
        # Convert conversation history into the format expected by the SDK
        messages = []
        for item in history:
            role = item.get("role", "user")
            text = item.get("text", "")
            messages.append({"role": role, "parts": [text]})

        response = model.generate_content(
            messages,
            generation_config={
                "temperature": 0.8,
                "max_output_tokens": 300,
            },
            safety_settings=[
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ],
        )

        # Try getting text from multiple possible structures
        reply = getattr(response, "text", None)
        if not reply and hasattr(response, "candidates"):
            reply = response.candidates[0].content.parts[0].text
        return reply or "I couldn’t think of a reply right now."
    except Exception as e:
        print("Gemini Error:", e)
        return "Sorry, I couldn’t process that right now."


def send_message(recipient_id, text):
    url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": text}
    }
    requests.post(url, json=payload)


if __name__ == "__main__":
    app.run(port=5000)





