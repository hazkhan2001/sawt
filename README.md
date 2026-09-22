# Sawt: the Islamic Soundscape Map

Click a place on a globe and hear what it sounds like. Adhan, dhikr, mugham,
maqam and field recordings, each with the context that makes it legible:
where it was recorded, how confident we are about that, who made it, and
under what licence it can be here at all.

Inspired by [Radio Garden](http://radio.garden) and
[The Global Jukebox](https://theglobaljukebox.org), but built around a
different problem. Those projects had archives handed to them. This one has
to find openly licensed recordings in the wild, check the rights on each one,
and admit in the interface where the archive is thin.

**Status: early. The data pipeline is finished and the map runs. Almost
everything else is open.** That is what I want eyes on.

---

## Run it

### On Replit (no setup)

Fork the repl and press Run. It installs dependencies and starts the dev
server on port 3000, which Replit exposes at the repl's public address.
First run takes a couple of minutes because `npm install` has to fetch
Next, React and three.js.

### Locally

```bash
cd web
npm install
npm run dev          # http://localhost:3000
```

Node 20 or newer. No API keys, no database, no `.env`. The page is a static
export: the JSON is compiled into it at build time and the audio is served
from `web/public/audio/`.

To produce the deployable folder:

```bash
npm run build        # writes web/out/, plain files any host will serve
```

---

## What is actually in here

**101 recordings across 63 places**, 60 of which hold something. Ten of the 63
are curated "anchors" meant to carry a written historical essay. The rest are generated from a gazetteer
of about 140 cities, so any geolocated recording can be found by wandering
rather than only by search.

```
genre       adhan 66 · art_music 17 · dhikr_hadra 11 · other 4 · ambience 3
rights      cc-by 38 · cc0 32 · pdm 22 · cc-by-sa 7 · pd-us-pre-cutoff 2
placeBasis  geotag 78 · title 18 · tradition 5
dateBasis   unknown 66 · catalogue 35

busiest     Istanbul 14 · Cairo 6 · Fez 3 · Shusha 3 · Omdurman 3
42 of the 63 places hold exactly one recording
three anchors are empty: Aleppo, Konya, Kashgar
```

Those last two lines are the honest part. **Two thirds of the set is adhan**,
mostly modern field recordings from the last twenty years, because that is
what open archives contain. The classical art music this project is named for
is barely represented, and the three empty anchors are three of the most
important cities in the subject. The map is currently a better picture of
what Creative Commons holds than of what the tradition is.

### Three kinds of certainty, kept apart

`placeBasis` says how a recording got its coordinates: a real GPS `geotag`,
a guess read off a `title`, or a claim about where a `tradition` belongs.
`dateBasis` does the same for time. The interface has to show these
differently. A map that presents an inference with the same confidence as a
fact is lying quietly, and 18 of the 78 placements here are inferences.

---

## Where feedback is most useful

Open an issue, or just tell me. Ranked by how much it would change:

1. **Does the globe read?** Colour carries the tradition family, shape carries
   genre, circle area carries how many recordings sit at that place. Is any of
   that legible without the legend? Does anything look like noise?
2. **The empty and near-empty places.** 42 places have one recording. Is a
   place with one field recording worth showing, or does it make the map feel
   emptier than a map with fewer, fuller places would?
3. **Sources.** This is the highest-value contribution by far. If you know an
   archive, a label with a permissive policy, a university collection, or a
   recordist who shares their work, say so. Especially for Aleppo, Konya,
   Kashgar, and for anything that is not adhan.
4. **The recitation problem.** Quran recitation and adhan are not music and
   must not be presented as such, or crossfaded, or played under anything.
   80 further items are quarantined until that category is built properly.
   How should the interface hold them?
5. **The essays.** Ten anchor hubs need real historical writing. Drafts live
   in `hub_essays.md`. Corrections welcome, particularly from anyone who knows
   a tradition from the inside.
6. **Anything that feels wrong.** A misattributed recording, a place label
   that a local would not recognise, a transliteration that grates.

What would *not* help right now: styling polish, performance tuning, or
framework opinions. The shape of the thing is still moving.

---

## Repo map

```
web/                    the Next.js app (this is what runs)
  app/                  layout and page, both server components
  components/           SawtGlobe.tsx, the whole interface
  lib/                  types.ts is the data contract in TypeScript
  public/data/          hubs.json and tracks.json, compiled into the build
  public/audio/         101 streaming copies, 64kbps mono Opus

site/                   the same JSON, as the Python pipeline writes it

sawt_harvester.py       finds candidates: Commons, radio aporee, Freesound
gallica_harvester.py    the same, for the BnF
gazetteer.py            ~140 cities. Titles to coordinates, and back
genres.py               classification shared across scripts and map
freesound_download.py   OAuth2 downloader, rate-limit aware
fetch_open_audio.py     Commons and archive.org, no auth needed
fetch_attribution.py    recovers missing CC BY credit lines
make_web_audio.py       ffmpeg transcode to 64kbps mono Opus
review.py               local server for listening to and judging candidates
build_site_data.py      THE CONTRACT: pydantic validation into site/*.json
prepare_web.py          copies validated data and audio into web/public/
make_globe.py           the globe.gl prototype the React version came from
test_harvester.py       18 offline tests

SAWT_HARVESTER_GUIDE.md the long version of all of this
permission_letters.md   archive outreach, sent and pending
hub_essays.md           anchor essay drafts
```

Pipeline order: harvest, prune, gazetteer, download, transcode, review,
`build_site_data.py`, `prepare_web.py`.

`build_site_data.py` is the piece worth reading if you read one. Nothing
reaches the site without passing it, so a set of guarantees hold by
construction rather than by anyone remembering: every track points at a hub
that exists, every audio URL is local, every CC BY track carries a credit
line, every rights basis is one of eight permitted values, every coordinate
is in range.

---

## Rights

Everything shipped is CC0, CC BY, CC BY-SA, a Public Domain Mark, or US
public domain by date. Every candidate was listened to by a human before it
shipped, all 231 of them, and the rejections are kept rather than deleted
because the decision is the artifact.

Attribution is a licence condition here, not a courtesy, and it is enforced:
a CC BY track with no credit line fails validation and does not ship. If you
find your recording here and the credit is wrong or you want it removed, open
an issue and it comes down the same day.

A few rules worth knowing before contributing sources:

- An archive.org upload is not a licence, and a licence on a digital transfer
  is not a licence on the recording.
- NonCommercial and NoDerivatives licences are both unusable for this project.
- Quran recitation is a copyrighted performance even though the text is not.
- Anything described as taken from YouTube is rejected on sight.

## Running the pipeline (optional)

Only needed if you want to harvest more. The app does not require it.

```bash
pip install -r requirements.txt   # plus pydantic and ffmpeg on PATH
cp .env.example .env              # add a Freesound key if harvesting there
python sawt_harvester.py --preview
```

Long jobs checkpoint every 25 items and take `--resume`. Destructive steps
print what they would do and wait for `--apply` or `--write`.
