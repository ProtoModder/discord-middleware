#!/usr/bin/env python3
"""
Nyx API Server - Connects middleware to Ollama for actual AI responses
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import aiohttp
import asyncio

PORT = 8767

SYSTEM_PROMPT = """You are Sentinel, a playful security bot on Discord. 
Keep responses SHORT (1-2 sentences), fun, with emojis.
Be helpful but keep it light. You're the guardian of this server."""

class NyxHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/message':
            length = int(self.headers['Content-Length'])
            body = self.rfile.read(length)
            data = json.loads(body)
            
            message = data.get('message', '')
            
            # Get AI response from Ollama
            response = asyncio.run(self.get_ollama_response(message))
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'response': response}).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    async def get_ollama_response(self, prompt: str) -> str:
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "model": "llama3.2:latest",
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt}
                    ],
                    "stream": False
                }
                async with session.post("http://localhost:11434/api/chat", json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get('message', {}).get('content', '🤖')
        except Exception as e:
            print(f"Ollama error: {e}")
        return "🛡️ Sentinel here! Something went wrong."
    
    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'ok', 'service': 'nyx-ollama'}).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        print(f"[NYX-OLLAMA] {format % args}")

print(f"🔮 Starting Nyx Brain (Ollama) on port {PORT}...")
server = HTTPServer(('0.0.0.0', PORT), NyxHandler)
server.serve_forever()
