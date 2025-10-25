import psycopg2
from flask import g
import os
from dotenv import load_dotenv


load_dotenv()  # 讀取 .env

# 數據庫
# PostgreSQL 連線設定
DB_PARAMS = {
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT"),
}


# 每次使用前建立連線
def get_db():
    if "conn" not in g:  # g 是 Flask 全域暫存區
        g.conn = psycopg2.connect(**DB_PARAMS)  # connect連接
    return g.conn
