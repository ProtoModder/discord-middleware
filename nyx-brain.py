#!/usr/bin/env python3
"""
Nyx API Server - Connects middleware to Ollama with conversation history
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import aiohttp
import asyncio
from collections import defaultdict

PORT = 8767

SYSTEM_PROMPT = """You are Sentinel, the guardian of the Void Node. 
- Professional but relaxed, like a seasoned space marine on duty
- You're watchful, vigilant, and don't trust easily - stowaways and troublemakers trigger your suspicion
- Keep responses concise but helpful
- If you're wrong or uncertain, admit it: "I forgot my communicator... you might be right"
- You're protective of the system you guard"""

# Store conversation history per channel
# Format: {channel_id: [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]}
conversation_history = defaultdict(list)
MAX_HISTORY = 50  # Keep last 50 messages per channel (roughly 32k tokens)

class NyxHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/message':
            length = int(self.headers['Content-Length'])
            body = self.rfile.read(length)
            data = json.loads(body)
            
            message = data.get('message', '')
            channel_id = data.get('channel_id', 'default')
            
            # Get AI response with history
            response = asyncio.run(self.get_ollama_response(message, channel_id))
            
            # Store in history
            conversation_history[channel_id].append({"role": "user", "content": message})
            conversation_history[channel_id].append({"role": "assistant", "content": response})
            
            # Trim history
            if len(conversation_history[channel_id]) > MAX_HISTORY * 2:
                conversation_history[channel_id] = conversation_history[channel_id][-MAX_HISTORY*2:]
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'response': response}).encode())
        elif self.path == '/clear':
            # Clear history for a channel
            length = int(self.headers['Content-Length'])
            body = self.rfile.read(length)
            data = json.loads(body)
            channel_id = data.get('channel_id', 'default')
            conversation_history.pop(channel_id, None)
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'cleared'}).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    async def get_ollama_response(self, prompt: str, channel_id: str) -> str:
        # Build messages with history
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        
        # Add conversation history
        for msg in conversation_history[channel_id]:
            messages.append(msg)
        
        # Add current message
        messages.append({"role": "user", "content": prompt})
        
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "model": "llama3.2:latest",
                    "messages": messages,
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
            self.wfile.write(json.dumps({
                'status': 'ok', 
                'service': 'nyx-ollama',
                'channels': len(conversation_history)
            }).encode())
        elif self.path == '/history':
            # Return history for debugging
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(dict(conversation_history)).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        print(f"[NYX-OLLAMA] {format % args}")

print(f"🔮 Starting Nyx Brain (with history) on port {PORT}...")
server = HTTPServer(('0.0.0.0', PORT), NyxHandler)
server.serve_forever()
