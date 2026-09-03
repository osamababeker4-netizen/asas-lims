PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS users(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 username TEXT UNIQUE NOT NULL,
 password_hash TEXT NOT NULL,
 full_name TEXT NOT NULL,
 role TEXT NOT NULL DEFAULT 'technician',
 phone TEXT,
 active INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS clients(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 name TEXT NOT NULL,
 phone TEXT,
 email TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS projects(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 code TEXT UNIQUE NOT NULL,
 name TEXT NOT NULL,
 client_id INTEGER,
 location TEXT,
 status TEXT NOT NULL DEFAULT 'مخطط',
 priority TEXT NOT NULL DEFAULT 'متوسطة',
 description TEXT,
 contractor_name TEXT,
 consultant_name TEXT,
 start_date TEXT,
 due_date TEXT,
 progress INTEGER NOT NULL DEFAULT 0,
 manager_id INTEGER,
 reviewed_by INTEGER,
 reviewed_at TEXT,
 approved_by INTEGER,
 approved_at TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at TEXT,
 FOREIGN KEY(client_id) REFERENCES clients(id),
 FOREIGN KEY(manager_id) REFERENCES users(id),
 FOREIGN KEY(reviewed_by) REFERENCES users(id),
 FOREIGN KEY(approved_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS work_orders(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 order_no TEXT UNIQUE NOT NULL,
 project_id INTEGER NOT NULL,
 title TEXT NOT NULL,
 description TEXT,
 status TEXT NOT NULL DEFAULT 'مفتوح',
 priority TEXT NOT NULL DEFAULT 'متوسطة',
 scheduled_date TEXT,
 due_date TEXT,
 assigned_to INTEGER,
 created_by INTEGER,
 reviewed_by INTEGER,
 reviewed_at TEXT,
 approved_by INTEGER,
 approved_at TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at TEXT,
 FOREIGN KEY(project_id) REFERENCES projects(id),
 FOREIGN KEY(assigned_to) REFERENCES users(id),
 FOREIGN KEY(created_by) REFERENCES users(id),
 FOREIGN KEY(reviewed_by) REFERENCES users(id),
 FOREIGN KEY(approved_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS samples(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 sample_no TEXT UNIQUE NOT NULL,
 project_id INTEGER,
 material TEXT NOT NULL,
 source TEXT,
 received_date TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'قيد الاختبار',
 notes TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY(project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS test_catalog(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 code TEXT UNIQUE NOT NULL,
 name_ar TEXT NOT NULL,
 name_en TEXT,
 category TEXT NOT NULL,
 standard TEXT NOT NULL,
 version TEXT,
 active INTEGER NOT NULL DEFAULT 1,
 input_schema TEXT,
 result_schema TEXT,
 notes TEXT
);

CREATE TABLE IF NOT EXISTS tests(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 test_no TEXT UNIQUE NOT NULL,
 sample_id INTEGER NOT NULL,
 catalog_id INTEGER NOT NULL,
 status TEXT NOT NULL DEFAULT 'مسودة',
 technician_id INTEGER,
 reviewer_id INTEGER,
 started_at TEXT,
 completed_at TEXT,
 approved_at TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY(sample_id) REFERENCES samples(id),
 FOREIGN KEY(catalog_id) REFERENCES test_catalog(id),
 FOREIGN KEY(technician_id) REFERENCES users(id),
 FOREIGN KEY(reviewer_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS test_data(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 test_id INTEGER NOT NULL,
 section TEXT NOT NULL,
 field_name TEXT NOT NULL,
 value_text TEXT,
 value_num REAL,
 unit TEXT,
 seq INTEGER DEFAULT 0,
 FOREIGN KEY(test_id) REFERENCES tests(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS proctor_points(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 test_id INTEGER NOT NULL,
 point_no INTEGER NOT NULL,
 moisture REAL NOT NULL,
 mold_soil_wet REAL NOT NULL,
 wet_density REAL,
 dry_density REAL,
 FOREIGN KEY(test_id) REFERENCES tests(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS proctor_results(
 test_id INTEGER PRIMARY KEY,
 mdd REAL NOT NULL,
 omc REAL NOT NULL,
 FOREIGN KEY(test_id) REFERENCES tests(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS equipment(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 name TEXT NOT NULL,
 serial_no TEXT,
 manufacturer TEXT,
 model TEXT,
 last_calibration TEXT,
 next_calibration TEXT,
 status TEXT NOT NULL DEFAULT 'ساري',
 certificate_no TEXT,
 notes TEXT
);

CREATE TABLE IF NOT EXISTS calibration_records(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 equipment_id INTEGER NOT NULL,
 calibration_date TEXT NOT NULL,
 next_due TEXT,
 certificate_no TEXT,
 provider TEXT,
 result TEXT NOT NULL DEFAULT 'مطابق',
 document_ref TEXT,
 notes TEXT,
 FOREIGN KEY(equipment_id) REFERENCES equipment(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS reports(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 report_no TEXT UNIQUE NOT NULL,
 test_id INTEGER NOT NULL,
 issued_at TEXT,
 status TEXT NOT NULL DEFAULT 'مسودة',
 approved_by INTEGER,
 FOREIGN KEY(test_id) REFERENCES tests(id),
 FOREIGN KEY(approved_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS audit_log(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 user_id INTEGER,
 action TEXT NOT NULL,
 entity TEXT,
 entity_id INTEGER,
 details TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS settings(
 key TEXT PRIMARY KEY,
 value TEXT
);

CREATE TABLE IF NOT EXISTS sync_queue(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 entity TEXT NOT NULL,
 entity_id INTEGER,
 operation TEXT NOT NULL,
 payload_json TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'queued',
 attempts INTEGER NOT NULL DEFAULT 0,
 last_error TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 sent_at TEXT
);

CREATE TABLE IF NOT EXISTS field_visits(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 license_no TEXT NOT NULL,
 contractor_name TEXT,
 project_name TEXT,
 sector_name TEXT,
 layer_no TEXT,
 location TEXT,
 latitude REAL,
 longitude REAL,
 tests_json TEXT NOT NULL DEFAULT '[]',
 notes TEXT,
 status TEXT NOT NULL DEFAULT 'مسودة',
 created_by INTEGER,
 project_id INTEGER,
 sample_id INTEGER,
 balady_permit_no TEXT,
 balady_municipality TEXT,
 balady_permit_type TEXT,
 balady_permit_status TEXT,
 balady_reference_url TEXT,
 reviewed_by INTEGER,
 reviewed_at TEXT,
 approved_by INTEGER,
 approved_at TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY(created_by) REFERENCES users(id),
 FOREIGN KEY(project_id) REFERENCES projects(id),
 FOREIGN KEY(sample_id) REFERENCES samples(id),
 FOREIGN KEY(reviewed_by) REFERENCES users(id),
 FOREIGN KEY(approved_by) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status);
CREATE INDEX IF NOT EXISTS idx_work_orders_project ON work_orders(project_id);
CREATE INDEX IF NOT EXISTS idx_work_orders_status ON work_orders(status);
CREATE INDEX IF NOT EXISTS idx_tests_sample ON tests(sample_id);
CREATE INDEX IF NOT EXISTS idx_tests_catalog ON tests(catalog_id);
CREATE INDEX IF NOT EXISTS idx_test_data_test ON test_data(test_id);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at);
CREATE INDEX IF NOT EXISTS idx_field_license ON field_visits(license_no);
CREATE INDEX IF NOT EXISTS idx_field_created ON field_visits(created_at);
CREATE INDEX IF NOT EXISTS idx_sync_queue_status ON sync_queue(status, created_at);

INSERT OR IGNORE INTO settings(key,value) VALUES('lab_name','مختبر أساس');

INSERT OR IGNORE INTO test_catalog(code,name_ar,name_en,category,standard,version,active) VALUES
('D1883','نسبة تحمل كاليفورنيا CBR','California Bearing Ratio','تربة','ASTM D1883','2024',1),
('D2216','محتوى الرطوبة','Water Content','تربة','ASTM D2216','2019',1),
('D4318','حدود أتربرج','Atterberg Limits','تربة','ASTM D4318','2018',1),
('C136','التحليل المنخلي','Sieve Analysis','ركام','ASTM C136','2019',1),
('D1557','بروكتور المعدل','Modified Proctor','تربة','ASTM D1557','2021',1),
('D698','بروكتور القياسي','Standard Proctor','تربة','ASTM D698','2021',1),
('C39','مقاومة الضغط للخرسانة','Compressive Strength','خرسانة','ASTM C39','2024',1),
('C143','اختبار الهطول','Slump','خرسانة','ASTM C143','2020',1),
('D2041','الوزن النوعي الأقصى للخلطة الإسفلتية Gmm','Maximum Specific Gravity','أسفلت','ASTM D2041','2022',1),
('D6132','سماكة الطلاء الجاف DFT','Dry Film Thickness','طلاءات','ASTM D6132','2022',1),
('D7091','قياس السماكة الجافة للطلاءات','Dry Film Thickness','طلاءات','ASTM D7091','2022',1),
('ROAD-PROFILER','بروفايل الطريق','Road Profiler','طرق','Road Profiler','1.0',1),
('GRB-ROUGHNESS','وعورة الأسفلت','Asphalt Roughness','طرق','GRB','1.0',1);
