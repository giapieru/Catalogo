from flask import Flask, request, jsonify
from openai import OpenAI
import requests
import json
import time

app = Flask(__name__)

# Le tue credenziali fisse
OPENAI_API_KEY = "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"
ASSISTANT_ID = "asst_MzHjj7TaYiFYakt65gdu7M3X"
GHL_REPLY_WEBHOOK = "https://services.leadconnectorhq.com/hooks/0PScOB7crfFPy3tRC5Zw/webhook-trigger/fcf8a005-4d74-4ce6-8758-003afae98833"

client = OpenAI(api_key=OPENAI_API_KEY)

# Carica ListaTelefoni.txt come file per l’assistente
with open("ListaTelefoni.txt", "rb") as f:
    tool_file = client.files.create(file=f, purpose="assistants")

@app.route("/ghl-webhook", methods=["POST"])
def handle_ghl():
    data = request.json
    msg = data.get("message", "")
    contact_id = data.get("contact_id", "")
    phone = data.get("phone", "")

    if not all([msg, contact_id, phone]):
        return jsonify({"error": "Dati mancanti"}), 400

    # Crea nuovo thread
    thread = client.beta.threads.create()

    # Invia messaggio dell’utente
    client.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content=msg
    )

    # Avvia run con file allegato
    run = client.beta.threads.runs.create(
        thread_id=thread.id,
        assistant_id=ASSISTANT_ID,
        tool_resources={"file_ids": [tool_file.id]}
    )

    # Attendi la risposta
    for _ in range(30):
        run_status = client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
        if run_status.status == "completed":
            break
        elif run_status.status == "failed":
            return jsonify({"error": "Run fallito"}), 500
        time.sleep(1)

    # Recupera risposta
    messages = client.beta.threads.messages.list(thread_id=thread.id)
    reply = messages.data[0].content[0].text.value

    # Invia la risposta al webhook GHL
    requests.post(GHL_REPLY_WEBHOOK, json={
        "phone": phone,
        "message": reply,
        "contact_id": contact_id
    })

    return jsonify({"status": "ok", "reply": reply})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000)
