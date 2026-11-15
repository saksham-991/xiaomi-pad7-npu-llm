package com.pad7.sysmon

import android.annotation.SuppressLint
import android.os.Bundle
import android.webkit.JavascriptInterface
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.appcompat.app.AppCompatActivity
import java.io.File

class MainActivity : AppCompatActivity() {
    private lateinit var web: WebView

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        web = findViewById(R.id.web)
        web.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            allowFileAccess = true
            useWideViewPort = true
            loadWithOverviewMode = true
        }
        web.setBackgroundColor(0xFF0B0B10.toInt())
        web.webViewClient = WebViewClient()
        web.addJavascriptInterface(Bridge(this), "SysMon")
        web.loadUrl("file:///android_asset/index.html")
    }

    override fun onBackPressed() {
        if (web.canGoBack()) web.goBack() else moveTaskToBack(true)
    }

    class Bridge(private val act: MainActivity) {
        private fun sh(cmd: String): String = try {
            val p = ProcessBuilder("su", "-c", cmd).redirectErrorStream(true).start()
            val out = p.inputStream.bufferedReader().readText()
            p.waitFor()
            out
        } catch (e: Exception) { "ERR " + (e.message ?: "") }

        @JavascriptInterface
        fun start(): String {
            val dst = File(act.filesDir, "sysmon.sh")
            if (!dst.exists()) {
                act.assets.open("sysmon.sh").use { i -> dst.outputStream().use { o -> i.copyTo(o) } }
            }
            return sh("cp ${dst.absolutePath} /data/local/tmp/sysmon.sh; chmod 755 /data/local/tmp/sysmon.sh; pkill -f /data/local/tmp/sysmon.sh; setsid /data/local/tmp/sysmon.sh >/data/local/tmp/sysmon.log 2>&1 &")
        }

        @JavascriptInterface
        fun stats(): String {
            val f = File("/data/local/tmp/sysmon.json")
            if (f.exists() && f.canRead()) return f.readText()
            return sh("cat /data/local/tmp/sysmon.json 2>/dev/null")
        }

        @JavascriptInterface
        fun setInterval(sec: Int) {
            sh("echo ${sec.coerceIn(1, 10)} > /data/local/tmp/sysmon.interval")
        }

        @JavascriptInterface
        fun stop() {
            sh("pkill -f /data/local/tmp/sysmon.sh")
        }
    }
}
