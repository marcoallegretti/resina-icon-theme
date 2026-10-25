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
        path: root.iconDir + "/scalable/apps/calendar.svg"
        blockLoading: true
    }

    function render() {
        const weekday = Qt.locale().dayName(root.time.getDay(), Locale.ShortFormat).toUpperCase();
        const weekdayText = '<text x="64" y="38" text-anchor="middle" font-family="sans-serif" font-size="15" font-weight="700" fill="#ffffff">' + weekday + '</text>';
        const dateText = '<text x="64" y="95" text-anchor="middle" font-family="sans-serif" font-size="46" font-weight="700" fill="#3f4349">' + root.time.getDate() + '</text>';
        return file.text()
            .replace(/<g id="weekday-slot"([^>]*?)(?:\s*\/>|>\s*<\/g>)/, function (all, attributes) {
                return '<g id="weekday-slot"' + attributes + '>' + weekdayText + '</g>';
            })
            .replace(/(<g id="date-slot"[^>]*>)[\s\S]*?<\/g>/, function (all, head) {
                return head + dateText + '</g>';
            });
    }

    Timer {
        interval: 60000
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
