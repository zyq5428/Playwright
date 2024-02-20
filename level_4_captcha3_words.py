from playwright.async_api import async_playwright
from motor.motor_asyncio import AsyncIOMotorClient
from pyquery import PyQuery as pq
from urllib.parse import urljoin
from hashlib import md5
from PIL import Image
import requests
import asyncio
import random
import time
import json
import re
import os
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s: %(message)s')

BASE_URL = 'https://captcha3.scrape.center/'

# Setting
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/105.0.0.0 Safari/537.36 Edg/105.0.1343.42'
USERNAME = 'admin'
PASSWORD = 'admin'
COOKIE_FILE = 'cookies.json'
LOGGED_LABEL = '登录成功'

# CJ_USERNAME = '******'
# CJ_PASSWORD = '******'
# SOFT_ID = '******'
SCREENSHOT_FILE = 'website.png'
CAPTCHA_FILE = 'captcha.png'
GET_CAPTCHA_POSITION = False
PIC_ID = ''

PAGE_NUM = 10
DETAIL_URL = []

# 可通过信号量控制并发数
CONCURRENCY_INDEX_VALUE = 10
CONCURRENCY_DETAIL_VALUE = 10
sem_index = asyncio.Semaphore(CONCURRENCY_INDEX_VALUE)
sem_detail = asyncio.Semaphore(CONCURRENCY_DETAIL_VALUE)

class Chaojiying_Client(object):

    def __init__(self, username, password, soft_id):
        self.username = username
        password =  password.encode('utf8')
        self.password = md5(password).hexdigest()
        self.soft_id = soft_id
        self.base_params = {
            'user': self.username,
            'pass2': self.password,
            'softid': self.soft_id,
        }
        self.headers = {
            'Connection': 'Keep-Alive',
            'User-Agent': 'Mozilla/4.0 (compatible; MSIE 8.0; Windows NT 5.1; Trident/4.0)',
        }

    def PostPic(self, im, codetype):
        """
        im: 图片字节
        codetype: 题目类型 参考 http://www.chaojiying.com/price.html
        """
        params = {
            'codetype': codetype,
        }
        params.update(self.base_params)
        files = {'userfile': ('ccc.png', im)}
        r = requests.post('http://upload.chaojiying.net/Upload/Processing.php', data=params, files=files, headers=self.headers)
        return r.json()

    def PostPic_base64(self, base64_str, codetype):
        """
        im: 图片字节
        codetype: 题目类型 参考 http://www.chaojiying.com/price.html
        """
        params = {
            'codetype': codetype,
            'file_base64':base64_str
        }
        params.update(self.base_params)
        r = requests.post('http://upload.chaojiying.net/Upload/Processing.php', data=params, headers=self.headers)
        return r.json()

    def ReportError(self, im_id):
        """
        im_id:报错题目的图片ID
        """
        params = {
            'id': im_id,
        }
        params.update(self.base_params)
        r = requests.post('http://upload.chaojiying.net/Upload/ReportError.php', data=params, headers=self.headers)
        return r.json()

'''
程序作用:截取浏览器截屏中的验证码部分
参数: position
返回值: 无
'''
def get_captcha_image(position):
    x = position.get('x')
    y = position.get('y')
    width = position.get('width')
    height = position.get('height')
    box = (x, y, x + width, y + height)
    logging.info('Captcha box: %s', box)
    with Image.open(SCREENSHOT_FILE) as im:
        im_crop = im.crop(box)
        im_crop.save(CAPTCHA_FILE)

'''
程序作用: 通过chaojiying的接口获取验证码的位置
参数: 无
返回值: 无
'''
def get_relative_positions():
    with open(CAPTCHA_FILE, 'rb') as f:
        img = f.read()
        chaojiying = Chaojiying_Client(CJ_USERNAME, CJ_PASSWORD, SOFT_ID)
        cjy_response = chaojiying.PostPic(img, 9004)
        if cjy_response['err_no'] == 0:
            GET_CAPTCHA_POSITION = True
            PIC_ID = cjy_response['pic_id']
            pic_str = cjy_response['pic_str']
            positions = re.split(r'\|', pic_str)
            pos = []
            for position in positions:
                x = int(position.split(',')[0])
                y = int(position.split(',')[1])
                pos.append({
                    'x': x,
                    'y': y,
                })
            logging.info('Get captcha positions: %s', pos)
            return pos
        
def report_error_id():
    chaojiying = Chaojiying_Client(CJ_USERNAME, CJ_PASSWORD, SOFT_ID)
    logging.info('Report error picture id: %s', PIC_ID)
    cjy_response = chaojiying.ReportError(PIC_ID)
    logging.info('Report error response: %s', cjy_response)

'''
程序作用: 获得验证码在网页中的位置
参数: 无
返回值: 无
'''
def get_absolute_positions(base_pos, rel_pos):
    x = base_pos.get('x')
    y = base_pos.get('y')
    for position in rel_pos:
        position['x'] = x + position.get('x')
        position['y'] = x + position.get('y')
    return rel_pos

async def sleep_ms_rand(lower, upper):
    ms = random.randint(lower, upper)
    await asyncio.sleep(ms / 1000)

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
            await page.locator('button[type="button"]').click()
            await page.wait_for_load_state("networkidle")
            await page.locator('.geetest_panel_next').wait_for()
            await page.screenshot(path = SCREENSHOT_FILE)
            captcha_position = await page.locator('.geetest_widget').bounding_box()
            get_captcha_image(captcha_position)
            relative_positions = get_relative_positions()
            absolute_positions = get_absolute_positions(captcha_position, relative_positions)
            for absolute_positon in absolute_positions:
                logging.info('Click %s', absolute_positon)
                await page.mouse.click(absolute_positon.get('x'), absolute_positon.get('y'))
                await sleep_ms_rand(200, 500)
            commit_tip = page.locator('.geetest_commit_tip')
            await commit_tip.wait_for()
            await commit_tip.click()
            await page.wait_for_load_state("networkidle")
            username = page.get_by_text(LOGGED_LABEL)
            await username.wait_for()
            # In order to obtain the token of JWT
            await page.reload()
            await page.wait_for_load_state("networkidle")
            # save storage_state to file
            storage = await context.storage_state(path=COOKIE_FILE)
            logging.info('Cookies is saved to %s: \n %s', COOKIE_FILE, storage)
            # await page.screenshot(path = SCREENSHOT_FILE)
            await page.close()
            await context.close()
            await browser.close()
        except Exception as e:
            logging.error('error occurred while scraping %s', url, exc_info=True)
            if GET_CAPTCHA_POSITION == True: 
                report_error_id()


async def main():
    await simulate_login(BASE_URL)

if __name__ == '__main__':
    chaojiying = Chaojiying_Client(CJ_USERNAME, CJ_PASSWORD, SOFT_ID)	#用户中心>>软件ID 生成一个替换
    im = open(CAPTCHA_FILE, 'rb').read()	
    print (chaojiying.PostPic(im, 9004))
    # start_time = time.time()
    # asyncio.run(main())
    # end_time = time.time()
    # print('程序运行时间为: {:5.2f}'.format(end_time - start_time))
