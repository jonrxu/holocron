from __future__ import annotations

import cgi
import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .config import Settings
from .service import HolocronService


def json_bytes(payload: Any) -> bytes:
    return json.dumps(payload).encode("utf-8")


def build_handler(service: HolocronService) -> type[BaseHTTPRequestHandler]:
    class HolocronHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            if path == "/api/health":
                self._write_json({"status": "ok"})
                return
            if path == "/api/papers":
                query = parse_qs(parsed.query)
                text_query = query.get("q", [""])[0]
                try:
                    limit = int(query.get("limit", ["100"])[0])
                except ValueError:
                    limit = 100
                self._write_json(service.query_library(query=text_query, limit=limit))
                return
            if path.startswith("/api/papers/") and path.endswith("/file"):
                self._serve_pdf(path)
                return
            if path.startswith("/api/papers/"):
                self._serve_paper_detail(path)
                return
            if path == "/":
                self._serve_static("index.html", "text/html; charset=utf-8")
                return
            if path == "/app.js":
                self._serve_static("app.js", "application/javascript; charset=utf-8")
                return
            if path == "/styles.css":
                self._serve_static("styles.css", "text/css; charset=utf-8")
                return
            self._write_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            try:
                if path == "/api/papers/upload":
                    self._handle_upload()
                    return
                if path == "/api/papers/from-url":
                    payload = self._read_json()
                    paper = service.ingest_url(str(payload["url"]))
                    self._write_json({"paper": paper}, status=HTTPStatus.ACCEPTED)
                    return
                if path.startswith("/api/papers/") and path.endswith("/notes"):
                    paper_id = self._paper_id_from_path(path, suffix="/notes")
                    payload = self._read_json()
                    paper = service.add_note(
                        paper_id,
                        body=str(payload["body"]),
                        page_number=payload.get("page_number"),
                    )
                    self._write_json({"paper": paper})
                    return
            except KeyError as error:
                self._write_json({"error": str(error)}, status=HTTPStatus.NOT_FOUND)
                return
            except ValueError as error:
                self._write_json({"error": str(error)}, status=HTTPStatus.BAD_REQUEST)
                return
            except Exception as error:
                self._write_json({"error": str(error)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
                return

            self._write_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

        def log_message(self, format: str, *args: Any) -> None:
            del format, args

        def _handle_upload(self) -> None:
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={
                    "REQUEST_METHOD": "POST",
                    "CONTENT_TYPE": self.headers.get("Content-Type", ""),
                },
            )
            if "file" not in form:
                raise ValueError("Missing file field.")
            item = form["file"]
            if not getattr(item, "file", None):
                raise ValueError("Missing uploaded file.")
            payload = item.file.read()
            filename = item.filename or "paper.pdf"
            paper = service.ingest_upload(filename=filename, payload=payload)
            self._write_json({"paper": paper}, status=HTTPStatus.ACCEPTED)

        def _serve_paper_detail(self, path: str) -> None:
            paper_id = self._paper_id_from_path(path)
            self._write_json({"paper": service.get_paper(paper_id)})

        def _serve_pdf(self, path: str) -> None:
            paper_id = self._paper_id_from_path(path, suffix="/file")
            pdf_path, filename = service.open_pdf(paper_id)
            data = pdf_path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Content-Disposition", f'inline; filename="{filename}"')
            self.end_headers()
            self.wfile.write(data)

        def _paper_id_from_path(self, path: str, suffix: str = "") -> int:
            stripped = path.removeprefix("/api/papers/")
            if suffix:
                stripped = stripped.removesuffix(suffix)
            return int(stripped)

        def _read_json(self) -> dict[str, Any]:
            content_length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(content_length)
            if not body:
                return {}
            return json.loads(body)

        def _serve_static(self, filename: str, content_type: str | None = None) -> None:
            package = resources.files("holocron.static")
            asset = package.joinpath(filename)
            data = asset.read_bytes()
            resolved_content_type = content_type or mimetypes.guess_type(filename)[0] or "text/plain"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", resolved_content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _write_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
            data = json_bytes(payload)
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return HolocronHandler


def run_server(settings: Settings) -> None:
    service = HolocronService(settings)
    service.start()
    server = ThreadingHTTPServer((settings.host, settings.port), build_handler(service))
    print(f"Holocron running at http://{settings.host}:{settings.port}")
    print(f"Blob store: {settings.blob_dir}")
    print(f"Database: {settings.database_path}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        service.stop()
