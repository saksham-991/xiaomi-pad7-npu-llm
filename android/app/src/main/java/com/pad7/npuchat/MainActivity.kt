package com.pad7.npuchat

import android.annotation.SuppressLint
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.View
import android.view.WindowInsets
import android.view.WindowInsetsController
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.appcompat.app.AppCompatActivity
import java.net.HttpURLConnection
import java.net.URL

class MainActivity : AppCompatActivity() {
    private lateinit var web: WebView
    private val main = Handler(Looper.getMainLooper())
    private var started = false

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        web = findViewById(R.id.web)

        web.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            allowFileAccess = true
            databaseEnabled = true
            mediaPlaybackRequiresUserGesture = false
            useWideViewPort = true
            loadWithOverviewMode = true
            setSupportZoom(false)
            builtInZoomControls = false
            displayZoomControls = false
            textZoom = 100
        }
        web.setBackgroundColor(0xFF000000.toInt())
        web.webViewClient = WebViewClient()
        web.loadDataWithBaseURL(null, splash("Starting NPU engine…"), "text/html", "utf-8", null)

        goFullscreen()
        bootBackend()
    }

    private fun goFullscreen() {
        window.decorView.post {
            val c = if (android.os.Build.VERSION.SDK_INT >= 30) window.insetsController else null
            if (c != null) {
                c.hide(WindowInsets.Type.systemBars())
                c.systemBarsBehavior = WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            } else {
                @Suppress("DEPRECATION")
                window.decorView.systemUiVisibility = (View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                        or View.SYSTEM_UI_FLAG_FULLSCREEN
                        or View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                        or View.SYSTEM_UI_FLAG_LAYOUT_STABLE)
            }
        }
    }

    private fun splash(msg: String): String = """
        <html><head><meta name="viewport" content="width=device-width,initial-scale=1">
        <style>
        html,body{height:100%;margin:0;background:#000;color:#eee;font-family:system-ui,sans-serif}
        .w{height:100%;display:grid;place-items:center;text-align:center}
        .o{width:64px;height:64px;border-radius:50%;margin:0 auto 18px;
           background:conic-gradient(from 0deg,#fff,#444,#fff);animation:s 1s linear infinite}
        @keyframes s{to{transform:rotate(360deg)}}
        .m{color:#9a9aa0;font-size:13px;max-width:80vw;white-space:pre-wrap}
        </style></head><body><div class="w"><div><div class="o"></div><div class="m">$msg</div></div></div></body></html>
    """.trimIndent()

    private fun bootBackend() {
        if (started) return
        started = true
        Thread {
            try {
                val cmds = listOf(
                    "setsid /data/local/tmp/qwen-npu/scripts/start-npu.sh >/data/local/tmp/qwen-npu/server.log 2>&1 </dev/null &",
                    "sleep 1; setsid /data/data/com.termux/files/usr/bin/python3 /data/data/com.termux/files/home/pad7-npu/app/server.py >/data/local/tmp/qwen-npu/ui.log 2>&1 </dev/null &"
                )
                for (c in cmds) {
                    val p = ProcessBuilder("su", "-c", c).redirectErrorStream(true).start()
                    p.waitFor()
                }
            } catch (_: Exception) {}

            var ok = false
            for (i in 0 until 60) {
                Thread.sleep(1000)
                if (httpOk("http://127.0.0.1:8088/")) { ok = true; break }
            }
            main.post {
                if (ok) {
                    web.loadUrl("http://127.0.0.1:8088/")
                } else {
                    web.loadDataWithBaseURL(null, splash("Could not start backend.\nGrant root (KernelSU) and tap to retry."), "text/html", "utf-8", null)
                    web.setOnClickListener {
                        web.setOnClickListener(null)
                        started = false
                        web.loadDataWithBaseURL(null, splash("Starting NPU engine…"), "text/html", "utf-8", null)
                        bootBackend()
                    }
                }
            }
        }.start()
    }

    private fun httpOk(url: String): Boolean = try {
        val c = URL(url).openConnection() as HttpURLConnection
        c.connectTimeout = 1500; c.readTimeout = 1500
        val ok = c.responseCode in 200..399
        c.disconnect(); ok
    } catch (_: Exception) { false }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) goFullscreen()
    }

    override fun onBackPressed() {
        if (web.canGoBack()) web.goBack() else moveTaskToBack(true)
    }
}
