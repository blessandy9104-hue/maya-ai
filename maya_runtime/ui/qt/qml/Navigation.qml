import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: rail
    implicitWidth: 176
    color: "#0d1322"

    property int currentIndex: 0
    signal navigate(int index)

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 10
        spacing: 3

        Label {
            text: "MAYA"
            color: "#9a8cff"
            font.bold: true
            font.pixelSize: 18
            topPadding: 8
            bottomPadding: 2
        }
        Label {
            text: "YOUR LOCAL HELPER"
            color: "#5b6488"
            font.pixelSize: 8
            font.bold: true
            bottomPadding: 14
            wrapMode: Text.Wrap
        }

        Repeater {
            model: [
                { label: "Home", key: "Ctrl+Alt+H" },
                { label: "Controls", key: "Ctrl+Alt+S" },
                { label: "Knowledge", key: "Ctrl+Alt+F" },
                { label: "My Day", key: "" },
                { label: "Connecting Ideas", key: "Ctrl+Alt+T" },
                { label: "Settings", key: "Ctrl+Alt+G" }
            ]
            delegate: Rectangle {
                id: item
                Layout.fillWidth: true
                height: 34
                radius: 6
                color: index === rail.currentIndex ? "#1b2340" : "#0d1322"

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 12
                    anchors.rightMargin: 8
                    Label {
                        text: modelData.label
                        color: index === rail.currentIndex ? "#e7ebfa" : "#8a93b8"
                        Layout.fillWidth: true
                    }
                    Label {
                        text: modelData.key
                        color: "#5b6488"
                        font.pixelSize: 9
                    }
                }
                MouseArea {
                    anchors.fill: parent
                    onClicked: rail.navigate(index)
                }
            }
        }

        Item { Layout.fillHeight: true }

        Label {
            text: "All actions review-gated."
            color: "#5b6488"
            font.pixelSize: 9
            wrapMode: Text.Wrap
        }
        Label {
            text: "Emergency: Ctrl+Alt+Esc"
            color: "#5b6488"
            font.pixelSize: 9
        }
        Label {
            text: "Close: Ctrl+Q"
            color: "#5b6488"
            font.pixelSize: 9
        }
    }
}