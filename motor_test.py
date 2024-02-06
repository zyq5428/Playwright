import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from pprint import pprint
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s: %(message)s')

# 定义MongoDB的连接字符串
MONGO_CONNECTION_STRING = 'mongodb://localhost:27017'
MONGO_DB_NAME = 'novel_0204'
MONGO_COLLECTION_NAME = 'novel_0204'

client = AsyncIOMotorClient(MONGO_CONNECTION_STRING)
db = client[MONGO_DB_NAME]
collection = db[MONGO_COLLECTION_NAME]

async def do_find():
    async for document in collection.find({}):  # 查询所有文档
        name = document.get('name')
        pprint('小说名字为: {}'.format(name))
        chapter_info = document.get('chapter_info')
        pprint(chapter_info)

async def main():
    await do_find()

if __name__ == '__main__':
    asyncio.run(main())