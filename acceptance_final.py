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

    ensure("function openAttachmentInViewer" in app_js, "internal original-file viewer missing")
    ensure("id=\"fieldTestSearch\"" in index_html and "openFieldTestPicker" in app_js, "searchable full field catalog missing")
    ensure("equipment-technical-table" in index_html and "function equipmentTone" in app_js, "technical equipment table missing")
    ensure("QUALITY_ACCESS_ROLES" in app_js and "page === 'quality' || page === 'documentCenter'" in app_js, "quality/document-center UI access guard missing")

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

    def request_as(access_token, method, path, payload=None, raw=False):
        client = http.client.HTTPConnection("127.0.0.1", port, timeout=45)
        headers = {"Authorization": "Bearer " + access_token} if access_token else {}
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

        # Operational health gate.
        status, health, _ = request_as(None, "GET", "/api/health")
        ensure(status == 200 and health.get("database") == "ready", f"health check failed: {health}")

        # Quality/document-control authorization gate: admin succeeds, technical manager is denied.
        denied_token = "acceptance-technical-manager"
        server.SESSIONS[denied_token] = {
            "id": 99991,
            "username": "acceptance-tech",
            "full_name": "Acceptance Technical Manager",
            "role": "technical_manager",
        }
        status, denied_quality, _ = request_as(denied_token, "GET", "/api/quality")
        ensure(status == 403, f"quality access must be denied to technical_manager: {denied_quality}")
        status, created_quality, _ = request("POST", "/api/quality/documents", {
            "category": "procedure",
            "code": "ACC-QMS-001",
            "title": "Final operational acceptance procedure",
        })
        ensure(status == 200, f"quality document creation failed: {created_quality}")
        status, quality, _ = request("GET", "/api/quality")
        ensure(status == 200 and any(row.get("code") == "ACC-QMS-001" for row in quality.get("documents", [])),
               f"quality document persistence failed: {quality}")

        # Field-program gate: use an actual catalog test and persist it in a field visit.
        connection = server.db()
        catalog_test = connection.execute(
            "select id,code,name_ar,standard from test_catalog order by id limit 1"
        ).fetchone()
        ensure(catalog_test is not None, "test catalog is empty")
        equipment_columns = {row["name"] for row in connection.execute("pragma table_info(equipment)").fetchall()}
        calibration_columns = {row["name"] for row in connection.execute("pragma table_info(calibration_records)").fetchall()}
        required_equipment = {
            "equipment_code", "name", "serial_no", "section", "range_text",
            "verification_status", "maintenance_status", "calibrated_to",
            "next_calibration", "certificate_no", "notes"
        }
        ensure(required_equipment.issubset(equipment_columns),
               "equipment technical schema is incomplete: " + str(sorted(required_equipment - equipment_columns)))
        ensure({"equipment_id", "calibration_date", "next_due", "certificate_no", "provider", "result"}.issubset(calibration_columns),
               "calibration record schema is incomplete")
        connection.close()

        status, field_visit, _ = request("POST", "/api/field/visits", {
            "license_no": "ACC-FIELD-001",
            "status": "مسودة",
            "project_name": "Final Acceptance",
            "location": "Operational acceptance",
            "tests": [{
                "catalog_id": catalog_test["id"],
                "name": catalog_test["name_ar"],
                "standard": catalog_test["standard"],
                "result": "قيد الإجراء",
            }],
        })
        ensure(status == 200 and field_visit.get("id"), f"field visit creation failed: {field_visit}")
        connection = server.db()
        saved_visit = connection.execute("select tests_json from field_visits where id=?", (field_visit["id"],)).fetchone()
        connection.close()
        saved_tests = json.loads(saved_visit["tests_json"] or "[]")
        ensure(saved_tests and saved_tests[0].get("catalog_id") == catalog_test["id"],
               "field visit did not persist the selected catalog test")

        print(json.dumps({
            "status": "PASS",
            "bulk_files_processed": bulk_count,
            "groups_verified": [case[2] for case in classification_cases],
            "zip_imported": zip_result.get("total"),
            "zip_skipped": len(zip_result.get("skipped") or []),
            "direct_download": "PASS",
            "three_mb_upload": "PASS",
            "health_check": "PASS",
            "quality_permission_gate": "PASS",
            "quality_persistence": "PASS",
            "field_catalog_visit": "PASS",
            "equipment_calibration_schema": "PASS",
            "json_body_limit_mb": server.MAX_JSON_BODY_BYTES // (1024 * 1024),
        }, ensure_ascii=False, indent=2))
    finally:
        server.SESSIONS.pop(token, None)
        server.SESSIONS.pop("acceptance-technical-manager", None)
        httpd.shutdown()
        httpd.server_close()
        worker.join(timeout=5)
