package com.projspec.util

import com.google.gson.Gson
import com.google.gson.JsonParser
import java.io.File
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URI
import java.security.KeyStore
import java.security.SecureRandom
import java.security.cert.CertificateFactory
import java.util.concurrent.atomic.AtomicBoolean
import javax.net.ssl.HttpsURLConnection
import javax.net.ssl.SSLContext
import javax.net.ssl.TrustManagerFactory

/**
 * ProjspecServer — Kotlin equivalent of vsextension/src/serverClient.ts.
 *
 * Generates a random bearer token, writes a temp port file, then starts
 * `projspec serve --port-file <f> --token <token>` via a login shell.
 * The server writes "https:port:token:certHex" to the port file once ready.
 * This class reads it back, builds a pinned [SSLContext] from the DER cert,
 * and uses that for all subsequent HTTPS connections.
 *
 * Every request (except /ping during the startup poll) carries an
 * `Authorization: Bearer <token>` header.
 *
 * stdout and stderr are drained by dedicated daemon threads so the process
 * never blocks on a full pipe buffer, and all output is written to the
 * plugin log.
 *
 * If the server cannot start (fastapi / uvicorn not installed, binary not on
 * PATH, port conflict) every public method returns `null` and callers fall
 * back to the [ProjspecRunner] CLI approach.
 *
 * Lifecycle: call [start] once (off the EDT), [dispose] when the plugin is
 * torn down.  The singleton is managed by [ProjspecToolWindowPanel].
 */
class ProjspecServer {

    // -------------------------------------------------------------------------
    //  Configuration
    // -------------------------------------------------------------------------
    private val START_TIMEOUT_MS = 15_000L
    private val POLL_INTERVAL_MS = 200L

    // -------------------------------------------------------------------------
    //  State
    // -------------------------------------------------------------------------
    @Volatile private var port: Int = 0
    @Volatile private var token: String = ""
    @Volatile private var sslContext: SSLContext? = null
    @Volatile private var ready = false
    @Volatile private var disposed = false
    private var proc: Process? = null
    private var portFile: File? = null
    private val started = AtomicBoolean(false)
    private val gson = Gson()

    // -------------------------------------------------------------------------
    //  Token generation — 32 random bytes encoded as hex (256-bit)
    // -------------------------------------------------------------------------
    private fun generateToken(): String {
        val bytes = ByteArray(32)
        SecureRandom().nextBytes(bytes)
        return bytes.joinToString("") { "%02x".format(it) }
    }

    // -------------------------------------------------------------------------
    //  SSL — build a trust store pinned to a single DER-encoded certificate
    // -------------------------------------------------------------------------
    private fun buildSslContext(certDer: ByteArray): SSLContext {
        val cf = CertificateFactory.getInstance("X.509")
        val cert = cf.generateCertificate(certDer.inputStream())
        val ks = KeyStore.getInstance(KeyStore.getDefaultType()).also {
            it.load(null, null)
            it.setCertificateEntry("projspec", cert)
        }
        val tmf = TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm())
        tmf.init(ks)
        return SSLContext.getInstance("TLS").also {
            it.init(null, tmf.trustManagers, SecureRandom())
        }
    }

    // -------------------------------------------------------------------------
    //  Startup
    // -------------------------------------------------------------------------

    /** Generate a token, start `projspec serve --port-file …`, poll /ping. */
    fun start() {
        if (!started.compareAndSet(false, true)) return

        val chosenToken = generateToken()
        token = chosenToken

        // Temp file for port/cert discovery — analogous to VS Code's approach.
        val pf = File.createTempFile("projspec-server-", ".port")
        pf.deleteOnExit()
        portFile = pf

        PluginLogger.info("SERVER starting, port-file=${pf.absolutePath}")

        val shell = System.getenv("SHELL")?.takeIf { it.isNotBlank() } ?: "/bin/sh"
        fun shellQuote(s: String) = "'" + s.replace("'", "'\\''") + "'"
        fun shellCmd(vararg parts: String) =
            listOf(shell, "-l", "-c", parts.joinToString(" ") { shellQuote(it) })

        // Log which Python binary the shell resolves.
        try {
            val pb = ProcessBuilder(shellCmd("python", "-c", "import sys;print(sys.executable)"))
                .redirectErrorStream(true).start()
            val out = pb.inputStream.bufferedReader().readText().trim()
            pb.waitFor()
            PluginLogger.info("SERVER python executable: $out")
        } catch (e: Exception) {
            PluginLogger.warn("SERVER could not determine python executable: ${e.message}")
        }

        val pfPath = pf.absolutePath
        val proc =
            tryStart(shellCmd("projspec", "serve", "--port-file", pfPath, "--token", chosenToken))
            ?: tryStart(shellCmd("python", "-m", "projspec", "serve", "--port-file", pfPath, "--token", chosenToken))
        if (proc == null) {
            PluginLogger.warn("SERVER could not launch any process — CLI fallback will be used")
            return
        }
        this.proc = proc

        // Drain stdout/stderr so the process never blocks on a full pipe buffer.
        Thread({
            proc.inputStream.bufferedReader().forEachLine { PluginLogger.info("SERVER stdout: $it") }
            PluginLogger.info("SERVER stdout stream closed")
        }, "projspec-server-stdout").also { it.isDaemon = true; it.start() }

        Thread({
            proc.errorStream.bufferedReader().forEachLine { PluginLogger.info("SERVER stderr: $it") }
            PluginLogger.info("SERVER stderr stream closed")
        }, "projspec-server-stderr").also { it.isDaemon = true; it.start() }

        // Reap the process so isAlive() / exitValue() work correctly.
        Thread({
            try {
                val code = proc.waitFor()
                PluginLogger.info("SERVER process reaped, exit code=$code")
            } catch (_: InterruptedException) {}
        }, "projspec-server-reaper").also { it.isDaemon = true; it.start() }

        // Poll the port file until it contains the full "https:port:token:certHex" line.
        val deadline = System.currentTimeMillis() + START_TIMEOUT_MS
        while (System.currentTimeMillis() < deadline) {
            if (disposed) return
            if (!proc.isAlive) {
                Thread.sleep(200)
                PluginLogger.warn("SERVER process exited with code ${proc.exitValue()} — CLI fallback")
                return
            }
            try {
                val raw = pf.readText().trim()
                // Format: "https:port:token:certHex"
                val firstColon  = raw.indexOf(':')
                val secondColon = raw.indexOf(':', firstColon + 1)
                val thirdColon  = raw.indexOf(':', secondColon + 1)
                if (firstColon > 0 && secondColon > firstColon && thirdColon > secondColon) {
                    val parsedPort    = raw.substring(firstColon + 1, secondColon).toIntOrNull() ?: 0
                    val certHex       = raw.substring(thirdColon + 1)
                    if (parsedPort > 0 && certHex.isNotEmpty()) {
                        val certDer = certHex.chunked(2).map { it.toInt(16).toByte() }.toByteArray()
                        sslContext = buildSslContext(certDer)
                        // Confirm the server responds to /ping (no token needed)
                        getJsonOnPort(parsedPort, "/ping")
                        port = parsedPort
                        ready = true
                        PluginLogger.info("SERVER ready on https://127.0.0.1:$parsedPort (token auth + TLS cert pinned)")
                        return
                    }
                }
            } catch (_: Exception) { /* not ready yet */ }
            Thread.sleep(POLL_INTERVAL_MS)
        }
        PluginLogger.warn("SERVER timed out (${START_TIMEOUT_MS}ms), alive=${proc.isAlive} — CLI fallback")
    }

    // -------------------------------------------------------------------------
    //  Disposal
    // -------------------------------------------------------------------------
    fun dispose() {
        disposed = true
        proc?.destroyForcibly()
        proc = null
        ready = false
        try { portFile?.delete() } catch (_: Exception) {}
    }

    private fun tryStart(cmd: List<String>): Process? {
        // Redact token from log (argument after "--token")
        val logCmd = cmd.toMutableList()
        val tokenIdx = logCmd.indexOf("--token")
        if (tokenIdx >= 0 && tokenIdx + 1 < logCmd.size) logCmd[tokenIdx + 1] = "<redacted>"
        PluginLogger.info("SERVER trying: ${logCmd.joinToString(" ")}")
        return try {
            val process = ProcessBuilder(cmd)
                .redirectErrorStream(false)
                .start()
            PluginLogger.info("SERVER process launched, alive=${process.isAlive}")
            process
        } catch (e: Exception) {
            PluginLogger.info("SERVER tryStart failed: ${e.javaClass.simpleName}: ${e.message}")
            null
        }
    }

    // -------------------------------------------------------------------------
    //  HTTP/HTTPS helpers
    // -------------------------------------------------------------------------

    private fun openConnection(urlStr: String): HttpURLConnection {
        val url = URI.create(urlStr).toURL()
        val conn = url.openConnection()
        if (conn is HttpsURLConnection) {
            sslContext?.let { conn.sslSocketFactory = it.socketFactory }
        }
        return conn as HttpURLConnection
    }

    /** GET on the chosen port — used during startup poll (/ping, no token). */
    private fun getJsonOnPort(p: Int, path: String): String {
        val url = URI.create("https://127.0.0.1:$p$path").toURL()
        val conn = url.openConnection() as HttpsURLConnection
        sslContext?.let { conn.sslSocketFactory = it.socketFactory }
        conn.requestMethod = "GET"
        conn.connectTimeout = 2_000
        conn.readTimeout    = 5_000
        return conn.inputStream.bufferedReader().readText()
    }

    private fun getJson(path: String): String {
        val conn = openConnection("https://127.0.0.1:$port$path")
        conn.requestMethod = "GET"
        conn.connectTimeout = 5_000
        conn.readTimeout    = 60_000
        if (token.isNotBlank()) conn.setRequestProperty("Authorization", "Bearer $token")
        return conn.inputStream.bufferedReader().readText()
    }

    private fun postJson(path: String, body: Any): String {
        val json = gson.toJson(body)
        val conn = openConnection("https://127.0.0.1:$port$path")
        conn.requestMethod = "POST"
        conn.doOutput = true
        conn.setRequestProperty("Content-Type", "application/json")
        conn.connectTimeout = 5_000
        conn.readTimeout    = 60_000
        if (token.isNotBlank()) conn.setRequestProperty("Authorization", "Bearer $token")
        OutputStreamWriter(conn.outputStream, Charsets.UTF_8).use { it.write(json) }
        return conn.inputStream.bufferedReader().readText()
    }

    /**
     * Wait for the server to become ready, up to [START_TIMEOUT_MS].
     */
    private fun awaitReady(): Boolean {
        if (ready) return true
        if (disposed) return false
        if (!started.get()) return false
        val deadline = System.currentTimeMillis() + START_TIMEOUT_MS
        while (System.currentTimeMillis() < deadline) {
            if (ready) return true
            if (disposed) return false
            if (started.get() && proc?.isAlive == false && !ready) return false
            Thread.sleep(POLL_INTERVAL_MS)
        }
        return false
    }

    /** Returns the parsed JSON Map, or null if the server is not available. */
    private fun get(path: String): Map<String, Any?>? {
        if (!awaitReady()) { PluginLogger.info("SERVER get $path skipped (not ready)"); return null }
        val t0 = System.currentTimeMillis()
        return try {
            val raw = getJson(path)
            val ms = System.currentTimeMillis() - t0
            PluginLogger.info("SERVER GET $path -> ${raw.length}b (${ms}ms)")
            @Suppress("UNCHECKED_CAST")
            gson.fromJson(raw, Map::class.java) as Map<String, Any?>
        } catch (e: Exception) {
            val ms = System.currentTimeMillis() - t0
            PluginLogger.warn("SERVER GET $path FAILED (${ms}ms): ${e.javaClass.simpleName}: ${e.message}")
            null
        }
    }

    /** Returns the parsed JSON (Map or List), or null if the server is not available. */
    private fun post(path: String, body: Map<String, Any?>): Any? {
        if (!awaitReady()) { PluginLogger.info("SERVER post $path skipped (not ready)"); return null }
        val t0 = System.currentTimeMillis()
        val bodyJson = gson.toJson(body)
        PluginLogger.info("SERVER POST $path body=${bodyJson.take(200)}")
        return try {
            val raw = postJson(path, body)
            val ms = System.currentTimeMillis() - t0
            PluginLogger.info("SERVER POST $path -> ${raw.length}b (${ms}ms) preview=${raw.take(200)}")
            JsonParser.parseString(raw).let { el ->
                when {
                    el.isJsonObject -> gson.fromJson(raw, Map::class.java)
                    el.isJsonArray  -> gson.fromJson(raw, List::class.java)
                    else            -> null
                }
            }
        } catch (e: Exception) {
            val ms = System.currentTimeMillis() - t0
            PluginLogger.warn("SERVER POST $path FAILED (${ms}ms): ${e.javaClass.simpleName}: ${e.message}")
            null
        }
    }

    // -------------------------------------------------------------------------
    //  Public API — mirrors serverClient.ts method signatures
    // -------------------------------------------------------------------------

    fun info(): Map<String, Any?>?             = get("/info")
    fun enumMembers(): Map<String, Any?>?      = get("/enum_members")
    fun libraryList(): Map<String, Any?>?      = get("/library")
    fun protocols(): List<*>?                  = getList("/filebrowser/protocols")
    fun bookmarksList(): List<*>?              = getList("/filebrowser/bookmarks")

    fun libraryDelete(url: String): Boolean {
        val r = post("/library/delete", mapOf("url" to url))
        return r != null
    }

    fun scan(path: String, addToLibrary: Boolean, storageOptions: String? = null): Map<String, Any?>? =
        post("/scan", mapOf(
            "path" to path,
            "add_to_library" to addToLibrary,
            "storage_options" to storageOptions,
        )) as? Map<String, Any?>

    fun create(spec: String, path: String): Map<String, Any?>? =
        post("/create", mapOf("spec" to spec, "path" to path)) as? Map<String, Any?>

    // Filebrowser
    fun browse(url: String, so: Map<String, Any?>? = null): Map<String, Any?>? =
        post("/filebrowser/browse", mapOf("url" to url, "storage_options" to so)) as? Map<String, Any?>

    fun inspectAsProject(url: String, so: Map<String, Any?>? = null): Map<String, Any?>? =
        post("/filebrowser/inspect_as_project", mapOf("url" to url, "storage_options" to so)) as? Map<String, Any?>

    fun scanDirectory(url: String, so: Map<String, Any?>? = null): Map<String, Any?>? =
        post("/filebrowser/scan_directory", mapOf("url" to url, "storage_options" to so)) as? Map<String, Any?>

    fun readFile(url: String, so: Map<String, Any?>? = null, maxBytes: Int? = null): Map<String, Any?>? =
        post("/filebrowser/read_file", mapOf("url" to url, "storage_options" to so, "max_bytes" to maxBytes)) as? Map<String, Any?>

    fun writeFile(url: String, content: String, so: Map<String, Any?>? = null): Map<String, Any?>? =
        post("/filebrowser/write_file", mapOf("url" to url, "content" to content, "storage_options" to so)) as? Map<String, Any?>

    fun delete(url: String, recursive: Boolean, so: Map<String, Any?>? = null): Map<String, Any?>? =
        post("/filebrowser/delete", mapOf("url" to url, "recursive" to recursive, "storage_options" to so)) as? Map<String, Any?>

    fun move(src: String, dst: String, so: Map<String, Any?>? = null): Map<String, Any?>? =
        post("/filebrowser/move", mapOf("src" to src, "dst" to dst, "storage_options" to so)) as? Map<String, Any?>

    fun copy(src: String, dst: String, so: Map<String, Any?>? = null, confirmed: Boolean = false): Map<String, Any?>? =
        post("/filebrowser/copy", mapOf(
            "src" to src, "dst" to dst, "storage_options" to so, "confirmed" to confirmed,
        )) as? Map<String, Any?>

    fun totalSize(urls: List<String>, so: Map<String, Any?>? = null): Map<String, Any?>? =
        post("/filebrowser/total_size", mapOf(
            "urls" to urls, "storage_options" to so,
        )) as? Map<String, Any?>

    fun mkdir(url: String, so: Map<String, Any?>? = null): Map<String, Any?>? =
        post("/filebrowser/mkdir", mapOf("url" to url, "storage_options" to so)) as? Map<String, Any?>

    fun addToLibrary(url: String, so: Map<String, Any?>? = null): Map<String, Any?>? =
        post("/filebrowser/add_to_library", mapOf("url" to url, "storage_options" to so)) as? Map<String, Any?>

    fun bookmarkAdd(url: String, label: String? = null, so: Map<String, Any?>? = null): List<*>? {
        val r = post("/filebrowser/bookmarks/add",
                     mapOf("url" to url, "label" to (label ?: ""), "storage_options" to so))
        return r as? List<*>
    }

    fun bookmarkRemove(url: String): List<*>? {
        val r = post("/filebrowser/bookmarks/remove", mapOf("url" to url))
        return r as? List<*>
    }

    // -------------------------------------------------------------------------
    //  Helpers
    // -------------------------------------------------------------------------

    private fun getList(path: String): List<*>? {
        if (!awaitReady()) { PluginLogger.info("SERVER get $path skipped (not ready)"); return null }
        val t0 = System.currentTimeMillis()
        return try {
            val raw = getJson(path)
            val ms = System.currentTimeMillis() - t0
            PluginLogger.info("SERVER GET $path (list) -> ${raw.length}b (${ms}ms)")
            gson.fromJson(raw, List::class.java)
        } catch (e: Exception) {
            val ms = System.currentTimeMillis() - t0
            PluginLogger.warn("SERVER GET $path (list) FAILED (${ms}ms): ${e.javaClass.simpleName}: ${e.message}")
            null
        }
    }

    /** Parse a JSON storage-options string into a Map, or null. */
    fun parseSo(soJson: String?): Map<String, Any?>? {
        if (soJson.isNullOrBlank()) return null
        return try {
            @Suppress("UNCHECKED_CAST")
            gson.fromJson(soJson, Map::class.java) as Map<String, Any?>
        } catch (_: Exception) { null }
    }

    val isReady: Boolean get() = ready
}
