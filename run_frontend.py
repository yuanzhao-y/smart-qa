"""Start the frontend HTTP server."""

import http.server
import os
import sys
import webbrowser

PORT = 8501


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=os.path.join(os.path.dirname(__file__), "frontend"), **kwargs)

    def log_message(self, format, *args):
        pass  # suppress logs


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    print(f"Frontend running at http://localhost:{port}")
    webbrowser.open(f"http://localhost:{port}")
    with http.server.HTTPServer(("", port), Handler) as httpd:
        httpd.serve_forever()
