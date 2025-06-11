from flask import Flask, request, jsonify
from openai import OpenAI
import httpx, requests, time, os, traceback

app = Flask(__name__)

# Variabili d’ambiente (da impostare su Render)
OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID      = os.getenv("ASSISTANT_ID")
GHL_REPLY_WEBHOOK = os.getenv("GHL_REPLY_WEBHOOK")

# Client OpenAI configurato senza proxy impliciti
custom_http_client = httpx.Client(proxies=None)
client = OpenAI(api_key=OPENAI_API_KEY, http_client=custom_http_client)

# Carica ListaTelefoni.txt all’avvio
with open("ListaTelefoni.txt", "rb") as f:
    tool_file = client.files.create(file=f, purpose="assistants")

@app.route("/ghl-webhook", methods=["POST"])
def handle_ghl():
    try:
        data = request.get_json(force=True)
        print("🔔 JSON ricevuto:", data)

        # Leggi da customData
        custom = data.get("customData", {})
        msg = str(custom.get("message", "")).strip()
        phone = str(custom.get("number", "")).strip()
        contact_id = data.get("contact_id")

        if not msg or not phone:
            print("❌ Messaggio o numero mancanti")
            return jsonify({"error": "message o number mancanti"}), 400

        # Crea un nuovo thread con messaggio utente
        thread = client.beta.threads.create()
        client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=msg
        )

        # Avvia la run con l'assistente e file allegato
        run = client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=ASSISTANT_ID,
            tool_resources={"file_ids": [tool_file.id]}
        )

        # Attendi completamento della run
        for _ in range(30):
            run_status = client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
            if run_status.status == "completed":
                break
            time.sleep(1)

        # Estrai la risposta del bot
        messages = client.beta.threads.messages.list(thread_id=thread.id)
        reply = messages.data[0].content[0].text.value

        # Invia la risposta via webhook GHL
        payload = {"phone": phone, "message": reply}
        if contact_id:
            payload["contact_id"] = contact_id

        resp = requests.post(GHL_REPLY_WEBHOOK, json=payload)
        print("✅ Inviato a GHL:", resp.status_code)

        return jsonify({"status": "ok", "reply": reply})

    except Exception as e:
        print("❌ Errore:", e)
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.getenv("PORT", 3000))
    app.run(host="0.0.0.0", port=port)
