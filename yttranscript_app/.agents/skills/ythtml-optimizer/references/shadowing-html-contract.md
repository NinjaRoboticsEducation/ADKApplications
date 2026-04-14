# Shadowing HTML Contract

Use this reference when transforming transcript HTML into the final shadowing page.

## Preferred input shape

The most reliable upstream HTML uses:

```html
<div class="cue">
  <span class="cue-time">[00:00:53.504 --> 00:00:56.180]</span>
  <span class="cue-text">and she taught us a cheer that she said we would be doing</span>
</div>
```

Section headings may appear as `h2`, `h3`, or `h4`. Key takeaways may appear as a titled list.

## Supported fallback cue shapes

- `.cue` elements with `data-start` and `data-end`
- `.cue` elements whose text begins with `[start --> end]`
- flattened HTML whose visible text still contains one cue per line

If none of these shapes are present, the upstream HTML needs to be fixed before the optimizer can create reliable synchronization.

## Required output features

- Embedded YouTube playback on the same page
- Active cue highlighting driven by playback time
- Cue click-to-seek behavior
- `<ruby>` per cue with the transcript text as the main content
- `<rt>` containing the full `[start --> end]` timestamp string
- `<rt>` styled to `font-size: 0.4em`
- Dictionary popup for clicked or selected English words
- Graceful fallback messaging when dictionary lookups or the YouTube API fail
- Local-file preview guidance when the page is opened via `file://`

## Runtime integrations

- YouTube playback and synchronization use the YouTube iframe API
- Dictionary lookup uses the free API at `https://api.dictionaryapi.dev/api/v2/entries/en/<word>`

These services may fail at runtime. The page should still remain usable and readable even if synchronization or dictionary results degrade.

## YouTube error 153 handling

- Error 153 means the embed request is missing the HTTP referrer or equivalent client identity.
- Opening the generated HTML directly as `file://...html` is not a valid embed environment for final QA because it does not provide the HTTP referrer YouTube expects.
- Preview the page through localhost or another HTTP(S) origin before deciding whether the embed is broken.
- When the page is served over HTTP(S), include `origin` and `widget_referrer` in the embed configuration.
- When the page is opened from `file://`, show a clear in-page warning and preserve transcript usability plus cue-to-YouTube fallback.

## Validator assumptions

The bundled validator checks for:

- YouTube embed markers
- cue elements with `data-start` and `data-end`
- `<ruby>` and `<rt>` inside cues
- `font-size: 0.4em` for `<rt>`
- active cue class logic
- dictionary API usage markers
- file-mode detection markers
- `origin` or `widget_referrer` handling for YouTube embeds

It does not prove the whole UX is perfect. After validation, still manually review:

1. playback alignment
2. transcript readability
3. popup placement
4. cue click behavior
5. section and takeaway structure
