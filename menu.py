from flask import request, redirect, url_for, flash, Blueprint, render_template, session, Response, jsonify
import os
from werkzeug.utils import secure_filename
from db import get_db
from psycopg2.extras import RealDictCursor
import uuid
from helpers import login_required
from datetime import datetime,  timedelta
import csv
from io import StringIO

menu_bp = Blueprint("menu_bp", __name__)  # 定義一個 Blueprint

UPLOAD_FOLDER = "static/uploads"  # 檔案儲存資料夾
MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 限制檔案上限為 5MB
ALLOWED_EXT = {"png", "jpg", "jpeg", "gif"}  # 允許上傳的檔案格式


# 檢查上傳的副檔名
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT

# 菜單上傳
@menu_bp.route("/upload_menu", methods=["GET","POST"])
@login_required
def upload_menu():
    if request.method == "POST":
        if "image" not in request.files:
            flash("沒有選擇檔案")
            return redirect(request.url)

        file = request.files["image"]
        name = request.form.get("name")
        price = request.form.get("price")
        category = request.form.get("category")

        if file.filename == "":
            flash("沒有選擇檔案")
            return redirect(request.url)

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)  # 防止惡意檔名
            # 生成唯一檔名，避免重複覆蓋
            unique_filename = f"{uuid.uuid4().hex}_{filename}"

            # 組合儲存路徑 (例如 static/uploads/xxxx.jpg)
            filepath = os.path.join(UPLOAD_FOLDER, unique_filename)

            # 儲存檔案到伺服器
            file.save(filepath)

            # 存入資料庫時：image 欄位存「檔案路徑」
            conn = get_db()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO menu (restaurant_id, name, price, image, category, available)
                    VALUES (%s, %s, %s, %s, %s, TRUE)
                """,
                    (session["user_id"], name, price, unique_filename, category),
                )
                conn.commit()

            flash("菜單上傳成功！")
            return redirect(url_for("menu_bp.menu_page"))
        else:
            flash("檔案格式僅支援: png jpg, jpeg, gif")
            return redirect(request.url)
    else:
        return render_template("upload_menu.html")


# 菜單邏輯
@menu_bp.route("/menu")
@login_required
def menu_page():
    conn = get_db()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT id, name, price, image, available, category FROM menu WHERE restaurant_id = %s ORDER BY category",
            (session["user_id"],),
        ) 
        items = cur.fetchall()
    
    # 分類整理成 dict：{分類名稱: [菜單們]}
    items_by_category = {}
    for item in items:
        category = item["category"] or "其他"
        if category not in items_by_category:
            items_by_category[category] = []
        items_by_category[category].append(item)

    return render_template("menu.html", items_by_category=items_by_category)

# 編輯菜單按鈕
@menu_bp.route("/edit_menu/<int:item_id>", methods=["GET", "POST"])
@login_required
def edit_menu(item_id):
    conn = get_db()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        if request.method == "POST":
            name = request.form.get("name")
            price = request.form.get("price")
            category = request.form.get("category")
            available = request.form.get("available") == "true"

            cur.execute("""
                UPDATE menu
                SET name = %s, price = %s, category = %s, available = %s
                WHERE id = %s AND restaurant_id = %s
            """, (name, price, category, available, item_id, session["user_id"]))
            conn.commit()

            flash("菜單更新成功！")
            return redirect(url_for("menu_bp.menu_page"))

        # 顯示目前內容供修改
        cur.execute("SELECT * FROM menu WHERE id = %s", (item_id,))
        item = cur.fetchone()
        return render_template("edit_menu.html", item=item)

# 刪除菜單按鈕
@menu_bp.route("/delete_menu/<int:item_id>", methods=["POST"])
@login_required
def delete_menu(item_id):
    
    conn = get_db()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:

        cur.execute(
            "SELECT image FROM menu WHERE id = %s AND restaurant_id = %s",
            (item_id, session["user_id"]),
        )
        row = cur.fetchone()

        if row and row["image"]:
            image_filename = row["image"]
            image_path = os.path.join("static", "uploads", image_filename)

            # 檢查圖片路徑是否存在再刪除
            if os.path.exists(image_path):
                os.remove(image_path)

        cur.execute("DELETE FROM menu WHERE id = %s AND restaurant_id = %s",
                    (item_id, session["user_id"]))
        conn.commit()

    flash("菜單已刪除！")
    return redirect(url_for("menu_bp.menu_page"))

# 餐廳端查看訂單
@menu_bp.route("/orders")
@login_required
def restaurant_orders():
    restaurant_id = session["user_id"]
    conn = get_db()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT id, number, name, quantity, remark, int_out, first_time, price
            FROM orders
            WHERE restaurant_id = %s
            ORDER BY first_time DESC
        """, (restaurant_id,))
        orders = cur.fetchall()
    # 計算總額
    totals = {}
    for o in orders:
        totals[o["number"]] = totals.get(o["number"], 0) + o["price"] * o["quantity"]
    return render_template("orders.html", orders=orders, totals=totals)

# 餐廳端-刪除訂單按鈕
@menu_bp.route("/delete_orders/<int:number>", methods=["POST"])
@login_required
def delete_orders(number):
        conn = get_db()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:

            cur.execute("DELETE FROM orders WHERE number = %s AND restaurant_id = %s",
                        (number, session["user_id"]))
            conn.commit()
# 刪除號碼才對
        flash("訂單已刪除！")
        return redirect(url_for("menu_bp.restaurant_orders"))

# 餐廳端-完成訂單按鈕
@menu_bp.route("/finish_order/<int:number>", methods=["POST"])
@login_required
def finish_order(number):
    restaurant_id = session["user_id"]
    conn = get_db()

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # 1. 撈出該訂單所有項目
        cur.execute("""
            SELECT restaurant_id, number, name, quantity, remark, price, int_out, first_time
            FROM orders
            WHERE number = %s AND restaurant_id = %s
        """, (number, restaurant_id))
        orders = cur.fetchall()

        if not orders:
            flash("找不到該訂單，可能已被刪除")
            return redirect(url_for("menu_bp.restaurant_orders"))

        # 2. 將資料插入到 finish_orders 表中
        for o in orders:
            cur.execute("""
                INSERT INTO finish_orders
                (restaurant_id, number, name, quantity, remark, price, int_out, first_time, finish_time)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                o["restaurant_id"],
                o["number"],
                o["name"],
                o["quantity"],
                o["remark"],
                o["price"],
                o["int_out"],
                o["first_time"],
                datetime.now()   # 完成時間
            ))

        # 3. 刪除原本 orders 中該號的訂單
        cur.execute("""
            DELETE FROM orders
            WHERE number = %s AND restaurant_id = %s
        """, (number, restaurant_id))

        conn.commit()

    flash(f"訂單 #{number} 已完成")
    return redirect(url_for("menu_bp.restaurant_orders"))

# 服務員點餐
@menu_bp.route("/waiter_order", methods=["GET", "POST"])
@login_required
def waiter_order():
    if request.method == "POST":
        restaurant_id = session["user_id"]
        int_out = request.form.get("int_out")
        conn = get_db()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # 查目前號碼
            cur.execute("SELECT current_number FROM number_counter WHERE restaurant_id = %s", (restaurant_id,))
            result = cur.fetchone()

            if result:
                pickup_number = result["current_number"] + 1
                cur.execute("UPDATE number_counter SET current_number = %s WHERE restaurant_id = %s",
                            (pickup_number, restaurant_id))
            else:
                pickup_number = 1
                cur.execute("INSERT INTO number_counter (restaurant_id, current_number) VALUES (%s, %s)",
                            (restaurant_id, pickup_number))

            # 查詢菜單
            cur.execute("SELECT id, name, price FROM menu WHERE restaurant_id = %s", (restaurant_id,))
            menu_items = cur.fetchall()
            checking = False    # 請選擇至少一個菜品
            for m in menu_items:
                qty = int(request.form.get(f"qty_{m["id"]}", 0))
                remark = request.form.get(f"remark_{m["id"]}", "")
                if qty > 0:
                    checking = True
                    cur.execute("""
                        INSERT INTO orders (restaurant_id, number, name_id, name, quantity, remark, price, int_out)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (restaurant_id, pickup_number, m["id"], m["name"], qty, remark, m["price"], int_out))
            if not checking:
                return  "請選擇至少一個菜品！", 404

            conn.commit()
        flash(f"感謝您的訂購！您的取餐號碼是： {pickup_number}號 記下您的號碼~等待叫號")

        return redirect("/orders")
    
    else:
        conn = get_db()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # 找到對應餐廳
        restaurant_id = session["user_id"]
        cur.execute("SELECT restaurant_name FROM restaurant WHERE id = %s", (restaurant_id, ))
        restaurant = cur.fetchone()
        if not restaurant:
            return "餐廳不存在", 404
        
        # 查出這家餐廳的菜單
        cur.execute("SELECT * FROM menu WHERE restaurant_id = %s AND available = TRUE  ORDER BY category, name", (restaurant_id, ))
        items = cur.fetchall()

    # 依分類分組
    items_by_category = {}
    for item in items:
        category = item["category"] or "其他"  # 若分類是 None 或空字串，就歸為「其他」
        if category not in items_by_category:
            items_by_category[category] = []
        items_by_category[category].append(item)
    
    return render_template("waiter_order.html", restaurant=restaurant, menu_items_by_category=items_by_category)

# 歷史交易-顯示
@menu_bp.route("/history")
@login_required
def history():
    restaurant_id = session["user_id"]
    conn = get_db()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:

        # 取得所有歷史訂單（多帶日期）
        cur.execute("""
            SELECT number, name, quantity, remark, price, int_out,
                   first_time, finish_time, DATE(finish_time) AS order_date
            FROM finish_orders
            WHERE restaurant_id = %s
            ORDER BY finish_time DESC
        """, (restaurant_id,))
        finish_orders = cur.fetchall()

        # 今日營業額
        cur.execute("""
            SELECT SUM(price * quantity) AS total_revenue
            FROM finish_orders
            WHERE restaurant_id = %s AND DATE(finish_time) = CURRENT_DATE
        """, (restaurant_id,))
        today_revenue = cur.fetchone()["total_revenue"] or 0

        # 今日銷售統計
        cur.execute("""
            SELECT name, SUM(quantity) AS total_sold
            FROM finish_orders
            WHERE restaurant_id = %s AND DATE(finish_time) = CURRENT_DATE
            GROUP BY name
            ORDER BY total_sold DESC
        """, (restaurant_id,))
        today_sales = cur.fetchall()

    return render_template("history.html", finish_orders=finish_orders, today_revenue=today_revenue, today_sales=today_sales)

# 清空歷史交易
@menu_bp.route("/clear_history", methods=["POST"])
@login_required
def clear_history():
    restaurant_id = session["user_id"]
    conn = get_db()
    with conn.cursor() as cur:
        
        # 完成訂單才能送出
        cur.execute("SELECT * FROM orders WHERE restaurant_id = %s", (restaurant_id,))
        items = cur.fetchall()
        if items:
            flash("還有未完成訂單，請先完成所有訂單!")
            return redirect(url_for("menu_bp.history"))

        cur.execute("DELETE FROM finish_orders WHERE restaurant_id = %s", (restaurant_id,))
        
        # 清空號碼牌
        cur.execute("UPDATE number_counter SET current_number = 0 WHERE restaurant_id = %s", (restaurant_id,))
        conn.commit()
    
    flash("歷史交易紀錄已清空！")
    return redirect(url_for("menu_bp.history"))

# 匯出報表並清空歷史交易
@menu_bp.route("/export_and_clear_history")
@login_required
def export_and_clear_history():
    restaurant_id = session["user_id"]
    conn = get_db()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:

        # 完成訂單才能送出
        cur.execute("SELECT * FROM orders WHERE restaurant_id = %s", (restaurant_id,))
        items = cur.fetchall()
        if items:
            flash("~~~還有未完成訂單，請先完成所有訂單~~~")
            return ""

        # 1️⃣ 先取得所有歷史交易
        cur.execute("""
            SELECT number, name, quantity, remark, price, int_out, first_time, finish_time
            FROM finish_orders
            WHERE restaurant_id = %s
            ORDER BY finish_time DESC
        """, (restaurant_id,))
        records = cur.fetchall()

        # 若無資料，直接返回提示
        if not records:
            flash("~~~目前沒有可匯出的歷史交易~~~")
            return ""
        
        # 建立 UTF-8 with BOM
        output = StringIO()
        output.write('\ufeff')  # <<<--- 這行很重要：在開頭加 BOM！

        # 建立 CSV 檔案
        writer = csv.writer(output)
        writer.writerow(["訂單號碼", "品名", "數量", "備註", "單價", "內用/外帶", "建立時間", "完成時間"])
        for r in records:
            writer.writerow([
                r["number"],
                r["name"],
                r["quantity"],
                r["remark"] or "",
                r["price"],
                r["int_out"],
                r["first_time"].strftime("%Y-%m-%d %H:%M:%S"),
                r["finish_time"].strftime("%Y-%m-%d %H:%M:%S")
            ])

        # 3️⃣ 匯出後立即清空歷史交易
        cur.execute("DELETE FROM finish_orders WHERE restaurant_id = %s", (restaurant_id,))
        # 清空號碼牌
        cur.execute("UPDATE number_counter SET current_number = 0 WHERE restaurant_id = %s", (restaurant_id,))
        conn.commit()

    # 4️⃣ 回傳 CSV 檔案
    response = Response(output.getvalue(), mimetype="text/csv; charset=utf-8")
    response.headers["Content-Disposition"] = f"attachment; filename=history_{restaurant_id}.csv"
    flash("已匯出報表")
    return response

# 訂單有更新才會更新html頁面（加上 AJAX 專用路由）
@menu_bp.route("/get_orders_json")
@login_required
def get_orders_json():
    restaurant_id = session["user_id"]
    conn = get_db()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT id, number, name, quantity, remark, int_out, first_time, price
            FROM orders
            WHERE restaurant_id = %s
            ORDER BY first_time DESC
        """, (restaurant_id,))
        orders = cur.fetchall()
    return jsonify(orders)