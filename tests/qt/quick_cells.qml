import QtQuick
import QtQuick.Controls.Basic

ApplicationWindow {
    id: root
    visible: true
    width: 960
    height: 640
    color: "#808080"

    Flow {
        x: 8
        y: 8
        width: root.width - 16
        spacing: 8

        Repeater {
            model: cellModel

            delegate: Rectangle {
                id: cell
                objectName: "cell-" + modelData.id
                required property var modelData
                width: modelData.size + 16
                height: modelData.size + 16
                color: modelData.bg

                ToolButton {
                    anchors.centerIn: parent
                    width: cell.modelData.size
                    height: cell.modelData.size
                    padding: 0
                    flat: true
                    enabled: cell.modelData.enabled
                    display: AbstractButton.IconOnly
                    icon.name: cell.modelData.name
                    icon.width: cell.modelData.size
                    icon.height: cell.modelData.size
                    background: Item {}
                    Component.onCompleted: {
                        if (cell.modelData.tint !== "default")
                            icon.color = cell.modelData.tint
                    }
                }
            }
        }
    }
}
