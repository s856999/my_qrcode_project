from flask import Blueprint, request,render_template
from db import get_db
from psycopg2.extras import RealDictCursor

client_bp = Blueprint("client_bp", __name__)  # 定義一個 Blueprint

# 當客戶掃描 QR code
@client_bp.route("/menu/<uuid>")
def menu_page(uuid):
    conn = get_db()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # 找到對應餐廳
        cur.execute("SELECT id, restaurant_name FROM restaurant WHERE uuid = %s", (uuid,))
        restaurant = cur.fetchone()
        if not restaurant:
            return "餐廳不存在", 404
        
        # 查出這家餐廳的菜單
        cur.execute("SELECT * FROM menu WHERE restaurant_id = %s AND available = TRUE  ORDER BY category, name", (restaurant["id"],))
        items = cur.fetchall()

    # 依分類分組
    items_by_category = {}
    for item in items:
        category = item["category"] or "其他"  # 若分類是 None 或空字串，就歸為「其他」
        if category not in items_by_category:
            items_by_category[category] = []
        items_by_category[category].append(item)
    
    return render_template("client_menu.html", restaurant=restaurant, menu_items_by_category=items_by_category)
    

# 當客戶送出訂單
@client_bp.route("/order/<int:restaurant_id>", methods=["POST"])
def submit_order(restaurant_id):
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
        print(menu_items)
        checking = False    # 請選擇至少一個菜品
        for m in menu_items:
            qty = int(request.form.get(f"qty_{m["id"]}", 0))
            remark = request.form.get(f"remark_{m["id"]}", "")
            if qty > 0:
                checking = True
                cur.execute("""
                    INSERT INTO orders (restaurant_id, number, name_id, name, quantity, remark, price, int_out)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (restaurant_id, pickup_number,m["id"], m["name"], qty, remark, m["price"], int_out))
        if not checking:
            return  "請選擇至少一個菜品！", 404

        conn.commit()

    return render_template("order_success.html", pickup_number=pickup_number)