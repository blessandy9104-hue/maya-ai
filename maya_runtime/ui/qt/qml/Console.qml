import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: consoleBox
    spacing: 8

    function append(text) {
        consoleOut.append(text)
        Qt.callLater(function () { scroll.contentY = scroll.contentHeight - scroll.height })
    }

    RowLayout {
        Layout.fillWidth: true
        Label { text: "Conversation"; color: "#e7ebfa"; font.pixelSize: 15; font.bold: true }
        Label {
            text: "Actions remain confirmation-controlled. Nothing activates without explicit approval."
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            Layout.maximumWidth: 220
            elide: Text.ElideRight
            color: "#8a93b8"
            font.pixelSize: 10
        }
        Item { Layout.fillWidth: true }
        Label {
            id: chatState
            text: "chat: offline"
            color: "#8a93b8"
            font.pixelSize: 10
        }
    }

    Rectangle {
        Layout.fillWidth: true
        Layout.fillHeight: true
        color: "#0d1322"
        radius: 6
        border.color: "#25305a"
        border.width: 1
        clip: true

        Flickable {
            id: scroll
            anchors.fill: parent
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            contentHeight: consoleOut.height

            TextArea {
                id: consoleOut
                width: parent.width
                height: Math.max(scroll.height, contentHeight)
                readOnly: true
                color: "#e7ebfa"
                font.family: "Consolas"
                font.pixelSize: 11
                textFormat: TextEdit.PlainText
                wrapMode: TextEdit.Wrap
                background: null
                focus: false
            }
        }
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: 8

        TextField {
            id: chatIn
            Layout.fillWidth: true
            implicitHeight: 34
            placeholderText: "Talk to Maya…"
            color: "#e7ebfa"
            placeholderTextColor: "#5b6488"
            background: Rectangle { color: "#0b1020"; radius: 6; border.color: "#25305a" }
            onAccepted: send()
            Keys.onPressed: ui.notifyTyping()
            function send() {
                var v = text.trim()
                if (!v) return
                ui.chatSend(v)
                text = ""
            }
        }

        Button {
            text: "Send"
            implicitHeight: 34
            onClicked: chatIn.send()
            background: Rectangle { color: "#6d7cff"; radius: 6 }
            contentItem: Text {
                text: "Send";
                color: "#e7ebfa";
                font.bold: true;
                horizontalAlignment: Text.AlignHCenter;
                verticalAlignment: Text.AlignVCenter
            }
        }
    }

    Connections {
        target: ui
        function onChatLine(line) {
            consoleBox.append(line)
        }
        function onChatOnline(online) {
            chatState.text = online ? "chat: online" : "chat: offline"
            chatState.color = online ? "#4ade80" : "#8a93b8"
        }
    }
}