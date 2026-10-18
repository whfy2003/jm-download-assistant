pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
        // 国内镜像（放在后面，只作加速/兜底；Chaquopy 只发布在 Maven Central）
        maven { url = uri("https://maven.aliyun.com/repository/google") }
        maven { url = uri("https://maven.aliyun.com/repository/public") }
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
        maven { url = uri("https://maven.aliyun.com/repository/google") }
        maven { url = uri("https://maven.aliyun.com/repository/public") }
    }
}

rootProject.name = "JmComicAndroid"
include(":app")
