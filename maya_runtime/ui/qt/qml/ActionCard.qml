import QtQuick

// A single, student-friendly quick action. Presentation only: it emits
// ``clicked`` and never performs work itself.
Rectangle {
    id: card
    property string title: ""
    property string subtitle: ""
    property color accent: "#6d7cff"
    signal clicked()

    implicitHeight: 84
    radius: 10
    color: hover.containsMouse ? "#16203a" : "#0d1322"
    border.color: hover.containsMouse ? card.accent : "#25305a"
    border.width: 1

    Column {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        anchors.leftMargin: 12
        anchors.rightMargin: 12
        spacing: 4

        Row {
            spacing: 7
            Rectangle {
                width: 9; height: 9; radius: 5
                color: card.accent
                anchors.verticalCenter: parent.verticalCenter
            }
            Text {
                text: card.title
                color: "#e7ebfa"
                font.pixelSize: 13
                font.bold: true
            }
        }
        Text {
            width: parent.width
            text: card.subtitle
            color: "#8a93b8"
            font.pixelSize: 10
            wrapMode: Text.Wrap
        }
    }

    MouseArea {
        id: hover
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: card.clicked()
    }
}
