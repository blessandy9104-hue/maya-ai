import QtQuick

Canvas {
    id: shapeView

    property var frame: null
    property var shapeColors: { "core": "#5884d8", "core_dim": "#3a4f8f", "ring": "#d8b46c", "pointer": "#bedca0", "bg": "#101218" }
    property string caption: "temp embodiment · state-driven"

    function setFrame(json) {
        if (json === null || json === undefined) {
            frame = null
            requestPaint()
            return
        }
        try {
            frame = JSON.parse(json)
        } catch (err) {
            frame = null
            requestPaint()
            return
        }
        shapeColors = (frame && frame.shape_colors) ? frame.shape_colors : shapeColors
        requestPaint()
    }

    onFrameChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()

    onPaint: {
        var ctx = getContext("2d")
        ctx.fillStyle = shapeColors["bg"] || "#101218"
        ctx.fillRect(0, 0, width, height)

        if (!frame || !frame.shape) {
            var cx0 = width / 2
            var cy0 = height / 2
            var r0 = width * 0.1152
            ctx.beginPath()
            ctx.arc(cx0, cy0, r0, 0, 6.283185307179586)
            ctx.fillStyle = shapeColors["core_dim"] || "#3a4f8f"
            ctx.fill()
            return
        }

        var sh = frame.shape
        var cx = sh.cx * width
        var cy = sh.cy * height
        var rad = sh.radius * width

        ctx.beginPath()
        ctx.arc(cx, cy, rad, 0, 6.283185307179586)
        ctx.fillStyle = sh.resting ? shapeColors["core_dim"] : shapeColors["core"]
        ctx.fill()

        if (frame.ring) {
            ctx.beginPath()
            var pts = frame.ring
            for (var i = 0; i < pts.length; i++) {
                var px = pts[i].x * width
                var py = pts[i].y * height
                if (i === 0) { ctx.moveTo(px, py) } else { ctx.lineTo(px, py) }
            }
            ctx.closePath()
            ctx.strokeStyle = shapeColors["ring"]
            ctx.lineWidth = 2
            ctx.stroke()
        }

        var ptr = frame.pointer
        if (ptr && ptr.visible) {
            ctx.beginPath()
            ctx.moveTo(ptr.x1 * width, ptr.y1 * height)
            ctx.lineTo(ptr.x2 * width, ptr.y2 * height)
            ctx.strokeStyle = shapeColors["pointer"]
            ctx.lineWidth = 2
            ctx.stroke()
        }
    }
}