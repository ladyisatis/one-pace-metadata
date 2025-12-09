CREATE TABLE "arc_episodes" (
	"id"	INTEGER,
	"arc_part"	INTEGER,
	"episode"	TEXT,
	"standard"	TEXT,
	"extended"	TEXT,
	PRIMARY KEY("id" AUTOINCREMENT)
);

CREATE TABLE "arc_info" (
	"id"	INTEGER,
	"arc_part"	INTEGER,
	"status"	TEXT,
	"manga_chapters"	TEXT,
	"num_of_chapters"	INTEGER,
	"anime_episodes"	TEXT,
	"episodes_adapted"	INTEGER,
	"filler_episodes"	TEXT,
	"num_of_pace_eps"	INTEGER,
	"piece_minutes"	INTEGER,
	"pace_minutes"	INTEGER,
	"audio_languages"	TEXT,
	"sub_languages"	TEXT,
	"pixeldrain_only"	TEXT,
	"resolution"	TEXT,
	"arc_watch_guide"	TEXT,
	PRIMARY KEY("id" AUTOINCREMENT)
);

CREATE TABLE "arcs" (
	"id"	INTEGER,
	"lang"	TEXT,
	"part"	TEXT,
	"saga"	TEXT,
	"title"	TEXT,
	"originaltitle"	TEXT,
	"shortcode"	TEXT,
	"mkvcode"	TEXT,
	"description"	INTEGER,
	"poster"   BLOB,
	PRIMARY KEY("id" AUTOINCREMENT)
);

CREATE TABLE "descriptions" (
	"id"	INTEGER,
	"lang"	TEXT,
	"arc"	INTEGER,
	"episode"	INTEGER,
	"title"	TEXT,
	"originaltitle"	TEXT,
	"description"	TEXT,
	PRIMARY KEY("id" AUTOINCREMENT)
);

CREATE TABLE "episodes" (
	"id"	INTEGER,
	"arc"	INTEGER,
	"episode"	INTEGER,
	"manga_chapters"	TEXT,
	"anime_episodes"	TEXT,
	"released"	TEXT,
	"duration"	INTEGER,
	"extended"	INTEGER,
	"hash_crc32"	TEXT,
	"hash_blake2s"	TEXT,
	"file_id"	INTEGER,
	"file_name"	TEXT,
	"file_size"	TEXT,
	"file_hash"	TEXT,
	"file_index"	INTEGER,
	PRIMARY KEY("id" AUTOINCREMENT)
);

CREATE TABLE "other_edits" (
	"id"	INTEGER,
	"edit_name" TEXT,
	"arc"	INTEGER,
	"episode"	INTEGER,
	"title"    TEXT,
	"description"    TEXT,
	"manga_chapters"	TEXT,
	"anime_episodes"	TEXT,
	"released"	TEXT,
	"duration"	INTEGER,
	"extended"	INTEGER,
	"hash_crc32"	TEXT,
	"hash_blake2s"	TEXT,
	PRIMARY KEY("id" AUTOINCREMENT)
);

CREATE TABLE "status" (
	"id"	INTEGER,
	"last_update"	TEXT,
	"last_update_ts"	INTEGER,
	"base_url"	TEXT,
	"version"	INTEGER,
	PRIMARY KEY("id" AUTOINCREMENT)
);

CREATE TABLE "tvshow" (
	"id"	INTEGER,
	"lang"	TEXT,
	"key"	TEXT,
	"value"	TEXT,
	PRIMARY KEY("id" AUTOINCREMENT)
);
