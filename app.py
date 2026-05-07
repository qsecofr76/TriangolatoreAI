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

def add_watermark(base_img):
    try:
        from PIL import Image, ImageDraw, ImageFont
        
        logo_path = os.path.join(BASE_DIR, "static", "LogoLaPrimavera.gif")
        if not os.path.exists(logo_path):
            return base_img
            
        # Convertiamo la GIF in RGBA mantenendo la trasparenza (se presente)
        logo = Image.open(logo_path).convert("RGBA")
        
        base_w, base_h = base_img.size
        # Rimpiccioliamo il logo per essere circa il 15% della base (o max 150px)
        target_logo_w = min(150, int(base_w * 0.15))
        w_percent = (target_logo_w / float(logo.size[0]))
        target_logo_h = int((float(logo.size[1]) * float(w_percent)))
        
        # In Pillow >= 10 esiste Image.Resampling.LANCZOS, altrimenti usiamo la fallback
        resampling_filter = getattr(Image, 'Resampling', Image).LANCZOS
        logo = logo.resize((target_logo_w, target_logo_h), resampling_filter)
        
        watermark_layer = Image.new('RGBA', base_img.size, (0,0,0,0))
        
        padding = 20
        # Posizione logo in basso a dx (lasciando 20px extra per il testo)
        pos_x = base_w - target_logo_w - padding
        pos_y = base_h - target_logo_h - padding - 20
        
        # Paste del logo usando lui stesso come maschera per la trasparenza
        watermark_layer.paste(logo, (pos_x, pos_y), logo)
        
        draw = ImageDraw.Draw(watermark_layer)
        text = "AI generated image"
        font = ImageFont.load_default()
        
        # Ottenere le dimensioni del font (compatibilità vecchie e nuove versioni PIL)
        if hasattr(draw, "textbbox"):
            bbox = draw.textbbox((0, 0), text, font=font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
        else:
            text_w, text_h = draw.textsize(text, font=font)
            
        # Creiamo un'immagine temporanea solo per il testo per poterla scalare
        # Aggiungiamo +2 per dare spazio all'effetto ombra
        text_img = Image.new('RGBA', (text_w + 2, text_h + 2), (0,0,0,0))
        text_draw = ImageDraw.Draw(text_img)
        
        # Effetto ombra e testo bianco
        text_draw.text((1, 1), text, fill="black", font=font)
        text_draw.text((0, 0), text, fill="white", font=font)
        
        # Ingrandiamo il testo (es. 1.8x leggermente più grande)
        scale_factor = 1.8
        new_text_w = int(text_img.width * scale_factor)
        new_text_h = int(text_img.height * scale_factor)
        text_img = text_img.resize((new_text_w, new_text_h), resampling_filter)
        
        # Calcoliamo la nuova posizione per il testo ingrandito
        text_x = base_w - new_text_w - padding
        text_y = base_h - new_text_h - padding
        
        # Incolliamo il testo scalato sul livello del watermark
        watermark_layer.paste(text_img, (text_x, text_y), text_img)
        
        # Unione dei livelli
        base_img = base_img.convert("RGBA")
        final_img = Image.alpha_composite(base_img, watermark_layer)
        return final_img.convert("RGB")
    except Exception as e:
        print(f"Errore watermark: {e}")
        return base_img

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
                    generated_img = add_watermark(generated_img)
                    generated_img.save(output_path)
                    saved_image = True
                    print(f"Immagine generata e salvata con successo da {MODEL_NAME}!")
                    break

        if not saved_image:
            scenario_img = add_watermark(scenario_img)
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
