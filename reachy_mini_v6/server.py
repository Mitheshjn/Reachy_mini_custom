from flask import Flask, render_template, request, jsonify, Response
from reachy_mini_sdk import ReachySDK
import threading
import os
import time
from flask_sock import Sock

app = Flask(__name__)
sock = Sock(app)
sdk = ReachySDK()

@app.route('/')
def index():
    return render_template('index.html', anims=list(sdk.animations.keys()), config=sdk.config, apps=sdk.get_apps(), running_apps=list(sdk.running_apps.keys()))

@sock.route('/web_mic')
def web_mic_socket(ws):
    while True:
        try:
            data = ws.receive()
            if sdk.config.get("mic_source") == "web":
                sdk.audio_rx_queue.put(data)
        except: break

@app.route('/api/state')
def get_state(): 
    state = sdk.pose.copy()
    state['conversation_active'] = (time.time() - sdk.last_interaction_time) < sdk.conversation_timeout
    return jsonify(state)

@app.route('/video_feed')
def video_feed():
    def gen():
        while True: yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + sdk.latest_frame + b'\r\n')
    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/connect', methods=['POST'])
def connect():
    ip = request.json.get('ip', '')
    if not ip: return jsonify({"status": "Error: No IP Provided"})
    
    # Resolves calibration profile synchronously by looking up Hardware ID from robot
    success = sdk.connect_and_identify(ip)
    
    threading.Thread(target=sdk.connect_sockets, daemon=True).start()
    
    status_msg = f"Profile resolved via identification. Opening ports..." if success else f"Default profile applied fallback to legacy IP resolution. Opening ports..."
    return jsonify({
        "status": status_msg, 
        "calibration": sdk.cal
    })

@app.route('/api/calibration', methods=['GET'])
def get_cal():
    return jsonify(sdk.cal)

@app.route('/api/calibration/save', methods=['POST'])
def save_cal():
    sdk.save_calibration(request.json)
    return jsonify({"status": "Calibration Profile Saved"})

@app.route('/api/servo_direct', methods=['POST'])
def servo_direct():
    sdk.direct_servo_move(request.json.get('id'), request.json.get('pos'))
    return jsonify({"status": "ok"})

@app.route('/api/video', methods=['POST'])
def toggle_video():
    sdk.toggle_video(request.json.get('state', False))
    return jsonify({"status": "ok"})

@app.route('/api/toggle_blink', methods=['POST'])
def toggle_blink():
    sdk.toggle_blink(request.json.get('state'))
    return jsonify({"status": "ok"})

@app.route('/api/force_listen', methods=['POST'])
def force_listen():
    sdk.force_listen = True
    sdk.last_interaction_time = time.time()
    return jsonify({"status": "Listening..."})

@app.route('/api/move', methods=['POST'])
def move():
    sdk.move_to(**request.json)
    return jsonify({"status": "ok"})

@app.route('/api/go_home', methods=['POST'])
def go_home():
    sdk.go_home()
    return jsonify({"status": "ok"})

@app.route('/api/chat', methods=['POST'])
def chat():
    reply = sdk.chat_generate(request.json.get('prompt', ''))
    return jsonify({"reply": reply})

@app.route('/api/ai', methods=['POST'])
def toggle_ai():
    data = request.json
    sdk.ai_enabled = data.get('enabled', False)
    if 'mode' in data: sdk.ai_mode = data['mode']
    return jsonify({"status": "ok"})

@app.route('/api/save_config', methods=['POST'])
def save_config():
    sdk.save_config(request.json)
    return jsonify({"status": "Saved"})

@app.route('/api/toggle_app', methods=['POST'])
def toggle_app():
    is_running = sdk.toggle_app(request.json.get('app_name'))
    return jsonify({"running": is_running})

# --- Editor Routes ---
@app.route('/api/get_anim', methods=['POST'])
def get_anim(): 
    name = request.json.get('name')
    steps = sdk.animations.get("built_in", {}).get(name)
    if not steps:
        steps = sdk.animations.get("custom", {}).get(name, [])
    return jsonify({"steps": steps})

@app.route('/api/play_anim', methods=['POST'])
def play_anim():
    sdk.play_animation(request.json.get('name'))
    return jsonify({"status": "Playing"})

@app.route('/api/save_anim_v6', methods=['POST'])
def save_anim_v6():
    data = request.json
    sdk.save_animation(data['name'], data['steps'], data.get('category', 'custom'))
    return jsonify({"status": "Saved"})

@app.route('/api/delete_anim', methods=['POST'])
def delete_anim():
    sdk.delete_animation(request.json.get('name'))
    return jsonify({"status": "Deleted"})

@app.route('/api/rename_anim', methods=['POST'])
def rename_anim():
    sdk.rename_animation(request.json.get('old_name'), request.json.get('new_name'))
    return jsonify({"status": "Renamed"})

@app.route('/api/get_all_anims_categorized', methods=['GET'])
def get_all_anims_categorized():
    built_in = list(sdk.animations.get("built_in", {}).keys())
    custom = list(sdk.animations.get("custom", {}).keys())
    return jsonify({"built_in": built_in, "custom": custom})

if __name__ == '__main__':
    cert_path, key_path = 'ssl.crt', 'ssl.key'
    try:
        if not os.path.exists(cert_path) or not os.path.exists(key_path):
            print("Generating Self-Signed SSL Certificate...")
            from werkzeug.serving import make_ssl_devcert
            make_ssl_devcert('ssl', host='localhost') 
        ssl_args = {'ssl_context': (cert_path, key_path)}
        print("\n✅ SECURE FLASK RUNNING")
    except Exception as e:
        print(f"SSL generation bypassed: {e}")
        ssl_args = {}
    
    app.run(host='0.0.0.0', port=8080, threaded=True, **ssl_args)