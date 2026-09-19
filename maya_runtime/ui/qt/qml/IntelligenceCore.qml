import QtQuick

// Maya Intelligence Core presentation surface — student-centric "orb" redesign.
//
// Presentation-only: paints an abstract orb/pulse whose colour, brightness,
// ring count and node activity all come from the pure core view the bridge
// hands it (schema "maya/intelligence-core/1.0.0"). It never decides Maya's
// state, authority or capability; missing/invalid data fails closed to the
// muted "unavailable" orb and can never be painted as success. Motion is
// declarative QML animation only: no wall clock, no timers, no randomness.
//
// Student-facing core language:
//   mint  = ready      electric = thinking/working
//   gold  = insight    red      = needs attention
Canvas {
    id: coreView

    property var coreData: null
    property string coreSchema: "maya/intelligence-core/1.0.0"
    property string state: "unavailable"
    // Last applied core JSON: identical data never triggers a repaint.
    property string lastJson: ""

    // Animation phases (driven declaratively, never by wall clock)
    property real breath: 0.0
    property real spin: 0.0
    property real pulse: 0.0
    property real errPhase: 0.0

    property var corePalette: {
        "mint": "#4fe0b0",
        "electric": "#3b9dff",
        "gold": "#ffd36e",
        "accent": "#6d7cff",
        "accent2": "#9a8cff",
        "cyan": "#38bdf8",
        "ok": "#4ade80",
        "warn": "#fbbf24",
        "bad": "#ff5c7a",
        "muted": "#8a93b8"
    }

    property var knownStates: {
        "idle": true, "observing": true, "reasoning": true,
        "approval": true, "acting": true, "verifying": true,
        "complete": true, "unavailable": true, "error": true
    }

    function colorFor(key) {
        return corePalette[key] || "#8a93b8"
    }

    // Single student-facing tone per state (colour is never the only channel:
    // Home.qml always pairs it with a text label).
    function toneFor(s) {
        if (s === "idle")
            return "mint"
        if (s === "observing" || s === "reasoning" || s === "acting" || s === "verifying")
            return "electric"
        if (s === "approval" || s === "complete")
            return "gold"
        if (s === "error")
            return "bad"
        return "muted"
    }

    function toneColor(s) {
        return colorFor(toneFor(s))
    }

    function isKnownState(s) {
        return s !== undefined && s !== null && knownStates[s] === true
    }

    function rgba(hex, a) {
        var r = parseInt(hex.substr(1, 2), 16)
        var g = parseInt(hex.substr(3, 2), 16)
        var b = parseInt(hex.substr(5, 2), 16)
        return "rgba(" + r + "," + g + "," + b + "," + a + ")"
    }

    function setCore(json) {
        if (json === lastJson) return
        lastJson = json
        if (json === null || json === undefined || json === "null") {
            coreData = null
            state = "unavailable"
            requestPaint()
            return
        }
        try {
            coreData = JSON.parse(json)
        } catch (err) {
            coreData = null
            state = "unavailable"
            requestPaint()
            return
        }
        if (!coreData || coreData.schema !== "maya/intelligence-core/1.0.0" || !coreData.geometry) {
            coreData = null
            state = "unavailable"
        } else {
            state = isKnownState(coreData.state) ? coreData.state : "unavailable"
        }
        requestPaint()
    }

    // Idle: soft breathing glow.
    SequentialAnimation {
        id: breathAnim
        loops: Animation.Infinite
        running: coreView.coreData !== null && coreView.state === "idle"
        NumberAnimation {
            target: coreView; property: "breath"
            from: 0.0; to: 1.0; duration: 1900; easing.type: Easing.InOutSine
        }
        NumberAnimation {
            target: coreView; property: "breath"
            from: 1.0; to: 0.0; duration: 1900; easing.type: Easing.InOutSine
        }
    }

    // Reasoning/thinking: rotating orbital rings.
    NumberAnimation {
        id: spinAnim
        target: coreView; property: "spin"
        from: 0.0; to: 360.0; duration: 9000
        loops: Animation.Infinite
        running: coreView.coreData !== null
    }

    // Error: subtle rhythmic red shift.
    SequentialAnimation {
        id: errAnim
        loops: Animation.Infinite
        running: coreView.state === "error"
        NumberAnimation {
            target: coreView; property: "errPhase"
            from: 0.0; to: 1.0; duration: 700; easing.type: Easing.InOutSine
        }
        NumberAnimation {
            target: coreView; property: "errPhase"
            from: 1.0; to: 0.0; duration: 700; easing.type: Easing.InOutSine
        }
    }

    // Complete: brief, bright pulse of light.
    SequentialAnimation {
        id: pulseAnim
        NumberAnimation {
            target: coreView; property: "pulse"
            from: 0.0; to: 1.0; duration: 200; easing.type: Easing.OutQuad
        }
        NumberAnimation {
            target: coreView; property: "pulse"
            from: 1.0; to: 0.0; duration: 850; easing.type: Easing.InQuad
        }
    }

    onStateChanged: {
        if (state === "complete")
            pulseAnim.restart()
    }

    onBreathChanged: requestPaint()
    onSpinChanged: requestPaint()
    onPulseChanged: requestPaint()
    onErrPhaseChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()

    onPaint: {
        var ctx = getContext("2d")
        ctx.clearRect(0, 0, width, height)

        var cx = width / 2
        var cy = height / 2
        var base = Math.min(width, height)
        if (base <= 0)
            return

        var known = coreData !== null && coreData.geometry !== undefined
        var tone = known ? toneColor(state) : colorFor("muted")
        var breathe = (known && state === "idle") ? breath : 0.3
        var intense = (known && (state === "reasoning" || state === "acting")) ? 0.5 : 0.0
        var pulseAmt = known ? pulse : 0.0
        var errAmt = (known && state === "error") ? (0.12 + 0.20 * errPhase) : 0.0

        // Outer glow (the "breathing" halo).
        var glowR = base * (0.30 + 0.07 * breathe + 0.05 * pulseAmt)
        var glow = ctx.createRadialGradient(cx, cy, 0, cx, cy, glowR)
        glow.addColorStop(0, rgba(tone, 0.30 + 0.12 * pulseAmt + errAmt))
        glow.addColorStop(0.55, rgba(tone, 0.12 + 0.05 * intense))
        glow.addColorStop(1, rgba(tone, 0.0))
        ctx.fillStyle = glow
        ctx.fillRect(0, 0, width, height)

        // Orbital rings: rotate while reasoning/working, calm otherwise.
        var ringCount = (known && (state === "reasoning" || state === "acting")) ? 3
                      : (known && state === "complete") ? 2 : 1
        ctx.lineCap = "round"
        for (var r = 0; r < ringCount; r++) {
            var rr = base * (0.17 + 0.055 * r)
            var rot = (spin * 3.141592653589793 / 180.0) * (r % 2 === 0 ? 1 : -1) * (1 + r * 0.4)
            var dashOn = (coreData && coreData.pattern) ? Math.max(1, coreData.pattern.dash_on) : 4
            var dashOff = (coreData && coreData.pattern) ? Math.max(1, coreData.pattern.dash_off) : 4
            var segs = 24
            var period = dashOn + dashOff
            ctx.strokeStyle = tone
            ctx.lineWidth = 2.0
            ctx.globalAlpha = 0.55
            for (var i = 0; i < segs; i++) {
                if ((i % period) >= dashOn)
                    continue
                var a0 = rot + 6.283185307179586 * i / segs
                var a1 = rot + 6.283185307179586 * (i + 1) / segs
                ctx.beginPath()
                ctx.arc(cx, cy, rr, a0, a1)
                ctx.stroke()
            }
        }

        // Central orb.
        var coreR = base * (0.095 + 0.012 * breathe + 0.055 * pulseAmt)
        var coreGrad = ctx.createRadialGradient(cx, cy, 0, cx, cy, coreR)
        coreGrad.addColorStop(0, rgba("#ffffff", known ? 0.95 : 0.30))
        coreGrad.addColorStop(0.45, rgba(tone, known ? 0.88 : 0.35))
        coreGrad.addColorStop(1, rgba(tone, 0.12))
        ctx.globalAlpha = 1.0
        ctx.beginPath()
        ctx.arc(cx, cy, coreR, 0, 6.283185307179586)
        ctx.fillStyle = coreGrad
        ctx.fill()

        if (!known) {
            ctx.globalAlpha = 1.0
            return
        }

        // Structured state layers from the core payload: connection nodes and
        // signals. Geometry always arrives as data; QML only paints it.
        var g = coreData.geometry
        ctx.lineWidth = 1.0
        for (var s = 0; s < g.signals.length; s++) {
            if (!g.signals[s].active)
                continue
            ctx.globalAlpha = 0.28
            ctx.strokeStyle = tone
            ctx.beginPath()
            ctx.moveTo(g.signals[s].x1 * width, g.signals[s].y1 * height)
            ctx.lineTo(g.signals[s].x2 * width, g.signals[s].y2 * height)
            ctx.stroke()
        }
        for (var n = 0; n < g.nodes.length; n++) {
            var node = g.nodes[n]
            ctx.beginPath()
            ctx.arc(node.x * width, node.y * height, Math.max(1.5, base * 0.006),
                    0, 6.283185307179586)
            if (node.active) {
                ctx.globalAlpha = 0.9
                ctx.fillStyle = tone
                ctx.fill()
            } else {
                ctx.globalAlpha = 0.30
                ctx.strokeStyle = colorFor("muted")
                ctx.stroke()
            }
        }

        // Pattern ticks: a quiet ring of marks that echoes the state pattern.
        var ticks = (coreData.pattern && coreData.pattern.ticks) ? coreData.pattern.ticks : 0
        ctx.globalAlpha = 0.4
        ctx.strokeStyle = tone
        for (var t = 0; t < ticks; t++) {
            var ta = 6.283185307179586 * t / ticks
            ctx.beginPath()
            ctx.moveTo((0.5 + 0.24 * Math.cos(ta)) * width,
                       (0.5 + 0.24 * Math.sin(ta)) * height)
            ctx.lineTo((0.5 + 0.28 * Math.cos(ta)) * width,
                       (0.5 + 0.28 * Math.sin(ta)) * height)
            ctx.stroke()
        }

        ctx.globalAlpha = 1.0
    }
}
