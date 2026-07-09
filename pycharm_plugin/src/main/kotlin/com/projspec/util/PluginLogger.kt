package com.projspec.util

import java.io.File
import java.io.FileWriter
import java.io.PrintWriter
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter

/**
 * File-based logger for the projspec PyCharm plugin.
 *
 * Writes timestamped lines to `<projspec-config-dir>/pycharm-plugin.log`
 * (default: `~/.config/projspec/pycharm-plugin.log`, overridden by the
 * `PROJSPEC_CONFIG_DIR` environment variable).
 *
 * All public methods are thread-safe.  The log file is appended to (not
 * truncated) across sessions so that problems spanning multiple IDE launches
 * can be diagnosed.  Lines are flushed immediately so the file is always
 * up-to-date even if the IDE crashes.
 */
object PluginLogger {

    private val TS = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss.SSS")

    private val logFile: File by lazy {
        val dir = File(
            System.getenv("PROJSPEC_CONFIG_DIR")
                ?: "${System.getProperty("user.home")}/.config/projspec"
        )
        dir.mkdirs()
        File(dir, "pycharm-plugin.log")
    }

    private val writer: PrintWriter by lazy {
        PrintWriter(FileWriter(logFile, /* append = */ true), /* autoFlush = */ true)
    }

    private fun write(level: String, msg: String) {
        val ts = LocalDateTime.now().format(TS)
        val line = "$ts [$level] $msg"
        synchronized(this) {
            try { writer.println(line) } catch (_: Exception) { /* best-effort */ }
        }
        // Also forward to the IntelliJ platform logger so it appears in idea.log
        val ideLog = com.intellij.openapi.diagnostic.Logger.getInstance(PluginLogger::class.java)
        when (level) {
            "ERROR" -> ideLog.error(msg)
            "WARN"  -> ideLog.warn(msg)
            else    -> ideLog.info(msg)
        }
    }

    fun info(msg: String)  = write("INFO",  msg)
    fun warn(msg: String)  = write("WARN",  msg)
    fun error(msg: String) = write("ERROR", msg)

    fun logFilePath(): String = logFile.absolutePath
}
