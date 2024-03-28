import asyncio
from playwright.async_api import async_playwright
from urllib.parse import urljoin
from pyquery import PyQuery as pq
import time
import json
import re
from motor.motor_asyncio import AsyncIOMotorClient
import logging
from zmhttp import ip_proxy

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s: %(message)s')

# 定义MongoDB的连接字符串
MONGO_CONNECTION_STRING = 'mongodb://localhost:27017'
MONGO_DB_NAME = 'movies0202'
MONGO_COLLECTION_NAME = 'movies0202'

client = AsyncIOMotorClient(MONGO_CONNECTION_STRING)
db = client[MONGO_DB_NAME]
collection = db[MONGO_COLLECTION_NAME]

BASE_URL = 'https://antispider5.scrape.center/'
USERNAME = 'admin'
PASSWORD = 'admin'
COOKIE_FILE = 'cookies.json'

PROXY_LIST = []
PROXY_SERVER = ''
Direct_IP = 'http://webapi.http.zhimacangku.com/getip?neek=860483b89fc4d67d&num=10&type=2&pro=&city=0&yys=0&port=11&time=4&ts=1&ys=1&cs=1&lb=1&sb=0&pb=4&mr=1&regions='
proxy = ip_proxy(Direct_IP)

PAGE_NUM = 10
DETAIL_URL = []

user_error = '403 Forbidden'

# 可通过信号量控制并发数
CONCURRENCY_INDEX_VALUE = 10
CONCURRENCY_DETAIL_VALUE = 10
sem_index = asyncio.Semaphore(CONCURRENCY_INDEX_VALUE)
sem_detail = asyncio.Semaphore(CONCURRENCY_DETAIL_VALUE)

'''
程序作用: 爬取指定页面,返回页面代码源文档
参数: page_obj (页面对象), url (爬取页面地址)
返回值: page_obj.content() (页面代码源文档)
'''
async def scrape_api(page_obj, url):
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

def set_proxy():
    global proxy
    global PROXY_LIST
    global PROXY_SERVER
    if len(PROXY_LIST) == 0:
        if proxy.get_proxy():
            PROXY_LIST = proxy.ip
            logging.info(PROXY_LIST)
    PROXY_SERVER = PROXY_LIST[-1]
    PROXY_LIST = PROXY_LIST[0:-1]

'''
程序作用: 爬取指定页码,返回页面代码源文档
参数: context (浏览器上下文), url (爬取页面页码)
返回值: page_obj.content() (页面代码源文档)
'''
async def scrape_index(browser, page_id):
    async with sem_index:
        context = await browser.new_context(
            proxy={'server': PROXY_SERVER}
            ) # linux下使用才生效
        index_url = f'{BASE_URL}page/{page_id}'
        page_obj = await context.new_page()
        html = await scrape_api(page_obj, index_url)
        await page_obj.close()
        await context.close()
        return html

# async def scrape_index(browser, page_id):
#     async with sem_index:
#         context = await browser.new_context(
#             proxy={'server': PROXY_SERVER}
#             )
#         page_obj = await context.new_page()
#         html = await scrape_api(page_obj, "https://httpbin.org/get")
#         # origin = json.loads(html)['origin']
#         origin = re.search(r'"origin": "(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', html).group(1)
#         logging.info('origin IP is %s', origin)
#         await page_obj.close()
#         await context.close()
#         return html

def parse_index(html):
    doc = pq(html)
    for item in doc('.el-card .name').items():
        url = urljoin(BASE_URL, item.attr('href'))
        logging.info('Get detail url %s', url)
        DETAIL_URL.append(url)

async def process_index(browser, page_id):
    html = await scrape_index(browser, page_id)
    parse_index(html)
    logging.info('第%d页抓取完毕', page_id)

async def scrape_detail(context, url):
    async with sem_detail:
        page_obj = await context.new_page()
        html = await scrape_api(page_obj, url)
        await page_obj.close()
        return html

def parse_detail(html):
    doc = pq(html)   # 将源代码初始化为PyQuery对象
    cover = doc('img.cover').attr('src')
    name = doc('a > h2').text()
    categories = [item.text() for item in doc('.categories button span').items()]
    published_at = doc('.info:contains(上映)').text()
    published_at = re.search(r'\d{4}-\d{2}-\d{2}', published_at).group(0) \
        if published_at and re.search(r'\d{4}-\d{2}-\d{2}', published_at) else None
    drama = doc('.drama p').text()
    score = doc('.score').text()
    score = float(score) if score else None
    return {
        'cover': cover,
        'name': name,
        'categories': categories,
        'published_at': published_at,
        'drama': drama,
        'score': score
    }

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
    data = parse_detail(html)
    await save_data(data)

async def main():
    # await simulate_login(BASE_URL)

    async with async_playwright() as playwright:
        chromium = playwright.chromium
        browser = await chromium.launch(headless=False)
        index_scrape_task = [asyncio.create_task(process_index(browser, page_id)) 
                             for page_id in range(1, PAGE_NUM + 1)]
        done, pending = await asyncio.wait(index_scrape_task, timeout=None)
        print(DETAIL_URL)
        await browser.close()

    # async with async_playwright() as playwright:
    #     chromium = playwright.chromium
    #     browser = await chromium.launch(headless=False)
    #     context_detail = await browser.new_context(storage_state=COOKIE_FILE)
    #     detail_scrape_task = [asyncio.create_task(process_detail(context_detail, url)) 
    #                           for url in DETAIL_URL]
    #     done, pending = await asyncio.wait(detail_scrape_task, timeout=None)
    #     await context_detail.close()
    #     await browser.close()

if __name__ == '__main__':
    start_time = time.time()
    set_proxy()
    asyncio.run(main())
    end_time = time.time()
    print('程序运行时间为:', end_time - start_time)
