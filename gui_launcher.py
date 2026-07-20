import webview
import threading
import time
from app import app  # Imports your existing Flask app

# Configuration
PORT = 5000
DASHBOARD_URL = f'http://localhost:{PORT}/'

def run_flask():
    """Runs the Flask application in a background thread."""
    app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)

if __name__ == '__main__':
    # 1. Start the Flask web server in a background thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # 2. Wait a moment for the server to initialize
    time.sleep(2)
    
    # 3. Create and launch the native GUI window
    # This window will use WSLg to render directly on your Windows desktop
    webview.create_window('OptiFlow Monitor', DASHBOARD_URL, width=1024, height=768)
    webview.start()