import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: settingsPage
    color: "#0a0e1a"

    property var settings: null
    property var suggestions: []
    property bool advancedOpen: false

    Flickable {
        id: scroll
        anchors.fill: parent
        contentHeight: body.implicitHeight
        clip: true
        ScrollBar.vertical: ScrollBar {}

        ColumnLayout {
            id: body
            width: settingsPage.width
            anchors.margins: 14
            spacing: 10

            Label { text: "Your Settings"; color: "#e7ebfa"; font.pixelSize: 19; font.bold: true }
            Label {
                text: "Simple controls for what Maya may do. Every change here is logged, and nothing in this panel invents new behaviour."
                color: "#8a93b8"; font.pixelSize: 10; wrapMode: Text.Wrap
                Layout.fillWidth: true
                Layout.minimumWidth: 0
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 12

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 10

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.minimumHeight: stateCol.implicitHeight + 20
                        radius: 8; color: "#101629"; border.color: "#25305a"; border.width: 1
                        ColumnLayout {
                            id: stateCol
                            anchors.fill: parent; anchors.margins: 10; spacing: 6
                            Label { text: "AT A GLANCE"; color: "#9a8cff"; font.pixelSize: 11; font.bold: true }

                            RowLayout {
                                Label { text: "Service"; color: "#8a93b8"; Layout.preferredWidth: 120 }
                                Label {
                                    text: valueOf("service")
                                    color: colorOf("service")
                                    font.bold: true
                                }
                                Item { Layout.fillWidth: true }
                                MayaBtn { text: "Wake"; onClicked: ui.enterCommand("settings", ":wake") }
                                MayaBtn { text: "Sleep"; onClicked: ui.enterCommand("settings", ":sleep") }
                            }
                            RowLayout {
                                Label { text: "Maya's Status"; color: "#8a93b8"; Layout.preferredWidth: 120 }
                                Label { text: valueOf("presence_mode"); color: colorOf("presence_mode"); font.bold: true }
                                Item { Layout.fillWidth: true }
                                MayaBtn { text: "Clear Emergency Stop"; textColor: "#fbbf24"
                                    onClicked: ui.presenceAction("reset-stop", "settings") }
                            }
                            RowLayout {
                                Label { text: "Emergency Stop"; color: "#8a93b8"; Layout.preferredWidth: 120 }
                                Label { text: valueOf("stop"); color: colorOf("stop"); font.bold: true }
                            }
                            RowLayout {
                                Label { text: "App Control"; color: "#8a93b8"; Layout.preferredWidth: 120 }
                                Label { text: valueOf("owner"); color: colorOf("owner"); font.bold: true }
                            }
                            RowLayout {
                                Label { text: "Voice sync"; color: "#8a93b8"; Layout.preferredWidth: 120 }
                                Label { text: valueOf("voice"); color: colorOf("voice"); font.bold: true }
                            }

                            Label {
                                Layout.fillWidth: true
                                Layout.minimumWidth: 0
                                text: "owner_control_enabled is a launch permission for allow-listed local apps. It is read-only here; enabling remains a deliberate manual policy-file edit."
                                color: "#5b6488"; font.pixelSize: 9; wrapMode: Text.Wrap
                            }
                        }
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.minimumHeight: cacheCol.implicitHeight + 20
                        radius: 8; color: "#101629"; border.color: "#25305a"; border.width: 1
                        ColumnLayout {
                            id: cacheCol
                            anchors.fill: parent; anchors.margins: 10; spacing: 6
                            Label { text: "SAVED KNOWLEDGE"; color: "#9a8cff"; font.pixelSize: 11; font.bold: true }
                            Label {
                                text: (settingsPage.settings && settingsPage.settings.cache_text) ? settingsPage.settings.cache_text : "…"
                                color: "#e7ebfa"; font.family: "Consolas"; font.pixelSize: 10
                            }
                            RowLayout {
                                Label { text: "Max saved items"; color: "#8a93b8"; Layout.preferredWidth: 120 }
                                TextField {
                                    id: capEntry; Layout.preferredWidth: 110; implicitHeight: 30
                                    color: "#e7ebfa"
                                    background: Rectangle { color: "#0b1020"; radius: 6; border.color: "#25305a" }
                                }
                                Label { text: "Days before stale"; color: "#8a93b8"; Layout.preferredWidth: 120 }
                                TextField {
                                    id: ttlEntry; Layout.preferredWidth: 110; implicitHeight: 30
                                    color: "#e7ebfa"
                                    background: Rectangle { color: "#0b1020"; radius: 6; border.color: "#25305a" }
                                }
                            }
                            RowLayout {
                                Item { Layout.fillWidth: true }
                                MayaBtn { text: "Save knowledge settings"; fill: "#6d7cff"; textColor: "#e7ebfa"
                                    onClicked: ui.applyCache(capEntry.text, ttlEntry.text) }
                                MayaBtn { text: "Clear saved knowledge"; textColor: "#ff5c7a"
                                    onClicked: ui.clearCache() }
                            }
                        }
                    }
                }

                Rectangle {
                    Layout.preferredWidth: 460
                    Layout.minimumWidth: 0
                    Layout.fillHeight: true
                    radius: 8; color: "#101629"; border.color: "#25305a"; border.width: 1
                    ColumnLayout {
                        anchors.fill: parent; anchors.margins: 10; spacing: 6
                        RowLayout {
                            Label { text: "IDEAS TO REVIEW"; color: "#9a8cff"; font.pixelSize: 11; font.bold: true }
                            Item { Layout.fillWidth: true }
                            Label {
                                text: (settingsPage.suggestions && settingsPage.suggestions.length !== undefined) ? String(settingsPage.suggestions.length) + " pending" : "…"
                                color: "#8a93b8"; font.pixelSize: 10
                            }
                            MayaBtn { text: "Refresh"; onClicked: ui.refreshSuggestions() }
                        }

                        ListView {
                            id: sugList
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            clip: true
                            model: ListModel { id: sugModel }
                            delegate: Rectangle {
                                width: sugList.width
                                height: 42
                                color: "#161d33"
                                radius: 4
                                RowLayout {
                                    anchors.fill: parent
                                    anchors.margins: 6
                                    ColumnLayout {
                                        spacing: 1
                                        Layout.fillWidth: true
                                        Layout.minimumWidth: 0
                                        Label { text: suggestionId; color: "#9a8cff"; font.family: "Consolas"; font.pixelSize: 9 }
                                        Label {
                                            text: goal
                                            color: "#e7ebfa"; font.pixelSize: 10
                                            Layout.fillWidth: true
                                            Layout.minimumWidth: 0
                                            elide: Text.ElideRight
                                            maximumLineCount: 1
                                        }
                                    }
                                    Item { Layout.fillWidth: true }
                                    MayaBtn {
                                        text: "Approve"; textColor: "#4ade80"
                                        onClicked: ui.suggestionReview(suggestionId, "approve")
                                    }
                                    MayaBtn {
                                        text: "Reject"; textColor: "#ff5c7a"
                                        onClicked: ui.suggestionReview(suggestionId, "reject")
                                    }
                                }
                            }
                        }
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.minimumHeight: 40
                Layout.preferredHeight: settingsPage.advancedOpen ? (mathLog.implicitHeight + 78) : 40
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
                            text: settingsPage.advancedOpen ? "Hide" : "Show"
                            onClicked: settingsPage.advancedOpen = !settingsPage.advancedOpen
                        }
                    }
                    Label {
                        visible: settingsPage.advancedOpen
                        text: "SETTINGS ACTIVITY LOG"
                        color: "#5b6488"; font.pixelSize: 9
                    }
                    TextArea {
                        id: mathLog
                        visible: settingsPage.advancedOpen
                        Layout.fillWidth: true
                        Layout.preferredHeight: 170
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
        mathLog.append(text)
        Qt.callLater(function () { scroll.contentY = scroll.contentHeight - scroll.height })
    }

    function valueOf(key) {
        return (settingsPage.settings && settingsPage.settings[key]) ? settingsPage.settings[key][0] : "…"
    }
    function colorOf(key) {
        return (settingsPage.settings && settingsPage.settings[key]) ? settingsPage.settings[key][1] : "#8a93b8"
    }

    function applySettings(json) {
        if (json === null || json === undefined) { settingsPage.settings = null; return }
        try { settingsPage.settings = JSON.parse(json) } catch (e) { settingsPage.settings = null; return }
        if (capEntry && settingsPage.settings.cache_cap !== null && settingsPage.settings.cache_cap !== undefined && settingsPage.settings.cache_cap !== "") {
            capEntry.text = String(settingsPage.settings.cache_cap)
        }
        if (ttlEntry && settingsPage.settings.cache_ttl !== null && settingsPage.settings.cache_ttl !== undefined && settingsPage.settings.cache_ttl !== "") {
            ttlEntry.text = String(settingsPage.settings.cache_ttl)
        }
    }

    function applySuggestions(json) {
        sugModel.clear()
        if (json === null || json === undefined) return
        try { settingsPage.suggestions = JSON.parse(json) } catch (e) { settingsPage.suggestions = []; return }
        if (!Array.isArray(settingsPage.suggestions)) return
        for (var i = 0; i < settingsPage.suggestions.length; i++) {
            var item = settingsPage.suggestions[i]
            if (!item) continue
            sugModel.append({
                "suggestionId": item.suggestion_id || "?",
                "goal": String(item.individual_goal || item.goal || item.label || "") .slice(0, 160)
            })
        }
    }

    Connections {
        target: ui
        function onSettingsJson(json) { settingsPage.applySettings(json) }
        function onSuggestionsJson(json) { settingsPage.applySuggestions(json) }
    }
}