#!/usr/bin/env python3
"""
Subagent Server - Persistent subagent for Sentinel
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import os

PORT = 8765

# This just responds - the subagent is simulated
class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/chat':
            length = int(self.headers['Content-Length'])
            body = self.rfile.read(length)
            data = json.loads(body)
            prompt = data.get('message', '')
            
            # Cycle through responses
import itertools
responses = [
    "🛡️ The gates are sealed! No sketchy prompts get through on my watch!",
    "👀 I see you trying to pull a fast one! Not today, buddy!",
    "🔒 BEEP BOOP! Security protocols engaged. Nice try!",
    "🦸 Protecting the realm one prompt at a time! What'd you have in mind?",
    "😄 Keep it safe, keep it silly! But mostly safe! What do you need?",
    "🛡️ Sentinel here! The security filters are humming along nicely!",
    "👀 Watching for troublemakers... but you seem okay! What's up?",
    "🔐 The defenses are up! Nothing gets past the guardian!",
]
response_cycle = itertools.cycle(responses)

            response = next(response_cycle)
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'response': response}).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'ok', 'service': 'sentinel-persistent'}).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        print(f"[SENTINEL] {format % args}")

print(f"🛡️ Starting Sentinel (persistent) on port {PORT}...")
server = HTTPServer(('0.0.0.0', PORT), Handler)
server.serve_forever()
