// SPDX-License-Identifier: EUPL-1.2
import Quickshell
import Quickshell.Io
import QtQuick

Item {
    id: root

    property string iconDir: Quickshell.env("HOME") + "/.local/share/icons/Resina"
    property date time: new Date()

    implicitWidth: 64
    implicitHeight: 64

    FileView {
        id: file
        path: root.iconDir + "/scalable/apps/clocks.svg"
        blockLoading: true
    }

    function rotated(text, id, degrees) {
        return text.replace(new RegExp('(id="' + id + '" transform="rotate[(])[-0-9.]+'), function (all, head) {
            return head + degrees;
        });
    }

    function render() {
        const hours = root.time.getHours() % 12 + root.time.getMinutes() / 60;
        const minutes = root.time.getMinutes() + root.time.getSeconds() / 60;
        let text = rotated(file.text(), "hour-hand", hours * 30);
        text = rotated(text, "minute-hand", minutes * 6);
        return rotated(text, "second-hand", root.time.getSeconds() * 6);
    }

    Timer {
        interval: 1000
        running: true
        repeat: true
        onTriggered: root.time = new Date()
    }

    Image {
        anchors.fill: parent
        sourceSize: Qt.size(width, height)
        cache: false
        source: "data:image/svg+xml;utf8," + encodeURIComponent(root.render())
    }
}
