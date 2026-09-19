import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: tasksPage
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

            Label { text: "Tasks"; color: "#e7ebfa"; font.pixelSize: 19; font.bold: true }
            Label {
                text: "Single source of truth: tasks.json. Changes are immediate and logged."
                color: "#8a93b8"; font.pixelSize: 10
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                MayaBtn { text: "Refresh List"; fill: "#6d7cff"; textColor: "#e7ebfa"
                    onClicked: ui.enterCommand("tasks", ":tasks") }
                MayaBtn { text: "Stats"; onClicked: ui.enterCommand("tasks", ":task stats") }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                Label { text: "Add:"; color: "#8a93b8" }
                TextField { id: addEntry; Layout.fillWidth: true; implicitHeight: 30
                    color: "#e7ebfa"; background: Rectangle { color: "#0b1020"; radius: 6; border.color: "#25305a" }
                    function go() { ui.taskOp("task add", text); text = "" }
                    onAccepted: go() }
                MayaBtn { text: "Add Task"; onClicked: addEntry.go() }

                Label { text: "Done #:"; color: "#8a93b8" }
                TextField { id: doneEntry; Layout.preferredWidth: 60; implicitHeight: 30
                    color: "#e7ebfa"; background: Rectangle { color: "#0b1020"; radius: 6; border.color: "#25305a" }
                    function go() { ui.taskOp("task done", text); text = "" }
                    onAccepted: go() }
                MayaBtn { text: "Done"; onClicked: doneEntry.go() }

                Label { text: "Remove #:"; color: "#8a93b8" }
                TextField { id: removeEntry; Layout.preferredWidth: 60; implicitHeight: 30
                    color: "#e7ebfa"; background: Rectangle { color: "#0b1020"; radius: 6; border.color: "#25305a" }
                    function go() { ui.taskOp("task remove", text); text = "" }
                    onAccepted: go() }
                MayaBtn { text: "Remove"; onClicked: removeEntry.go() }
            }

            Label { text: "OUTPUT"; color: "#9a8cff"; font.pixelSize: 11; font.bold: true }
            TextArea {
                id: tasksOut
                Layout.fillWidth: true
                Layout.preferredHeight: 320
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
        tasksOut.append(text)
        Qt.callLater(function () { scroll.contentY = scroll.contentHeight - scroll.height })
    }
}