import asyncio, json, collections, locale, httpx, os, aiofiles
from logging import error
from bs4 import BeautifulSoup
import playwright.async_api
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async
from typing import Any, Dict, Literal
from colorama import Fore
import argparse

headers = {'Accept': 'video/webm,video/ogg,video/*;q=0.9,application/ogg;q=0.7,audio/*;q=0.6,*/*;q=0.5','Accept-Language': 'fr,fr-FR;q=0.8,en-US;q=0.5,en;q=0.3','Cache-Control': 'no-cache','Connection': 'keep-alive','Pragma': 'no-cache','Range': 'bytes=0-','Referer': 'https://www.tiktok.com/','Sec-Fetch-Dest': 'video','Sec-Fetch-Mode': 'no-cors','Sec-Fetch-Site': 'same-site','User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.0.0 Safari/537.36",}

class TikTok:
    def __init__(self, tiktok_data: Dict[str, Any]) -> None:
        self._tiktok_data = tiktok_data

    def __str__(self) -> str:
        return f"<{self.__class__.__name__}(id='{self.id}', description='{self.description}')>"

    @property
    def id(self) -> str:
        return self._tiktok_data["id"]

    @property
    def download_addr(self) -> str:
        return self._tiktok_data["video"]["downloadAddr"]

    @property
    def description(self) -> str:
        return self._tiktok_data["desc"]

    @property
    def create_time(self) -> int:
        return self._tiktok_data["createTtime"]

    @property
    def unique_id(self) -> str:
        return self._tiktok_data["author"]["uniqueId"]

    @property
    def video_format(self) -> str:
        return self._tiktok_data["video"]["format"]

    @property
    def video_filename(self) -> str:
        return f"{self.id}.{self.video_format}"

async def download_video(session: httpx.AsyncClient, download_addr_url: str, filename: str, username: str) -> None:
    full_directory_path = f"video/{username}"
    if not os.path.exists(full_directory_path):
        os.makedirs(full_directory_path)

    files = set(os.listdir(full_directory_path))

    if filename not in files:
        full_path_file = f"{full_directory_path}/{filename}"
        async with aiofiles.open(full_path_file, mode="wb") as file:
            response = await session.get(download_addr_url)
            async for chunk in response.aiter_bytes():
                await file.write(chunk)
            print(f"{Fore.RESET}[{Fore.GREEN}+{Fore.RESET}] {filename}")

    else:
        print(f"{Fore.RESET}[{Fore.GREEN}+{Fore.RESET}] {filename} already downloaded.")


async def block_unnecessary_resources(route: playwright.async_api.Route) -> None:
    resourc_type = ["stylesheet", "image", "media", "font", "websocket", "eventsource"]
    if (route.request.resource_type in resourc_type):
        await route.abort()
    elif route.request.url == "https://mon-va.byteoversea.com/monitor_browser/collect/batch/":
        await route.abort()
    else:
        await route.continue_()

async def scroll_to_bottom(page: playwright.async_api.Page,
                           load_state_method: Literal["networkidle", "load", "domcontentloaded"] = "domcontentloaded"
                           ) -> None:

    positions_deque_size = 300
    last_y_positions = collections.deque(maxlen=positions_deque_size)

    has_reached = False
    while not has_reached:
        await page.mouse.wheel(delta_x=0, delta_y=75)
        await page.wait_for_load_state(load_state_method)

        value = await page.evaluate("window.scrollY")
        last_y_positions.append(value)

        if len(last_y_positions) == positions_deque_size and len(set(last_y_positions)) == 1:
            has_reached = True


async def handle_response(response: playwright.async_api.Response) -> None:
    try:
        if (response.request.resource_type == "document" and response.status != 302):
            content = await response.text()
            soup = BeautifulSoup(content, "html.parser")
            json_data = soup.select_one("script#SIGI_STATE").text
            data = json.loads(json_data)

            users = data["UserModule"]["users"]
            tiktoks = data["ItemModule"].values()

            for tiktok in tiktoks:
                user = tiktok["author"]
                tiktok["author"] = users[user]

        elif response.url.startswith("https://www.tiktok.com/api/post/item_list/"):
            json_data = await response.json()
            tiktoks = json_data["itemList"]

        async with httpx.AsyncClient(headers=headers) as client:
            tasks = []
            for tiktok in tiktoks:
                item = TikTok(tiktok)
                tasks.append(asyncio.ensure_future(download_video(client, item.download_addr, item.video_filename, item.unique_id)))
            await asyncio.gather(*tasks)
    except:
        pass

async def scraper(username: str, headless: bool = True):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.5060.53 Safari/537.36",
            locale=locale.getdefaultlocale()[0]
        )
        page = await context.new_page()
        await stealth_async(page)

        await page.route("**/*", block_unnecessary_resources)
        page.on("response", handle_response)

        await page.goto(f"https://www.tiktok.com/@{username}")
        await scroll_to_bottom(page)

        await context.close()
        await browser.close()

def run(username: str) -> None:
    asyncio.run(scraper(username, headless=True))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("user", help="Tiktok User Name", type=str)
    args = parser.parse_args()
    user = args.user.lower()
    run(user)