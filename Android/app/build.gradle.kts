import java.io.FileInputStream
import java.util.Properties

plugins {
    id("com.android.application")
    id("com.chaquo.python")
}

android {
    namespace = "com.jmcomic.android"
    compileSdk {
        version = release(37)
    }

    defaultConfig {
        applicationId = "com.jmcomic.android"
        minSdk = 24
        targetSdk = 37
        versionCode = 14
        versionName = "1.02"

        // Chaquopy 的 Python 解释器是原生库，必须显式声明 ABI
        ndk {
            abiFilters += listOf("arm64-v8a", "x86_64")
        }
    }

    buildFeatures {
        viewBinding = true
    }

    signingConfigs {
        // 从 local.properties 读，避免把密码写进仓库
        create("release") {
            val props = Properties()
            val propFile = rootProject.file("local.properties")
            if (propFile.exists()) {
                val stream = FileInputStream(propFile)
                try {
                    props.load(stream)
                } finally {
                    stream.close()
                }
            }
            storeFile = rootProject.file(props.getProperty("jm.storeFile", "keystore/jm-release.jks"))
            storePassword = props.getProperty("jm.storePassword", "")
            keyAlias = props.getProperty("jm.keyAlias", "jm")
            keyPassword = props.getProperty("jm.keyPassword", "")
        }
    }

    buildTypes {
        release {
            signingConfig = signingConfigs.getByName("release")
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    packaging {
        resources {
            excludes += setOf(
                "META-INF/DEPENDENCIES",
                "META-INF/LICENSE*",
                "META-INF/NOTICE*",
                "META-INF/*.kotlin_module"
            )
        }
    }
}

chaquopy {
    defaultConfig {
        // 选 3.13：Chaquopy 17.1 的 Android 轮子覆盖最好的一档
        version = "3.13"
        // 构建机上的 Python 大版本必须与 app 一致（3.13）。
        // Windows 上 Chaquopy 会自动尝试 py -3.13 / py -3 / python；
        // 若自动探测失败，取消下面一行注释并改成你的解释器绝对路径：
        // buildPython("C:/Users/Chen/AppData/Local/Programs/Python/Python313/python.exe")

        pip {
            // 原生扩展（Chaquopy 提供 Android 轮子）
            install("pycryptodome")
            install("pillow")
            // 纯 Python
            install("PyYAML")
            // img2pdf 0.4 起把 pikepdf 变成了必装依赖，而 pikepdf 依赖 qpdf C++，
            // 没有 Android 轮子 → pip 会自动回退到 0.3.1（只依赖 Pillow）。
            // 这里显式钉住 0.3.1：既避免每次构建回溯，也避免哪天装不上。
            install("img2pdf==0.3.1")
            install("requests")
        }
    }
}

dependencies {
    implementation("androidx.appcompat:appcompat:1.6.1")
    implementation("com.google.android.material:material:1.10.0")
    implementation("androidx.recyclerview:recyclerview:1.3.2")
    implementation("androidx.constraintlayout:constraintlayout:2.1.4")
    // 代理认证：Android 的 HttpURLConnection 对 HTTPS CONNECT 的 407 处理不可靠，
    // 换成 OkHttp（3.14.x 是纯 Java、无 Kotlin 依赖，Java 调用最省事）
    implementation("com.squareup.okhttp3:okhttp:3.14.9")
}
