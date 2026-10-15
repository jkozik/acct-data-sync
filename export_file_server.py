"""Minimal read-only static file server for the exported CSV/JSON files, so a
remote PowerShell curl script can fetch them by a fixed URL instead of needing
filesystem access to dell1.

Serves only /home/nf/websiteexports (nothing else on the machine). No write
routes, no directory listing -- just GET <path under websiteexports>.

Run with:  .venv/bin/python export_file_server.py
"""
from flask import Flask, send_from_directory, abort

EXPORTS_ROOT = "/home/nf/websiteexports"

app = Flask(__name__)


@app.route("/<path:relpath>")
def serve_export(relpath):
    try:
        return send_from_directory(EXPORTS_ROOT, relpath)
    except FileNotFoundError:
        abort(404)


if __name__ == "__main__":
    print(f"\nServing {EXPORTS_ROOT} read-only on http://0.0.0.0:8080")
    print("Example: curl http://<dell1-LAN-IP>:8080/Chase301Export/Chase1818_Balance_Plaid.json\n")
    app.run(host="0.0.0.0", port=8080)
