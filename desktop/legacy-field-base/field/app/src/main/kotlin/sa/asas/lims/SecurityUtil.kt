package sa.asas.lims

import java.security.MessageDigest
import java.security.SecureRandom

object SecurityUtil {
    fun hash(password: String, salt: String): String {
        val md = MessageDigest.getInstance("SHA-256")
        return md.digest((salt + password).toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) }
    }
    fun salt(): String {
        val b = ByteArray(16)
        SecureRandom().nextBytes(b)
        return b.joinToString("") { "%02x".format(it) }
    }
}
