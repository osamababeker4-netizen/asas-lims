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


def check(condition, message):
    if not condition:
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

    check('type="file"' in index_html and "multiple" in index_html, "multi-file input is missing")
    check("files.length>30" not in app_js and "الحد الأقصى 30" not in app_js, "legacy 30-file cap still exists")
    check("for(let index=0;index<files.length;index+=1)" in app_js.replace(" ", ""), "client does not iterate through the full selected batch")
    check("failed.push" in app_js, "client does not collect failed files")
    check("ملفات لم تدخل النظام" in app_js, "final skipped-file report is missing")
    check("/api/attachments/files/" in app_js, "direct-download link is missing")
    check(server.MAX_JSON_BODY_BYTES >= 40 * 1024 * 1024, "JSON body limit is too small for a 25MB base64 upload")

    connection = server.db()
    admin = dict(connection.execute("select * from users where username='admin'").fetchone())
    connection.close()
    token = server.create_session(admin)

    httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.H)
    worker = threading.Thread(target=httpd.serve_forever, daemon=True)
    worker.start()
    port = httpd.server_address[1]

    def request(method, path, payload=None, raw=False):
        client = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
        headers = {"Authorization": "Bearer " + token}
        body = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload).encode("utf-8")
        client.request(method, path, body, headers)
        response = client.getresponse()
        data = response.read()
        result_headers = dict(response.getheaders())
        status = response.status
        client.close()
        if raw:
            return status, data, result_headers
        try:
            parsed = json.loads(data.decode("utf-8"))
        except Exception:
            parsed = {"_raw": data.decode("utf-8", errors="replace")}
        return status, parsed, result_headers

    try:
        bulk_ids = []
        for i in range(40):
            content = ("bulk-" + str(i)).encode("utf-8")
            status, result, _ = request("POST", "/api/smart-import", {
                "section": "reports",
                "file_name": f"Concrete-C39-bulk-{i:02d}.txt",
                "file_base64": base64.b64encode(content).decode("ascii"),
            })
            check(status == 200, f"bulk upload failed at file {i + 1}: {result}")
            check(result.get("total") == 1, f"bulk upload did not import file {i + 1}")
            bulk_ids.append(result["imported"][0]["id"])
        check(len(bulk_ids) == 40, "service did not accept more than 30 files")

        cases = [
            ("Concrete-C39-Cubes.pdf", b"concrete", "خرسانة"),
            ("ASTM-D1557-Proctor.pdf", b"soil", "تربة"),
            ("Marshall-D6927.xlsx", b"asphalt", "أسفلت"),
            ("D7091-Rebar-Cover-NDT.pdf", b"field", "الحقل وNDT"),
            ("general-document.pdf", b"other", "أخرى"),
        ]
        download_id = None
        download_bytes = None
        for name, content, expected in cases:
            status, result, _ = request("POST", "/api/smart-import", {
                "section": "reports",
                "file_name": name,
                "file_base64": base64.b64encode(content).decode("ascii"),
            })
            check(status == 200, f"classification upload failed for {name}: {result}")
            item = result["imported"][0]
            check(item.get("material_group") == expected, f"{name} classified as {item.get('material_group')} instead of {expected}")
            if download_id is None:
                download_id = item["id"]
                download_bytes = content

        archive_buffer = io.BytesIO()
        with zipfile.ZipFile(archive_buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("Concrete-C39-valid.txt", b"ok-concrete")
            archive.writestr("unsupported.exe", b"skip-me")
            archive.writestr("ASTM-D1557-valid.txt", b"ok-soil")
        status, result, _ = request("POST", "/api/smart-import", {
            "section": "reports",
            "file_name": "mixed-acceptance.zip",
            "file_base64": base64.b64encode(archive_buffer.getvalue()).decode("ascii"),
        })
        check(status == 200, f"mixed ZIP upload failed: {result}")
        check(result.get("total") == 2, f"ZIP continuation expected 2 imported files, got {result.get('total')}")
        skipped = result.get("skipped") or []
        check(any(item.get("name") == "unsupported.exe" for item in skipped), "unsupported ZIP member was not reported as skipped")

        status, data, headers = request("GET", f"/api/attachments/files/{download_id}", raw=True)
        check(status == 200, f"direct download failed with HTTP {status}")
        check(data == download_bytes, "direct download bytes do not match uploaded content")
        check("content-disposition" in {k.lower(): v for k, v in headers.items()}, "download response has no Content-Disposition header")

        medium = b"x" * (3 * 1024 * 1024)
        status, result, _ = request("POST", "/api/smart-import", {
            "section": "reports",
            "file_name": "Concrete-C39-3MB.txt",
            "file_base64": base64.b64encode(medium).decode("ascii"),
        })
        check(status == 200, f"3MB upload is still blocked by request-size handling: {result}")
        check(result.get("total") == 1, "3MB file was not stored")

        print(json.dumps({
            "status": "PASS",
            "bulk_files": 40,
            "classification_groups": [item[2] for item in cases],
            "zip_imported": result.get("total", 1),
            "direct_download": "PASS",
            "medium_file_upload": "PASS",
            "json_body_limit_mb": server.MAX_JSON_BODY_BYTES // (1024 * 1024),
        }, ensure_ascii=False, indent=2))
    finally:
        server.SESSIONS.pop(token, None)
        httpd.shutdown()
        httpd.server_close()
        worker.join(timeout=5)
