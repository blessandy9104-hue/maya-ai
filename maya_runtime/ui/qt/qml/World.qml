import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: worldPage
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

            Label { text: "World Model"; color: "#e7ebfa"; font.pixelSize: 19; font.bold: true }
            Label {
                text: "Provenance-first evidence store. Source, confidence, and retrieval time are always recorded."
                color: "#8a93b8"; font.pixelSize: 10
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                MayaBtn { text: "Summary"; fill: "#6d7cff"; textColor: "#e7ebfa"
                    onClicked: ui.enterCommand("world", ":world summary") }
                MayaBtn { text: "List Evidence"; onClicked: ui.enterCommand("world", ":world list") }
                TextField {
                    id: cmpEntry
                    Layout.fillWidth: true
                    implicitHeight: 32
                    placeholderText: "Compare topic…"
                    color: "#e7ebfa"; placeholderTextColor: "#5b6488"
                    background: Rectangle { color: "#0b1020"; radius: 6; border.color: "#25305a" }
                    function go() { ui.worldCompare(text); text = "" }
                    onAccepted: go()
                }
                MayaBtn { text: "Compare Topic"; onClicked: cmpEntry.go() }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.minimumHeight: evidenceCol.implicitHeight + 20
                radius: 8; color: "#101629"; border.color: "#25305a"; border.width: 1
                ColumnLayout {
                    id: evidenceCol
                    anchors.fill: parent; anchors.margins: 10; spacing: 6
                    Label { text: "ADD SOURCE-BACKED EVIDENCE"; color: "#9a8cff"; font.pixelSize: 11; font.bold: true }
                    RowLayout {
                        Label { text: "Claim"; color: "#8a93b8"; Layout.preferredWidth: 64 }
                        TextField { id: claimEntry; Layout.fillWidth: true; implicitHeight: 30
                            color: "#e7ebfa"; background: Rectangle { color: "#0b1020"; radius: 6; border.color: "#25305a" } }
                        Label { text: "Source"; color: "#8a93b8"; Layout.preferredWidth: 76 }
                        TextField { id: sourceEntry; Layout.fillWidth: true; implicitHeight: 30
                            color: "#e7ebfa"; background: Rectangle { color: "#0b1020"; radius: 6; border.color: "#25305a" } }
                    }
                    RowLayout {
                        Label { text: "Confidence"; color: "#8a93b8"; Layout.preferredWidth: 124 }
                        ComboBox {
                            id: confBox; Layout.preferredWidth: 110
                            model: ["low", "medium", "high"]
                        }
                        Label { text: "Type"; color: "#8a93b8"; Layout.preferredWidth: 52 }
                        ComboBox {
                            id: typeBox; Layout.fillWidth: true
                            model: ["fact", "historical_record", "observation", "report"]
                        }
                        MayaBtn {
                            text: "Add Evidence"; fill: "#1b2340"; textColor: "#4ade80"
                            onClicked: {
                                ui.worldAdd(claimEntry.text, sourceEntry.text,
                                            confBox.currentText, typeBox.currentText)
                                claimEntry.text = ""; sourceEntry.text = ""
                            }
                        }
                    }
                }
            }

            Label { text: "OUTPUT"; color: "#9a8cff"; font.pixelSize: 11; font.bold: true }
            TextArea {
                id: worldOut
                Layout.fillWidth: true
                Layout.preferredHeight: 260
                readOnly: true
                color: "#e7ebfa"
                font.family: "Consolas"; font.pixelSize: 10
                textFormat: TextEdit.PlainText
                background: Rectangle { color: "#0d1322"; radius: 6; border.color: "#25305a" }
                focus: false
            }
        }
    }

    function log(text, color) {
        worldOut.append(text)
        Qt.callLater(function () { scroll.contentY = scroll.contentHeight - scroll.height })
    }
}