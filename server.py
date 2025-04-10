import os
import base64
from datetime import datetime
import google.generativeai as genai
from flask import Flask, request, jsonify, render_template_string, url_for
import operator

with open("templates/index.html","r") as file:
    html_template=file.read()

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'static/uploads'

os.makedirs('static', exist_ok=True)
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

GEMINI_API_KEY = "Your-key-here"
try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash') 
except Exception as e:
    print(f"Error configuring Gemini: {e}")
    model = None # Set model to None if configuration fails

leaderboard_entries = []
MAX_LEADERBOARD_SIZE = 10 

def analyze_image_for_grass(image_path):
    if not model:
        return "Gemini model not available"
    try:
        if not image_path or not os.path.exists(image_path):
            print(f"Image path invalid or file doesn't exist: {image_path}")
            return "No image available for analysis"

        print(f"Analyzing image: {image_path}")
        # Prepare the image for Gemini
        uploaded_file = genai.upload_file(path=image_path)
        print(f"File uploaded successfully: {uploaded_file.name}")

        # Prompt for Gemini
        prompt = """Analyze this image and determine if it contains grass suitable for exercising outdoors.
        Consider lawn grass, park grass, fields, etc. Ignore small patches or indoor artificial grass.
        Respond only with 'Yes' if significant outdoor grass is clearly present,
        'No' if no such grass is present, or
        'Uncertain' if you can't determine or the image is unclear."""

        # content part - ali
        response = model.generate_content([prompt, uploaded_file])

        try:
            genai.delete_file(uploaded_file.name)
            print(f"Deleted uploaded file: {uploaded_file.name}")
        except Exception as delete_err:
            print(f"Warning: Could not delete uploaded file {uploaded_file.name}: {delete_err}")

        if response and response.text:
             analysis_result = response.text.strip()
             print(f"Gemini analysis result: {analysis_result}")
             if analysis_result in ['Yes', 'No', 'Uncertain']:
                 return analysis_result
             else:
                 print(f"Warning: Unexpected response from Gemini: {analysis_result}")
                 return "Uncertain"
        else:
            print("Warning: Received empty or invalid response from Gemini.")
            return "Analysis Failed"

    except Exception as e: #this shouldnt happen?
        print(f"Error analyzing image with Gemini: {str(e)}")
        try:
            if 'uploaded_file' in locals() and uploaded_file:
                genai.delete_file(uploaded_file.name)
                print(f"Deleted uploaded file after error: {uploaded_file.name}")
        except Exception as delete_err:
            print(f"Warning: Could not delete uploaded file {uploaded_file.name} after error: {delete_err}")
        return f"Analysis error"

#this one receives: username:username , arduino_data:num, image_data:the image
@app.route('/receive', methods=['POST'])
def receive():
    global leaderboard_entries
    try:
        data = request.get_json()

        if not data:
            return jsonify({"status": "error", "message": "No data received"}), 400

        arduino_raw_data = data.get('arduino_data', '0') # Default to '0' if not provided
        image_data_b64 = data.get('image_data')
        image_name = data.get('image_name', 'image.jpg') # Default filename
        username = data.get('username')
        print(username)
        print(data)

        try:
            pushup_count = int(arduino_raw_data)
        except ValueError:
            print(f"Warning: Could not parse arduino_data '{arduino_raw_data}' as integer. Using 0.")
            pushup_count = 0

        image_path = None
        image_filename = None
        grass_result = "No Image" 
        bonus_active = False

        if image_data_b64:
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            image_filename = f"{timestamp_str}_{image_name}"
            image_path = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)

            try:
                # Decode and save the image
                with open(image_path, 'wb') as f:
                    f.write(base64.b64decode(image_data_b64))
                print(f"Image saved to: {image_path}")

                grass_result = analyze_image_for_grass(image_path)
                if grass_result == 'Yes':
                    bonus_active = True
            except base64.binascii.Error as b64_err:
                print(f"Error decoding base64 image data: {b64_err}")
                image_path = None #
                image_filename = None
                grass_result = "Image Error"
            except Exception as img_err:
                print(f"Error processing image: {img_err}")
                image_filename = None
                grass_result = "Image Error"
        else:
             print("No image data received in payload.")


        score = pushup_count * 2 if bonus_active else pushup_count

        entry_timestamp = datetime.now()
        new_entry = {
            'id': entry_timestamp.strftime("%Y%m%d%H%M%S%f"), 
            'name': username,
            'raw_count': pushup_count,
            'score': score,
            'bonus': bonus_active,
            'username':username,
            'grass_analysis': grass_result,
            'image_filename': image_filename,
            'timestamp': entry_timestamp.strftime("%Y-%m-%d %H:%M:%S")
        }

        leaderboard_entries.append(new_entry)
        leaderboard_entries.sort(key=operator.itemgetter('score', 'timestamp'), reverse=True)
        leaderboard_entries = leaderboard_entries[:MAX_LEADERBOARD_SIZE]

        print("-" * 20)
        print(f"Received Data: Pushups={pushup_count}, Image Provided={bool(image_data_b64)}")
        print(f"Grass Analysis: {grass_result}, Bonus Active: {bonus_active}")
        print(f"Calculated Score: {score}")
        print(f"Leaderboard Size: {len(leaderboard_entries)}")
        print(f"Top entry score: {leaderboard_entries[0]['score'] if leaderboard_entries else 'N/A'}")
        print("-" * 20)

        return jsonify({
            "status": "success",
            "message": "Data received and processed",
            "entry_details": new_entry 
        }), 200

    except Exception as e:
        print(f"Error in /receive endpoint: {str(e)}")
        import traceback
        traceback.print_exc() 
        return jsonify({"status": "error", "message": str(e)}), 500



@app.route('/', methods=['GET'])
def index():

    return render_template_string(html_template, leaderboard=leaderboard_entries)


if __name__ == '__main__':
    # this shouldnt be overloaded
    app.run(host='0.0.0.0', port=5000, debug=True)
