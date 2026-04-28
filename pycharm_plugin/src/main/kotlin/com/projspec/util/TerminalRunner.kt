package com.projspec.util

import com.intellij.openapi.project.Project

/**
 * Runs the `projspec make …` subcommand in an interactive terminal tab so
 * the user can watch build output scroll.
 *
 * VSCode equivalent: the `runInTerminal` helper in vsextension/src/projspec.ts,
 * called from the panel's `make` message handler.  We mirror the shape:
 * the terminal name is "projspec" and the command line is
 * `projspec make <artifactArg> <projectPath>`.
 *
 * The terminal plugin dependency is declared optional in plugin.xml, so we
 * guard the reflective call-chain and fall back to an informational balloon
 * with the command string if the plugin is missing.
 */
object TerminalRunner {

    /**
     * @param project      The open IDE project.
     * @param artifactArg  `<spec>.<artifact>[.<name>]` qualified identifier.
     * @param projectPath  Filesystem path of the target project (for cwd /
     *                     argv); stripped of any `file://` prefix.
     * @param cliPath      Path to the projspec binary (from settings).
     */
    fun makeArtifact(project: Project, artifactArg: String, projectPath: String, cliPath: String) {
        val command = "$cliPath make $artifactArg \"$projectPath\""
        if (!tryRunInTerminal(project, command)) {
            Notifier.info(
                "Run the following command in a terminal:\n$command",
                project,
            )
        }
    }

    /**
     * Attempt to open the IntelliJ terminal tool window and run the command.
     * Returns true on success, false if the terminal plugin is unavailable.
     *
     * Uses reflection throughout to avoid a hard compile-time dependency on
     * org.jetbrains.plugins.terminal — the plugin is declared optional.
     */
    private fun tryRunInTerminal(project: Project, command: String): Boolean {
        return try {
            val managerClass = Class.forName("org.jetbrains.plugins.terminal.TerminalToolWindowManager")
            val getInstance = managerClass.getMethod("getInstance", Project::class.java)
            val manager = getInstance.invoke(null, project)

            val widget = try {
                val createMethod = managerClass.getMethod(
                    "createLocalShellWidget", String::class.java, String::class.java
                )
                createMethod.invoke(manager, null as String?, "projspec")
            } catch (_: NoSuchMethodException) { null }

            if (widget != null) {
                val execMethod = try {
                    widget.javaClass.getMethod("executeCommand", String::class.java)
                } catch (_: NoSuchMethodException) {
                    widget.javaClass.getMethod("sendString", String::class.java)
                }
                execMethod.invoke(widget, command)
                true
            } else false
        } catch (_: Exception) {
            false
        }
    }
}
