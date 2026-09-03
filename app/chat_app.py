"""Local web chat interface for the Aspen HYSYS simulation adapters."""

from __future__ import annotations

import argparse
import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from app.chat_service import (
    ChatService,
    ChatServiceError,
    ModelConfig,
    OpenAICompatibleModel,
    load_dotenv,
)


SUI_ROOT = Path(__file__).resolve().parent.parent
STATIC = Path(__file__).resolve().parent / "web"
MAX_BODY_BYTES = 64 * 1024
APP_VERSION = "2026.09.03.4"


class AppHandler(BaseHTTPRequestHandler):
    service: ChatService
    model_config: ModelConfig

    def log_message(self, format: str, *args: Any) -> None:
        print(f"WEB {self.address_string()} {format % args}")

    def _json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/api/health":
            self._json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "model_enabled": self.model_config.enabled,
                    "model": self.model_config.model if self.model_config.enabled else None,
                    "version": APP_VERSION,
                },
            )
            return
        request_path = "/index.html" if self.path == "/" else self.path
        relative = request_path.lstrip("/")
        target = (STATIC / relative).resolve()
        if STATIC.resolve() not in target.parents or not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        body = target.read_bytes()
        content_type, _ = mimetypes.guess_type(target.name)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", (content_type or "application/octet-stream") + ("; charset=utf-8" if target.suffix in {'.html', '.css', '.js'} else ""))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if self.path != "/api/chat":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_BODY_BYTES:
                raise ChatServiceError("请求内容为空或过大。")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ChatServiceError("请求必须是 JSON 对象。")
            response = self.service.handle(
                payload.get("message"),
                payload.get("dry_run", False),
                payload.get("conversation_id"),
            )
            self._json(HTTPStatus.OK, response)
        except (ChatServiceError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
        except Exception as exc:
            self._json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"ok": False, "error": f"服务器内部错误：{type(exc).__name__}: {exc}"},
            )


def build_server(host: str, port: int) -> ThreadingHTTPServer:
    load_dotenv(SUI_ROOT / ".env")
    config = ModelConfig.from_environment()
    model = OpenAICompatibleModel(config) if config.enabled else None
    AppHandler.service = ChatService(model=model)
    AppHandler.model_config = config
    return ThreadingHTTPServer((host, port), AppHandler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the local HYSYS chat UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = build_server(args.host, args.port)
    address = f"http://{args.host}:{server.server_port}"
    print(f"HYSYS AI 对话界面已启动：{address}")
    print("按 Ctrl+C 停止服务。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止。")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
