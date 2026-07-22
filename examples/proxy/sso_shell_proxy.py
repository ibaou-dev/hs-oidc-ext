#!/usr/bin/env python3
"""SSO shell for the Hindsight control-plane UI (authentication only).

Renders a thin identity header above the stock control-plane, without forking it.
React 19's streaming SSR strips any node injected into its document, so instead of
injecting we serve — for top-level navigations — a small wrapper page we own: a
non-sticky header (who is signed in) above an <iframe> of the real UI. Everything
else is proxied straight through.

This is authentication/identity only — it does NOT do per-user authorization
(that is the separate RBAC extension's job; see ADR-008). oauth2-proxy in front
forwards the user's access token as X-Forwarded-Access-Token, which we decode only
to show the identity header.

Run:  UPSTREAM=http://127.0.0.1:9998 python3 sso_shell_proxy.py 5155
"""

from __future__ import annotations

import base64
import html
import json
import os
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM = os.environ.get("UPSTREAM", "http://127.0.0.1:9998").rstrip("/")
_HOP = {
    "host",
    "connection",
    "accept-encoding",
    "content-length",
    "keep-alive",
    "transfer-encoding",
    "te",
    "trailer",
    "upgrade",
    "proxy-authorization",
}


def _identity(token: str) -> tuple[str, str]:
    """Best-effort (username, tenant) from the forwarded access token (display only)."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        c = json.loads(base64.urlsafe_b64decode(payload))
        return c.get("preferred_username", "?"), c.get("tenant", "—")
    except Exception:
        return "?", "—"


def _wrapper(user: str, tenant: str, path: str) -> str:
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Hindsight</title>
<style>
 html,body{{margin:0;height:100%;font-family:ui-sans-serif,system-ui,sans-serif}}
 #hs-topbar{{height:44px;box-sizing:border-box;display:flex;align-items:center;gap:14px;
   padding:0 18px;font-size:13px;border-bottom:1px solid #e5e7eb;background:#fff;color:#111827}}
 #hs-cp{{border:0;width:100%;height:calc(100vh - 44px);display:block}}
</style></head>
<body>
 <div id="hs-topbar">
   <span style="color:#0075d6;font-weight:700;letter-spacing:.3px">HINDSIGHT · SSO</span>
   <span>signed in as <b>{html.escape(user)}</b></span>
   <span style="opacity:.6">tenant <code>{html.escape(tenant)}</code></span>
   <span style="margin-left:auto"><a href="/oauth2/sign_out?rd=%2F"
     style="color:#0075d6;text-decoration:none;font-weight:600">Sign out</a></span>
 </div>
 <iframe id="hs-cp" src="{html.escape(path)}"></iframe>
 <script>
  setInterval(function(){{
    try{{
      var r=document.getElementById('hs-cp').contentDocument.documentElement;
      var dark=r.classList.contains('dark')||r.getAttribute('data-theme')==='dark';
      var b=document.getElementById('hs-topbar');
      b.style.background=dark?'#0b1220':'#ffffff'; b.style.color=dark?'#e5e7eb':'#111827';
      b.style.borderBottom='1px solid '+(dark?'#1f2937':'#e5e7eb');
    }}catch(e){{}}
  }},500);
 </script>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _proxy(self) -> None:
        token = self.headers.get("X-Forwarded-Access-Token", "")
        dest = self.headers.get("Sec-Fetch-Dest", "")
        path_only = self.path.split("?")[0]

        # Top-level navigation → our SSO shell (header + iframe of the real UI).
        if (
            token
            and self.command == "GET"
            and dest == "document"
            and not path_only.startswith(("/api", "/_next", "/__hs"))
        ):
            user, tenant = _identity(token)
            body = _wrapper(user, tenant, self.path).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
            return

        # Everything else → straight proxy to the control-plane.
        length = int(self.headers.get("Content-Length") or 0)
        payload = self.rfile.read(length) if length else None
        req = urllib.request.Request(UPSTREAM + self.path, data=payload, method=self.command)
        for k, v in self.headers.items():
            if k.lower() not in _HOP:
                req.add_header(k, v)
        req.add_header("Accept-Encoding", "identity")
        try:
            resp = urllib.request.urlopen(req, timeout=30)  # noqa: S310
            status, hdrs, data = resp.status, resp.headers, resp.read()
        except urllib.error.HTTPError as e:
            status, hdrs, data = e.code, e.headers, e.read()
        except Exception as e:
            self.send_error(502, f"upstream error: {e}")
            return

        self.send_response(status)
        for k, v in hdrs.items():
            if k.lower() in ("content-length", "content-encoding", "transfer-encoding", "connection"):
                continue
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = _proxy

    def log_message(self, *args: object) -> None:
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5155
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
