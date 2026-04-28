package com.projspec.settings

import com.intellij.openapi.fileChooser.FileChooserDescriptorFactory
import com.intellij.openapi.options.Configurable
import com.intellij.openapi.ui.TextFieldWithBrowseButton
import com.intellij.ui.components.JBLabel
import com.intellij.util.ui.FormBuilder
import javax.swing.JComponent
import javax.swing.JPanel

/**
 * Settings UI for the projspec plugin, exposed under Settings → Tools → Projspec.
 *
 * VSCode equivalent: none — the original extension assumed projspec was on PATH.
 * This panel lets the user specify an explicit path to the projspec binary.
 */
class ProjspecSettingsConfigurable : Configurable {

    private var settingsPanel: ProjspecSettingsPanel? = null

    override fun getDisplayName(): String = "Projspec"

    override fun createComponent(): JComponent {
        settingsPanel = ProjspecSettingsPanel()
        return settingsPanel!!.panel
    }

    override fun isModified(): Boolean {
        val panel = settingsPanel ?: return false
        return panel.cliPath != ProjspecSettings.instance.cliPath
    }

    override fun apply() {
        val panel = settingsPanel ?: return
        ProjspecSettings.instance.cliPath = panel.cliPath
    }

    override fun reset() {
        settingsPanel?.cliPath = ProjspecSettings.instance.cliPath
    }

    override fun disposeUIResources() {
        settingsPanel = null
    }
}

/**
 * The actual Swing form for the settings panel.
 */
class ProjspecSettingsPanel {

    private val cliPathField = TextFieldWithBrowseButton().apply {
        addBrowseFolderListener(
            "Select projspec Binary",
            "Choose the path to the projspec executable",
            null,
            FileChooserDescriptorFactory.createSingleFileDescriptor()
        )
    }

    val panel: JPanel = FormBuilder.createFormBuilder()
        .addLabeledComponent(
            JBLabel("projspec CLI path:"),
            cliPathField,
            1,
            false
        )
        .addComponentFillVertically(JPanel(), 0)
        .panel

    var cliPath: String
        get() = cliPathField.text.trim()
        set(value) { cliPathField.text = value }
}
