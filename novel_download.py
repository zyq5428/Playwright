import asyncio
from playwright.async_api import async_playwright
from urllib.parse import urljoin
from pyquery import PyQuery as pq
import time
import json
import re
import os
from motor.motor_asyncio import AsyncIOMotorClient
import logging

logging.basicConfig(level=logging.WARN, format='%(asctime)s - %(levelname)s: %(message)s')

# 推荐文档：https://www.cnblogs.com/aduner/p/13532504.html
# 定义MongoDB的连接字符串
MONGO_CONNECTION_STRING = 'mongodb://localhost:27017'
MONGO_DB_NAME = 'novel'
MONGO_COLLECTION_NAME = 'novel'

client = AsyncIOMotorClient(MONGO_CONNECTION_STRING)
db = client[MONGO_DB_NAME]
collection = db[MONGO_COLLECTION_NAME]

BASE_URL = 'http://www.qzxs.cc/'
NOVEL_URL = 'http://www.qzxs.cc/xiaoshuo/rbd2vo1/'
CHAPTER_URL = 'http://www.qzxs.cc/xiaoshuo/rbd2vo1/1.html'
BOOK_NAME = ''
BOOK_CHAPTER_COLLECTION_NAME = '章节链接'
BOOK_TEXT_COLLECTION_NAME = '文本'

# Setting
HEADLESS = True
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.90 Safari/537.36'
USERNAME = 'admin'
PASSWORD = 'admin'
COOKIE_FILE = 'cookies.json'

PAGE_NUM = 1
ACCESS_FAILED_URL = []

# 可通过信号量控制并发数
CONCURRENCY_INDEX_VALUE = 5
CONCURRENCY_DETAIL_VALUE = 10
CONCURRENCY_RETRY_VALUE = 10
sem_index = asyncio.Semaphore(CONCURRENCY_INDEX_VALUE)

'''
程序作用: 爬取指定页面,返回页面代码源文档
参数: page_obj (页面对象), url (爬取页面地址)
返回值: page_obj.content() (页面代码源文档)
'''
async def scrape_api(page_obj, url):
    # Images are not allowed to be loaded
    await page_obj.route(re.compile(r"(\.png)|(\.jpg)"), lambda route: route.abort())

    logging.info('Scraping %s...', url)
    try:
        await page_obj.goto(url)
        await page_obj.wait_for_load_state("networkidle")
        return await page_obj.content()
    except Exception as e:
        logging.error('error occurred while scraping %s', url, exc_info=True)

'''
程序作用: 完成网站模拟登录,并保存cookies
参数: page_obj (页面对象), url (爬取页面地址)
返回值: storage (登录后的cookies, 字典类型)
'''
async def simulate_login(url):
    async with async_playwright() as playwright:
        chromium = playwright.chromium
        browser = await chromium.launch(headless=HEADLESS)
        context = await browser.new_context()
        page = await context.new_page()
        try:
            logging.info('Start logging in %s...', url)
            await page.goto(url)
            await page.wait_for_load_state("networkidle")
            await page.locator('input[type="text"]').fill(USERNAME)
            await page.locator('input[type="password"]').fill(PASSWORD)
            await page.locator("form").get_by_role("button", name="登录").click()
            await page.wait_for_load_state("networkidle")
            username = page.get_by_text(USERNAME)
            await username.wait_for()
            # In order to obtain the token of JWT
            await page.reload()
            await page.wait_for_load_state("networkidle")
            # save storage_state to file
            storage = await context.storage_state(path=COOKIE_FILE)
            logging.info('Cookies is saved to %s: \n %s', COOKIE_FILE, storage)
            await page.close()
            await context.close()
            await browser.close()
            return storage
        except Exception as e:
            logging.error('error occurred while scraping %s', url, exc_info=True)

def parse_chapter_list(html):
    doc = pq(html)
    try:
        urls = []
        for item in doc('.listpage').items():
            option = item('option')
            for item in option.items():
                url = urljoin(BASE_URL, item.attr('value'))
                logging.info('Get chapter_list url %s', url)
                urls.append(url)
            break
        return urls
    except Exception as e:
        logging.error('Failed to parse the website', exc_info=True)
        return None

async def get_chapter_url():
    global BOOK_NAME
    async with async_playwright() as playwright:
        chromium = playwright.chromium
        browser = await chromium.launch(headless=HEADLESS)
        context = await browser.new_context(user_agent = USER_AGENT)
        page_obj = await context.new_page()

        
        html = await scrape_api(page_obj, CHAPTER_URL)
        doc = pq(html)
        # 获取书名
        name = doc('.booktitle h1').text()
        BOOK_NAME = name
        db = client[BOOK_NAME]
        collection_list = await db.list_collection_names()
        if BOOK_CHAPTER_COLLECTION_NAME in collection_list:
            logging.warning('The book chapter urls has already Saved')
            return
        else:
            collection = db[BOOK_CHAPTER_COLLECTION_NAME]

            # 获取章节列表的链接
            chapter_list_urls = []
            for item in doc('.listpage').items():
                option = item('option')
                for item in option.items():
                    url = urljoin(BASE_URL, item.attr('value'))
                    logging.info('Get chapter_list url %s', url)
                    chapter_list_urls.append(url)
                break

            # 按顺序获取每个章节的链接
            chapter_urls = []
            for chapter_list_url in chapter_list_urls:
                html = await scrape_api(page_obj, chapter_list_url)
                doc = pq(html)
                for item in doc('.chapterlist ul a').items():
                    href = re.search(r"href='(.*)'", item.attr('onclick')).group(1)
                    url = urljoin(BASE_URL, href)
                    logging.info('Get chapter url %s', url)
                    chapter_urls.append(url)
            logging.info('All chapter url is: \n %s', chapter_urls)
                
            await page_obj.close()
            await context.close()
            await browser.close()

            book_url = {
                'name': name,
                'chapter_urls': chapter_urls
            }
            if book_url:
                return await     collection.update_one({
                'name': book_url.get('name')
                }, {
                    '$set': book_url
                }, upsert=True
            )

def parse_chapter_text(index, html):
    doc = pq(html)
    title = doc('.read .booktitle h1').text()
    content = doc('.read .content p').text()
    logging.info('Chapter %d: %s \n %s', index, title, content)
    return {
        'index': index,
        'title': title,
        'content': content
    }

async def save_novel_text(data):
    # logging.info('Save data %s', data)
    global BOOK_NAME
    db = client[BOOK_NAME]
    collection = db[BOOK_TEXT_COLLECTION_NAME]

    if data:
        return await     collection.update_one({
        'index': data.get('index')
        }, {
            '$set': data
        }, upsert=True
    )

async def check_exist(index):
    global BOOK_NAME
    db = client[BOOK_NAME]
    collection = db[BOOK_TEXT_COLLECTION_NAME]
    result = await collection.count_documents({'index': index}) > 0
    return result

async def get_chapter_text(context, index, url, sem):
    if await check_exist(index):
        logging.info('novel text is exist')
        return
    else:
        async with sem:
            page_obj = await context.new_page()
            html = await scrape_api(page_obj, url)
            if html == None:
                logging.error('The website cannot be accessed: %s', url)
                ACCESS_FAILED_URL.append({
                    'index': index,
                    'url': url
                })
            else:
                data = parse_chapter_text(index, html)
                if data:
                    await save_novel_text(data)
            await page_obj.close()

async def get_chapter_info():
    global BOOK_NAME
    global ACCESS_FAILED_URL

    db = client[BOOK_NAME]
    collection = db[BOOK_CHAPTER_COLLECTION_NAME]

    sem_detail = asyncio.Semaphore(CONCURRENCY_DETAIL_VALUE)
    sem_retry = asyncio.Semaphore(CONCURRENCY_RETRY_VALUE)

    retry_cnt = 0

    chapter_urls = []
    async for document in collection.find({}):  # 查询所有文档
        if document.get('name') == BOOK_NAME:
            chapter_urls = document.get('chapter_urls')

    async with async_playwright() as playwright:
        chromium = playwright.chromium
        browser = await chromium.launch(headless=HEADLESS)
        context = await browser.new_context(user_agent = USER_AGENT)
        detail_scrape_task = [asyncio.create_task(get_chapter_text(context, id + 1, url, sem_detail)) for id, url in enumerate(chapter_urls)]
        done, pending = await asyncio.wait(detail_scrape_task, timeout=None)
        await context.close()
        await browser.close()

    while(ACCESS_FAILED_URL):
        retry_cnt += 1
        logging.warning('Start recrawling the information for the %s time', retry_cnt)
        async with async_playwright() as playwright:
            chromium = playwright.chromium
            browser = await chromium.launch(headless=HEADLESS)
            context = await browser.new_context(user_agent = USER_AGENT)
            retry_scrape_task = [asyncio.create_task(get_chapter_text(context, item.get('index'), item.get('url'), sem_retry)) for item in ACCESS_FAILED_URL]
            ACCESS_FAILED_URL = []
            done, pending = await asyncio.wait(retry_scrape_task, timeout=None)
            await context.close()
            await browser.close()

async def save_to_txt():
    global BOOK_NAME

    db = client[BOOK_NAME]
    collection = db[BOOK_TEXT_COLLECTION_NAME]

    cursor = collection.find({})
    cursor.sort('index', 1)

    with open(BOOK_NAME + ".txt", "w", encoding="utf-8") as file:
        async for document in cursor:
            file.write(document.get('content') + "\n\n")

async def main():
    # 获取小说章节链接并保存到mongodb
    await get_chapter_url()

    # 获取每个章节的内容并保存到mongodb
    await get_chapter_info()

    # 将小说内容拼接成txt文件
    await save_to_txt()



if __name__ == '__main__':
    start_time = time.time()
    asyncio.get_event_loop().run_until_complete(main())
    end_time = time.time()
    print('程序运行时间为:', end_time - start_time)
