# api(10个，https，1-5分钟，JSON，全属性，4位端口，去重，不限运营商)

# 直连IP
Direct_IP = 'http://webapi.http.zhimacangku.com/getip?neek=860483b89fc4d67d&num=10&type=2&pro=&city=0&yys=0&port=11&time=4&ts=1&ys=1&cs=1&lb=1&sb=0&pb=4&mr=1&regions='
# 独享IP
Exclusive_IP = 'http://http.tiqu.letecs.com/getip3?neek=860483b89fc4d67d&num=10&type=2&pro=&city=0&yys=0&port=11&time=4&ts=1&ys=1&cs=1&lb=1&sb=0&pb=4&mr=1&regions=&gm=4'
# 隧道IP
Tunnel_IP = 'http://http.tiqu.letecs.com/getip3?neek=860483b89fc4d67d&num=10&type=2&pro=&city=0&yys=0&port=11&time=4&ts=1&ys=1&cs=1&lb=1&sb=0&pb=4&mr=1&regions='
# 白名单列表
Whitelist_API = 'https://wapi.proxy.linkudp.com/api/white_list?'
# 设置白名单
Whiteset_API = 'https://wapi.http.linkudp.com/index/index/save_white?'

Your_IP = '113.87.80.21'

import requests
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s: %(message)s')

class ip_proxy:
    def scrape_page(self, url):
        # logging.info('scraping %s', url)
        try:
            response = requests.get(url)
            if response.status_code == 200:
                return response.json()
            logging.info('get invalid status code %s while scraping %s', response.status_code, url)
        except requests.RequestException:
            logging.error('error occurred while scraping %s', url, exc_info=True)

    # def __init__(self, ip_api, white_list_api, white_set_api, your_ip):
    def __init__(self, ip_api):
        self.ip_api = ip_api
        self.ip = []

        # set white list
        # list_json = self.scrape_page(white_list_api)
        # if list_json['code'] == 0:
        #     lists = list_json['data']['lists']
        #     white_list = []
        #     for list in lists:
        #         white_list.append(list['mark_ip'])
        #     if your_ip in white_list:
        #         logging.info('Your ip is exit')
        #     else:
        #         url = white_set_api + your_ip
        #         result = self.scrape_page(url)
        #         if result['code'] == 0:
        #             logging.info('Save ip to white list successed')
        #         else:
        #             logging.error('Please check white list set error code:', result['code'])
        # else:
        #     logging.error('Withe list api is error %s', white_list_api)

    def get_proxy(self):
        logging.info('Start get proxy server')
        data = self.scrape_page(self.ip_api)
        if data['code'] == 0:
            servers = []
            for item in data['data']:
                ip = item['ip']
                port = item['port']
                server = ip + ':' + str(port)
                servers.append(server)
            self.ip = servers
            return self.ip
        else:
            logging.error('Get proxy Failed')
            return None
        
if __name__ == '__main__':
    proxy = ip_proxy(Direct_IP, Whitelist_API, Whiteset_API, Your_IP)
    if proxy.get_proxy():
        logging.info(proxy.ip)
