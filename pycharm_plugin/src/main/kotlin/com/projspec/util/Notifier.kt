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
        // The 4-arg constructor Notification(groupId, title, content, type) was
        // deprecated in IntelliJ 2021.3.  Use the 3-arg form and let the
        // notification group's display name serve as the title.
        val notification = Notification(GROUP_ID, message, type)
        Notifications.Bus.notify(notification, project)
    }
}
