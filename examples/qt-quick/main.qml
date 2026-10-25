// SPDX-License-Identifier: EUPL-1.2
import QtQuick
import QtQuick.Controls

ApplicationWindow {
    visible: true
    width: 360
    height: 120

    Row {
        padding: 12
        spacing: 12

        ToolButton {
            display: AbstractButton.IconOnly
            icon.name: "folder"
            icon.color: "transparent"
            icon.width: 48
            icon.height: 48
        }

        ToolButton {
            display: AbstractButton.IconOnly
            icon.name: "go-next-symbolic"
            icon.width: 24
            icon.height: 24
        }

        ToolButton {
            display: AbstractButton.IconOnly
            icon.name: "application-pdf"
            icon.color: "transparent"
            icon.width: 48
            icon.height: 48
        }
    }
}
