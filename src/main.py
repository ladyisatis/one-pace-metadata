import asyncio
import httpx
import httpx_retries
import io
import mimetypes
import os
import javaproperties
import json
import re
import sqlite3
import string
import sys
import time

from bs4 import BeautifulSoup
from collections import OrderedDict
from csv import DictReader as CSVReader
from datetime import date, datetime, timezone, timedelta
from functools import reduce
from loguru import logger
from pathlib import Path
from rss_parser import RSSParser
from urllib.parse import urlparse, parse_qs, unquote
from yaml import safe_dump as YamlDump, safe_load as YamlLoad

class OnePaceMetadata:
    def __init__(self):
        try:
            self.config = self.read_yaml(Path("../config.yml"))
        except:
            logger.exception("Error loading config.yml")
            sys.exit(1)

        self.GCLOUD_API_KEY = os.environ['GCLOUD_API_KEY'] if 'GCLOUD_API_KEY' in os.environ else ''
        self.ONE_PACE_RSS_FEED = os.environ['ONE_PACE_RSS_FEED'] if 'ONE_PACE_RSS_FEED' in os.environ else ''
        self.GITHUB_ACTIONS = 'GITHUB_ACTIONS' in os.environ

        self.client = None

        self.arcs = {}
        self.arc_to_num = {}
        self.arc_dir = Path(self.config["paths"]["arcs"])

        self.episodes = {}
        self.episodes_dir = Path(self.config["paths"]["episodes"])
        self.mkv_titles = {}
        self.mkvcode = []
        self.chapter_list = {}

        self.http_cache = OrderedDict()
        self.existing_sc = set()
        self.metadata_dir = Path(self.config["paths"]["metadata"])
        self.other_edits_dir = Path(self.config["paths"]["other_edits"])

    def read_yaml(self, file_path):
        data = {}
        with file_path.open(mode="r", encoding="utf-8") as f:
            data = YamlLoad(stream=f)

        return data

    def write_yaml(self, file_path, data):
        with file_path.open(mode="w", encoding="utf-8") as f:
            YamlDump(data, stream=f, allow_unicode=True, sort_keys=False)

    def serialize_json(self, obj):
        if isinstance(obj, date):
            return obj.isoformat()
        if isinstance(obj, datetime):
            return obj.isoformat(timespec='seconds') #.replace('T', ' ')
        raise TypeError ("Type %s not serializable" % type(obj))

    def escape_char(self, c):
        if c == "’":
            return "'"
        elif c == "…":
            return "..."
        elif c == "“" or c == "”":
            return '"'

        return c

    def unicode_fix(self, s):
        return ''.join(self.escape_char(c) for c in s)

    def set_cache(self, k, v):
        if k in self.http_cache:
            del self.http_cache[k]
        elif len(self.http_cache) >= 5:
            self.http_cache.popitem(last=False)

        self.http_cache[k] = v

    def generate_arc_tmpl(self, **kwargs):
        config = {
            "part": int(kwargs.get("part", 0)),
            "saga": kwargs.get("saga", ""),
            "title": kwargs.get("title", ""),
            "originaltitle": kwargs.get("originaltitle", ""),
            "shortcode": kwargs.get("shortcode", ""),
            "mkvcode": kwargs.get("mkvcode", ""),
            "description": kwargs.get("description", ""),
            "episodes": kwargs.get("episodes", []),
            "info": {
                "status": "",
                "manga_chapters": "",
                "num_of_chapters": 0,
                "anime_episodes": "",
                "episodes_adapted": 0,
                "filler_episodes": "",
                "num_of_pace_eps": 0,
                "piece_minutes": 0,
                "pace_minutes": 0,
                "audio_languages": "",
                "sub_languages": "",
                "pixeldrain_only": "",
                "resolution": "",
                "arc_watch_guide": ""
            }
        }

        if config["title"] != "":
            arc = kwargs.get("title", "")

            if "part" not in kwargs:
                config["part"] = self.arc_to_num[arc] if arc in self.arc_to_num else 0

            if config["shortcode"] == "":
                config["shortcode"] = self.generate_shortcode(arc)

            if config["mkvcode"] == "" and arc in self.mkvcode:
                config["mkvcode"] = self.mkvcode[arc]

        return config

    def generate_shortcode(self, name):
        cleaned = ("".join(ch for ch in name if ch.isalpha())).upper()
        if cleaned == "":
            return ""

        first = cleaned[0]
        char_list = reduce(lambda l1, l2: l1+l2, (cleaned[1:], string.ascii_uppercase, string.ascii_lowercase))

        for second in char_list:
            shortcode = first + second
            if shortcode not in self.existing_sc:
                self.existing_sc.add(shortcode)
                return shortcode

        return ""

    def load_arcs(self):
        if len(self.arc_to_num) > 0 or not self.arc_dir.is_dir():
            return

        for arc_yml in self.arc_dir.rglob("config.yml"):
            config_yml = self.read_yaml(arc_yml)

            if not "title" in config_yml:
                continue

            self.arc_to_num[config_yml["title"]] = int(config_yml["part"])
            if config_yml.get("originaltitle", "") != "":
                self.arc_to_num[config_yml["originaltitle"]] = int(config_yml["part"])

    def scrape_gsheet(self, resp_text):
        data = []
        poster = ""

        soup = BeautifulSoup(resp_text, "html.parser")

        img = soup.find("img")
        if img and img.get("src"):
            poster = img["src"]

        table = soup.find("table", class_="waffle")
        if table:
            rows = []

            for tr in table.find("tbody").find_all("tr"):
                th = tr.find("div", class_="row-header-wrapper")
                if not th:
                    continue

                if th.get_text(strip=True) == "1":
                    for td in tr.find_all("td"):
                        if td.has_attr("class") and td['class'][0].startswith("s"):
                            rows.append(td.get_text(strip=True))
                    continue

                inserted_data = {}
                row_index = 0
                has_contents = False
                for td in tr.find_all("td"):
                    if td.has_attr("class") and td['class'][0].startswith("s"):
                        text = self.unicode_fix(td.get_text(strip=True))
                        links = td.find_all("a")

                        if len(links) > 0:
                            href = str(links[0].get("href"))
                            if href.startswith("https://www.google.com/"):
                                href = unquote(parse_qs(urlparse(href).query)['q'][0])

                                inserted_data[rows[row_index]] = [text, href]
                        else:
                            inserted_data[rows[row_index]] = text

                        row_index += 1

                        if not has_contents and text != "":
                            has_contents = True

                if has_contents:
                    data.append(inserted_data)

        return (data, poster)

    def get_titles_chapters(self):
        try:
            title_props_resp = self.client.get("https://raw.githubusercontent.com/one-pace/one-pace-public-subtitles/refs/heads/main/main/title.properties", follow_redirects=True)
            title_props = javaproperties.loads(title_props_resp.text)
        except:
            logger.exception("Unable to retrieve or parse title.properties")
            return False

        try:
            chapter_props_resp = self.client.get("https://raw.githubusercontent.com/one-pace/one-pace-public-subtitles/refs/heads/main/main/chapter.properties", follow_redirects=True)
            chapter_props = javaproperties.loads(chapter_props_resp.text)
        except:
            logger.exception("Unable to retrieve or parse chapter.properties")
            return False

        if title_props is None or chapter_props is None:
            logger.error("Unable to parse titles and/or chapters")
            return False

        pattern = re.compile(r"^(?P<arc>[a-z]+)(?:_[0-9]+)?_(?P<num>\d+)\.eptitle$")
        arc_name_to_id = {}

        for k, v in title_props.items():
            match = pattern.match(k)
            if not match:
                continue

            arc_name = match.group("arc")
            ep_num = f"{int(match.group('num'))}"

            if arc_name not in arc_name_to_id:
                if arc_name == "loguetown":
                    arc_name_to_id["buggy"] = {}
                    self.chapter_list["buggy"] = {}
                    self.mkvcode.append("buggy")
                elif arc_name == "littlegarden":
                    arc_name_to_id["trials_koby"] = {}
                    self.chapter_list["trials_koby"] = {}
                    self.mkvcode.append("trials_koby")
                elif arc_name == "marineford":
                    arc_name_to_id["av_strawhats"] = {}
                    self.chapter_list["av_strawhats"] = {}
                    self.mkvcode.append("av_strawhats")

                arc_id = f"{len(arc_name_to_id)}"
                arc_name_to_id[arc_name] = arc_id
                self.mkv_titles[arc_id] = {}
                self.chapter_list[arc_id] = {}
                self.mkvcode.append(arc_name)

                logger.info(f"-- ID {arc_id}: {arc_name}")

            arc_id = arc_name_to_id[arc_name]
            self.mkv_titles[arc_id][ep_num] = v

            chapter_key = k.replace(".eptitle", ".chapter")
            if chapter_key in chapter_props:
                self.chapter_list[arc_id][ep_num] = chapter_props[chapter_key]
                logger.info(f"---- {arc_name} {ep_num} ({chapter_props[chapter_key]}): {v}")
            else:
                logger.info(f"---- {arc_name} {ep_num}: {v}")

        return True

    def update_desc_sources(self):
        urls = []

        if len(self.mkv_titles) == 0 or len(self.mkvcode) == 0:
            self.get_titles_chapters()

        if self.GCLOUD_API_KEY == "":
            logger.critical("GCLOUD_API_KEY not set")
            return False

        for source in self.config["description_sources"]:
            source = source.strip()
            match = re.search(r"/d/([a-zA-Z0-9-_]+)", source)
            if match:
                logger.info(f"Adding source: {match.group(1)}")
                urls.append(match.group(1))
            else:
                logger.warning(f"Discarding: {source} (invalid URL)")

        for doc_id in urls:
            sheets_resp = self.client.get(f"https://sheets.googleapis.com/v4/spreadsheets/{doc_id}?key={self.GCLOUD_API_KEY}", follow_redirects=True)
            if sheets_resp.status_code < 200 or sheets_resp.status_code >= 400:
                logger.error(f"Skipping: {doc_id}: Status code {sheets_resp.status_code} returned")
                continue

            sheets = sheets_resp.json()
            locale = sheets["properties"]["locale"]

            for sheet in sheets["sheets"]:
                sheet_id = sheet["properties"]["sheetId"]
                sheet_title = sheet["properties"]["title"]

                if "Episodes" in sheet_title:
                    self.parse_desc_episodes(doc_id, sheet_id, locale)
                elif "Arcs" in sheet_title:
                    self.parse_desc_arcs(doc_id, sheet_id, locale)

        return True

    def parse_desc_arcs(self, doc_id, sheet_id, locale):
        self.existing_sc = set()

        with self.client.stream("GET", f"https://docs.google.com/spreadsheets/d/{doc_id}/export?gid={sheet_id}&format=csv", follow_redirects=True) as resp:
            reader = CSVReader(resp.iter_lines())

            title_key = "title"
            desc_key = "description"
            poster_key = "poster"
            lang = ""

            for key in reader.fieldnames:
                if "title" in key:
                    title_key = key
                elif "description" in key:
                    desc_key = key
                elif "poster" in key:
                    poster_key = key

            if "_" in title_key:
                lang = title_key.split("_")[1].replace("-", "_").strip()
            else:
                lang = locale.replace("-", "_")

            arc_lang_path = Path(self.arc_dir, lang)
            if not arc_lang_path.is_dir():
                arc_lang_path.mkdir(exist_ok=True, parents=True)
                logger.info(f"Created directory: {arc_lang_path}")

            for row in reader:
                if title_key not in row or "part" not in row or row[title_key] == "" or row["part"] == "":
                    continue

                part = row["part"].strip()
                title = self.unicode_fix(row[title_key].strip())

                if lang == "en":
                    if part == "11" and title.startswith("Whisk"):
                        part = "10"
                    elif part == "10" and title.startswith("The Trials"):
                        part = "11"
                    elif part == "99":
                        part = "0"
                    elif int(part) > 90:
                        continue

                part_i = int(part)
                saga = self.unicode_fix(row["saga_title"].strip()) if "saga_title" in row else ""
                desc = self.unicode_fix(row[desc_key].strip())
                mkvc = self.mkvcode[part_i] if len(self.mkvcode) > part_i else ""
                shortc = self.generate_shortcode(title)

                poster_url = row.get(poster_key, "").strip()
                if poster_url != "":
                    poster_file = Path(arc_lang_path, part, "poster.png")
                    if not poster_file.is_file():
                        with self.client.stream("GET", poster_url, follow_redirects=True) as poster_resp:
                            cont_len = 0
                            if "Content-Length" in poster_resp.headers:
                                cont_len = int(poster_resp.headers["Content-Length"])
                            elif "content-length" in poster_resp.headers:
                                cont_len = int(poster_resp.headers["content-length"])

                            cont_type = ""
                            if "Content-Type" in poster_resp.headers:
                                cont_type = poster_resp.headers["Content-Type"]
                            elif "content-type" in poster_resp.headers:
                                cont_type = poster_resp.headers["content-type"]

                            if cont_len > 1024 and cont_type == "image/png":
                                with poster_file.open(mode='wb') as f:
                                    for chunk in poster_resp.iter_bytes():
                                        f.write(chunk)
                            else:
                                logger.error(f"Skipping downloading poster from {poster_url}: invalid image or mime type invalid? [{cont_type}]")

                config_yml = Path(arc_lang_path, part, "config.yml")
                if not config_yml.is_file():
                    if not config_yml.parent.is_dir():
                        config_yml.parent.mkdir(exist_ok=True)
                        logger.info(f"Created directory: {config_yml.parent}")

                    config_yml.write_text(
                        YamlDump(
                            self.generate_arc_tmpl(
                                part=part_i,
                                saga=saga,
                                title=title,
                                shortcode=shortc,
                                mkvcode=mkvc,
                                description=desc
                            ),
                            allow_unicode=True, 
                            sort_keys=False
                        ).replace("\ninfo:\n", "\n\ninfo:\n").replace("\nepisodes:\n", "\n\nepisodes:\n"),
                        encoding="utf-8"
                    )

                    logger.info(f"[{part} - {title}] Wrote to: {config_yml}")

                else:
                    data = self.read_yaml(config_yml)
                    changed = False

                    if data.get("part", None) != part_i:
                        changed = True
                        logger.info(f"[{part} - {title}] Part: {data.get('part', None)} -> {part_i}")
                        data["part"] = part_i

                    if data.get("saga", "") != saga:
                        changed = True
                        logger.info(f"[{part} - {title}] Saga: {data.get('saga', '')} -> {saga}")
                        data["saga"] = saga

                    if data.get("title", "") == "":
                        changed = True
                        logger.info(f"[{part} - {title}] Title: {data.get('title', '')} -> {title}")
                        data["title"] = title

                    if data.get("description", "") != desc:
                        changed = True
                        logger.info(f"[{part} - {title}] Description: {data.get('description', '')} -> {desc}")
                        data["description"] = desc

                    if data.get("shortcode", "") != shortc:
                        changed = True
                        logger.info(f"[{part} - {title}] Shortcode: {data.get('shortcode', '')} -> {shortc}")
                        data["shortcode"] = shortc

                    if data.get("mkvcode", "") != mkvc:
                        changed = True
                        logger.info(f"[{part} - {title}] MKV Code: {data.get('mkvcode', '')} -> {mkvc}")
                        data["mkvcode"] = mkvc

                    if changed:
                        config_yml.write_text(
                            YamlDump(data, allow_unicode=True, sort_keys=False).replace("\ninfo:\n", "\n\ninfo:\n").replace("\nepisodes:\n", "\n\nepisodes:\n"),
                            encoding="utf-8"
                        )
                        logger.info(f"-- Wrote to: {config_yml}")

                self.arc_to_num[title] = int(part)

    def parse_desc_episodes(self, doc_id, sheet_id, locale):
        logger.info("Updating Episode Descriptions")

        with self.client.stream("GET", f"https://docs.google.com/spreadsheets/d/{doc_id}/export?gid={sheet_id}&format=csv", follow_redirects=True) as resp:
            reader = CSVReader(resp.iter_lines())

            title_key = "title"
            desc_key = "description"
            lang = ""

            for key in reader.fieldnames:
                if "title" in key:
                    title_key = key
                elif "description" in key:
                    desc_key = key

            if "_" in title_key:
                lang = title_key.split("_")[1].replace("-", "_").strip()
            else:
                lang = locale.replace("-", "_")

            for row in reader:
                if "arc_title" not in row or "arc_part" not in row or title_key not in row or desc_key not in row:
                    logger.info(f"Not in row: {row}")
                    continue

                arc = row["arc_title"].strip()
                episode = row["arc_part"].strip()
                title = row[title_key].strip()
                description = row[desc_key].strip()

                if arc == "" or episode == "" or title == "":
                    continue

                if arc in self.arc_to_num:
                    arc_num = self.arc_to_num[arc]
                    ep_path = Path(self.arc_dir, lang, str(arc_num), f"episode_{int(episode):02d}.yml")

                    logger.info(f"{arc} {episode}: {ep_path}")

                    try:
                        if not ep_path.parent.is_dir():
                            ep_path.parent.mkdir(exist_ok=True, parents=True)
                            logger.info(f"-- Directory created: {ep_path.parent}")

                        if ep_path.is_file():
                            ep_data = self.read_yaml(ep_path)
                            changed = False

                            if ep_data.get("title", "") != title:
                                logger.info(f"-- Title: {ep_data.get('title', '')} -> {title}")
                                ep_data["title"] = title
                                changed = True

                            if arc_num in self.mkv_titles and episode in self.mkv_titles[arc_num]:
                                originaltitle = self.mkv_titles[arc_num][episode]
                                if title.lower() != originaltitle.lower() and ep_data.get("originaltitle", "") != originaltitle:
                                    logger.info(f"-- Original Title: {ep_data.get('originaltitle', None)} -> {originaltitle}")
                                    ep_data["originaltitle"] = originaltitle
                                    changed = True

                            if ep_data.get("description", "") != description:
                                logger.info(f"-- Description: {ep_data.get('description', '')} -> {description}")
                                ep_data["description"] = description
                                changed = True

                            if changed:
                                self.write_yaml(ep_path, ep_data)
                                logger.info("-- Changes written to file")

                        else:
                            with ep_path.open(mode="w", encoding="utf-8") as f:
                                originaltitle = ""
                                if arc_num in self.mkv_titles and episode in self.mkv_titles[arc_num]:
                                    originaltitle = self.mkv_titles[arc_num][episode]
                                    if title.lower() == originaltitle.lower():
                                        originaltitle = ""

                                YamlDump({
                                    "title": title,
                                    "originaltitle": originaltitle,
                                    "description": description
                                }, stream=f, allow_unicode=True, sort_keys=False)
                                logger.info(f"-- Wrote '{title}' to file")

                    except:
                        logger.exception("-- Unable to make changes")

    def update_from_episode_guide(self):
        if self.GCLOUD_API_KEY == "":
            logger.critical("GCLOUD_API_KEY not set")
            return

        try:
            if "episode_guide" not in self.config:
                logger.error("Skipping: episode_guide not in config.yml")
                return

            guide_id = ""
            match = re.search(r"/d/([a-zA-Z0-9-_]+)", self.config["episode_guide"])
            if match:
                guide_id = match.group(1)
            else:
                logger.error("Skipping: episode_guide does not have a valid Google Sheets URL")
                return

            ep_guide_resp = self.client.get(f"https://sheets.googleapis.com/v4/spreadsheets/{guide_id}?key={self.GCLOUD_API_KEY}", follow_redirects=True)
            ep_guide_resp.raise_for_status()

            for sheet in ep_guide_resp.json()["sheets"]:
                properties = sheet["properties"]

                sheet_id = properties["sheetId"]
                sheet_title = properties["title"]
                sheet_index = properties["index"]

                if sheet_index == 0: #Arc Overview
                    self.parse_arc_overview(guide_id, sheet_id)

                else:
                    if not self.episodes_dir.is_dir():
                        self.episodes_dir.mkdir(exist_ok=True)
                        logger.info(f"Created directory: {self.episodes_dir}")

                    config_yml = Path(f"{self.arc_dir}/en/{sheet_index}/config.yml")
                    if config_yml.is_file():
                        data = self.read_yaml(config_yml)

                        if "title" in data and sheet_title.lower() != data["title"].lower():
                            data["originaltitle"] = f"{data['title']}"
                            data["title"] = sheet_title
                            self.arc_to_num[sheet_title] = int(sheet_index)
                            config_yml.write_text(
                                YamlDump(data, allow_unicode=True, sort_keys=False).replace("\ninfo:\n", "\n\ninfo:\n").replace("\nepisodes:\n", "\n\nepisodes:\n"),
                                encoding="utf-8"
                            )

                        self.parse_spreadsheet_page(guide_id, sheet_id, sheet_title, sheet_index)

        except:
            logger.exception("Unable to update from Episode Guide")

    def safe_int(self, i):
        try:
            return 0 if i == "" else int(i)
        except ValueError:
            return 0

    def parse_arc_overview(self, guide_id, sheet_id):
        with self.client.stream("GET", f"https://docs.google.com/spreadsheets/d/{guide_id}/export?gid={sheet_id}&format=csv", follow_redirects=True) as resp:
            reader = CSVReader(resp.iter_lines())

            arc_num = 0
            for row in reader:
                if row.get("Arcs", "") == "Totals":
                    break
                elif row.get("No.", "") == "":
                    continue

                arc_num += 1

                for arc_folder in self.arc_dir.iterdir():
                    config_yml = Path(arc_folder, str(arc_num), "config.yml")
                    if not config_yml.is_file():
                        continue

                    arc_name = row.get("Arcs", "")
                    manga_chapters = row.get("Manga Chapters", "")
                    num_of_chapters = self.safe_int(row.get("# of Ch.", "0"))
                    anime_episodes = row.get("Anime Episodes", "")
                    episodes_adapted = self.safe_int(row.get("Episodes Adapted", "0"))
                    filler_episodes = row.get("Filler Episodes", "")
                    num_of_pace_eps = self.safe_int(row.get("# of Pace Ep.", "0"))
                    piece_minutes = self.safe_int(row.get("Piece Minutes", "0"))
                    pace_minutes = self.safe_int(row.get("Pace Minutes", "0"))
                    audio_languages = row.get("Audio Languages", "")
                    sub_languages = row.get("Sub Languages", "")
                    pixeldrain_only = row.get("Pixeldrain only", "")
                    resolution = row.get("Resolution", "")
                    arc_watch_guide = row.get("Arc Watch Guide: Pace + Original", "")

                    status = ""
                    if "(TBR)" in arc_name:
                        status = "To Be Redone"
                    elif "(WIP)" in arc_name:
                        status = "Work In Progress"

                    data = self.read_yaml(config_yml)
                    data["info"] = {
                        "status": status,
                        "manga_chapters": manga_chapters,
                        "num_of_chapters": num_of_chapters,
                        "anime_episodes": anime_episodes,
                        "episodes_adapted": episodes_adapted,
                        "filler_episodes": filler_episodes,
                        "num_of_pace_eps": num_of_pace_eps,
                        "piece_minutes": piece_minutes,
                        "pace_minutes": pace_minutes,
                        "audio_languages": audio_languages,
                        "sub_languages": sub_languages,
                        "pixeldrain_only": pixeldrain_only,
                        "resolution": resolution,
                        "arc_watch_guide": arc_watch_guide
                    }

                    config_yml.write_text(
                        YamlDump(data, allow_unicode=True, sort_keys=False).replace("\ninfo:\n", "\n\ninfo:\n").replace("\nepisodes:\n", "\n\nepisodes:\n"),
                        encoding="utf-8"
                    )

                    logger.info(f"[{arc_name}] Wrote to: {config_yml}")

    def parse_spreadsheet_page(self, guide_id, sheet_id, sheet_title, sheet_index):
        logger.info(f"[{sheet_title}] Retrieving HTML sheet")

        resp = self.client.get(f"https://docs.google.com/spreadsheets/u/0/d/{guide_id}/htmlview/sheet?headers=false&gid={sheet_id}", follow_redirects=True)
        if resp.status_code < 200 or resp.status_code >= 400:
            logger.error(f"Skipping: Sheet {sheet_id} ({sheet_title})")
            return

        if not self.episodes_dir.is_dir():
            self.episodes_dir.mkdir(exist_ok=True)

        sheet_data, poster = self.scrape_gsheet(resp.text)
        for row in sheet_data:
            if "MKV CRC32" not in row:
                continue

            op_id = row.get("One Pace Episode", "")
            chapters = row.get("Chapters", "")
            episodes = row.get("Episodes", "")
            release_date = row.get("Release Date", "")
            length = row.get("Length", "")
            mkv_crc32 = row.get("MKV CRC32", [])
            mkv_crc32_extended = row.get("MKV CRC32 (Extended)", [])
            length_extended = row.get("Length (Extended)", "")

            if op_id == "" or chapters == "" or episodes == "" or len(mkv_crc32) == 0:
                continue

            match = re.search(r'(\d+)', op_id)
            if match:
                ep = int(match.group(1))
            else:
                ep = 1

            match = re.search(r'\b\d+(?:-\d+)?(?:,\s*\d+(?:-\d+)?)*\b', chapters)
            if match:
                chapters = match.group(0).replace(" ", "").replace(",", ", ")
            
            match = re.search(r'\b\d+(?:-\d+)?(?:,\s*\d+(?:-\d+)?)*\b', episodes)
            if match:
                episodes = match.group(0).replace(" ", "").replace(",", ", ")

            release_date_group = release_date.split(".")
            if len(release_date_group) == 3:
                release_date = date(int(release_date_group[0]), int(release_date_group[1]), int(release_date_group[2]))
            else:
                release_date_group = release_date.split("-")
                if len(release_date_group) == 3:
                    release_date = date(int(release_date_group[0]), int(release_date_group[1]), int(release_date_group[2]))
                else:
                    continue

            if ":" in length:
                length_group = length.split(":")
                if len(length_group) == 2:
                    length = timedelta(minutes=int(length_group[0]), seconds=int(length_group[1])).total_seconds()
                elif len(length_group) == 3:
                    length = timedelta(hours=int(length_group[0]), minutes=int(length_group[1]), seconds=int(length_group[2])).total_seconds()

            if ":" in length_extended:
                length_group = length_extended.split(":")
                if len(length_group) == 2:
                    length_extended = timedelta(minutes=int(length_group[0]), seconds=int(length_group[1])).total_seconds()
                elif len(length_group) == 3:
                    length_extended = timedelta(hours=int(length_group[0]), minutes=int(length_group[1]), seconds=int(length_group[2])).total_seconds()

            for arc_folder in self.arc_dir.iterdir():
                config_yml = Path(arc_folder, str(sheet_index), "config.yml")

                if config_yml.is_file():
                    changed = False
                    config_data = self.read_yaml(config_yml)
                    ep_str = f"{ep:02d}"

                    if "episodes" not in config_data or isinstance(config_data["episodes"], dict):
                        config_data["episodes"] = []
                        changed = True

                    i = None
                    for ind, obj in enumerate(config_data["episodes"]):
                        if obj["episode"] == ep_str:
                            i = ind
                            break

                    if i is None:
                        config_data["episodes"].append({
                            "episode": ep_str,
                            "standard": mkv_crc32[0],
                            "extended": mkv_crc32_extended[0] if len(mkv_crc32_extended) > 0 else ""
                        })
                        changed = True
                    else:
                        if config_data["episodes"][i]["standard"] != mkv_crc32[0]:
                            config_data["episodes"][i]["standard"] = mkv_crc32[0]
                            changed = True

                        if len(mkv_crc32_extended) > 0 and config_data["episodes"][i]["extended"] != mkv_crc32_extended[0]:
                            config_data["episodes"][i]["extended"] = mkv_crc32_extended[0]
                            changed = True

                    if changed:
                        config_data["episodes"].sort(key=lambda x: int(x["episode"]))
                        config_yml.write_text(
                            YamlDump(config_data, allow_unicode=True, sort_keys=False).replace("\ninfo:\n", "\n\ninfo:\n").replace("\nepisodes:\n", "\n\nepisodes:\n"),
                            encoding="utf-8"
                        )

            crc_file = Path(self.episodes_dir, f"{mkv_crc32[0]}.yml")
            if not crc_file.is_file():
                self.create_crc_file(sheet_index, ep, crc_file, mkv_crc32, chapters, episodes, release_date, length, False)

            if len(mkv_crc32_extended) > 0:
                crc_file = Path(self.episodes_dir, f"{mkv_crc32_extended[0]}.yml")
                if not crc_file.is_file():
                    self.create_crc_file(sheet_index, ep, crc_file, mkv_crc32_extended, chapters, episodes, release_date, length, True)

        if poster != "":
            poster_file = Path(f"{self.arc_dir}/en/{sheet_index}/poster.png")
            if not poster_file.is_file():
                with self.client.stream("GET", poster, follow_redirects=True) as poster_resp:
                    cont_len = 0
                    if "Content-Length" in poster_resp.headers:
                        cont_len = int(poster_resp.headers["Content-Length"])
                    elif "content-length" in poster_resp.headers:
                        cont_len = int(poster_resp.headers["content-length"])

                    if cont_len > 1024:
                        with poster_file.open(mode='wb') as f:
                            for chunk in poster_resp.iter_bytes():
                                f.write(chunk)

    def create_crc_file(self, sheet_index, ep, crc_file, mkv_crc32, chapters, episodes, release_date, length, extended):
        file_info = self.fetch_file_info(mkv_crc32[1], search=f"[{mkv_crc32[0]}]")
        file_dump = YamlDump({"file": file_info[0]}, allow_unicode=True, sort_keys=False) if len(file_info) > 0 else "\n"

        out = (
            f"arc: {sheet_index}\n"
            f"episode: {ep}\n"
            "\n"
            f"manga_chapters: {chapters}\n"
            f"anime_episodes: {episodes}\n"
            f"released: {release_date.isoformat() if isinstance(release_date, (date, datetime)) else release_date}\n"
            f"duration: {length}\n"
            f"extended: {'true' if extended else 'false'}\n"
            "\n"
            "hashes:\n"
            f"  crc32: {mkv_crc32[0]}\n"
            f"  blake2s: ''\n"
            "\n"
            f"{file_dump}"
        )

        crc_file.write_text(out, encoding="utf-8")

    def fetch_file_info(self, url, search=""):
        is_url = False

        if url in self.http_cache:
            logger.info(f"Retrieving cached item ({url})")
            soup = BeautifulSoup(self.http_cache.get(url), "html.parser")
        elif url.startswith("http"):
            logger.info(f"Sending request to: {url}")
            resp = httpx.get(url)

            if 'location' in resp.headers:
                old_url = f"{url}"
                url = resp.headers['location']
                logger.info(f"Redirected to: {url}")
                resp = httpx.get(url)
                self.set_cache(old_url, resp.text)

            self.set_cache(url, resp.text)
            soup = BeautifulSoup(resp.text, "html.parser")
            is_url = True
        else:
            soup = BeautifulSoup(url, "html.parser")

        if is_url and "/view/" in url:
            file_id = int(url.split("/view/")[1])
        else:
            clearfix = soup.find("div", class_="clearfix")
            if clearfix:
                href = clearfix.find("a", href=True)
                if href:
                    match = re.search(r"/download/(\d+)", href["href"])
                    if match:
                        file_id = int(match.group(1))

        timestamp_div = soup.find("div", attrs={"data-timestamp": True})
        timestamp = int(timestamp_div["data-timestamp"]) if timestamp_div else 0

        file_size = ""
        file_hash = ""

        for row in soup.find("div", class_="panel-body").select(".row"):
            label = row.find("div", class_="col-md-offset-6")
            if label:
                label = label.get_text(strip=True)
                if label == "Info hash:":
                    kbd = row.find("kbd")
                    file_hash = kbd.get_text(strip=True) if kbd else ""
                    continue

        files = []
        c = 0

        for fi in soup.select("li i.fa-file"):
            li = fi.find_parent("li")
            if not li:
                continue

            file_size_el = li.find("span", class_="file-size")
            if file_size_el:
                file_size = file_size_el.get_text(strip=True).replace("(", "").replace(")", "")

            file_info = {
                "id": file_id,
                "name": (" ".join([t for t in li.stripped_strings])).replace(f" ({file_size})", ""),
                "size": file_size,
                "hash": file_hash,
                "index": c
            }

            if search != "":
                if search in file_info["name"]:
                    files.append(file_info)
            else:
                files.append(file_info)

            c += 1

        return files

    def update_from_rss_feed(self, rss_feed_url):
        if len(self.arc_to_num) == 0:
            self.load_arcs()

        resp = self.client.get(rss_feed_url, follow_redirects=True)

        title_pattern = re.compile(r'\[One Pace\]\[\d+(?:[-,]\d+)*\]\s+(.+?)\s+(\d{2,})\s*(\w+)?\s*\[\d+p\]\[([A-Fa-f0-9]{8})\]\.mkv', re.IGNORECASE)
        now = datetime.now().astimezone(timezone.utc)
        added_metadata = []

        for i, item in enumerate(RSSParser.parse(resp.text).channel.items):
            if i == 25:
                break

            if not item.title or not item.title.content or item.title.content == "":
                continue

            pub_date = datetime.strptime(item.pub_date.content, "%a, %d %b %Y %H:%M:%S %z")
            if (now - pub_date).total_seconds() > (int(self.config["oldest_rss_release_hours"]) * 3600):
                continue

            logger.info(f"Processing new release from: {item.guid.content}")
            resp = self.client.get(item.guid.content, follow_redirects=True)
            files = self.fetch_file_info(resp.text)
            only_file = len(files) == 1

            for mkv_file in files:
                match = title_pattern.match(mkv_file["name"])
                if not match:
                    logger.warning(f"Skipping: regex does not match [{mkv_file['name']}]")
                    continue

                arc_name, ep_num, extra, crc32 = match.groups()

                crc_file = Path(self.episodes_dir, f"{crc32}.yml")
                if crc_file.is_file():
                    logger.info(f"Skipping {arc_name} {ep_num}: episodes/{crc32}.yml exists")
                    continue

                added_metadata.append(f"{arc_name} {ep_num} {extra} ({crc32})")

                arc_num = self.arc_to_num.get(arc_name, 0)
                standard_crc = crc32 if extra is None else ""
                extended_crc = crc32 if extra is not None else ""

                for arc_folder in self.arc_dir.iterdir():
                    arc_file = Path(arc_folder, str(arc_num), "config.yml")

                    if not arc_file.parent.is_dir():
                        arc_file.parent.mkdir(exist_ok=True)

                    if arc_file.is_file():
                        config_yml = self.read_yaml(arc_file)

                        i = None
                        for ind, ep_item in enumerate(config_yml["episodes"]):
                            if ep_item["episode"] == ep_num:
                                i = ind
                                break

                        if i is None:
                            logger.info(f"Add new episode to arc {arc_num}: {arc_name} {ep_num} ['{standard_crc}'/'{extended_crc}']")
                            config_yml["episodes"].append({
                                "episode": ep_num,
                                "standard": standard_crc,
                                "extended_crc": extended_crc
                            })
                        else:
                            crc_key = "standard" if extra is None else "extended"
                            logger.info(f"Update episode #{i}: {crc_key} = {crc32}")
                            config_yml["episodes"][i][crc_key] = crc32

                    else:
                        config_yml = self.generate_arc_tmpl(
                            title=arc_name,
                            episodes=[{
                                "episode": ep_num,
                                "standard": standard_crc,
                                "extended": extended_crc
                            }]
                        )

                    arc_file.write_text(
                        YamlDump(config_yml, allow_unicode=True, sort_keys=False).replace("\ninfo:\n", "\n\ninfo:\n").replace("\nepisodes:\n", "\n\nepisodes:\n"),
                        encoding="utf-8"
                    )

                chapters = ""
                episodes = ""
                if only_file:
                    div = BeautifulSoup(resp.text, "html.parser").find('div', { 'class': 'panel-body', 'id': 'torrent-description' })
                    desc = div.get_text(strip=True).split("\n") if div else []

                    for d in desc:
                        if d.startswith("Chapters: "):
                            chapters = d.replace("Chapters: ", "")
                        elif d.startswith("Episodes: "):
                            episodes = d.replace("Episodes: ", "")

                ep_num_i = int(ep_num)

                if chapters == "" and episodes == "":
                    for yml_file in self.episodes_dir.rglob("*.yml"):
                        data = self.read_yaml(yml_file)

                        if data["arc"] == arc_num and data["episode"] == ep_num_i:
                            logger.info(f"Using chapters/episodes from: {yml_file}")
                            chapters = data["manga_chapters"]
                            episodes = data["anime_episodes"]
                            break

                meta = {
                    "manga_chapters": chapters,
                    "anime_episodes": episodes,
                    "released": pub_date,
                    "duration": 0,
                    "extended": extra is not None
                }

                hashes = {
                    "hashes": {
                        "crc32": crc32,
                        "blake2s": ""
                    }
                }

                file_info = YamlDump({"file": mkv_file}, allow_unicode=True, sort_keys=False)

                out = (
                    f"arc: {arc_num}\n"
                    f"episode: {ep_num_i}\n"
                    "\n"
                    f"{YamlDump(meta, allow_unicode=True, sort_keys=False)}"
                    "\n"
                    f"{YamlDump(hashes, allow_unicode=True, sort_keys=False)}"
                    "\n"
                    f"{file_info}"
                )

                logger.info(f"Writing to: {crc_file}")
                crc_file.unlink(missing_ok=True)
                crc_file.write_text(out, encoding="utf-8")

        if len(added_metadata) > 0:
            print(f"Add metadata: {', '.join(added_metadata)}")
        else:
            print("Update metadata from remote sources")

        return True

    def generate_arcs(self):
        arcs = {}

        for lang_folder in self.arc_dir.iterdir():
            if not lang_folder.is_dir():
                continue

            lang = lang_folder.name
            arcs[lang] = []
            data = {}

            for config_yml in lang_folder.rglob("config.yml"):
                data = self.read_yaml(config_yml)
                data["description"] = data.get("description", "").strip()
                arcs[lang].append(data)

            arcs[lang].sort(key=lambda x: int(x["part"]))
        return arcs

    def generate_descriptions(self):
        desc = {}
        pattern = re.compile(r"episode_(\d+)\.yml$")

        for lang_folder in self.arc_dir.iterdir():
            if not lang_folder.is_dir():
                continue

            lang = lang_folder.name
            desc[lang] = []

            for ep_yml in lang_folder.rglob("episode_*.yml"):
                data = {"arc": int(ep_yml.parent.name)}

                m = pattern.search(ep_yml.name)
                if m:
                    data["episode"] = int(m.group(1))
                else:
                    data["episode"] = ""

                for k, v in self.read_yaml(ep_yml).items():
                    data[k] = v

                desc[lang].append(data)

            desc[lang].sort(key=lambda x: (int(x["arc"]), int(x["episode"])))

        return desc

    def generate_episodes(self):
        episodes = {}
        for yml in self.episodes_dir.glob("*.yml"):
            crc32 = yml.stem

            data = self.read_yaml(yml)
            data["manga_chapters"] = str(data.get("manga_chapters", ""))
            data["anime_episodes"] = str(data.get("anime_episodes", ""))

            if "_" in crc32:
                crc32_spl = crc32.split("_")
                crc32 = crc32_spl[0]

                if crc32 in episodes:
                    if isinstance(episodes[crc32], dict):
                        episodes[crc32] = [episodes[crc32], data]
                    elif isinstance(episodes[crc32], list):
                        episodes[crc32].append(data)
                    else:
                        episodes[crc32] = [data]

            else:
                episodes[crc32] = data

        return {key: episodes[key] for key in sorted(episodes.keys())}

    def generate_tvshow(self):
        return self.config["tvshow"] if "tvshow" in self.config else {}

    def generate_other_edits(self):
        other_edits = {}

        for edit_dir in self.other_edits_dir.iterdir():
            if not edit_dir.is_dir():
                continue

            e_id = edit_dir.name
            other_edits[e_id] = {}

            for yml in edit_dir.rglob("*.yml"):
                try:
                    other_edits[e_id][yml.stem] = self.read_yaml(yml)
                except:
                    logger.exception(f"Skipping: Cannot read {yml}")

        return {key: other_edits[key] for key in sorted(other_edits.keys())}

    def generate_sqlite(self, data_file, arcs, episodes, descriptions, status, tvshow, other_edits, with_posters=False):
        with sqlite3.connect(data_file, timeout=15.0) as conn:
            cursor = conn.cursor()

            schema_tables = Path("./schema.sql").read_text().split(";\n")
            for table in schema_tables:
                cursor.execute(table)
                conn.commit()

            for arc_lang, arc_item in arcs.items():
                for arc in arc_item:
                    if arc.get("part", "") == "":
                        continue

                    poster_blob = None
                    poster_path = Path(self.arc_dir, arc_lang, str(arc["part"]), "poster.png")
                    if with_posters and poster_path.is_file():
                        try:
                            poster_blob = poster_path.read_bytes()
                        except:
                            logger.exception("Skipping fetching poster")

                    cursor.execute(
                        "INSERT INTO arcs (lang, part, saga, title, " + 
                        "originaltitle, shortcode, mkvcode, description, poster) " +
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (arc_lang,
                        arc.get("part", 0),
                        arc.get("saga", ""),
                        arc.get("title", ""),
                        arc.get("originaltitle", ""),
                        arc.get("shortcode", ""),
                        arc.get("mkvcode", ""),
                        arc.get("description", ""),
                        poster_blob)
                    )

                    conn.commit()

                    for ep in arc.get("episodes", []):
                        cursor.execute(
                            "INSERT INTO arc_episodes (arc_part, episode, standard, extended) " +
                            "VALUES (?, ?, ?, ?)",
                            (arc.get("part", 0),
                            ep.get("episode", ""),
                            ep.get("standard", ""),
                            ep.get("extended", ""))
                        )

                    info = arc.get("info", {})

                    cursor.execute(
                        "INSERT INTO arc_info (arc_part, status, manga_chapters, " +
                        "num_of_chapters, anime_episodes, episodes_adapted, filler_episodes," +
                        "num_of_pace_eps, piece_minutes, pace_minutes, audio_languages, " +
                        "sub_languages, pixeldrain_only, resolution, arc_watch_guide) " +
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (arc.get("part", 0),
                        info.get("status", ""),
                        info.get("manga_chapters", ""),
                        info.get("num_of_chapters", 0),
                        info.get("anime_episodes", ""),
                        info.get("episodes_adapted", 0),
                        info.get("filler_episodes", ""),
                        info.get("num_of_pace_eps", 0),
                        info.get("piece_minutes", 0),
                        info.get("pace_minutes", 0),
                        info.get("audio_languages", ""),
                        info.get("sub_languages", ""),
                        info.get("pixeldrain_only", ""),
                        info.get("resolution", ""),
                        info.get("arc_watch_guide", ""))
                    )

                    conn.commit()

            for desc_lang, desc_item in descriptions.items():
                for desc in desc_item:
                    cursor.execute(
                        "INSERT INTO descriptions (lang, arc, episode, title, " +
                        "originaltitle, description) VALUES (?, ?, ?, ?, ?, ?)",
                        (desc_lang,
                        desc.get("arc", 0),
                        desc.get("episode", 0),
                        desc.get("title", ""),
                        desc.get("originaltitle", ""),
                        desc.get("description", ""))
                    )

            conn.commit()

            for crc32, all_eps in episodes.items():
                total_eps = [all_eps] if isinstance(all_eps, dict) else all_eps

                for episode in total_eps:
                    hashes = episode.get("hashes", {})
                    file = episode.get("file", {})

                    cursor.execute("INSERT INTO episodes (arc, episode, manga_chapters, " +
                        "anime_episodes, released, duration, extended, hash_crc32, " +
                        "hash_blake2s, file_id, file_name, file_size, file_hash, " +
                        "file_index) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (episode.get("arc", 0),
                        episode.get("episode", 0),
                        episode.get("manga_chapters", ""),
                        episode.get("anime_episodes", ""),
                        episode.get("released", ""),
                        episode.get("duration", 0),
                        episode.get("extended", False),
                        hashes.get("crc32", ""),
                        hashes.get("blake2s", ""),
                        file.get("id", 0),
                        file.get("name", ""),
                        file.get("size", ""),
                        file.get("hash", ""),
                        file.get("index", 0))
                )

            conn.commit()

            cursor.execute("INSERT INTO status (last_update, last_update_ts, base_url, version) " +
                "VALUES (?, ?, ?, ?)",
                (status["last_update"],
                status["last_update_ts"],
                status["base_url"],
                status["version"])
            )

            query = "INSERT INTO tvshow (lang, key, value) VALUES (?, ?, ?)"
            for show_lang, show_items in tvshow.items():
                for k, v in show_items.items():
                    if isinstance(v, list):
                        for item in v:
                            cursor.execute(query, (show_lang, str(k), str(item)))
                    elif isinstance(v, bool):
                        cursor.execute(query, (show_lang, str(k), "true" if v else "false"))
                    elif isinstance(v, datetime) or isinstance(v, date):
                        cursor.execute(query, (show_lang, str(k), v.isoformat()))
                    else:
                        cursor.execute(query, (show_lang, str(k), str(v)))

            conn.commit()

            for edit_name, b2 in other_edits.items():
                for ep in b2.values():
                    hashes = ep.get("hashes", {})
                    cursor.execute("INSERT INTO other_edits (edit_name, arc, " +
                        "episode, title, description, manga_chapters, " +
                        "anime_episodes, released, duration, extended, " +
                        "hash_crc32, hash_blake2s) VALUES (?, ?, ?, " +
                        "?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            edit_name,
                            ep.get("arc", 0),
                            ep.get("episode", 0),
                            ep.get("title", ""),
                            ep.get("description", ""),
                            ep.get("manga_chapters", ""),
                            ep.get("anime_episodes", ""),
                            ep.get("released", ""),
                            ep.get("duration", 0),
                            ep.get("extended", False),
                            str(hashes.get("crc32", "")).upper(),
                            str(hashes.get("blake2", "")).upper()
                        )
                    )

            conn.commit()

    def generate_data(self):
        arcs = self.generate_arcs()
        episodes = self.generate_episodes()
        descriptions = self.generate_descriptions()
        tvshow = self.generate_tvshow()
        other_edits = self.generate_other_edits()

        logger.info("Generate arcs")
        Path(self.metadata_dir, "arcs.json").write_text(json.dumps(arcs, indent=2, default=self.serialize_json))
        Path(self.metadata_dir, "arcs.min.json").write_text(json.dumps(arcs, default=self.serialize_json))
        self.write_yaml(Path(self.metadata_dir, "arcs.yml"), arcs)

        logger.info("Generate descriptions")
        Path(self.metadata_dir, "descriptions.json").write_text(json.dumps(descriptions, indent=2, default=self.serialize_json))
        Path(self.metadata_dir, "descriptions.min.json").write_text(json.dumps(descriptions, default=self.serialize_json))
        self.write_yaml(Path(self.metadata_dir, "descriptions.yml"), descriptions)

        logger.info("Generate episodes")
        Path(self.metadata_dir, "episodes.json").write_text(json.dumps(episodes, indent=2, default=self.serialize_json))
        Path(self.metadata_dir, "episodes.min.json").write_text(json.dumps(episodes, default=self.serialize_json))
        self.write_yaml(Path(self.metadata_dir, "arcs.yml"), episodes)

        logger.info("Generate other edits")
        Path(self.metadata_dir, "other_edits.json").write_text(json.dumps(other_edits, indent=2, default=self.serialize_json))
        Path(self.metadata_dir, "other_edits.min.json").write_text(json.dumps(other_edits, default=self.serialize_json))
        self.write_yaml(Path(self.metadata_dir, "other_edits.yml"), other_edits)

        logger.info("Generate tvshow")
        Path(self.metadata_dir, "tvshow.json").write_text(json.dumps(tvshow, indent=2, default=self.serialize_json))
        Path(self.metadata_dir, "tvshow.min.json").write_text(json.dumps(tvshow, default=self.serialize_json))
        self.write_yaml(Path(self.metadata_dir, "tvshow.yml"), tvshow)

        now = datetime.now().astimezone(timezone.utc).replace(microsecond=0)

        if self.GITHUB_ACTIONS:
            base_url = f"https://raw.githubusercontent.com/{os.environ['GITHUB_REPOSITORY']}/{os.environ['GITHUB_REF']}"
        else:
            base_url = "https://raw.githubusercontent.com/ladyisatis/one-pace-metadata/refs/heads/v2"

        status = {
            "last_update": now.isoformat(),
            "last_update_ts": round(now.timestamp()),
            "base_url": base_url,
            "version": int(os.environ['METADATA_VERSION']) if 'METADATA_VERSION' in os.environ else 0
        }

        Path(self.metadata_dir, "status.json").write_text(json.dumps(status, indent=2, default=self.serialize_json))
        self.write_yaml(Path(self.metadata_dir, "status.yml"), status)

        data = {
            "status": status,
            "tvshow": tvshow,
            "arcs": arcs,
            "descriptions": descriptions,
            "episodes": episodes,
            "other_edits": other_edits
        }

        logger.info("Generate data.json")
        Path(self.metadata_dir, "data.json").write_text(json.dumps(data, indent=2, default=self.serialize_json))
        Path(self.metadata_dir, "data.min.json").write_text(json.dumps(data, default=self.serialize_json))
        self.write_yaml(Path(self.metadata_dir, "data.yml"), data)

        data_sqlite = Path(self.metadata_dir, "data.sqlite")
        if data_sqlite.is_file():
            data_sqlite.unlink()

        data_posters_sqlite = Path(self.metadata_dir, "data_with_posters.sqlite")
        if data_posters_sqlite.is_file():
            data_posters_sqlite.unlink()

        logger.info("Generate data.sqlite")
        self.generate_sqlite(data_sqlite, arcs, episodes, descriptions, status, tvshow, other_edits, False)

        logger.info("Generate data_with_posters.sqlite")
        self.generate_sqlite(data_posters_sqlite, arcs, episodes, descriptions, status, tvshow, other_edits, True)

        logger.info("Generate data.json compatible with Organizer")
        self.generate_compat_data(arcs, episodes, descriptions, status, tvshow)

    def generate_compat_data(self, arcs, episodes, descriptions, status, tvshow):
        try:
            output = {
                "last_update": status["last_update"],
                "last_update_ts": status["last_update_ts"],
                "base_url": status["base_url"],
                "tvshow": tvshow["en"],
                "arcs": [],
                "episodes": {}
            }

            for arc in arcs["en"]:
                output["arcs"].append({
                    "part": arc.get("part", 0),
                    "saga": arc.get("saga", ""),
                    "title": arc.get("title", ""),
                    "originaltitle": arc.get("originaltitle", ""),
                    "description": arc.get("description", ""),
                    "poster": f"arcs/en/{arc.get('part', 0)}/poster.png"
                })

            desc_dict = {}
            for desc in descriptions["en"]:
                if desc["arc"] not in desc_dict:
                    desc_dict[desc["arc"]] = {}

                desc_dict[desc["arc"]][desc["episode"]] = {
                    "title": desc["title"],
                    "originaltitle": desc["originaltitle"],
                    "description": desc["description"]
                }

            for crc32, ep in episodes.items():
                if ep["arc"] in desc_dict and ep["episode"] in desc_dict[ep["arc"]]:
                    ep_desc = desc_dict[ep["arc"]][ep["episode"]]
                    if "title" in ep_desc:
                        output["episodes"][crc32] = {
                            "arc": ep.get("arc", 0),
                            "episode": ep.get("episode", 0),
                            "title": ep_desc.get("title", ""),
                            "originaltitle": ep_desc.get("originaltitle", ""),
                            "description": ep_desc.get("description", ""),
                            "chapters": str(ep.get("manga_chapters", "")),
                            "episodes": str(ep.get("anime_episodes", "")),
                            "released": str(ep.get("released", "")),
                            "hashes": {
                                "crc32": str(ep["hashes"].get("crc32", "")),
                                "blake2": str(ep["hashes"].get("blake2s", ""))
                            }
                        }

            data = Path("../data.json")
            data.unlink(missing_ok=True)
            data.write_text(json.dumps(output, indent=2, default=self.serialize_json))

            data = Path("../data.min.json")
            data.unlink(missing_ok=True)
            data.write_text(json.dumps(output, default=self.serialize_json))

        except:
            logger.exception("Unable to create compat data.json")

    def cmd_update(self):
        self.client = httpx.Client(
            transport=httpx_retries.RetryTransport(
                retry=httpx_retries.Retry(total=999, backoff_factor=5.0)
            )
        )

        now = datetime.now().astimezone(timezone.utc)

        try:
            logger.success("Loading existing arcs")
            self.load_arcs()

            logger.success("Loading title.properties / chapter.properties")
            self.get_titles_chapters()

            if now.hour % int(self.config["check_ep_descriptions_every_hours"]) == 0:
                logger.success("Updating episode descriptions")
                self.update_desc_sources()
            
            if now.hour % int(self.config["check_ep_guide_every_hours"]) == 0:
                logger.success("Updating metadata from episode guide")
                self.update_from_episode_guide()

            if now.hour % int(self.config["check_rss_every_hours"]) == 0 and self.ONE_PACE_RSS_FEED != "":
                logger.success("Checking RSS feed for new releases")
                self.update_from_rss_feed(self.ONE_PACE_RSS_FEED)

        finally:
            self.client.close()

    def cmd_json(self):
        sqlite3.register_adapter(date, self.serialize_json)
        sqlite3.register_adapter(datetime, self.serialize_json)
        self.generate_data()

if __name__ == "__main__":
    if sys.argv[1] == "update":
        OnePaceMetadata().cmd_update()
    elif sys.argv[1] == "json":
        OnePaceMetadata().cmd_json()
