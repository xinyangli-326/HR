"""Loopback-only local pilot. Documents and OCR remain on this computer."""
import argparse
import base64
import hashlib
import hmac
import io
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import sqlite3
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
WORK = ROOT.parent.parent / "work"
sys.path.insert(0, str(WORK / "pydeps"))
import pymupdf as fitz
from PIL import Image, ImageOps
from rules import SLOTS, VERSION, check_materials

DATA = Path(os.environ.get("HR_DATA_DIR", str(WORK / "hr-private")))
DATA.mkdir(parents=True, exist_ok=True)
DB = DATA / "store.sqlite"
POOL = ThreadPoolExecutor(max_workers=1)
OCR = None
OCR_ERROR = None
SESSIONS = {}
SESSION_LOCK = threading.Lock()
LOGIN_FAILURES = {}
MAX_FILE = 15 * 1024 * 1024
MAX_TOTAL = 45 * 1024 * 1024
MAX_BODY = 64 * 1024 * 1024
MAX_PAGES = 60
PORT = 8765


def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def connection():
    con = sqlite3.connect(DB, timeout=30)
    con.row_factory = sqlite3.Row
    return con


def password_hash(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260000).hex()


def init():
    with connection() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS users(
                username TEXT PRIMARY KEY, salt TEXT NOT NULL,
                password TEXT NOT NULL, role TEXT NOT NULL, name TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS applications(
                id TEXT PRIMARY KEY, owner TEXT NOT NULL, data TEXT NOT NULL);
        """)
        for username, password, role, name in [
            ("employee", "Employee2026!", "employee", "员工体验账号"),
            ("hr", "Hr2026!", "hr", "HR 体验账号"),
        ]:
            salt = secrets.token_hex(16)
            db.execute("INSERT OR IGNORE INTO users VALUES (?,?,?,?,?)",
                       (username, salt, password_hash(password, salt), role, name))
        # Interrupted tasks must be explicitly surfaced after a restart.
        for row in db.execute("SELECT id,data FROM applications").fetchall():
            app = json.loads(row["data"])
            if app["status"] in ("queued", "processing"):
                app["status"] = "review"
                app["error"] = "上次审核被服务重启中断，请由 HR 复核或退回后重新提交。"
                db.execute("UPDATE applications SET data=? WHERE id=?", (json.dumps(app, ensure_ascii=False), app["id"]))


def save_app(app):
    with connection() as db:
        db.execute("INSERT OR REPLACE INTO applications VALUES (?,?,?)",
                   (app["id"], app["owner"], json.dumps(app, ensure_ascii=False)))


def load_app(app_id, user):
    with connection() as db:
        row = db.execute("SELECT data FROM applications WHERE id=?", (app_id,)).fetchone()
    if not row:
        raise ApiError(404, "申请不存在。")
    app = json.loads(row["data"])
    if user["role"] != "hr" and app["owner"] != user["username"]:
        raise ApiError(403, "无权访问其他员工的申请。")
    return app


def public_app(app):
    return app


def get_ocr():
    global OCR, OCR_ERROR
    if OCR is None and OCR_ERROR is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            OCR = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=2)
        except Exception as exc:
            OCR_ERROR = type(exc).__name__
    return OCR


def recognize_image(image):
    engine = get_ocr()
    if engine is None:
        return "", False, "unavailable"
    import numpy as np
    result, _ = engine(np.asarray(image.convert("RGB"))[:, :, ::-1])
    lines = result or []
    text = "\n".join(item[1] for item in lines)
    confidence = min((float(item[2]) for item in lines), default=0)
    return text, bool(lines) and confidence >= 0.93, round(confidence, 3)


def process_document(app_id, doc):
    path = DATA / app_id / doc["id"]
    pages = []
    pdf = None
    if doc["kind"] == "pdf":
        pdf = fitz.open(path)
        count = len(pdf)
    else:
        count = 1
    for index in range(count):
        text = ""
        if pdf is not None:
            page = pdf[index]
            text = page.get_text("text", sort=True).strip()
            scale = min(2, 2000 / max(page.rect.width, page.rect.height))
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        else:
            with Image.open(path) as raw:
                image = ImageOps.exif_transpose(raw).convert("RGB")
            image.thumbnail((2200, 2200))
        source = "pdf-text"
        confidence = 1
        reliable = len(text) >= 20
        if len(text) < 20:
            source = "local-ocr"
            text, reliable, confidence = recognize_image(image)
        image.thumbnail((1600, 1600))
        image.save(DATA / app_id / f"{doc['id']}-{index + 1}.png")
        pages.append({
            "number": index + 1, "text": text, "reliable": reliable,
            "source": source, "confidence": confidence,
        })
    if pdf is not None:
        pdf.close()
    return pages


def audit_job(app_id, owner):
    user = {"username": owner, "role": "employee"}
    app = load_app(app_id, user)
    try:
        app["status"] = "processing"
        save_app(app)
        for doc in app["documents"]:
            try:
                doc["pages"] = process_document(app_id, doc)
            except Exception:
                doc["pages"] = []
                doc["error"] = "文件解析失败，请人工检查文件是否损坏。"
            app["progress"] += 1
            save_app(app)
        app["checks"] = check_materials(app["documents"], app["applicant"])
        app["status"] = "returned" if any(c["status"] == "fail" for c in app["checks"]) else "review"
        app["events"].append({
            "time": now(), "actor": "本地预审",
            "text": "自动退回补正" if app["status"] == "returned" else "识别完成，待 HR 复核",
        })
        app["updated"] = now()
        save_app(app)
    except Exception:
        app["status"] = "review"
        app["error"] = "自动处理未完成，已转交人工复核。"
        save_app(app)


class ApiError(Exception):
    def __init__(self, status, message):
        self.status = status
        self.message = message


def validate_file(name, content):
    suffix = Path(name).suffix.lower()
    if not content or len(content) > MAX_FILE:
        raise ApiError(400, "单个文件必须非空且不超过 15 MB。")
    try:
        if suffix == ".pdf" and content.startswith(b"%PDF-"):
            with fitz.open(stream=content, filetype="pdf") as doc:
                if doc.needs_pass or len(doc) == 0 or len(doc) > MAX_PAGES:
                    raise ApiError(400, "PDF 不能加密，且须包含 1–60 页。")
                return "pdf", len(doc)
        if suffix in (".png", ".jpg", ".jpeg"):
            with Image.open(io.BytesIO(content)) as image:
                if image.format not in ("PNG", "JPEG") or image.width * image.height > 40_000_000:
                    raise ApiError(400, "仅支持不超过 4000 万像素的 PNG/JPG 图片。")
                image.verify()
            return "image", 1
    except ApiError:
        raise
    except Exception:
        raise ApiError(400, "无法读取文件，请上传有效的 PDF、JPG 或 PNG。")
    raise ApiError(400, "文件内容与类型不符，仅支持 PDF、JPG、PNG。")


def create_application(payload, user):
    if user["role"] != "employee":
        raise ApiError(403, "只有员工账号可以提交申请。")
    applicant = str(payload.get("applicant", "")).strip()
    if not 2 <= len(applicant) <= 40 or any(c in applicant for c in "<>\n"):
        raise ApiError(400, "请填写 2–40 个字符的申请人姓名。")
    items = payload.get("items", [])
    if not isinstance(items, list) or not 8 <= len(items) <= 40:
        raise ApiError(400, "请选齐所有必需材料后再提交。")
    slots = {item.get("slot") for item in items if isinstance(item, dict)}
    if set(SLOTS) != slots:
        raise ApiError(400, "必需材料不齐全，不能上传。")
    previous = None
    if payload.get("previous"):
        previous = load_app(payload["previous"], user)
        if previous["status"] != "returned":
            raise ApiError(409, "只有已退回的申请可以补正。")
        with connection() as db:
            rows = db.execute("SELECT data FROM applications WHERE owner=?", (user["username"],)).fetchall()
        if any(json.loads(row["data"]).get("previous") == previous["id"] for row in rows):
            raise ApiError(409, "该版本已经重新提交，请查看最新申请。")
    packed = {}
    total = 0
    page_total = 0
    for item in items:
        if "ref" in item:
            if not previous:
                raise ApiError(400, "保留文件缺少原申请。")
            old = next((d for d in previous["documents"] if d["id"] == item["ref"]), None)
            if not old or item["slot"] not in old["slots"]:
                raise ApiError(400, "无效的保留文件。")
            content = (DATA / previous["id"] / old["id"]).read_bytes()
            name = old["name"]
        else:
            name = Path(str(item.get("name", ""))).name[:180]
            try:
                content = base64.b64decode(item.get("data", ""), validate=True)
            except Exception:
                raise ApiError(400, "文件编码无效。")
        digest = hashlib.sha256(content).hexdigest()
        if digest not in packed:
            kind, count = validate_file(name, content)
            total += len(content)
            page_total += count
            if total > MAX_TOTAL or page_total > MAX_PAGES:
                raise ApiError(400, "整套材料不得超过 45 MB 或 60 页。")
            packed[digest] = dict(id=secrets.token_hex(12), name=name, slots=[], kind=kind, size=len(content), content=content, pages=[])
        if item["slot"] not in packed[digest]["slots"]:
            packed[digest]["slots"].append(item["slot"])
    app_id = "HD-" + datetime.now().strftime("%Y%m%d") + "-" + secrets.token_hex(4).upper()
    folder = DATA / app_id
    folder.mkdir()
    docs = []
    for doc in packed.values():
        content = doc.pop("content")
        (folder / doc["id"]).write_bytes(content)
        docs.append(doc)
    app = dict(
        id=app_id, owner=user["username"], applicant=applicant, documents=docs,
        status="queued", progress=0, checks=[], created=now(), updated=now(),
        version=VERSION, previous=payload.get("previous"), events=[
            dict(time=now(), actor=applicant, text="补正材料已重新提交" if previous else "整套材料已提交")
        ],
    )
    save_app(app)
    POOL.submit(audit_job, app_id, user["username"])
    return app


class Handler(BaseHTTPRequestHandler):
    server_version = "LocalReview/1.0"

    def log_message(self, fmt, *args):
        # Do not log document names, extracted text, credentials or request bodies.
        pass

    def headers_common(self, content_type):
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")

    def respond(self, data, status=200, cookie=None):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.headers_common("application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ApiError(400, "请求长度无效。")
        if length <= 0 or length > MAX_BODY:
            raise ApiError(413, "请求过大或内容为空。")
        if not self.headers.get("Content-Type", "").startswith("application/json"):
            raise ApiError(415, "仅接受 JSON 请求。")
        try:
            payload = json.loads(self.rfile.read(length))
        except Exception:
            raise ApiError(400, "请求格式错误。")
        if not isinstance(payload, dict):
            raise ApiError(400, "请求格式错误。")
        return payload

    def user(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
        except Exception:
            raise ApiError(401, "请重新登录。")
        token = cookie["session"].value if "session" in cookie else ""
        with SESSION_LOCK:
            session = SESSIONS.get(token)
        if not session or session["expires"] < time.time():
            raise ApiError(401, "请登录后继续。")
        return session["user"]

    def handle_request(self, post=False):
        allowed_hosts = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
        if self.headers.get("Host") not in allowed_hosts:
            raise ApiError(403, "仅允许本机访问。")
        if post and self.headers.get("Origin") not in {f"http://{host}" for host in allowed_hosts}:
            raise ApiError(403, "请求来源不正确。")
        path = urlparse(self.path).path
        if not post and path in ("/", "/app.js", "/style.css", "/lucide.js"):
            filename = "index.html" if path == "/" else path[1:]
            target = ROOT / "static" / filename
            if not target.is_file():
                raise ApiError(404, "资源不存在。")
            body = target.read_bytes()
            self.send_response(200)
            self.headers_common(mimetypes.guess_type(filename)[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/api/login" and post:
            payload = self.read_json()
            key = self.client_address[0]
            recent = [t for t in LOGIN_FAILURES.get(key, []) if t > time.time() - 300]
            if len(recent) >= 15:
                raise ApiError(429, "登录尝试过多，请 5 分钟后重试。")
            with connection() as db:
                row = db.execute("SELECT * FROM users WHERE username=?", (str(payload.get("username", "")),)).fetchone()
            if not row or not hmac.compare_digest(row["password"], password_hash(str(payload.get("password", "")), row["salt"])):
                LOGIN_FAILURES[key] = recent + [time.time()]
                raise ApiError(401, "账号或密码错误。")
            if payload.get("role") != row["role"]:
                raise ApiError(403, "账号与所选入口不匹配。")
            user = {k: row[k] for k in ("username", "role", "name")}
            token = secrets.token_urlsafe(32)
            with SESSION_LOCK:
                SESSIONS[token] = dict(user=user, expires=time.time() + 8 * 3600)
            return self.respond(user, cookie=f"session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800")
        user = self.user()
        if path == "/api/samples" and not post:
            from samples import fixtures
            return self.respond(fixtures())
        if path == "/api/me" and not post:
            return self.respond(dict(user=user, ocr="unavailable" if OCR_ERROR else "local", version=VERSION))
        if path == "/api/logout" and post:
            cookie = SimpleCookie(self.headers.get("Cookie", ""))
            with SESSION_LOCK:
                SESSIONS.pop(cookie["session"].value, None)
            return self.respond({"ok": True}, cookie="session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0")
        if path == "/api/applications":
            if post:
                return self.respond(public_app(create_application(self.read_json(), user)), 201)
            with connection() as db:
                rows = db.execute("SELECT data FROM applications" + ("" if user["role"] == "hr" else " WHERE owner=?"),
                                  () if user["role"] == "hr" else (user["username"],)).fetchall()
            apps = [json.loads(row["data"]) for row in rows]
            apps.sort(key=lambda a: a["created"], reverse=True)
            return self.respond([{
                k: app[k] for k in ("id", "applicant", "status", "created", "updated", "previous")
            } | {"issues": sum(c["status"] == "fail" for c in app["checks"])} for app in apps])
        match = re.fullmatch(r"/api/applications/(HD-[A-Z0-9-]+)(?:/(decision|appeal|preview)/?([a-f0-9]+)?/?(\d+)?)?", path)
        if match:
            app = load_app(match[1], user)
            action = match[2]
            if not action and not post:
                return self.respond(public_app(app))
            if action == "preview" and not post:
                doc = next((d for d in app["documents"] if d["id"] == match[3]), None)
                page = int(match[4] or "0")
                if not doc or not 1 <= page <= len(doc.get("pages", [])):
                    raise ApiError(404, "预览尚未生成。")
                target = DATA / app["id"] / f"{doc['id']}-{page}.png"
                if not target.is_file():
                    raise ApiError(404, "预览尚未生成。")
                body = target.read_bytes()
                self.send_response(200)
                self.headers_common("image/png")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if action == "appeal" and post:
                if user["role"] != "employee" or app["status"] != "returned":
                    raise ApiError(409, "当前状态不能申请复核。")
                payload = self.read_json()
                reason = str(payload.get("reason", "")).strip()
                if not 3 <= len(reason) <= 2000:
                    raise ApiError(400, "请填写 3–2000 字的复核说明。")
                app["status"] = "review"
                app["events"].append(dict(time=now(), actor=app["applicant"], text="申请人工复核：" + reason))
            elif action == "decision" and post:
                if user["role"] != "hr":
                    raise ApiError(403, "只有 HR 可以复核。")
                if app["status"] in ("queued", "processing"):
                    raise ApiError(409, "自动审核处理中，请稍后复核。")
                if app["status"] not in ("review", "returned"):
                    raise ApiError(409, "当前申请已经结案。")
                with connection() as db:
                    newer = db.execute("SELECT data FROM applications WHERE owner=?", (app["owner"],)).fetchall()
                if any(json.loads(row["data"]).get("previous") == app["id"] for row in newer):
                    raise ApiError(409, "已有补正版本，请审核最新申请。")
                payload = self.read_json()
                status = payload.get("status")
                reason = str(payload.get("reason", "")).strip()
                if status not in ("approved", "returned") or not 3 <= len(reason) <= 2000:
                    raise ApiError(400, "请选择复核结果并填写 3–2000 字的依据。")
                app["status"] = status
                app["decision"] = reason
                app["events"].append(dict(time=now(), actor=user["name"], text=("企业预审通过：" if status == "approved" else "HR 退回补正：") + reason))
            else:
                raise ApiError(404, "接口不存在。")
            app["updated"] = now()
            save_app(app)
            return self.respond(public_app(app))
        raise ApiError(404, "接口不存在。")

    def do_GET(self):
        self.run(False)

    def do_POST(self):
        self.run(True)

    def run(self, post):
        self.connection.settimeout(90)
        try:
            self.handle_request(post)
        except ApiError as exc:
            self.respond({"error": exc.message}, exc.status)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            self.respond({"error": "处理失败，请稍后重试；原申请不会被删除。"}, 500)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    PORT = args.port
    init()
    get_ocr()
    print(f"Local review ready: http://127.0.0.1:{PORT}", flush=True)
    print("Local OCR: " + ("ready" if OCR is not None else "unavailable; manual review fallback"), flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
