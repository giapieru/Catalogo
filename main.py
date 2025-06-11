from flask import Flask, request, jsonify
from openai import OpenAI
import httpx, requests, time, os, traceback

app = Flask(__name__)

# Variabili di ambiente
OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID      = os.getenv("ASSISTANT_ID")
GHL_REPLY_WEBHOOK = os.getenv("GHL_REPLY_WEBHOOK")

# OpenAI client senza proxy impliciti
client = OpenAI(
    api_key=OPENAI_API_KEY,
    http_client=httpx.Client(proxies=None)
)

# Carica file per tool_resources
print("📁 Caricamento ListaTelefoni.txt...")
try:
    with open("ListaTelefoni.txt", "rb") as f:
        tool_file = client.files.create(file=f, purpose="assistants")
    print(f"✅ File caricato correttamente. ID: {tool_file.id}")
except Exception as e:
    print("❌ Errore caricamento ListaTelefoni.txt:", e)
    traceback.print_exc()
    tool_file = None

@app.route("/ghl-webhook", methods=["POST"])
def handle_ghl():
    try:
        # Leggi e logga il JSON
        data = request.get_json(force=True)
        print("🔔 JSON ricevuto dal webhook:", data)

        # Estrai messaggio e numero
        custom = data.get("customData", {})
        msg = str(custom.get("message", "")).strip()
        phone = str(custom.get("number", "")).strip()
        contact_id = data.get("contact_id")
        print(f"🟡 Messaggio: {msg}")
        print(f"🟡 Numero: {phone}")
        print(f"🟡 Contact ID: {contact_id}")

        if not msg or not phone:
            print("❌ Manca messaggio o numero")
            return jsonify({"error": "message o number mancanti"}), 400

        # Crea thread
        print("📤 Creazione thread OpenAI...")
        thread = client.beta.threads.create()
        print(f"✅ Thread creato: {thread.id}")

        # Invia messaggio dell'utente
        client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=msg
        )
        print("✅ Messaggio inviato nel thread.")

        # Avvia run
        print("▶️ Avvio run assistente...")
        run = client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=ASSISTANT_ID,
            tool_resources={"file_ids": [tool_file.id]} if tool_file else {}
        )
        print(f"✅ Run avviata: {run.id}")

        # Attendi completamento
        for i in range(30):
            run_status = client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
            print(f"⌛ Stato run: {run_status.status}")
            if run_status.status == "completed":
                print("✅ Run completata.")
                break
            elif run_status.status == "failed":
                print("❌ Run fallita.")
                return jsonify({"error": "Run fallita"}), 500
            time.sleep(1)

        # Recupera risposta
        messages = client.beta.threads.messages.list(thread_id=thread.id)
        reply = messages.data[0].content[0].text.value
        print(f"💬 Risposta dell'assistente: {reply}")

        # Invia a GHL
        payload = {"phone": phone, "message": reply}
        if contact_id:
            payload["contact_id"] = contact_id

        print(f"📡 Invio a GHL: {GHL_REPLY_WEBHOOK} con payload:", payload)
        resp = requests.post(GHL_REPLY_WEBHOOK, json=payload)
        print(f"📬 Risposta GHL: {resp.status_code} {resp.text}")

        return jsonify({"status": "ok", "reply": reply})

    except Exception as e:
        print("❌ Errore interno:")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.getenv("PORT", 3000))
    print(f"🚀 Server in ascolto su http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port)
