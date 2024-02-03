# Playwright常用对象说明

## Browser
    对应一个浏览器实例(Chromium、Firefox或WebKit),Playwright脚本以启动浏览器实例开始,以关闭浏览器结束。浏览器实例可以在headless或者 headful模式下启动。一个 Browser 可以包含多个 BrowserContext。

## BrowserContext
    Playwright为每个测试创建一个浏览器上下文,即BrowserContext,浏览器上下文相当于一个全新的浏览器配置文件,提供了完全的测试隔离,并且零开销。创建一个新的浏览器上下文只需要几毫秒,每个上下文都有自己的Cookie、浏览器存储和浏览历史记录。浏览器上下文允许同时打开多个页面并与之交互,每个页面都有自己单独的状态,一个 BrowserContext 可以包含多个 Page。

## Page
    页面指的是浏览器上下文中的单个选项卡或弹出窗口。在Page中主要完成与页面元素交互,一个 Page 可以包含多个 Frame

## Frame
    每个页面有一个主框架(page.MainFrame()),也可以有多个子框架,由 iframe 标签创建产生。在playwright中,无需切换iframe,可以直接定位元素(这点要比selenium方便很多)。

## 登录认证

### HTTP基本认证(HTTP Basic Authentication)

    RFC 7235 定义了一个 HTTP 身份验证框架，服务器可以用来质询（challenge）客户端的请求，客户端则可以提供身份验证凭据。
    通过设置context的http_credentials即可：
```  {python .line-numbers highlight=[1]}
context = await browser.new_context(
    http_credentials={
        'username': 'admin',
        'password': 'admin'
    }
)
```

### 模拟登录

    直接参考以下代码即可：
```  {python .line-numbers highlight=[11, 12, 13]}
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
            await page.locator('input[name="username"]').fill(USERNAME)
            await page.locator('input[name="password"]').fill(PASSWORD)
            await page.locator('input[type="submit"]').click()
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
)
```

### 保存和加载cookies

    Playwright 提供了一种在测试中重用登录状态的方法。这样您就可以只登录一次，然后跳过所有测试的登录步骤。
    Web 应用程序使用基于 cookie 或基于令牌的身份验证，其中经过身份验证的状态存储为cookie或本地存储。Playwright 提供browserContext.storageState([options])方法，可用于从经过身份验证的上下文中检索存储状态，然后创建具有预填充状态的新上下文。
    Cookie 和本地存储状态可以跨不同的浏览器使用。它们取决于您的应用程序的身份验证模型：某些应用程序可能需要 cookie 和本地存储。
    采用以下方式就可以实现保存和加载cookies：
```  {python .line-numbers highlight=[2， 4]}
# 保存storage state 到指定的文件
storage = await context.storage_state(path="state.json")
# 加载storage state 到指定的文件
context_index = await browser.new_context(storage_state="state.json")
```

### JWT(JSON Web Token)的登录验证

#### 什么是JWT（what）

* JWT(JSON Web Token)是一个开放标准(RFC 7519)，它定义了一种紧凑且自包含的方式，以JSON对象的形式在各方之间安全地传输信息。
* JWT是一个数字签名，生成的信息是可以验证并被信任的。
* 使用密钥(使用HMAC算法)或使用RSA或ECDSA的公钥/私钥对JWT进行签名。
* JWT是目前最流行的跨域认证解决方案
* 
#### JWT令牌结构

* SON Web令牌以紧凑的形式由三部分组成，这些部分由点（.）分隔，分别是：
  * Header
  * Payload
  * Signature

#### requests进行JWT的保存和加载

    可使用下面的示例进行：
```  {python .line-numbers highlight=[21]}
import requests
from urllib.parse import urljoin

BASE_URL = 'https://login3.scrape.center/'
LOGIN_URL = urljoin(BASE_URL, '/api/login')
INDEX_URL = urljoin(BASE_URL, '/api/book')
USERNAME = 'admin'
PASSWORD = 'admin'

response_login = requests.post(LOGIN_URL, json={
   'username': USERNAME,
   'password': PASSWORD
})

data = response_login.json()
print('Response JSON', data)
jwt = data.get('token')
print('JWT', jwt)

headers = {
   'Authorization': f'jwt {jwt}'
}

response_index = requests.get(INDEX_URL, params={
   'limit': 18,
   'offset': 0
}, headers=headers)

print('Response Status', response_index.status_code)
print('Response URL', response_index.url)
print('Response Data', response_index.json())
```