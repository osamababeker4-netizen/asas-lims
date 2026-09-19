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
        self.assertIn('<h1>تسجيل دخول النظام</h1>', html)
        self.assertIn('data-page="dashboard">الرئيسية</button>', html)
        self.assertNotIn('id="documentCenterNav"', html)
        self.assertIn('id="qualityFilesEntry"', html)
        self.assertIn('data-page-go="documentCenter"', html)
        self.assertIn('id="documentCenter"', html)
        self.assertIn('QUALITY_ACCESS_ROLES', app)
        self.assertIn("page === 'quality' || page === 'documentCenter'", app)
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
        self.assertIn('4 أقسام رئيسية', html)
        self.assertIn('field-test-guide.html', html)
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
        self.assertIn('src="logo.jpg" class="login-logo"', html)
        self.assertIn('src="asas-home-banner.jpg" class="dashboard-brand-logo dashboard-home-banner"', html)
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
        self.assertIn('src="logo.jpg" class="login-logo"', html)
        self.assertIn('src="asas-home-banner.jpg" class="dashboard-brand-logo dashboard-home-banner"', html)
        self.assertIn('src="logo.jpg" class="brand-logo"', html)
        self.assertIn('src="logo.jpg" alt="شركة مختبر أساس للاستشارات الفنية والمختبرات الهندسية"', html)
        self.assertIn('src="logo.jpg" class="dashboard-brand-logo"', html)
        self.assertNotIn('src="asas-logo-primary.png"', html)
        self.assertIn('src="whatsapp-logo.svg"', html)
        self.assertIn('src="telegram-logo.svg"', html)
        self.assertNotIn('>WA</span>', html)
        self.assertNotIn('>TG</span>', html)
        self.assertIn("'/whatsapp-logo.svg': ('whatsapp-logo.svg', 'image/svg+xml; charset=utf-8')", server_source)
        self.assertIn("'/telegram-logo.svg': ('telegram-logo.svg', 'image/svg+xml; charset=utf-8')", server_source)
        self.assertIn("'./logo.jpg'", sw)
        self.assertIn("'./asas-home-banner.jpg'", sw)
        self.assertIn("'./whatsapp-logo.svg'", sw)
        self.assertIn("'./telegram-logo.svg'", sw)
        self.assertNotIn("'./asas-logo-primary.png'", sw)
        self.assertIn('whatsapp-logo.svg', pages)
        self.assertIn('telegram-logo.svg', pages)
        self.assertIn('asas-home-banner.jpg', pages)
        self.server.init()
        httpd = self.server.ThreadingHTTPServer(('127.0.0.1', 0), self.server.H)
        worker = threading.Thread(target=httpd.serve_forever)
        worker.start()
        try:
            for path, signature in (
                ('/logo.jpg', b'\xff\xd8\xff'),
                ('/asas-home-banner.jpg', b'\xff\xd8\xff'),
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
        self.assertIn('data-viewer-newtab', app)
        self.assertIn('.attachment-viewer-frame', css)
        self.assertIn('.attachment-original-format', css)
        self.assertIn('فتح الملف</button>', app)
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

    def test_admin_can_delete_audit_entry_and_deletion_is_audited(self):
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
            self.assertIsNotNone(connection.execute("select id from audit_log where action='حذف سجل تدقيق'").fetchone())
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


if __name__ == '__main__':
    unittest.main()
