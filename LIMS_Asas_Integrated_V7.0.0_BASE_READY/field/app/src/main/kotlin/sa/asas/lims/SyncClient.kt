package sa.asas.lims

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.UUID

/** Uploads durable SQLite queue entries; network failure never rolls back field work. */
class SyncClient(private val context: Context, private val db: LimsDb) {
    data class Result(val message:String, val uploaded:Int=0, val conflicts:Int=0)
    data class AuthResult(val message:String, val token:String?=null)
    private fun post(url:String, body:JSONObject, token:String?=null):Pair<Int,String>{
        val c=(URL(url).openConnection() as HttpURLConnection).apply { requestMethod="POST";connectTimeout=10000;readTimeout=20000;doOutput=true;setRequestProperty("Content-Type","application/json");if(!token.isNullOrBlank())setRequestProperty("Authorization","Bearer $token") }
        c.outputStream.use{it.write(body.toString().toByteArray(Charsets.UTF_8))}
        return c.responseCode to ((if(c.responseCode in 200..299)c.inputStream else c.errorStream)?.bufferedReader()?.use{it.readText()} ?: "")
    }
    fun requestCentralOtp(api:String, username:String, password:String):AuthResult = try {
        val (code,raw)=post(api.trimEnd('/')+"/api/auth/login",JSONObject().put("username",username).put("password",password))
        val j=JSONObject(raw); if(code !in 200..299) AuthResult("تعذر طلب رمز الدخول المركزي") else AuthResult(if(j.has("otp")) "تم طلب الرمز. رمز بيئة التطوير: ${j.optString("otp")}" else "تم إرسال رمز التحقق إلى الجوال")
    } catch(e:Exception){AuthResult("تعذر الاتصال بالخادم المركزي")}
    fun verifyCentralOtp(api:String, username:String, otp:String):AuthResult = try {
        val (code,raw)=post(api.trimEnd('/')+"/api/auth/verify",JSONObject().put("username",username).put("otp",otp))
        val j=JSONObject(raw); val token=j.optString("token"); if(code !in 200..299 || token.isBlank()) AuthResult("رمز التحقق غير صحيح أو انتهت صلاحيته") else AuthResult("تم ربط الحساب المركزي",token)
    } catch(e:Exception){AuthResult("تعذر الاتصال بالخادم المركزي")}
    fun upload(api:String, token:String): Result {
        val rows=db.pendingSyncRows()
        if(rows.isEmpty()) return Result("لا توجد عمليات معلقة")
        if(api.isBlank() || token.isBlank()) return Result("أدخل عنوان الخادم ورمز الوصول المركزي")
        val ids=rows.mapNotNull{it[0]?.toLongOrNull()}
        try {
            val events=JSONArray()
            rows.forEach { r -> events.put(JSONObject().put("id",r[0]?.toLong()).put("entity",r[1]).put("entityId",r[2]).put("operation",r[3]).put("payload",JSONObject(r[4] ?: "{}")).apply { r[6]?.toIntOrNull()?.let{put("baseVersion",it)} }) }
            val prefs=context.getSharedPreferences("central_sync",Context.MODE_PRIVATE)
            val device=prefs.getString("device_id",null) ?: UUID.randomUUID().toString().also { prefs.edit().putString("device_id",it).apply() }
            val url=api.trimEnd('/')+"/api/sync/queue"
            val (code,raw)=post(url,JSONObject().put("deviceId",device).put("events",events),token)
            if(code==401 || code==403){db.markSyncFailed(ids,"Authentication rejected ($code)");return Result("فشلت مصادقة الخادم؛ بقيت العمليات محلياً")}
            if(code !in 200..299){db.markSyncRetry(ids,"HTTP $code: $raw");return Result("تعذر الرفع، ستتم إعادة المحاولة لاحقاً")}
            val response=JSONObject(raw); val accepted=response.optJSONArray("accepted") ?: JSONArray(); val ok=(0 until accepted.length()).map{accepted.getJSONObject(it).getLong("id")}; db.markSyncAccepted(ok)
            val conflicts=response.optJSONArray("conflicts") ?: JSONArray(); for(i in 0 until conflicts.length()){val x=conflicts.getJSONObject(i);val id=x.getLong("id");val local=rows.firstOrNull{it[0]?.toLongOrNull()==id}?.get(4) ?: "{}";db.markSyncConflict(id,x.optString("entity"),x.optString("entityId"),local,x.optJSONObject("remotePayload")?.toString() ?: "{}")}
            return Result("تم رفع ${ok.size} عملية${if(conflicts.length()>0) "؛ ${conflicts.length()} تعارض يحتاج مراجعة" else ""}",ok.size,conflicts.length())
        } catch(e:Exception) { db.markSyncRetry(ids,e.message ?: e.javaClass.simpleName); return Result("لا يوجد اتصال بالخادم؛ بقيت العمليات في الطابور") }
    }
}
