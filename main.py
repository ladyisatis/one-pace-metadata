import traceback
import re
import sys
import orjson
import httpx
import javaproperties
import io
import os
import string
import time
from loguru import logger
from deepdiff import DeepDiff
from csv import DictReader as CSVReader
from datetime import date, datetime, timezone, timedelta
from yaml import dump as YamlDump, safe_load as YamlLoad
from pathlib import Path
from httpx_retries import RetryTransport, Retry
from rss_parser import RSSParser
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs, unquote

def escape_char(c):
    if c == "’":
        return "'"
    elif c == "…":
        return "..."
    elif c == "“" or c == "”":
        return '"'
    elif c in string.printable and ord(c) < 128:
        return c
    elif ord(c) <= 0xFFFF:
        return f'\\u{ord(c):04x}'
    else:
        return f'\\U{ord(c):08x}'

def unicode_fix(s):
    return ''.join(escape_char(c) for c in s)

def update():
    GCLOUD_API_KEY=os.environ['GCLOUD_API_KEY'] if 'GCLOUD_API_KEY' in os.environ else ''
    if GCLOUD_API_KEY == "":
        logger.critical("Skipping: GCLOUD_API_KEY is empty")
        return

    ONE_PACE_EPISODE_GUIDE_ID="1HQRMJgu_zArp-sLnvFMDzOyjdsht87eFLECxMK858lA"
    ONE_PACE_EPISODE_DESC_ID="1M0Aa2p5x7NioaH9-u8FyHq6rH3t5s6Sccs8GoC6pHAM"
    ONE_PACE_RSS_FEED=os.environ['ONE_PACE_RSS_FEED'] if 'ONE_PACE_RSS_FEED' in os.environ else ''

    PATTERN_END_NUMBER = r'(\d+)'
    PATTERN_CHAPTER_EPISODE = r'\b\d+(?:-\d+)?(?:,\s*\d+(?:-\d+)?)*\b'
    PATTERN_TITLE = r'\[One Pace\]\[\d+(?:[-,]\d+)*\]\s+(.+?)\s+(\d{2,})\s*(\w+)?\s*\[\d+p\]\[([A-Fa-f0-9]{8})\]\.mkv'

    try:
        with Path(".", "arcs.yml").open(mode='r', encoding='utf-8') as f:
            out_arcs = YamlLoad(stream=f)
    except:
        out_arcs = {}

    out_episodes = {}
    arc_eps = {}
    arc_to_num = {}

    try:
        now = datetime.now(timezone.utc)
        retry = Retry(total=999, backoff_factor=5.0)
        spreadsheet = {"sheets": []}

        with httpx.Client(transport=RetryTransport(retry=retry)) as client:
            title_props = None
            chapter_props = None
            mkv_titles = {}
            chapter_list = {}

            logger.info("1. mkv_titles")

            try:
                resp = client.get("https://raw.githubusercontent.com/one-pace/one-pace-public-subtitles/refs/heads/main/main/title.properties", follow_redirects=True)
                title_props = javaproperties.loads(resp.text)
                resp = client.get("https://raw.githubusercontent.com/one-pace/one-pace-public-subtitles/refs/heads/main/main/chapter.properties", follow_redirects=True)
                chapter_props = javaproperties.loads(resp.text)
            except:
                logger.warning(f"Skipping title.properties parsing\n{traceback.format_exc()}")

            if isinstance(title_props, dict):
                pattern = re.compile(r"^(?P<arc>[a-z]+)(?:_[0-9]+)?_(?P<num>\d+)\.eptitle$")
                arc_name_to_id = {}

                for k, v in title_props.items():
                    match = pattern.match(k)
                    if not match:
                        continue

                    arc_name = match.group("arc")
                    ep_num = f"{int(match.group("num"))}"

                    if arc_name not in arc_name_to_id:
                        if arc_name == "loguetown":
                            arc_name_to_id["adv_buggy"] = {}
                            chapter_list["adv_buggy"] = {}
                        elif arc_name == "littlegarden":
                            arc_name_to_id["trials_koby"] = {}
                            chapter_list["trials_koby"] = {}
                        elif arc_name == "marineford":
                            arc_name_to_id["adv_strawhats"] = {}
                            chapter_list["adv_strawhats"] = {}

                        arc_id = f"{len(arc_name_to_id)}"
                        arc_name_to_id[arc_name] = arc_id
                        mkv_titles[arc_id] = {}
                        chapter_list[arc_id] = {}

                    arc_id = arc_name_to_id[arc_name]
                    mkv_titles[arc_id][ep_num] = v

                    chap_k = k.replace(".eptitle", ".chapter")
                    if chap_k in chapter_props:
                        chapter_list[arc_id][ep_num] = chapter_props[chap_k]

            logger.info("2. One Pace Episode Descriptions Arcs")

            _s = []
            with client.stream("GET", f"https://docs.google.com/spreadsheets/d/{ONE_PACE_EPISODE_DESC_ID}/export?gid=2010244982&format=csv", follow_redirects=True) as resp:
                reader = CSVReader(resp.iter_lines())

                for row in reader:
                    if 'title_en' not in row or row['title_en'] == '' or row['part'] == '':
                        continue

                    part = int(row['part'])
                    title = row['title_en'].strip()

                    if part == 11 and title.startswith("Whisk"):
                        part = 10
                    elif part == 10 and title.startswith("The Trials"):
                        part = 11
                    elif part == 99:
                        part = 0
                    elif part > 90:
                        continue

                    if part not in out_arcs:
                        out_arcs[part] = {
                            "part": part,
                            "saga": row['saga_title'],
                            "title": title,
                            "originaltitle": "",
                            "description": row['description_en'],
                            "poster": "",
                            "episodes": {}
                        }
                    else:
                        out_arcs[part]["part"] = part
                        out_arcs[part]["saga"] = row["saga_title"]
                        out_arcs[part]["title"] = title
                        out_arcs[part]["description"] = row["description_en"]

                    arc_to_num[title] = part

            logger.info("3. CRC32 updates from One Pace Episode Guide")

            r = client.get(f"https://sheets.googleapis.com/v4/spreadsheets/{ONE_PACE_EPISODE_GUIDE_ID}?key={GCLOUD_API_KEY}")
            spreadsheet = orjson.loads(r.content)

            for arc, sheet in enumerate(spreadsheet['sheets']):
                sheetId = sheet['properties']['sheetId']
                if sheetId == 0:
                    continue

                arc_title = sheet['properties']['title']

                if arc_title != out_arcs[arc]['title']:
                    out_arcs[arc]['originaltitle'] = out_arcs[arc]['title']
                    out_arcs[arc]['title'] = arc_title
                    arc_to_num[arc_title] = arc

                crc32_id = {}

                try:
                    spreadsheet_html = None

                    if now.weekday() == 2 and now.hour == 0:
                        logger.info("3a. Update IDs")

                        spreadsheet_html = client.get(f"https://docs.google.com/spreadsheets/u/0/d/{ONE_PACE_EPISODE_GUIDE_ID}/htmlview/sheet?headers=true&gid={sheetId}", follow_redirects=True)
                        html_parser = BeautifulSoup(spreadsheet_html.text, "html.parser")

                        for a in html_parser.find_all("a", href=True):
                            crc32 = a.get_text(strip=True)
                            if re.fullmatch(r"[A-Z0-9]{8}", crc32):
                                if "/view/" in a["href"]:
                                    match = re.search(r"/view/(\d+)", a["href"])
                                    if match:
                                        crc32_id[crc32] = match.group(1)
                                elif "/?q%3D" in a["href"]:
                                    href = a["href"]
                                    if "google.com" in href:
                                        href = unquote(parse_qs(urlparse(href).query)['q'][0])

                                    res = client.get(href)
                                    if (res.status_code == 301 or res.status_code == 302) and "Location" in res.headers:
                                        match = re.search(r"/view/(\d+)", res.headers["Location"])
                                        if match:
                                            crc32_id[crc32] = match.group(1)

                    poster_path = Path(".", "posters", f"{arc}", "poster.png")

                    if not poster_path.exists():
                        poster_path.parent.mkdir(exist_ok=True)

                        if spreadsheet_html is None:
                            spreadsheet_html = client.get(f"https://docs.google.com/spreadsheets/u/0/d/{ONE_PACE_EPISODE_GUIDE_ID}/htmlview/sheet?headers=true&gid={sheetId}", follow_redirects=True)
                            html_parser = BeautifulSoup(spreadsheet_html.text, "html.parser")

                        img = html_parser.find("img")
                        if img and img.get("src", "") != "":
                            with poster_path.open(mode='wb') as f:
                                with client.stream("GET", img["src"], follow_redirects=True) as resp:
                                    for chunk in resp.iter_bytes():
                                        f.write(chunk)

                    if poster_path.exists():
                        out_arcs[arc]['poster'] = f"posters/{arc}/{poster_path.name}"

                except:
                    logger.exception("-- Skipping fetching poster/links")

                with client.stream("GET", f"https://docs.google.com/spreadsheets/d/{ONE_PACE_EPISODE_GUIDE_ID}/export?gid={sheetId}&format=csv", follow_redirects=True) as resp:
                    reader = CSVReader(resp.iter_lines())

                    for _row in reader:
                        row = {}
                        for k, v in _row.items():
                            row[k.strip()] = v

                        if 'MKV CRC32' not in row:
                            continue

                        id = row['One Pace Episode'].strip() if 'One Pace Episode' in row else ''
                        chapters = row['Chapters'].strip() if 'Chapters' in row else ''
                        anime_episodes = row['Episodes'].strip() if 'Episodes' in row else ''
                        release_date = row['Release Date'].strip() if 'Release Date' in row else ''
                        mkv_crc32 = row['MKV CRC32'].strip() if 'MKV CRC32' in row else ''
                        mkv_crc32_ext = row['MKV CRC32 (Extended)'].strip() if 'MKV CRC32 (Extended)' in row else ''

                        if mkv_crc32 == '':
                            continue

                        if id == '' or chapters == '' or anime_episodes == '' or release_date == '' or mkv_crc32 == '':
                            logger.warning(f"Skipping: {row} (no data)")
                            continue

                        match = re.search(PATTERN_END_NUMBER, id)
                        if match:
                            _e = match.group(1)
                            episode = int(_e)
                        else:
                            _e = "01"
                            episode = 1

                        match = re.search(PATTERN_CHAPTER_EPISODE, chapters)
                        if match:
                            chapters = match.group(0).replace(" ", "").replace(",", ", ")

                        match = re.search(PATTERN_CHAPTER_EPISODE, anime_episodes)
                        if match:
                            anime_episodes = match.group(0).replace(", ", ",").replace(",", ", ")

                        release_date_group = release_date.split(".")
                        if len(release_date_group) == 3:
                            release_date = date(int(release_date_group[0]), int(release_date_group[1]), int(release_date_group[2]))
                        else:
                            release_date_group = release_date.split("-")
                            if len(release_date_group) == 3:
                                release_date = date(int(release_date_group[0]), int(release_date_group[1]), int(release_date_group[2]))
                            else:
                                logger.warning(f"Skipping: {row} (invalid release date)")
                                continue

                        out_episodes[mkv_crc32] = {
                            "arc": arc,
                            "episode": episode,
                            "title": f"{out_arcs[arc]['title']} {episode:02d}",
                            "description": "",
                            "chapters": str(chapters),
                            "episodes": str(anime_episodes),
                            "released": release_date.isoformat()
                        }

                        if _e not in out_arcs[arc]["episodes"]:
                            out_arcs[arc]["episodes"][_e] = {
                                "length": row['Length'].strip() if 'Length' in row else '',
                                "crc32": mkv_crc32,
                                "crc32_extended": mkv_crc32_ext,
                                "tid": "",
                                "tid_extended": ""
                            }
                        else:
                            out_arcs[arc]["episodes"][_e]["length"] = row['Length'].strip() if 'Length' in row else ''
                            out_arcs[arc]["episodes"][_e]["crc32"] = mkv_crc32
                            out_arcs[arc]["episodes"][_e]["crc32_extended"] = mkv_crc32_ext

                        _tid = crc32_id.get(mkv_crc32, "")
                        if _tid != "" and out_arcs[arc]["episodes"][_e]["tid"] == "":
                            out_arcs[arc]["episodes"][_e]["tid"] = _tid

                        _tid_ext = crc32_id.get(mkv_crc32_ext, "")
                        if _tid_ext != "" and out_arcs[arc]["episodes"][_e]["tid_extended"] == "":
                            out_arcs[arc]["episodes"][_e]["tid_extended"] = _tid_ext

                        if len(mkv_crc32_ext) > 0:
                            out_episodes[mkv_crc32_ext] = out_episodes[mkv_crc32]

                        key = f"{out_arcs[arc]['originaltitle']} {episode}" if 'originaltitle' in out_arcs[arc] and out_arcs[arc]['originaltitle'] != "" else f"{out_arcs[arc]['title']} {episode}"
                        if key in arc_eps:
                            arc_eps[key].append(mkv_crc32)

                            if mkv_crc32_ext != '':
                                arc_eps[key].append(mkv_crc32_ext)

                        else:
                            arc_eps[key] = [mkv_crc32] if mkv_crc32_ext == '' else [mkv_crc32, mkv_crc32_ext]

            logger.info("4. One Pace RSS Feed")

            if ONE_PACE_RSS_FEED != '':
                try:
                    r = client.get(ONE_PACE_RSS_FEED)
                    title_pattern = re.compile(PATTERN_TITLE, re.IGNORECASE)
                    now = datetime.now().astimezone(timezone.utc)

                    for i, item in enumerate(RSSParser.parse(r.text).channel.items):
                        if not item.title or not item.title.content or item.title.content == "":
                            logger.warning(f"Skipping: {item}")
                            continue

                        pub_date = datetime.strptime(item.pub_date.content, "%a, %d %b %Y %H:%M:%S %z")

                        if item.title.content.endswith(".mkv") or item.title.content.endswith(".mp4"):
                            match = title_pattern.match(item.title.content)
                            if not match:
                                continue

                            arc_name, ep_num, extra, crc32 = match.groups()

                            key = f"{arc_name} {ep_num}"
                            if key in arc_eps:
                                if crc32 not in arc_eps[key]:
                                    arc_eps[key].append(crc32)
                            else:
                                arc_eps[key] = [crc32]

                            crc_key = "crc32_extended" if "Extended" in item.title.content else "crc32"
                            tid_key = "tid_extended" if "Extended" in item.title.content else "tid"

                            arc_id = arc_to_num.get(arc_name, -1)
                            if arc_id != -1 and ep_num in out_arcs[arc_id]["episodes"]:
                                out_arcs[arc_id]["episodes"][ep_num][crc_key] = crc32
                                if "/view/" in item.guid.content and tid_key in out_arcs[arc_id]["episodes"][ep_num]:
                                    out_arcs[arc_id]["episodes"][ep_num][tid_key] = item.guid.content.split("/view/")[1]

                            if Path(".", "episodes", f"{crc32}.yml").exists():
                                continue

                            r = httpx.get(item.guid.content)
                            div = BeautifulSoup(r.text, 'html.parser').find('div', { 'class': 'panel-body', 'id': 'torrent-description' })
                            desc = div.get_text(strip=True).split("\n") if div else []

                            chs = ""
                            eps = ""

                            for d in desc:
                                if d.startswith("Chapters: "):
                                    chs = d.replace("Chapters: ", "")
                                elif d.startswith("Episodes: "):
                                    eps = d.replace("Episodes: ", "")

                            if arc_name in arc_to_num:
                                _s = arc_to_num[arc_name]
                                ep_num = int(ep_num)
                                released = (pub_date.isoformat().split("T"))[0]
                                t = f"{arc_name} {ep_num:02d}"
                                ep_desc = ""

                                if crc32 not in out_episodes:
                                    if chs == "" or eps == "":
                                        for v in out_episodes.values():
                                            if v["arc"] == _s and v["episode"] == ep_num and v["chapters"] != "" and v["episodes"] != "":
                                                t = v["title"]
                                                ep_desc = v["description"]
                                                chs = v["chapters"]
                                                eps = v["episodes"]
                                                break

                                    out_episodes[crc32] = {
                                        "arc": _s,
                                        "episode": ep_num,
                                        "title": t,
                                        "description": ep_desc,
                                        "chapters": chs,
                                        "episodes": eps,
                                        "released": released
                                    }

                                logger.success(f"-- Added S{arc_to_num[arc_name]:02d}E{ep_num:02d} ({t}, {released})")

                            else:
                                logger.warning(f"-- Skipping: arc {arc_name} not found")

                        elif now.hour % 6 == 0:
                            r = httpx.get(item.guid.content)

                            for item in BeautifulSoup(r.text, "html.parser").select("li i.fa-file"):
                                li = item.find_parent("li")
                                if not li:
                                    continue

                                filename = " ".join([t for t in li.stripped_strings if not t.startswith("(")])

                                match = title_pattern.match(filename)
                                if not match:
                                    logger.warning("---- Skipping: regex does not match")
                                    continue

                                arc_name, ep_num, extra, crc32 = match.groups()

                                key = f"{arc_name} {ep_num}"
                                if key in arc_eps:
                                    if crc32 not in arc_eps[key]:
                                        arc_eps[key].append(crc32)
                                else:
                                    arc_eps[key] = [crc32]

                                crc_key = "crc32_extended" if "Extended" in item.title.content else "crc32"
                                tid_key = "tid_extended" if "Extended" in item.title.content else "tid"
    
                                arc_id = arc_to_num.get(arc_name, -1)
                                if arc_id != -1 and ep_num in out_arcs[arc_id]["episodes"]:
                                    out_arcs[arc_id]["episodes"][ep_num][crc_key] = crc32
                                    if "/view/" in item.guid.content and tid_key in out_arcs[arc_id]["episodes"][ep_num]:
                                        out_arcs[arc_id]["episodes"][ep_num][tid_key] = item.guid.content.split("/view/")[1]

                                if Path(".", "episodes", f"{crc32}.yml").exists():
                                    logger.warning("---- Skipping: crc32 file exists")
                                    continue

                                if arc_name in arc_to_num:
                                    ep_num = int(ep_num)
                                    released = (pub_date.isoformat().split("T"))[0]
                                    t = f"{arc_name} {ep_num:02d}"
                                    ep_desc = ""

                                    if crc32 not in out_episodes:
                                        _s = arc_to_num[arc_name]
                                        chs = ""
                                        eps = ""

                                        for v in out_episodes.values():
                                            if v["arc"] == _s and v["episode"] == ep_num and v["chapters"] != "" and v["episodes"] != "":
                                                t = v["title"]
                                                ep_desc = v["description"]
                                                chs = v["chapters"]
                                                eps = v["episodes"]
                                                break

                                        out_episodes[crc32] = {
                                            "arc": _s,
                                            "episode": ep_num,
                                            "title": t,
                                            "description": ep_desc,
                                            "chapters": chs,
                                            "episodes": eps,
                                            "released": released
                                        }

                                    logger.success(f"---- Added S{arc_to_num[arc_name]:02d}E{ep_num:02d} ({t}, {released})")
                                else:
                                    logger.warning(f"---- Skipping: arc {arc_name} not found")

                except:
                    logger.error(f"Skipping RSS parsing\n{traceback.format_exc()}")

            logger.info("5. One Pace Episode Descriptions Update")

            with client.stream("GET", f"https://docs.google.com/spreadsheets/d/{ONE_PACE_EPISODE_DESC_ID}/export?gid=0&format=csv", follow_redirects=True) as resp:
                reader = CSVReader(resp.iter_lines())

                for row in reader:
                    if 'arc_title' not in row:
                        continue

                    arc = row['arc_title']
                    episode = row['arc_part']
                    title = row['title_en']
                    description = row['description_en']

                    if arc == '' or episode == '' or title == '':
                        continue

                    key = f"{arc} {episode}"
                    if key not in arc_eps:
                        logger.warning(f"Skipping: {key} (not found)")
                        continue

                    for crc32 in arc_eps[key]:
                        if crc32 in out_episodes:
                            out_episodes[crc32]["episode"] = int(episode)
                            out_episodes[crc32]["title"] = title
                            out_episodes[crc32]["description"] = description
    
                            try:
                                _s = f"{out_episodes[crc32]['arc']}"
                                _e = f"{out_episodes[crc32]['episode']}"
    
                                if _s != "0":
                                    if _s in mkv_titles and _e in mkv_titles[_s]:
                                        _origtitle = mkv_titles[_s][_e]
        
                                        if title.lower() != _origtitle.lower():
                                            out_episodes[crc32]["originaltitle"] = _origtitle
    
                                    if _s in chapter_list and _e in chapter_list[_s]:
                                        out_episodes[crc32]["chapters"] = chapter_list[_s][_e]
    
                            except:
                                logger.error(f"Skipping: {key}\n{traceback.format_exc()}")

        logger.info("6. Update Files")

        for crc32, data in out_episodes.items():
            file_path = Path(".", "episodes", f"{crc32}.yml")

            arc = data['arc']
            episode = data['episode']
            released = data['released']

            if arc == 99:
                arc = 0
            elif arc > 90:
                episode = arc
                arc = 0

            if isinstance(released, date) or isinstance(released, datetime):
                released = released.isoformat()

            if file_path.exists():
                old_data = {"episode": None, "title": "", "description": "", "chapters": "", "episodes": "", "released": ""}

                with file_path.open(mode='r', encoding='utf-8') as f:
                    old_data = YamlLoad(stream=f)

                if "reference" in old_data:
                    continue

                if isinstance(old_data["released"], date) or isinstance(old_data["released"], datetime):
                    old_data["released"] = old_data["released"].isoformat()

                if old_data["episode"] == episode and old_data["title"] != "" and old_data["description"] != "" and old_data["chapters"] != "" and old_data["episodes"] != "" and old_data["released"] != "":
                    continue

            out = (
                f"arc: {arc}\n"
                f"episode: {episode}\n"
                "\n"
                "{title}"
                "{originaltitle}"
                "{sorttitle}\n"
                "{description}"
                f"chapters: {data['chapters']}\n"
                f"episodes: {data['episodes']}\n"
                "\n"
                "# rating: TV-14\n"
                f"released: {released}\n"
                "\n"
                "hashes:\n"
                f"  crc32: {crc32}\n"
                "# blake2: \n"
            )

            # attempt to bypass some unicode nonsense

            if 'originaltitle' in data and data['originaltitle'] != "":
                out = out.replace("{originaltitle}", YamlDump({"originaltitle": data['originaltitle']}, allow_unicode=True), 1)
            else:
                out = out.replace("{originaltitle}", "# originaltitle: \n", 1)

            if data['title'].startswith('The '):
                out = out.replace("{sorttitle}", YamlDump({"sorttitle": data['title'].replace('The ', '', 1)}, allow_unicode=True), 1)
            else:
                out = out.replace("{sorttitle}", "# sorttitle: \n", 1)

            out = out.replace("{title}", YamlDump({"title": data['title']}, allow_unicode=True), 1)
            out = out.replace("{description}", YamlDump({"description": data['description']}, allow_unicode=True), 1)

            if not file_path.is_file() or file_path.read_text() != out:
                with file_path.open(mode='w') as f:
                    f.write(out)

                logger.success(f"Wrote episode to {file_path}")

        _all_crc32 = True
        if isinstance(out_arcs, list):
            for i, a in enumerate(out_arcs):
                if i != 0 and len(a["episodes"]) == 0:
                    _all_crc32 = False
                    break
        elif isinstance(out_arcs, dict):
            for k, v in out_arcs.items():
                if int(k) != 0 and len(v["episodes"]) == 0:
                    _all_crc32 = False
                    break

        if _all_crc32:
            arc_path = Path(".", "arcs.yml")
            with arc_path.open(mode='w') as f:
                YamlDump(data=out_arcs, stream=f, allow_unicode=True, sort_keys=False)

    except:
        logger.critical(f"Uncaught Exception\n{traceback.format_exc()}")
        sys.exit(1)

def sort_dict(d):
    return {key: d[key] for key in sorted(d.keys())}

def dict_changed(old, new):
    changed = DeepDiff(old, new)

    for i in ['dictionary_item_added', 'dictionary_item_removed', 'values_changed']:
        if i in changed:
            return True

    return False

def unicode_fix_dict(d):
    new_dict = {}

    for key in d.keys():
        str_key = str(key)
        new_dict[str_key] = {}

        for inner_key, val in d[key].items():
            if isinstance(val, date) or isinstance(val, datetime):
                new_dict[str_key][inner_key] = val.isoformat()
            elif isinstance(val, str):
                new_dict[str_key][inner_key] = unicode_fix(val)
            elif not (inner_key == "arc" or inner_key == "episode" or inner_key == "part") and (isinstance(val, int) or isinstance(val, float)):
                new_dict[str_key][inner_key] = str(val)
            else:
                new_dict[str_key][inner_key] = val

    return new_dict

def val_convert_string(d):
    if isinstance(d, list):
        for k, v in enumerate(d):
            d[k] = val_convert_string(v)
        return d

    elif isinstance(d, dict):
        for k, v in d.items():
            d[k] = val_convert_string(v)
        return d

    elif isinstance(d, bool):
        return "true" if d else "false"

    return unicode_fix(str(d))

def generate_json():
    tvshow_yml = Path(".", "tvshow.yml")
    arcs_yml = Path(".", "arcs.yml")
    episodes_dir = Path(".", "episodes")
    data_yml = Path(".", "data.yml")
    json_file = Path(".", "data.json")
    json_min_file = Path(".", "data.min.json")

    tvshow = {}
    arcs = []

    with tvshow_yml.open(mode='r', encoding='utf-8') as f:
        tvshow = val_convert_string(YamlLoad(stream=f))

    with arcs_yml.open(mode='r', encoding='utf-8') as f:
        arcs = YamlLoad(stream=f)

    episodes = {}

    for episode_yml in episodes_dir.glob('*.yml'):
        key = episode_yml.name.replace('.yml', '')

        with episode_yml.open(mode='r', encoding='utf-8') as f:
            episodes[key] = YamlLoad(stream=f)

        if 'reference' in episodes[key]:
            with Path(episodes_dir, f"{episodes[key]['reference']}.yml").open(mode='r', encoding='utf-8') as f:
                episodes[key] = YamlLoad(stream=f)

    episodes = sort_dict(episodes)

#    try:
#        old = {}
#        with data_yml.open(mode='r', encoding='utf-8') as f:
#            old = YamlLoad(stream=f)

#        episodes_changed = dict_changed(old["episodes"], episodes)
#        arcs_changed = dict_changed(old["arcs"], arcs)
#        tvshow_changed = dict_changed(old["tvshow"], tvshow)
#    except Exception as e:
#        logger.exception("Something went wrong")
#        episodes_changed = True
#        arcs_changed = True
#        tvshow_changed = True
    enable_changes = True

    if enable_changes:
        now = datetime.now(timezone.utc)

        with data_yml.open(mode='w') as f:
            YamlDump(data={
                "last_update": now.isoformat(),
                "last_update_ts": now.timestamp(),
                "base_url": f"https://raw.githubusercontent.com/{os.environ['GITHUB_REPOSITORY']}/refs/heads/main",
                "tvshow": tvshow,
                "arcs": arcs,
                "episodes": episodes
            }, stream=f, allow_unicode=True, sort_keys=False)

        if isinstance(arcs, list):
            for i, arc in enumerate(arcs):
                arcs[i] = unicode_fix_dict(arc)
        elif isinstance(arcs, dict):
            arcs = unicode_fix_dict(sort_dict(arcs))
            arcs = [arc for arc in arcs.values()]

        out = {
            "last_update": now.isoformat(),
            "last_update_ts": now.timestamp(),
            "base_url": f"https://raw.githubusercontent.com/{os.environ['GITHUB_REPOSITORY']}/refs/heads/main",
            "tvshow": tvshow,
            "arcs": arcs,
            "episodes": unicode_fix_dict(episodes)
        }

        _data_json_out = orjson.dumps(out, option=orjson.OPT_NON_STR_KEYS | orjson.OPT_INDENT_2).replace(b"\\\\", b"\\")
        json_file.write_bytes(_data_json_out)
        _data_min_json = orjson.dumps(out, option=orjson.OPT_NON_STR_KEYS).replace(b"\\\\", b"\\")
        json_min_file.write_bytes(_data_min_json)

def main():
    if len(sys.argv) > 1 and sys.argv[1] == 'update':
        update()
        return

    generate_json()

if __name__ == '__main__':
    main()
