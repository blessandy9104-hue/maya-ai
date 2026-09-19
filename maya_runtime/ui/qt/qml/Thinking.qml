import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: thinkPage
    color: "#0a0e1a"

    Flickable {
        id: scroll
        anchors.fill: parent
        contentHeight: viewport.height
        clip: true
        ScrollBar.vertical: ScrollBar {}

        Item {
            id: viewport
            width: scroll.width
            height: body.implicitHeight + 28
        }

        ColumnLayout {
            id: body
            anchors.fill: viewport
            anchors.margins: 14
            spacing: 10

            Label { text: "Connecting Ideas"; color: "#e7ebfa"; font.pixelSize: 19; font.bold: true }
            Label {
                text: "See how Maya links the ideas you have been working with, using only local evidence. This is a preview for you to review — the fit is relative, not a guaranteed answer. You decide what to do; Maya takes no outside action."
                color: "#8a93b8"; font.pixelSize: 10; wrapMode: Text.Wrap
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                MayaBtn { text: "AI and Python ideas"; borderColor: "#1b2340"
                    onClicked: ui.thinkMap("I want to build automated Python workflows with local AI that save me time") }
                MayaBtn { text: "Research and writing"; borderColor: "#1b2340"
                    onClicked: ui.thinkMap("I want to offer source-labelled research and writing briefs as a service") }
                MayaBtn { text: "Markets and data"; borderColor: "#1b2340"
                    onClicked: ui.thinkMap("I want to build educational tools around markets and data analysis without trading") }
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                MayaBtn { text: "My interests"; onClicked: ui.thinkInterests() }
                MayaBtn { text: "New directions"; onClicked: ui.thinkEmerging() }
                Item { Layout.fillWidth: true }
            }

            Label { text: "WHAT MAYA FOUND"; color: "#9a8cff"; font.pixelSize: 11; font.bold: true }
            TextArea {
                id: thinkOut
                Layout.fillWidth: true
                Layout.preferredHeight: 360
                readOnly: true
                color: "#e7ebfa"
                font.family: "Consolas"; font.pixelSize: 10
                textFormat: TextEdit.PlainText
                background: Rectangle { color: "#0d1322"; radius: 6; border.color: "#25305a" }
                focus: false
                Component.onCompleted: text = "Press one of the buttons above to see how Maya connects ideas from what she has saved locally.\n"
            }
        }
    }

    function log(text, color) {
        thinkOut.append(text)
        Qt.callLater(function () { scroll.contentY = scroll.contentHeight - scroll.height })
    }
}