from flask import Flask, render_template, request, jsonify, Response, stream_with_context
import os
import time

app = Flask(__name__)

LOG_DIR = "logs"

@app.route('/')
def index():
    log_files = os.listdir(LOG_DIR)
    return render_template('index.html', log_files=log_files)

@app.route('/logs/<filename>')
def show_log(filename):
    with open(os.path.join(LOG_DIR, filename)) as f:
        content = f.read()
    return render_template('log.html', log_content=content, filename=filename)

@app.route('/stream/<filename>')
def stream_log(filename):
    filepath = os.path.join(LOG_DIR, filename)
    def event_stream():
        last_pos = 0
        start_time=time.time()
        while True:
            try:
                with open(filepath, 'r') as f:
                    f.seek(0, 2)
                    size = f.tell()
                    if size > last_pos:
                        f.seek(last_pos)
                        new_content = f.read()
                        last_pos = f.tell()
                        yield f"data: {new_content}\n\n"
                    time.sleep(0.5)
            except Exception as e:
                print(f"Error in SSE stream: {e}")
                break
            if time.time() - start_time > 120:
                break
    return Response(stream_with_context(event_stream()), mimetype="text/event-stream")

@app.route('/delete_log/<filename>', methods=['POST'])
def delete_log(filename):
    try:
        os.remove(os.path.join(LOG_DIR, filename))
        return jsonify({"success": True, "message": f"Log {filename} deleted successfully"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/delete_all_logs', methods=['POST'])
def delete_all_logs():
    try:
        for filename in os.listdir(LOG_DIR):
            os.remove(os.path.join(LOG_DIR, filename))
        return jsonify({"success": True, "message": "All logs deleted successfully"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/static/<path:path>')
def send_static(path):
    return send_from_directory('static', path)

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000)
