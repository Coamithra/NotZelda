# Runbook: Adding Music Tracks

Step-by-step guide for adding a new MP3 to the game.

## 1. Place the file

Put the MP3 in the appropriate `music/` subdirectory:
- `music/overworld/` — overworld area themes
- `music/dungeon1/` — Dark Dungeon ambient + boss
- `music/dungeon2/` — Water Temple ambient + boss
- `music/dungeon3/` — Desert Tomb ambient + boss
- `music/other/` — menu, credits, etc.

Use **underscores** in filenames, not spaces (e.g. `castle_ruins.mp3`).

## 2. Update metadata via `tag_music.py`

Open `tools/tag_music.py` and:

**a)** If this track needs a new artwork theme, add a 3x3 tile layout to the `LAYOUTS` dict using tiles from the `TILES` dict (GR, TR, DW, DF, WA, SH, ST):

```python
"castle": [
    ["DW", "ST", "DW"],
    ["ST", "DF", "ST"],
    ["DW", "ST", "DW"],
],
```

**b)** Add the track to the `TRACKS` list:

```python
("overworld/castle_ruins.mp3", "Castle Ruins", "castle"),
```

Format: `(relative_path, title, theme)` — the title becomes the ID3 title tag.

**c)** Check the `ARTIST` and `COMMENT` constants at the top of the file. Defaults are `"Legends of Amara"` and `"Made with Suno"` — change if the track has a different artist or origin.

**d)** Run the tagger:

```
python tools/tag_music.py
```

To tag a single track instead of all, pass a filename fragment:

```
python tools/tag_music.py desert_c
```

This overwrites existing MP3 metadata (cleaning up Suno defaults etc.) with the title, artist, and comment from the script, and embeds a pixel-art cover generated from the tile layout. Previews saved to `tools/artwork_preview/`.

## 3. Add the server route

In `mud_server.py`, add a static file route in the `STATIC_FILES` dict (around line 289):

```python
"/music_castle_ruins.mp3": ("music/overworld/castle_ruins.mp3", "audio/mpeg"),
```

Pattern: `"/music_{name}.mp3": ("music/{subdir}/{filename}.mp3", "audio/mpeg")`

## 4. Register in the client music system

In `client/music.js`:

**a)** Add to `MUSIC_TRACKS` (explicit music field mapping):

```javascript
"castle_ruins": "music_castle_ruins.mp3",
```

**b)** Optionally update `BIOME_MUSIC` if this track should be the default for a biome:

```javascript
"castle": "music_castle_ruins.mp3",
```

## 5. Add to the OST page

In `client/ost.html`, add a track entry to the `TRACKS` array in the `<script>` block:

```javascript
{ title: "Castle Ruins", area: "Ruined Castle", url: "music_castle_ruins.mp3" },
```

- Use a `section` property on the first track of a new group to start a new section header:
  ```javascript
  { section: "The Dark Dungeon", title: "Dungeon Ambient I", area: "Dark Dungeon — Exploration", url: "music_dungeon2.mp3" },
  ```
- Choir tracks are not listed separately — only the main boss/ambient tracks appear.
- The page is served at `/ost`.

## 6. Assign to rooms

Either:
- Set `music=castle_ruins` in the `.room` file header (explicit per-room), or
- Rely on the `BIOME_MUSIC` fallback if the biome mapping is set (step 4b)

## Summary checklist

- [ ] MP3 placed in `music/{subdir}/` with underscored filename
- [ ] Track + theme added to `tools/tag_music.py`, tagger run
- [ ] Static route added in `mud_server.py`
- [ ] Track registered in `client/music.js` MUSIC_TRACKS
- [ ] Track entry added to `client/ost.html` TRACKS array
- [ ] Biome fallback or room-level `music=` field set
- [ ] Commit the MP3 + code changes
