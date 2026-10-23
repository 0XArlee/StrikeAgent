# The demo video

A two-minute demo of EdgeCraft-StrikeCity, built with [Remotion](https://www.remotion.dev): recordings of the live
product on Strike mainnet (1920×1080, Chrome's screencast), cut with `@remotion/transitions` and kinetic type in IBM Plex.

- `src/Demo.tsx`: the cut, fifteen beats.
- `public/clips/`: the recordings (not in the repository: they are made again by the recording script).

```console
npm i
npx remotion studio                                        # preview
npx remotion render Demo out/EdgeCraft-StrikeCity-demo.mp4 --crf=18
```

Remotion is free for individuals and small teams; check its licence before any other use.
