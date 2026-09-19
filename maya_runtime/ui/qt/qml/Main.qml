import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

ApplicationWindow {
    id: win
    visible: true
    width: 1180
    height: 800
    minimumWidth: 1020
    minimumHeight: 680
    title: "Maya - Local Intelligence"
    color: "#0a0e1a"

    property bool showWelcome: true

    // Latest view + last applied revision. QML is presentation-only: the same
    // revision is never re-applied, and hidden pages are not fed at all.
    property var lastView: null
    property int lastRevision: -1

    // Phase 4E pipeline visibility (driven from ui.pipelineJson): the first
    // projected view takes ~4.9 s cold / ~140 ms warm, so a non-blank skeleton
    // shows until a view applies or the first projection is ready.
    property bool projectReady: false
    property bool projecting: false
    property int queueDepth: 0
    property int dropCount: 0

    onClosing: ui.closeNow()

    function applyVisibleView(v) {
        if (!v) return
        if (stack.currentIndex === 0) {
            homePage.tick = v
            homePage.setCore(v.core ? JSON.stringify(v.core) : "null")
        } else if (stack.currentIndex === 1) {
            controlPage.liveDataReady(v)
        }
    }

    function refreshVisiblePage() {
        if (win.lastView) { win.applyVisibleView(win.lastView) }
    }

    // Keyboard surface (mirrors the Tk bindings)
    Shortcut { sequence: "Ctrl+Alt+H"; onActivated: nav.currentIndex = 0 }
    Shortcut { sequence: "Ctrl+Alt+S"; onActivated: nav.currentIndex = 1 }
    Shortcut { sequence: "Ctrl+Alt+F"; onActivated: nav.currentIndex = 2 }
    Shortcut { sequence: "Ctrl+Alt+T"; onActivated: nav.currentIndex = 4 }
    Shortcut { sequence: "Ctrl+Alt+G"; onActivated: nav.currentIndex = 5 }
    Shortcut { sequence: "Ctrl+Alt+Esc"; onActivated: ui.emergency() }
    Shortcut { sequence: "Ctrl+Q"; onActivated: win.close() }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            Navigation {
                id: nav
                Layout.fillHeight: true
                onNavigate: function (index) { nav.currentIndex = index }
            }

            StackLayout {
                id: stack
                Layout.fillWidth: true
                Layout.fillHeight: true
                currentIndex: nav.currentIndex
                onCurrentIndexChanged: win.refreshVisiblePage()

                Home {
                    id: homePage
                    onHelpRequested: win.showWelcome = true
                }
                Control {
                    id: controlPage
                }
                World {
                    id: worldPage
                }
                Tasks {
                    id: tasksPage
                }
                Thinking {
                    id: thinkingPage
                }
                Settings {
                    id: settingsPage
                }
            }
        }

        // Phase 4E cold-start skeleton: covers the content pane (never the
        // Navigation rail) until a view applies or the first projection is
        // ready, so the ~4.9 s cold / ~140 ms warm first frame is never a
        // blank pane. Static placeholder only - no timers, no wall clock.
        Rectangle {
            id: skeletonView
            visible: win.lastView === null && !win.projectReady
            anchors.fill: stack
            z: 20
            color: "#0a0e1a"
            Column {
                anchors.centerIn: parent
                spacing: 16
                Rectangle {
                    anchors.horizontalCenter: parent.horizontalCenter
                    width: 42
                    height: 42
                    radius: 21
                    color: "#101629"
                    border.width: 2
                    border.color: "#3b9dff"
                }
                Label {
                    text: "Maya is starting…"
                    color: "#e7ebfa"
                    font.pixelSize: 16
                    font.bold: true
                    anchors.horizontalCenter: parent.horizontalCenter
                }
                Label {
                    text: "Preparing your local intelligence"
                    color: "#8a93b8"
                    font.pixelSize: 11
                    anchors.horizontalCenter: parent.horizontalCenter
                }
            }
        }

        StatusBar {
            id: statusBar
            Layout.fillWidth: true
        }
    }

    function routeLog(page, text, color) {
        if (page === "control") { controlPage.log(text, color) }
        else if (page === "world") { worldPage.log(text, color) }
        else if (page === "tasks") { tasksPage.log(text, color) }
        else if (page === "thinking") { thinkingPage.log(text, color) }
        else if (page === "settings") { settingsPage.log(text, color) }
    }

    Connections {
        target: ui
        function onViewJson(json) {
            var v = JSON.parse(json)
            if (v && v.revision !== undefined) {
                if (v.revision === win.lastRevision) { return }
                win.lastRevision = v.revision
            }
            win.lastView = v
            statusBar.tick = v
            win.applyVisibleView(v)
        }
        function onLogLine(page, text, color) {
            win.routeLog(page, text, color)
        }
        function onPipelineJson(json) {
            var p = JSON.parse(json)
            if (!p) return
            win.projectReady = !!p.ready
            win.projecting = p.ready && (p.queued > 0 || p.running > 0)
            win.queueDepth = (p.queued || 0) + (p.running || 0)
            win.dropCount = p.dropped || 0
            statusBar.pipeline = p
        }
    }

    WelcomeOverlay {
        id: welcome
        anchors.fill: parent
        visible: win.showWelcome
        onDismissed: win.showWelcome = false
    }
}