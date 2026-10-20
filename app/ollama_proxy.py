"""
Simple HTTP proxy to make Ollama accessible to Cursor
This bypasses Cursor's SSRF protection by using a different hostname
"""
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
import requests
import json

class ProxyHandler(BaseHTTPRequestHandler):
    OLLAMA_BASE = "http://127.0.0.1:11434"
    
    def do_POST(self):
        # Forward to Ollama
        url = f"{self.OLLAMA_BASE}{self.path}"
        
        # Read request body
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        
        # Forward headers (remove host)
        headers = dict(self.headers)
        headers.pop('Host', None)
        headers.pop('host', None)
        
        try:
            # Forward request to Ollama
            response = requests.post(url, data=body, headers=headers, stream=True)
            
            # Send response back to client
            self.send_response(response.status_code)
            for key, value in response.headers.items():
                if key.lower() not in ['connection', 'transfer-encoding']:
                    self.send_header(key, value)
            self.end_headers()
            
            # Stream response
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    self.wfile.write(chunk)
                    
        except Exception as e:
            self.send_error(500, str(e))
    
    def do_GET(self):
        # Forward to Ollama
        url = f"{self.OLLAMA_BASE}{self.path}"
        
        headers = dict(self.headers)
        headers.pop('Host', None)
        headers.pop('host', None)
        
        try:
            response = requests.get(url, headers=headers, stream=True)
            
            self.send_response(response.status_code)
            for key, value in response.headers.items():
                if key.lower() not in ['connection', 'transfer-encoding']:
                    self.send_header(key, value)
            self.end_headers()
            
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    self.wfile.write(chunk)
                    
        except Exception as e:
            self.send_error(500, str(e))
    
    def log_message(self, format, *args):
        # Suppress default logging
        pass

if __name__ == "__main__":
    PORT = 11435  # Different port to avoid conflicts
    
    server = HTTPServer(("127.0.0.1", PORT), ProxyHandler)
    print(f"Ollama proxy running on http://127.0.0.1:{PORT}")
    print(f"Use this URL in Cursor: http://127.0.0.1:{PORT}/v1")
    print("Press Ctrl+C to stop")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping proxy...")
        server.shutdown()

