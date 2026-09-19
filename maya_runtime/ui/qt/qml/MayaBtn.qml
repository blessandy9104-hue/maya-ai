import QtQuick
import QtQuick.Controls

Rectangle {
    id: root
    property string text: ""
    property color fill: "#101629"
    property color textColor: "#8a93b8"
    property color borderColor: "#25305a"
    signal clicked()

    property font uiFont: Qt.font({ pixelSize: 11, bold: true })

    FontMetrics {
        id: buttonFontMetrics
        font: root.uiFont
    }

    implicitWidth: Math.round(buttonFontMetrics.advanceWidth(root.text)) + 30
    implicitHeight: 30
    radius: 6
    color: root.fill
    border.color: root.borderColor
    border.width: 1

    Text {
        anchors.centerIn: parent
        text: root.text
        color: root.textColor
        font: root.uiFont
    }
    MouseArea {
        anchors.fill: parent
        onClicked: root.clicked()
    }
}