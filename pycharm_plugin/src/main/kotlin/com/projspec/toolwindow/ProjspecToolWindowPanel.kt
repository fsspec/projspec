package com.projspec.toolwindow

import com.google.gson.Gson
import com.google.gson.JsonParser
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.diagnostic.Logger
import com.intellij.openapi.diagnostic.debug
import com.intellij.openapi.fileChooser.FileChooser
import com.intellij.openapi.fileChooser.FileChooserDescriptorFactory
import com.intellij.openapi.fileEditor.FileEditorManager
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.LocalFileSystem
import com.intellij.openapi.wm.ToolWindow
import com.intellij.ui.jcef.JBCefBrowser
import com.intellij.ui.jcef.JBCefJSQuery
import com.projspec.settings.ProjspecSettings
import com.projspec.util.CliResult
import com.projspec.util.Notifier
import com.projspec.util.OpenWithHelper
import com.projspec.util.ProjspecRunner
import com.projspec.util.TerminalRunner
import org.cef.browser.CefBrowser
import org.cef.browser.CefFrame
import org.cef.handler.CefLoadHandlerAdapter
import java.awt.BorderLayout
import java.io.File
import java.nio.file.Files
import java.nio.file.Paths
import java.util.concurrent.atomic.AtomicInteger
import javax.swing.JPanel

/**
 * The "Project Library" tool window panel.
 *
 * Port of vsextension/src/panel.ts (class `ProjspecPanel`) to IntelliJ's JCEF
 * (Chromium) browser component.  The HTML/CSS/JS page is lifted verbatim from
 * the VSCode panel (see [HtmlContent]) — this file is the Kotlin equivalent
 * of the panel's message-handling backend.
 *
 * Mapping:
 *   createWebviewPanel                → JBCefBrowser
 *   acquireVsCodeApi() / postMessage  → JBCefJSQuery (window.__javaBridge)
 *   panel.webview.onDidReceiveMessage → [handleJsMessage]
 *   panel.webview.postMessage         → [deliverToWebview] via executeJavaScript
 *   execSync / spawn                  → ProjspecRunner / OpenWithHelper
 *   showOpenDialog(folder)            → FileChooser.chooseFile (folder descriptor)
 *   createTerminal / sendText         → TerminalRunner
 */
class ProjspecToolWindowPanel(
    private val project: Project,
    @Suppress("unused") private val toolWindow: ToolWindow,
) : JPanel(BorderLayout()) {

    private val gson = Gson()
    private val browser: JBCefBrowser = JBCefBrowser()
    private val jsQuery: JBCefJSQuery = JBCefJSQuery.create(browser)

    // Cached data matching panel.ts's `info`, `enums` and `library` fields.
    @Volatile private var info: String = "null"           // raw JSON
    @Volatile private var enums: String = "{}"            // raw JSON
    @Volatile private var library: String = "{}"         // raw JSON
    @Volatile private var specNames: List<String> = emptyList()
    @Volatile private var libraryMap: Map<String, Any?> = emptyMap()

    /**
     * Reference count for in-flight operations.  The spinner is displayed
     * whenever this is > 0 — see panel.ts's `busyCount`.  Uses atomics so
     * the counter can be incremented from any background thread.
     */
    private val busyCount = AtomicInteger(0)

    /**
     * True once the webview has posted its initial `ready` message.  Until
     * then, calls to [deliverToWebview] are deferred because executeJavaScript
     * would simply drop the payload.
     */
    @Volatile private var webviewReady = false

    /** Any messages posted before the webview was ready. */
    private val pending = ArrayDeque<String>()

    /** Guards against starting the initial data load twice (onLoadEnd +
     *  the JS `ready` message both race to trigger it). */
    private val initialLoadStarted = java.util.concurrent.atomic.AtomicBoolean(false)

    init {
        jsQuery.addHandler { json ->
            handleJsMessage(json)
            null
        }

        browser.jbCefClient.addLoadHandler(object : CefLoadHandlerAdapter() {
            override fun onLoadEnd(b: CefBrowser?, frame: CefFrame?, httpStatusCode: Int) {
                if (frame?.isMain == true) injectBridge()
            }
        }, browser.cefBrowser)

        add(browser.component, BorderLayout.CENTER)

        browser.loadHTML(HtmlContent.buildHtml())

        // Kick off initial data load once the JS posts `ready`.
    }

    // ------------------------------------------------------------------------
    //  JS bridge
    // ------------------------------------------------------------------------

    /**
     * Register `window.__javaBridge` in the newly-loaded page so the panel JS
     * can call back into Kotlin.  The shim matches the one the VSCode webview
     * runtime injects automatically via `acquireVsCodeApi()`.
     *
     * After installing the bridge we call `window.__projspecBridgeReady()`
     * which flushes any messages the page JS queued before the bridge was
     * available (including the initial `ready` handshake).
     *
     * We also kick off the initial data load directly from here — relying
     * solely on the JS `ready` round-trip is fragile if the bridge install
     * and the page's inline script race; by triggering the first `reload()`
     * from Kotlin we guarantee the subprocess calls happen even if the JS
     * never manages to send `ready`.
     */
    private fun injectBridge() {
        val inject = jsQuery.inject(
            "msgJson",
            "function(response) {}",
            "function(error_code, error_message) {}",
        )
        browser.cefBrowser.executeJavaScript(
            """
            window.__javaBridge = {
                query: function(msgJson) { $inject }
            };
            if (typeof window.__projspecBridgeReady === 'function') {
                window.__projspecBridgeReady();
            }
            """.trimIndent(),
            browser.cefBrowser.url,
            0,
        )
        // Start the initial load exactly once, regardless of whether the
        // JS handshake arrives.
        if (!initialLoadStarted.getAndSet(true)) {
            webviewReady = true
            synchronized(pending) {
                while (pending.isNotEmpty()) {
                    val script = pending.removeFirst()
                    ApplicationManager.getApplication().invokeLater {
                        browser.cefBrowser.executeJavaScript(script, browser.cefBrowser.url, 0)
                    }
                }
            }
            pool { reload(initial = true) }
        }
    }

    /**
     * Deliver a message to the webview.  Mirrors `panel.webview.postMessage`.
     *
     * JCEF does not expose an inbound message channel the way VSCode does, so
     * we call a globally-installed handler (`window.__projspecDeliver`) via
     * `executeJavaScript`.  See the JS at the top of [HtmlContent.PANEL_JS].
     */
    private fun deliverToWebview(msg: Any) {
        val json = gson.toJson(msg)
        val script = "window.__projspecDeliver && window.__projspecDeliver($json);"
        if (!webviewReady) {
            synchronized(pending) { pending.addLast(script) }
            return
        }
        ApplicationManager.getApplication().invokeLater {
            browser.cefBrowser.executeJavaScript(script, browser.cefBrowser.url, 0)
        }
    }

    // ------------------------------------------------------------------------
    //  Busy indicator — counted so nested operations don't flicker the spinner
    // ------------------------------------------------------------------------

    private fun beginBusy() {
        if (busyCount.incrementAndGet() == 1) {
            deliverToWebview(mapOf("type" to "loading", "loading" to true))
        }
    }

    private fun endBusy() {
        if (busyCount.decrementAndGet() == 0) {
            deliverToWebview(mapOf("type" to "loading", "loading" to false))
        }
    }

    private fun withBusy(work: Runnable) {
        beginBusy()
        try { work.run() } finally { endBusy() }
    }

    // ------------------------------------------------------------------------
    //  Inbound message dispatch (JS → Kotlin)
    // ------------------------------------------------------------------------

    @Suppress("UNCHECKED_CAST")
    private fun handleJsMessage(rawJson: String) {
        LOG.debug { "JS→Kotlin: $rawJson" }
        val msg: Map<String, Any?> = try {
            gson.fromJson(rawJson, Map::class.java) as Map<String, Any?>
        } catch (e: Exception) {
            LOG.warn("Failed to parse JS message: $rawJson", e)
            return
        }
        when (msg["cmd"] as? String) {
            "ready"              -> onReady()
            "reload"             -> pool { reload(initial = false) }
            "add"                -> addProject()
            "configure"          -> configure()
            "openWith"           -> openWith(msg["tool"] as? String ?: "", msg["url"] as? String ?: "")
            "rescan"             -> pool { rescan(msg["url"] as? String ?: "") }
            "createSpec"         -> createSpecFor(msg["url"] as? String ?: "")
            "createSpecConfirmed"-> pool { createSpecConfirmed(
                msg["url"] as? String ?: "",
                msg["spec"] as? String ?: "",
            ) }
            "removeFromLibrary"  -> pool { removeFromLibrary(msg["url"] as? String ?: "") }
            "make"               -> make(
                msg["url"] as? String ?: "",
                msg["spec"] as? String,
                msg["artifactType"] as? String ?: "",
                msg["name"] as? String,
            )
            "copyToLocal"        -> Notifier.info("Copy to local: not implemented", project)
            "revealFile"         -> revealFile(msg["fn"] as? String ?: "")
            else -> { /* ignore */ }
        }
    }

    private fun pool(fn: () -> Unit) {
        ApplicationManager.getApplication().executeOnPooledThread {
            try { fn() } catch (e: Exception) {
                Notifier.error("projspec: ${e.message}", project)
            }
        }
    }

    private fun onReady() {
        // If injectBridge() already kicked things off, the JS `ready`
        // message is just a late confirmation and has nothing to do.
        if (initialLoadStarted.getAndSet(true)) return
        webviewReady = true
        synchronized(pending) {
            while (pending.isNotEmpty()) {
                val script = pending.removeFirst()
                ApplicationManager.getApplication().invokeLater {
                    browser.cefBrowser.executeJavaScript(script, browser.cefBrowser.url, 0)
                }
            }
        }
        pool { reload(initial = true) }
    }

    // ------------------------------------------------------------------------
    //  Data loading
    // ------------------------------------------------------------------------

    /**
     * Fetch `info`, enum members, and the library listing, then push the
     * combined payload to the webview.  On the first call we also load the
     * enum members (panel.ts refreshes them only on `initial`).
     */
    private fun reload(initial: Boolean) {
        LOG.info("reload(initial=$initial) starting")
        withBusy {
            if (initial || info == "null") {
                LOG.info("running: projspec info")
                when (val res = ProjspecRunner.runInfo()) {
                    is CliResult.Success -> info = ProjspecRunner.extractJson(res.stdout).ifEmpty { "null" }
                    is CliResult.Failure -> {
                        Notifier.error("projspec info: ${res.message}", project)
                        info = "null"
                    }
                }
                enums = ProjspecRunner.runEnumMembers().ifBlank { "{}" }
                specNames = extractCreatableSpecs(info)
            }
            LOG.info("running: projspec library list --json-out")
            when (val res = ProjspecRunner.runLibraryList()) {
                is CliResult.Success -> {
                    val extracted = ProjspecRunner.extractJson(res.stdout)
                    library = extracted.ifEmpty { "{}" }
                    libraryMap = parseMap(library)
                }
                is CliResult.Failure -> {
                    Notifier.error("projspec library list: ${res.message}", project)
                    library = "{}"
                    libraryMap = emptyMap()
                }
            }
            postData()
            LOG.info("reload complete; library has ${libraryMap.size} entries")
        }
    }

    private fun postData() {
        // Build the payload as a raw JSON string to preserve the webview's
        // expected shape without re-serialising through Kotlin types.
        val script = """
            (function(){
              var msg = {type:'data', info: $info, enums: $enums, library: $library};
              window.__projspecDeliver && window.__projspecDeliver(msg);
            })();
        """.trimIndent()
        if (!webviewReady) {
            synchronized(pending) { pending.addLast(script) }
            return
        }
        ApplicationManager.getApplication().invokeLater {
            browser.cefBrowser.executeJavaScript(script, browser.cefBrowser.url, 0)
        }
    }

    /** Parse a JSON object string into a Map, or an empty map on failure. */
    @Suppress("UNCHECKED_CAST")
    private fun parseMap(json: String): Map<String, Any?> =
        try { gson.fromJson(json, Map::class.java) as Map<String, Any?> }
        catch (_: Exception) { emptyMap() }

    /**
     * Extract the snake-case names of every spec marked `create: true` in the
     * `info` payload.  Used to pre-populate the Create-spec modal.
     */
    private fun extractCreatableSpecs(rawInfo: String): List<String> {
        val out = mutableListOf<String>()
        try {
            val root = JsonParser.parseString(rawInfo)
            if (!root.isJsonObject) return out
            val specs = root.asJsonObject.getAsJsonObject("specs") ?: return out
            for ((name, entry) in specs.entrySet()) {
                if (entry.isJsonObject && entry.asJsonObject.has("create") &&
                    entry.asJsonObject.get("create").asBoolean) {
                    out += name
                }
            }
        } catch (_: Exception) {}
        return out.sorted()
    }

    // ------------------------------------------------------------------------
    //  Toolbar actions
    // ------------------------------------------------------------------------

    /**
     * "Add" button — open a folder picker, scan the chosen path, reload.
     *
     * VSCode: `showOpenDialog({ canSelectFolders: true })` + `projspec scan --library`.
     */
    private fun addProject() {
        ApplicationManager.getApplication().invokeLater {
            val descriptor = FileChooserDescriptorFactory.createSingleFolderDescriptor()
                .withTitle("Add to Library")
            val chosen = FileChooser.chooseFile(descriptor, project, null) ?: return@invokeLater
            val target = chosen.path
            pool {
                withBusy {
                    val res = ProjspecRunner.runScan(target)
                    if (res is CliResult.Failure) {
                        Notifier.warning("projspec scan: ${res.message}", project)
                    }
                    reload(initial = false)
                }
            }
        }
    }

    /**
     * "Configure" button — open the user's projspec.json (creating a default
     * if needed) in an editor tab.  Matches the VSCode panel behaviour.
     */
    private fun configure() {
        val dir = System.getenv("PROJSPEC_CONFIG_DIR")
            ?: Paths.get(System.getProperty("user.home"), ".config", "projspec").toString()
        val file = File(dir, "projspec.json")
        try {
            if (!file.exists()) {
                file.parentFile?.mkdirs()
                file.writeText(DEFAULT_CONFIG)
            }
        } catch (e: Exception) {
            Notifier.error("Could not write ${file.path}: ${e.message}", project)
            return
        }
        val vf = LocalFileSystem.getInstance().refreshAndFindFileByIoFile(file)
        if (vf != null) {
            ApplicationManager.getApplication().invokeLater {
                FileEditorManager.getInstance(project).openFile(vf, true)
            }
            Notifier.info(
                "ProjSpec configuration — <a href=\"https://projspec.readthedocs.io/en/latest/config.html\">see the docs</a> for all available fields.",
                project
            )
        } else {
            Notifier.error("Could not open ${file.path}", project)
        }
    }

    // ------------------------------------------------------------------------
    //  Kebab-menu actions
    // ------------------------------------------------------------------------

    private fun openWith(tool: String, url: String) {
        when (tool) {
            "vscode"      -> OpenWithHelper.openWithVSCode(project, url)
            "filebrowser" -> OpenWithHelper.openWithFileBrowser(project, url)
            "pycharm"     -> OpenWithHelper.openWithPyCharm(project, url)
            "jupyter"     -> OpenWithHelper.openWithJupyter(project, url)
        }
    }

    private fun rescan(url: String) {
        withBusy {
            val path = OpenWithHelper.urlToPath(url)
            val res = ProjspecRunner.runScan(path)
            if (res is CliResult.Failure) {
                Notifier.warning("projspec scan: ${res.message}", project)
            }
            reload(initial = false)
        }
    }

    /**
     * Show the create-spec modal — but first filter the known spec list by
     * what is *not* already present in the selected project.  Mirrors the
     * VSCode panel's `createSpecFor` handler.
     */
    private fun createSpecFor(url: String) {
        val existing: Set<String> = try {
            @Suppress("UNCHECKED_CAST")
            val proj = libraryMap[url] as? Map<String, Any?> ?: emptyMap()
            (proj["specs"] as? Map<String, Any?>)?.keys ?: emptySet()
        } catch (_: Exception) { emptySet() }

        val creatable = specNames.filter { it !in existing }
        if (creatable.isEmpty()) {
            Notifier.info("No spec types available to create.", project)
            return
        }
        deliverToWebview(mapOf(
            "type" to "openCreateSpecModal",
            "url" to url,
            "specs" to creatable,
        ))
    }

    private fun createSpecConfirmed(url: String, spec: String) {
        withBusy {
            val path = OpenWithHelper.urlToPath(url)
            val createRes = ProjspecRunner.runCreate(spec, path)
            if (createRes is CliResult.Failure) {
                Notifier.warning("projspec create: ${createRes.message}", project)
            }
            ProjspecRunner.runScan(path)
            reload(initial = false)
        }
    }

    private fun removeFromLibrary(url: String) {
        withBusy {
            val res = ProjspecRunner.runLibraryDelete(url)
            if (res is CliResult.Failure) {
                Notifier.warning("projspec library delete: ${res.message}", project)
            }
            reload(initial = false)
        }
    }

    // ------------------------------------------------------------------------
    //  Artifact widget actions
    // ------------------------------------------------------------------------

    /**
     * Run `projspec make <spec>.<artifactType>[.<name>] <projectPath>` in a
     * terminal tab so the user can watch the build.
     */
    private fun make(url: String, spec: String?, artifactType: String, name: String?) {
        val parts = buildList {
            if (!spec.isNullOrBlank()) add(spec)
            add(artifactType)
            if (!name.isNullOrBlank()) add(name)
        }
        if (parts.size < 1) return
        val artifactArg = parts.joinToString(".")
        val projectPath = OpenWithHelper.urlToPath(url)
        val cli = ProjspecSettings.instance.cliPath
        ApplicationManager.getApplication().invokeLater {
            TerminalRunner.makeArtifact(project, artifactArg, projectPath, cli)
        }
    }

    /**
     * Reveal a file in the Project tool window.  Accepts a local path or a
     * `file://` URL, expands simple wildcard patterns (e.g. a wheel glob such
     * as `dist` + `/` + `*.whl`), and opens the first match via
     * `FileEditorManager`.  Remote URLs are ignored with an info notification.
     */
    private fun revealFile(fn: String) {
        if (fn.isBlank()) return
        val local = if (fn.startsWith("file://")) fn.removePrefix("file://") else fn
        if (Regex("^[a-z][a-z0-9+.-]*://", RegexOption.IGNORE_CASE).containsMatchIn(local)) {
            Notifier.info("Cannot reveal remote file: $fn", project)
            return
        }
        val matches = expandGlob(local)
        if (matches.isEmpty()) {
            Notifier.info("No files match: $fn", project)
            return
        }
        val target = matches.first()
        val vf = LocalFileSystem.getInstance().refreshAndFindFileByPath(target)
        if (vf == null) {
            Notifier.warning("Could not reveal $target", project)
            return
        }
        ApplicationManager.getApplication().invokeLater {
            FileEditorManager.getInstance(project).openFile(vf, true)
        }
    }

    /** Expand `*` and `?` wildcards in a single path segment or whole path. */
    private fun expandGlob(pattern: String): List<String> {
        if (!pattern.contains('*') && !pattern.contains('?') && !pattern.contains('[')) {
            return if (Files.exists(Paths.get(pattern))) listOf(pattern) else emptyList()
        }
        val isAbsolute = pattern.startsWith('/')
        val parts = pattern.split('/').filter { it.isNotEmpty() }
        var current: List<String> = listOf(if (isAbsolute) "/" else ".")
        for (seg in parts) {
            val re = globSegmentToRegex(seg)
            val next = mutableListOf<String>()
            for (dir in current) {
                val d = File(dir)
                if (!d.isDirectory) continue
                for (entry in d.list() ?: emptyArray()) {
                    if (re.matches(entry)) {
                        next += File(d, entry).path
                    }
                }
            }
            current = next
        }
        return current
    }

    private fun globSegmentToRegex(seg: String): Regex {
        val sb = StringBuilder("^")
        for (ch in seg) {
            when (ch) {
                '*' -> sb.append("[^/]*")
                '?' -> sb.append("[^/]")
                '.', '+', '^', '$', '{', '}', '(', ')', '|', '\\' ->
                    sb.append('\\').append(ch)
                else -> sb.append(ch)
            }
        }
        sb.append('$')
        return Regex(sb.toString())
    }

    private companion object {
        private val LOG = Logger.getInstance(ProjspecToolWindowPanel::class.java)

        /** Written by the "Configure" button when the file does not exist. */
        private val DEFAULT_CONFIG = """
            {
                "scan_types": [".py", ".yaml", ".yml", ".toml", ".json", ".md"],
                "scan_max_files": 100,
                "scan_max_size": 5000,
                "remote_artifact_status": false,
                "capture_artifact_output": true,
                "preferred_install_methods": ["conda", "pip"]
            }
        """.trimIndent()
    }
}
