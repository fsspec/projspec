package com.projspec.settings

import com.intellij.openapi.components.*

/**
 * Application-level persistent state that stores the path to the projspec CLI binary.
 *
 * VSCode equivalent: there was no settings panel — the CLI was assumed to be on PATH.
 * Here we allow the user to configure the path explicitly via Settings → Tools → Projspec.
 *
 * Accessed anywhere via: ProjspecSettings.instance.cliPath
 */
@Service(Service.Level.APP)
@State(
    name = "ProjspecSettings",
    storages = [Storage("projspec.xml")]
)
class ProjspecSettings : PersistentStateComponent<ProjspecSettings.State> {

    data class State(
        /** Absolute path to the projspec binary, or just "projspec" to rely on PATH. */
        var cliPath: String = "projspec"
    )

    private var myState = State()

    override fun getState(): State = myState

    override fun loadState(state: State) {
        myState = state
    }

    /** The resolved CLI path/command to use when running projspec. */
    var cliPath: String
        get() = myState.cliPath.ifBlank { "projspec" }
        set(value) { myState.cliPath = value.ifBlank { "projspec" } }

    companion object {
        /** Retrieve the singleton instance. */
        val instance: ProjspecSettings
            get() = service()
    }
}
