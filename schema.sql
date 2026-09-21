PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS users(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 username TEXT UNIQUE NOT NULL,
 password_hash TEXT NOT NULL,
 full_name TEXT NOT NULL,
 role TEXT NOT NULL DEFAULT 'technician',
 phone TEXT,
 avatar_data_url TEXT,
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
 equipment_code TEXT,
 range_text TEXT,
 section TEXT,
 verification_status TEXT,
 maintenance_status TEXT,
 calibrated_to TEXT,
 service_date TEXT,
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

CREATE TABLE IF NOT EXISTS record_attachments(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 entity_type TEXT NOT NULL,
 entity_id INTEGER NOT NULL,
 original_name TEXT NOT NULL,
 stored_name TEXT NOT NULL UNIQUE,
 uploaded_by INTEGER,
 section TEXT,
 file_category TEXT,
 material_group TEXT NOT NULL DEFAULT 'أخرى',
 classification_status TEXT,
 mime_type TEXT,
 display_name TEXT,
 description TEXT,
 archived INTEGER NOT NULL DEFAULT 0,
 version_no INTEGER NOT NULL DEFAULT 1,
 previous_attachment_id INTEGER,
 updated_at TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY(uploaded_by) REFERENCES users(id),
 FOREIGN KEY(previous_attachment_id) REFERENCES record_attachments(id)
);
CREATE INDEX IF NOT EXISTS idx_record_attachments_entity ON record_attachments(entity_type,entity_id);

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

CREATE TABLE IF NOT EXISTS trash_items(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 entity_type TEXT NOT NULL,
 original_id INTEGER NOT NULL,
 label TEXT NOT NULL,
 payload_json TEXT NOT NULL,
 deleted_by INTEGER,
 deleted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY(deleted_by) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_trash_items_deleted_at ON trash_items(deleted_at);

-- Quality records are intentionally separate from technical operations.
CREATE TABLE IF NOT EXISTS quality_documents(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 category TEXT NOT NULL CHECK(category IN ('procedure','worksheet','admin_form')),
 code TEXT NOT NULL,
 title TEXT NOT NULL,
 revision TEXT,
 status TEXT NOT NULL DEFAULT 'ساري',
 owner TEXT,
 document_ref TEXT,
 notes TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS proficiency_tests(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 test_name TEXT NOT NULL,
 material TEXT,
 standard TEXT,
 provider TEXT,
 participation_date TEXT,
 result TEXT,
 z_score TEXT,
 report_ref TEXT,
 notes TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS quality_staff(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 full_name TEXT NOT NULL,
 job_title TEXT,
 specialty TEXT,
 experience_years TEXT,
 qualification_ref TEXT,
 cv_ref TEXT,
 active INTEGER NOT NULL DEFAULT 1,
 notes TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS catalog_resources(
 test_catalog_id INTEGER PRIMARY KEY,
 astm_attachment_id INTEGER,
 worksheet_attachment_id INTEGER,
 results_attachment_id INTEGER,
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY(test_catalog_id) REFERENCES test_catalog(id),
 FOREIGN KEY(astm_attachment_id) REFERENCES record_attachments(id),
 FOREIGN KEY(worksheet_attachment_id) REFERENCES record_attachments(id),
 FOREIGN KEY(results_attachment_id) REFERENCES record_attachments(id)
);

-- Draft-only WhatsApp outbox.  The application never posts to a group or
-- community automatically: a company administrator reviews and sends each
-- draft through the official WhatsApp Business channel.
CREATE TABLE IF NOT EXISTS whatsapp_drafts(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 draft_name TEXT,
 recipient_user_id INTEGER,
 related_entity TEXT NOT NULL,
 related_id INTEGER,
 target_name TEXT NOT NULL DEFAULT 'مجتمع مختبر أساس',
 message_text TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'draft',
 created_by INTEGER,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 reviewed_at TEXT,
 FOREIGN KEY(recipient_user_id) REFERENCES users(id),
 FOREIGN KEY(created_by) REFERENCES users(id)
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
CREATE INDEX IF NOT EXISTS idx_whatsapp_drafts_status ON whatsapp_drafts(status, created_at);

INSERT OR IGNORE INTO settings(key,value) VALUES('lab_name','مختبر أساس');
INSERT OR IGNORE INTO settings(key,value) VALUES('lab_name_en','ASAS Laboratory');
INSERT OR IGNORE INTO settings(key,value) VALUES('website_url','https://www.asaslab.com/');
INSERT OR IGNORE INTO settings(key,value) VALUES('support_email','info@asaslab.com');
INSERT OR IGNORE INTO settings(key,value) VALUES('currency','SAR');
INSERT OR IGNORE INTO settings(key,value) VALUES('report_prefix','AST-R-');
INSERT OR IGNORE INTO settings(key,value) VALUES('sample_prefix','AS-');
INSERT OR IGNORE INTO settings(key,value) VALUES('work_order_prefix','WO-');
INSERT OR IGNORE INTO settings(key,value) VALUES('timezone','Asia/Riyadh');
INSERT OR IGNORE INTO settings(key,value) VALUES('default_language','ar');
INSERT OR IGNORE INTO settings(key,value) VALUES('date_format','DD/MM/YYYY');
INSERT OR IGNORE INTO settings(key,value) VALUES('whatsapp_group_url','https://chat.whatsapp.com/LxqH7L6GorGEhMfUTYthgG?s=sh&p=a&mlu=4&ilr=4');
INSERT OR IGNORE INTO settings(key,value) VALUES('telegram_url','https://t.me/+xPEyC5xPw8w5MjE0');
INSERT OR IGNORE INTO settings(key,value) VALUES('map_provider','google');
INSERT OR IGNORE INTO settings(key,value) VALUES('max_attachment_mb','25');
INSERT OR IGNORE INTO settings(key,value) VALUES('enable_otp','true');
INSERT OR IGNORE INTO settings(key,value) VALUES('require_report_approval','true');

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


-- V9 additive operational modules. Existing ASAS tables remain unchanged.
CREATE TABLE IF NOT EXISTS inventory_items(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 item_code TEXT UNIQUE,
 name TEXT NOT NULL,
 category TEXT,
 quantity REAL NOT NULL DEFAULT 0 CHECK(quantity >= 0),
 min_quantity REAL NOT NULL DEFAULT 0,
 unit TEXT,
 location TEXT,
 notes TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at TEXT
);

CREATE TABLE IF NOT EXISTS order_requests(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 request_no TEXT UNIQUE,
 request_type TEXT NOT NULL DEFAULT 'general',
 title TEXT NOT NULL,
 description TEXT,
 status TEXT NOT NULL DEFAULT 'pending',
 requested_by INTEGER,
 reviewed_by INTEGER,
 approved_by INTEGER,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 reviewed_at TEXT,
 approved_at TEXT,
 FOREIGN KEY(requested_by) REFERENCES users(id),
 FOREIGN KEY(reviewed_by) REFERENCES users(id),
 FOREIGN KEY(approved_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS sample_result_entries(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 test_id INTEGER NOT NULL,
 field_name TEXT NOT NULL,
 value_num REAL,
 value_text TEXT,
 unit TEXT,
 min_value REAL,
 max_value REAL,
 compliance_status TEXT NOT NULL DEFAULT 'not_evaluated',
 entered_by INTEGER,
 approved_by INTEGER,
 approved_at TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY(test_id) REFERENCES tests(id) ON DELETE CASCADE,
 FOREIGN KEY(entered_by) REFERENCES users(id),
 FOREIGN KEY(approved_by) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_inventory_items_code ON inventory_items(item_code);
CREATE INDEX IF NOT EXISTS idx_order_requests_status ON order_requests(status);
CREATE INDEX IF NOT EXISTS idx_sample_result_entries_test ON sample_result_entries(test_id);


-- V9.3 laboratory quality and commercial expansion (additive only).
CREATE TABLE IF NOT EXISTS test_methods(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 catalog_id INTEGER NOT NULL,
 method_code TEXT NOT NULL,
 revision TEXT,
 effective_date TEXT,
 acceptance_min REAL,
 acceptance_max REAL,
 acceptance_unit TEXT,
 uncertainty_text TEXT,
 decision_rule TEXT,
 active INTEGER NOT NULL DEFAULT 1,
 notes TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY(catalog_id) REFERENCES test_catalog(id)
);

CREATE TABLE IF NOT EXISTS chain_of_custody(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 sample_id INTEGER NOT NULL,
 event_type TEXT NOT NULL,
 from_user INTEGER,
 to_user INTEGER,
 location TEXT,
 condition_text TEXT,
 notes TEXT,
 occurred_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY(sample_id) REFERENCES samples(id) ON DELETE CASCADE,
 FOREIGN KEY(from_user) REFERENCES users(id),
 FOREIGN KEY(to_user) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS nonconformities(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 ncr_no TEXT UNIQUE NOT NULL,
 source_type TEXT,
 source_id INTEGER,
 category TEXT,
 severity TEXT NOT NULL DEFAULT 'minor',
 description TEXT NOT NULL,
 immediate_action TEXT,
 root_cause TEXT,
 status TEXT NOT NULL DEFAULT 'open',
 owner_id INTEGER,
 due_date TEXT,
 closed_by INTEGER,
 closed_at TEXT,
 created_by INTEGER,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY(owner_id) REFERENCES users(id),
 FOREIGN KEY(closed_by) REFERENCES users(id),
 FOREIGN KEY(created_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS corrective_actions(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 ncr_id INTEGER,
 action_no TEXT UNIQUE,
 action_type TEXT NOT NULL DEFAULT 'corrective',
 description TEXT NOT NULL,
 owner_id INTEGER,
 due_date TEXT,
 effectiveness_check TEXT,
 effectiveness_result TEXT,
 status TEXT NOT NULL DEFAULT 'open',
 completed_at TEXT,
 verified_by INTEGER,
 verified_at TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY(ncr_id) REFERENCES nonconformities(id) ON DELETE CASCADE,
 FOREIGN KEY(owner_id) REFERENCES users(id),
 FOREIGN KEY(verified_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS training_records(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 user_id INTEGER NOT NULL,
 training_title TEXT NOT NULL,
 competency_area TEXT,
 provider TEXT,
 training_date TEXT,
 expiry_date TEXT,
 result TEXT,
 certificate_ref TEXT,
 authorization_scope TEXT,
 notes TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS environmental_monitoring(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 area TEXT NOT NULL,
 parameter TEXT NOT NULL,
 value_num REAL,
 unit TEXT,
 min_limit REAL,
 max_limit REAL,
 compliance_status TEXT NOT NULL DEFAULT 'not_evaluated',
 recorded_by INTEGER,
 recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 notes TEXT,
 FOREIGN KEY(recorded_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS maintenance_records(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 equipment_id INTEGER NOT NULL,
 maintenance_type TEXT NOT NULL,
 service_date TEXT NOT NULL,
 provider TEXT,
 description TEXT,
 parts_used TEXT,
 cost REAL,
 next_due TEXT,
 status TEXT NOT NULL DEFAULT 'completed',
 performed_by INTEGER,
 attachment_ref TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY(equipment_id) REFERENCES equipment(id) ON DELETE CASCADE,
 FOREIGN KEY(performed_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS suppliers(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 supplier_code TEXT UNIQUE,
 name TEXT NOT NULL,
 phone TEXT,
 email TEXT,
 scope TEXT,
 approval_status TEXT NOT NULL DEFAULT 'pending',
 rating REAL,
 last_review_date TEXT,
 notes TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS quotations(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 quotation_no TEXT UNIQUE NOT NULL,
 client_id INTEGER,
 project_id INTEGER,
 issue_date TEXT,
 valid_until TEXT,
 subtotal REAL NOT NULL DEFAULT 0,
 tax_amount REAL NOT NULL DEFAULT 0,
 total_amount REAL NOT NULL DEFAULT 0,
 currency TEXT NOT NULL DEFAULT 'SAR',
 status TEXT NOT NULL DEFAULT 'draft',
 created_by INTEGER,
 approved_by INTEGER,
 approved_at TEXT,
 notes TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY(client_id) REFERENCES clients(id),
 FOREIGN KEY(project_id) REFERENCES projects(id),
 FOREIGN KEY(created_by) REFERENCES users(id),
 FOREIGN KEY(approved_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS quotation_items(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 quotation_id INTEGER NOT NULL,
 catalog_id INTEGER,
 description TEXT NOT NULL,
 quantity REAL NOT NULL DEFAULT 1,
 unit_price REAL NOT NULL DEFAULT 0,
 discount REAL NOT NULL DEFAULT 0,
 line_total REAL NOT NULL DEFAULT 0,
 FOREIGN KEY(quotation_id) REFERENCES quotations(id) ON DELETE CASCADE,
 FOREIGN KEY(catalog_id) REFERENCES test_catalog(id)
);

CREATE TABLE IF NOT EXISTS contracts(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 contract_no TEXT UNIQUE NOT NULL,
 client_id INTEGER,
 project_id INTEGER,
 title TEXT NOT NULL,
 start_date TEXT,
 end_date TEXT,
 value REAL,
 currency TEXT NOT NULL DEFAULT 'SAR',
 status TEXT NOT NULL DEFAULT 'active',
 document_ref TEXT,
 notes TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY(client_id) REFERENCES clients(id),
 FOREIGN KEY(project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS customer_complaints(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 complaint_no TEXT UNIQUE NOT NULL,
 client_id INTEGER,
 project_id INTEGER,
 subject TEXT NOT NULL,
 description TEXT NOT NULL,
 priority TEXT NOT NULL DEFAULT 'normal',
 status TEXT NOT NULL DEFAULT 'open',
 owner_id INTEGER,
 resolution TEXT,
 closed_at TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY(client_id) REFERENCES clients(id),
 FOREIGN KEY(project_id) REFERENCES projects(id),
 FOREIGN KEY(owner_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_test_methods_catalog ON test_methods(catalog_id,active);
CREATE INDEX IF NOT EXISTS idx_coc_sample ON chain_of_custody(sample_id,occurred_at);
CREATE INDEX IF NOT EXISTS idx_ncr_status ON nonconformities(status,due_date);
CREATE INDEX IF NOT EXISTS idx_capa_ncr ON corrective_actions(ncr_id,status);
CREATE INDEX IF NOT EXISTS idx_training_user ON training_records(user_id,expiry_date);
CREATE INDEX IF NOT EXISTS idx_environment_area ON environmental_monitoring(area,recorded_at);
CREATE INDEX IF NOT EXISTS idx_maintenance_equipment ON maintenance_records(equipment_id,service_date);
CREATE INDEX IF NOT EXISTS idx_quotation_client ON quotations(client_id,status);
CREATE INDEX IF NOT EXISTS idx_contract_client ON contracts(client_id,status);
CREATE INDEX IF NOT EXISTS idx_complaint_status ON customer_complaints(status,priority);

INSERT OR IGNORE INTO settings(key,value) VALUES('require_test_review','true');
INSERT OR IGNORE INTO settings(key,value) VALUES('require_result_approval','true');
INSERT OR IGNORE INTO settings(key,value) VALUES('enable_chain_of_custody','true');
INSERT OR IGNORE INTO settings(key,value) VALUES('enable_ncr_capa','true');
INSERT OR IGNORE INTO settings(key,value) VALUES('enable_environment_monitoring','true');
INSERT OR IGNORE INTO settings(key,value) VALUES('enable_training_competency','true');
INSERT OR IGNORE INTO settings(key,value) VALUES('enable_inventory_alerts','true');
INSERT OR IGNORE INTO settings(key,value) VALUES('enable_calibration_alerts','true');
INSERT OR IGNORE INTO settings(key,value) VALUES('enable_customer_complaints','true');
INSERT OR IGNORE INTO settings(key,value) VALUES('tax_rate','15');

-- V10.3 integrated quality planning.
CREATE TABLE IF NOT EXISTS quality_swot(id INTEGER PRIMARY KEY AUTOINCREMENT,quadrant TEXT NOT NULL CHECK(quadrant IN ('strength','weakness','opportunity','threat')),title TEXT NOT NULL,description TEXT,owner_id INTEGER,status TEXT NOT NULL DEFAULT 'active',created_by INTEGER,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,FOREIGN KEY(owner_id) REFERENCES users(id),FOREIGN KEY(created_by) REFERENCES users(id));
CREATE TABLE IF NOT EXISTS quality_risks(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT NOT NULL,category TEXT,probability INTEGER NOT NULL DEFAULT 1 CHECK(probability BETWEEN 1 AND 5),impact INTEGER NOT NULL DEFAULT 1 CHECK(impact BETWEEN 1 AND 5),mitigation TEXT,owner_id INTEGER,due_date TEXT,status TEXT NOT NULL DEFAULT 'open',created_by INTEGER,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,FOREIGN KEY(owner_id) REFERENCES users(id),FOREIGN KEY(created_by) REFERENCES users(id));
CREATE TABLE IF NOT EXISTS quality_kpis(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,unit TEXT,target REAL NOT NULL DEFAULT 0,actual REAL NOT NULL DEFAULT 0,period TEXT,owner_id INTEGER,status TEXT NOT NULL DEFAULT 'active',created_by INTEGER,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,FOREIGN KEY(owner_id) REFERENCES users(id),FOREIGN KEY(created_by) REFERENCES users(id));
CREATE TABLE IF NOT EXISTS quality_actions(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT NOT NULL,source_type TEXT NOT NULL DEFAULT 'improvement',source_id INTEGER,description TEXT,owner_id INTEGER,due_date TEXT,result_text TEXT,effectiveness TEXT,status TEXT NOT NULL DEFAULT 'open',created_by INTEGER,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,completed_at TEXT,FOREIGN KEY(owner_id) REFERENCES users(id),FOREIGN KEY(created_by) REFERENCES users(id));
CREATE INDEX IF NOT EXISTS idx_quality_risks_status ON quality_risks(status,due_date);
CREATE INDEX IF NOT EXISTS idx_quality_actions_status ON quality_actions(status,due_date);

-- V10.4 management review and continual-improvement workflow.
CREATE TABLE IF NOT EXISTS quality_cycles(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  objective TEXT,
  owner_id INTEGER,
  start_date TEXT,
  due_date TEXT,
  baseline REAL NOT NULL DEFAULT 0,
  target REAL NOT NULL DEFAULT 0,
  result REAL NOT NULL DEFAULT 0,
  current_stage INTEGER NOT NULL DEFAULT 1 CHECK(current_stage BETWEEN 1 AND 9),
  status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','completed','cancelled')),
  created_by INTEGER,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  completed_at TEXT,
  FOREIGN KEY(owner_id) REFERENCES users(id),
  FOREIGN KEY(created_by) REFERENCES users(id)
);
CREATE TABLE IF NOT EXISTS quality_cycle_steps(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cycle_id INTEGER NOT NULL,
  stage INTEGER NOT NULL CHECK(stage BETWEEN 1 AND 9),
  title TEXT NOT NULL,
  notes TEXT,
  decision TEXT,
  details_json TEXT NOT NULL DEFAULT '{}',
  owner_id INTEGER,
  due_date TEXT,
  status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','active','completed')),
  completed_by INTEGER,
  completed_at TEXT,
  UNIQUE(cycle_id,stage),
  FOREIGN KEY(cycle_id) REFERENCES quality_cycles(id) ON DELETE CASCADE,
  FOREIGN KEY(owner_id) REFERENCES users(id),
  FOREIGN KEY(completed_by) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_quality_cycles_status ON quality_cycles(status,due_date);
CREATE INDEX IF NOT EXISTS idx_quality_cycle_steps ON quality_cycle_steps(cycle_id,stage,status);

CREATE TABLE IF NOT EXISTS operational_tasks(
  id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT NOT NULL,description TEXT,
  source_type TEXT NOT NULL DEFAULT 'manual',source_id INTEGER,project_id INTEGER,
  assigned_to INTEGER,priority TEXT NOT NULL DEFAULT 'متوسطة' CHECK(priority IN ('منخفضة','متوسطة','عالية','حرجة')),
  status TEXT NOT NULL DEFAULT 'جديدة' CHECK(status IN ('جديدة','قيد التنفيذ','مكتملة','مؤجلة')),
  due_date TEXT,created_by INTEGER NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,completed_at TEXT,
  FOREIGN KEY(project_id) REFERENCES projects(id),FOREIGN KEY(assigned_to) REFERENCES users(id),FOREIGN KEY(created_by) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_operational_tasks_status ON operational_tasks(status,due_date,priority);
