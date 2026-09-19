import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: controlPage
    color: "#0a0e1a"

    property var tick: null
    property bool advancedOpen: false

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

            Label { text: "Controls"; color: "#e7ebfa"; font.pixelSize: 19; font.bold: true }
            Label {
                text: "One-click supervised controls. Every action is executed, logged, and reported here."
                color: "#8a93b8"; font.pixelSize: 10
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.topMargin: 6
                spacing: 12

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 10

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.minimumHeight: serviceCol.implicitHeight + 20
                        radius: 8; color: "#101629"; border.color: "#25305a"; border.width: 1
                        ColumnLayout {
                            id: serviceCol
                            anchors.fill: parent; anchors.margins: 10; spacing: 6
                            Label { text: "SERVICE"; color: "#9a8cff"; font.pixelSize: 11; font.bold: true }
                            RowLayout {
                                MayaBtn { text: "Wake"; fill: "#1b2340"; textColor: "#4ade80"
                                    onClicked: ui.enterCommand("control", ":wake") }
                                MayaBtn { text: "Sleep"; onClicked: ui.enterCommand("control", ":sleep") }
                                MayaBtn { text: "Status"; onClicked: ui.enterCommand("control", ":status") }
                                Item { Layout.fillWidth: true }
                            }
                        }
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.minimumHeight: learnCol.implicitHeight + 20
                        radius: 8; color: "#101629"; border.color: "#25305a"; border.width: 1
                        ColumnLayout {
                            id: learnCol
                            anchors.fill: parent; anchors.margins: 10; spacing: 6
                            Label { text: "LEARNING"; color: "#9a8cff"; font.pixelSize: 11; font.bold: true }
                            RowLayout {
                                MayaBtn { text: "Activate"; fill: "#1b2340"; textColor: "#4ade80"
                                    onClicked: ui.enterCommand("control", "activate learning") }
                                MayaBtn { text: "Pause"; onClicked: ui.enterCommand("control", "pause learning") }
                                MayaBtn { text: "Status"; onClicked: ui.enterCommand("control", "learning status") }
                                Item { Layout.fillWidth: true }
                            }
                        }
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.minimumHeight: presenceCol.implicitHeight + 20
                        radius: 8; color: "#101629"; border.color: "#25305a"; border.width: 1
                        ColumnLayout {
                            id: presenceCol
                            anchors.fill: parent; anchors.margins: 10; spacing: 6
                            Label { text: "MAYA'S STATUS"; color: "#9a8cff"; font.pixelSize: 11; font.bold: true }
                            GridLayout {
                                columns: 2
                                columnSpacing: 8
                                rowSpacing: 6
                                MayaBtn { text: "On"; fill: "#1b2340"; textColor: "#4ade80"
                                    onClicked: ui.presenceAction("on", "control") }
                                MayaBtn { text: "Off"; onClicked: ui.presenceAction("off", "control") }
                                MayaBtn { text: "Check"; onClicked: ui.presenceAction("status", "control") }
                                MayaBtn { text: "Clear emergency stop"; onClicked: ui.presenceAction("reset-stop", "control") }
                            }
                        }
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.minimumHeight: reviewCol.implicitHeight + 20
                        radius: 8; color: "#101629"; border.color: "#25305a"; border.width: 1
                        ColumnLayout {
                            id: reviewCol
                            anchors.fill: parent; anchors.margins: 10; spacing: 6
                            Label { text: "REVIEWS"; color: "#9a8cff"; font.pixelSize: 11; font.bold: true }
                            GridLayout {
                                columns: 2
                                columnSpacing: 8
                                rowSpacing: 6
                                MayaBtn { text: "Focus"; borderColor: "#1b2340"; onClicked: ui.enterCommand("control", ":focus") }
                                MayaBtn { text: "Approvals"; borderColor: "#1b2340"; onClicked: ui.enterCommand("control", ":review") }
                                MayaBtn { text: "Research"; borderColor: "#1b2340"; onClicked: ui.enterCommand("control", ":research") }
                                MayaBtn { text: "Evidence"; borderColor: "#1b2340"; onClicked: ui.enterCommand("control", ":evidence") }
                                MayaBtn { text: "Income"; borderColor: "#1b2340"; onClicked: ui.enterCommand("control", ":income") }
                            }
                        }
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.minimumHeight: safetyCol.implicitHeight + 20
                        radius: 8; color: "#101629"; border.color: "#25305a"; border.width: 1
                        ColumnLayout {
                            id: safetyCol
                            anchors.fill: parent; anchors.margins: 10; spacing: 6
                            Label { text: "SAFETY"; color: "#9a8cff"; font.pixelSize: 11; font.bold: true }
                            RowLayout {
                                MayaBtn { text: "EMERGENCY STOP"; fill: "#3a1520"; textColor: "#ff5c7a"
                                    onClicked: ui.emergency() }
                                MayaBtn { text: "Resource Status"; borderColor: "#1b2340"
                                    onClicked: ui.enterCommand("control", ":status detail") }
                                Item { Layout.fillWidth: true }
                            }
                        }
                    }
                }

                Rectangle {
                    Layout.preferredWidth: 360
                    Layout.fillHeight: true
                    Layout.minimumHeight: liveCol.implicitHeight + 20
                    radius: 8; color: "#101629"; border.color: "#25305a"; border.width: 1
                    ColumnLayout {
                        id: liveCol
                        anchors.fill: parent; anchors.margins: 10; spacing: 8
                        Label { text: "LIVE STATUS"; color: "#9a8cff"; font.pixelSize: 11; font.bold: true }
                        TextArea {
                            id: liveOut
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            Layout.minimumHeight: 140
                            readOnly: true
                            color: "#e7ebfa"
                            font.family: "Consolas"; font.pixelSize: 10
                            textFormat: TextEdit.PlainText
                            background: null
                            focus: false
                        }
                        MayaBtn {
                            text: "Refresh Now"
                            fill: "#6d7cff"; textColor: "#e7ebfa"
                            Layout.fillWidth: true
                            onClicked: ui.refreshTick()
                        }
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.minimumHeight: 40
                Layout.preferredHeight: controlPage.advancedOpen ? (controlLog.implicitHeight + 78) : 40
                radius: 8; color: "#101629"; border.color: "#25305a"; border.width: 1
                clip: true

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 10
                    spacing: 8

                    RowLayout {
                        Layout.fillWidth: true
                        Label { text: "Advanced / Developer"; color: "#9a8cff"; font.pixelSize: 11; font.bold: true }
                        Item { Layout.fillWidth: true }
                        MayaBtn {
                            text: controlPage.advancedOpen ? "Hide" : "Show"
                            onClicked: controlPage.advancedOpen = !controlPage.advancedOpen
                        }
                    }
                    Label {
                        visible: controlPage.advancedOpen
                        text: "ACTIVITY LOG"
                        color: "#5b6488"; font.pixelSize: 9
                    }
                    TextArea {
                        id: controlLog
                        visible: controlPage.advancedOpen
                        Layout.fillWidth: true
                        Layout.preferredHeight: 180
                        readOnly: true
                        color: "#e7ebfa"
                        font.family: "Consolas"; font.pixelSize: 10
                        textFormat: TextEdit.PlainText
                        background: Rectangle { color: "#0d1322"; radius: 6; border.color: "#25305a" }
                        focus: false
                    }
                }
            }
        }
    }

    function log(text, color) {
        controlLog.append(text)
        Qt.callLater(function () { scroll.contentY = scroll.contentHeight - scroll.height })
    }

    property string liveSig: ""

    function liveDataReady(v) {
        if (v === null || v === undefined || !v.live_lines) return
        var joined = v.live_lines.join("\n")
        if (joined === liveSig) return
        liveSig = joined
        liveOut.clear()
        for (var i = 0; i < v.live_lines.length; i++) liveOut.append(v.live_lines[i])
    }
}