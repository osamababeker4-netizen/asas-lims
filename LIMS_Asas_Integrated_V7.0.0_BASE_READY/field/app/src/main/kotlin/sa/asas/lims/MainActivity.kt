package sa.asas.lims

import android.app.*
import android.os.Bundle
import android.print.PrintAttributes
import android.print.PrintManager
import android.content.Intent
import android.graphics.*
import android.net.Uri
import android.text.InputType
import android.view.*
import android.widget.*
import androidx.core.content.FileProvider
import java.io.File

class MainActivity : Activity() {
    private companion object { const val DEFAULT_CENTRAL_API="https://asas-lims-api.onrender.com" }
    private lateinit var db:LimsDb
    private lateinit var root:LinearLayout
    private var currentUserId=0
    private var currentUser=""
    private var currentRole="user"
    private var backAction:(()->Unit)?=null
    @Volatile private var autoSyncRunning=false

    override fun onBackPressed(){ backAction?.invoke() ?: super.onBackPressed() }
    override fun onCreate(b:Bundle?){super.onCreate(b);db=LimsDb(this);showLogin()}

    private fun base()=LinearLayout(this).apply{orientation=LinearLayout.VERTICAL;setPadding(20,20,20,20);setBackgroundColor(Color.rgb(247,250,249))}
    private fun officialFooter()=TextView(this).apply{
        text="مختبر أساس للاستشارات الفنية والمختبرات الهندسية\nwww.asaslab.com  •  جميع الحقوق محفوظة"
        textSize=12f
        setTextColor(Color.rgb(82,111,106))
        gravity=Gravity.CENTER
        setPadding(8,32,8,8)
    }
    // حاوية تمرير صريحة وموثوقة لجميع شاشات التطبيق، بما فيها لوحة التحكم الرئيسية.
    private fun mount(){
        val content = root.apply {
            layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
            )
            isFocusable = false
            isFocusableInTouchMode = false
        }
        // نستخدم ScrollView عموديًا بشكل مباشر لتفادي أي تعارض في nested scrolling على بعض المحاكيات.
        val scroll = ScrollView(this).apply {
            layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT
            )
            isFillViewport = false
            isVerticalScrollBarEnabled = true
            overScrollMode = View.OVER_SCROLL_ALWAYS
            clipToPadding = false
            setPadding(0, 0, 0, 24)
            descendantFocusability = ViewGroup.FOCUS_BEFORE_DESCENDANTS
            addView(content)
        }
        content.addView(officialFooter())
        setContentView(scroll)
        scroll.post {
            scroll.scrollTo(0, 0)
            scroll.requestLayout()
        }
    }
    private fun tv(s:String,size:Float=16f,bold:Boolean=false)=TextView(this).apply{text=s;textSize=size;setTextColor(Color.rgb(25,35,45));if(bold)setTypeface(null,Typeface.BOLD);setPadding(4,8,4,8)}
    private fun logo()=ImageView(this).apply{setImageResource(R.drawable.asas_official_logo);adjustViewBounds=true;scaleType=ImageView.ScaleType.FIT_CENTER;layoutParams=LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,120).apply{gravity=Gravity.CENTER_HORIZONTAL}}
    private fun btn(s:String,on:()->Unit)=Button(this).apply{text=s;isAllCaps=false;setOnClickListener{on()}}
    private fun inp(h:String,v:String="")=EditText(this).apply{hint=h;setText(v);setPadding(12,8,12,8)}
    private fun header(title:String,back:()->Unit={dashboard()}){root=base();backAction=back;root.addView(btn("← رجوع"){back()});root.addView(tv(title,24f,true))}
    private fun dashboard(){showDashboard()}
    private fun centralApi():String = db.getSetting("central_api").trim().ifBlank { DEFAULT_CENTRAL_API }
    private fun signInLocally(usernameOrPhone:String,password:String):Boolean {
        val account=db.login(usernameOrPhone,password) ?: return false
        currentUserId=account[0]?.toIntOrNull()?:0
        currentUser=account[1]?:usernameOrPhone
        currentRole=account[3]?:"user"
        db.audit(currentUserId,"LOGIN","USER",currentUser,"Local authenticated sign-in")
        showDashboard()
        return true
    }

    private fun showLogin(){
        if(db.getSetting("initial_setup_required")=="1"){showInitialSetup();return}
        backAction=null;root=base();root.addView(logo());root.addView(tv("مختبر أساس LIMS V7.3.0",28f,true));root.addView(tv("نظام إدارة المختبر — النسخة النهائية الموحدة",16f))
        val u=inp("اسم المستخدم أو رقم الجوال الدولي");u.inputType=InputType.TYPE_CLASS_TEXT;val p=inp("كلمة المرور");p.inputType=InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
        root.addView(u);root.addView(p);root.addView(btn("دخول"){
            val username=u.text.toString().trim();val password=p.text.toString()
            if(username.isBlank()||password.isBlank()){toast("أدخل اسم المستخدم وكلمة المرور");return@btn}
            toast("جارٍ التحقق من الحساب المركزي…")
            Thread {
                val result=SyncClient(this,db).requestCentralOtp(centralApi(),username,password)
                runOnUiThread {
                    when {
                        result.user!=null -> showCentralOtp(centralApi(),result.user)
                        result.unavailable && signInLocally(username,password) -> Unit
                        result.unavailable -> toast("تعذر الاتصال بالخادم، ولم تتطابق بيانات الدخول المحلي")
                        else -> toast(result.message)
                    }
                }
            }.start()
        })
        root.addView(tv("يتم التحقق أولاً من الحساب المركزي ثم إرسال رمز تحقق حقيقي. عند انقطاع الاتصال فقط يمكن استخدام الحساب المحلي المحفوظ على الجهاز.",13f))
        mount(); autoSyncIfConfigured()
    }
    private fun showCentralOtp(api:String, account:SyncClient.CentralUser){
        backAction={showLogin()};root=base();root.addView(logo());root.addView(tv("تأكيد الدخول المركزي",25f,true))
        val phone=account.phone.takeLast(4).let { if(it.isBlank()) "الجوال المسجل" else "••••$it" }
        root.addView(tv("أُرسل رمز تحقق إلى $phone للحساب ${account.username}.",15f))
        val otp=inp("رمز التحقق المكوّن من 6 أرقام");otp.inputType=InputType.TYPE_CLASS_NUMBER
        root.addView(otp);root.addView(btn("تحقق ودخول"){
            val code=otp.text.toString().trim();if(code.length!=6||!code.all{it.isDigit()}){toast("أدخل رمز التحقق المكوّن من 6 أرقام");return@btn}
            toast("جارٍ التحقق من الرمز…")
            Thread {
                val result=SyncClient(this,db).verifyCentralOtp(api,account.username,code)
                runOnUiThread {
                    val verified=result.user
                    if(result.token.isNullOrBlank()||verified==null){toast(result.message);return@runOnUiThread}
                    db.setSetting("central_api",api)
                    getSharedPreferences("central_sync",MODE_PRIVATE).edit().putString("access_token",result.token).putString("central_user",verified.username).apply()
                    currentUserId=db.userIdByUsername(verified.username)
                    currentUser=verified.name.ifBlank { verified.username }
                    currentRole=verified.role.ifBlank { "user" }
                    db.audit(currentUserId,"LOGIN","USER",verified.username,"Central OTP authenticated sign-in")
                    showDashboard()
                }
            }.start()
        });root.addView(btn("عودة لتغيير الحساب"){showLogin()});mount()
    }
    private fun showInitialSetup(){backAction=null;root=base();root.addView(logo());root.addView(tv("تهيئة مختبر أساس",26f,true));root.addView(tv("أنشئ كلمة مرور مدير النظام ورقم الجوال قبل أول استخدام.",15f));val pass=inp("كلمة مرور المدير (12 حرفاً على الأقل)");pass.inputType=0x81;val confirm=inp("تأكيد كلمة المرور");confirm.inputType=0x81;val phone=inp("رقم الجوال");root.addView(pass);root.addView(confirm);root.addView(phone);root.addView(btn("إنهاء التهيئة"){val p=pass.text.toString();if(p.length<12||p!=confirm.text.toString()||phone.text.trim().length<8){toast("تحقق من كلمة المرور ورقم الجوال");return@btn};db.completeInitialSetup(p,phone.text.toString().trim());toast("اكتملت التهيئة؛ سجّل الدخول الآن");showLogin()});mount()}

    private fun autoSyncIfConfigured(){
        val prefs=getSharedPreferences("central_sync",MODE_PRIVATE); val api=db.getSetting("central_api"); val token=prefs.getString("access_token","").orEmpty()
        if(autoSyncRunning || api.isBlank() || token.isBlank() || db.pendingSyncRows().isEmpty()) return
        autoSyncRunning=true; Thread { SyncClient(this,db).upload(api,token); autoSyncRunning=false }.start()
    }
    private fun showDashboard(){
        backAction=null;root=base();root.addView(logo());root.addView(tv("مختبر أساس LIMS V7.3.0",28f,true));root.addView(tv("المستخدم: $currentUser   |   الصلاحية: $currentRole",15f))
        val c=db.counts();root.addView(tv("المشاريع ${c[0]}   | العينات ${c[1]}   | الاختبارات ${c[2]}   | التقارير ${c[3]}   | NCR ${c[4]}   | رخص الحفريات ${db.excavationCount()}",16f,true))
        root.addView(tv("━━ الإدارة والتكامل ━━",19f,true));root.addView(btn("📊 لوحة القيادة والتحليلات"){analytics()});root.addView(btn("👤 المستخدمون والصلاحيات"){users()});root.addView(btn("📝 سجل التدقيق Audit Trail"){audit()});root.addView(btn("⚙ الإعدادات والأمان"){settings()})
        root.addView(tv("━━ إدارة الأعمال والعملاء ━━",19f,true));root.addView(btn("👥 العملاء"){clients()});root.addView(btn("🏗 المشاريع والمواقع"){projects()});root.addView(btn("💰 عروض الأسعار"){quotes()});root.addView(btn("📑 العقود"){contracts()});root.addView(btn("📨 طلبات العملاء"){requests()});root.addView(btn("🧾 أوامر العمل"){workOrders()});root.addView(btn("💵 الفواتير"){invoices()});root.addView(btn("⚠ شكاوى العملاء"){complaints()})
        root.addView(tv("━━ المختبر والعمليات الميدانية ━━",19f,true));root.addView(btn("🧪 العينات + QR"){samples()});root.addView(btn("🔬 الاختبارات والحسابات"){tests()});root.addView(btn("👨‍🔬 إسناد الاختبارات للفنيين"){assignments()});root.addView(btn("⚙ الأجهزة والمعايرة والصيانة"){equipment()});root.addView(btn("📦 مواقع التخزين"){storage()});root.addView(btn("🚚 حركة الأجهزة"){movements()});root.addView(btn("❌ تقارير عدم المطابقة NCR"){ncr()});root.addView(btn("📄 التقارير والمراجعة والاعتماد"){reports()})
        root.addView(tv("━━ الجودة والتكامل ━━",19f,true));root.addView(btn("🏛 منصة بلدي"){openBalady()});root.addView(btn("💬 واتساب الرسمي للمختبر"){openOfficialWhatsApp()});root.addView(btn("⛏ رخص الحفريات"){excavationLicenses()});root.addView(btn("🔄 المزامنة مع النظام المركزي"){sync()});root.addView(btn("💾 النسخ الاحتياطي والاستعادة"){backup()});root.addView(btn("📋 إعدادات الاختبارات وحدود القبول"){testSettings()});root.addView(btn("🚪 تسجيل الخروج"){currentUser="";showLogin()})
        mount()
    }

    private fun analytics(){header("Dashboard & Analytics");val c=db.counts();root.addView(tv("المؤشرات الرئيسية",20f,true));root.addView(tv("المشاريع: ${c[0]}\nالعينات: ${c[1]}\nالاختبارات: ${c[2]}\nالتقارير: ${c[3]}\nNCR المفتوحة/المسجلة: ${c[4]}",18f));root.addView(tv("مؤشرات الجودة والتشغيل تُبنى من قاعدة البيانات المركزية عند ربط الـAPI.",13f));mount()}

    private fun userRoleSpinner(selected:String="technician")=Spinner(this).apply{
        val roles=listOf("user","technician","reviewer","admin")
        adapter=ArrayAdapter(this@MainActivity,android.R.layout.simple_spinner_dropdown_item,roles)
        setSelection(roles.indexOf(selected).coerceAtLeast(0))
    }
    private fun users(){
        if(currentRole!="admin"){toast("هذه الصلاحية لمدير النظام");return}
        header("إدارة المستخدمين والصلاحيات")
        val username=inp("اسم المستخدم")
        val password=inp("كلمة المرور (12 حرفاً على الأقل)");password.inputType=0x81
        val fullName=inp("الاسم الكامل")
        val phone=inp("الجوال الدولي")
        val role=userRoleSpinner()
        root.addView(username);root.addView(password);root.addView(fullName);root.addView(phone);root.addView(tv("الدور"));root.addView(role)
        root.addView(btn("+ إضافة مستخدم وحفظ"){
            try {
                if(username.text.isBlank()||fullName.text.isBlank()||phone.text.isBlank()) throw Exception("أكمل البيانات")
                if(password.text.length<12) throw Exception("كلمة المرور يجب ألا تقل عن 12 حرفاً")
                db.addUser(username.text.toString().trim(),password.text.toString(),fullName.text.toString().trim(),role.selectedItem.toString(),phone.text.toString().trim())
                db.audit(currentUserId,"CREATE","USER",username.text.toString().trim(),"New local user")
                toast("تمت إضافة المستخدم وحفظه")
                users()
            } catch(e:Exception){toast("تعذر الإضافة: ${e.message}")}
        })
        root.addView(tv("المستخدمون الحاليون",18f,true))
        db.userRows().forEach{ row ->
            val id=row[0]?.toIntOrNull() ?: return@forEach
            root.addView(tv("• ${row[1]} | ${row[2]} | ${row[3]} | ${row[4]} | ${if(row[5]=="1")"فعال" else "موقوف"}"))
            root.addView(btn("✎ تعديل ${row[1]}"){editUser(row)})
            if(row[1]!="admin") root.addView(btn("🗑 حذف ${row[1]}"){
                AlertDialog.Builder(this).setTitle("حذف المستخدم").setMessage("تأكيد حذف ${row[1]}؟")
                    .setNegativeButton("إلغاء",null).setPositiveButton("حذف"){_,_->
                        db.deleteUser(id);db.audit(currentUserId,"DELETE","USER",id.toString(),"Local user deleted");users()
                    }.show()
            })
        }
        mount()
    }
    private fun editUser(row:Array<String?>){
        val id=row[0]?.toIntOrNull() ?: return
        header("تعديل المستخدم ${row[1]}",{users()})
        root.addView(tv("اسم المستخدم: ${row[1]} (لا يمكن تغييره)",15f,true))
        val fullName=inp("الاسم الكامل",row[2] ?: "")
        val phone=inp("الجوال الدولي",row[4] ?: "")
        val role=userRoleSpinner(row[3] ?: "technician")
        val password=inp("كلمة مرور جديدة (اتركها فارغة للإبقاء)");password.inputType=0x81
        val active=CheckBox(this).apply{text="الحساب نشط";isChecked=row[5]=="1"}
        root.addView(fullName);root.addView(phone);root.addView(tv("الدور"));root.addView(role);root.addView(password);root.addView(active)
        root.addView(btn("حفظ تعديل المستخدم"){
            try {
                if(fullName.text.isBlank()||phone.text.isBlank()) throw Exception("أكمل الاسم ورقم الجوال")
                if(password.text.isNotBlank()&&password.text.length<12) throw Exception("كلمة المرور يجب ألا تقل عن 12 حرفاً")
                if(id==currentUserId&&!active.isChecked) throw Exception("لا يمكنك إيقاف حسابك الحالي")
                db.updateUser(id,fullName.text.toString().trim(),role.selectedItem.toString(),phone.text.toString().trim(),active.isChecked,password.text.toString())
                db.audit(currentUserId,"UPDATE","USER",id.toString(),"Local user updated")
                toast("تم تعديل المستخدم وحفظه")
                users()
            } catch(e:Exception){toast("تعذر التعديل: ${e.message}")}
        })
        mount()
    }

    private fun clients(){header("إدارة العملاء");val n=inp("اسم العميل");val p=inp("الهاتف");val e=inp("البريد الإلكتروني");val v=inp("الرقم الضريبي");root.addView(n);root.addView(p);root.addView(e);root.addView(v);root.addView(btn("+ إضافة عميل"){if(n.text.isNotBlank()){db.addClient(n.text.toString(),p.text.toString(),e.text.toString(),v.text.toString());clients()}});db.clientsRows().forEach{root.addView(tv("• ${it[0]} | ${it[1]} | ${it[2]} | VAT: ${it[3]}"))};mount()}
    private fun projects(){header("المشاريع والمواقع");val n=inp("اسم المشروع");val l=inp("الموقع");val co=inp("الاستشاري");val ct=inp("المقاول");root.addView(n);root.addView(l);root.addView(co);root.addView(ct);root.addView(btn("+ إضافة مشروع"){if(n.text.isNotBlank()){db.addProject(n.text.toString(),l.text.toString(),null,co.text.toString(),ct.text.toString());projects()}});db.projectsRows().forEach{root.addView(tv("• ${it[0]} | ${it[1]} | ${it[2]} | استشاري: ${it[3]} | مقاول: ${it[4]} | ${it[5]}"))};mount()}
    private fun quotes(){header("عروض الأسعار");val no=inp("رقم العرض");val amount=inp("القيمة");root.addView(no);root.addView(amount);root.addView(btn("+ حفظ عرض"){if(no.text.isNotBlank())db.writableDatabase.execSQL("INSERT INTO quotations(quote_no,amount,status,created_at) VALUES(?,?,?,?)",arrayOf(no.text.toString(),amount.text.toString().toDoubleOrNull()?:0.0,"Draft",System.currentTimeMillis().toString()));toast("تم حفظ العرض");quotes()});db.query("SELECT quote_no,amount,status,created_at FROM quotations ORDER BY id DESC").forEach{root.addView(tv("• ${it.joinToString(" | ")}"))};mount()}
    private fun contracts(){header("العقود");val no=inp("رقم العقد");val amount=inp("القيمة");val start=inp("تاريخ البداية");val end=inp("تاريخ النهاية");root.addView(no);root.addView(amount);root.addView(start);root.addView(end);root.addView(btn("+ حفظ عقد"){if(no.text.isNotBlank()){db.writableDatabase.execSQL("INSERT INTO contracts(contract_no,amount,start_date,end_date,status,created_at) VALUES(?,?,?,?,?,?)",arrayOf(no.text.toString(),amount.text.toString().toDoubleOrNull()?:0.0,start.text.toString(),end.text.toString(),"Active",System.currentTimeMillis().toString()));contracts()}});db.query("SELECT contract_no,amount,start_date,end_date,status FROM contracts ORDER BY id DESC").forEach{root.addView(tv("• ${it.joinToString(" | ")}"))};mount()}
    private fun requests(){header("طلبات العملاء");val desc=inp("وصف الطلب");root.addView(desc);root.addView(btn("+ تسجيل طلب"){if(desc.text.isNotBlank()){val no="REQ-"+System.currentTimeMillis().toString().takeLast(8);db.writableDatabase.execSQL("INSERT INTO customer_requests(request_no,description,status,created_at) VALUES(?,?,?,?)",arrayOf(no,desc.text.toString(),"Open",System.currentTimeMillis().toString()));requests()}});db.query("SELECT request_no,description,status,created_at FROM customer_requests ORDER BY id DESC").forEach{root.addView(tv("• ${it.joinToString(" | ")}"))};mount()}
    private fun workOrders(){header("أوامر العمل");val priority=Spinner(this).apply{adapter=ArrayAdapter(this@MainActivity,android.R.layout.simple_spinner_dropdown_item,listOf("Normal","High","Urgent"))};root.addView(tv("الأولوية"));root.addView(priority);root.addView(btn("+ إنشاء أمر عمل"){val no="WO-"+System.currentTimeMillis().toString().takeLast(8);db.writableDatabase.execSQL("INSERT INTO work_orders(wo_no,priority,status,created_at) VALUES(?,?,?,?)",arrayOf(no,priority.selectedItem.toString(),"Open",System.currentTimeMillis().toString()));workOrders()});db.query("SELECT wo_no,priority,status,created_at FROM work_orders ORDER BY id DESC").forEach{root.addView(tv("• ${it.joinToString(" | ")}"))};mount()}
    private fun invoices(){header("الفواتير");val no=inp("رقم الفاتورة");val amount=inp("المبلغ قبل الضريبة");root.addView(no);root.addView(amount);root.addView(btn("+ إنشاء فاتورة VAT"){val a=amount.text.toString().toDoubleOrNull()?:0.0;val vat=a*.15;val total=a+vat;if(no.text.isNotBlank()){db.writableDatabase.execSQL("INSERT INTO invoices(invoice_no,amount,vat,total,status,created_at) VALUES(?,?,?,?,?,?)",arrayOf(no.text.toString(),a,vat,total,"Draft",System.currentTimeMillis().toString()));invoices()}});db.query("SELECT invoice_no,amount,vat,total,status FROM invoices ORDER BY id DESC").forEach{root.addView(tv("• ${it.joinToString(" | ")}"))};mount()}
    private fun complaints(){header("شكاوى العملاء");val d=inp("وصف الشكوى");root.addView(d);root.addView(btn("+ تسجيل شكوى"){if(d.text.isNotBlank()){val no="CMP-"+System.currentTimeMillis().toString().takeLast(8);db.writableDatabase.execSQL("INSERT INTO complaints(complaint_no,description,status,created_at) VALUES(?,?,?,?)",arrayOf(no,d.text.toString(),"Open",System.currentTimeMillis().toString()));complaints()}});db.query("SELECT complaint_no,description,status,created_at FROM complaints ORDER BY id DESC").forEach{root.addView(tv("• ${it.joinToString(" | ")}"))};mount()}

    private fun samples(){header("العينات والتتبع");val no=inp("كود العينة");val m=inp("المادة","تربة");val s=inp("مصدر العينة");val gps=inp("GPS / إحداثيات");root.addView(no);root.addView(m);root.addView(s);root.addView(gps);root.addView(btn("+ تسجيل عينة"){if(no.text.isNotBlank()){db.addSample(no.text.toString(),m.text.toString(),s.text.toString(),null,gps.text.toString());db.audit(currentUserId,"CREATE","SAMPLE",no.text.toString(),m.text.toString());samples()}});db.samplesRows().forEach{r->root.addView(tv("• ${r[0]} | ${r[1]} | ${r[2]} | ${r[3]} | تخزين: ${r[4]} | GPS: ${r[5]}"));root.addView(btn("▣ QR — ${r[0]}"){showQr("كود العينة",r[0]?:"")})};mount()}

    private fun tests(){header("دليل الاختبارات والحسابات");val cats=listOf("التربة","الخرسانة","الاسفلت","أخرى");cats.forEach{cat->root.addView(tv("━━ $cat ━━",19f,true));db.testCatalog().filter{it[2]==cat}.forEach{t->root.addView(btn("${t[0]} — ${t[1]} [${t[4]}]"){testForm(t[0],t[1])})}};mount()}
    private fun testForm(code:String,name:String){header("$code — $name",{tests()});val sample=inp("كود العينة");root.addView(sample);when(code){"ASTM D1557","ASTM D698"->proctor(sample,code);"ASTM D2216"->moisture(sample);"ASTM D4318"->atterberg(sample);"ASTM D1883"->cbr(sample);else->generic(sample,code,name)};mount()}
    private fun proctor(sample:EditText,code:String){root.addView(tv("أدخل 5 نقاط على الأقل. يحسب أعلى كثافة جافة كنقطة أولية، ويمكن تطوير interpolation في خادم الحسابات المركزي."));val rows=mutableListOf<Pair<EditText,EditText>>();repeat(5){val w=inp("الرطوبة ${it+1}%");val d=inp("الكثافة الجافة ${it+1} g/cm³");rows.add(w to d);root.addView(w);root.addView(d)};root.addView(btn("حساب وحفظ"){val v=rows.mapNotNull{a->val w=a.first.text.toString().toDoubleOrNull();val d=a.second.text.toString().toDoubleOrNull();if(w!=null&&d!=null)w to d else null};if(v.isEmpty()||sample.text.isBlank()){toast("أكمل البيانات");return@btn};val best=v.maxBy{it.second};val res="MDD=${"%.3f".format(best.second)} g/cm³; OMC=${"%.2f".format(best.first)}%";db.addTest(code,sample.text.toString(),res,currentUserId,v.joinToString(";"){it.first.toString()+","+it.second},"Calculated");alert("تم الحفظ",res)})}
    private fun moisture(sample:EditText){val wet=inp("الوزن الرطب g");val dry=inp("الوزن الجاف g");root.addView(wet);root.addView(dry);root.addView(btn("حساب وحفظ"){val a=wet.text.toString().toDoubleOrNull();val b=dry.text.toString().toDoubleOrNull();if(a!=null&&b!=null&&b>0&&sample.text.isNotBlank()){val r=(a-b)/b*100;val res="Moisture=${"%.2f".format(r)}%";db.addTest("ASTM D2216",sample.text.toString(),res,currentUserId,"wet=$a,dry=$b","Calculated");alert("النتيجة",res)}})}
    private fun atterberg(sample:EditText){val ll=inp("LL %");val pl=inp("PL %");root.addView(ll);root.addView(pl);root.addView(btn("حساب PI وحفظ"){val a=ll.text.toString().toDoubleOrNull();val b=pl.text.toString().toDoubleOrNull();if(a!=null&&b!=null&&sample.text.isNotBlank()){val res="LL=${"%.2f".format(a)}%; PL=${"%.2f".format(b)}%; PI=${"%.2f".format(a-b)}%";db.addTest("ASTM D4318",sample.text.toString(),res,currentUserId,"LL=$a,PL=$b","Calculated");alert("النتيجة",res)}})}
    private fun cbr(sample:EditText){val a=inp("CBR عند 2.5 mm %");val b=inp("CBR عند 5.0 mm %");root.addView(a);root.addView(b);root.addView(btn("حفظ CBR"){val x=a.text.toString().toDoubleOrNull();val y=b.text.toString().toDoubleOrNull();if(x!=null&&y!=null&&sample.text.isNotBlank()){val selected=if(y>x)y else x;val res="CBR=${"%.1f".format(selected)}%";db.addTest("ASTM D1883",sample.text.toString(),res,currentUserId,"2.5mm=$x,5mm=$y","Calculated");alert("النتيجة",res)}})}
    private fun generic(sample:EditText,code:String,name:String){val r=inp("النتيجة / الملاحظات");root.addView(r);root.addView(btn("حفظ نتيجة $name"){if(r.text.isNotBlank()&&sample.text.isNotBlank()){db.addTest(code,sample.text.toString(),r.text.toString(),currentUserId,"manual","Pending Review");alert("تم","تم تسجيل النتيجة للمراجعة")}})}

    private fun assignments(){header("إسناد الاختبارات للفنيين");root.addView(tv("تُسند الاختبارات آليًا من خلال محرك التوزيع المركزي عند المزامنة. هذه الشاشة تعرض نقطة التكامل.",14f));root.addView(btn("تشغيل التوزيع التلقائي"){db.audit(currentUserId,"AUTO_ASSIGN","TEST_ASSIGNMENT","","Automatic distribution requested");toast("تم تسجيل طلب التوزيع للمزامنة المركزية")});mount()}
    private fun equipment(){header("الأجهزة والمعايرة والصيانة");val n=inp("اسم الجهاز");val s=inp("الرقم التسلسلي");val d=inp("المعايرة القادمة");val l=inp("الموقع","LAB-01");root.addView(n);root.addView(s);root.addView(d);root.addView(l);root.addView(btn("+ إضافة جهاز"){if(n.text.isNotBlank()){db.addEquipment(n.text.toString(),s.text.toString(),d.text.toString(),l.text.toString());equipment()}});db.equipmentRows().forEach{root.addView(tv("• ${it.joinToString(" | ")}"))};mount()}
    private fun storage(){header("مواقع التخزين");val c=inp("كود الموقع");val n=inp("الاسم");val t=inp("درجة الحرارة");val cap=inp("السعة");root.addView(c);root.addView(n);root.addView(t);root.addView(cap);root.addView(btn("+ إضافة موقع"){if(c.text.isNotBlank()&&n.text.isNotBlank()){db.addStorage(c.text.toString(),n.text.toString(),t.text.toString(),cap.text.toString().toIntOrNull()?:0);storage()}});db.storageRows().forEach{root.addView(tv("• ${it.joinToString(" | ")}"))};mount()}
    private fun movements(){header("تتبع حركة الأجهزة");val e=inp("كود/اسم الجهاز");val from=inp("من");val to=inp("إلى");root.addView(e);root.addView(from);root.addView(to);root.addView(btn("تسجيل حركة"){db.writableDatabase.execSQL("INSERT INTO equipment_movements(equipment_id,from_location,to_location,moved_by,moved_at) VALUES(?,?,?,?,?)",arrayOf(0,from.text.toString(),to.text.toString(),currentUserId,System.currentTimeMillis().toString()));db.audit(currentUserId,"MOVE","EQUIPMENT",e.text.toString(),"$from -> $to");toast("تم التسجيل")});mount()}
    private fun ncr(){header("NCR — تقارير عدم المطابقة");val d=inp("وصف عدم المطابقة");root.addView(d);root.addView(btn("+ فتح NCR"){if(d.text.isNotBlank()){db.addNcr(d.text.toString(),currentUserId);ncr()}});db.ncrRows().forEach{root.addView(tv("• ${it.joinToString(" | ")}"))};mount()}

    private fun reports(){header("التقارير والمراجعة والاعتماد");db.reportRows().forEach{r->root.addView(tv("${r[0]} | ${r[1]} | عينة ${r[2]} | ${r[3]} | الحالة: ${r[4]}"));root.addView(btn("📄 PDF"){exportReportPdf(r[0]?:"")});root.addView(btn("📤 مشاركة PDF"){shareReportPdf(r[0]?:"")});if(currentRole=="reviewer"||currentRole=="admin"){root.addView(btn("✓ مراجعة ${r[0]}"){db.reviewReport(r[0]?:"",currentUserId);reports()});root.addView(btn("✓ اعتماد نهائي ${r[0]}"){db.approveReport(r[0]?:"",currentUserId);reports()})}};mount()}

    private fun audit(){if(currentRole!="admin"&&currentRole!="reviewer"){toast("غير مصرح");return};header("Audit Trail");db.auditRows().forEach{root.addView(tv("${it[5]} | ${it[0]} | ${it[1]} | ${it[2]}:${it[3]}\n${it[4]}"))};mount()}
    private fun settings(){if(currentRole!="admin"){toast("للمدير فقط");return};header("الإعدادات والأمان");val org=inp("اسم المنشأة",db.getSetting("organization"));val api=inp("Central API URL",db.getSetting("central_api"));val sms=inp("SMS Provider",db.getSetting("sms_provider"));root.addView(org);root.addView(api);root.addView(sms);root.addView(btn("حفظ الإعدادات"){db.setSetting("organization",org.text.toString());db.setSetting("central_api",api.text.toString());db.setSetting("sms_provider",sms.text.toString());db.audit(currentUserId,"UPDATE","SETTINGS","","Security/integration settings updated");toast("تم الحفظ")});root.addView(tv("الأمان: كلمات المرور مخزنة بتجزئة SHA-256 مع Salt، OTP مخزن كتجزئة ومحدد بمدة 5 دقائق، وAudit Trail يسجل العمليات.",13f));mount()}
    private fun excavationLicenses(){
        header("⛏ بلدي — رخص الحفريات", {showDashboard()})
        root.addView(tv("إدارة ومتابعة تصاريح أعمال البنية التحتية",21f,true))
        root.addView(tv("بحث محلي سريع في الرخص المسجلة، مع فتح منصة بلدي الرسمية عند الحاجة. الربط الآلي المباشر ببيانات بلدي لا يتم إلا عبر واجهة API وصلاحية رسمية.",13f))
        val search=inp("ابحث برقم التصريح أو أمر العمل أو المشروع أو المقاول")
        root.addView(search)
        root.addView(btn("🔎 بحث"){renderExcavationRows(search.text.toString().trim())})
        root.addView(btn("➕ تسجيل تصريح"){excavationForm()})
        root.addView(btn("🏛 فتح طلبات بلدي"){openBalady()})
        root.addView(tv("إجمالي الرخص المحلية: ${db.excavationCount()}",14f,true))
        renderExcavationRows("")
        mount()
    }

    private fun renderExcavationRows(q:String){
        val rows=db.excavationRows(q)
        root.addView(tv(if(rows.isEmpty()) "لا توجد نتائج مطابقة" else "النتائج: ${rows.size}",16f,true))
        rows.take(100).forEach { r ->
            val no=r[0] ?: ""
            root.addView(tv("تصريح $no\nأمر العمل: ${r[1] ?: "—"}\n${r[2] ?: "—"}\n${r[3] ?: "—"} — ${r[4] ?: "—"}\nالحالة: ${r[5] ?: "—"} | الحفرية: ${r[6] ?: "—"}\nمن ${r[7] ?: "—"} إلى ${r[8] ?: "—"}",15f,true))
            root.addView(btn("📋 تفاصيل $no"){excavationDetail(no)})
        }
    }

    private fun excavationDetail(no:String){
        val r=db.excavationDetail(no) ?: run {toast("التصريح غير موجود");return}
        header("تفاصيل تصريح الحفر", {excavationLicenses()})
        val labels=listOf("رقم التصريح","رقم أمر العمل","اسم المشروع","الجهة الخدمية","الأمانة/البلدية","الحي","المقاول الرئيسي","الاستشاري الرئيسي","تاريخ بدء العمل","تاريخ انتهاء التصريح","نوع التصريح","حالة التصريح","حالة الحفرية","الموقع","GPS","المصدر","ملاحظات")
        val idx=listOf(0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,16,15)
        idx.forEachIndexed { i,k -> root.addView(tv("${labels[i]}\n${r[k] ?: "—"}",16f)) }
        root.addView(btn("📍 فتح الموقع في الخرائط"){val gps=r[14].orEmpty();if(gps.isBlank()){toast("لا توجد إحداثيات مسجلة")}else{try{startActivity(Intent(Intent.ACTION_VIEW,Uri.parse("geo:$gps?q=$gps")))}catch(_:Exception){toast("تعذر فتح الخرائط")}}})
        root.addView(btn("🔄 تعديل بيانات التصريح"){excavationForm(r)})
        root.addView(btn("🏛 فتح منصة بلدي"){openBalady()})
        mount()
    }

    private fun excavationForm(existing:Array<String?>?=null){
        header(if(existing==null) "تسجيل تصريح بلدي" else "تعديل تصريح بلدي", {excavationLicenses()})
        fun value(i:Int)=existing?.getOrNull(i).orEmpty()
        val no=inp("رقم التصريح *",value(0)); val wo=inp("رقم أمر العمل",value(1)); val project=inp("اسم المشروع",value(2)); val service=inp("الجهة الخدمية",value(3)); val municipality=inp("الأمانة / البلدية",value(4)); val district=inp("الحي",value(5)); val contractor=inp("المقاول الرئيسي",value(6)); val consultant=inp("الاستشاري الرئيسي",value(7)); val start=inp("تاريخ بدء العمل",value(8)); val end=inp("تاريخ انتهاء التصريح",value(9)); val type=inp("نوع التصريح",value(10)); val status=inp("حالة التصريح",value(11)); val excStatus=inp("حالة الحفرية",value(12)); val location=inp("الموقع",value(13)); val gps=inp("الإحداثيات GPS",value(14)); val notes=inp("ملاحظات",value(15))
        listOf(no,wo,project,service,municipality,district,contractor,consultant,start,end,type,status,excStatus,location,gps,notes).forEach{root.addView(it)}
        root.addView(btn("💾 حفظ"){if(no.text.isBlank()){toast("رقم التصريح مطلوب");return@btn};try{db.upsertExcavationLicense(no.text.toString().trim(),wo.text.toString(),project.text.toString(),service.text.toString(),municipality.text.toString(),district.text.toString(),contractor.text.toString(),consultant.text.toString(),start.text.toString(),end.text.toString(),type.text.toString(),status.text.toString(),excStatus.text.toString(),location.text.toString(),gps.text.toString(),notes.text.toString(),currentUserId);toast("تم حفظ تصريح بلدي");excavationDetail(no.text.toString().trim())}catch(e:Exception){toast("تعذر الحفظ: ${e.message}")}})
        root.addView(btn("🏛 فتح بلدي الرسمي"){openBalady()})
        mount()
    }

    private fun openBalady(){
        db.audit(currentUserId,"OPEN","BALADY","https://balady.gov.sa","Opened official Balady portal")
        val intent=Intent(Intent.ACTION_VIEW, Uri.parse("https://balady.gov.sa"))
        try{startActivity(intent)}catch(_:Exception){toast("تعذر فتح منصة بلدي") }
    }

    private fun openOfficialWhatsApp(){
        val url="https://chat.whatsapp.com/CWalJYwXsocKtYiqsJsMSh"
        db.audit(currentUserId,"OPEN","WHATSAPP_GROUP",url,"Opened official laboratory WhatsApp channel")
        try{startActivity(Intent(Intent.ACTION_VIEW,Uri.parse(url)))}catch(_:Exception){toast("تعذر فتح واتساب الرسمي")}
    }

    private fun sync(){
        header("المزامنة المركزية")
        val api=inp("عنوان الخادم (مثال: http://192.168.1.10:8080)",db.getSetting("central_api"));root.addView(api)
        val prefs=getSharedPreferences("central_sync",MODE_PRIVATE)
        val token=inp("رمز وصول مركزي Bearer",prefs.getString("access_token","") ?: "");root.addView(token)
        val centralUser=inp("اسم المستخدم أو الجوال المركزي",prefs.getString("central_user",currentUser) ?: currentUser);root.addView(centralUser)
        val centralPassword=inp("كلمة المرور المركزية");centralPassword.inputType=InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD;root.addView(centralPassword)
        val centralOtp=inp("رمز OTP المركزي");root.addView(centralOtp)
        val c=db.syncCounts(); root.addView(tv("الطابور: ${c[0]} معلقة | ${c[1]} تعارض | ${c[2]} فشلت",15f,true))
        root.addView(btn("حفظ الإعدادات"){db.setSetting("central_api",api.text.toString().trim());prefs.edit().putString("access_token",token.text.toString().trim()).apply();toast("تم حفظ إعدادات المزامنة")})
        root.addView(btn("طلب رمز الدخول المركزي"){toast("جارٍ طلب الرمز…");Thread{val r=SyncClient(this,db).requestCentralOtp(api.text.toString(),centralUser.text.toString().trim(),centralPassword.text.toString());runOnUiThread{toast(r.message)}}.start()})
        root.addView(btn("تحقق واربط الحساب المركزي"){toast("جارٍ التحقق…");Thread{val r=SyncClient(this,db).verifyCentralOtp(api.text.toString(),centralUser.text.toString().trim(),centralOtp.text.toString().trim());runOnUiThread{if(r.token!=null){token.setText(r.token);prefs.edit().putString("access_token",r.token).putString("central_user",centralUser.text.toString().trim()).apply()};toast(r.message)}}.start()})
        root.addView(btn("رفع الطابور الآن"){db.setSetting("central_api",api.text.toString().trim());prefs.edit().putString("access_token",token.text.toString().trim()).apply();toast("جارٍ رفع العمليات…");Thread{val r=SyncClient(this,db).upload(api.text.toString(),token.text.toString());runOnUiThread{toast(r.message);sync()}}.start()})
        root.addView(btn("إعادة محاولة العمليات الفاشلة"){db.retryFailedSync();toast("أعيدت العمليات الفاشلة إلى الطابور");sync()})
        root.addView(btn("مراجعة التعارضات المحلية (${c[1]})"){syncConflicts()})
        root.addView(tv("العمل يبقى محلياً عند انقطاع الشبكة. تُرسل العملية مرة واحدة بشكل idempotent، وتُحفظ التعارضات محلياً للمراجعة. استخدم HTTPS ورمزاً صادراً من الخادم في الإنتاج.",13f));mount()
    }
    private fun syncConflicts(){
        header("تعارضات المزامنة",{sync()}); val rows=db.openSyncConflicts()
        if(rows.isEmpty()) root.addView(tv("لا توجد تعارضات مفتوحة",16f,true))
        rows.forEach { r -> val id=r[0]?.toIntOrNull() ?: return@forEach
            root.addView(tv("${r[1]} / ${r[2]}\nالمحلي: ${r[3]}\nالخادم: ${r[4]}\n${r[5]}",13f))
            root.addView(btn("إبقاء النسخة المحلية وإعادة رفعها"){db.keepLocalConflict(id);toast("أعيدت النسخة المحلية للطابور");syncConflicts()})
            root.addView(btn("قبول نسخة الخادم وإغلاق التعارض"){db.acceptRemoteConflict(id);toast("تم إغلاق التعارض");syncConflicts()})
        }; mount()
    }
    private fun backup(){val f=FileExport.export(this,db.exportSql());alert("نسخة احتياطية","تم إنشاء Backup:\n${f.absolutePath}\n\nللاعتماد النهائي يجب حفظ نسخة دورية على خادم مركزي وموقع احتياطي منفصل.")}
    private fun testSettings(){if(currentRole!="admin"&&currentRole!="reviewer"){toast("غير مصرح");return};header("إعدادات الاختبارات وحدود القبول");val code=inp("كود الاختبار");val min=inp("الحد الأدنى");val max=inp("الحد الأعلى");val unit=inp("الوحدة");root.addView(code);root.addView(min);root.addView(max);root.addView(unit);root.addView(btn("+ حفظ حدود القبول"){val a=min.text.toString().toDoubleOrNull();val b=max.text.toString().toDoubleOrNull();if(code.text.isNotBlank()&&a!=null&&b!=null){db.writableDatabase.execSQL("INSERT INTO result_limits(test_code,min_value,max_value,unit,version,active) VALUES(?,?,?,?,?,1)",arrayOf(code.text.toString(),a,b,unit.text.toString(),"Current"));toast("تم الحفظ")}});mount()}

    private fun showQr(title:String,value:String){val image=ImageView(this).apply{setImageBitmap(QrCodeUtil.create(value,720));adjustViewBounds=true};AlertDialog.Builder(this).setTitle("QR — $title").setView(image).setMessage(value).setPositiveButton("موافق",null).show()}
    private fun exportReportPdf(no:String){val row=db.getReport(no)?:return;val f=ReportExport.createPdf(this,row);toast("تم إنشاء PDF: ${f.name}")}
    private fun shareReportPdf(no:String){val row=db.getReport(no)?:return;val f=ReportExport.createPdf(this,row);val uri=FileProvider.getUriForFile(this,"${applicationContext.packageName}.fileprovider",f);startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).apply{type="application/pdf";putExtra(Intent.EXTRA_STREAM,uri);addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)},"مشاركة التقرير"))}
    private fun alert(t:String,m:String){AlertDialog.Builder(this).setTitle(t).setMessage(m).setPositiveButton("موافق",null).show()}
    private fun toast(s:String)=Toast.makeText(this,s,Toast.LENGTH_LONG).show()
}
