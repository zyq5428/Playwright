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

BASE_URL = 'https://antispider7.scrape.center/'
LOGIN_URL = 'https://antispider7.scrape.center/login'
PAGE_NUM = 5

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
    # async def choose_proxy(self, cur_proxy=None):
    #     async with self.proxy_lock:
    #         if len(self.proxy_list) == 0:
    #             if self.proxy.get_proxy():
    #                 self.proxy_list = self.proxy.ip
    #                 logging.info('New proxy list: \n%s', self.proxy_list)
    #         self.proxy_server = self.proxy_list[-1]
    #         self.proxy_list = self.proxy_list[0:-1]
    #         logging.info('Choose proxy: %s', self.proxy_server)

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
    程序作用: 完成网站模拟登录, 并保存cookies
    参数: page_obj (页面对象), url (爬取页面地址)
    返回值: storage (登录后的cookies, 字典类型)
    '''
    async def parse_login(self, login_url, cookie_url, username, password):
        logging.info('Acquire login lock')
        async with self.login_lock:
            if os.path.exists(self.username) == False:
                async with async_playwright() as playwright:
                    chromium = playwright.chromium
                    browser = await chromium.launch(headless=False)
                    context = await browser.new_context()
                    page = await context.new_page()
                    try:
                        logging.info('Start use %s logging in %s...', username, login_url)
                        await page.add_init_script(self.js)
                        await page.goto(login_url)
                        await page.wait_for_load_state("networkidle")
                        await page.locator('input[type="text"]').fill(username)
                        await page.locator('input[type="password"]').fill(password)
                        await page.locator("form").get_by_role("button", name="登录").click()
                        await page.wait_for_load_state("networkidle")
                        user = page.get_by_text(username)
                        await user.wait_for()
                        # In order to obtain the token of JWT
                        await page.goto(cookie_url)
                        await page.wait_for_load_state("networkidle")
                        # save storage_state to file
                        storage = await context.storage_state(path=username)
                        logging.info('Cookies is saved to %s: \n%s', username, storage)
                        await page.close()
                        await context.close()
                        await browser.close()
                        return storage
                    except Exception as e:
                        logging.error('error occurred while scraping %s', login_url, exc_info=True)

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
    async def scrape_index(self, browser, page_id):
        async with self.sem_page:
            # context = await browser.new_context(proxy={'server': PROXY_SERVER}) # linux下使用才生效
            context = await browser.new_context(storage_state=self.username)
            index_url = f'{BASE_URL}page/{page_id}'
            page_obj = await context.new_page()
            html = await self.scrape_api(page_obj, index_url)
            await page_obj.close()
            await context.close()
            return html

    '''
    程序作用: 解析网页文本，拼接出详情页网址
    参数: html (页面文本)
    返回值: url (详情页网址)
    '''
    def parse_index(self, html):
        doc = pq(html)
        with open('index.html', 'w', encoding='utf-8') as f:
            f.write(html)
        for item in doc('#index .el-row .el-col-4').items():
            url = urljoin(BASE_URL, item('.bottom a').attr('href'))
            logging.debug('Get detail url %s', url)
            self.detail_urls.append(url)

    '''
    程序作用: 列表页处理线程
    参数: browser (浏览器实例), page_id (待爬取页面页码)
    返回值: url (详情页网址)
    '''
    async def process_index(self, browser, page_id):
        html = await self.scrape_index(browser, page_id)
        self.parse_index(html)
        logging.info('第%d页列表抓取完毕', page_id)

    '''
    程序作用: 爬取指定网址, 返回页面代码源文档
    参数: browser (浏览器实例), url (待爬取网址)
    返回值: page_obj.content() (页面代码源文档)
    '''
    async def scrape_detail(self, browser, url):
        async with self.sem_page:
            if os.path.exists(self.username) == False:
                await asyncio.sleep(30)
            context = await browser.new_context(
                storage_state=self.username,
                proxy={'server': self.proxy_server}
                )
            page_obj = await context.new_page()
            html = await self.scrape_api(page_obj, url)
            await page_obj.close()
            await context.close()
            return html

    '''
    程序作用: 解析网页文本，提取页面信息
    参数: html (页面文本)
    返回值: item (详情页信息,字典格式)
    '''
    async def parse_detail(self, html, url):
        doc = pq(html)
        username = doc('.login .logout').text()
        username = re.search(r'(\b.*\b)', username).group(1)
        if '403 Forbidden.' == doc('.m-t.el-row div.el-card__body h2').text():
            logging.error('403 Forbidden, Current user is: %s', username)
            if username == self.username:
                await self.choose_user(username)
            else:
                await asyncio.sleep(10)
            if os.path.exists(self.username):
                logging.info('cookie file is exists: %s', self.username)
            else:
                logging.info('Nend login new user: %s', self.username)
                await self.parse_login(LOGIN_URL, BASE_URL, self.username, self.password)
            return None, username
        else:
            try:
                item = {}
                score = doc('.score').text()
                item['score'] = float(score) if score else None
                item['name'] = doc('h2.name').text()
                item['tags'] = [item.text() for item in doc('.tags span').items()]
                price = doc('.info .price span').text()
                if price and re.search(r'\d+(\.\d*)?', price):
                    item['price'] = float(re.search(r'\d+(\.\d*)?', price).group())
                item['authors'] = re.search(r'作者：(.*)', doc('.info .authors').text()).group(1) \
                    if doc('.info .authors').text() else None
                item['published_at'] = re.search(r'(\d{4}-\d{2}-\d{2})', doc('.info .published-at').text()).group(1) \
                    if doc('.info .published-at').text() else None
                item['isbm'] = re.search(r'ISBN：(.*)', doc('.info .isbn').text()).group(1) \
                    if doc('.info .isbn').text() else None
                item['cover'] = doc('img.cover').attr('src')
                item['comments'] = [item.text() for item in doc('.comments p').items()]
                logging.debug('item: %s', item)
                return item, username
            except Exception as e:
                logging.error('parse detail html failed', exc_info=True)

    '''
    程序作用: 保存数据到mongodb
    参数: data (数据)
    返回值: 无
    '''
    async def save_data(self, data):
        logging.info('Save data %s', data)
        if data:
            return await self.collection.update_one(
                {
                    'name': data.get('name')
                }, 
                {
                    '$set': data
                }, 
                upsert=True
        )

    '''
    程序作用: 详情页处理线程
    参数: browser (浏览器实例), url (待爬取网址)
    返回值: url (详情页网址)
    '''
    async def process_detail(self, browser, url):
        html = await self.scrape_detail(browser, url)
        data, user = await self.parse_detail(html, url)
        if data == None:
            detail_scrape_task = asyncio.create_task(self.process_detail(browser, url))
            await detail_scrape_task
        else:
            await self.save_data(data)

async def main():
    spider = AntiuserSpider(ACCOUNT, download_delay = 1000)
    await spider.choose_user()
    await spider.choose_proxy()
    await spider.parse_login(LOGIN_URL, BASE_URL, spider.username, spider.password)

    async with async_playwright() as playwright:
        chromium = playwright.chromium
        browser = await chromium.launch(headless=False)
        index_scrape_tasks = [asyncio.create_task(spider.process_index(browser, page_id)) 
                             for page_id in range(1, PAGE_NUM + 1)]
        done, pending = await asyncio.wait(index_scrape_tasks, timeout=None)
        logging.debug('detail url: \n%s', spider.detail_urls)
        await browser.close()

    async with async_playwright() as playwright:
        chromium = playwright.chromium
        browser = await chromium.launch(headless=False)
        detail_scrape_tasks = [asyncio.create_task(spider.process_detail(browser, url)) 
                              for url in spider.detail_urls]
        done, pending = await asyncio.wait(detail_scrape_tasks, timeout=None)
        await browser.close()

if __name__ == '__main__':
    start_time = time.time()
    asyncio.run(main())
    end_time = time.time()
    print('程序运行时间为:', end_time - start_time)
