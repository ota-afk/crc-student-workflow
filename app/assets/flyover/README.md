# Flyover artwork

The user supplied the hand-drawn logo and three travel photographs in this chat on
2026-11-17. `logo-original.png` preserves the source drawing; an SVG color matrix maps
its black strokes to `#629677` at render time without retracing it or changing the file.

The built-in imagegen tool generated these local illustrations from the respective
reference photographs. No CLI or paid OpenAI API integration was used by the app.

- `tokyo.png`: Shibuya Crossing, Tokyo at blue hour, broad diagonal zebra crossing,
  blocky storefront towers and illuminated billboards.
- `san-francisco.png`: Bay Bridge suspension towers and diagonal roadway sweeping
  toward the San Francisco skyline, bay water at sunset.
- `las-vegas.png`: Las Vegas Strip at dusk, Bellagio fountain lake, Paris Las Vegas
  Eiffel Tower replica, hotel blocks and little glowing lights.

## Prompt set

Each built-in call used its corresponding user photograph as a geographic reference,
with this shared prompt and the scene description above substituted for `[scene]`:

> Use case: style-transfer. Asset type: wide website travel banner illustration.
> Use the input photo as a geographic reference, transform it into an original
> playful educational-app low-poly illustration: [scene]. Flat geometric shapes,
> softly rounded edges, simple faceted architecture, uncluttered charming toy-like
> forms reminiscent of Duolingo's environmental illustration aesthetic, no mascots.
> Muted but lively palette of sage #629677, peach #E6CCBE and twilight periwinkle
> #777DA7, warm cloud ivory, restrained yellow window lights. Wide landscape 3:1
> composition, recognizable landmarks concentrated in center and right; quiet
> lighter open space on the left behind a profile form. No text, no logos, no
> labels, no lettering, no watermark, no photographic texture, no UI. Make this
> a finished illustration filling the full canvas.

The three-piece SVG map is decorative geographic artwork, not a navigational map.
Its reveals are driven by completed backend tasks. Cached assets contain no student data.


## First-page revision - 17 November 2026

Replaced the three city PNGs using the original photographs extracted from page 5
of the supplied flyover-ai-handoff.pdf. Built-in imagegen was used, one call per
photo. Prompts required matching the original camera and landmark placement,
crisp opaque polygon faces, stronger city-specific colors, and no haze/pastel wash.
Tokyo retains diagonal crossings, curved billboard facade and right glass tower;
San Francisco retains the X-braced Bay Bridge tower and diagonal orange roadway;
Las Vegas retains Bellagio fountain rings, Paris tower, hotel and blue balloon.

logo-original.png remains untouched. logo-peach.png is a generated recoloring
reference preserving the hand-drawn composition, green interiors and white
outlines on peach. It is an imagegen derivative, not a pixel-exact tracing.
CSS header background is exactly #E6CCBE. Generated raster tones can vary slightly.

The map now reveals more of its three interlocking pieces on every confirmed
completion. Full-piece milestones remain first completion / halfway / final.
