import asyncio
from playwright.async_api import async_playwright
from urllib.parse import urljoin
from pyquery import PyQuery as pq
import time
import json
import re
from motor.motor_asyncio import AsyncIOMotorClient
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s: %(message)s')

# 定义MongoDB的连接字符串
MONGO_CONNECTION_STRING = 'mongodb://localhost:27017'
MONGO_DB_NAME = 'novel_0204'
MONGO_COLLECTION_NAME = 'novel_0204'

client = AsyncIOMotorClient(MONGO_CONNECTION_STRING)
db = client[MONGO_DB_NAME]
collection = db[MONGO_COLLECTION_NAME]

BASE_URL = 'https://www.qzsc.cc/'
# cat_name = {
#     'xuanhuanxiaoshuo/': '玄幻',
#     'xiuzhenxiaoshuo/': '修真',
#     'dushixiaoshuo/': '都市',
#     }
cat_name = {
    'xuanhuanxiaoshuo/': '玄幻'
    }

# Setting
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.90 Safari/537.36'
USERNAME = 'admin'
PASSWORD = 'admin'
COOKIE_FILE = 'cookies.json'

PAGE_NUM = 1
ACCESS_FAILED_URL = []

# 可通过信号量控制并发数
CONCURRENCY_INDEX_VALUE = 5
CONCURRENCY_DETAIL_VALUE = 10
sem_index = asyncio.Semaphore(CONCURRENCY_INDEX_VALUE)
sem_detail = asyncio.Semaphore(CONCURRENCY_DETAIL_VALUE)

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
        browser = await chromium.launch(headless=False)
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

'''
程序作用: 爬取指定页码,返回页面代码源文档
参数: context (浏览器上下文), url (爬取页面页码)
返回值: page_obj.content() (页面代码源文档)
'''
async def scrape_category(context, url):
    async with sem_index:
        page_obj = await context.new_page()
        html = await scrape_api(page_obj, url)
        await page_obj.close()
        return html

def parse_category(html):
    doc = pq(html)
    urls = []
    for item in doc('ul li .s2 a').items():
        url = urljoin(BASE_URL, item.attr('href'))
        logging.info('Get detail url %s', url)
        urls.append(url)
    return urls

async def scrape_detail(context, url):
    async with sem_detail:
        page_obj = await context.new_page()
        html = await scrape_api(page_obj, url)
        await page_obj.close()
        return html

def parse_detail(html):
    doc = pq(html)   # 将源代码初始化为PyQuery对象
    try:
        name = doc('#info h1').text()
        author = doc('#info p').text()
        author = re.search(r'者：(.*)', doc('#info p:contains(者：)').text()).group(1)
        last_update = re.search(r'更新：(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', doc('#info p:contains(更新：)').text()).group(1)
        brief = doc('#intro p').text()
        chapters = doc('.box_con #list a')
        chapter_info = []
        for chapter in chapters.items():
            url = urljoin(BASE_URL, chapter.attr('href'))
            title = chapter.text()
            chapter_info.append({
                'url': url,
                'title': title
            })
        return {
            'name': name,
            'author': author,
            'last_update': last_update,
            'brief': brief,
            'chapter_info': chapter_info
        }
    except Exception as e:
        logging.info('Failed to parse the website', exc_info=True)
        return None

'''
程序作用: 保存数据到mongodb
参数: data (数据)
返回值: 无
'''
async def save_data(data):
    logging.info('Save data %s', data)
    if data:
        return await     collection.update_one({
        'name': data.get('name')
        }, {
            '$set': data
        }, upsert=True
    )

async def process_detail(context, url):
    html = await scrape_detail(context, url)
    if html == None:
        logging.info('The website cannot be accessed: %s', url)
        ACCESS_FAILED_URL.append[url]
    else:
        data = parse_detail(html)
        if data:
            await save_data(data)


async def process_category(context, category):
    url = urljoin(BASE_URL, category)
    html = await scrape_category(context, url)
    # print(html)
    updated_novel_urls = parse_category(html)
    logging.info('%s 分类页抓取完毕', cat_name[category])
    detail_scrape_task = [asyncio.create_task(process_detail(context, url)) for url in updated_novel_urls]
    done, pending = await asyncio.wait(detail_scrape_task, timeout=None)

async def main():
    # await simulate_login(BASE_URL)

    async with async_playwright() as playwright:
        chromium = playwright.chromium
        browser = await chromium.launch(headless=False)
        context_category = await browser.new_context(user_agent = USER_AGENT)
        category_scrape_task = [asyncio.create_task(process_category(context_category, key)) 
                             for key, value in cat_name.items()]
        done, pending = await asyncio.wait(category_scrape_task, timeout=None)
        await context_category.close()
        await browser.close()

if __name__ == '__main__':
    start_time = time.time()
    asyncio.run(main())
    end_time = time.time()
    print('程序运行时间为:', end_time - start_time)
