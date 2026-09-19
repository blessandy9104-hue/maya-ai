import QtQuick

// Maya canonical face presentation surface (Batch 8M).
//
// Presentation-only: paints the point list the pure bridge gives it
// (schema "maya/canonical-vector-face/1.0.0"). It never defines landmarks,
// identity geometry, expression semantics or visual state; every coordinate
// comes from the payload and is mapped to local pixels. Colours are
// presentation constants. No randomness, no time reading, no animation loop.
Canvas {
    id: faceView

    property var data: null
    property string faceSchema: "maya/canonical-vector-face/1.0.0"
    property string surfaceColor: "#101218"

    // Presentation palette (colour only; geometry always comes from payload)
    property var palette: {
        "identity": "#8fb7ff",
        "iris": "#9a8cff",
        "pupil": "#e7ebfa",
        "mouth": "#9a8cff",
        "glowA": "rgba(109,124,255,"
    }

    function setFace(json) {
        if (json === null || json === undefined) {
            data = null
            requestPaint()
            return
        }
        try {
            data = JSON.parse(json)
        } catch (err) {
            data = null
            requestPaint()
            return
        }
        // presentation gate: accept only the canonical schema payload
        if (!data || data.schema !== "maya/canonical-vector-face/1.0.0" || !data.surface) {
            data = null
        }
        requestPaint()
    }

    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()

    function colorFor(kind) {
        if (kind === "mouth") return palette.mouth
        if (kind === "iris") return palette.iris
        if (kind === "pupil") return palette.pupil
        return palette.identity
    }

    onPaint: {
        var ctx = getContext("2d")
        ctx.fillStyle = faceView.surfaceColor
        ctx.fillRect(0, 0, width, height)

        if (!data || !data.surface) return

        var i, j, c, x, y, rad
        for (i = 0; i < data.surface.length; i++) {
            c = data.surface[i]
            if (c.op === "clear") {
                ctx.fillStyle = faceView.surfaceColor
                ctx.fillRect(0, 0, width, height)
            } else if (c.op === "path" || c.op === "polyline") {
                ctx.beginPath()
                for (j = 0; j < c.points.length; j++) {
                    x = c.points[j][0] * width
                    y = c.points[j][1] * height
                    if (j === 0) { ctx.moveTo(x, y) } else { ctx.lineTo(x, y) }
                }
                ctx.strokeStyle = colorFor(c.stroke)
                ctx.lineWidth = (c.op === "path") ? 1.6 : 1.1
                ctx.stroke()
            } else if (c.op === "circle") {
                rad = c.radius * width
                ctx.beginPath()
                ctx.arc(c.center[0] * width, c.center[1] * height, rad, 0, 6.283185307179586)
                ctx.fillStyle = colorFor(c.fill)
                ctx.fill()
            } else if (c.op === "anchor") {
                rad = Math.max(1.6, width * 0.004)
                ctx.beginPath()
                ctx.arc(c.point[0] * width, c.point[1] * height, rad, 0, 6.283185307179586)
                ctx.fillStyle = colorFor(c.stroke)
                ctx.fill()
            } else if (c.op === "glow") {
                var glow = ctx.createRadialGradient(width / 2, height / 2, 0,
                                                    width / 2, height / 2, width * 0.46)
                glow.addColorStop(0, palette.glowA + ((0.10 * c.value).toFixed(3)) + ")")
                glow.addColorStop(1, palette.glowA + "0)")
                ctx.fillStyle = glow
                ctx.fillRect(0, 0, width, height)
            }
        }
    }
}