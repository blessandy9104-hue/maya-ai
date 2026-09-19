import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

Rectangle {
    id: home
    color: "#0a0e1a"

    property var tick: null
    property var core: null
    property var ident: null
    property string identityName: ""
    property string identityVersion: ""
    property string identityTagline: ""
    property string identityRule: ""
    property bool placeholder: true
    property bool advancedOpen: false
    // Reassigned only when the pending set actually changes, so the Repeater
    // is not torn down and rebuilt on every identical tick.
    property var pendingModel: []
    property string pendingSig: ""

    signal helpRequested()

    function applyIdent(json) {
        if (json === null || json === undefined) return
        try { ident = JSON.parse(json) } catch (err) { ident = null; return }
        identityName = (ident && ident.canonical_name) ? ident.canonical_name : ""
        identityVersion = (ident && ident.version) ? String(ident.version) : ""
        identityTagline = (ident && ident.tagline) ? ident.tagline : ""
        identityRule = (ident && ident.critical_identity_rule) ? ident.critical_identity_rule : ""
        placeholder = !identityName
    }

    Connections {
        target: ui
        function onIdentityJson(json) { home.applyIdent(json) }
    }

    function coreColor() {
        if (!core) return "#8a93b8"
        var map = {
            "idle": "#4fe0b0", "observing": "#3b9dff", "reasoning": "#3b9dff",
            "approval": "#ffd36e", "acting": "#3b9dff", "verifying": "#3b9dff",
            "complete": "#ffd36e", "unavailable": "#8a93b8", "error": "#ff5c7a"
        }
        return map[core.state] || "#8a93b8"
    }

    function studentLabel() {
        if (home.tick && home.tick.ui && home.tick.ui.status_label)
            return home.tick.ui.status_label
        if (!core) return "Paused"
        var map = {
            "idle": "Ready", "observing": "Listening", "reasoning": "Thinking",
            "approval": "Needs your OK", "acting": "Working", "verifying": "Checking",
            "complete": "All done", "unavailable": "Paused", "error": "Something's wrong"
        }
        return map[core.state] || "Paused"
    }

    function studentDetail() {
        if (!core) return "Maya is resting."
        var map = {
            "idle": "Maya is awake and ready.",
            "observing": "Maya is listening.",
            "reasoning": "Maya is thinking it through.",
            "approval": "Maya is waiting for your OK before doing anything.",
            "acting": "Maya is working on a permitted, bounded step.",
            "verifying": "Maya is double-checking the result.",
            "complete": "Maya finished and verified that.",
            "unavailable": "Maya is paused — she has no authority data to act on.",
            "error": "Something is wrong; Maya is not acting."
        }
        return map[core.state] || "Maya is paused."
    }

    function healthy() {
        return !!(core && !core.implies_failure
                  && home.tick && home.tick.resources === "safe")
    }

    function healthText() {
        if (!core) return "Checking…"
        if (healthy()) return "System Healthy"
        return core.implies_failure ? "Needs attention" : "Limited"
    }

    function healthColor() {
        if (!core) return "#8a93b8"
        if (healthy()) return "#4fe0b0"
        return core.implies_failure ? "#ff5c7a" : "#ffd36e"
    }

    function updatePending() {
        var items = (home.tick && home.tick.ui && home.tick.ui.pending)
                    ? home.tick.ui.pending : []
        var sig = JSON.stringify(items)
        if (sig === home.pendingSig) return
        home.pendingSig = sig
        home.pendingModel = items
    }

    function pendingItems() {
        return home.pendingModel
    }

    function pendingOpenCount() {
        var items = pendingItems()
        var n = 0
        for (var i = 0; i < items.length; i++)
            if (!items[i].terminal) n++
        return n
    }

    function pendingSummary() {
        if (home.tick && home.tick.ui && home.tick.ui.human_summary)
            return home.tick.ui.human_summary
        return "Nothing needs your approval right now."
    }

    function refreshAdvanced() {
        // The Advanced panel is collapsed by default: never rebuild its text
        // while it is hidden. It refreshes when opened and on later ticks.
        if (!home.advancedOpen) return
        if (!home.tick || !home.tick.live_lines) {
            activityOut.text = ""
        } else {
            activityOut.text = home.tick.live_lines.join("\n")
        }
        var lines = []
        if (core && core.indicators) {
            for (var i = 0; i < core.indicators.length; i++) {
                var it = core.indicators[i]
                lines.push(it.name + "  —  " + it.status)
            }
        }
        trustOut.text = lines.length ? lines.join("\n") : "No saved trust entries yet."
    }

    function setCore(json) {
        if (json === null || json === undefined) {
            core = null
            coreCanvas.setCore("null")
            refreshAdvanced()
            updatePending()
            return
        }
        try {
            core = JSON.parse(json)
        } catch (err) {
            core = null
            coreCanvas.setCore("null")
            refreshAdvanced()
            updatePending()
            return
        }
        coreCanvas.setCore(json)
        refreshAdvanced()
        updatePending()
    }

    onTickChanged: { refreshAdvanced(); updatePending() }
    onAdvancedOpenChanged: if (home.advancedOpen) refreshAdvanced()

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 14
        spacing: 10

        RowLayout {
            Layout.fillWidth: true
            spacing: 10

            Label {
                text: (home.identityName || "MAYA").toUpperCase()
                color: "#e7ebfa"
                font.pixelSize: 18
                font.bold: true
            }
            Label {
                text: home.identityVersion ? ("v" + home.identityVersion) : ""
                color: "#9a8cff"
                font.pixelSize: 11
            }
            Rectangle {
                visible: home.placeholder
                color: "#3a1520"
                radius: 3
                implicitWidth: placeholderLabel.implicitWidth + 8
                implicitHeight: placeholderLabel.implicitHeight + 4
                Label {
                    id: placeholderLabel
                    anchors.centerIn: parent
                    text: "PLACEHOLDER IDENTITY"
                    color: "#ff7f9b"
                    font.pixelSize: 9
                    font.bold: true
                }
            }
            Item { Layout.fillWidth: true }
            Rectangle {
                radius: 13
                implicitWidth: healthRow.implicitWidth + 20
                implicitHeight: 26
                color: "#0d1322"
                border.width: 1
                border.color: home.healthColor()
                RowLayout {
                    id: healthRow
                    anchors.centerIn: parent
                    spacing: 7
                    Rectangle {
                        width: 9; height: 9; radius: 5
                        color: home.healthColor()
                    }
                    Label {
                        text: home.healthText()
                        color: home.healthColor()
                        font.pixelSize: 11
                        font.bold: true
                    }
                }
            }
            MayaBtn {
                text: "What do the colors mean?"
                borderColor: "#1b2340"
                onClicked: home.helpRequested()
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 12

            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumWidth: 420
                spacing: 10

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 210
                    Layout.minimumHeight: 170
                    radius: 10
                    color: "#0d1322"
                    border.color: "#25305a"
                    border.width: 1

                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 12
                        spacing: 14

                        Item {
                            Layout.preferredWidth: 170
                            Layout.fillHeight: true
                            Layout.minimumWidth: 130
                            IntelligenceCore {
                                id: coreCanvas
                                anchors.fill: parent
                            }
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            spacing: 4
                            Label {
                                text: home.studentLabel()
                                color: home.coreColor()
                                font.pixelSize: 22
                                font.bold: true
                            }
                            Label {
                                Layout.fillWidth: true
                                Layout.minimumWidth: 0
                                text: home.studentDetail()
                                color: "#e7ebfa"
                                font.pixelSize: 12
                                wrapMode: Text.Wrap
                            }
                            Label {
                                Layout.fillWidth: true
                                Layout.minimumWidth: 0
                                text: home.identityTagline
                                color: "#5b6488"
                                font.pixelSize: 10
                                wrapMode: Text.Wrap
                            }
                            Item { Layout.fillHeight: true }
                            Label {
                                Layout.fillWidth: true
                                Layout.minimumWidth: 0
                                visible: core && core.implies_failure
                                text: "Maya is not acting. A paused or error state can never mean she is safe, allowed or finished."
                                color: "#ff7f9b"
                                font.pixelSize: 9
                                wrapMode: Text.Wrap
                            }
                        }
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10

                    ActionCard {
                        Layout.fillWidth: true
                        accent: "#4fe0b0"
                        title: "Summarize This"
                        subtitle: "Ask Maya to sum up what you have been working on."
                        onClicked: ui.chatSend("Please summarize what we have been working on.")
                    }
                    ActionCard {
                        Layout.fillWidth: true
                        accent: "#3b9dff"
                        title: "Find Connections"
                        subtitle: "Let Maya link ideas across what she has saved."
                        onClicked: ui.chatSend("Find connections between the ideas I have been working on.")
                    }
                    ActionCard {
                        Layout.fillWidth: true
                        accent: "#ffd36e"
                        title: "Organize My Day"
                        subtitle: "Turn today's plan into a clear, ordered list."
                        onClicked: ui.chatSend("Help me organize my day into a simple plan.")
                    }
                }

                Console {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumHeight: 220
                }
            }

            ColumnLayout {
                Layout.preferredWidth: 300
                Layout.maximumWidth: 340
                Layout.fillHeight: true
                spacing: 10

                Rectangle {
                    Layout.fillWidth: true
                    Layout.minimumHeight: mstatus.implicitHeight + 20
                    radius: 10
                    color: "#101629"
                    border.color: "#25305a"
                    border.width: 1
                    ColumnLayout {
                        id: mstatus
                        anchors.fill: parent
                        anchors.margins: 10
                        spacing: 6
                        Label {
                            text: "Maya's Status"
                            color: "#9a8cff"
                            font.pixelSize: 12
                            font.bold: true
                        }
                        RowLayout {
                            Label { text: "Doing"; color: "#8a93b8"; Layout.preferredWidth: 70; font.pixelSize: 11 }
                            Label { text: home.studentLabel(); color: home.coreColor(); font.bold: true; font.pixelSize: 11 }
                            Item { Layout.fillWidth: true }
                        }
                        RowLayout {
                            Label { text: "Awake"; color: "#8a93b8"; Layout.preferredWidth: 70; font.pixelSize: 11 }
                            Label {
                                text: (home.tick && home.tick.service) ? home.tick.service : "…"
                                color: (home.tick && home.tick.service_color) ? home.tick.service_color : "#8a93b8"
                                font.pixelSize: 11
                            }
                            Item { Layout.fillWidth: true }
                        }
                        RowLayout {
                            Label { text: "Learning"; color: "#8a93b8"; Layout.preferredWidth: 70; font.pixelSize: 11 }
                            Label {
                                text: (home.tick && home.tick.learning) ? home.tick.learning : "…"
                                color: (home.tick && home.tick.learning_color) ? home.tick.learning_color : "#8a93b8"
                                font.pixelSize: 11
                            }
                            Item { Layout.fillWidth: true }
                        }
                        Label {
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            text: "You stay in control. Maya asks before she acts."
                            color: "#5b6488"
                            font.pixelSize: 9
                            wrapMode: Text.Wrap
                        }
                    }
                }

                Rectangle {
                    id: pendingPanel
                    Layout.fillWidth: true
                    visible: home.pendingOpenCount() > 0
                    Layout.preferredHeight: visible ? (pendingCol.implicitHeight + 20) : 0
                    radius: 10
                    color: "#1a1608"
                    border.color: "#ffd36e"
                    border.width: 1

                    ColumnLayout {
                        id: pendingCol
                        anchors.fill: parent
                        anchors.margins: 10
                        spacing: 6

                        Label {
                            text: "Needs your OK"
                            color: "#ffd36e"
                            font.pixelSize: 12
                            font.bold: true
                        }
                        Label {
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            text: home.pendingSummary()
                            color: "#e7ebfa"
                            font.pixelSize: 10
                            wrapMode: Text.Wrap
                        }
                        Repeater {
                            model: home.pendingItems()
                            delegate: Rectangle {
                                id: pendingItem
                                property string itemId: modelData.id
                                property var itemControls: modelData.controls
                                Layout.fillWidth: true
                                visible: !modelData.terminal
                                implicitHeight: (visible ? pendingItemRow.implicitHeight : 0) + 12
                                radius: 6
                                color: "#0d1322"

                                RowLayout {
                                    id: pendingItemRow
                                    anchors.fill: parent
                                    anchors.margins: 6
                                    spacing: 6

                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        Layout.minimumWidth: 0
                                        Label {
                                            Layout.fillWidth: true
                                            Layout.minimumWidth: 0
                                            text: modelData.title
                                            color: "#e7ebfa"
                                            font.pixelSize: 11
                                            font.bold: true
                                            wrapMode: Text.Wrap
                                        }
                                        Label {
                                            Layout.fillWidth: true
                                            Layout.minimumWidth: 0
                                            text: modelData.required_action + " - " + modelData.next_step
                                            color: "#8a93b8"
                                            font.pixelSize: 9
                                            wrapMode: Text.Wrap
                                        }
                                    }
                                    Repeater {
                                        model: pendingItem.itemControls
                                        delegate: MayaBtn {
                                            text: modelData
                                            onClicked: ui.pendingAction(pendingItem.itemId, modelData)
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.fillHeight: home.advancedOpen
                    Layout.preferredHeight: home.advancedOpen ? 0 : 40
                    radius: 10
                    color: "#101629"
                    border.color: "#25305a"
                    border.width: 1
                    clip: true

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 10
                        spacing: 8

                        RowLayout {
                            Layout.fillWidth: true
                            Label {
                                text: "Advanced / Developer"
                                color: "#9a8cff"
                                font.pixelSize: 11
                                font.bold: true
                            }
                            Item { Layout.fillWidth: true }
                            MayaBtn {
                                text: home.advancedOpen ? "Hide" : "Show"
                                onClicked: home.advancedOpen = !home.advancedOpen
                            }
                        }

                        ColumnLayout {
                            visible: home.advancedOpen
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            spacing: 6

                            Label {
                                text: "Activity (technical)"
                                color: "#5b6488"
                                font.pixelSize: 9
                            }
                            TextArea {
                                id: activityOut
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                Layout.minimumHeight: 120
                                readOnly: true
                                color: "#e7ebfa"
                                font.family: "Consolas"
                                font.pixelSize: 9
                                textFormat: TextEdit.PlainText
                                background: Rectangle { color: "#0d1322"; radius: 6; border.color: "#25305a" }
                                focus: false
                            }
                            Label {
                                text: "Trust list"
                                color: "#5b6488"
                                font.pixelSize: 9
                            }
                            TextArea {
                                id: trustOut
                                Layout.fillWidth: true
                                Layout.preferredHeight: 92
                                readOnly: true
                                color: "#e7ebfa"
                                font.family: "Consolas"
                                font.pixelSize: 9
                                textFormat: TextEdit.PlainText
                                background: Rectangle { color: "#0d1322"; radius: 6; border.color: "#25305a" }
                                focus: false
                            }
                        }
                    }
                }

                Item { Layout.fillHeight: !home.advancedOpen }
            }
        }
    }
}
