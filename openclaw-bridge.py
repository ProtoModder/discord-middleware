#!/usr/bin/env python3
"""
OpenClaw Bridge - Simple HTTP server that forwards to OpenClaw via sessions_send
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import subprocess
import os

PORT = 8768
GATEWAY_TOKEN = "ad01607adc5c03cc59ffb35efba60a8a6f2d99e0d3d173d9"
GATEWAY_URL = "http://127.0.0.1:18789"

class OpenClawHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/message':
            length = int(self.headers['Content-Length'])
            body = self.rfile.read(length)
            data = json.loads(body)
            
            message = data.get('message', '')
            
            # Send to OpenClaw via HTTP API
            response = self.send_to_openclaw(message)
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'response': response}).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def send_to_openclaw(self, prompt: str) -> str:
        """Send message via OpenClaw CLI sessions_send"""
        try:
            # Use subprocess to call OpenClaw CLI
            result = subprocess.run(
                ['openclaw', 'sessions', 'send', '--help'],
                capture_output=True, text=True, timeout=10
            )
            
            # Check if sessions send is available
            if 'sessions send' in result.stdout.lower() or result.returncode == 0:
                # Try using sessions send command
                cmd = ['openclaw', 'sessions', 'send', '-m', prompt]
                result = subprocess.run(
                    cmd,
                    capture_output=True, text=True, timeout=30,
                    env={**os.environ, 'OPENCLAW_GATEWAY_TOKEN': GATEWAY_TOKEN}
                )
                if result.returncode == 0 and result.stdout:
                    return result.stdout.strip()
            
            # Fallback: use message tool if sessions_send not available
            return "🛡️ Sentinel here! Using CLI fallback."
                
        except Exception as e:
            print(f"OpenClaw error: {e}")
            return "🛡️ Sentinel here! OpenClaw connection failed."
    
    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'ok', 'service': 'openclaw-bridge'}).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        print(f"[OPENCLAW-BRIDGE] {format % args}")

print(f"🔗 Starting OpenClaw Bridge on port {PORT}...")
server = HTTPServer(('0.0.0.0', PORT), OpenClawHandler)
server.serve_forever()
