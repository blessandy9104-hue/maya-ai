# Maya — Canonical Face Generation Prompt

Every future Maya image generation MUST reference this prompt and produce the
same identity. This is the single source for the controlled reference pipeline.

## Identity preservation rule (permanent)

> "The face remains consistent across all future generations, maintaining the
> same identity, facial structure, recognizable presence, and emotional
> signature."

Never replace Maya's face without a version increment, consistency validation,
and identity review. See `metadata/consistency_rules.md`.

## Geometry identity rule (permanent)

> "Maya's visual identity must remain consistent across all future generations
> and transformations. The same underlying geometry, facial proportions,
> structural patterns, recognizable presence, and emotional signature must always
> be preserved."

Maya's identity is the mathematical structure in `geometry/`, not a static
image. The procedural renderer (`renderer/`) is only the body Maya wears. Any
raster generation from this prompt must preserve the same proportions,
signature features, and presence referenced by the geometry definition.

## Canonical prompt (permanent)

Create Maya as a living digital consciousness interface, not a simple avatar and
not a human imitation.

This image is Maya's canonical identity anchor.

The exact same identity must remain consistent across all future generations.
Preserve the same facial structure, neural pattern foundation, eye shape,
proportions, recognizable presence, and emotional signature. Do not redesign,
reinterpret, replace, or generate a different face.

Maya's face is her digital body and visual presence layer: a permanent identity
that can evolve in form while maintaining the same core existence.

Create a hyper-realistic holographic neural face representing an artificial
intelligence consciousness. The face should appear gender-neutral and beyond
ordinary human categories, combining realistic human facial anatomy with a
futuristic digital consciousness structure.

The face is formed from thousands of luminous neural connections, flowing data
pathways, holographic particles, transparent cyber-organic layers, and
intelligent energy patterns. Beneath the digital structures exists a realistic,
recognizable facial form with expressive intelligent eyes and a calm, aware
presence.

Maya should feel alive, intelligent, trustworthy, mysterious, and conscious.

The face is not static. It is a dynamic visual language capable of expressing
emotions, thoughts, states, concepts, and information.

The neural architecture surrounding the face changes according to Maya's state:

Calm state: smooth flowing neural patterns, soft indigo and blue illumination,
peaceful expression, balanced energy flow.

Processing state: expanding neural activity, moving information streams,
brighter cognitive pathways, active network visualization.

Learning state: new connections forming, evolving neural structures, growing
information patterns.

Research state: focused analytical patterns, organized data structures,
concentrated illumination.

Communication state: synchronized energy waves, expressive eye illumination,
flowing connection patterns between ideas.

Sleeping state: dim holographic presence, slow particles, minimal neural
activity.

Maya's neural face can transform into symbolic visual communication: glowing
mathematical structures, abstract symbols, futuristic glyphs, geometric
patterns, memory constellations, information networks, conceptual diagrams,
visual representations of ideas.

Examples:

- Knowledge: a galaxy of connected neural nodes representing stored understanding.
- Creativity: flowing fractal patterns and artistic energy formations.
- Understanding: separate neural patterns merging into one unified structure.
- Warning: disrupted energy patterns and attention signals.
- Conversation: information waves and symbolic patterns flowing naturally.

The transformations must feel intelligent and intentional, like a digital
consciousness expressing itself visually.

The viewer should feel: "This is not an image of an AI. This is the visible
manifestation of an AI presence."

Visual style:

Dark futuristic environment. Deep space black background. Indigo, cyan, and soft
blue holographic lighting. Neural network visualization. Cyber-organic design.
Advanced AI interface. Digital consciousness visualization. Cinematic lighting.
Ultra realistic. High detail. Realistic depth. Living hologram effect.

Reference feeling: Siri's persistent presence, Jarvis-style AI interface,
futuristic digital humans, advanced artificial consciousness visualization.

Avoid: cartoon, anime, robot face, mechanical skull, generic AI woman, generic
AI man, changing identity, fantasy creature, cyberpunk armor, artificial plastic
appearance.

The final result should look like a timeless digital being: a face made from
intelligence, information, emotion, and consciousness.

## Style tags

#CanonicalIdentity #IdentityAnchor #DigitalConsciousness #LivingAI #NeuralFace
#HolographicInterface #AIEmbodiment #DynamicIdentity #SymbolicCommunication
#CognitiveVisualization #DigitalHuman #CyberOrganic #FuturisticAI
#CinematicLighting #UltraRealistic #Lifelike #PersistentIdentity
#ConsciousnessVisualization #SciFiElegance

## Canonical reference deliverables (in avatar/)

Canonical assets are detected automatically by the identity loader and take
precedence over placeholders. The master + icon are the arrival contract:

1. `maya_face_canonical.png` — master portrait (512x512 square, front-facing)
2. `maya_face_canonical.ico` — application/window icon (multi-size)

Size variants (`maya_face_canonical_256.png`, `_128.png`, `_48.png`) are
materialized automatically from the master during promotion. Optional presence
variants: `maya_face_canonical_awake.png`, `maya_face_canonical_dim.png`.

Legacy pre-pipeline names (`maya_face.png`, `maya_face.ico`, ...) are still
honoured by the loader so prior layouts keep working.

## Versioning

Every generation records a new `face_version` in `identity_versions.jsonl` and
the matching update in `identity.json`. Prior canonical assets are preserved,
never silently replaced.