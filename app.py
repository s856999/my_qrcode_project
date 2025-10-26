import secrets
import os
from flask import Flask, render_template, redirect, request, session, flash, g, url_for
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash
from validate_email import validate_email
import qrcode
from menu import menu_bp
from client_orders import client_bp
from db import get_db
from helpers import login_required
from psycopg2.extras import RealDictCursor
import uuid
from flask_mail import Mail, Message
from dotenv import load_dotenv

load_dotenv()  # 讀取 .env 檔案內容

app = Flask(__name__)

# 設定郵件寄送
app.config["MAIL_SERVER"] = os.getenv("MAIL_SERVER")
app.config["MAIL_PORT"] = int(os.getenv("MAIL_PORT"))
app.config["MAIL_USE_TLS"] = os.getenv("MAIL_USE_TLS") == "True"
app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")
app.config["MAIL_DEFAULT_SENDER"] = os.getenv("MAIL_DEFAULT_SENDER")
mail = Mail(app)

# Flask 結束時自動關閉資料庫連線
@app.teardown_appcontext  # Flask 提供的「應用結束時」觸發的裝飾器
def close_db(error):
    conn = g.pop("conn", None)  # pop彈出conn,意思取出 conn（資料庫連線），
    # 並同時把它從 g 裡刪除
    # 如果g沒有conn，就回傳None
    if conn is not None:
        conn.close()


# session過濾器設定
app.secret_key = os.urandom(24)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# 註冊 Blueprint
app.register_blueprint(menu_bp)
app.register_blueprint(client_bp)

# 存放 QR code 的資料夾
UPLOAD_FOLDER = "static/qrcodes"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# 生成 QR code
def generate_qrcode(data, filepath):
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(filepath)


# 登入
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        session.clear()
        # 判斷賬號密碼為空
        if not request.form.get("username") or not request.form.get("password"):
            flash("欄位不能為空")
            return redirect("/login")
        # 查詢SQL
        conn = get_db()  # 建立連綫
        with conn.cursor() as cur:  # 游標物件，執行指令、接受查詢結果
            # 執行查詢
            cur.execute(
                "SELECT user_name FROM restaurant WHERE user_name = %s;",
                (request.form.get("username"),),
            )
            # 提取資料
            user_name = cur.fetchone()
            # 賬號及密碼是否正確
            if not user_name:
                flash("賬號錯誤")
                return redirect("/login")
            else:
                username = request.form.get("username")
                cur.execute(
                    "SELECT id, password, verified FROM restaurant WHERE user_name = %s;", (username,)
                )
                # 提取資料
                row = cur.fetchone()
                password = row[1]
                if not check_password_hash(password, request.form.get("password")):
                    flash("請檢查密碼")
                    return redirect("/login")
                
                elif not row[2]:
                    flash("請先完成信箱驗證後再登入")
                    return redirect("/login")
                
                else:
                    # 提取id資料
                    uid = row[0]
                    session["user_id"] = uid
                    flash("登入成功")
                    return redirect("/qrcode")
    else:
        return render_template("login.html")


# 注冊
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        session.clear()
        # 判斷賬號密碼餐廳名稱信箱為空，或賬號是否相等
        if (
            not request.form.get("username")
            or not request.form.get("email")
            or not request.form.get("restaurant_name")
            or not request.form.get("password")
            or not request.form.get("again_password")
        ):
            flash("欄位不能為空")
            return redirect("/register")
        # 檢查信箱格式
        elif not validate_email(request.form.get("email")):
            flash("Email 格式錯誤")
            return redirect("/register")
        # 密碼兩次是否相同
        elif request.form.get("password") != request.form.get("again_password"):
            flash("輸入密碼不一致")
            return redirect("/register")

        conn = get_db()  # 建立連綫
        with conn.cursor() as cur:  # 游標物件，執行指令、接受查詢結果
            # 執行查詢
            cur.execute(
                "SELECT user_name FROM restaurant WHERE user_name = %s;",
                (request.form.get("username"),),
            )
            # 提取資料
            # 代表不成功
            if cur.fetchone():
                flash("賬號重複")
                return redirect("/register")
            # 注冊成功儲存成雜凑值
            else:
                user_name = request.form.get("username")
                password = request.form.get("password")
                hash_password = generate_password_hash(password)  # 儲存成雜凑值
                restaurant_name = request.form.get("restaurant_name")
                email = request.form.get("email")

                unique_id = str(uuid.uuid4())

                # 產生驗證 token
                token = secrets.token_urlsafe(32)
                
                # 生成 QR code 檔案路徑
                qrcode_filename = f"{unique_id}.png"
                qrcode_path = os.path.join(UPLOAD_FOLDER, qrcode_filename)
                generate_qrcode(f"jamesqrcode.onrender.com/menu/{unique_id}", qrcode_path)
                # 本地方式 generate_qrcode(f"http://127.0.0.1:5000/menu/{unique_id}", qrcode_path)

                # 存資料庫時只存相對於 static 的路徑
                qrcode_db_path = f"qrcodes/{qrcode_filename}"
                
                # 插入注冊資料
                cur.execute(
                    "INSERT INTO restaurant (user_name, password, restaurant_name, qrcode, email, uuid, verify_token) VALUES (%s, %s, %s, %s, %s, %s, %s);",
                    (user_name, hash_password, restaurant_name, qrcode_db_path, email, unique_id, token),
                )
                # 提交變更
                conn.commit()

            # 寄出驗證信
            verify_url = url_for("verify_email", token=token, _external=True)
            print("模擬寄信 → 收件者:", email)
            print("驗證連結:", verify_url)
            # 原本的寄信程式碼暫時註解掉
            # msg = Message("請驗證您的信箱", recipients=[email])
            # msg.body = f"您好！請點擊以下連結完成信箱驗證：\n{verify_url}"
            # mail.send(msg)

            flash("註冊成功！請前往信箱點擊驗證連結。")
            return redirect("/login")
    else:
        return render_template("register.html")

# 驗證信箱
@app.route("/verify/<token>")
def verify_email(token):
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute("UPDATE restaurant SET verified = TRUE WHERE verify_token = %s;", (token,))
        conn.commit()
    flash("信箱驗證成功，您現在可以登入！")
    return redirect("/login")


# 登出
@app.route("/logout")
def logout():
    session.clear()
    flash("登出成功")
    return redirect("/")

@app.route("/text")
def text():
    return render_template("text.html")

# QrCode
@app.route("/qrcode")
@login_required
def myqrcode():
    # 餐廳名稱
    conn = get_db()  # 建立連綫
    with conn.cursor(cursor_factory=RealDictCursor) as cur:  # 游標物件，執行指令、接受查詢結果
            # 執行查詢
            cur.execute(
                "SELECT restaurant_name, qrcode FROM restaurant WHERE id = %s;",
                (session["user_id"], )
            )
            # 提取資料
            restaurant = cur.fetchone()
            
    return render_template("qrcode.html", restaurant=restaurant)

# 關於我
@app.route("/")
def index():
    return  render_template("index.html")