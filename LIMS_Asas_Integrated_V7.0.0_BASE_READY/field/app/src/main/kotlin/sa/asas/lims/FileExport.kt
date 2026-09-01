package sa.asas.lims
import android.content.Context
import java.io.File
object FileExport {
    fun export(ctx: Context, data: String): File {
        val dir = File(ctx.getExternalFilesDir(null), "Backups")
        if (!dir.exists()) dir.mkdirs()
        val f = File(dir, "LIMS_Asas_Backup_${System.currentTimeMillis()}.txt")
        f.writeText(data, Charsets.UTF_8)
        return f
    }
}
