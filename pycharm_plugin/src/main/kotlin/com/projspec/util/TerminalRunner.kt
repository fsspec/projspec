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
 *
 * Reflection is used throughout to avoid a hard compile-time dependency on
 * org.jetbrains.plugins.terminal.  The method signatures we probe for:
 *
 *  IntelliJ ≤ 2023.0  — TerminalToolWindowManager.createLocalShellWidget(path, name)
 *                        widget.sendString(cmd) / widget.executeCommand(cmd)
 *  IntelliJ 2023.1–2024.0 — TerminalToolWindowManager.createShellWidget(path, name, focus)
 *                             widget.executeCommand(cmd)
 *  IntelliJ 2024.1+   — same createShellWidget signature; executeCommand still present
 *
 * Each probe is tried in descending-recency order so the most-current path wins.
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
        if (!tryRunInTerminal(project, projectPath, command)) {
            Notifier.info(
                "Run the following command in a terminal:\n$command",
                project,
            )
        }
    }

    /**
     * Attempt to open the IntelliJ terminal tool window and run the command.
     * Returns true on success, false if the terminal plugin is unavailable or
     * no supported API was found.
     */
    private fun tryRunInTerminal(project: Project, workDir: String, command: String): Boolean {
        return try {
            val managerClass = Class.forName(
                "org.jetbrains.plugins.terminal.TerminalToolWindowManager"
            )
            val getInstance = managerClass.getMethod("getInstance", Project::class.java)
            val manager = getInstance.invoke(null, project)

            val widget = createWidget(managerClass, manager, workDir) ?: return false
            sendCommand(widget, command)
            true
        } catch (_: Exception) {
            false
        }
    }

    /**
     * Try each known factory method in reverse-chronological order.
     *
     * 2023.1+ API: createShellWidget(workDirPath: String?, tabName: String?, requestFocus: Boolean)
     * pre-2023 API: createLocalShellWidget(workDirPath: String?, tabName: String)
     */
    private fun createWidget(managerClass: Class<*>, manager: Any, workDir: String): Any? {
        // 2023.1+ preferred path
        tryMethod(managerClass, manager, "createShellWidget",
            arrayOf(String::class.java, String::class.java, Boolean::class.java),
            arrayOf(workDir, "projspec", true)
        )?.let { return it }

        // pre-2023 fallback
        tryMethod(managerClass, manager, "createLocalShellWidget",
            arrayOf(String::class.java, String::class.java),
            arrayOf(workDir, "projspec")
        )?.let { return it }

        return null
    }

    /**
     * Try to send [command] to the terminal widget using whichever execute
     * method is available on the installed version.
     *
     * executeCommand(String)  — 2023.1+ (ShellTerminalWidget)
     * sendString(String)      — pre-2023 (JBTerminalWidget)
     */
    private fun sendCommand(widget: Any, command: String) {
        for (methodName in listOf("executeCommand", "sendString")) {
            try {
                widget.javaClass.getMethod(methodName, String::class.java)
                    .invoke(widget, command)
                return
            } catch (_: NoSuchMethodException) {
                // try next
            }
        }
    }

    private fun tryMethod(
        cls: Class<*>,
        instance: Any,
        name: String,
        paramTypes: Array<Class<*>>,
        args: Array<Any?>,
    ): Any? =
        try {
            cls.getMethod(name, *paramTypes).invoke(instance, *args)
        } catch (_: NoSuchMethodException) {
            null
        }
}
