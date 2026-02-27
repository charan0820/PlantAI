import os
import io
import json
import secrets
import numpy as np
from datetime import datetime
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, Response, stream_with_context
from tensorflow.keras.models import load_model
from tensorflow.keras.applications.mobilenet_v2 import preprocess_input
from PIL import Image
import tensorflow as tf
from groq import Groq
from dotenv import load_dotenv

# Import the enhanced report generator
from report_generator import generate_enhanced_report

load_dotenv()

# Configure Groq
groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# Configuration
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
STATIC_FOLDER = os.path.join(BASE_DIR, 'static', 'images')
MODEL_PATH = os.path.join(BASE_DIR, 'mobilenetv2_best.keras')
CLASS_NAMES_PATH = os.path.join(BASE_DIR, 'class_names.json')
IMG_SIZE = (224, 224)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['STATIC_FOLDER'] = STATIC_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max

# Create directories
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(STATIC_FOLDER, exist_ok=True)

# Load model and class names globally
model = None
class_names = []


# ─── Model Loading ────────────────────────────────────────────────────────────

def load_model_and_classes():
    global model, class_names
    try:
        model = load_model(MODEL_PATH)
        print(f"Model loaded successfully from {MODEL_PATH}")
    except Exception as e:
        print(f"Error loading model: {e}")
        model = None

    try:
        with open(CLASS_NAMES_PATH, 'r') as f:
            class_names = json.load(f)
        print(f"Loaded {len(class_names)} class names")
    except Exception as e:
        print(f"Error loading class names: {e}")
        class_names = [
            "Apple___Apple_scab", "Apple___Black_rot", "Apple___Cedar_apple_rust",
            "Apple___healthy", "Blueberry___healthy",
            "Cherry_(including_sour)___Powdery_mildew", "Cherry_(including_sour)___healthy",
            "Corn_(maize)___Cercospora_leaf_spot Gray_leaf_spot",
            "Corn_(maize)___Common_rust_", "Corn_(maize)___Northern_Leaf_Blight",
            "Corn_(maize)___healthy", "Grape___Black_rot",
            "Grape___Esca_(Black_Measles)", "Grape___Leaf_blight_(Isariopsis_Leaf_Spot)",
            "Grape___healthy", "Orange___Haunglongbing_(Citrus_greening)",
            "Peach___Bacterial_spot", "Peach___healthy",
            "Pepper,_bell___Bacterial_spot", "Pepper,_bell___healthy",
            "Potato___Early_blight", "Potato___Late_blight", "Potato___healthy",
            "Raspberry___healthy", "Soybean___healthy", "Squash___Powdery_mildew",
            "Strawberry___Leaf_scorch", "Strawberry___healthy",
            "Tomato___Bacterial_spot", "Tomato___Early_blight", "Tomato___Late_blight",
            "Tomato___Leaf_Mold", "Tomato___Septoria_leaf_spot",
            "Tomato___Spider_mites Two-spotted_spider_mite",
            "Tomato___Target_Spot", "Tomato___Tomato_Yellow_Leaf_Curl_Virus",
            "Tomato___Tomato_mosaic_virus", "Tomato___healthy"
        ]


# ─── Image Processing ─────────────────────────────────────────────────────────

def preprocess_image(filepath):
    with Image.open(filepath) as img:
        img_rgb = img.convert('RGB')
        img_resized = img_rgb.resize(IMG_SIZE)
        img_array = np.array(img_resized)
    img_array = np.expand_dims(img_array, axis=0)
    img_array = preprocess_input(img_array.astype(np.float32))
    return img_array


def parse_class_name(raw_class):
    parts = raw_class.split('___')
    plant = parts[0].replace('_', ' ').replace(',', '')
    condition = parts[1].replace('_', ' ') if len(parts) > 1 else 'Unknown'
    is_healthy = 'healthy' in condition.lower()
    return plant, condition, is_healthy


def predict_image(filepath):
    if model is None:
        raise ValueError("Model not loaded")
    img_array = preprocess_image(filepath)
    predictions = model.predict(img_array, verbose=0)
    predicted_idx = int(np.argmax(predictions[0]))
    confidence = float(np.max(predictions[0])) * 100
    raw_class = class_names[predicted_idx] if predicted_idx < len(class_names) else "Unknown"
    plant_type, condition, is_healthy = parse_class_name(raw_class)

    if is_healthy:
        recommendations = [
            "Continue regular watering and care",
            "Ensure adequate sunlight and nutrients",
            "Monitor for any changes in appearance",
            "Maintain good air circulation"
        ]
    else:
        recommendations = [
            "Isolate affected plants to prevent spread",
            "Consult with an agricultural expert",
            "Consider appropriate treatment methods",
            "Monitor other plants for similar symptoms"
        ]

    return {
        'raw_class': raw_class,
        'plant_type': plant_type,
        'condition': condition,
        'is_healthy': is_healthy,
        'confidence': round(confidence, 2),
        'recommendations': recommendations
    }


# ─── AI Helper ────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are PlantCare AI Assistant, an expert plant pathologist and agricultural advisor embedded in the PlantCare AI diagnostic platform.

Your role is to help three types of users:
1. Farm operators using automated agricultural monitoring systems who need precise, actionable disease management data.
2. Home gardeners who need friendly, accessible advice on keeping their plants healthy.
3. Agricultural students and technicians learning plant pathology and disease identification.

When discussing a plant classification result, always cover:
- What the disease/condition is (biology, cause, how it spreads)
- Preventive measures (cultural practices, resistant varieties, environmental controls)
- Future damage risks if untreated (yield loss estimates, spread patterns, economic impact for farms)
- Treatment options (organic and conventional)

Keep responses clear, structured, and appropriately detailed. Use markdown formatting for readability.
Always be encouraging and solution-focused rather than alarmist.
If the plant is healthy, provide maintenance tips and early warning signs to watch for."""


def build_plant_context(prediction: dict) -> str:
    return (
        f"Plant: {prediction['plant_type']}\n"
        f"Condition: {prediction['condition']}\n"
        f"Status: {'Healthy' if prediction['is_healthy'] else 'Disease Detected'}\n"
        f"Classification: {prediction['raw_class']}\n"
        f"Model Confidence: {prediction['confidence']}%"
    )


# ─── ROUTES ───────────────────────────────────────────────────────────────────

@app.route('/')
def home():
    return render_template('home.html')


@app.route('/about')
def about():
    return render_template('about.html')


@app.route('/upload')
def upload():
    return render_template('upload.html')


@app.route('/predict', methods=['POST'])
def predict():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if file:
        filename = secrets.token_hex(8) + os.path.splitext(file.filename)[1]
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        try:
            prediction = predict_image(filepath)

            static_filename = f"upload_{secrets.token_hex(8)}.jpg"
            static_path = os.path.join(app.config['STATIC_FOLDER'], static_filename)
            with Image.open(filepath) as img:
                img.convert('RGB').save(static_path)

            session['prediction'] = prediction
            session['image_path'] = f'images/{static_filename}'

            os.remove(filepath)
            return jsonify({'success': True})

        except Exception as e:
            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except Exception:
                    pass
            return jsonify({'error': str(e)}), 500


@app.route('/result')
def result():
    prediction = session.get('prediction')
    image_path = session.get('image_path')
    if not prediction:
        return redirect(url_for('upload'))
    return render_template('result.html', prediction=prediction, image_path=image_path)


# ─── PDF REPORT ───────────────────────────────────────────────────────────────

@app.route('/report')
def report():
    """Generate and download the enhanced PDF diagnosis report."""
    prediction = session.get('prediction')
    image_path = session.get('image_path')
    
    if not prediction:
        return redirect(url_for('upload'))

    # Prepare absolute path for the image (required by ReportLab)
    abs_image_path = None
    if image_path:
        abs_image_path = os.path.join(BASE_DIR, 'static', image_path)

    try:
        # Generate the PDF using the enhanced generator
        pdf_bytes = generate_enhanced_report(
            plant=prediction['plant_type'],
            condition=prediction['condition'],
            confidence=prediction['confidence'],
            image_path=abs_image_path
        )
        
        # Create a clean filename
        plant_fn = prediction['plant_type'].replace(' ', '_')
        cond_fn = prediction['condition'].replace(' ', '_')
        filename = f"PlantCare_Report_{plant_fn}_{cond_fn}.pdf"
        
        return Response(
            pdf_bytes,
            mimetype='application/pdf',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'}
        )

    except ValueError as e:
        # Fallback if the disease is not in report_generator.DISEASE_DATA
        return f"Detailed report currently unavailable for this condition: {prediction['condition']}. Please check back later.", 404
    except Exception as e:
        return f"Error generating report: {str(e)}", 500


# ─── AI CHATBOT ROUTES ────────────────────────────────────────────────────────

@app.route('/learn', methods=['POST'])
def learn():
    prediction = session.get('prediction')
    if not prediction:
        return jsonify({'error': 'No active prediction in session'}), 400

    panel = request.json.get('panel', 'overview')
    plant_context = build_plant_context(prediction)

    panel_prompts = {
        'overview': (
            f"Given this plant diagnosis:\n{plant_context}\n\n"
            "Provide a detailed overview with these sections:\n"
            "1. **What is it?** - Explain the disease/condition, its scientific name if applicable, and biological cause\n"
            "2. **How it spreads** - Transmission vectors, environmental conditions that favour it\n"
            "3. **Visual symptoms** - Detailed description of what to look for beyond what was detected\n"
            "4. **Severity assessment** - How serious is this for the plant and surrounding crops?\n\n"
            "Format using markdown. Be thorough but accessible."
        ),
        'prevention': (
            f"Given this plant diagnosis:\n{plant_context}\n\n"
            "Provide comprehensive prevention guidance with these sections:\n"
            "1. **Immediate actions** - What to do right now\n"
            "2. **Cultural practices** - Watering, spacing, pruning, sanitation\n"
            "3. **Environmental controls** - Humidity, temperature, airflow management\n"
            "4. **Resistant varieties** - Suggest disease-resistant cultivars where applicable\n"
            "5. **Organic treatments** - Natural/biological control methods\n"
            "6. **Chemical treatments** - Fungicides/pesticides (active ingredients, not brand names)\n"
            "7. **Monitoring schedule** - How often to inspect and what to track\n\n"
            "Format using markdown. Include specific, actionable steps."
        ),
        'damage': (
            f"Given this plant diagnosis:\n{plant_context}\n\n"
            "Provide a detailed future damage and risk assessment with these sections:\n"
            "1. **Short-term impact (1-2 weeks)** - What will happen if untreated\n"
            "2. **Medium-term impact (1-3 months)** - Disease progression timeline\n"
            "3. **Long-term consequences** - Permanent damage, plant death risk\n"
            "4. **Spread risk** - Which nearby plants/crops are vulnerable\n"
            "5. **Yield/economic impact** - Estimated losses for commercial growers\n"
            "6. **Environmental factors** - Conditions that accelerate damage\n"
            "7. **Recovery prognosis** - Can the plant fully recover? Under what conditions?\n\n"
            "Format using markdown. Be realistic but solution-focused."
        )
    }

    prompt = panel_prompts.get(panel, panel_prompts['overview'])

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=1500,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ]
        )
        content = response.choices[0].message.content
        return jsonify({'content': content, 'panel': panel})

    except Exception as e:
        return jsonify({'error': f'AI service error: {str(e)}'}), 500


@app.route('/chat', methods=['POST'])
def chat():
    prediction = session.get('prediction')
    if not prediction:
        return jsonify({'error': 'No active prediction in session'}), 400

    data = request.json
    messages = data.get('messages', [])

    if not messages:
        return jsonify({'error': 'No messages provided'}), 400

    plant_context = build_plant_context(prediction)
    system_with_context = (
        f"{SYSTEM_PROMPT}\n\n"
        f"--- CURRENT DIAGNOSIS CONTEXT ---\n{plant_context}\n"
        "--- END CONTEXT ---\n\n"
        "The user is asking follow-up questions about this specific diagnosis. "
        "Always relate answers back to their specific plant and situation."
    )

    groq_messages = [{"role": "system", "content": system_with_context}] + messages

    def generate():
        try:
            stream = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                max_tokens=1024,
                messages=groq_messages,
                stream=True
            )
            for chunk in stream:
                text = chunk.choices[0].delta.content
                if text:
                    escaped = text.replace('\n', '\\n')
                    yield f"data: {escaped}\n\n"

            yield "data: [DONE]\n\n"

        except Exception as e:
            yield f"data: [ERROR] {str(e)}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive'
        }
    )


# Initialize application dependencies
load_model_and_classes()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)