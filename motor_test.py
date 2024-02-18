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

BOOK_NAME = '废土'
BOOK_CHAPTER_COLLECTION_NAME = '章节链接'
BOOK_TEXT_COLLECTION_NAME = '文本'

async def do_find():
    async for document in collection.find({}):  # 查询所有文档
        name = document.get('name')
        pprint('小说名字为: {}'.format(name))
        chapter_info = document.get('chapter_info')
        pprint(chapter_info)

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
    await save_to_txt()

if __name__ == '__main__':
    asyncio.run(main())