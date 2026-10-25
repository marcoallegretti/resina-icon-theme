// SPDX-License-Identifier: EUPL-1.2
import Quickshell
import QtQuick
import QtQuick.Controls

PanelWindow {
    anchors {
        top: true
        left: true
        right: true
    }
    implicitHeight: 120
    color: "#ECE8DF"

    Row {
        anchors.centerIn: parent
        spacing: 16

        ToolButton {
            display: AbstractButton.IconOnly
            flat: true
            padding: 0
            icon.name: "folder"
            icon.color: "transparent"
            icon.width: 64
            icon.height: 64
            background: Item {}
        }

        ToolButton {
            display: AbstractButton.IconOnly
            flat: true
            padding: 0
            icon.name: "application-pdf"
            icon.color: "transparent"
            icon.width: 64
            icon.height: 64
            background: Item {}
        }

        ToolButton {
            display: AbstractButton.IconOnly
            flat: true
            padding: 0
            icon.name: "go-next-symbolic"
            icon.color: "#222222"
            icon.width: 48
            icon.height: 48
            background: Item {}
        }

        DynamicClock {
            width: 64
            height: 64
        }

        DynamicCalendar {
            width: 64
            height: 64
        }
    }
}
