import asyncio
from playwright.async_api import async_playwright
from urllib.parse import urljoin
from pyquery import PyQuery as pq
import time
import json
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s: %(message)s')

BASE_URL = 'https://ssr1.scrape.center/'
PAGE_NUM = 2
DETAIL_URL = []

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
程序作用: 爬取指定页码,返回页面代码源文档
参数: context (浏览器上下文), url (爬取页面页码)
返回值: page_obj.content() (页面代码源文档)
'''
async def scrape_index(context, page_id):
    async with sem_index:
        index_url = f'{BASE_URL}page/{page_id}'
        page_obj = await context.new_page()
        html = await scrape_api(page_obj, index_url)
        await page_obj.close()
        return html

async def parse_index(html):
    doc = pq(html)
    for item in doc('.el-card .name').items():
        url = urljoin(BASE_URL, item.attr('href'))
        logging.info('Get detail url %s', url)
        DETAIL_URL.append(url)

async def process_index(context, page_id):
    html = await scrape_index(context, page_id)
    await parse_index(html)
    logging.info('第%d页抓取完毕', page_id)

async def scrape_detail(context, url):
    async with sem_detail:
        page_obj = await context.new_page()
        html = await scrape_api(page_obj, url)
        await page_obj.close()
        return html

async def parse_detail(html):
    doc = pq(html)
    name = doc('.m-b-sm').text()
    categories = [item.text() for item in doc('.categories button span').items()]
    drama = doc('.drama p').text()
    return {
        'name': name,
        'categories': categories,
        'drama': drama
    }

async def process_detail(context, url):
    html = await scrape_detail(context, url)
    data = await parse_detail(html)
    logging.info('Get detail data %s', data)

async def main():
    async with async_playwright() as playwright:
        chromium = playwright.chromium
        browser = await chromium.launch(headless=False)
        context_index = await browser.new_context()
        index_scrape_task = [asyncio.create_task(process_index(context_index, page_id)) 
                             for page_id in range(1, PAGE_NUM + 1)]
        done, pending = await asyncio.wait(index_scrape_task, timeout=None)
        print(DETAIL_URL)
        await context_index.close()
        await browser.close()
    async with async_playwright() as playwright:
        chromium = playwright.chromium
        browser = await chromium.launch(headless=False)
        context_detail = await browser.new_context()
        detail_scrape_task = [asyncio.create_task(process_detail(context_detail, url)) 
                              for url in DETAIL_URL]
        done, pending = await asyncio.wait(detail_scrape_task, timeout=None)
        await context_detail.close()
        await browser.close()

if __name__ == '__main__':
    start_time = time.time()
    asyncio.run(main())
    end_time = time.time()
    print('程序运行时间为:', end_time - start_time)
