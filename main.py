from flask import Flask, request, jsonify
from openai import OpenAI
import httpx, requests, time, os

app = Flask(__name__)

OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID      = os.getenv("ASSISTANT_ID")
GHL_REPLY_WEBHOOK = os.getenv("GHL_REPLY_WEBHOOK")

custom_http_client = httpx.Client(proxies=None)
client = OpenAI(api_key=OPENAI_API_KEY, http_client=custom_http_client)

with open("ListaTelefoni.txt", "rb") as f:
    tool_file = client.files.create(file=f, purpose="assistants")

@app.route("/ghl-webhook", methods=["POST"])
def handle_ghl():
    # LOG DI DEBUG COMPLETO
    print("📦 RAW request.data:", request.data.decode("utf-8"))
    print("📬 Headers:", dict(request.headers))

    try:
        data = request.get_json(force=True)  # forza il parsing anche se content-type è sbagliato
        print("🔔 JSON decodificato:", data)
    except Exception as e:
        print("❌ Errore nel parsing JSON:", e)
        return jsonify({"error": "Impossibile leggere il JSON"}), 400

    # Continua con la logica solo se il JSON è valido
    msg = str(data.get("message", "")).strip()
    phone = str(data.get("number", "")).strip()
    contact_id = data.get("contact_id")

    if not msg or not phone:
        print("❌ Messaggio o numero mancanti")
        return jsonify({"error": "message o number mancanti"}), 400

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
            time.sleep(1)

        messages = client.beta.threads.messages.list(thread_id=thread.id)
        reply = messages.data[0].content[0].text.value

        payload = {"phone": phone, "message": reply}
        if contact_id:
            payload["contact_id"] = contact_id

        resp = requests.post(GHL_REPLY_WEBHOOK, json=payload)
        print("✅ Risposta inviata a GHL:", resp.status_code, resp.text)

        return jsonify({"status": "ok", "reply": reply})

    except Exception as e:
        print("❌ Errore finale:", e)
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.getenv("PORT", 3000))
    app.run(host="0.0.0.0", port=port)
