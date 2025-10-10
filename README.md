# One Pace Metadata

## URLs

There are five separate files that are always kept up to date in case you want to develop something with it or keep it up to date:

- **data.json**: Main file with `last_update`, `base_url`, `tvshow`, `arcs`, `episodes`, etc. that gets updated and referenced.
  - [https://raw.githubusercontent.com/ladyisatis/one-pace-metadata/refs/heads/main/data.json](https://raw.githubusercontent.com/ladyisatis/one-pace-metadata/refs/heads/main/data.json)
- **data.min.json**: More compact version of `data.json` that strips out spacing. (On average, this file is 26% smaller than `data.json`, e.g. 359KB becomes 272KB.)
  - [https://raw.githubusercontent.com/ladyisatis/one-pace-metadata/refs/heads/main/data.min.json](https://raw.githubusercontent.com/ladyisatis/one-pace-metadata/refs/heads/main/data.min.json)
- **data.yml**: Main file but in YAML form instead of JSON form.
  - [https://raw.githubusercontent.com/ladyisatis/one-pace-metadata/refs/heads/main/data.yml](https://raw.githubusercontent.com/ladyisatis/one-pace-metadata/refs/heads/main/data.yml)
- **status.json**: Status file that only contains `last_update`, `last_update_ts`, `base_url`, and `version` for tracking versioning without downloading a whole datafile.
  - [https://raw.githubusercontent.com/ladyisatis/one-pace-metadata/refs/heads/main/status.json](https://raw.githubusercontent.com/ladyisatis/one-pace-metadata/refs/heads/main/status.json)
- **status.yml**: Status file but in YAML form instead of JSON form.
  - [https://raw.githubusercontent.com/ladyisatis/one-pace-metadata/refs/heads/main/status.yml](https://raw.githubusercontent.com/ladyisatis/one-pace-metadata/refs/heads/main/status.yml)

The most pertinent values for this will be `last_update` which is compatible with Python's datetime parser, `last_update_ts` in Unix epoch timestamp format as a float, and `base_url` in case the metadata provider location changes and there needs to be a reference point for downloading posters.

These are sourced from these files:

- Posters: https://github.com/ladyisatis/one-pace-metadata/tree/main/posters
- Series Information: https://github.com/ladyisatis/one-pace-metadata/blob/main/tvshow.yml
- Season/Arc Information: https://github.com/ladyisatis/one-pace-metadata/blob/main/arcs.yml
- Episodes by CRC32: https://github.com/ladyisatis/one-pace-metadata/tree/main/episodes

## Information

The metadata is updated [once per hour](https://github.com/ladyisatis/one-pace-metadata/blob/main/.github/workflows/metadata-job.yml#L5) based upon these sources:

- [One Pace Episode Guide](https://docs.google.com/spreadsheets/d/1HQRMJgu_zArp-sLnvFMDzOyjdsht87eFLECxMK858lA/) for CRC32, Manga Chapters, Anime Episodes
- [One Pace Subtitles' title.properties](https://raw.githubusercontent.com/one-pace/one-pace-public-subtitles/refs/heads/main/main/title.properties) for `originaltitle` properties, matching the title in the video files.
- [One Pace Chapters' chapter.properties](https://raw.githubusercontent.com/one-pace/one-pace-public-subtitles/refs/heads/main/main/chapter.properties) for matching manga `chapters` properties to new episodes.
- [One Pace Episode Descriptions](https://docs.google.com/spreadsheets/d/1M0Aa2p5x7NioaH9-u8FyHq6rH3t5s6Sccs8GoC6pHAM/) for descriptions for arcs and episodes
  - Maintained by Craigy from the One Pace team - please tag him in the One Pace Discord if there are missing descriptions for episodes.

Tasks such as generation of metadata from inside a release's folders run every 6 hours, and `tid` information for downloading episodes is updated every Wednesday at 00:00:00 UTC.

## YAML (episodes/*.yml, arcs.yml, tvshow.yml)

Metadata is provided in [YAML format](https://en.wikipedia.org/wiki/YAML#Syntax). Each YAML file is the CRC32 with the .yml extension, e.g. `E5F09F49.yml`.

This CRC32 is based off the 8-character ID at the end of the filename, for example: `[One Pace][1] Romance Dawn 01 [1080p][E5F09F49].mkv`

The contents of the `.yml` file:

```
arc: 1
episode: 1

title: Romance Dawn, the Dawn of an Adventure
# originaltitle:
# sorttitle:
description: Influenced by the straw-hat-wearing pirate Red-Haired Shanks, an enthusiastic young boy named Monkey D. Luffy dreams of one day becoming King of the Pirates.

chapters: 1
episodes: Episode of East Blue, 312 (Intro)
rating: TV-14
released: 2025-05-03 00:42

hashes: 
  crc32: E5F09F49
# blake2: cd1da1484f997a73
```

If there's two clashing CRC32's:
- The original `.yml` should be renamed to end with `_1.yml` instead, with the other one renamed to add `_2.yml`.
  - This ends up as two files, `E5F09F49_1.yml` and `E5F09F49_2.yml`.
- The `hashes` section becomes required, not optional.
  - The value of `crc32` is the original CRC32. (`E5F09F49`)
  - The value of `blake2` is the first 16 characters of the blake2s hash of the file.

If there are new One Pace releases that the automatic updater misses, send a [Pull Request](https://github.com/ladyisatis/one-pace-metadata/pulls) with the added `.yml` in the `episodes` folder. Already-existing `.yml` files do not get overwritten by the automatic metadata updater as long as the `title`, `description`, `chapters`, `episodes`, and `released` fields are not missing or empty.
