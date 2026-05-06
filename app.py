import os
from flask import Flask, request, render_template, send_from_directory, jsonify
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Configure Gemini API
API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-image-preview")
PROMPT_TEMPLATE = os.getenv("GEMINI_PROMPT", "Prendi il top del tavolo fotografato in Scenario e cambialo con la finitura Finitura.")

if API_KEY:
    genai.configure(api_key=API_KEY)
else:
    print("WARNING: GEMINI_API_KEY non trovata nelle variabili d'ambiente (.env).")

# Define directories
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCENARI_DIR = os.path.join(BASE_DIR, "Scenari")
FINITURE_DIR = os.path.join(BASE_DIR, "Finiture")
OUTPUT_DIR = os.path.join(BASE_DIR, "OutputAI")

@app.route("/")
def index():
    return "Il Server è in esecuzione! Utilizza il link nel formato: /render?scenario=NomeScenario&finitura=NomeFinitura"

@app.route("/OutputAI/<path:filename>")
def serve_output(filename):
    return send_from_directory(OUTPUT_DIR, filename)

@app.route("/render")
def render_image():
    scenario_name = request.args.get("scenario")
    finitura_name = request.args.get("finitura")

    if not scenario_name or not finitura_name:
        return "Parametri 'scenario' o 'finitura' mancanti nell'URL. Assicurati di usare ?scenario=XYZ&finitura=ABC", 400

    scenario_filename = f"{scenario_name}.jpg" if not scenario_name.lower().endswith(".jpg") else scenario_name
    finitura_filename = f"{finitura_name}.jpg" if not finitura_name.lower().endswith(".jpg") else finitura_name

    scenario_base = os.path.splitext(scenario_filename)[0]
    finitura_base = os.path.splitext(finitura_filename)[0]
    output_filename = f"{scenario_base}__{finitura_base}.jpg"
    output_path = os.path.join(OUTPUT_DIR, output_filename)

    # 1. Controlla se l'immagine esiste già in OutputAI (Cache)
    if os.path.exists(output_path):
        return render_template("index.html", image_url=f"/OutputAI/{output_filename}")

    # 2. Mostra la pagina di caricamento se l'immagine non esiste
    # La pagina JS farà una chiamata in background a /api/generate
    return render_template("loading.html", scenario=scenario_name, finitura=finitura_name)

@app.route("/api/generate")
def api_generate():
    scenario_name = request.args.get("scenario")
    finitura_name = request.args.get("finitura")

    scenario_filename = f"{scenario_name}.jpg" if not scenario_name.lower().endswith(".jpg") else scenario_name
    finitura_filename = f"{finitura_name}.jpg" if not finitura_name.lower().endswith(".jpg") else finitura_name

    scenario_path = os.path.join(SCENARI_DIR, scenario_filename)
    finitura_path = os.path.join(FINITURE_DIR, finitura_filename)
    
    scenario_base = os.path.splitext(scenario_filename)[0]
    finitura_base = os.path.splitext(finitura_filename)[0]
    output_filename = f"{scenario_base}__{finitura_base}.jpg"
    output_path = os.path.join(OUTPUT_DIR, output_filename)

    if not os.path.exists(scenario_path):
        return jsonify({"success": False, "error": f"File scenario non trovato: {scenario_filename}"}), 404
    if not os.path.exists(finitura_path):
        return jsonify({"success": False, "error": f"File finitura non trovato: {finitura_filename}"}), 404

    # 3. Genera l'immagine con Gemini
    try:
        import PIL.Image
        scenario_img = PIL.Image.open(scenario_path)
        finitura_img = PIL.Image.open(finitura_path)

        prompt = PROMPT_TEMPLATE
        model = genai.GenerativeModel(MODEL_NAME)
        response = model.generate_content([prompt, scenario_img, finitura_img])

        saved_image = False
        if response.candidates and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if hasattr(part, 'inline_data') and part.inline_data:
                    import io
                    image_bytes = part.inline_data.data
                    generated_img = PIL.Image.open(io.BytesIO(image_bytes))
                    generated_img.save(output_path)
                    saved_image = True
                    print(f"Immagine generata e salvata con successo da {MODEL_NAME}!")
                    break

        if not saved_image:
            scenario_img.save(output_path)

        return jsonify({"success": True, "filename": output_filename})

    except Exception as e:
        print(f"Errore durante la generazione: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/result")
def result_page():
    filename = request.args.get("filename")
    if not filename:
        return "Filename mancante", 400
    return render_template("index.html", image_url=f"/OutputAI/{filename}")

if __name__ == "__main__":
    app.run(debug=True, port=5000, host="0.0.0.0")
