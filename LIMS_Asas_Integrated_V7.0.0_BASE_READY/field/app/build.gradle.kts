import java.io.FileInputStream
import java.util.Properties

plugins { id("com.android.application") }

val signingProperties = Properties()
val signingPropertiesFile = rootProject.file("release-signing.properties")
if (signingPropertiesFile.exists()) {
    FileInputStream(signingPropertiesFile).use { signingProperties.load(it) }
}

dependencies {
    implementation("com.google.zxing:core:3.5.3")
    implementation("androidx.core:core:1.15.0")
}

android {
    namespace = "sa.asas.lims"
    compileSdk = 36
    defaultConfig {
        applicationId = "sa.asas.lims"
        minSdk = 26
        targetSdk = 36
        versionCode = 14
        versionName = "7.2.1"
    }
    if (signingPropertiesFile.exists()) {
        signingConfigs {
            create("release") {
                storeFile = rootProject.file(signingProperties.getProperty("storeFile"))
                storePassword = signingProperties.getProperty("storePassword")
                keyAlias = signingProperties.getProperty("keyAlias")
                keyPassword = signingProperties.getProperty("keyPassword")
            }
        }
    }
    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.findByName("release")
        }
    }
}
