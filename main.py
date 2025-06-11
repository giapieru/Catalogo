from flask import Flask, request, jsonify
from openai import OpenAI
import httpx, requests, time, os

app = Flask(__name__)

# Variabili d’ambiente
OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID      = os.getenv("ASSISTANT_ID")
GHL_REPLY_WEBHOOK = os.getenv("GHL_REPLY_WEBHOOK")

# Client HTTP personalizzato
custom_http_client = httpx.Client(proxies=None)
client = OpenAI(api_key=OPENAI_API_KEY, http_client=custom_http_client)

# Carica ListaTelefoni.txt
with open("ListaTelefoni.txt", "rb") as f:
    tool_file = client.files.create(file=f, purpose="assistants")

@app.route("/ghl-webhook", methods=["POST"])
def handle_ghl():
    data = request.json or {}

    # Estrai message
    raw_msg = data.get("message", "")
    if isinstance(raw_msg, dict):
        # GHL può inviare {"body": "...", ...}
        msg = raw_msg.get("body", "")
    else:
        msg = raw_msg
    msg = str(msg).strip()

    # Estrai number
    phone = str(data.get("number", "")).strip()
    contact_id = data.get("contact_id")  # facoltativo

    if not msg or not phone:
        return jsonify({"error": "message o number mancanti"}), 400

    try:
        # 1) crea thread e invia user message
        thread = client.beta.threads.create()
        client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=msg
        )

        # 2) avvia run con il file allegato
        run = client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=ASSISTANT_ID,
            tool_resources={"file_ids": [tool_file.id]}
        )

        # 3) attendi completamento
        for _ in range(30):
            status = client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
            if status.status == "completed":
                break
            time.sleep(1)

        # 4) prendi risposta
        messages = client.beta.threads.messages.list(thread_id=thread.id)
        reply = messages.data[0].content[0].text.value

        # 5) invia a GHL
        payload = {"phone": phone, "message": reply}
        if contact_id:
            payload["contact_id"] = contact_id

        resp = requests.post(GHL_REPLY_WEBHOOK, json=payload)
        if resp.status_code != 200:
            print("Errore GHL:", resp.status_code, resp.text)
            return jsonify({"error": "webhook GHL fallito"}), 500

        return jsonify({"status": "ok", "reply": reply})

    except Exception as e:
        print("Errore interno:", e)
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.getenv("PORT", 3000))
    app.run(host="0.0.0.0", port=port)
