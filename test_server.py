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
        import server
        self.server = importlib.reload(server)

    def tearDown(self):
        self.temp.cleanup()
        os.environ.pop('LIMS_DB_PATH', None)
        os.environ.pop('LIMS_BOOTSTRAP_PASSWORD', None)

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
        httpd = self.server.ThreadingHTTPServer(('127.0.0.1', 0), self.server.H)
        worker = threading.Thread(target=httpd.serve_forever)
        worker.start()
        port = httpd.server_address[1]

        def request(method, path, payload=None, cookie=None):
            connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
            headers = {}
            if payload is not None:
                headers['Content-Type'] = 'application/json'
            if cookie:
                headers['Cookie'] = cookie
            connection.request(method, path, json.dumps(payload).encode('utf-8') if payload is not None else None, headers)
            response = connection.getresponse()
            data = json.loads(response.read().decode('utf-8'))
            response_headers = dict(response.getheaders())
            connection.close()
            return response.status, data, response_headers

        try:
            status, login, headers = request('POST', '/api/login', {'username': 'admin', 'password': self.bootstrap_password})
            self.assertEqual(status, 200)
            cookie = headers['Set-Cookie'].split(';', 1)[0]

            status, client, _ = request('POST', '/api/clients', {'name': 'عميل الاختبار'}, cookie)
            self.assertEqual(status, 200)
            status, project, _ = request('POST', '/api/projects', {'name': 'مشروع الربط', 'client_id': client['id'], 'priority': 'عالية', 'start_date': '2026-09-01', 'due_date': '2026-09-30'}, cookie)
            self.assertEqual(status, 200)
            status, order, _ = request('POST', '/api/work-orders', {'project_id': project['id'], 'title': 'فحص عينات الموقع', 'status': 'مفتوح'}, cookie)
            self.assertEqual(status, 200)

            status, workspace, _ = request('GET', '/api/projects/' + str(project['id']) + '/workspace', cookie=cookie)
            self.assertEqual(status, 200)
            self.assertEqual(workspace['project']['code'], project['code'])
            self.assertEqual(workspace['work_orders'][0]['order_no'], order['order_no'])
            self.assertEqual(workspace['samples'], [])

            status, board, _ = request('GET', '/api/dashboard', cookie=cookie)
            self.assertEqual(status, 200)
            self.assertEqual(board['projects'][0]['work_orders_count'], 1)
            self.assertGreaterEqual(board['counts']['sync_queue'], 2)
        finally:
            httpd.shutdown()
            httpd.server_close()
            worker.join(timeout=5)


if __name__ == '__main__':
    unittest.main()
