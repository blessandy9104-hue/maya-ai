import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: bar
    height: 30
    color: "#101629"

    property var tick: null

    // Phase 4E pipeline visibility: queue depth + drop counter rendered from
    // the bounded ``ui.pipelineJson`` summary (never per event).
    property var pipeline: null

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 14
        anchors.rightMargin: 14
        spacing: 10

        Label { text: "Maya"; color: "#8a93b8"; font.pixelSize: 11; font.bold: true }
        Label {
            id: serviceVal
            text: (bar.tick && bar.tick.service) ? bar.tick.service : "…"
            color: (bar.tick && bar.tick.service_color) ? bar.tick.service_color : "#8a93b8"
            font.pixelSize: 11
        }
        Label { text: "|  Computer"; color: "#8a93b8"; font.pixelSize: 11 }
        Label {
            id: resVal
            text: (bar.tick && bar.tick.resources) ? bar.tick.resources : "…"
            color: (bar.tick && bar.tick.resources_color) ? bar.tick.resources_color : "#8a93b8"
            font.pixelSize: 11
        }
        Label { text: "|  Learning"; color: "#8a93b8"; font.pixelSize: 11 }
        Label {
            id: learnVal
            text: (bar.tick && bar.tick.learning) ? bar.tick.learning : "…"
            color: (bar.tick && bar.tick.learning_color) ? bar.tick.learning_color : "#8a93b8"
            font.pixelSize: 11
        }
        Label { text: "|  Status"; color: "#8a93b8"; font.pixelSize: 11 }
        Label {
            id: presenceVal
            text: (bar.tick && bar.tick.presence) ? bar.tick.presence : "…"
            color: (bar.tick && bar.tick.presence_color) ? bar.tick.presence_color : "#8a93b8"
            font.pixelSize: 11
        }
        Rectangle {
            id: pipeBadge
            visible: bar.pipeline && (bar.pipeline.queued > 0
                                      || bar.pipeline.running > 0
                                      || bar.pipeline.dropped > 0)
            Layout.preferredWidth: pipeRow.implicitWidth + 16
            Layout.preferredHeight: 18
            radius: 9
            color: bar.pipeline.dropped > 0 ? "#231a08" : "#1a2036"
            border.width: 1
            border.color: bar.pipeline.dropped > 0 ? "#ffb454" : "#3b9dff"
            RowLayout {
                id: pipeRow
                anchors.centerIn: parent
                spacing: 6
                Label {
                    text: "Projecting"
                    color: bar.pipeline.dropped > 0 ? "#ffb454" : "#9cc8ff"
                    font.pixelSize: 10
                    font.bold: true
                }
                Label {
                    visible: bar.pipeline.queueDepth > 0
                    text: "Q " + bar.pipeline.queueDepth
                    color: "#8a93b8"
                    font.pixelSize: 10
                }
                Label {
                    visible: bar.pipeline.dropped > 0
                    text: "dropped " + bar.pipeline.dropped
                    color: "#ffb454"
                    font.pixelSize: 10
                }
            }
        }
        Item { Layout.fillWidth: true }
        Label { text: "All actions review-gated   ·   Emergency: Ctrl+Alt+Esc"; color: "#5b6488"; font.pixelSize: 10 }
    }
}