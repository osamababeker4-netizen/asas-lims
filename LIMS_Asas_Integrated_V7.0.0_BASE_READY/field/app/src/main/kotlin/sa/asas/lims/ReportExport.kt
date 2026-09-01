package sa.asas.lims

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Paint
import android.graphics.Rect
import android.graphics.pdf.PdfDocument
import java.io.File

object ReportExport {
    fun createPdf(ctx: Context, report: Array<String?>): File {
        val dir = File(ctx.getExternalFilesDir(null), "Reports")
        if (!dir.exists()) dir.mkdirs()
        val file = File(dir, "${report[0]}.pdf")
        val doc = PdfDocument()
        val page = doc.startPage(PdfDocument.PageInfo.Builder(595, 842, 1).create())
        val canvas = page.canvas
        val paint = Paint().apply { textSize = 18f; isAntiAlias = true }
        val logo = BitmapFactory.decodeResource(ctx.resources, R.drawable.asas_official_logo)
        canvas.drawBitmap(logo, null, Rect(40, 28, 310, 108), paint)
        var y = 135f
        canvas.drawText("ASAS LIMS - Laboratory Report", 40f, y, paint); y += 34f
        paint.textSize = 15f
        canvas.drawText("Report No: ${report[0] ?: ""}", 40f, y, paint); y += 28f
        canvas.drawText("Test: ${report[1] ?: ""}", 40f, y, paint); y += 28f
        canvas.drawText("Sample No: ${report[2] ?: ""}", 40f, y, paint); y += 28f
        canvas.drawText("Result: ${report[3] ?: ""}", 40f, y, paint); y += 28f
        canvas.drawText("Date: ${report[4] ?: ""}", 40f, y, paint); y += 55f
        doc.finishPage(page)
        file.outputStream().use { doc.writeTo(it) }
        doc.close()
        return file
    }
}
