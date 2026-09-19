import base64
import http.client
import importlib
import io
import json
import os
import tempfile
import threading
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def ensure(value, message):
    if not value:
        raise AssertionError(message)

with tempfile.TemporaryDirectory() as tmp:
    os.environ["LIMS_DB_PATH"] = str(Path(tmp) / "acceptance.db")
    os.environ["LIMS_BOOTSTRAP_PASSWORD"] = "Acceptance-Only-Password-2026!"
    os.environ["LIMS_BOOTSTRAP_PHONE"] = "+966500000001"

    import server
    server = importlib.reload(server)
    server.RECORD_UPLOADS = str(Path(tmp) / "uploads" / "records")
    server.BACKUP_DIR = str(Path(tmp) / "backups")
    server.init()

    app_js = (ROOT / "app-password.js").read_text(encoding="utf-8")
    index_html = (ROOT / "index.html").read_text(encoding="utf-8")
    server_source = (ROOT / "server.py").read_text(encoding="utf-8")
    render_yaml = (ROOT / "render.yaml").read_text(encoding="utf-8")
    compact_js = "".join(app_js.split())

    ensure("LIMS_RECORD_UPLOADS" in server_source and "LIMS_QUALITY_UPLOADS" in server_source, "server upload paths are not configurable")
    ensure("LIMS_RECORD_UPLOADS" in render_yaml and "/storage/uploads/records" in render_yaml, "record uploads are not configured on persistent Render storage")
    ensure("LIMS_QUALITY_UPLOADS" in render_yaml and "/storage/uploads/quality" in render_yaml, "quality uploads are not configured on persistent Render storage")

    ensure('type="file"' in index_html and "multiple" in index_html, "multi-file selection missing")
    ensure("files.length>30" not in compact_js and "الحدالأقصى30" not in compact_js, "legacy 30-file limit still present")
    ensure("for(letindex=0;index<files.length;index+=1)" in compact_js, "client does not iterate selected files")
    ensure("failed.push" in app_js, "per-file failure collection missing")
    ensure("ملفات تحتاج إعادة محاولة" in app_js, "failed-file retry report missing")
    ensure("data-smart-retry-failed" in app_js, "failed-file retry action missing")
    ensure("upload_id:smartUploadToken(form,file)" in app_js, "idempotent upload token missing")
    ensure("/api/attachments/files/" in app_js, "direct download UI link missing")
    ensure(server.MAX_JSON_BODY_BYTES >= 40 * 1024 * 1024, "request body limit is below 40MB")

    connection = server.db()
    admin = dict(connection.execute("select * from users where username='admin'").fetchone())
    connection.close()
    token = server.create_session(admin)

    httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.H)
    worker = threading.Thread(target=httpd.serve_forever, daemon=True)
    worker.start()
    port = httpd.server_address[1]

    def request(method, path, payload=None, raw=False):
        client = http.client.HTTPConnection("127.0.0.1", port, timeout=45)
        headers = {"Authorization": "Bearer " + token}
        body = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload).encode("utf-8")
        client.request(method, path, body, headers)
        response = client.getresponse()
        body_bytes = response.read()
        response_headers = dict(response.getheaders())
        status = response.status
        client.close()
        if raw:
            return status, body_bytes, response_headers
        try:
            parsed = json.loads(body_bytes.decode("utf-8"))
        except Exception:
            parsed = {"_raw": body_bytes.decode("utf-8", errors="replace")}
        return status, parsed, response_headers

    try:
        bulk_count = 40
        for i in range(bulk_count):
            content = ("bulk-" + str(i)).encode()
            status, result, _ = request("POST", "/api/smart-import", {
                "section": "reports",
                "file_name": f"Concrete-C39-bulk-{i:02d}.txt",
                "file_base64": base64.b64encode(content).decode(),
            })
            ensure(status == 200 and result.get("total") == 1, f"bulk file {i + 1} failed: {result}")

        classification_cases = [
            ("Concrete-C39-Cubes.pdf", b"concrete", "خرسانة"),
            ("ASTM-D1557-Proctor.pdf", b"soil", "تربة"),
            ("Marshall-D6927.xlsx", b"asphalt", "أسفلت"),
            ("D7091-Rebar-Cover-NDT.pdf", b"field", "الحقل وNDT"),
            ("general-document.pdf", b"other", "أخرى"),
        ]
        download_id = None
        download_bytes = None
        for name, content, expected in classification_cases:
            status, result, _ = request("POST", "/api/smart-import", {
                "section": "reports",
                "file_name": name,
                "file_base64": base64.b64encode(content).decode(),
            })
            ensure(status == 200 and result.get("total") == 1, f"classification upload failed for {name}: {result}")
            item = result["imported"][0]
            ensure(item.get("material_group") == expected, f"{name}: expected {expected}, got {item.get('material_group')}")
            if download_id is None:
                download_id = item["id"]
                download_bytes = content

        archive_buffer = io.BytesIO()
        with zipfile.ZipFile(archive_buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("Concrete-C39-valid.txt", b"ok-concrete")
            archive.writestr("unsupported.exe", b"skip-me")
            archive.writestr("ASTM-D1557-valid.txt", b"ok-soil")
        status, zip_result, _ = request("POST", "/api/smart-import", {
            "section": "reports",
            "file_name": "mixed-acceptance.zip",
            "file_base64": base64.b64encode(archive_buffer.getvalue()).decode(),
        })
        ensure(status == 200, f"mixed ZIP request failed: {zip_result}")
        ensure(zip_result.get("total") == 2, f"ZIP should import 2 supported files: {zip_result}")
        ensure(any(item.get("name") == "unsupported.exe" for item in (zip_result.get("skipped") or [])), "skipped ZIP member was not reported")

        status, downloaded, headers = request("GET", f"/api/attachments/files/{download_id}", raw=True)
        ensure(status == 200, f"direct download returned HTTP {status}")
        ensure(downloaded == download_bytes, "downloaded bytes differ from uploaded bytes")
        ensure("content-disposition" in {k.lower(): v for k, v in headers.items()}, "download has no Content-Disposition")

        medium = b"x" * (3 * 1024 * 1024)
        status, medium_result, _ = request("POST", "/api/smart-import", {
            "section": "reports",
            "file_name": "Concrete-C39-3MB.txt",
            "file_base64": base64.b64encode(medium).decode(),
        })
        ensure(status == 200 and medium_result.get("total") == 1, f"3MB upload failed: {medium_result}")

        print(json.dumps({
            "status": "PASS",
            "bulk_files_processed": bulk_count,
            "groups_verified": [case[2] for case in classification_cases],
            "zip_imported": zip_result.get("total"),
            "zip_skipped": len(zip_result.get("skipped") or []),
            "direct_download": "PASS",
            "three_mb_upload": "PASS",
            "json_body_limit_mb": server.MAX_JSON_BODY_BYTES // (1024 * 1024),
        }, ensure_ascii=False, indent=2))
    finally:
        server.SESSIONS.pop(token, None)
        httpd.shutdown()
        httpd.server_close()
        worker.join(timeout=5)
