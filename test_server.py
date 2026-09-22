import base64
import importlib
import http.client
import json
import os
import secrets
import sqlite3
import tempfile
import threading
import time
import unittest
import re
from pathlib import Path


class SchemaMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp.name) / 'lims-test.db')
        os.environ['LIMS_DB_PATH'] = self.db_path
        self.bootstrap_password = secrets.token_urlsafe(24)
        os.environ['LIMS_BOOTSTRAP_PASSWORD'] = self.bootstrap_password
        os.environ['LIMS_BOOTSTRAP_PHONE'] = '+966500000001'
        import server
        self.server = importlib.reload(server)

    def tearDown(self):
        self.temp.cleanup()
        os.environ.pop('LIMS_DB_PATH', None)
        os.environ.pop('LIMS_BOOTSTRAP_PASSWORD', None)
        os.environ.pop('LIMS_BOOTSTRAP_PHONE', None)

    def test_init_creates_v720_tables_and_secure_bootstrap_user(self):
        self.server.init()
        connection = self.server.db()
        tables = {row['name'] for row in connection.execute("select name from sqlite_master where type='table'")}
        project_columns = {row['name'] for row in connection.execute('pragma table_info(projects)')}
        admin = connection.execute("select password_hash from users where username='admin'").fetchone()
        connection.close()

        self.assertTrue({'projects', 'work_orders', 'sync_queue', 'field_visits', 'audit_log', 'quality_documents', 'proficiency_tests', 'quality_staff', 'upload_receipts'}.issubset(tables))
        self.assertTrue({'priority', 'description', 'start_date', 'due_date', 'progress', 'reviewed_by', 'approved_by'}.issubset(project_columns))
        self.assertIsNotNone(admin)
        self.assertIn(':', admin['password_hash'])

    def test_smart_files_are_classified_by_engineering_material(self):
        self.assertEqual(self.server.detect_material_group('ASTM-D1557-Proctor.pdf', b''), 'تربة')
        self.assertEqual(self.server.detect_material_group('Marshall-D6927.xlsx', b''), 'أسفلت')
        self.assertEqual(self.server.detect_material_group('Concrete-C39-Cubes.pdf', b''), 'خرسانة')
        self.assertEqual(self.server.detect_material_group('RCDetector-Rebar-Cover-NDT.docx', b''), 'الحقل وNDT')
        self.assertEqual(self.server.detect_material_group('Road-Profiler-IRI-Field-Report.pdf', b''), 'الحقل وNDT')
        self.assertEqual(self.server.detect_material_group('general-document.pdf', b''), 'أخرى')

    def test_professional_document_center_and_login_contract(self):
        html = (Path(__file__).parent / 'index.html').read_text(encoding='utf-8')
        app = (Path(__file__).parent / 'app-password.js').read_text(encoding='utf-8')
        self.assertIn('<h1>تسجيل الدخول</h1>', html)
        self.assertIn('data-page="dashboard">الرئيسية</button>', html)
        self.assertNotIn('id="documentCenterNav"', html)
        self.assertIn('id="qualityFilesEntry"', html)
        self.assertIn('data-inline-smart-import="technicalLibrary"', html)
        self.assertIn('id="documentCenter"', html)
        self.assertIn('QUALITY_ACCESS_ROLES', app)
        self.assertIn("if (page === 'documentCenter') page = 'quality';", app)
        self.assertIn("page === 'quality'", app)
        for group in ('الأسفلت', 'التربة', 'الخرسانة', 'الحقل وNDT'):
            self.assertIn(group, html)
        self.assertIn('technicalLibrary', self.server.SMART_SECTIONS)
        self.assertIn('companyVault', self.server.SMART_SECTIONS)
        self.assertTrue(self.server.smart_section_allowed({'role': 'quality_officer'}, 'technicalLibrary'))
        self.assertFalse(self.server.smart_section_allowed({'role': 'technical_manager'}, 'technicalLibrary'))

    def test_attachment_schema_has_material_group(self):
        self.server.init()
        connection = self.server.db()
        columns = {row['name'] for row in connection.execute('pragma table_info(record_attachments)')}
        connection.close()
        self.assertIn('material_group', columns)

    def test_expanded_catalog_contains_requested_field_and_ndt_tests(self):
        self.server.init()
        connection = self.server.db()
        rows = {row['code']: dict(row) for row in connection.execute("select code,name_en,category,standard from test_catalog")}
        connection.close()
        expected = {'C876', 'C1876', 'EN14630', 'MC1-RC2', 'D7091', 'D6132', 'D5162', 'G57', 'D6431', 'D2412', 'D2290', 'D2584'}
        self.assertTrue(expected.issubset(rows))
        self.assertEqual(rows['EN14630']['standard'], 'EN 14630')
        self.assertEqual(rows['MC1-RC2']['standard'], 'ASTM D2027 / D2028 + Project Specification')
        self.assertEqual(rows['D7091']['category'], 'الحقل وNDT')
        self.assertEqual(rows['D7091']['name_en'], 'Dry Film Thickness on Metals')

    def test_field_program_exposes_classified_guides_and_operating_reference(self):
        html = (Path(__file__).parent / 'index.html').read_text(encoding='utf-8')
        app = (Path(__file__).parent / 'app-password.js').read_text(encoding='utf-8')
        guide = (Path(__file__).parent / 'field-test-guide.html').read_text(encoding='utf-8')
        self.assertIn('id="fieldGuideFilters"', html)
        self.assertNotIn('4 أقسام رئيسية', html)
        self.assertIn('id="openFieldManual"', html)
        self.assertIn('دليل الاختبارات الميدانيه', html)
        self.assertIn('FIELD_MANUAL_REF', app)
        self.assertIn('field-group-card', app)
        for english in ('Concrete', 'Soil', 'Asphalt', 'Field & NDT'):
            self.assertIn("english:'" + english + "'", app)
        self.assertIn("let fieldGuideCategory = 'الكل'", app)
        self.assertIn("data-field-guide-filter=", app)
        for group in ('أسفلت', 'تربة', 'خرسانة', 'الحقل وNDT'):
            self.assertIn(group, app)
            self.assertIn(group, guide)
        for code in ('D4318', 'D1883', 'D6927', 'C597', 'C876', 'D7091', 'D5162', 'G57', 'D2412'):
            self.assertIn("code:'" + code + "'", app)

    def test_field_test_results_have_three_marked_states(self):
        html = (Path(__file__).parent / 'index.html').read_text(encoding='utf-8')
        app = (Path(__file__).parent / 'app-password.js').read_text(encoding='utf-8')
        css = (Path(__file__).parent / 'style.css').read_text(encoding='utf-8')
        for marker in ('✅ ناجح', '❌ راسب', '⏳ قيد الإجراء'):
            self.assertIn(marker, html)
            self.assertIn(marker, app)
        self.assertIn("option value=\"قيد الإجراء\"", app)
        self.assertIn('testResultBadge', app)
        self.assertIn('.test-result-badge.success', css)
        self.assertIn('.test-result-badge.danger', css)
        self.assertIn('.test-result-badge.progress', css)
        self.assertIn("rawResult === 'قيد الإجراء' ? '⏳ قيد الإجراء'", html)

    def test_field_program_uses_full_searchable_catalog_and_internal_result_badges(self):
        html = (Path(__file__).parent / 'index.html').read_text(encoding='utf-8')
        app = (Path(__file__).parent / 'app-password.js').read_text(encoding='utf-8')
        self.assertIn('id="fieldTestSearch"', html)
        self.assertIn('id="fieldTestSearchBtn"', html)
        self.assertIn('id="openCustomFieldTest"', html)
        self.assertNotIn('class="test-result-legend"', html)
        self.assertIn('function fieldCatalogRows()', app)
        self.assertIn('return catalog.filter(function(item)', app)
        self.assertIn('data-field-guide-add', app)
        self.assertIn('testResultBadge(test.result)', app)
        self.assertIn("option value=\"قيد الإجراء\"", app)

    def test_document_center_browses_real_files_without_fake_counts(self):
        html = (Path(__file__).parent / 'index.html').read_text(encoding='utf-8')
        app = (Path(__file__).parent / 'app-password.js').read_text(encoding='utf-8')
        self.assertNotIn('<strong>97</strong>', html)
        self.assertNotIn('<strong>75</strong>', html)
        self.assertNotIn('<strong>53</strong>', html)
        self.assertNotIn('<strong>18</strong>', html)
        self.assertIn('id="documentLibraryFiles"', html)
        self.assertIn('id="documentLibrarySearch"', html)
        self.assertIn('function loadDocumentCenter()', app)
        self.assertIn("/api/smart-imports?section=technicalLibrary", app)
        self.assertIn('data-smart-open', app)
        self.assertIn('data-smart-download', app)

    def test_quality_bottom_sections_match_card_design_and_tables_use_engineering_style(self):
        html = (Path(__file__).parent / 'index.html').read_text(encoding='utf-8')
        app = (Path(__file__).parent / 'app-password.js').read_text(encoding='utf-8')
        css = (Path(__file__).parent / 'style.css').read_text(encoding='utf-8')
        for code in ('QMS-04', 'QMS-05', 'QMS-06'):
            self.assertIn(code, html)
        self.assertIn('quality-table-card', html)
        self.assertIn("table.classList.add('engineering-table')", app)
        self.assertIn('.page table.engineering-table thead th', css)
        self.assertIn('.page table.engineering-table tbody td', css)

    def test_management_cycle_is_real_sequential_workflow(self):
        schema = (Path(__file__).parent / 'schema.sql').read_text(encoding='utf-8')
        server = (Path(__file__).parent / 'server.py').read_text(encoding='utf-8')
        html = (Path(__file__).parent / 'index.html').read_text(encoding='utf-8')
        app = (Path(__file__).parent / 'quality-management.js').read_text(encoding='utf-8')
        css = (Path(__file__).parent / 'style.css').read_text(encoding='utf-8')
        self.assertIn('CREATE TABLE IF NOT EXISTS quality_cycles', schema)
        self.assertIn('CREATE TABLE IF NOT EXISTS quality_cycle_steps', schema)
        self.assertIn("path == '/api/quality/cycles'", server)
        self.assertIn("action == 'create'", server)
        self.assertIn("stage != cycle['current_stage']", server)
        self.assertIn('id="managementStages"', html)
        self.assertIn('id="qualityCycles"', html)
        self.assertIn("complete_stage", app)
        self.assertIn('.management-cycle-board', css)

    def test_management_cycle_api_creates_nine_steps_and_blocks_skipping(self):
        self.server.init()
        connection = self.server.db()
        admin = dict(connection.execute("select * from users where username='admin'").fetchone())
        connection.close()
        token = self.server.create_session(admin)
        httpd = self.server.ThreadingHTTPServer(('127.0.0.1', 0), self.server.H)
        worker = threading.Thread(target=httpd.serve_forever)
        worker.start()
        def post(payload):
            client = http.client.HTTPConnection('127.0.0.1', httpd.server_address[1], timeout=5)
            client.request('POST', '/api/quality/cycles', json.dumps(payload).encode('utf-8'), {
                'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
            response = client.getresponse(); body = json.loads(response.read().decode('utf-8')); client.close()
            return response.status, body
        try:
            status, created = post({'action':'create','title':'مراجعة أداء المختبر','objective':'رفع الالتزام','baseline':55,'target':90})
            self.assertEqual(status, 200)
            connection = self.server.db()
            steps = connection.execute('select stage,status from quality_cycle_steps where cycle_id=? order by stage',(created['id'],)).fetchall()
            connection.close()
            self.assertEqual(len(steps), 9)
            self.assertEqual(steps[0]['status'], 'active')
            status, _ = post({'action':'complete_stage','cycle_id':created['id'],'stage':2,'notes':'محاولة تخطي'})
            self.assertEqual(status, 409)
            status, completed = post({'action':'complete_stage','cycle_id':created['id'],'stage':1,'notes':'تمت مراجعة التقارير','decision':'اعتماد النتائج','details':{'report_refs':'RPT-001,RPT-002','approval':'معتمد'}})
            self.assertEqual(status, 200)
            self.assertEqual(completed['next_stage'], 2)
            connection = self.server.db()
            saved_step = connection.execute('select details_json from quality_cycle_steps where cycle_id=? and stage=1',(created['id'],)).fetchone()
            connection.close()
            saved_details = json.loads(saved_step['details_json'])
            self.assertEqual(saved_details['report_refs'], 'RPT-001,RPT-002')
            self.assertEqual(saved_details['approval'], 'معتمد')
        finally:
            httpd.shutdown(); httpd.server_close(); worker.join(timeout=5)

    def test_every_static_button_has_a_real_interaction_handler(self):
        html = (Path(__file__).parent / 'index.html').read_text(encoding='utf-8')
        scripts = '\n'.join((Path(__file__).parent / name).read_text(encoding='utf-8') for name in (
            'app-password.js','quality-management.js','branch-map.js'))
        delegated = {'page','page-go','open-project','project-view','smart-import','quality-add','quality-template',
            'quality-import','qm-open','qm-inline-save','document-group','file-bulk','branch-query','field-guide-filter','profile-action'}
        missing = []
        for tag in re.findall(r'<button\b[^>]*>', html, flags=re.I):
            attrs = dict(re.findall(r'([\w-]+)="([^"]*)"', tag))
            button_id = attrs.get('id')
            data_keys = {key[5:] for key in re.findall(r'\b(data-[\w-]+)(?:=|\s|>)', tag)}
            bound_id = button_id and ("$('" + button_id + "')" in scripts or
                "getElementById('" + button_id + "')" in scripts or 'getElementById("' + button_id + '")' in scripts)
            implicit = attrs.get('type') == 'submit' or attrs.get('value') in {'cancel','default'}
            if not (bound_id or data_keys.intersection(delegated) or implicit):
                missing.append(button_id or sorted(data_keys) or tag)
        self.assertEqual(missing, [], 'أزرار بلا معالج فعلي: ' + repr(missing))

    def test_full_ui_navigation_and_frontend_backend_contract_integrity(self):
        root = Path(__file__).parent
        html = (root / 'index.html').read_text(encoding='utf-8')
        scripts = '\n'.join((root / name).read_text(encoding='utf-8') for name in (
            'app-password.js', 'quality-management.js', 'branch-map.js', 'i18n.js', 'asas_tests_module.js'))
        server = (root / 'server.py').read_text(encoding='utf-8')

        ids = re.findall(r'\bid="([^"]+)"', html)
        duplicates = sorted({item for item in ids if ids.count(item) > 1})
        self.assertEqual(duplicates, [], 'معرفات HTML مكررة: ' + repr(duplicates))

        page_ids = set(re.findall(r'<section\b[^>]*\bid="([^"]+)"[^>]*\bclass="[^"]*\bpage\b[^"]*"', html, flags=re.I))
        nav_targets = set(re.findall(r'\bdata-page="([^"]+)"', html))
        go_targets = set(re.findall(r'\bdata-page-go="([^"]+)"', html))
        missing_pages = sorted((nav_targets | go_targets) - page_ids)
        self.assertEqual(missing_pages, [], 'روابط تنقل تشير إلى صفحات غير موجودة: ' + repr(missing_pages))

        local_assets = []
        local_assets += re.findall(r'<script\b[^>]*\bsrc="([^"]+)"', html, flags=re.I)
        local_assets += re.findall(r'<link\b[^>]*\bhref="([^"]+)"', html, flags=re.I)
        local_assets += re.findall(r'<img\b[^>]*\bsrc="([^"]+)"', html, flags=re.I)
        missing_assets = []
        for asset in local_assets:
            if asset.startswith(('http://', 'https://', 'data:', '#')):
                continue
            clean = asset.split('?', 1)[0].split('#', 1)[0]
            if clean and not (root / clean).exists():
                missing_assets.append(clean)
        self.assertEqual(sorted(set(missing_assets)), [], 'ملفات واجهة مفقودة: ' + repr(sorted(set(missing_assets))))

        self.assertNotIn('href="#"', html)
        self.assertNotIn('javascript:void(0)', html.lower())

        qm_values = set(re.findall(r'\bdata-qm-open="([^"]+)"', html))
        self.assertTrue(qm_values.issubset({'swot', 'risk', 'kpi', 'action'}), 'قيمة QMS غير مدعومة: ' + repr(qm_values))

        api_literals = set()
        for match in re.findall(r"api\(\s*['\"](/api/[^'\"]+)['\"]", scripts):
            base = match.split('?', 1)[0]
            if '${' not in base:
                api_literals.add(base)
        unresolved_api = sorted(path for path in api_literals if path not in server)
        self.assertEqual(unresolved_api, [], 'استدعاءات واجهة بلا مسار خلفي ظاهر: ' + repr(unresolved_api))

    def test_authorized_user_can_extend_catalog_but_field_user_cannot(self):
        self.server.init()
        connection = self.server.db()
        admin = dict(connection.execute("select * from users where username='admin'").fetchone())
        connection.close()
        admin_token = self.server.create_session(admin)
        denied_token = 'field-catalog-denied'
        self.server.SESSIONS[denied_token] = {'id': 9090, 'username': 'field-only', 'full_name': 'Field Only', 'role': 'field'}
        httpd = self.server.ThreadingHTTPServer(('127.0.0.1', 0), self.server.H)
        worker = threading.Thread(target=httpd.serve_forever)
        worker.start()
        port = httpd.server_address[1]

        def post(token, payload):
            client = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
            client.request('POST', '/api/catalog', json.dumps(payload).encode('utf-8'), {
                'Authorization': 'Bearer ' + token,
                'Content-Type': 'application/json'
            })
            response = client.getresponse()
            data = json.loads(response.read().decode('utf-8'))
            client.close()
            return response.status, data

        payload = {
            'category': 'الحقل وNDT',
            'code': 'WORLD-TEST-001',
            'name_ar': 'اختبار مخصص قابل للتوسعة',
            'name_en': 'Custom Extensible Test',
            'standard': 'Project / International Standard',
            'version': 'Current'
        }
        try:
            status, created = post(admin_token, payload)
            self.assertEqual(status, 200)
            self.assertEqual(created['code'], 'WORLD-TEST-001')
            connection = self.server.db()
            stored = connection.execute("select category,standard from test_catalog where code='WORLD-TEST-001'").fetchone()
            connection.close()
            self.assertEqual(stored['category'], 'الحقل وNDT')
            self.assertEqual(post(denied_token, dict(payload, code='WORLD-TEST-002'))[0], 403)
        finally:
            self.server.SESSIONS.pop(admin_token, None)
            self.server.SESSIONS.pop(denied_token, None)
            httpd.shutdown()
            httpd.server_close()
            worker.join(timeout=5)

    def test_direct_core_record_delete_and_impactful_audit_filter(self):
        self.server.init()
        connection = self.server.db()
        admin = dict(connection.execute("select * from users where username='admin'").fetchone())
        catalog_id = connection.execute('select id from test_catalog order by id limit 1').fetchone()['id']
        connection.execute("insert into clients(name) values('عميل للحذف')")
        client_id = connection.execute('select last_insert_rowid()').fetchone()[0]
        connection.execute("insert into projects(code,name,client_id) values('DEL-PR-1','مشروع باقٍ',?)", (client_id,))
        project_id = connection.execute('select last_insert_rowid()').fetchone()[0]
        connection.execute("insert into samples(sample_no,project_id,material,received_date) values('DEL-S-1',?,'تربة','2026-09-20')", (project_id,))
        sample_id = connection.execute('select last_insert_rowid()').fetchone()[0]
        connection.execute("insert into tests(test_no,sample_id,catalog_id) values('DEL-T-1',?,?)", (sample_id, catalog_id))
        test_id = connection.execute('select last_insert_rowid()').fetchone()[0]
        connection.execute("insert into reports(report_no,test_id) values('DEL-R-1',?)", (test_id,))
        connection.execute("insert into audit_log(user_id,action,entity,entity_id,details) values(?,?,?,?,?)", (admin['id'],'مزامنة تلقائية','system',0,'غير مؤثر'))
        connection.commit(); connection.close()
        token = self.server.create_session(admin)
        httpd = self.server.ThreadingHTTPServer(('127.0.0.1', 0), self.server.H)
        worker = threading.Thread(target=httpd.serve_forever)
        worker.start(); port = httpd.server_address[1]

        def request(method, path, payload=None):
            client = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
            headers = {'Authorization': 'Bearer ' + token}
            body = None
            if payload is not None:
                headers['Content-Type'] = 'application/json'; body = json.dumps(payload).encode('utf-8')
            client.request(method, path, body, headers)
            response = client.getresponse(); data = json.loads(response.read().decode('utf-8')); client.close()
            return response.status, data

        try:
            self.assertEqual(request('POST','/api/records/delete',{'entity':'sample','id':sample_id})[0], 200)
            connection = self.server.db()
            self.assertEqual(connection.execute('select count(*) from samples where id=?',(sample_id,)).fetchone()[0], 0)
            self.assertEqual(connection.execute('select count(*) from tests where id=?',(test_id,)).fetchone()[0], 0)
            self.assertEqual(connection.execute("select count(*) from reports where report_no='DEL-R-1'").fetchone()[0], 0)
            self.assertEqual(connection.execute("select count(*) from trash_items where entity_type='sample' and original_id=?",(sample_id,)).fetchone()[0], 1)
            connection.close()
            status, trash = request('GET','/api/trash')
            self.assertEqual(status, 200); self.assertEqual(trash[0]['label'], 'DEL-S-1')
            status, exported = request('GET','/api/trash/item?id='+str(trash[0]['id']))
            self.assertEqual(status, 200); self.assertEqual(exported['payload']['record']['sample_no'], 'DEL-S-1')
            self.assertEqual(request('POST','/api/trash/restore',{'id':trash[0]['id']})[0], 200)
            connection = self.server.db()
            self.assertEqual(connection.execute('select count(*) from samples where id=?',(sample_id,)).fetchone()[0], 1)
            self.assertEqual(connection.execute('select count(*) from tests where id=?',(test_id,)).fetchone()[0], 1)
            self.assertEqual(connection.execute("select count(*) from reports where report_no='DEL-R-1'").fetchone()[0], 1)
            connection.close()
            self.assertEqual(request('POST','/api/records/delete',{'entity':'project','id':project_id})[0], 200)
            connection = self.server.db()
            self.assertEqual(connection.execute('select count(*) from projects where id=?',(project_id,)).fetchone()[0], 0)
            self.assertEqual(connection.execute('select count(*) from samples where id=?',(sample_id,)).fetchone()[0], 0)
            project_trash_id = connection.execute("select id from trash_items where entity_type='project' and original_id=? order by id desc",(project_id,)).fetchone()[0]
            self.assertEqual(connection.execute("select count(*) from audit_log where action like 'حذف %'").fetchone()[0], 0)
            connection.close()
            self.assertEqual(request('POST','/api/trash/restore',{'id':project_trash_id})[0], 200)
            connection = self.server.db()
            self.assertEqual(connection.execute('select count(*) from projects where id=?',(project_id,)).fetchone()[0], 1)
            self.assertEqual(connection.execute('select count(*) from samples where id=?',(sample_id,)).fetchone()[0], 1)
            connection.close()
            self.assertEqual(request('POST','/api/records/delete',{'entity':'client','id':client_id})[0], 200)
            connection = self.server.db()
            project = connection.execute('select client_id from projects where id=?',(project_id,)).fetchone()
            connection.close()
            self.assertIsNotNone(project); self.assertIsNone(project['client_id'])
            status, dashboard = request('GET','/api/dashboard')
            self.assertEqual(status, 200)
            self.assertTrue(all(item.get('entity') in {'client','project','work_order','sample','test','report','field_visit','equipment','quality_document','user'} for item in dashboard['audit']))
            self.assertNotIn('مزامنة تلقائية', [item.get('action') for item in dashboard['audit']])
            status, reset = request('POST','/api/sync/reset',{})
            self.assertEqual(status, 200); self.assertGreaterEqual(reset['deleted'], 1)
            connection = self.server.db()
            self.assertEqual(connection.execute('select count(*) from sync_queue').fetchone()[0], 0)
            connection.close()
        finally:
            self.server.SESSIONS.pop(token, None)
            httpd.shutdown(); httpd.server_close(); worker.join(timeout=5)

    def test_core_tables_show_plain_delete_buttons(self):
        html = (Path(__file__).parent / 'index.html').read_text(encoding='utf-8')
        app = (Path(__file__).parent / 'app-password.js').read_text(encoding='utf-8')
        self.assertIn("data-record-delete=\"client\"", app)
        self.assertIn("data-record-delete=\"sample\"", app)
        self.assertIn("data-record-delete=\"test\"", app)
        self.assertIn("data-record-delete=\"report\"", app)
        self.assertIn("type=\"button\">حذف</button>", app)
        self.assertIn('<th>البريد</th><th></th>', html)
        self.assertIn('<th>الحالة</th><th></th>', html)
        self.assertIn('id="trashNav"', html)
        self.assertIn('id="trashTable"', html)
        self.assertIn('data-trash-restore', app)
        self.assertIn('data-trash-download', app)
        self.assertIn('data-trash-delete', app)

    def test_safe_upload_picker_and_drag_drop_are_available(self):
        app = (Path(__file__).parent / 'app-password.js').read_text(encoding='utf-8')
        css = (Path(__file__).parent / 'style.css').read_text(encoding='utf-8')
        self.assertIn("window.showOpenFilePicker", app)
        self.assertIn("startIn:'downloads'", app)
        self.assertIn('id="smartDropZone"', app)
        self.assertIn("drop.addEventListener('drop'", app)
        self.assertIn('smartSelectedFiles(form)', app)
        self.assertIn('data-smart-remove-selected', app)
        self.assertIn('.smart-drop-zone', css)

    def test_smart_upload_retry_is_idempotent_and_client_preserves_failures(self):
        app = (Path(__file__).parent / 'app-password.js').read_text(encoding='utf-8')
        self.assertIn('data-smart-retry-failed', app)
        self.assertIn('form.__selectedFiles=failedFiles', app)
        self.assertIn('upload_id:smartUploadToken(form,file)', app)
        self.assertIn('attempt<=3', app)

        self.server.init()
        connection = self.server.db()
        admin = dict(connection.execute("select * from users where username='admin'").fetchone())
        connection.close()
        token = self.server.create_session(admin)
        httpd = self.server.ThreadingHTTPServer(('127.0.0.1', 0), self.server.H)
        worker = threading.Thread(target=httpd.serve_forever)
        worker.start()
        port = httpd.server_address[1]

        payload = {
            'section': 'reports',
            'file_name': 'Concrete-C39-retry.txt',
            'file_base64': base64.b64encode(b'retry-safe').decode('ascii'),
            'upload_id': 'acceptance-retry-token-001',
        }

        def post():
            client = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
            client.request('POST', '/api/smart-import', json.dumps(payload).encode('utf-8'), {
                'Authorization': 'Bearer ' + token,
                'Content-Type': 'application/json'
            })
            response = client.getresponse()
            data = json.loads(response.read().decode('utf-8'))
            client.close()
            return response.status, data

        try:
            first_status, first = post()
            second_status, second = post()
            self.assertEqual(first_status, 200)
            self.assertEqual(second_status, 200)
            self.assertEqual(first['imported'][0]['id'], second['imported'][0]['id'])
            connection = self.server.db()
            count = connection.execute("select count(*) from record_attachments where original_name='Concrete-C39-retry.txt'").fetchone()[0]
            receipts = connection.execute("select count(*) from upload_receipts where upload_id='acceptance-retry-token-001'").fetchone()[0]
            connection.close()
            self.assertEqual(count, 1)
            self.assertEqual(receipts, 1)
        finally:
            self.server.SESSIONS.pop(token, None)
            httpd.shutdown()
            httpd.server_close()
            worker.join(timeout=5)

    def test_add_field_test_button_opens_searchable_catalog_picker(self):
        html = (Path(__file__).parent / 'index.html').read_text(encoding='utf-8')
        app = (Path(__file__).parent / 'app-password.js').read_text(encoding='utf-8')
        self.assertIn('id="addFieldTest"', html)
        self.assertIn("openFieldTestPicker", app)
        self.assertIn("id=\"fieldTestPickerSearch\"", app)
        self.assertIn("id=\"fieldTestPickerCategory\"", app)
        self.assertIn("data-field-picker-add", app)
        self.assertIn("fieldTestPickerRows", app)
        # The four top-level field groups must remain available.
        for group in ('خرسانة', 'تربة', 'أسفلت', 'الحقل وNDT'):
            self.assertIn("key:'" + group + "'", app)

    def test_dashboard_and_login_use_primary_company_logo_without_removed_hero_controls(self):
        html = (Path(__file__).parent / 'index.html').read_text(encoding='utf-8')
        css = (Path(__file__).parent / 'style.css').read_text(encoding='utf-8')
        self.assertNotIn('ASAS OPERATIONS CENTER', html)
        self.assertNotIn('من العينة إلى التقرير — في مسار واحد واضح', html)
        self.assertIn('src="logo.png" class="login-logo"', html)
        self.assertIn('src="asas-home-banner.png" class="dashboard-brand-logo dashboard-home-banner"', html)
        self.assertIn('srcset="asas-home-banner-mobile.png"', html)
        self.assertIn('dashboard-logo-only', html)
        hero_start = html.index('<article class="dashboard-brand-hero dashboard-logo-only">')
        hero_end = html.index('</article>', hero_start)
        hero = html[hero_start:hero_end]
        self.assertNotIn('شريكك الاستراتيجي في كل اختبارات مشروعك', hero)
        self.assertNotIn('dashboard-brand-actions', hero)
        self.assertIn('.dashboard-logo-only .dashboard-brand-logo', css)
        self.assertIn('/* V10.2.7 approved dashboard banner */', css)
        self.assertIn('width:100%!important', css)
        self.assertIn('height:100%!important', css)
        self.assertIn('object-fit:contain!important', css)
        self.assertIn('padding:0!important', css)

    def test_topbar_uses_fixed_identity_profile_menu_and_back_navigation(self):
        html = (Path(__file__).parent / 'index.html').read_text(encoding='utf-8')
        app = (Path(__file__).parent / 'app-password.js').read_text(encoding='utf-8')
        css = (Path(__file__).parent / 'style.css').read_text(encoding='utf-8')
        self.assertNotIn('id="saudiClock"', html)
        self.assertNotIn('id="syncNow"', html)
        self.assertNotIn('id="changePassword"', html)
        self.assertNotIn('id="openProfile"', html)
        self.assertIn('id="profileMenuToggle"', html)
        self.assertIn('id="profileMenu"', html)
        self.assertIn('data-profile-action="avatar"', html)
        self.assertIn('data-profile-action="password"', html)
        self.assertIn('data-profile-action="language"', html)
        self.assertIn('id="pageBack"', html)
        self.assertNotIn('class="profile-chevron"', html)
        self.assertIn('function goBackPage()', app)
        self.assertIn('function toggleProfileMenu()', app)
        self.assertIn("setText($('currentUsername'), currentUser.full_name", app)
        self.assertNotIn("setText($('currentUsername'), '@' +", app)
        self.assertIn('.profile-mini-menu', css)
        self.assertIn('.page-back', css)
        self.assertIn('background:linear-gradient(105deg,#0a4650 0%,#0f6f78 44%,#5e6f73 72%,#df7b2a 100%)!important', css)
        self.assertIn('.topbar .fixed-profile strong{color:#fff!important}', css)

    def test_clean_primary_logo_and_messaging_brand_icons_are_served_and_published(self):
        html = (Path(__file__).parent / 'index.html').read_text(encoding='utf-8')
        server_source = (Path(__file__).parent / 'server.py').read_text(encoding='utf-8')
        sw = (Path(__file__).parent / 'sw.js').read_text(encoding='utf-8')
        pages = (Path(__file__).parent / '.github/workflows/deploy-pages.yml').read_text(encoding='utf-8')
        self.assertIn('src="logo.png" class="login-logo"', html)
        self.assertIn('src="asas-home-banner.png" class="dashboard-brand-logo dashboard-home-banner"', html)
        self.assertIn('srcset="asas-home-banner-mobile.png"', html)
        self.assertIn('src="logo.png" alt="شعار شركة مختبر أساس"', html)
        self.assertIn('src="logo.png" alt="شركة مختبر أساس للاستشارات الفنية والمختبرات الهندسية"', html)
        self.assertIn('id="currentUserAvatar" class="user-avatar" src="logo.png"', html)
        self.assertEqual(html.count('src="asas-home-banner.png"'), 1)
        self.assertGreaterEqual(html.count('src="logo.png"'), 4)
        self.assertNotIn('src="asas-logo-primary.png"', html)
        self.assertIn('src="whatsapp-logo.svg"', html)
        self.assertIn('src="telegram-logo.svg"', html)
        self.assertNotIn('>WA</span>', html)
        self.assertNotIn('>TG</span>', html)
        self.assertIn("'/whatsapp-logo.svg': ('whatsapp-logo.svg', 'image/svg+xml; charset=utf-8')", server_source)
        self.assertIn("'/telegram-logo.svg': ('telegram-logo.svg', 'image/svg+xml; charset=utf-8')", server_source)
        self.assertIn("'./logo.png'", sw)
        self.assertIn("'./asas-home-banner.png'", sw)
        self.assertIn("'./asas-home-banner-mobile.png'", sw)
        self.assertIn("'./engineering-pages-bg.jpg'", sw)
        self.assertIn("'./whatsapp-logo.svg'", sw)
        self.assertIn("'./telegram-logo.svg'", sw)
        self.assertNotIn("'./asas-logo-primary.png'", sw)
        self.assertIn('whatsapp-logo.svg', pages)
        self.assertIn('telegram-logo.svg', pages)
        self.assertIn('asas-home-banner.png', pages)
        self.assertIn('asas-home-banner-mobile.png', pages)
        self.assertIn('engineering-pages-bg.jpg', pages)
        self.server.init()
        httpd = self.server.ThreadingHTTPServer(('127.0.0.1', 0), self.server.H)
        worker = threading.Thread(target=httpd.serve_forever)
        worker.start()
        try:
            for path, signature in (
                ('/logo.png', b'\x89PNG'),
                ('/asas-home-banner.png', b'\x89PNG'),
                ('/asas-home-banner-mobile.png', b'\x89PNG'),
                ('/engineering-pages-bg.jpg', b'\xff\xd8\xff'),
                ('/whatsapp-logo.svg', b'<svg'),
                ('/telegram-logo.svg', b'<svg'),
            ):
                client = http.client.HTTPConnection('127.0.0.1', httpd.server_address[1], timeout=5)
                client.request('GET', path)
                response = client.getresponse()
                body = response.read()
                client.close()
                self.assertEqual(response.status, 200)
                self.assertTrue(body.startswith(signature))
        finally:
            httpd.shutdown(); httpd.server_close(); worker.join(timeout=5)

    def test_original_files_open_in_internal_viewer_and_keep_original_download(self):
        app = (Path(__file__).parent / 'app-password.js').read_text(encoding='utf-8')
        css = (Path(__file__).parent / 'style.css').read_text(encoding='utf-8')
        self.assertIn('function openAttachmentInViewer', app)
        self.assertIn("if(kind==='pdf')", app)
        self.assertIn("kind==='image'", app)
        self.assertIn("kind==='text'", app)
        self.assertIn('الملف محفوظ في النظام بصيغته الأصلية دون تحويل', app)
        self.assertIn('data-viewer-download', app)
        self.assertNotIn('data-viewer-newtab', app)
        self.assertIn("kind==='audio'", app)
        self.assertIn("kind==='video'", app)
        self.assertIn('.attachment-viewer-frame', css)
        self.assertIn('.attachment-original-format', css)
        self.assertIn('data-smart-open', app)
        self.assertNotIn("excel?'تشغيل/تنزيل':'فتح'", app)

    def test_asas_brand_palette_is_consistent(self):
        css = (Path(__file__).parent / 'style.css').read_text(encoding='utf-8')
        self.assertIn('--primary:#0f6f78', css)
        self.assertIn('--primary-deep:#0a4650', css)
        self.assertIn('--orange:#df7b2a', css)
        self.assertIn('background:linear-gradient(180deg,#0a4650 0%,#083941 72%,#0d3036 100%)', css)
        self.assertIn('border-bottom-color:var(--orange)!important', css)

    def test_equipment_table_has_technical_status_design(self):
        html = (Path(__file__).parent / 'index.html').read_text(encoding='utf-8')
        app = (Path(__file__).parent / 'app-password.js').read_text(encoding='utf-8')
        css = (Path(__file__).parent / 'style.css').read_text(encoding='utf-8')
        self.assertIn('equipment-technical-table', html)
        self.assertIn('function equipmentTone', app)
        self.assertIn('equipment-badge', app)
        self.assertIn('.equipment-badge.success', css)
        self.assertIn('.equipment-badge.warning', css)
        self.assertIn('.equipment-badge.danger', css)

    def test_equipment_save_and_correction_contract(self):
        app = (Path(__file__).parent / 'app-password.js').read_text(encoding='utf-8')
        self.assertIn("button.type = button.hasAttribute('data-modal-close') ? 'button' : 'submit';", app)
        self.assertIn('data-save-equipment', app)
        self.assertIn("if (form.id === 'equipmentForm') await submitSimple(form,'/api/equipment');", app)

        self.server.init()
        connection = self.server.db()
        admin = dict(connection.execute("select * from users where username='admin'").fetchone())
        connection.close()
        token = self.server.create_session(admin)
        httpd = self.server.ThreadingHTTPServer(('127.0.0.1', 0), self.server.H)
        worker = threading.Thread(target=httpd.serve_forever)
        worker.start()
        port = httpd.server_address[1]

        def request(method, path, payload=None):
            client = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
            headers = {'Authorization': 'Bearer ' + token}
            body = None
            if payload is not None:
                headers['Content-Type'] = 'application/json'
                body = json.dumps(payload).encode('utf-8')
            client.request(method, path, body, headers)
            response = client.getresponse()
            data = json.loads(response.read().decode('utf-8'))
            client.close()
            return response.status, data

        try:
            status, created = request('POST', '/api/equipment', {
                'name': 'CBR Tester',
                'serial_no': 'N-5211-DX',
                'manufacturer': 'ASAS Test Manufacturer',
                'model': 'Model A',
                'last_calibration': '2026-01-01',
                'next_calibration': '2027-01-01',
                'certificate_no': 'CAL-001',
                'notes': 'initial'
            })
            self.assertEqual(status, 200)
            self.assertTrue(created['ok'])

            status, updated = request('POST', '/api/equipment', {
                'action': 'update',
                'id': created['id'],
                'name': 'CBR Tester Updated',
                'serial_no': 'N-5211-DX',
                'manufacturer': 'ASAS Test Manufacturer',
                'model': 'Model B',
                'last_calibration': '2026-02-01',
                'next_calibration': '2027-02-01',
                'certificate_no': 'CAL-002',
                'notes': 'corrected'
            })
            self.assertEqual(status, 200)
            self.assertTrue(updated['updated'])

            status, dashboard = request('GET', '/api/dashboard')
            self.assertEqual(status, 200)
            saved = next(item for item in dashboard['equipment'] if item['id'] == created['id'])
            self.assertEqual(saved['name'], 'CBR Tester Updated')
            self.assertEqual(saved['model'], 'Model B')
            self.assertEqual(saved['next_calibration'], '2027-02-01')
            self.assertEqual(saved['certificate_no'], 'CAL-002')
            self.assertEqual(saved['notes'], 'corrected')
        finally:
            self.server.SESSIONS.pop(token, None)
            httpd.shutdown()
            httpd.server_close()
            worker.join(timeout=5)

    def test_telegram_draft_uses_one_album_with_text_and_excludes_global_images(self):
        html = (Path(__file__).parent / 'index.html').read_text(encoding='utf-8')
        server_source = (Path(__file__).parent / 'server.py').read_text(encoding='utf-8')
        self.assertIn("telegram_send_media_group(photos, text)", server_source)
        self.assertNotIn("telegram_send_media_group(photos, 'صور الزيارة الميدانية')", server_source)
        self.assertIn("target.id !== 'fieldCameraInput' && target.id !== 'fieldGalleryInput'", html)
        self.assertIn("document.querySelectorAll('#fieldPhotoPreview img')", html)
        self.assertNotIn("<h3>صور الزيارة الميدانية</h3>", html)

        self.server.init()
        connection = self.server.db()
        admin = dict(connection.execute("select * from users where username='admin'").fetchone())
        connection.close()
        token = self.server.create_session(admin)
        calls = []
        original_group = self.server.telegram_send_media_group
        original_text = self.server.telegram_send_text
        self.server.telegram_send_media_group = lambda photos, caption='': calls.append(('album', list(photos), caption)) or [{'message_id': 701}, {'message_id': 702}]
        self.server.telegram_send_text = lambda text: calls.append(('text', text)) or {'message_id': 703}
        httpd = self.server.ThreadingHTTPServer(('127.0.0.1', 0), self.server.H)
        worker = threading.Thread(target=httpd.serve_forever)
        worker.start()
        try:
            client = http.client.HTTPConnection('127.0.0.1', httpd.server_address[1], timeout=5)
            payload = {
                'text': '👤 المرسل الميداني: اسم من الواجهة\nبيانات الزيارة والاختبارات',
                'photos': ['data:image/png;base64,AAAA', 'data:image/png;base64,BBBB']
            }
            client.request('POST', '/api/telegram/draft', json.dumps(payload).encode('utf-8'), {
                'Authorization': 'Bearer ' + token,
                'Content-Type': 'application/json'
            })
            response = client.getresponse()
            result = json.loads(response.read().decode('utf-8'))
            client.close()
            self.assertEqual(response.status, 200)
            self.assertEqual(result['layout'], 'album_then_text')
            self.assertEqual(result['photos_sent'], 2)
            self.assertEqual([item[0] for item in calls], ['album'])
            self.assertEqual(len(calls[0][1]), 2)
            self.assertTrue(calls[0][2].startswith(admin['full_name'] + '\n'))
            self.assertNotIn('صور الزيارة الميدانية', calls[0][2])
        finally:
            self.server.telegram_send_media_group = original_group
            self.server.telegram_send_text = original_text
            self.server.SESSIONS.pop(token, None)
            httpd.shutdown()
            httpd.server_close()
            worker.join(timeout=5)

    def test_pwa_assets_are_served_by_the_central_service(self):
        self.server.init()
        httpd = self.server.ThreadingHTTPServer(('127.0.0.1', 0), self.server.H)
        worker = threading.Thread(target=httpd.serve_forever)
        worker.start()
        try:
            for path, marker in (('/sw.js', 'CACHE_NAME'), ('/manifest.webmanifest', 'أساس LIMS'), ('/runtime-config.js', 'LIMS_API_BASE_URL'), ('/field-test-guide.html', 'ASTM D5162')):
                client = http.client.HTTPConnection('127.0.0.1', httpd.server_address[1], timeout=5)
                client.request('GET', path)
                response = client.getresponse()
                body = response.read().decode('utf-8')
                client.close()
                self.assertEqual(response.status, 200)
                self.assertIn(marker, body)
        finally:
            httpd.shutdown()
            httpd.server_close()
            worker.join(timeout=5)

    def test_health_endpoint_checks_database_without_authentication(self):
        self.server.init()
        httpd = self.server.ThreadingHTTPServer(('127.0.0.1', 0), self.server.H)
        worker = threading.Thread(target=httpd.serve_forever)
        worker.start()
        try:
            client = http.client.HTTPConnection('127.0.0.1', httpd.server_address[1], timeout=5)
            client.request('GET', '/api/health')
            response = client.getresponse()
            result = json.loads(response.read().decode('utf-8'))
            client.close()
            self.assertEqual(response.status, 200)
            self.assertEqual(result['database'], 'ready')
        finally:
            httpd.shutdown(); httpd.server_close(); worker.join(timeout=5)

    def test_sessions_expire_and_backup_is_created_for_admin(self):
        self.server.init()
        connection = self.server.db()
        admin = dict(connection.execute("select * from users where username='admin'").fetchone())
        connection.close()
        expired = secrets.token_urlsafe(24)
        self.server.SESSIONS[expired] = {'user': admin, 'expires_at': time.time() - 1}
        backup_dir = Path(self.temp.name) / 'backups'
        self.server.BACKUP_DIR = str(backup_dir)
        token = self.server.create_session(admin)
        httpd = self.server.ThreadingHTTPServer(('127.0.0.1', 0), self.server.H)
        worker = threading.Thread(target=httpd.serve_forever)
        worker.start()
        try:
            client = http.client.HTTPConnection('127.0.0.1', httpd.server_address[1], timeout=5)
            client.request('GET', '/api/system/status', headers={'Authorization': 'Bearer ' + expired})
            response = client.getresponse(); response.read(); client.close()
            self.assertEqual(response.status, 401)

            client = http.client.HTTPConnection('127.0.0.1', httpd.server_address[1], timeout=5)
            client.request('POST', '/api/system/backup', b'{}', {'Content-Type':'application/json','Authorization':'Bearer '+token})
            response = client.getresponse()
            result = json.loads(response.read().decode('utf-8'))
            client.close()
            self.assertEqual(response.status, 200)
            self.assertTrue((backup_dir / result['file_name']).is_file())
            self.assertGreater(result['size_bytes'], 0)
        finally:
            self.server.SESSIONS.pop(token, None)
            httpd.shutdown(); httpd.server_close(); worker.join(timeout=5)

    def test_migrates_a_legacy_projects_table_without_dropping_it(self):
        connection = sqlite3.connect(self.db_path)
        connection.execute("create table projects(id integer primary key, code text unique not null, name text not null, client_id integer, location text, status text not null default 'مفتوح', created_at text)")
        connection.execute("insert into projects(code,name,status) values('PR-000001','مشروع قديم','مفتوح')")
        connection.commit()
        connection.close()

        self.server.init()
        connection = self.server.db()
        row = connection.execute("select code,name,priority,progress from projects where code='PR-000001'").fetchone()
        columns = {item['name'] for item in connection.execute('pragma table_info(projects)')}
        connection.close()

        self.assertEqual(row['name'], 'مشروع قديم')
        self.assertEqual(row['priority'], 'متوسطة')
        self.assertEqual(row['progress'], 0)
        self.assertIn('approved_at', columns)

    def test_audit_and_sync_queue_are_written_on_the_same_database(self):
        self.server.init()
        connection = self.server.db()
        self.server.audit(connection, 1, 'اختبار', 'project', 7, 'PR-000007')
        self.server.queue_sync(connection, 'project', 7, 'create', {'code': 'PR-000007'})
        connection.commit()
        audit_count = connection.execute('select count(*) from audit_log').fetchone()[0]
        sync = connection.execute('select entity,entity_id,operation,status from sync_queue').fetchone()
        connection.close()

        self.assertEqual(audit_count, 1)
        self.assertEqual((sync['entity'], sync['entity_id'], sync['operation'], sync['status']), ('project', 7, 'create', 'queued'))

    def test_admin_can_delete_audit_entry_without_leaving_a_delete_marker(self):
        self.server.init()
        connection = self.server.db()
        self.server.audit(connection, 1, 'عملية قابلة للحذف', 'test', 9, 'تفاصيل')
        target_id = connection.execute("select id from audit_log where action='عملية قابلة للحذف'").fetchone()[0]
        connection.commit()
        admin = dict(connection.execute("select * from users where username='admin'").fetchone())
        token = secrets.token_urlsafe(24)
        self.server.SESSIONS[token] = admin
        connection.close()
        httpd = self.server.ThreadingHTTPServer(('127.0.0.1', 0), self.server.H)
        worker = threading.Thread(target=httpd.serve_forever)
        worker.start()
        try:
            client = http.client.HTTPConnection('127.0.0.1', httpd.server_address[1], timeout=5)
            payload = json.dumps({'id': target_id}).encode('utf-8')
            client.request('POST', '/api/audit/delete', payload, {'Content-Type':'application/json','Authorization':'Bearer '+token})
            response = client.getresponse()
            result = json.loads(response.read().decode('utf-8'))
            client.close()
            self.assertEqual(response.status, 200)
            self.assertEqual(result['deleted'], 1)
            connection = self.server.db()
            self.assertIsNone(connection.execute('select id from audit_log where id=?', (target_id,)).fetchone())
            self.assertIsNone(connection.execute("select id from audit_log where action='حذف سجل تدقيق'").fetchone())
            connection.close()
        finally:
            self.server.SESSIONS.pop(token, None)
            httpd.shutdown(); httpd.server_close(); worker.join(timeout=5)

    def test_project_work_order_and_workspace_api_flow(self):
        self.server.init()
        connection = self.server.db()
        connection.execute("update users set phone='+966500000001' where username='admin'")
        connection.commit()
        connection.close()
        httpd = self.server.ThreadingHTTPServer(('127.0.0.1', 0), self.server.H)
        worker = threading.Thread(target=httpd.serve_forever)
        worker.start()
        port = httpd.server_address[1]

        def request(method, path, payload=None, token=None):
            connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
            headers = {}
            if payload is not None:
                headers['Content-Type'] = 'application/json'
            if token:
                headers['Authorization'] = 'Bearer ' + token
            connection.request(method, path, json.dumps(payload).encode('utf-8') if payload is not None else None, headers)
            response = connection.getresponse()
            data = json.loads(response.read().decode('utf-8'))
            response_headers = dict(response.getheaders())
            connection.close()
            return response.status, data, response_headers

        try:
            self.server.twilio_verify_ready = lambda: True
            self.server.twilio_verify_request = lambda endpoint, fields: {'status': 'approved'}
            status, _, _ = request('POST', '/api/login', {'username': 'admin', 'password': self.bootstrap_password})
            self.assertEqual(status, 410)
            status, login, _ = request('POST', '/api/auth/login', {'username': 'admin', 'password': self.bootstrap_password})
            self.assertEqual(status, 200)
            token = login['token']

            status, client, _ = request('POST', '/api/clients', {'name': 'عميل الاختبار'}, token)
            self.assertEqual(status, 200)
            status, project, _ = request('POST', '/api/projects', {'name': 'مشروع الربط', 'client_id': client['id'], 'priority': 'عالية', 'start_date': '2026-09-01', 'due_date': '2026-09-30'}, token)
            self.assertEqual(status, 200)
            status, order, _ = request('POST', '/api/work-orders', {'project_id': project['id'], 'title': 'فحص عينات الموقع', 'status': 'مفتوح'}, token)
            self.assertEqual(status, 200)

            status, workspace, _ = request('GET', '/api/projects/' + str(project['id']) + '/workspace', token=token)
            self.assertEqual(status, 200)
            self.assertEqual(workspace['project']['code'], project['code'])
            self.assertEqual(workspace['work_orders'][0]['order_no'], order['order_no'])
            self.assertEqual(workspace['samples'], [])

            status, board, _ = request('GET', '/api/dashboard', token=token)
            self.assertEqual(status, 200)
            self.assertEqual(board['projects'][0]['work_orders_count'], 1)
            self.assertGreaterEqual(board['counts']['sync_queue'], 2)
            self.assertNotIn('whatsapp_drafts', board['counts'])
            self.assertNotIn('whatsapp_drafts', board)
            with sqlite3.connect(self.db_path) as connection:
                self.assertEqual(connection.execute('select count(*) from whatsapp_drafts').fetchone()[0], 0)
        finally:
            httpd.shutdown()
            httpd.server_close()
            worker.join(timeout=5)

    def test_admin_can_create_and_update_a_user(self):
        self.server.init()
        connection = self.server.db()
        connection.execute("update users set phone='+966500000001' where username='admin'")
        connection.commit()
        connection.close()
        httpd = self.server.ThreadingHTTPServer(('127.0.0.1', 0), self.server.H)
        worker = threading.Thread(target=httpd.serve_forever)
        worker.start()
        port = httpd.server_address[1]

        def request(method, path, payload=None, token=None):
            connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
            headers = {'Content-Type': 'application/json'} if payload is not None else {}
            if token:
                headers['Authorization'] = 'Bearer ' + token
            body = json.dumps(payload).encode('utf-8') if payload is not None else None
            connection.request(method, path, body, headers)
            response = connection.getresponse()
            data = json.loads(response.read().decode('utf-8'))
            response_headers = dict(response.getheaders())
            connection.close()
            return response.status, data, response_headers

        try:
            self.server.twilio_verify_ready = lambda: True
            self.server.twilio_verify_request = lambda endpoint, fields: {'status': 'approved'}
            status, login, _ = request('POST', '/api/auth/login', {'username': 'admin', 'password': self.bootstrap_password})
            self.assertEqual(status, 200)
            token = login['token']

            status, created, _ = request('POST', '/api/users/create', {
                'username': 'lab.user', 'full_name': 'مستخدم المختبر', 'password': 'Secure-password-123', 'role': 'technician'
            }, token)
            self.assertEqual(status, 200)
            self.assertTrue(created['ok'])

            status, updated, _ = request('POST', '/api/users/update', {
                'id': created['id'], 'full_name': 'مستخدم مختبر محدّث', 'role': 'manager', 'active': True,
                'password': '', 'avatar_data_url': 'data:image/jpeg;base64,/9j/test-avatar'
            }, token)
            self.assertEqual(status, 200)
            self.assertTrue(updated['ok'])

            status, users, _ = request('GET', '/api/users', token=token)
            self.assertEqual(status, 200)
            saved = next(item for item in users if item['id'] == created['id'])
            self.assertEqual(saved['full_name'], 'مستخدم مختبر محدّث')
            self.assertEqual(saved['role'], 'manager')
            self.assertEqual(saved['active'], 1)
            self.assertEqual(saved['avatar_data_url'], 'data:image/jpeg;base64,/9j/test-avatar')
            connection = self.server.db()
            user_sync = connection.execute("select entity,entity_id,operation,payload_json from sync_queue where entity='user' order by id").fetchall()
            connection.close()
            self.assertEqual([(row['entity'], row['entity_id'], row['operation']) for row in user_sync], [('user', created['id'], 'create'), ('user', created['id'], 'update')])
            self.assertNotIn('password', user_sync[-1]['payload_json'].lower())
        finally:
            httpd.shutdown()
            httpd.server_close()
            worker.join(timeout=5)

    def test_quality_records_api_requires_quality_permission_and_persists_records(self):
        self.server.init()
        connection = self.server.db()
        admin = connection.execute("select * from users where username='admin'").fetchone()
        connection.close()
        token = 'quality-admin-token'
        denied_token = 'quality-denied-token'
        self.server.SESSIONS[token] = dict(admin)
        self.server.SESSIONS[denied_token] = {'id': 999, 'username': 'technical', 'role': 'technical_manager'}
        httpd = self.server.ThreadingHTTPServer(('127.0.0.1', 0), self.server.H)
        worker = threading.Thread(target=httpd.serve_forever)
        worker.start()
        port = httpd.server_address[1]

        def request(method, path, payload=None, access_token=None):
            client = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
            headers = {'Authorization': 'Bearer ' + access_token} if access_token else {}
            if payload is not None:
                headers['Content-Type'] = 'application/json'
            client.request(method, path, json.dumps(payload).encode('utf-8') if payload is not None else None, headers)
            response = client.getresponse()
            data = json.loads(response.read().decode('utf-8'))
            client.close()
            return response.status, data

        try:
            self.assertEqual(request('POST', '/api/quality/documents', {'category': 'procedure', 'code': 'QMS-P-001', 'title': 'إجراء الجودة'}, token)[0], 200)
            self.assertEqual(request('POST', '/api/quality/proficiency', {'test_name': 'مقاومة الضغط', 'material': 'خرسانة'}, token)[0], 200)
            self.assertEqual(request('POST', '/api/quality/staff', {'full_name': 'موظف الجودة', 'specialty': 'خرسانة'}, token)[0], 200)
            status, quality = request('GET', '/api/quality', access_token=token)
            self.assertEqual(status, 200)
            self.assertEqual(quality['documents'][0]['code'], 'QMS-P-001')
            self.assertEqual(quality['proficiency'][0]['test_name'], 'مقاومة الضغط')
            self.assertEqual(quality['staff'][0]['full_name'], 'موظف الجودة')
            self.assertEqual(request('GET', '/api/quality', access_token=denied_token)[0], 403)
        finally:
            self.server.SESSIONS.pop(token, None)
            self.server.SESSIONS.pop(denied_token, None)
            httpd.shutdown()
            httpd.server_close()
            worker.join(timeout=5)

    def test_pages_origin_cors_allows_otp_authentication(self):
        self.server.init()
        connection = self.server.db()
        connection.execute("update users set phone='+966500000001' where username='admin'")
        connection.commit()
        connection.close()
        original_origin = self.server.ALLOWED_ORIGIN
        self.server.ALLOWED_ORIGIN = 'https://osamababeker4-netizen.github.io'
        httpd = self.server.ThreadingHTTPServer(('127.0.0.1', 0), self.server.H)
        worker = threading.Thread(target=httpd.serve_forever)
        worker.start()
        port = httpd.server_address[1]
        origin = 'https://osamababeker4-netizen.github.io'
        self.server.twilio_verify_ready = lambda: True
        self.server.twilio_verify_request = lambda endpoint, fields: {'status': 'approved'}

        try:
            connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
            connection.request('OPTIONS', '/api/auth/login', headers={'Origin': origin, 'Access-Control-Request-Method': 'POST'})
            response = connection.getresponse()
            self.assertEqual(response.status, 204)
            self.assertEqual(response.getheader('Access-Control-Allow-Origin'), origin)
            self.assertEqual(response.getheader('Access-Control-Allow-Credentials'), 'true')
            response.read()
            connection.close()

            connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
            body = json.dumps({'username': 'admin', 'password': self.bootstrap_password}).encode('utf-8')
            connection.request('POST', '/api/auth/login', body, {'Origin': origin, 'Content-Type': 'application/json'})
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.getheader('Access-Control-Allow-Origin'), origin)
            self.assertEqual(response.getheader('Access-Control-Allow-Credentials'), 'true')
            response.read()
            connection.close()

        finally:
            httpd.shutdown()
            httpd.server_close()
            worker.join(timeout=5)
            self.server.ALLOWED_ORIGIN = original_origin

    def test_field_visit_persists_official_tests_and_balady_data(self):
        self.server.init()
        connection = self.server.db()
        user = connection.execute("select * from users where username='admin'").fetchone()
        connection.close()
        token = 'field-visit-test-token'
        self.server.SESSIONS[token] = dict(user)
        httpd = self.server.ThreadingHTTPServer(('127.0.0.1', 0), self.server.H)
        worker = threading.Thread(target=httpd.serve_forever)
        worker.start()
        port = httpd.server_address[1]
        try:
            connection = self.server.db()
            catalog = connection.execute("select id,code,name_ar,standard from test_catalog where code='D1883'").fetchone()
            connection.close()
            body = {
                'license_no': 'BAL-1001', 'status': 'مسودة',
                'tests': [{'catalog_id': catalog['id'], 'name': catalog['name_ar'], 'standard': catalog['standard'], 'result': 'قيد التنفيذ'}],
                'balady_permit_no': 'BAL-1001', 'balady_municipality': 'أمانة الرياض',
                'balady_permit_type': 'حفرية', 'balady_permit_status': 'ساري',
                'balady_reference_url': 'https://balady.gov.sa/'
            }
            client = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
            client.request('POST', '/api/field/visits', json.dumps(body).encode('utf-8'), {
                'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token
            })
            response = client.getresponse()
            payload = json.loads(response.read().decode('utf-8'))
            client.close()
            self.assertEqual(response.status, 200)
            connection = self.server.db()
            saved = connection.execute('select * from field_visits where id=?', (payload['id'],)).fetchone()
            connection.close()
            self.assertEqual(saved['balady_municipality'], 'أمانة الرياض')
            self.assertEqual(json.loads(saved['tests_json'])[0]['catalog_id'], catalog['id'])
        finally:
            self.server.SESSIONS.pop(token, None)
            httpd.shutdown()
            httpd.server_close()
            worker.join(timeout=5)

    def test_final_device_acceptance_contract_is_wired(self):
        html = (Path(__file__).parent / 'index.html').read_text(encoding='utf-8')
        app = (Path(__file__).parent / 'app-password.js').read_text(encoding='utf-8')
        server = (Path(__file__).parent / 'server.py').read_text(encoding='utf-8')
        self.assertIn('id="runDeviceAcceptance"', html)
        self.assertIn('id="deviceAcceptanceResults"', html)
        self.assertIn('navigator.mediaDevices.getUserMedia', app)
        self.assertIn('navigator.geolocation.getCurrentPosition', app)
        self.assertIn("api('/api/system/acceptance')", app)
        self.assertIn("path == '/api/system/acceptance'", server)
        self.assertIn("PRAGMA quick_check", server)
        self.assertIn("database_write", server)
        self.assertIn("permissions_valid", server)

    def test_all_defined_roles_have_deterministic_permissions(self):
        expected_roles = {
            'admin','general_manager','technical_manager','laboratory_manager','quality_manager',
            'quality_officer','calibration_officer','document_controller','manager','quality','technician','field'
        }
        self.assertEqual(set(self.server.ROLE_PERMS), expected_roles)
        self.assertEqual(self.server.ROLE_PERMS['admin'], {'*'})
        self.assertEqual(self.server.ROLE_PERMS['quality_manager'], {'*'})
        for role, permissions in self.server.ROLE_PERMS.items():
            self.assertTrue(permissions, role)
            self.assertTrue(all(isinstance(item, str) and item for item in permissions))



    def test_v10218_operational_fixes_are_release_gated(self):
        root = Path(__file__).parent
        server = (root / 'server.py').read_text(encoding='utf-8')
        app = (root / 'app-password.js').read_text(encoding='utf-8')
        html = (root / 'index.html').read_text(encoding='utf-8')
        css = (root / 'style.css').read_text(encoding='utf-8')
        sw = (root / 'sw.js').read_text(encoding='utf-8')

        self.assertIn("APP_VERSION = '10.8.4-login-fix'", server)
        self.assertIn("MAX_SMART_FILE_BYTES", server)
        self.assertIn("MAX_ZIP_EXPANDED_BYTES", server)
        self.assertIn("self.send_cors_headers()", server)
        self.assertIn("for required_dir in (os.path.dirname(os.path.abspath(DB)), BACKUP_DIR, QUALITY_UPLOADS, RECORD_UPLOADS)", server)

        self.assertIn("file.size>100*1024*1024", app)
        self.assertIn("data-quality-file-ref", app)
        self.assertIn("mode:'cors'", app)
        self.assertIn("تم تجاوز '+failed.length+' ملف", app)

        self.assertIn('id="qualityInternalHub"', html)
        for window_id in ('qualityDocumentsWindow', 'proficiencyWindow', 'qualityStaffWindow'):
            self.assertIn('id="' + window_id + '"', html)
        self.assertEqual(html.count('id="qualityDocumentsTable"'), 1)
        self.assertEqual(html.count('id="proficiencyTable"'), 1)
        self.assertEqual(html.count('id="qualityStaffTable"'), 1)
        self.assertIn('الملف الرئيسي الموحد', html)
        self.assertIn('.internal-window-card', css)
        self.assertIn('v10-8-9-button-save-fix', sw)

    def test_init_creates_all_production_storage_directories(self):
        backup = Path(self.temp.name) / 'backups'
        quality = Path(self.temp.name) / 'quality'
        records = Path(self.temp.name) / 'records'
        self.server.BACKUP_DIR = str(backup)
        self.server.QUALITY_UPLOADS = str(quality)
        self.server.RECORD_UPLOADS = str(records)
        self.server.init()
        self.assertTrue(backup.is_dir())
        self.assertTrue(quality.is_dir())
        self.assertTrue(records.is_dir())



    def test_v10219_quality_control_is_one_unified_inline_file(self):
        root = Path(__file__).parent
        html = (root / 'index.html').read_text(encoding='utf-8')
        app = (root / 'app-password.js').read_text(encoding='utf-8')
        qms = (root / 'quality-management.js').read_text(encoding='utf-8')
        css = (root / 'style.css').read_text(encoding='utf-8')

        self.assertIn('ضبط الجودة', html)
        self.assertIn('QUALITY CONTROL', html)
        self.assertIn('id="qualityInternalHub"', html)
        ordered = [
            'qualityDocumentsWindow','qualityFilesEntry','proficiencyWindow','qualityStaffWindow',
            'procedureWindow','worksheetWindow','adminFormsWindow','swotWindow','riskWindow','kpiWindow',
            'actionWindow','qualityEquipmentCard','qualityImportLogWindow','managementCycleWindow',
            'technicalLibraryWindow','companyVaultCard'
        ]
        positions = [html.index('id="' + item + '"') for item in ordered]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn('management-cycle-board', html)
        self.assertIn('data-inline-smart-import="technicalLibrary"', html)
        self.assertIn('data-inline-smart-import="companyVault"', html)
        self.assertIn('data-inline-quality-document="procedure"', html)
        self.assertIn('data-inline-quality-record="proficiency"', html)
        self.assertIn('data-inline-equipment', html)
        self.assertIn('data-qm-inline-save="swot"', html)
        self.assertIn('data-cycle-stage-form', qms)
        self.assertIn("if (page === 'documentCenter') page = 'quality';", app)
        self.assertIn('.quality-control-hero', css)
        self.assertIn('#quality .qc-window-card', css)



    def test_v10220_smart_standards_auto_link_and_field_manual(self):
        root = Path(__file__).parent
        html = (root / 'index.html').read_text(encoding='utf-8')
        app = (root / 'app-password.js').read_text(encoding='utf-8')
        css = (root / 'style.css').read_text(encoding='utf-8')
        server = (root / 'server.py').read_text(encoding='utf-8')

        self.assertIn('id="catalogBulkStandardsButton"', html)
        self.assertIn('id="catalogStandardsInput"', html)
        self.assertIn('دليل الاختبارات الميداني', html)
        self.assertIn('id="openFieldManual"', html)
        self.assertIn('xlsx.full.min.js', html)
        self.assertIn('mammoth.browser.min.js', html)
        self.assertIn('jszip.min.js', html)
        self.assertIn('uploadCatalogStandardsBatch', app)
        self.assertIn('spreadsheetPreviewHtml', app)
        self.assertIn('wordPreviewHtml', app)
        self.assertIn('zipPreviewHtml', app)
        self.assertIn('FIELD_MANUAL_REF', app)
        self.assertIn('detect_catalog_target', server)
        self.assertIn('detect_catalog_resource_type', server)
        self.assertIn('.spreadsheet-preview-table', css)

    def test_catalog_smart_upload_links_short_and_long_astm_codes_without_manual_step(self):
        self.server.init()
        self.server.RECORD_UPLOADS = str(Path(self.temp.name) / 'records')
        os.makedirs(self.server.RECORD_UPLOADS, exist_ok=True)
        connection = self.server.db()
        admin = dict(connection.execute("select * from users where username='admin'").fetchone())

        d1557 = connection.execute("select id from test_catalog where code='D1557'").fetchone()['id']
        d5 = connection.execute("select id from test_catalog where code='D5'").fetchone()['id']
        d5444 = connection.execute("select id from test_catalog where code='D5444'").fetchone()['id']

        first = self.server.store_smart_file(connection, admin, 'catalog', 'ASTM D1557 Modified Proctor.pdf', b'%PDF-1.4 ASTM D1557')
        self.assertEqual(first['entity_id'], d1557)
        self.assertEqual(first['resource_type'], 'astm')
        linked = connection.execute('select astm_attachment_id from catalog_resources where test_catalog_id=?', (d1557,)).fetchone()
        self.assertEqual(linked['astm_attachment_id'], first['id'])

        short = self.server.store_smart_file(connection, admin, 'catalog', 'ASTM D5 penetration.pdf', b'%PDF-1.4 ASTM D5')
        self.assertEqual(short['entity_id'], d5)
        self.assertNotEqual(short['entity_id'], d5444)

        worksheet = self.server.store_smart_file(connection, admin, 'catalog', 'C39 Work Sheet.xlsx', b'not-a-real-xlsx C39 worksheet')
        c39 = connection.execute("select id from test_catalog where code='C39'").fetchone()['id']
        self.assertEqual(worksheet['entity_id'], c39)
        self.assertEqual(worksheet['resource_type'], 'worksheet')
        linked_ws = connection.execute('select worksheet_attachment_id from catalog_resources where test_catalog_id=?', (c39,)).fetchone()
        self.assertEqual(linked_ws['worksheet_attachment_id'], worksheet['id'])
        connection.commit()
        connection.close()



    def test_v10221_all_uploaded_files_have_open_download_delete_and_any_format_storage(self):
        root = Path(__file__).parent
        html = (root / 'index.html').read_text(encoding='utf-8')
        app = (root / 'app-password.js').read_text(encoding='utf-8')
        server = (root / 'server.py').read_text(encoding='utf-8')

        self.assertIn('دليل الاختبارات الميدانيه', html)
        self.assertNotIn('4 أقسام رئيسية', html)
        self.assertIn('data-smart-open', app)
        self.assertIn('data-smart-download', app)
        self.assertIn('data-smart-delete', app)
        self.assertIn('data-catalog-download', app)
        self.assertIn('data-catalog-delete', app)
        self.assertIn('data-quality-file-download', app)
        self.assertIn('data-quality-file-delete', app)
        self.assertIn("'/api/attachments/delete'", server)
        self.assertIn("'/api/quality/files/delete'", server)
        self.assertIn('FILE_DELETE_ROLES', server)
        self.assertIn('smart_file_category', server)
        self.assertIn("return ('ملف ' + extension.lstrip('.').upper()) if extension else 'ملف'", server)

        self.server.init()
        self.server.RECORD_UPLOADS = str(Path(self.temp.name) / 'records-v10221')
        os.makedirs(self.server.RECORD_UPLOADS, exist_ok=True)
        connection = self.server.db()
        admin = dict(connection.execute("select * from users where username='admin'").fetchone())
        technician = {'role':'technician'}
        before_audit = connection.execute('select count(*) from audit_log').fetchone()[0]

        stored = self.server.store_smart_file(connection, admin, 'technicalLibrary', 'device-output.sensorbin', b'\x00\x01ASAS binary payload')
        self.assertEqual(stored['category'], 'ملف SENSORBIN')
        row = connection.execute('select * from record_attachments where id=?', (stored['id'],)).fetchone()
        self.assertTrue(self.server.attachment_delete_allowed(admin, row))
        self.assertFalse(self.server.attachment_delete_allowed(technician, row))
        stored_path = Path(self.server.RECORD_UPLOADS) / row['stored_name']
        self.assertTrue(stored_path.exists())

        deleted = self.server.delete_record_attachment(connection, stored['id'])
        self.assertEqual(deleted['original_name'], 'device-output.sensorbin')
        connection.commit()
        after_audit = connection.execute('select count(*) from audit_log').fetchone()[0]
        self.assertEqual(before_audit, after_audit)
        self.assertIsNone(connection.execute('select id from record_attachments where id=?', (stored['id'],)).fetchone())
        connection.close()

    def test_v10221_catalog_file_delete_clears_resource_link(self):
        self.server.init()
        self.server.RECORD_UPLOADS = str(Path(self.temp.name) / 'records-catalog-delete')
        os.makedirs(self.server.RECORD_UPLOADS, exist_ok=True)
        connection = self.server.db()
        admin = dict(connection.execute("select * from users where username='admin'").fetchone())
        d1557 = connection.execute("select id from test_catalog where code='D1557'").fetchone()['id']
        stored = self.server.store_smart_file(connection, admin, 'catalog', 'ASTM D1557 specification.custom', b'ASTM D1557 standard specification')
        link = connection.execute('select astm_attachment_id from catalog_resources where test_catalog_id=?', (d1557,)).fetchone()
        self.assertEqual(link['astm_attachment_id'], stored['id'])
        self.server.delete_record_attachment(connection, stored['id'])
        connection.commit()
        link = connection.execute('select astm_attachment_id from catalog_resources where test_catalog_id=?', (d1557,)).fetchone()
        self.assertIsNone(link['astm_attachment_id'])
        connection.close()


    def test_field_catalog_is_sidebar_of_visit_form_and_responsive(self):
        root = Path(__file__).parent
        html = (root / 'index.html').read_text(encoding='utf-8')
        css = (root / 'style.css').read_text(encoding='utf-8')

        field_start = html.index('<section id="field" class="page">')
        field_end = html.index('<section id="clients" class="page">', field_start)
        field_html = html[field_start:field_end]
        layout_start = field_html.index('<div class="field-layout">')
        visit_start = field_html.index('<article class="panel">', layout_start)
        sidebar_start = field_html.index('<aside class="panel field-guide-library field-guide-sidebar">', layout_start)

        self.assertLess(visit_start, sidebar_start)
        self.assertNotIn('<section class="panel field-guide-library">', field_html[:layout_start])
        self.assertIn('id="fieldTestSearch"', field_html[sidebar_start:])
        self.assertIn('id="openCustomFieldTest"', field_html[sidebar_start:])
        self.assertIn('id="fieldGuideGrid"', field_html[sidebar_start:])
        self.assertIn('id="openFieldManual"', field_html[sidebar_start:])
        self.assertIn('دليل الاختبارات الميدانيه', field_html[sidebar_start:])

        self.assertIn('#field .field-layout{', css)
        self.assertIn('grid-template-columns:minmax(0,1.35fr) minmax(330px,.65fr)', css)
        self.assertIn('#field .field-guide-sidebar .field-guide-grid{', css)
        self.assertIn('grid-template-columns:1fr', css)
        self.assertIn('@media(max-width:900px)', css)
        self.assertIn('#field .field-guide-sidebar{order:-1}', css)
        self.assertIn('@media(max-width:620px)', css)


    def test_deleted_uploaded_files_move_to_trash_and_restore_with_catalog_link(self):
        self.server.init()
        self.server.RECORD_UPLOADS = str(Path(self.temp.name) / 'trash-record-files')
        os.makedirs(self.server.RECORD_UPLOADS, exist_ok=True)
        connection = self.server.db()
        admin = dict(connection.execute("select * from users where username='admin'").fetchone())
        before_audit = connection.execute('select count(*) from audit_log').fetchone()[0]

        d1557 = connection.execute("select id from test_catalog where code='D1557'").fetchone()['id']
        stored = self.server.store_smart_file(connection, admin, 'catalog', 'ASTM D1557 deleted-standard.pdf', b'%PDF-1.4 ASTM D1557')
        row = dict(connection.execute('select * from record_attachments where id=?', (stored['id'],)).fetchone())
        stored_path = Path(self.server.RECORD_UPLOADS) / row['stored_name']
        self.assertTrue(stored_path.exists())
        links = []
        for column in ('astm_attachment_id','worksheet_attachment_id','results_attachment_id'):
            for link in connection.execute('select test_catalog_id from catalog_resources where ' + column + '=?', (stored['id'],)).fetchall():
                links.append({'test_catalog_id': link['test_catalog_id'], 'column': column})
        payload = {'entity_type':'uploaded_file','original_id':stored['id'],'attachments':[row],'catalog_links':links}
        connection.execute('insert into trash_items(entity_type,original_id,label,payload_json,deleted_by) values(?,?,?,?,?)',
                           ('uploaded_file', stored['id'], row['original_name'], json.dumps(payload, ensure_ascii=False), admin['id']))
        self.server.delete_record_attachment(connection, stored['id'])
        connection.commit()

        self.assertIsNone(connection.execute('select id from record_attachments where id=?', (stored['id'],)).fetchone())
        self.assertTrue(stored_path.exists(), 'moving to Trash must keep original file bytes')
        self.assertEqual(connection.execute("select count(*) from trash_items where entity_type='uploaded_file' and original_id=?", (stored['id'],)).fetchone()[0], 1)
        self.assertEqual(connection.execute('select count(*) from audit_log').fetchone()[0], before_audit)

        self.server.restore_deleted_record(connection, payload)
        connection.execute("delete from trash_items where entity_type='uploaded_file' and original_id=?", (stored['id'],))
        connection.commit()
        self.assertIsNotNone(connection.execute('select id from record_attachments where id=?', (stored['id'],)).fetchone())
        link = connection.execute('select astm_attachment_id from catalog_resources where test_catalog_id=?', (d1557,)).fetchone()
        self.assertEqual(link['astm_attachment_id'], stored['id'])
        self.assertTrue(stored_path.exists())
        connection.close()

    def test_deleted_quality_file_can_be_restored_from_trash(self):
        self.server.init()
        self.server.QUALITY_UPLOADS = str(Path(self.temp.name) / 'trash-quality-files')
        os.makedirs(self.server.QUALITY_UPLOADS, exist_ok=True)
        connection = self.server.db()
        admin = dict(connection.execute("select * from users where username='admin'").fetchone())
        stored_name = 'quality-trash-test.pdf'
        target = Path(self.server.QUALITY_UPLOADS) / stored_name
        target.write_bytes(b'%PDF-1.4 quality')
        ref = '/api/quality/files/' + stored_name
        connection.execute("insert into quality_documents(category,code,title,status,document_ref) values('procedure','TRASH-Q','Trash quality','ساري',?)", (ref,))
        document_id = connection.execute('select last_insert_rowid()').fetchone()[0]
        payload = {'entity_type':'quality_file','original_id':0,'quality_file':{'stored_name':stored_name,'ref':ref},
                   'quality_links':[{'table':'quality_documents','column':'document_ref','id':document_id}]}
        connection.execute('insert into trash_items(entity_type,original_id,label,payload_json,deleted_by) values(?,?,?,?,?)',
                           ('quality_file', 0, 'quality-trash-test.pdf', json.dumps(payload, ensure_ascii=False), admin['id']))
        connection.execute('update quality_documents set document_ref=null where id=?', (document_id,))
        connection.commit()

        self.assertTrue(target.exists(), 'quality file bytes must remain while item is in Trash')
        self.assertIsNone(connection.execute('select document_ref from quality_documents where id=?', (document_id,)).fetchone()['document_ref'])
        self.server.restore_deleted_record(connection, payload)
        connection.commit()
        self.assertEqual(connection.execute('select document_ref from quality_documents where id=?', (document_id,)).fetchone()['document_ref'], ref)
        self.assertTrue(target.exists())
        connection.close()

    def test_file_delete_ui_explicitly_moves_files_to_trash(self):
        root = Path(__file__).parent
        app = (root / 'app-password.js').read_text(encoding='utf-8')
        server = (root / 'server.py').read_text(encoding='utf-8')
        self.assertIn('إلى سلة المحذوفات؟ يمكنك استعادته لاحقًا', app)
        self.assertIn('تم نقل الملف إلى سلة المحذوفات', app)
        self.assertIn("('uploaded_file', attachment_id, row['original_name']", server)
        self.assertIn("('quality_file', 0, str(data.get('name') or stored_name)", server)
        self.assertIn("if path == '/api/trash/file':", server)
        self.assertIn("row['entity_type'] == 'quality_file'", server)


    def test_field_manual_uses_authenticated_proxy_and_local_pdf_cache(self):
        root = Path(__file__).parent
        app = (root / 'app-password.js').read_text(encoding='utf-8')
        server = (root / 'server.py').read_text(encoding='utf-8')
        self.assertIn("const FIELD_MANUAL_REF = '/api/field/manual';", app)
        self.assertIn("fetch(API_BASE_URL+FIELD_MANUAL_REF", app)
        self.assertIn("if path == '/api/field/manual':", server)
        self.assertIn("'Content-Disposition': \"inline; filename*=UTF-8''\" + quote(filename)", server)
        self.assertNotIn('FIELD_MANUAL_URL', app)
        self.assertIn('عرض الدليل التشغيلي المحلي داخل البرنامج', app)

        cache = Path(self.temp.name) / 'field-guide.pdf'
        cache.write_bytes(b'%PDF-' + b'x' * 2048)
        old_cache = self.server.FIELD_MANUAL_CACHE
        try:
            self.server.FIELD_MANUAL_CACHE = str(cache)
            self.assertEqual(self.server.ensure_field_manual_cache(), str(cache))
        finally:
            self.server.FIELD_MANUAL_CACHE = old_cache


    def test_v1030_decision_intelligence_is_live_and_operational(self):
        root = Path(__file__).parent
        html = (root / 'index.html').read_text(encoding='utf-8')
        app = (root / 'app-password.js').read_text(encoding='utf-8')
        css = (root / 'style.css').read_text(encoding='utf-8')
        server = (root / 'server.py').read_text(encoding='utf-8')
        sw = (root / 'sw.js').read_text(encoding='utf-8')

        self.assertIn("APP_VERSION = '10.8.4-login-fix'", server)
        self.assertIn('v10-8-4-login-fix', sw)
        self.assertIn('ASAS LIMS · V10.8.9', html)
        self.assertIn('V10.8.9 · Button Save Fix', html)
        self.assertNotIn('V10.3.0 Decision Intelligence', html)
        self.assertIn('id="decisionIntelligenceCenter"', html)
        self.assertIn('id="refreshDecisionIntelligence"', html)
        self.assertIn('id="exportDecisionIntelligence"', html)
        self.assertIn('id="openDecisionReport"', html)
        for item in (
            'decisionProjectProgress','decisionWorkOrderRate','decisionTestRate','decisionReportRate',
            'decisionDataIssueCount','decisionCriticalCount','decisionExecutiveSummary',
            'decisionDataQuality','decisionProjectHealth','decisionRecommendations'
        ):
            self.assertIn('id="' + item + '"', html)

        self.assertIn('function decisionIntelligenceModel()', app)
        self.assertIn('function renderDecisionIntelligence()', app)
        self.assertIn('function exportDecisionIntelligence()', app)
        self.assertIn('function openDecisionIntelligenceReport()', app)
        self.assertIn("XLSX.writeFile(workbook,'ASAS_Decision_Intelligence_'", app)
        self.assertIn("أوامر عمل بلا مسؤول", app)
        self.assertIn("اختبارات غير مسندة لفني", app)
        self.assertIn("أجهزة تجاوزت تاريخ المعايرة", app)
        self.assertIn("أسماء عملاء مكررة", app)
        self.assertIn("هذا التقرير يعتمد على بيانات النظام المسجلة", app)
        self.assertIn('.decision-intelligence', css)
        self.assertIn('.decision-kpi-grid', css)
        self.assertIn('body.decision-print-mode', css)

    def test_v1030_decision_intelligence_buttons_have_handlers(self):
        root = Path(__file__).parent
        app = (root / 'app-password.js').read_text(encoding='utf-8')
        self.assertIn("refreshDecisionIntelligence').addEventListener('click'", app)
        self.assertIn("exportDecisionIntelligence').addEventListener('click'", app)
        self.assertIn("openDecisionReport').addEventListener('click'", app)
        self.assertIn("data-decision-report-export", app)
        self.assertIn("data-decision-report-print", app)
        self.assertIn("data-decision-action", app)
        self.assertIn("data-decision-issue", app)
        self.assertIn("data-decision-record", app)
        self.assertIn('renderDecisionIntelligence();', app)

    def test_v104_operational_workspace_is_persistent_and_actionable(self):
        root = Path(__file__).parent
        html = (root / 'index.html').read_text(encoding='utf-8')
        app = (root / 'app-password.js').read_text(encoding='utf-8')
        schema = (root / 'schema.sql').read_text(encoding='utf-8')
        server = (root / 'server.py').read_text(encoding='utf-8')
        self.assertIn("APP_VERSION = '10.8.4-login-fix'", server)
        self.assertIn('CREATE TABLE IF NOT EXISTS operational_tasks', schema)
        self.assertIn("path == '/api/operational-tasks'", server)
        self.assertIn('id="operationalWorkspace"', html)
        self.assertIn('id="openOperationalTask"', html)
        self.assertIn('function renderOperationalWorkspace()', app)
        self.assertIn("form.id === 'operationalTaskForm'", app)
        self.assertIn("data-task-status", app)
        self.assertIn("Eng. osama Ismail", server)

    def test_v107_live_notifications_and_direct_remediation_are_wired(self):
        root = Path(__file__).parent
        html = (root / 'index.html').read_text(encoding='utf-8')
        app = (root / 'app-password.js').read_text(encoding='utf-8')
        server = (root / 'server.py').read_text(encoding='utf-8')
        for element in ('notificationToggle','notificationCount','notificationPanel','notificationList','markNotificationsRead'):
            self.assertIn('id="' + element + '"', html)
        for contract in ('function buildSystemNotifications()','function renderSystemNotifications()','function openNotificationItem(index)','data-notification-index','openSyncWorkQueue()'):
            self.assertIn(contract, app)
        self.assertIn("data.get('action') == 'update'", server)
        self.assertIn("queue_sync(connection,'work_order'", server)
        self.assertIn("queue_sync(connection,'sample'", server)

    def test_operational_task_api_creates_updates_and_queues_sync(self):
        self.server.init()
        connection = self.server.db()
        admin = dict(connection.execute("select * from users where username='admin'").fetchone())
        connection.close()
        token = self.server.create_session(admin)
        httpd = self.server.ThreadingHTTPServer(('127.0.0.1', 0), self.server.H)
        worker = threading.Thread(target=httpd.serve_forever)
        worker.start()
        def post(payload):
            client = http.client.HTTPConnection('127.0.0.1', httpd.server_address[1], timeout=5)
            client.request('POST', '/api/operational-tasks', json.dumps(payload).encode('utf-8'), {
                'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
            response = client.getresponse()
            body = json.loads(response.read().decode('utf-8'))
            client.close()
            return response.status, body
        try:
            status, created = post({'title':'مراجعة الاختبارات المتأخرة','assigned_to':admin['id'],'priority':'حرجة','due_date':'2026-09-21'})
            self.assertEqual(status, 200)
            status, updated = post({'action':'update','id':created['id'],'status':'مكتملة'})
            self.assertEqual(status, 200)
            connection = self.server.db()
            task = connection.execute('select * from operational_tasks where id=?',(created['id'],)).fetchone()
            queued = connection.execute("select count(*) total from sync_queue where entity='operational_task' and entity_id=?",(created['id'],)).fetchone()['total']
            connection.close()
            self.assertEqual(task['status'], 'مكتملة')
            self.assertIsNotNone(task['completed_at'])
            self.assertEqual(queued, 2)
        finally:
            httpd.shutdown(); httpd.server_close(); worker.join(timeout=5)


if __name__ == '__main__':
    unittest.main()
