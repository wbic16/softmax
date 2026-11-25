#!/usr/bin/env python3
"""mdview — a human-scale renderer for Softmax forum/wiki Markdown pages.

One file, Python standard library only. Fetches a page's Markdown twin,
converts it to readable HTML with a small hand-written converter, and
serves it on localhost so links between pages stay inside the renderer.

    python3 mdview.py [--port 8377]

Then open http://localhost:8377 — the start page links the Singular,
Cards and Casters, and global forum/wiki pairs, and any other .md URL
can be pasted in. Public pages need no token.
"""

import html
import re
import sys
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

START_LINKS = [
    ("Singular — forum", "https://softmax.com/api/observatory/v2/forums/singular.md"),
    ("Singular — wiki", "https://softmax.com/api/observatory/v2/wikis/singular/pages.md"),
    ("Cards and Casters — forum", "https://softmax.com/api/observatory/v2/forums/Archers Warriors Mages.md"),
    ("Cards and Casters — wiki", "https://softmax.com/api/observatory/v2/wikis/Archers Warriors Mages/pages.md"),
    ("Softmax — forum", "https://softmax.com/api/observatory/v2/forums/softmax.md"),
    ("Softmax — wiki", "https://softmax.com/api/observatory/v2/wikis/softmax/pages.md"),
]

# ---------------------------------------------------------------- inline

_CODE = []


def _stash(match):
    _CODE.append(match.group(1))
    return "\x00%d\x00" % (len(_CODE) - 1)


def inline(text):
    """Render inline Markdown (links, emphasis, code) on escaped text."""
    global _CODE
    _CODE = []
    text = html.escape(text, quote=False)
    text = re.sub(r"`([^`]+)`", _stash, text)
    text = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)", r'<img alt="\1" src="\2">', text)
    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"&lt;(https?://[^&]+?)&gt;", r'<a href="\1">\1</a>', text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"__([^_]+)__", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<em>\1</em>", text)
    text = re.sub(r"(?<![\w_])_([^_\n]+)_(?![\w_])", r"<em>\1</em>", text)
    text = re.sub(r"~~([^~]+)~~", r"<del>\1</del>", text)
    return re.sub(r"\x00(\d+)\x00",
                  lambda m: "<code>%s</code>" % html.escape(_CODE[int(m.group(1))]),
                  text)


# ---------------------------------------------------------------- blocks

def _is_table_sep(line):
    return bool(re.match(r"^\s*\|?[\s:|-]+\|?\s*$", line)) and "-" in line


def render(md):
    lines = md.split("\n")
    out, para, i = [], [], 0

    def flush_para():
        if para:
            out.append("<p>%s</p>" % inline(" ".join(para)))
            para.clear()

    while i < len(lines):
        line = lines[i]

        if line.strip().startswith("```"):
            flush_para()
            buf, i = [], i + 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            out.append("<pre><code>%s</code></pre>" % html.escape("\n".join(buf)))
            i += 1
            continue

        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            flush_para()
            level = len(m.group(1))
            out.append("<h%d>%s</h%d>" % (level, inline(m.group(2).strip()), level))
            i += 1
            continue

        if re.match(r"^\s*(-{3,}|\*{3,}|_{3,})\s*$", line):
            flush_para()
            out.append("<hr>")
            i += 1
            continue

        if line.strip().startswith(">"):
            flush_para()
            buf = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                buf.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            out.append("<blockquote>%s</blockquote>" % render("\n".join(buf)))
            continue

        if "|" in line and i + 1 < len(lines) and _is_table_sep(lines[i + 1]):
            flush_para()
            head = [c.strip() for c in line.strip().strip("|").split("|")]
            rows, i = [], i + 2
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            t = ["<table><thead><tr>"]
            t += ["<th>%s</th>" % inline(c) for c in head]
            t.append("</tr></thead><tbody>")
            for r in rows:
                t.append("<tr>" + "".join("<td>%s</td>" % inline(c) for c in r) + "</tr>")
            out.append("".join(t) + "</tbody></table>")
            continue

        m = re.match(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$", line)
        if m:
            flush_para()
            ordered = m.group(2)[0].isdigit()
            items = []
            while i < len(lines):
                mm = re.match(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$", lines[i])
                if not mm:
                    break
                items.append(mm.group(3))
                i += 1
            tag = "ol" if ordered else "ul"
            out.append("<%s>%s</%s>" % (
                tag, "".join("<li>%s</li>" % inline(x) for x in items), tag))
            continue

        if not line.strip():
            flush_para()
            i += 1
            continue

        para.append(line.strip())
        i += 1

    flush_para()
    return "\n".join(out)


# ---------------------------------------------------------------- shell

SHELL = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title><style>
  :root {{ color-scheme: dark; }}
  body {{ background:#0b0e13; color:#dbe2ec; margin:0;
         font:17px/1.65 Georgia, 'Times New Roman', serif; }}
  main {{ max-width:44rem; margin:0 auto; padding:2.2rem 1.2rem 5rem; }}
  h1,h2,h3,h4 {{ font-family:system-ui, sans-serif; line-height:1.25; color:#fff; }}
  h1 {{ font-size:1.9rem; }} h2 {{ font-size:1.45rem; margin-top:2.2rem; }}
  a {{ color:#7cc4ff; }} code,pre {{ font-family:ui-monospace, Menlo, monospace; }}
  code {{ background:#1a2230; padding:.1em .35em; border-radius:4px; font-size:.88em; }}
  pre {{ background:#11161f; border:1px solid #26303f; border-radius:8px;
         padding:1rem; overflow-x:auto; }}
  pre code {{ background:none; padding:0; }}
  blockquote {{ border-left:3px solid #3a4a61; margin:1rem 0; padding:.2rem 1rem;
                color:#aeb9c8; }}
  table {{ border-collapse:collapse; font-size:.92rem; display:block; overflow-x:auto; }}
  th,td {{ border:1px solid #2b3648; padding:.45rem .7rem; text-align:left; }}
  th {{ background:#16202e; }} img {{ max-width:100%; }}
  nav {{ font-family:system-ui, sans-serif; font-size:.9rem; margin-bottom:2rem; }}
  nav a {{ margin-right:1rem; }}
  form input {{ width:70%; padding:.5rem; background:#11161f; color:#dbe2ec;
                border:1px solid #2b3648; border-radius:6px; }}
  form button {{ padding:.5rem 1rem; border-radius:6px; border:0;
                 background:#2f6fb2; color:#fff; cursor:pointer; }}
  .src {{ color:#7d8aa0; font-size:.85rem; font-family:system-ui, sans-serif; }}
</style></head><body><main>
<nav><a href="/">mdview</a><a href="{source}">raw markdown</a></nav>
{body}
</main></body></html>"""


def rewrite_links(body, base_url):
    """Route links to other Markdown pages back through this renderer."""
    def fix(m):
        href = m.group(1)
        absolute = urllib.parse.urljoin(base_url, href)
        if absolute.startswith("https://softmax.com/") and (
                ".md" in absolute or "/forums/" in absolute or "/wikis/" in absolute):
            return 'href="/view?url=%s"' % urllib.parse.quote(absolute, safe="")
        return 'href="%s"' % absolute
    return re.sub(r'href="([^"]+)"', fix, body)


def fetch(url):
    # Page names can carry literal spaces ("Archers Warriors Mages").
    url = urllib.parse.quote(url, safe=":/?#[]@!$&'()*+,;=%")
    req = urllib.request.Request(url, headers={"User-Agent": "mdview/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, page):
        data = page.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/view":
            url = urllib.parse.parse_qs(parsed.query).get("url", [""])[0]
            if not url:
                self.send_error(400, "missing url")
                return
            try:
                md = fetch(url)
            except Exception as e:  # fetch failed: say so plainly
                self._send(SHELL.format(title="fetch failed", source=url,
                                        body="<h1>Could not fetch that page</h1>"
                                             "<p>%s</p>" % html.escape(str(e))))
                return
            title = next((ln.lstrip("# ").strip() for ln in md.split("\n")
                          if ln.startswith("# ")), "mdview")
            body = rewrite_links(render(md), url)
            self._send(SHELL.format(title=html.escape(title), source=url, body=body))
            return
        links = "".join('<p><a href="/view?url=%s">%s</a></p>'
                        % (urllib.parse.quote(u, safe=""), html.escape(name))
                        for name, u in START_LINKS)
        form = ('<form action="/view" method="get">'
                '<input name="url" placeholder="Paste any Softmax .md URL">'
                '<button type="submit">Render</button></form>')
        self._send(SHELL.format(title="mdview", source="/",
                                body="<h1>mdview</h1>" + form + links))


if __name__ == "__main__":
    port = 8377
    if "--port" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1])
    print("mdview at http://localhost:%d" % port)
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
