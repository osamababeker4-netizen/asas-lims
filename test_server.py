import importlib
import http.client
import json
import os
import secrets
import sqlite3
import tempfile
import threading
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

        self.assertTrue({'projects', 'work_orders', 'sync_queue', 'field_visits', 'audit_log'}.issubset(tables))
        self.assertTrue({'priority', 'description', 'start_date', 'due_date', 'progress', 'reviewed_by', 'approved_by'}.issubset(project_columns))
        self.assertIsNotNone(admin)
        self.assertIn(':', admin['password_hash'])

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
            self.assertTrue(login['challenge'])
            status, verified, _ = request('POST', '/api/auth/verify', {'username': 'admin', 'otp': '123456'})
            self.assertEqual(status, 200)
            token = verified['token']

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
            status, _, _ = request('POST', '/api/auth/login', {'username': 'admin', 'password': self.bootstrap_password})
            self.assertEqual(status, 200)
            status, verified, _ = request('POST', '/api/auth/verify', {'username': 'admin', 'otp': '123456'})
            self.assertEqual(status, 200)
            token = verified['token']

            status, created, _ = request('POST', '/api/users/create', {
                'username': 'lab.user', 'full_name': 'مستخدم المختبر', 'password': 'Secure-password-123', 'role': 'technician'
            }, token)
            self.assertEqual(status, 200)
            self.assertTrue(created['ok'])

            status, updated, _ = request('POST', '/api/users/update', {
                'id': created['id'], 'full_name': 'مستخدم مختبر محدّث', 'role': 'manager', 'active': True, 'password': ''
            }, token)
            self.assertEqual(status, 200)
            self.assertTrue(updated['ok'])

            status, users, _ = request('GET', '/api/users', token=token)
            self.assertEqual(status, 200)
            saved = next(item for item in users if item['id'] == created['id'])
            self.assertEqual(saved['full_name'], 'مستخدم مختبر محدّث')
            self.assertEqual(saved['role'], 'manager')
            self.assertEqual(saved['active'], 1)
        finally:
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
