from flask import Flask, render_template, request, Response, jsonify
import subprocess
import os
import sys

# The base directory where the scraper is located
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

app = Flask(__name__)

# Track the currently executing process
current_process = None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/scrape', methods=['POST'])
def start_scrape():
    global current_process
    
    # Don't start a new scrape if one is already running
    if current_process and current_process.poll() is None:
        return jsonify({'error': 'A scraping process is already running.'}), 400

    data = request.json
    
    # Base command
    cmd = [sys.executable, 'main.py']
    
    # Build arguments based on user input
    if data.get('hashtags'):
        cmd.extend(['--hashtags'] + data['hashtags'].split())
        
    if data.get('usernames'):
        cmd.extend(['--usernames'] + data['usernames'].split())
        
    if data.get('minFollowers'):
        cmd.extend(['--min-followers', str(data['minFollowers'])])
        
    if data.get('maxPerHashtag'):
        cmd.extend(['--max-per-hashtag', str(data['maxPerHashtag'])])
        
    if data.get('mode'):
        cmd.extend(['--mode', data['mode']])
        
    if data.get('outputFile'):
        cmd.extend(['--output', data['outputFile']])
        
    if data.get('resetCheckpoint'):
        cmd.append('--reset-checkpoint')
        
    if data.get('dryRun'):
        cmd.append('--dry-run')

    try:
        # Start the process in the base directory
        current_process = subprocess.Popen(
            cmd,
            cwd=BASE_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, # Combine stdout and stderr
            text=True,
            bufsize=1, # Line buffered
            universal_newlines=True
        )
        return jsonify({'message': 'Scraping started successfully.'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/stream')
def stream_logs():
    def generate():
        global current_process
        if not current_process:
            yield "data: No active process.\n\n"
            return
            
        try:
            for line in iter(current_process.stdout.readline, ''):
                if line:
                    yield f"data: {line.strip()}\n\n"
                    
            current_process.stdout.close()
            current_process.wait()
            yield "data: [PROCESS_COMPLETE]\n\n"
        except Exception as e:
             yield f"data: Error reading logs: {str(e)}\n\n"
    
    return Response(generate(), mimetype='text/event-stream')

@app.route('/api/stop', methods=['POST'])
def stop_scrape():
    global current_process
    if current_process and current_process.poll() is None:
        current_process.terminate()
        current_process = None
        return jsonify({'message': 'Process terminated.'})
    return jsonify({'message': 'No process running.'})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
