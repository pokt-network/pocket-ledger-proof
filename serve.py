#!/usr/bin/env python3
"""HTTP server that serves static files and proxies /speculos/* to Speculos API."""

import http.server
import socketserver
import json
import os
import urllib.request
import urllib.error

SPECULOS_URL = "http://127.0.0.1:5005"
PORT = 8080

class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True

class ProxyHandler(http.server.SimpleHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self._cors_headers()
        self.end_headers()

    def do_GET(self):
        if self.path.startswith('/speculos/'):
            self._proxy('GET')
        else:
            super().do_GET()

    def do_POST(self):
        if self.path.startswith('/speculos/'):
            self._proxy('POST')
        else:
            self.send_error(405)

    def do_DELETE(self):
        if self.path.startswith('/speculos/'):
            self._proxy('DELETE')
        else:
            self.send_error(405)

    def _cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def _proxy(self, method):
        target = self.path.replace('/speculos/', '/', 1)
        url = SPECULOS_URL + target
        body = None
        if method == 'POST':
            length = int(self.headers.get('Content-Length', 0))
            if length > 0:
                body = self.rfile.read(length)

        try:
            req = urllib.request.Request(url, data=body, method=method)
            if body:
                req.add_header('Content-Type', 'application/json')
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = resp.read()
                self.send_response(resp.status)
                self._cors_headers()
                self.send_header('Content-Type', resp.headers.get('Content-Type', 'application/json'))
                self.send_header('Content-Length', len(data))
                self.end_headers()
                self.wfile.write(data)
        except urllib.error.HTTPError as e:
            data = e.read()
            self.send_response(e.code)
            self._cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            self.send_response(502)
            self._cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def log_message(self, format, *args):
        if '/speculos/' in str(args[0]):
            super().log_message(format, *args)

if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    server = ThreadingHTTPServer(('127.0.0.1', PORT), ProxyHandler)
    print(f"Serving on http://localhost:{PORT}")
    print(f"Proxying /speculos/* -> {SPECULOS_URL}")
    print(f"Open: http://localhost:{PORT}/index.html?dev=true")
    server.serve_forever()
