package com.projspec.util

import com.intellij.execution.configurations.GeneralCommandLine
import com.intellij.execution.process.CapturingProcessHandler
import com.projspec.settings.ProjspecSettings

/**
 * Centralised wrapper around every `projspec` CLI invocation used by the
 * plugin.  Mirrors the TypeScript `projspec.ts` helpers in the VSCode
 * extension (vsextension/src/projspec.ts).
 *
 * All calls are synchronous and block the calling thread — they MUST NOT be
 * invoked from the EDT.  Call sites use `ApplicationManager.executeOnPooledThread`
 * or `ProgressManager.runProcessWithProgressSynchronously`.
 *
 * The CLI binary path is read from [ProjspecSettings] on every call so user
 * changes take effect without restarting the IDE.
 */
object ProjspecRunner {

    private val cli: String
        get() = ProjspecSettings.instance.cliPath

    // -------------------------------------------------------------------------
    // Commands used by the tool-window webview
    // VSCode equivalents live in vsextension/src/projspec.ts.
    // -------------------------------------------------------------------------

    /** `projspec info` — returns spec/artifact/content metadata (JSON). */
    fun runInfo(): CliResult = run(listOf(cli, "info"))

    /** `projspec library list --json-out` — returns project library JSON. */
    fun runLibraryList(): CliResult = run(listOf(cli, "library", "list", "--json-out"))

    /** `projspec scan --library <path>` — scan & register a directory. */
    fun runScan(path: String): CliResult = run(listOf(cli, "scan", "--library", path))

    /** `projspec create <spec> <path>` — create a new spec inside a project. */
    fun runCreate(spec: String, path: String): CliResult =
        run(listOf(cli, "create", spec, path))

    /** `projspec library delete <url>` — remove a URL from the library. */
    fun runLibraryDelete(url: String): CliResult =
        run(listOf(cli, "library", "delete", url))

    // -------------------------------------------------------------------------
    // Enum members (python3 introspection subprocess)
    //
    // `projspec info` does not expose Enum members, so — exactly as the VSCode
    // extension does — we call python3 directly to walk projspec.utils.Enum
    // subclasses and print {snake_name: {MEMBER_NAME: value}} as JSON.
    // -------------------------------------------------------------------------

    /**
     * Return a JSON string mapping snake-cased enum class name → {MEMBER_NAME:
     * value}, or an empty JSON object `"{}"` if python3 is unavailable or the
     * import fails.  The result is consumed by the webview's YAML renderer to
     * display enum values as their member name instead of a raw integer.
     */
    fun runEnumMembers(): String {
        val script = """
            import json, importlib, pkgutil
            import projspec.utils as pu
            import projspec.content, projspec.artifact
            for pkg in (projspec.content, projspec.artifact):
                for m in pkgutil.iter_modules(pkg.__path__, pkg.__name__ + '.'):
                    importlib.import_module(m.name)
            from projspec.utils import camel_to_snake
            out, seen = {}, set()
            def walk(cls):
                for sub in cls.__subclasses__():
                    if sub in seen: continue
                    seen.add(sub); walk(sub)
                    out[camel_to_snake(sub.__name__)] = {m.name: m.value for m in sub}
            walk(pu.Enum)
            print(json.dumps(out))
            """.trimIndent()
        return try {
            val cmd = GeneralCommandLine(listOf("python3", "-c", script))
            val output = CapturingProcessHandler(cmd).runProcess(30_000)
            if (output.isTimeout || output.exitCode != 0) "{}" else output.stdout.trim().ifBlank { "{}" }
        } catch (_: Exception) { "{}" }
    }

    // -------------------------------------------------------------------------
    // Internal execution
    // -------------------------------------------------------------------------

    /**
     * Execute an external command and capture stdout/stderr.
     *
     * NOTE: blocks the calling thread for up to 60 s.  Never call from the EDT.
     */
    fun run(args: List<String>): CliResult {
        return try {
            val commandLine = GeneralCommandLine(args)
            val handler = CapturingProcessHandler(commandLine)
            val output = handler.runProcess(60_000)

            when {
                output.isTimeout ->
                    CliResult.Failure("projspec timed out after 60 s", -1)
                output.exitCode != 0 ->
                    CliResult.Failure(
                        output.stderr.ifBlank { output.stdout }
                            .ifBlank { "Exit code ${output.exitCode}" },
                        output.exitCode,
                    )
                else ->
                    CliResult.Success(output.stdout)
            }
        } catch (e: Exception) {
            CliResult.Failure("Failed to launch projspec: ${e.message}")
        }
    }

    /**
     * Extract the first balanced JSON object/array from CLI stdout.  Some
     * projspec subcommands print banners before the JSON payload; this
     * helper is the Kotlin equivalent of `parseJsonOutput` in projspec.ts.
     *
     * Returns an empty string if no JSON can be found.
     */
    fun extractJson(stdout: String): String {
        val trimmed = stdout.trim()
        if (trimmed.isEmpty()) return ""
        val firstChar = trimmed.first()
        if (firstChar == '{' || firstChar == '[') return trimmed
        val start = trimmed.indexOfFirst { it == '{' || it == '[' }
        if (start < 0) return ""
        return trimmed.substring(start)
    }
}
