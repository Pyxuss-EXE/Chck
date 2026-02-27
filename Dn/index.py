from http.server import BaseHTTPRequestHandler
import json
from datetime import datetime

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        
        response = {
            "status": "running",
            "message": "IVASMS Bot - Use Render or Heroku for full bot functionality",
            "note": "Vercel serverless functions don't support long-running processes. Deploy on Render.com for best results.",
            "powered_by": f"AuroraIInc {datetime.now().year}"
        }
        
        self.wfile.write(json.dumps(response).encode())
        return
    
    def do_POST(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        
        response = {"status": "ok"}
        self.wfile.write(json.dumps(response).encode())
        return
