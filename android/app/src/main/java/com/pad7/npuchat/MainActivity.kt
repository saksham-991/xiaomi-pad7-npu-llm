package com.pad7.npuchat

import android.annotation.SuppressLint
import android.app.Activity
import android.content.Context
import android.os.Handler
import android.os.Looper
import android.webkit.JavascriptInterface
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.appcompat.app.AppCompatActivity
import android.os.Bundle
import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.io.File
import java.io.FileOutputStream
import java.io.InputStreamReader
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors

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
            databaseEnabled = true
            mediaPlaybackRequiresUserGesture = false
        }
        web.setBackgroundColor(0xFF101014.toInt())
        web.webViewClient = WebViewClient()
        web.addJavascriptInterface(NpuBridge(this, web), "NPU")
        web.loadUrl("file:///android_asset/index.html")
    }

    override fun onBackPressed() {
        if (web.canGoBack()) web.goBack() else super.onBackPressed()
    }
}

class NpuBridge(private val act: Activity, private val web: WebView) {
    private val io = Executors.newSingleThreadExecutor()
    private val main = Handler(Looper.getMainLooper())
    private val prefs = act.getSharedPreferences("npu", Context.MODE_PRIVATE)

    private val filesDir get() = act.filesDir.absolutePath
    private val libDir get() = act.applicationInfo.nativeLibraryDir
    private val modelFile get() = File("$filesDir/models/model.gguf")
    private val ctxSize = 16384

    private fun emit(obj: JSONObject) {
        val s = obj.toString()
        main.post { web.evaluateJavascript("window.__npuEvent&&window.__npuEvent(${JSONObject.quote(s)})", null) }
    }

    private fun emit(type: String, block: JSONObject.() -> Unit = {}) {
        val o = JSONObject(); o.put("type", type); o.block(); emit(o)
    }

    @JavascriptInterface
    fun ensureEngine() {
        io.execute {
            try {
                if (!modelFile.exists()) { emit("engine") { put("state", "no_model") }; return@execute }
                if (health()) { emit("engine") { put("state", "ready") }; return@execute }
                emit("engine") { put("state", "starting") }
                startServer()
                var ok = false
                for (i in 0 until 90) {
                    Thread.sleep(1000)
                    if (health()) { ok = true; break }
                }
                emit("engine") {
                    put("state", if (ok) "ready" else "error")
                    if (!ok) put("msg", tailLog())
                }
            } catch (e: Exception) {
                emit("engine") { put("state", "error"); put("msg", e.message ?: "engine error") }
            }
        }
    }

    private fun health(): Boolean = try {
        val c = URL("http://127.0.0.1:8090/health").openConnection() as HttpURLConnection
        c.connectTimeout = 1500; c.readTimeout = 1500
        val ok = c.responseCode == 200
        c.disconnect(); ok
    } catch (_: Exception) { false }

    private fun startServer() {
        val lib = libDir
        val cmd = "cd $filesDir && mkdir -p models && " +
            "LD_LIBRARY_PATH=$lib ADSP_LIBRARY_PATH=$lib " +
            "GGML_HEXAGON_MM_SELECT=1 GGML_HEXAGON_HOSTBUF=1 " +
            "GGML_HEXAGON_POWER_MODE=sustained_high_performance " +
            "setsid $lib/libllama-server.so -m ${modelFile.absolutePath} " +
            "--device HTP0 -ngl 99 -t 4 -fa off -c $ctxSize -b 256 -ub 256 -np 1 " +
            "--host 127.0.0.1 --port 8090 --jinja --reasoning-format deepseek --no-webui " +
            "> $filesDir/server.log 2>&1 < /dev/null &"
        val p = ProcessBuilder("su", "-c", cmd).redirectErrorStream(true).start()
        p.waitFor()
    }

    private fun tailLog(): String = try {
        val f = File("$filesDir/server.log")
        if (f.exists()) f.readText().takeLast(600) else "no log"
    } catch (_: Exception) { "no log" }

    @JavascriptInterface
    fun downloadModel() {
        io.execute {
            try {
                val url = prefs.getString("model_url", DEFAULT_MODEL_URL)!!
                val dir = File("$filesDir/models"); dir.mkdirs()
                val tmp = File(dir, "model.tmp")
                var conn = URL(url).openConnection() as HttpURLConnection
                var redirects = 0
                while (conn.responseCode in 300..399 && redirects < 6) {
                    val loc = conn.getHeaderField("Location") ?: break
                    conn = URL(loc).openConnection() as HttpURLConnection
                    redirects++
                }
                val total = conn.contentLengthLong
                conn.inputStream.use { input ->
                    FileOutputStream(tmp).use { out ->
                        val buf = ByteArray(1 shl 20)
                        var done = 0L; var lastPct = -1
                        while (true) {
                            val n = input.read(buf); if (n <= 0) break
                            out.write(buf, 0, n); done += n
                            val pct = if (total > 0) ((done * 100) / total).toInt() else -1
                            if (pct != lastPct) {
                                lastPct = pct
                                emit("model") { put("state", "progress"); put("pct", pct); put("done", done); put("total", total) }
                            }
                        }
                    }
                }
                tmp.renameTo(modelFile)
                emit("model") { put("state", "ready"); put("size", modelFile.length()) }
            } catch (e: Exception) {
                emit("model") { put("state", "error"); put("msg", e.message ?: "download failed") }
            }
        }
    }

    @JavascriptInterface
    fun setModelUrl(url: String) { prefs.edit().putString("model_url", url).apply() }

    @JavascriptInterface
    fun chat(payload: String) {
        io.execute {
            try {
                val req = JSONObject(payload)
                val messages = req.getJSONArray("messages")
                val useSearch = req.optBoolean("search", false)
                val think = req.optBoolean("think", false)
                val maxTokens = req.optInt("max_tokens", 2048)

                var msgs = JSONArray()
                msgs.put(JSONObject().put("role", "system").put("content", SYSTEM_PROMPT))
                for (i in 0 until messages.length()) msgs.put(messages.getJSONObject(i))

                val lastUser = lastUserText(msgs)
                if (useSearch || Regex("(?i)^\\s*search\\b").containsMatchIn(lastUser)) {
                    val q = lastUser.replace(Regex("(?i)^\\s*search[:\\s]*"), "").trim().ifEmpty { lastUser }
                    val results = searchWeb(q, 5)
                    emit("search") { put("count", results.size); put("query", q) }
                    if (results.isNotEmpty()) {
                        val sb = StringBuilder("Web search results for '$q':\n\n")
                        results.forEachIndexed { i, r -> sb.append("[${i + 1}] ${r.title}\n${r.url}\n${r.snippet}\n\n") }
                        msgs.put(1, JSONObject().put("role", "system").put("content", sb.toString()))
                        msgs.put(2, JSONObject().put("role", "system").put("content", "Use the search results above when relevant. Cite as [n]."))
                    }
                }

                val joined = (0 until msgs.length()).joinToString("\n") { msgs.getJSONObject(it).getString("content") }
                val used = countTokens(joined)
                emit("usage") { put("tokens", used); put("ctx", ctxSize) }
                if (used > (ctxSize * 0.85).toInt() && msgs.length() > 2) {
                    try {
                        val summary = summarize(msgs)
                        emit("summary") { put("text", summary) }
                        val nm = JSONArray()
                        nm.put(JSONObject().put("role", "system")
                            .put("content", "Lossless summary of the earlier conversation (all technical details preserved):\n\n$summary"))
                        nm.put(msgs.getJSONObject(msgs.length() - 1))
                        msgs = nm
                    } catch (e: Exception) {
                        emit("summary_error") { put("error", e.message ?: "summary failed") }
                    }
                }

                streamChat(msgs, think, maxTokens)
                emit("done")
            } catch (e: Exception) {
                emit("error") { put("error", e.message ?: "chat failed") }
            }
        }
    }

    private fun lastUserText(msgs: JSONArray): String {
        for (i in msgs.length() - 1 downTo 0) {
            val m = msgs.getJSONObject(i)
            if (m.optString("role") == "user") return m.optString("content")
        }
        return ""
    }

    private fun countTokens(text: String): Int = try {
        val body = JSONObject().put("content", text).toString()
        val r = JSONObject(postJson("http://127.0.0.1:8090/tokenize", body))
        r.getJSONArray("tokens").length()
    } catch (_: Exception) { text.length / 4 }

    private fun summarize(msgs: JSONArray): String {
        val sb = StringBuilder()
        for (i in 0 until msgs.length()) {
            val m = msgs.getJSONObject(i)
            sb.append(m.getString("role").uppercase()).append(": ").append(m.getString("content")).append("\n")
        }
        val req = JSONObject()
        val arr = JSONArray()
        arr.put(JSONObject().put("role", "system").put("content", SUMMARY_PROMPT))
        arr.put(JSONObject().put("role", "user").put("content", sb.toString().take(24000)))
        req.put("messages", arr)
        req.put("max_tokens", 700).put("temperature", 0.2).put("stream", false)
        req.put("chat_template_kwargs", JSONObject().put("enable_thinking", false))
        val r = JSONObject(postJson("http://127.0.0.1:8090/v1/chat/completions", req.toString()))
        return r.getJSONArray("choices").getJSONObject(0).getJSONObject("message").getString("content").trim()
    }

    private fun streamChat(msgs: JSONArray, think: Boolean, maxTokens: Int) {
        val req = JSONObject()
        req.put("messages", msgs)
        req.put("stream", true).put("max_tokens", maxTokens).put("temperature", 0.7)
        req.put("chat_template_kwargs", JSONObject().put("enable_thinking", think))
        val c = URL("http://127.0.0.1:8090/v1/chat/completions").openConnection() as HttpURLConnection
        c.requestMethod = "POST"
        c.doOutput = true
        c.setRequestProperty("Content-Type", "application/json")
        c.readTimeout = 900_000
        c.outputStream.use { it.write(req.toString().toByteArray()) }
        BufferedReader(InputStreamReader(c.inputStream)).use { br ->
            var line: String?
            while (br.readLine().also { line = it } != null) {
                val l = line!!.trim()
                if (!l.startsWith("data:")) continue
                val d = l.substring(5).trim()
                if (d == "[DONE]") break
                try {
                    val ev = JSONObject(d)
                    val ch = ev.optJSONArray("choices")?.optJSONObject(0) ?: continue
                    val delta = ch.optJSONObject("delta") ?: continue
                    if (delta.has("reasoning_content") && !delta.isNull("reasoning_content")) {
                        emit("reasoning") { put("text", delta.getString("reasoning_content")) }
                    }
                    if (delta.has("content") && !delta.isNull("content")) {
                        emit("content") { put("text", delta.getString("content")) }
                    }
                } catch (_: Exception) {}
            }
        }
        c.disconnect()
    }

    private fun postJson(url: String, body: String): String {
        val c = URL(url).openConnection() as HttpURLConnection
        c.requestMethod = "POST"
        c.doOutput = true
        c.setRequestProperty("Content-Type", "application/json")
        c.readTimeout = 600_000
        c.outputStream.use { it.write(body.toByteArray()) }
        val out = c.inputStream.bufferedReader().readText()
        c.disconnect()
        return out
    }

    private data class Hit(val title: String, val url: String, val snippet: String)

    private fun searchWeb(query: String, n: Int): List<Hit> {
        try {
            val q = java.net.URLEncoder.encode(query, "UTF-8")
            val c = URL("https://r.jina.ai/https://html.duckduckgo.com/html/?q=$q").openConnection() as HttpURLConnection
            c.setRequestProperty("User-Agent", "curl/8.23.0")
            c.setRequestProperty("Accept", "text/plain")
            c.connectTimeout = 20_000; c.readTimeout = 45_000
            val txt = c.inputStream.bufferedReader().readText()
            c.disconnect()
            val out = ArrayList<Hit>()
            var cur: Hit? = null
            for (ln in txt.lines()) {
                val m = Regex("^#{2,3}\\s+\\[(.+?)\\]\\((https?://[^)]+)\\)").find(ln)
                if (m != null) {
                    cur?.let { if (it.snippet.isNotEmpty()) out.add(it) }
                    if (out.size >= n) break
                    var href = m.groupValues[2]
                    Regex("[?&]uddg=([^&]+)").find(href)?.let { href = java.net.URLDecoder.decode(it.groupValues[1], "UTF-8") }
                    cur = Hit(m.groupValues[1], href, "")
                    continue
                }
                val t = ln.replace(Regex("!?\\[[^\\]]*]\\([^)]*\\)"), "")
                    .replace(Regex("<[^>]+>"), "").replace("&amp;", "&").trim()
                if (cur != null && t.length > 24 && !t.startsWith("http") && !t.contains("DuckDuckGo"))
                    cur = cur.copy(snippet = (cur.snippet + " " + t).trim().take(400))
            }
            cur?.let { if (it.snippet.isNotEmpty() && out.size < n) out.add(it) }
            if (out.isNotEmpty()) return out
        } catch (_: Exception) {}
        return try {
            val q = java.net.URLEncoder.encode(query, "UTF-8")
            val c = URL("https://api.duckduckgo.com/?q=$q&format=json&no_html=1").openConnection() as HttpURLConnection
            c.connectTimeout = 20_000; c.readTimeout = 30_000
            val d = JSONObject(c.inputStream.bufferedReader().readText())
            val out = ArrayList<Hit>()
            if (d.optString("AbstractText").isNotEmpty())
                out.add(Hit(d.optString("Heading"), d.optString("AbstractURL"), d.optString("AbstractText").take(400)))
            val rel = d.optJSONArray("RelatedTopics") ?: JSONArray()
            for (i in 0 until rel.length()) {
                if (out.size >= n) break
                val o = rel.optJSONObject(i) ?: continue
                val t = o.optString("Text")
                if (t.isNotEmpty()) out.add(Hit(t.substringBefore(" - "), o.optString("FirstURL"), t.take(400)))
            }
            out
        } catch (_: Exception) { emptyList() }
    }

    companion object {
        private const val DEFAULT_MODEL_URL =
            "https://huggingface.co/LiquidAI/LFM2-1.2B-GGUF/resolve/main/LFM2-1.2B-Q4_0.gguf"
        private const val SYSTEM_PROMPT =
            "You are a local engineering SLM running on this tablet's Hexagon NPU. Expertise: coding " +
            "(Python/C/C++/Rust/Kotlin/Java/SQL), systems engineering, Linux sysadmin, Android app development, " +
            "software engineering, mathematics and physics. Reason internally when the problem needs it, then give " +
            "the shortest correct solution: exact commands, paths, versions and numbers. No filler, no boilerplate, " +
            "no over-engineering - simplest working answer first."
        private const val SUMMARY_PROMPT =
            "You are a lossless context compactor for an ongoing technical conversation. Rewrite the conversation " +
            "as dense bullets preserving EVERY technical detail (paths, commands, versions, errors, symptoms, root " +
            "causes, fixes, numbers, decisions, open questions, latest state). End with a bullet LATEST:. English only."
    }
}
