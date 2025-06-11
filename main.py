from flask import Flask, request, jsonify
from openai import OpenAI
import httpx, requests, time, os

app = Flask(__name__)

OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID      = os.getenv("ASSISTANT_ID")
GHL_REPLY_WEBHOOK = os.getenv("GHL_REPLY_WEBHOOK")

custom_http_client = httpx.Client(proxies=None)
client = OpenAI(api_key=OPENAI_API_KEY, http_client=custom_http_client)

# Carica ListaTelefoni.txt
with open("ListaTelefoni.txt", "rb") as f:
    tool_file = client.files.create(file=f, purpose="assistants")

@app.route("/ghl-webhook", methods=["POST"])
def handle_ghl():
    try:
        data = request.json or {}
        print("🔔 Payload in ingresso:", data)

        msg = str(data.get("message", "")).strip()
        phone = str(data.get("number", "")).strip()

        if not msg or not phone:
            print("❌ Messaggio o numero mancanti")
            return jsonify({"error": "message o number mancanti"}), 400

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

        response = requests.post(GHL_REPLY_WEBHOOK, json={
            "phone": phone,
            "message": reply
        })

        if response.status_code != 200:
            print("❌ Errore invio a GHL:", response.status_code, response.text)
            return jsonify({"error": "webhook GHL fallito"}), 500

        return jsonify({"status": "ok", "reply": reply})

    except Exception as e:
        print("❌ Errore interno:", e)
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 3000)))

