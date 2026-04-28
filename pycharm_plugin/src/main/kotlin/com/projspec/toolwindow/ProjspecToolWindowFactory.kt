package com.projspec.toolwindow

import com.intellij.openapi.project.Project
import com.intellij.openapi.wm.ToolWindow
import com.intellij.openapi.wm.ToolWindowFactory
import com.intellij.ui.content.ContentFactory
import com.intellij.ui.jcef.JBCefApp
import java.awt.BorderLayout
import javax.swing.JLabel
import javax.swing.JPanel
import javax.swing.SwingConstants

/**
 * Creates the content for the "Project Library" tool window.
 *
 * The factory is registered in plugin.xml under <toolWindow/>.  The real UI
 * lives in [ProjspecToolWindowPanel], which hosts a JCEF (Chromium) browser
 * displaying the same HTML/CSS/JS two-pane layout as the VSCode extension.
 *
 * JCEF fallback: if the IDE runtime does not support JCEF (headless mode,
 * certain remote configurations) we show a plain text panel so the plugin
 * loads without throwing.
 */
class ProjspecToolWindowFactory : ToolWindowFactory {

    companion object {
        /** Must match the `id` attribute in plugin.xml's <toolWindow> entry. */
        const val TOOL_WINDOW_ID: String = "Project Library"
    }

    override fun createToolWindowContent(project: Project, toolWindow: ToolWindow) {
        val contentFactory = ContentFactory.getInstance()

        val component = if (JBCefApp.isSupported()) {
            ProjspecToolWindowPanel(project, toolWindow)
        } else {
            JPanel(BorderLayout()).apply {
                add(
                    JLabel(
                        "<html><body style='padding:16px'>" +
                                "<b>projspec: JCEF not available</b><br/><br/>" +
                                "This plugin requires the JCEF (Chromium) runtime.<br/>" +
                                "Please restart the IDE with JCEF enabled." +
                                "</body></html>",
                        SwingConstants.LEFT,
                    ),
                    BorderLayout.NORTH,
                )
            }
        }

        val content = contentFactory.createContent(component, "", false)
        toolWindow.contentManager.addContent(content)
    }

    override fun isApplicable(project: Project): Boolean = true
}
