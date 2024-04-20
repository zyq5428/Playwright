import asyncio
import threading
import sys
import os
from playwright.async_api import async_playwright
from urllib.parse import urljoin
from pyquery import PyQuery as pq
import time
import random
import json
import re
from motor.motor_asyncio import AsyncIOMotorClient
import logging
from zmhttp import ip_proxy

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s: %(message)s')

TEST_URL = 'https://httpbin.org/get'
BASE_URL = 'https://antispider7.scrape.center/'
LOGIN_URL = 'https://antispider7.scrape.center/login'
PAGE_NUM = 1

ACCOUNT = [
    ['herozhou1', 'asdfgh'], ['herozhou2', 'asdfgh'], ['herozhou3', 'asdfgh'], 
    ['herozhou4', 'asdfgh'], ['herozhou5', 'asdfgh'], ['herozhou6', 'asdfgh'], 
    ['herozhou7', 'asdfgh'], ['herozhou8', 'asdfgh'], ['herozhou9', 'asdfgh'], 
    ['herozhou10', 'asdfgh'], ['herozhou11', 'asdfgh'], ['herozhou12', 'asdfgh'], 
    ['herozhou13', 'asdfgh'], ['herozhou14', 'asdfgh'], ['herozhou15', 'asdfgh'], 
    ['herozhou16', 'asdfgh'], ['herozhou17', 'asdfgh'], ['herozhou18', 'asdfgh'], 
]

ERROR_STR = '403 Forbidden.'

Direct_IP = 'http://webapi.http.zhimacangku.com/getip?neek=860483b89fc4d67d&num=10&type=2&time=4&pro=0&city=0&yys=0&port=11&pack=0&ts=1&ys=1&cs=1&lb=1&sb=&pb=4&mr=3&regions='

'''
思路一: 出现爬取失败时，保存爬取失败的链接，关闭当前页面，切换新账户后登录，适用于爬取限制没那么严厉的网站。
思路而: 使用多个账户同时爬取，每个账户每次爬取的链接数较少，然后设置随机的爬取间隔，这样避免触发网站反爬。
'''

class AntiuserSpider:
    name = 'antiuser'
    # 定义MongoDB的连接字符串
    MONGO_CONNECTION_STRING = 'mongodb://localhost:27017'
    MONGO_DB_NAME = 'antiuser'
    MONGO_COLLECTION_NAME = 'book'
    # Bypass Webdriver detection
    js = """
    Object.defineProperties(navigator, {webdriver:{get:()=>undefined}});
    """
    # User-Agent
    User_Agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36'

    def __init__(self, account, concurrency=10, download_delay=0):
        # init mongodb
        self.client = AsyncIOMotorClient(self.MONGO_CONNECTION_STRING)
        self.db = self.client[self.MONGO_DB_NAME]
        self.collection = self.db[self.MONGO_COLLECTION_NAME]
        # init user
        self.account = account
        self.username = ''
        self.password = ''
        # init proxy
        self.proxy = ip_proxy(Direct_IP)
        self.proxy_list = []
        self.proxy_server = ''
        # init Semaphore and lock
        self.sem_page = asyncio.Semaphore(concurrency)
        self.user_lock = asyncio.Lock()
        self.proxy_lock = asyncio.Lock()
        self.login_lock = asyncio.Lock()
        # detail url list
        self.detail_urls = []
        self.download_delay_L = int(0.5 *download_delay)
        self.download_delay_H = int(1.5 *download_delay)

    '''
    程序作用: 选择新账户
    参数: cur_user (当前用户)
    返回值: 无
    '''
    async def choose_user(self, cur_user=None):
        async with self.user_lock:
            if cur_user == self.username or cur_user == None:
                if len(self.account) == 0:
                    logging.error('Account resources have been depleted!')
                    sys.exit(1)
                self.username = self.account[-1][0]
                self.password = self.account[-1][1]
                self.account = self.account[0:-1]
                logging.info('Choose user: %s, pwd: %s', self.username, self.password)
                await self.choose_proxy()

    '''
    程序作用: 选择新代理
    参数: cur_proxy (当前代理)
    返回值: 无
    '''
    async def choose_proxy(self, cur_proxy=None):
        async with self.proxy_lock:
            if self.proxy.get_proxy():
                self.proxy_list = self.proxy.ip
                logging.info('New proxy list: \n%s', self.proxy_list)
            self.proxy_server = self.proxy_list[-1]
            self.proxy_list = self.proxy_list[0:-1]
            logging.info('Choose proxy: %s', self.proxy_server)

    '''
    程序作用: 爬取指定页面, 返回页面代码源文档
    参数: page_obj (页面对象), url (爬取页面地址)
    返回值: page_obj.content() (页面代码源文档)
    '''
    async def scrape_api(self, page_obj, url):
        try:
            # Randomly wait for request(millisecond)
            await page_obj.wait_for_timeout(random.randint(self.download_delay_L, self.download_delay_H))
            # Bypass Webdriver detection
            await page_obj.add_init_script(self.js)
            # Images are not allowed to be loaded
            await page_obj.route(re.compile(r"(\.png)|(\.jpg)"), lambda route: route.abort())
            logging.info('Scraping %s...', url)
            await page_obj.goto(url)
            await page_obj.wait_for_load_state("networkidle")
            return await page_obj.content()
        except Exception as e:
            logging.error('error occurred while scraping %s', url, exc_info=True)
            return None

    '''
    程序作用: 爬取指定页码, 返回页面代码源文档
    参数: browser (浏览器实例), page_id (待爬取页面页码)
    返回值: page_obj.content() (页面代码源文档)
    '''
    async def scrape_index(self, browser, proxy_server):
        async with self.sem_page:
            proxy_list = self.proxy.get_proxy()
            if proxy_list:
                proxy_server = proxy_list[-1]
                logging.info('Choose proxy: %s', proxy_server)
            context = await browser.new_context(
                user_agent= self.User_Agent,
                proxy={'server': proxy_server}
                )
            page_obj = await context.new_page()
            html = await self.scrape_api(page_obj, TEST_URL)
            await page_obj.close()
            await context.close()
            return html

    '''
    程序作用: 解析网页文本，拼接出详情页网址
    参数: html (页面文本)
    返回值: url (详情页网址)
    '''
    def parse_index(self, proxy_server, html):
        logging.info('proxy: %s, html: \n%s', proxy_server, html)
        # doc = pq(html)
        # for item in doc('#index .el-row .el-col-4').items():
        #     url = urljoin(BASE_URL, item('.bottom a').attr('href'))
        #     logging.debug('Get detail url %s', url)
        #     self.detail_urls.append(url)

    '''
    程序作用: 列表页处理线程
    参数: browser (浏览器实例), page_id (待爬取页面页码)
    返回值: url (详情页网址)
    '''
    async def process_index(self, browser, page_id):
        await asyncio.sleep(page_id)
        proxy_server = ''
        html = await self.scrape_index(browser, proxy_server)
        self.parse_index(proxy_server, html)
        logging.info('第%d页列表抓取完毕', page_id)

async def main():
    spider = AntiuserSpider(ACCOUNT)

    async with async_playwright() as playwright:
        chromium = playwright.chromium
        browser = await chromium.launch(headless=False)
        index_scrape_tasks = [asyncio.create_task(spider.process_index(browser, page_id)) 
                             for page_id in range(1, PAGE_NUM + 1)]
        done, pending = await asyncio.wait(index_scrape_tasks, timeout=None)
        await browser.close()


if __name__ == '__main__':
    start_time = time.time()
    asyncio.run(main())
    end_time = time.time()
    print('程序运行时间为:', end_time - start_time)
