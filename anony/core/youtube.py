# Copyright (c) 2025 AnonymousX1025
# Licensed under the MIT License.
# This file is part of AnonXMusic

import os
import re
import yt_dlp
import random
import asyncio
import aiohttp
from pathlib import Path

from py_yt import Playlist, VideosSearch

from anony import logger
from anony.helpers import Track, utils


class YouTube:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.cookies = []
        self.checked = False
        self.warned = False
        self.cookie_dir = "anony/cookies"
        self.regex = re.compile(
            r"(https?://)?(www\.|m\.|music\.)?"
            r"(youtube\.com/(watch\?v=|shorts/|playlist\?list=)|youtu\.be/)"
            r"([A-Za-z0-9_-]{11}|PL[A-Za-z0-9_-]+)([&?][^\s]*)?"
        )

    # ================= COOKIE HANDLING =================

    def get_cookies(self):
        if self.checked:
            return random.choice(self.cookies) if self.cookies else None

        self.checked = True

        if not os.path.isdir(self.cookie_dir):
            logger.warning("Cookie directory not found, continuing without cookies.")
            return None

        for file in os.listdir(self.cookie_dir):
            if not file.endswith(".txt"):
                continue

            path = os.path.join(self.cookie_dir, file)

            # skip empty / tiny / broken cookies
            if os.path.getsize(path) < 50:
                logger.warning(f"Skipping invalid cookie: {path}")
                continue

            self.cookies.append(path)

        if not self.cookies and not self.warned:
            self.warned = True
            logger.warning("No valid cookies found, continuing without cookies.")

        return random.choice(self.cookies) if self.cookies else None

    async def save_cookies(self, urls: list[str]) -> None:
        if not urls:
            return

        os.makedirs(self.cookie_dir, exist_ok=True)
        logger.info("Saving cookies from urls...")

        async with aiohttp.ClientSession() as session:
            for i, url in enumerate(urls):
                try:
                    path = f"{self.cookie_dir}/cookie_{i}.txt"
                    link = "https://batbin.me/api/v2/paste/" + url.split("/")[-1]

                    async with session.get(link) as resp:
                        resp.raise_for_status()
                        data = await resp.read()

                    if len(data) < 50:
                        continue

                    with open(path, "wb") as fw:
                        fw.write(data)

                except Exception as e:
                    logger.warning(f"Failed to save cookie: {e}")

        logger.info("Cookie saving finished.")

    # ================= URL CHECK =================

    def valid(self, url: str) -> bool:
        return bool(re.match(self.regex, url))

    # ================= SEARCH =================

    async def search(self, query: str, m_id: int, video: bool = False) -> Track | None:
        _search = VideosSearch(query, limit=1, with_live=False)
        results = await _search.next()

        if not results or not results.get("result"):
            return None

        data = results["result"][0]

        return Track(
            id=data.get("id"),
            channel_name=data.get("channel", {}).get("name"),
            duration=data.get("duration"),
            duration_sec=utils.to_seconds(data.get("duration")),
            message_id=m_id,
            title=data.get("title"),
            thumbnail=data.get("thumbnails", [{}])[-1].get("url", "").split("?")[0],
            url=data.get("link"),
            view_count=data.get("viewCount", {}).get("short"),
            video=video,
        )

    # ================= PLAYLIST =================

    async def playlist(self, limit: int, user: str, url: str, video: bool) -> list[Track]:
        tracks = []
        try:
            plist = await Playlist.get(url)
            for data in plist["videos"][:limit]:
                tracks.append(
                    Track(
                        id=data.get("id"),
                        channel_name=data.get("channel", {}).get("name", ""),
                        duration=data.get("duration"),
                        duration_sec=utils.to_seconds(data.get("duration")),
                        title=data.get("title"),
                        thumbnail=data.get("thumbnails")[-1].get("url").split("?")[0],
                        url=data.get("link").split("&list=")[0],
                        user=user,
                        view_count="",
                        video=video,
                    )
                )
        except Exception as e:
            logger.warning(f"Playlist fetch failed: {e}")

        return tracks

    # ================= DOWNLOAD =================

    async def download(self, video_id: str, video: bool = False) -> str | None:
        url = self.base + video_id
        ext = "mp4" if video else "webm"
        filename = f"downloads/{video_id}.{ext}"

        if Path(filename).exists():
            return filename

        os.makedirs("downloads", exist_ok=True)

        cookie = self.get_cookies()

        base_opts = {
            "outtmpl": "downloads/%(id)s.%(ext)s",
            "quiet": True,
            "noplaylist": True,
            "geo_bypass": True,
            "no_warnings": True,
            "overwrites": False,
            "nocheckcertificate": True,
        }

        if cookie:
            base_opts["cookiefile"] = cookie

        if video:
            ydl_opts = {
                **base_opts,
                "format": "(bestvideo[height<=?720][width<=?1280][ext=mp4])+(bestaudio)",
                "merge_output_format": "mp4",
            }
        else:
            ydl_opts = {
                **base_opts,
                "format": "bestaudio[acodec=opus]/bestaudio",
            }

        def _download():
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                return filename
            except yt_dlp.utils.DownloadError as e:
                logger.warning(f"yt-dlp error: {e}")

                # auto fallback: retry without cookies
                if "cookiefile" in ydl_opts:
                    logger.warning("Retrying download without cookies...")
                    ydl_opts.pop("cookiefile", None)
                    try:
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            ydl.download([url])
                        return filename
                    except Exception as ex:
                        logger.warning(f"Retry failed: {ex}")

                return None
            except Exception as ex:
                logger.warning(f"Download failed: {ex}")
                return None

        return await asyncio.to_thread(_download)
