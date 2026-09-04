package sa.asas.lims

import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import java.text.SimpleDateFormat
import java.util.*
import org.json.JSONObject

class LimsDb(ctx: Context) : SQLiteOpenHelper(ctx, "lims_asas_v5.db", null, 6) {
    private val now: String get() = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US).format(Date())

    override fun onCreate(d: SQLiteDatabase) {
        createSchema(d)
        createEnhancedSchema(d)
        seed(d)
    }

    override fun onOpen(d: SQLiteDatabase) {
        super.onOpen(d)
        // Idempotent hardening: also applies the enhanced schema to existing V5 installations.
        createEnhancedSchema(d)
    }

    private fun createEnhancedSchema(d: SQLiteDatabase) {
        d.execSQL("CREATE TABLE IF NOT EXISTS attachments(id INTEGER PRIMARY KEY AUTOINCREMENT,entity TEXT NOT NULL,entity_id TEXT NOT NULL,file_name TEXT NOT NULL,file_path TEXT NOT NULL,sha256 TEXT,uploaded_by INTEGER,created_at TEXT NOT NULL)")
        d.execSQL("CREATE TABLE IF NOT EXISTS report_signatures(id INTEGER PRIMARY KEY AUTOINCREMENT,report_id INTEGER NOT NULL,user_id INTEGER NOT NULL,signature_type TEXT NOT NULL,signature_hash TEXT NOT NULL,signed_at TEXT NOT NULL)")
        d.execSQL("CREATE TABLE IF NOT EXISTS calibration_records(id INTEGER PRIMARY KEY AUTOINCREMENT,equipment_id INTEGER NOT NULL,certificate_no TEXT,calibration_date TEXT,due_date TEXT,result TEXT,certificate_path TEXT,created_by INTEGER,created_at TEXT NOT NULL)")
        d.execSQL("CREATE TABLE IF NOT EXISTS method_versions(id INTEGER PRIMARY KEY AUTOINCREMENT,test_code TEXT NOT NULL,standard TEXT NOT NULL,version TEXT NOT NULL,effective_date TEXT,document_ref TEXT,active INTEGER DEFAULT 1,created_at TEXT NOT NULL)")
        d.execSQL("CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,title TEXT,message TEXT,type TEXT,read_at TEXT,created_at TEXT NOT NULL)")
        d.execSQL("CREATE TABLE IF NOT EXISTS sync_conflicts(id INTEGER PRIMARY KEY AUTOINCREMENT,entity TEXT,entity_id TEXT,local_payload TEXT,remote_payload TEXT,resolution TEXT,status TEXT DEFAULT 'OPEN',created_at TEXT NOT NULL,resolved_at TEXT)")
        d.execSQL("CREATE TABLE IF NOT EXISTS login_events(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,username TEXT,event TEXT,ip_or_device TEXT,created_at TEXT NOT NULL)")
        d.execSQL("CREATE INDEX IF NOT EXISTS idx_samples_project ON samples(project_id)")
        d.execSQL("CREATE INDEX IF NOT EXISTS idx_tests_sample ON tests(sample_no)")
        d.execSQL("CREATE INDEX IF NOT EXISTS idx_reports_sample ON reports(sample_no)")
        d.execSQL("CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at)")
        d.execSQL("CREATE INDEX IF NOT EXISTS idx_sync_status ON sync_queue(status)")
        d.execSQL("CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id,read_at)")
        try { d.execSQL("ALTER TABLE sync_queue ADD COLUMN base_version INTEGER") } catch (_: Exception) { }
    }

    private fun createSchema(d: SQLiteDatabase) {
        d.execSQL("CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,username TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,salt TEXT NOT NULL,full_name TEXT NOT NULL,role TEXT NOT NULL,phone TEXT,active INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL)")
        d.execSQL("CREATE TABLE IF NOT EXISTS clients(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,phone TEXT,email TEXT,vat_no TEXT,address TEXT,created_at TEXT NOT NULL)")
        d.execSQL("CREATE TABLE IF NOT EXISTS suppliers(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,phone TEXT,email TEXT,vat_no TEXT,active INTEGER DEFAULT 1,created_at TEXT NOT NULL)")
        d.execSQL("CREATE TABLE IF NOT EXISTS projects(id INTEGER PRIMARY KEY AUTOINCREMENT,code TEXT UNIQUE,name TEXT NOT NULL,location TEXT,client_id INTEGER,consultant TEXT,contractor TEXT,status TEXT DEFAULT 'نشط',created_at TEXT NOT NULL)")
        d.execSQL("CREATE TABLE IF NOT EXISTS quotations(id INTEGER PRIMARY KEY AUTOINCREMENT,quote_no TEXT UNIQUE,client_id INTEGER,project_id INTEGER,amount REAL,status TEXT,created_at TEXT NOT NULL)")
        d.execSQL("CREATE TABLE IF NOT EXISTS contracts(id INTEGER PRIMARY KEY AUTOINCREMENT,contract_no TEXT UNIQUE,client_id INTEGER,project_id INTEGER,amount REAL,start_date TEXT,end_date TEXT,status TEXT,created_at TEXT NOT NULL)")
        d.execSQL("CREATE TABLE IF NOT EXISTS customer_requests(id INTEGER PRIMARY KEY AUTOINCREMENT,request_no TEXT UNIQUE,client_id INTEGER,project_id INTEGER,description TEXT,status TEXT,created_at TEXT NOT NULL)")
        d.execSQL("CREATE TABLE IF NOT EXISTS work_orders(id INTEGER PRIMARY KEY AUTOINCREMENT,wo_no TEXT UNIQUE,project_id INTEGER,requested_by INTEGER,priority TEXT,status TEXT,assigned_to INTEGER,created_at TEXT NOT NULL)")
        d.execSQL("CREATE TABLE IF NOT EXISTS samples(id INTEGER PRIMARY KEY AUTOINCREMENT,sample_no TEXT UNIQUE NOT NULL,project_id INTEGER,material TEXT,source TEXT,location TEXT,gps TEXT,status TEXT,storage_location TEXT,collected_at TEXT,received_at TEXT,created_by INTEGER,created_at TEXT NOT NULL)")
        d.execSQL("CREATE TABLE IF NOT EXISTS tests_catalog(code TEXT PRIMARY KEY,name TEXT NOT NULL,category TEXT,standard TEXT,version TEXT,unit TEXT,active INTEGER DEFAULT 1)")
        d.execSQL("CREATE TABLE IF NOT EXISTS test_assignments(id INTEGER PRIMARY KEY AUTOINCREMENT,test_id INTEGER,technician_id INTEGER,status TEXT,assigned_at TEXT,completed_at TEXT)")
        d.execSQL("CREATE TABLE IF NOT EXISTS tests(id INTEGER PRIMARY KEY AUTOINCREMENT,code TEXT NOT NULL,sample_no TEXT NOT NULL,technician_id INTEGER,result TEXT,raw_data TEXT,decision TEXT,status TEXT DEFAULT 'Draft',created_at TEXT NOT NULL,updated_at TEXT NOT NULL)")
        d.execSQL("CREATE TABLE IF NOT EXISTS result_limits(id INTEGER PRIMARY KEY AUTOINCREMENT,test_code TEXT,min_value REAL,max_value REAL,unit TEXT,version TEXT,active INTEGER DEFAULT 1)")
        d.execSQL("CREATE TABLE IF NOT EXISTS reports(id INTEGER PRIMARY KEY AUTOINCREMENT,report_no TEXT UNIQUE,test_code TEXT,sample_no TEXT,result TEXT,status TEXT DEFAULT 'Draft',reviewed_by INTEGER,approved_by INTEGER,created_at TEXT NOT NULL,approved_at TEXT)")
        d.execSQL("CREATE TABLE IF NOT EXISTS report_versions(id INTEGER PRIMARY KEY AUTOINCREMENT,report_id INTEGER,version_no INTEGER,pdf_path TEXT,created_by INTEGER,created_at TEXT NOT NULL)")
        d.execSQL("CREATE TABLE IF NOT EXISTS equipment(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT,serial_no TEXT UNIQUE,next_calibration TEXT,status TEXT,location TEXT,last_maintenance TEXT,created_at TEXT NOT NULL)")
        d.execSQL("CREATE TABLE IF NOT EXISTS equipment_movements(id INTEGER PRIMARY KEY AUTOINCREMENT,equipment_id INTEGER,from_location TEXT,to_location TEXT,moved_by INTEGER,moved_at TEXT NOT NULL)")
        d.execSQL("CREATE TABLE IF NOT EXISTS storage_locations(id INTEGER PRIMARY KEY AUTOINCREMENT,code TEXT UNIQUE,name TEXT,temperature TEXT,capacity INTEGER,active INTEGER DEFAULT 1)")
        d.execSQL("CREATE TABLE IF NOT EXISTS ncr(id INTEGER PRIMARY KEY AUTOINCREMENT,ncr_no TEXT UNIQUE,project_id INTEGER,sample_no TEXT,description TEXT,root_cause TEXT,corrective_action TEXT,status TEXT,created_by INTEGER,created_at TEXT NOT NULL,closed_at TEXT)")
        d.execSQL("CREATE TABLE IF NOT EXISTS invoices(id INTEGER PRIMARY KEY AUTOINCREMENT,invoice_no TEXT UNIQUE,client_id INTEGER,amount REAL,vat REAL,total REAL,status TEXT,created_at TEXT NOT NULL)")
        d.execSQL("CREATE TABLE IF NOT EXISTS complaints(id INTEGER PRIMARY KEY AUTOINCREMENT,complaint_no TEXT UNIQUE,client_id INTEGER,description TEXT,status TEXT,created_at TEXT NOT NULL)")
        d.execSQL("CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,action TEXT,entity TEXT,entity_id TEXT,details TEXT,created_at TEXT NOT NULL)")
        d.execSQL("CREATE TABLE IF NOT EXISTS otp_challenges(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,code_hash TEXT,expires_at INTEGER,used INTEGER DEFAULT 0,created_at TEXT NOT NULL)")
        d.execSQL("CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT)")
        d.execSQL("CREATE TABLE IF NOT EXISTS sync_queue(id INTEGER PRIMARY KEY AUTOINCREMENT,entity TEXT,entity_id TEXT,operation TEXT,payload TEXT,status TEXT DEFAULT 'PENDING',attempts INTEGER DEFAULT 0,last_error TEXT,created_at TEXT NOT NULL)")
        d.execSQL("CREATE TABLE IF NOT EXISTS permissions(role TEXT,permission TEXT,PRIMARY KEY(role,permission))")
        d.execSQL("CREATE TABLE IF NOT EXISTS excavation_licenses(id INTEGER PRIMARY KEY AUTOINCREMENT,license_no TEXT UNIQUE NOT NULL,work_order_no TEXT,project_name TEXT,service_entity TEXT,municipality TEXT,district TEXT,contractor TEXT,consultant TEXT,start_at TEXT,end_at TEXT,permit_type TEXT,permit_status TEXT,excavation_status TEXT,location TEXT,gps TEXT,notes TEXT,source TEXT DEFAULT 'بلدي',created_by INTEGER,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)")
        d.execSQL("CREATE INDEX IF NOT EXISTS idx_exc_license_no ON excavation_licenses(license_no)")
        d.execSQL("CREATE INDEX IF NOT EXISTS idx_exc_work_order ON excavation_licenses(work_order_no)")
        d.execSQL("CREATE INDEX IF NOT EXISTS idx_exc_status ON excavation_licenses(permit_status,excavation_status)")
    }

    private fun seed(d: SQLiteDatabase) {
        val salt = SecurityUtil.salt(); val hash = SecurityUtil.hash(UUID.randomUUID().toString(), salt)
        d.execSQL("INSERT INTO users(username,password_hash,salt,full_name,role,phone,active,created_at) VALUES(?,?,?,?,?,?,1,?)", arrayOf("admin",hash,salt,"مدير النظام","admin","",now))
        val roles = mapOf(
            "admin" to listOf("*") ,
            "reviewer" to listOf("reports.review","reports.approve","samples.view","tests.view","tests.result"),
            "technician" to listOf("samples.view","samples.create","tests.view","tests.result"),
            "user" to listOf("samples.view","samples.create","reports.view")
        )
        roles.forEach { (r, ps) -> ps.forEach { p -> d.execSQL("INSERT INTO permissions(role,permission) VALUES(?,?)", arrayOf(r,p)) } }
        val tests = listOf(
            "التربة|ASTM D1557|Modified Proctor|ASTM D1557|%/g/cm3", "التربة|ASTM D698|Standard Proctor|ASTM D698|%/g/cm3", "التربة|ASTM D1883|California Bearing Ratio (CBR)|ASTM D1883|%", "التربة|ASTM D2216|Moisture Content|ASTM D2216|%", "التربة|ASTM D4318|Atterberg Limits|ASTM D4318|%", "التربة|ASTM C136/C136M|Sieve Analysis|ASTM C136/C136M|%", "التربة|ASTM D6913|Particle-Size Distribution|ASTM D6913|%", "التربة|ASTM D854|Specific Gravity of Soil Solids|ASTM D854|-", "التربة|ASTM D1140|Material Finer Than 75 µm by Washing|ASTM D1140|%", "التربة|ASTM D1556|Sand Cone Density|ASTM D1556|%", "التربة|ASTM D6938|Nuclear Density Gauge|ASTM D6938|%",
            "الخرسانة|ASTM C39|Compressive Strength|ASTM C39|MPa", "الخرسانة|ASTM C143|Slump|ASTM C143|mm", "الخرسانة|ASTM C31|Making and Curing Specimens|ASTM C31|-", "الخرسانة|ASTM C42|Concrete Cores|ASTM C42|MPa", "الخرسانة|ASTM C496|Splitting Tensile Strength|ASTM C496|MPa", "الخرسانة|ASTM C78|Flexural Strength|ASTM C78|MPa", "الخرسانة|ASTM C597|Ultrasonic Pulse Velocity|ASTM C597|km/s", "الخرسانة|ASTM C805|Rebound Hammer|ASTM C805|MPa", "الخرسانة|ASTM C642|Density/Absorption/Voids|ASTM C642|%", "الخرسانة|Carbonation|Concrete Carbonation|Internal|mm", "الخرسانة|Rebar Corrosion|Rebar Corrosion Test|Internal|mV",
            "الاسفلت|ASTM D2041|Maximum Specific Gravity (GMM)|ASTM D2041|g/cm3", "الاسفلت|ASTM D2726|Bulk Specific Gravity (Gmb)|ASTM D2726|g/cm3", "الاسفلت|ASTM D6927|Marshall Stability and Flow|ASTM D6927|kN/mm", "الاسفلت|ASTM D3203|Air Voids|ASTM D3203|%", "الاسفلت|ASTM D979|Sampling Asphalt Mixtures|ASTM D979|-", "الاسفلت|ASTM D6307|Asphalt Content by Ignition|ASTM D6307|%", "الاسفلت|ASTM D2172|Extraction of Bitumen|ASTM D2172|%", "الاسفلت|ASTM D5444|Gradation of Extracted Aggregate|ASTM D5444|%", "الاسفلت|ASTM D5|Penetration|ASTM D5|0.1 mm", "الاسفلت|ASTM D36|Softening Point|ASTM D36|°C", "الاسفلت|ASTM D113|Ductility|ASTM D113|cm", "الاسفلت|ASTM D70|Specific Gravity of Bituminous Materials|ASTM D70|-", "الاسفلت|ASTM D6132|Coating Thickness|ASTM D6132|µm", "الاسفلت|ASTM D7091|Coating Thickness|ASTM D7091|µm", "الاسفلت|Road Profiler|Road Roughness / IRI|Internal|m/km", "الاسفلت|GRB|Road Roughness / IRI|Internal|m/km",
            "أخرى|ASTM C29|Unit Weight of Aggregate|ASTM C29|kg/m3", "أخرى|ASTM C127|Specific Gravity Coarse Aggregate|ASTM C127|-", "أخرى|ASTM C128|Specific Gravity Fine Aggregate|ASTM C128|-", "أخرى|Fiber Pipe|Fiber Pipe Tests|Internal|-"
        )
        tests.forEach { s -> val p=s.split("|"); d.execSQL("INSERT INTO tests_catalog(code,name,category,standard,version,unit) VALUES(?,?,?,?,?,?)", arrayOf(p[1],p[2],p[0],p[3],"Current",p[4])) }
        listOf("LAB-01|مختبر رئيسي|18-25°C|100","STORE-A|مخزن العينات A|18-25°C|500").forEach { s -> val p=s.split("|"); d.execSQL("INSERT INTO storage_locations(code,name,temperature,capacity) VALUES(?,?,?,?)",arrayOf(p[0],p[1],p[2],p[3])) }
        d.execSQL("INSERT INTO settings(key,value) VALUES('organization','مختبر أساس')")
        d.execSQL("INSERT INTO settings(key,value) VALUES('sms_provider','NOT_CONFIGURED')")
        d.execSQL("INSERT INTO settings(key,value) VALUES('central_api','')")
        d.execSQL("INSERT INTO settings(key,value) VALUES('initial_setup_required','1')")
        d.execSQL("INSERT OR IGNORE INTO excavation_licenses(license_no,work_order_no,project_name,service_entity,municipality,district,contractor,consultant,start_at,end_at,permit_type,permit_status,excavation_status,location,gps,notes,source,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", arrayOf("480224898026","0890163418","مشروع تنفيذ خدمات المياه والصرف الصحي من خلال تنفيذ التوصيلات المنزلية بمنطقة القصيم إيصال الثاني","شركة المياه الوطنية","بلدية الرس","الشهداء","شركة سعد بن فهد الحربي للمقاولات","بيت الخبرة للاستشارات الهندسية","2026/07/23 23:30:00","2026/09/05 23:30:00","إصدار تصريح حفرية توصيلة مباني مفردة","معدل","تم التمديد","","","بيانات مرجعية تم إدخالها من التصريح الذي تمت معاينته في منصة بلدي","بلدي",1,now,now))
    }

    override fun onUpgrade(d: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
        if (oldVersion < 5) {
            val legacy = d.rawQuery("SELECT name FROM sqlite_master WHERE type='table' AND name='users'",null).use{it.moveToFirst()}
            if (legacy) {
                // Preserve existing V4 data where possible, then add the V5 schema.
                val oldUsers = mutableListOf<Array<String?>>()
                try { d.rawQuery("SELECT username,password,full_name,role,phone,active FROM users",null).use{c->while(c.moveToNext()) oldUsers.add(arrayOf(c.getString(0),c.getString(1),c.getString(2),c.getString(3),c.getString(4),c.getString(5)))} } catch(_:Exception){}
                d.execSQL("ALTER TABLE users RENAME TO users_v4")
                createSchema(d)
                oldUsers.forEach { u -> val salt=SecurityUtil.salt(); val h=SecurityUtil.hash(u[1] ?: "",salt); try { d.execSQL("INSERT OR IGNORE INTO users(username,password_hash,salt,full_name,role,phone,active,created_at) VALUES(?,?,?,?,?,?,?,?)",arrayOf(u[0],h,salt,u[2],u[3],u[4],u[5]?.toIntOrNull()?:1,now)) } catch(_:Exception){} }
                d.execSQL("DROP TABLE users_v4")
            } else createSchema(d)
        }
        if (oldVersion < 6) {
            createEnhancedSchema(d)
        }
    }

    fun login(usernameOrPhone:String,password:String): Array<String?>? {
        return readableDatabase.rawQuery("SELECT id,username,password_hash,salt,full_name,role,phone FROM users WHERE (username=? OR phone=?) AND active=1",arrayOf(usernameOrPhone,usernameOrPhone)).use { c ->
            if(!c.moveToFirst()) null else if(SecurityUtil.hash(password,c.getString(3)) == c.getString(2)) arrayOf(c.getString(0),c.getString(1),c.getString(4),c.getString(5),c.getString(6)) else null
        }
    }
    fun userRows()=query("SELECT id,username,full_name,role,COALESCE(phone,''),active FROM users ORDER BY id")
    fun userIdByUsername(username:String):Int = readableDatabase.rawQuery(
        "SELECT id FROM users WHERE username=? LIMIT 1", arrayOf(username)
    ).use { cursor -> if(cursor.moveToFirst()) cursor.getInt(0) else 0 }
    fun addUser(username:String,password:String,fullName:String,role:String,phone:String){ val s=SecurityUtil.salt(); writableDatabase.execSQL("INSERT INTO users(username,password_hash,salt,full_name,role,phone,active,created_at) VALUES(?,?,?,?,?,?,1,?)",arrayOf(username,SecurityUtil.hash(password,s),s,fullName,role,phone,now)); }
    fun deleteUser(id:Int){writableDatabase.execSQL("DELETE FROM users WHERE id=? AND username<>'admin'",arrayOf(id))}
    fun updateUserPhone(username:String,phone:String){writableDatabase.execSQL("UPDATE users SET phone=? WHERE username=?",arrayOf(phone,username))}
    fun completeInitialSetup(password:String,phone:String){val salt=SecurityUtil.salt();writableDatabase.execSQL("UPDATE users SET password_hash=?,salt=?,phone=? WHERE username='admin'",arrayOf(SecurityUtil.hash(password,salt),salt,phone));setSetting("initial_setup_required","0")}
    fun createOtp(userId:Int,code:String):Long { val h=SecurityUtil.hash(code,"OTP-ASAS"); val exp=System.currentTimeMillis()+5*60*1000; return writableDatabase.insert("otp_challenges",null,android.content.ContentValues().apply{put("user_id",userId);put("code_hash",h);put("expires_at",exp);put("created_at",now)}) }
    fun verifyOtp(userId:Int,code:String):Boolean { val c=readableDatabase.rawQuery("SELECT id,code_hash,expires_at FROM otp_challenges WHERE user_id=? AND used=0 ORDER BY id DESC LIMIT 1",arrayOf(userId.toString())); c.use{ if(!it.moveToFirst())return false; val ok=System.currentTimeMillis()<=it.getLong(2)&&SecurityUtil.hash(code,"OTP-ASAS")==it.getString(1); if(ok) writableDatabase.execSQL("UPDATE otp_challenges SET used=1 WHERE id=?",arrayOf(it.getInt(0))); return ok } }
    fun audit(userId:Int,action:String,entity:String,entityId:String="",details:String=""){writableDatabase.execSQL("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",arrayOf(userId,action,entity,entityId,details,now))}
    fun hasPermission(role:String,p:String)=role=="admin"||readableDatabase.rawQuery("SELECT 1 FROM permissions WHERE role=? AND (permission=? OR permission='*') LIMIT 1",arrayOf(role,p)).use{it.moveToFirst()}
    fun addClient(n:String,p:String,e:String="",vat:String="",addr:String=""){writableDatabase.execSQL("INSERT INTO clients(name,phone,email,vat_no,address,created_at) VALUES(?,?,?,?,?,?)",arrayOf(n,p,e,vat,addr,now))}
    fun addProject(n:String,l:String,client:Int?=null,consultant:String="",contractor:String=""){val code="PR-"+System.currentTimeMillis().toString().takeLast(7);writableDatabase.execSQL("INSERT INTO projects(code,name,location,client_id,consultant,contractor,status,created_at) VALUES(?,?,?,?,?,?,?,?)",arrayOf(code,n,l,client,consultant,contractor,"نشط",now))}
    private fun enqueue(entity:String,id:String,op:String,payload:JSONObject){writableDatabase.insert("sync_queue",null,android.content.ContentValues().apply{put("entity",entity);put("entity_id",id);put("operation",op);put("payload",payload.toString());put("status","PENDING");put("created_at",now)})}
    fun addSample(no:String,m:String,s:String,project:Int?=null,gps:String=""){writableDatabase.execSQL("INSERT OR REPLACE INTO samples(sample_no,project_id,material,source,gps,status,created_at) VALUES(?,?,?,?,?,'مستلمة',?)",arrayOf(no,project,m,s,gps,now));enqueue("sample",no,"UPSERT",JSONObject().put("sampleNo",no).put("material",m).put("source",s).put("projectId",project).put("gps",gps).put("status","مستلمة"))}
    fun addTest(code:String,sample:String,result:String,userId:Int=0,raw:String="",decision:String="غير محدد"){val t=writableDatabase.insert("tests",null,android.content.ContentValues().apply{put("code",code);put("sample_no",sample);put("technician_id",userId);put("result",result);put("raw_data",raw);put("decision",decision);put("status","Submitted");put("created_at",now);put("updated_at",now)});val rn="AST-R-"+System.currentTimeMillis().toString().takeLast(8);val rid=writableDatabase.insert("reports",null,android.content.ContentValues().apply{put("report_no",rn);put("test_code",code);put("sample_no",sample);put("result",result);put("status","Draft");put("created_at",now)});audit(userId,"CREATE","TEST",t.toString(),code+" / "+sample);enqueue("test",t.toString(),"CREATE",JSONObject().put("code",code).put("sampleNo",sample).put("result",result).put("rawData",raw).put("decision",decision).put("technicianId",userId));rid}
    fun getReport(no:String)=query("SELECT report_no,test_code,sample_no,result,status,created_at,approved_at FROM reports WHERE report_no='${no.replace("'","''")}' LIMIT 1").firstOrNull()
    fun reportRows()=query("SELECT report_no,test_code,sample_no,result,status,created_at,approved_at FROM reports ORDER BY id DESC")
    fun approveReport(no:String,userId:Int){
        val status=getReport(no)?.getOrNull(4) ?: return
        if(status != "Reviewed") return
        writableDatabase.execSQL("UPDATE reports SET status='Approved',approved_by=?,approved_at=? WHERE report_no=?",arrayOf(userId,now,no))
        audit(userId,"APPROVE","REPORT",no,"Final report approved after review")
        enqueue("report",no,"UPDATE",JSONObject().put("reportNo",no).put("status","Approved").put("approvedBy",userId))
    }
    fun reviewReport(no:String,userId:Int){
        val status=getReport(no)?.getOrNull(4) ?: return
        if(status == "Approved") return
        writableDatabase.execSQL("UPDATE reports SET status='Reviewed',reviewed_by=? WHERE report_no=?",arrayOf(userId,no))
        audit(userId,"REVIEW","REPORT",no,"Report reviewed; approval gate opened")
        enqueue("report",no,"UPDATE",JSONObject().put("reportNo",no).put("status","Reviewed").put("reviewedBy",userId))
    }
    fun addEquipment(n:String,s:String,next:String,loc:String="LAB-01"){writableDatabase.execSQL("INSERT INTO equipment(name,serial_no,next_calibration,status,location,created_at) VALUES(?,?,?,'ساري',?,?)",arrayOf(n,s,next,loc,now));enqueue("equipment",s.ifBlank{n},"CREATE",JSONObject().put("name",n).put("serialNo",s).put("nextCalibration",next).put("location",loc).put("status","ساري"))}
    fun addStorage(code:String,name:String,temp:String,capacity:Int){writableDatabase.execSQL("INSERT INTO storage_locations(code,name,temperature,capacity) VALUES(?,?,?,?)",arrayOf(code,name,temp,capacity));enqueue("storage_location",code,"CREATE",JSONObject().put("code",code).put("name",name).put("temperature",temp).put("capacity",capacity))}
    fun addNcr(desc:String,userId:Int){val no="NCR-"+System.currentTimeMillis().toString().takeLast(8);writableDatabase.execSQL("INSERT INTO ncr(ncr_no,description,status,created_by,created_at) VALUES(?,?,'Open',?,?)",arrayOf(no,desc,userId,now));audit(userId,"CREATE","NCR",no,desc);enqueue("ncr",no,"CREATE",JSONObject().put("ncrNo",no).put("description",desc).put("status","Open").put("createdBy",userId))}
    fun testCatalog():List<Array<String>>{val out=mutableListOf<Array<String>>();readableDatabase.rawQuery("SELECT code,name,category,standard,unit FROM tests_catalog WHERE active=1 ORDER BY category,code",null).use{c->while(c.moveToNext())out.add(arrayOf(c.getString(0),c.getString(1),c.getString(2),c.getString(3),c.getString(4)))};return out}
    fun counts()=intArrayOf(count("projects"),count("samples"),count("tests"),count("reports"),count("ncr")); private fun count(t:String)=readableDatabase.rawQuery("SELECT COUNT(*) FROM $t",null).use{it.moveToFirst();it.getInt(0)}
    fun auditRows()=query("SELECT COALESCE(u.username,'system'),action,entity,entity_id,details,created_at FROM audit_log a LEFT JOIN users u ON u.id=a.user_id ORDER BY a.id DESC LIMIT 200")
    fun ncrRows()=query("SELECT ncr_no,description,status,created_at FROM ncr ORDER BY id DESC")
    fun equipmentRows()=query("SELECT name,serial_no,next_calibration,status,location FROM equipment ORDER BY id DESC")
    fun storageRows()=query("SELECT code,name,temperature,capacity FROM storage_locations ORDER BY id")
    fun clientsRows()=query("SELECT name,phone,email,vat_no FROM clients ORDER BY id DESC")
    fun projectsRows()=query("SELECT code,name,location,consultant,contractor,status FROM projects ORDER BY id DESC")
    fun samplesRows()=query("SELECT sample_no,material,source,status,storage_location,gps FROM samples ORDER BY id DESC")
    fun upsertExcavationLicense(licenseNo:String,workOrderNo:String,projectName:String,serviceEntity:String,municipality:String,district:String,contractor:String,consultant:String,startAt:String,endAt:String,permitType:String,permitStatus:String,excavationStatus:String,location:String,gps:String,notes:String,userId:Int){
        val t=now
        val cv=android.content.ContentValues().apply{
            put("license_no",licenseNo);put("work_order_no",workOrderNo);put("project_name",projectName);put("service_entity",serviceEntity);put("municipality",municipality);put("district",district);put("contractor",contractor);put("consultant",consultant);put("start_at",startAt);put("end_at",endAt);put("permit_type",permitType);put("permit_status",permitStatus);put("excavation_status",excavationStatus);put("location",location);put("gps",gps);put("notes",notes);put("source","بلدي");put("created_by",userId);put("updated_at",t)
        }
        val existing=query("SELECT id FROM excavation_licenses WHERE license_no='${licenseNo.replace("'","''")}' LIMIT 1").firstOrNull()?.firstOrNull()?.toIntOrNull()
        if(existing==null){cv.put("created_at",t);writableDatabase.insertOrThrow("excavation_licenses",null,cv);audit(userId,"CREATE","EXCAVATION_LICENSE",licenseNo,"Imported/registered from Balady")}
        else{writableDatabase.update("excavation_licenses",cv,"id=?",arrayOf(existing.toString()));audit(userId,"UPDATE","EXCAVATION_LICENSE",licenseNo,"Updated Balady permit")}
        enqueue("excavation_license",licenseNo,if(existing==null)"CREATE" else "UPDATE",JSONObject().put("licenseNo",licenseNo).put("workOrderNo",workOrderNo).put("projectName",projectName).put("permitStatus",permitStatus).put("excavationStatus",excavationStatus).put("location",location).put("gps",gps).put("notes",notes).put("updatedAt",t))
    }
    fun excavationRows(search:String="")=query("SELECT license_no,work_order_no,project_name,municipality,district,permit_status,excavation_status,start_at,end_at FROM excavation_licenses WHERE license_no LIKE '%${search.replace("'","''")}%' OR work_order_no LIKE '%${search.replace("'","''")}%' OR project_name LIKE '%${search.replace("'","''")}%' OR contractor LIKE '%${search.replace("'","''")}%' ORDER BY id DESC")
    fun excavationDetail(no:String)=query("SELECT license_no,work_order_no,project_name,service_entity,municipality,district,contractor,consultant,start_at,end_at,permit_type,permit_status,excavation_status,location,gps,notes,source,created_at,updated_at FROM excavation_licenses WHERE license_no='${no.replace("'","''")}' LIMIT 1").firstOrNull()
    fun excavationCount()=count("excavation_licenses")

    fun setSetting(k:String,v:String){writableDatabase.execSQL("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)",arrayOf(k,v))}
    fun pendingSyncRows()=query("SELECT id,entity,entity_id,operation,payload,attempts,base_version FROM sync_queue WHERE status IN ('PENDING','RETRY') ORDER BY id LIMIT 50")
    fun syncCounts():Array<Int>{
        fun n(status:String):Int = readableDatabase.rawQuery("SELECT COUNT(*) FROM sync_queue WHERE status=?",arrayOf(status)).use { cursor -> cursor.moveToFirst(); cursor.getInt(0) }
        return arrayOf(n("PENDING")+n("RETRY"),n("CONFLICT"),n("FAILED"))
    }
    fun markSyncAccepted(ids:Collection<Long>){ids.forEach{writableDatabase.execSQL("UPDATE sync_queue SET status='SYNCED',last_error=NULL WHERE id=?",arrayOf(it))}}
    fun markSyncRetry(ids:Collection<Long>,error:String){ids.forEach{writableDatabase.execSQL("UPDATE sync_queue SET status='RETRY',attempts=attempts+1,last_error=? WHERE id=?",arrayOf(error.take(500),it))}}
    fun markSyncFailed(ids:Collection<Long>,error:String){ids.forEach{writableDatabase.execSQL("UPDATE sync_queue SET status='FAILED',attempts=attempts+1,last_error=? WHERE id=?",arrayOf(error.take(500),it))}}
    fun markSyncConflict(id:Long,e:String,eid:String,local:String,remote:String){writableDatabase.execSQL("UPDATE sync_queue SET status='CONFLICT',last_error='server conflict' WHERE id=?",arrayOf(id));writableDatabase.execSQL("INSERT INTO sync_conflicts(entity,entity_id,local_payload,remote_payload,status,created_at) VALUES(?,?,?,?, 'OPEN',?)",arrayOf(e,eid,local,remote,now))}
    fun retryFailedSync(){writableDatabase.execSQL("UPDATE sync_queue SET status='PENDING',last_error=NULL WHERE status='FAILED'")}
    fun openSyncConflicts()=query("SELECT id,entity,entity_id,local_payload,remote_payload,created_at FROM sync_conflicts WHERE status='OPEN' ORDER BY id DESC")
    fun keepLocalConflict(conflictId:Int){
        val row=query("SELECT entity,entity_id,local_payload FROM sync_conflicts WHERE id=$conflictId AND status='OPEN'").firstOrNull() ?: return
        enqueue(row[0] ?: "unknown",row[1] ?: "unknown","UPDATE",JSONObject(row[2] ?: "{}"))
        writableDatabase.execSQL("UPDATE sync_conflicts SET status='RESOLVED',resolution='KEEP_LOCAL',resolved_at=? WHERE id=?",arrayOf(now,conflictId))
    }
    fun acceptRemoteConflict(conflictId:Int){writableDatabase.execSQL("UPDATE sync_conflicts SET status='RESOLVED',resolution='KEEP_REMOTE',resolved_at=? WHERE id=?",arrayOf(now,conflictId))}
    fun getSetting(k:String)=query("SELECT value FROM settings WHERE key='${k.replace("'","''")}' LIMIT 1").firstOrNull()?.firstOrNull()?:""
    fun exportSql():String{val sb=StringBuilder("-- ASAS LIMS V5 BACKUP $now\n");listOf("users","clients","suppliers","projects","quotations","contracts","customer_requests","work_orders","samples","tests","reports","equipment","storage_locations","ncr","invoices","complaints","audit_log","attachments","report_signatures","calibration_records","method_versions","notifications","sync_conflicts","login_events","settings","sync_queue").forEach{t->sb.append("\n-- ").append(t).append("\n");query("SELECT * FROM $t").forEach{sb.append(it.joinToString("|"){v->v?:("NULL")}).append("\n")}};return sb.toString()}
    fun query(sql:String):List<Array<String?>>{val out=mutableListOf<Array<String?>>();readableDatabase.rawQuery(sql,null).use{c->while(c.moveToNext())out.add(Array(c.columnCount){i->if(c.isNull(i))null else c.getString(i)})};return out}
}
