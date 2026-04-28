package com.projspec.util

import com.intellij.notification.Notification
import com.intellij.notification.NotificationType
import com.intellij.notification.Notifications
import com.intellij.openapi.project.Project

/**
 * Convenience wrapper for showing projspec notifications.
 *
 * VSCode equivalent: vscode.window.showErrorMessage / showInformationMessage
 * IntelliJ uses a balloon-style notification system rather than a modal message.
 *
 * The notification group "Projspec" must be declared in plugin.xml.
 */
object Notifier {

    private const val GROUP_ID = "Projspec"

    fun error(message: String, project: Project? = null) =
        notify(message, NotificationType.ERROR, project)

    fun warning(message: String, project: Project? = null) =
        notify(message, NotificationType.WARNING, project)

    fun info(message: String, project: Project? = null) =
        notify(message, NotificationType.INFORMATION, project)

    private fun notify(message: String, type: NotificationType, project: Project?) {
        val notification = Notification(GROUP_ID, "projspec", message, type)
        Notifications.Bus.notify(notification, project)
    }
}
