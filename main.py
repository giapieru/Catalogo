from flask import Flask, request, jsonify
from openai import OpenAI
import requests
import time
import os

app = Flask(__name__)

# Usa variabili d'ambiente (nessuna chiave esposta!)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID = os.getenv("ASSISTANT_ID")
GHL_REPLY_WEBHOOK = os.getenv("GHL_REPLY_WEBHOOK")

client = OpenAI(api_key=OPENAI_API_KEY, http_client=None)

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

    try:
        thread = client.beta.threads.create()
        client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=msg
        )

        run = client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=ASSISTANT_ID,
            tool_resources={"file_ids": [tool_file.id]}
        )

        for _ in range(30):
            run_status = client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
            if run_status.status == "completed":
                break
            elif run_status.status == "failed":
                return jsonify({"error": "Run fallito"}), 500
            time.sleep(1)

        messages = client.beta.threads.messages.list(thread_id=thread.id)
        reply = messages.data[0].content[0].text.value

        requests.post(GHL_REPLY_WEBHOOK, json={
            "phone": phone,
            "message": reply,
            "contact_id": contact_id
        })

        return jsonify({"status": "ok", "reply": reply})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000)
