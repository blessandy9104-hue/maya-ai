import QtQuick

// First-run onboarding overlay. Purely informational: it explains the orb's
// colours in student language and never touches runtime state.
Rectangle {
    id: welcome
    signal dismissed()

    color: "#e605070f"

    MouseArea { anchors.fill: parent }

    Rectangle {
        id: card
        anchors.centerIn: parent
        width: Math.min(580, parent.width - 60)
        height: body.implicitHeight + 48
        radius: 14
        color: "#101629"
        border.color: "#6d7cff"
        border.width: 1

        Column {
            id: body
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            anchors.leftMargin: 24
            anchors.rightMargin: 24
            spacing: 12

            Text {
                text: "Welcome to Maya"
                color: "#e7ebfa"
                font.pixelSize: 22
                font.bold: true
            }
            Text {
                width: parent.width
                wrapMode: Text.Wrap
                color: "#8a93b8"
                font.pixelSize: 12
                text: "Maya is a local helper that thinks with you. You are always in charge — she asks before she acts."
            }
            Text {
                text: "The glowing orb shows what Maya is doing"
                color: "#e7ebfa"
                font.pixelSize: 13
                font.bold: true
            }

            Column {
                id: legend
                spacing: 9
                Repeater {
                    model: [
                        { dot: "#4fe0b0", title: "Mint — Ready", note: "Maya is awake and listening." },
                        { dot: "#3b9dff", title: "Blue — Thinking", note: "She is working something out." },
                        { dot: "#ffd36e", title: "Gold — All done", note: "She finished, or needs your OK." },
                        { dot: "#ff5c7a", title: "Red — Needs attention", note: "Something is wrong; she has paused." }
                    ]
                    delegate: Row {
                        spacing: 10
                        Rectangle {
                            width: 10; height: 10; radius: 5
                            color: modelData.dot
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        Text {
                            text: modelData.title
                            color: "#e7ebfa"
                            font.pixelSize: 12
                            font.bold: true
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        Text {
                            text: modelData.note
                            color: "#8a93b8"
                            font.pixelSize: 12
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }
                }
            }

            Text {
                width: parent.width
                wrapMode: Text.Wrap
                color: "#5b6488"
                font.pixelSize: 11
                text: "Tip: the Advanced / Developer section on Home holds the technical activity log and the trust list. You can ignore it unless you want the details."
            }

            Row {
                spacing: 10
                anchors.right: parent.right
                MayaBtn {
                    text: "Got it — let's start"
                    fill: "#6d7cff"
                    textColor: "#e7ebfa"
                    onClicked: welcome.dismissed()
                }
                MayaBtn {
                    text: "Help"
                    onClicked: welcome.dismissed()
                }
            }
        }
    }
}
