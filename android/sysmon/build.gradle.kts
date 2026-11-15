plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.pad7.sysmon"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.pad7.sysmon"
        minSdk = 26
        targetSdk = 34
        versionCode = 1
        versionName = "1.0"
    }
    signingConfigs {
        create("stable") {
            storeFile = file("../app/keystore.jks")
            storePassword = System.getenv("KS_PASS") ?: "npuchat123"
            keyAlias = "npu"
            keyPassword = System.getenv("KS_PASS") ?: "npuchat123"
        }
    }
    buildTypes {
        debug { signingConfig = signingConfigs.getByName("stable") }
        release { isMinifyEnabled = false; signingConfig = signingConfigs.getByName("stable") }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("com.google.android.material:material:1.12.0")
}
