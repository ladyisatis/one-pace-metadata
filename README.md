# One Pace Metadata

Metadata updater for One Pace. Every hour, the metadata updater will check an RSS feed for new releases and update the repository accordingly. Every 6 hours, the Episode Descriptions and Episode Guides spreadsheets are checked for new information.

All updates and batch metadata files are made in the [arcs](https://github.com/ladyisatis/one-pace-metadata/tree/v2/arcs) and [episodes](https://github.com/ladyisatis/one-pace-metadata/tree/v2/episodes) folder respectively, with the former holding information on titles and descriptions, and the latter defining the information on the video file.

The data.json and data.min.json will stay for compatibility reasons for One Pace Organizer support, but this will go away 3 months after v1.2.0 is released.

## URLs

* **One Pace Data (Total)** - Biggest file that includes arc and episode file information, status, as well as descriptions.
  * **data.json**: [https://raw.githubusercontent.com/ladyisatis/one-pace-metadata/refs/heads/v2/metadata/data.json](https://raw.githubusercontent.com/ladyisatis/one-pace-metadata/refs/heads/v2/metadata/data.json)
  * **data.min.json**: [https://raw.githubusercontent.com/ladyisatis/one-pace-metadata/refs/heads/v2/metadata/data.min.json](https://raw.githubusercontent.com/ladyisatis/one-pace-metadata/refs/heads/v2/metadata/data.min.json)
  * **data.yml**: [https://raw.githubusercontent.com/ladyisatis/one-pace-metadata/refs/heads/v2/metadata/data.yml](https://raw.githubusercontent.com/ladyisatis/one-pace-metadata/refs/heads/v2/metadata/data.yml)
  * **data.sqlite**: [https://raw.githubusercontent.com/ladyisatis/one-pace-metadata/refs/heads/v2/metadata/data.sqlite](https://raw.githubusercontent.com/ladyisatis/one-pace-metadata/refs/heads/v2/metadata/data.sqlite)
  * **data_with_posters.sqlite**: [https://raw.githubusercontent.com/ladyisatis/one-pace-metadata/refs/heads/v2/metadata/data_with_posters.sqlite](https://raw.githubusercontent.com/ladyisatis/one-pace-metadata/refs/heads/v2/metadata/data_with_posters.sqlite)

* **Status Information** - When the data was last updated and version numbers.
  * **status.json**: [https://raw.githubusercontent.com/ladyisatis/one-pace-metadata/refs/heads/v2/metadata/status.json](https://raw.githubusercontent.com/ladyisatis/one-pace-metadata/refs/heads/v2/metadata/status.json)
  * **status.yml**: [https://raw.githubusercontent.com/ladyisatis/one-pace-metadata/refs/heads/v2/metadata/status.yml](https://raw.githubusercontent.com/ladyisatis/one-pace-metadata/refs/heads/v2/metadata/status.yml)

* **Arc Information** - Includes arcs with the arc title, descriptions, and episode listings with CRC32 IDs.
  * **arcs.json**: [https://raw.githubusercontent.com/ladyisatis/one-pace-metadata/refs/heads/v2/metadata/arcs.json](https://raw.githubusercontent.com/ladyisatis/one-pace-metadata/refs/heads/v2/metadata/arcs.json)
  * **arcs.min.json**: [https://raw.githubusercontent.com/ladyisatis/one-pace-metadata/refs/heads/v2/metadata/arcs.min.json](https://raw.githubusercontent.com/ladyisatis/one-pace-metadata/refs/heads/v2/metadata/arcs.min.json)
  * **arcs.yml**: [https://raw.githubusercontent.com/ladyisatis/one-pace-metadata/refs/heads/v2/metadata/arcs.yml](https://raw.githubusercontent.com/ladyisatis/one-pace-metadata/refs/heads/v2/metadata/arcs.yml)

* **Episode Descriptions** - Episode descriptions and alternate titles.
  * **descriptions.json**: [https://raw.githubusercontent.com/ladyisatis/one-pace-metadata/refs/heads/v2/metadata/descriptions.json](https://raw.githubusercontent.com/ladyisatis/one-pace-metadata/refs/heads/v2/metadata/descriptions.json)
  * **descriptions.min.json**: [https://raw.githubusercontent.com/ladyisatis/one-pace-metadata/refs/heads/v2/metadata/descriptions.min.json](https://raw.githubusercontent.com/ladyisatis/one-pace-metadata/refs/heads/v2/metadata/descriptions.min.json)
  * **descriptions.yml**: [https://raw.githubusercontent.com/ladyisatis/one-pace-metadata/refs/heads/v2/metadata/descriptions.yml](https://raw.githubusercontent.com/ladyisatis/one-pace-metadata/refs/heads/v2/metadata/descriptions.yml)

* **Episode Listings** - Episodes with metadata sorted by CRC32.
  * **episodes.json**: [https://raw.githubusercontent.com/ladyisatis/one-pace-metadata/refs/heads/v2/metadata/episodes.json](https://raw.githubusercontent.com/ladyisatis/one-pace-metadata/refs/heads/v2/metadata/episodes.json)
  * **episodes.min.json**: [https://raw.githubusercontent.com/ladyisatis/one-pace-metadata/refs/heads/v2/metadata/episodes.min.json](https://raw.githubusercontent.com/ladyisatis/one-pace-metadata/refs/heads/v2/metadata/episodes.json)
  * **episodes.yml**: [https://raw.githubusercontent.com/ladyisatis/one-pace-metadata/refs/heads/v2/metadata/episodes.yml](https://raw.githubusercontent.com/ladyisatis/one-pace-metadata/refs/heads/v2/metadata/episodes.yml)

* **Show Information** - Plex/Jellyfin-specific show settings.
  * **tvshow.json**: [https://raw.githubusercontent.com/ladyisatis/one-pace-metadata/refs/heads/v2/metadata/tvshow.json](https://raw.githubusercontent.com/ladyisatis/one-pace-metadata/refs/heads/v2/metadata/tvshow.json)
  * **tvshow.min.json**: [https://raw.githubusercontent.com/ladyisatis/one-pace-metadata/refs/heads/v2/metadata/tvshow.min.json](https://raw.githubusercontent.com/ladyisatis/one-pace-metadata/refs/heads/v2/metadata/tvshow.min.json)
  * **tvshow.yml**: [https://raw.githubusercontent.com/ladyisatis/one-pace-metadata/refs/heads/v2/metadata/tvshow.yml](https://raw.githubusercontent.com/ladyisatis/one-pace-metadata/refs/heads/v2/metadata/tvshow.yml)

## Sources

- [One Pace Episode Guide](https://docs.google.com/spreadsheets/d/1HQRMJgu_zArp-sLnvFMDzOyjdsht87eFLECxMK858lA/) for CRC32, Manga Chapters, Anime Episodes
- [One Pace Subtitles' title.properties](https://raw.githubusercontent.com/one-pace/one-pace-public-subtitles/refs/heads/main/main/title.properties) for `originaltitle` properties, matching the title in the video files.
- [One Pace Chapters' chapter.properties](https://raw.githubusercontent.com/one-pace/one-pace-public-subtitles/refs/heads/main/main/chapter.properties) for matching manga `chapters` properties to new episodes.
- [One Pace Episode Descriptions](https://docs.google.com/spreadsheets/d/1M0Aa2p5x7NioaH9-u8FyHq6rH3t5s6Sccs8GoC6pHAM/) for English descriptions for arcs and episodes
  - Maintained by Craigy from the One Pace team - please tag @verywittyname in the [One Pace Discord](https://discord.gg/onepace) if there are missing descriptions for episodes.

## Languages

Translations for metadata are welcome. If you would like to add any languages:

1. Create a spreadsheet similar to the [One Pace Episode Descriptions](https://docs.google.com/spreadsheets/d/1M0Aa2p5x7NioaH9-u8FyHq6rH3t5s6Sccs8GoC6pHAM/) English sheet. Make sure the "en" is replaced with the corresponding [ISO-639 language code](https://en.wikipedia.org/wiki/List_of_ISO_639_language_codes#Table) from Set 1, since the code for "en" is English.
2. Set it as a public spreadsheet via File > Share > Anyone with the link.
2. [Fork the repository](https://github.com/ladyisatis/one-pace-metadata/fork) to be able to prepare changes.
3. Edit the `config.yml` file, and add the spreadsheet underneath the `description_sources` key. You can do this from GitHub's website via viewing the file and then hitting the Edit button, or you can clone the repository with Git and edit it that way.
4. Create a [Pull Request](https://github.com/ladyisatis/one-pace-metadata/pulls) with the repository you edited.

Upon the pull request being approved and merged, a new folder should appear in [arcs](https://github.com/ladyisatis/one-pace-metadata/tree/v2/arcs) when the program runs next.
