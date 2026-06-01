package com.projspec.util

import com.intellij.execution.configurations.GeneralCommandLine
import com.intellij.ide.BrowserUtil
import com.intellij.openapi.project.Project
import java.io.File

/**
 * Helpers for the "Open with…" kebab-menu entries in each project widget.
 *
 * VSCode equivalent: the `openWith` message handler in panel.ts, which
 * shells out to `code`, `xdg-open`/`open`/`explorer`, `pycharm`, and
 * `jupyter lab` respectively.
 *
 * In PyCharm we reuse the same external binaries where available.  The
 * caller must have `code`, `pycharm`, and `jupyter` on PATH for those
 * entries to work.  Invocations are fire-and-forget — errors surface as a
 * balloon notification but never block the UI.
 */
object OpenWithHelper {

    /** Strip any leading `file://` prefix so the result can be passed as a path. */
    fun urlToPath(url: String): String =
        if (url.startsWith("file://")) url.removePrefix("file://") else url

    /**
     * Launch a visual-code editor on the given project directory.
     * Uses the `code` CLI wrapper that ships with VSCode.
     */
    fun openWithVSCode(project: Project, url: String) {
        val path = urlToPath(url)
        spawn(project, listOf("code", path))
    }

    /**
     * Open the OS file browser at the given path.
     *
     * Uses platform-specific launchers first (open/explorer/xdg-open).
     * Falls back to IntelliJ's BrowserUtil which is reliable across all
     * IDE deployment modes including JetBrains Gateway / remote dev —
     * unlike java.awt.Desktop which is unreliable on Linux/headless.
     */
    fun openWithFileBrowser(project: Project, url: String) {
        val path = urlToPath(url)
        val osName = System.getProperty("os.name", "").lowercase()
        val cmd = when {
            osName.contains("mac") -> listOf("open", path)
            osName.contains("win") -> listOf("explorer", path)
            else                   -> listOf("xdg-open", path)
        }
        if (!spawn(project, cmd)) {
            // BrowserUtil handles the URI-to-browser dispatch reliably across
            // all IntelliJ Platform deployment modes, replacing the previous
            // java.awt.Desktop.open() call which fails in remote/headless contexts.
            BrowserUtil.browse(File(path).toURI())
        }
    }

    /**
     * Launch a standalone PyCharm instance on the directory (new window).
     * Matches the VSCode behaviour which always spawned `pycharm` as an
     * external process rather than reusing the current IDE.
     */
    fun openWithPyCharm(project: Project, url: String) {
        val path = urlToPath(url)
        spawn(project, listOf("pycharm", path, "nosplash", "dontReopenProjects"))
    }

    /** Launch `jupyter lab <path>`. */
    fun openWithJupyter(project: Project, url: String) {
        val path = urlToPath(url)
        spawn(project, listOf("jupyter", "lab", path))
    }

    /**
     * Spawn a detached subprocess using IntelliJ's GeneralCommandLine, which
     * handles cross-platform PATH resolution and argument quoting correctly —
     * replacing the previous direct java.lang.ProcessBuilder usage.
     *
     * Returns true on success, false if the binary could not be found or the
     * process failed to start.  Errors surface as a warning notification.
     */
    private fun spawn(project: Project, cmd: List<String>): Boolean {
        return try {
            GeneralCommandLine(cmd)
                .withRedirectErrorStream(true)
                .createProcess()
            true
        } catch (e: Exception) {
            Notifier.warning("Could not run ${cmd.joinToString(" ")}: ${e.message}", project)
            false
        }
    }
}
