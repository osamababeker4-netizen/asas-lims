plugins { id("com.android.application") }

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
        versionCode = 10
        versionName = "7.1.0"
    }
    buildTypes { release { isMinifyEnabled = false } }
}
