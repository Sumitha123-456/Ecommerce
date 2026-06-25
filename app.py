from flask import Flask, render_template, request, redirect, session, jsonify
from flask_pymongo import PyMongo
from bson.objectid import ObjectId
import bcrypt
import os
from werkzeug.utils import secure_filename
from config import Config
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langgraph.graph import StateGraph, END
from datetime import datetime

load_dotenv()

# ========================
# GROQ AI
# ========================
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

llm = ChatGroq(
    model_name="llama-3.3-70b-versatile",
    groq_api_key=GROQ_API_KEY
)

# ========================
# APP
# ========================
app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = os.getenv("SECRET_KEY", "secret")

UPLOAD_FOLDER = "static/uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

mongo = PyMongo(app)

# =====================================================
# LANGGRAPH (UNCHANGED)
# =====================================================

def router(state):
    msg = state["message"].lower()

    if "price" in msg or "buy" in msg:
        return "product_node"
    elif "order" in msg:
        return "order_node"
    return "chat_node"


def chat_node(state):
    res = llm.invoke(state["message"])
    return {"response": res.content}


def product_node(state):
    products = state["products"]

    text = ""
    for p in products:
        text += f"{p['name']} - ₹{p['price']} - {p['description']}\n"

    prompt = f"Products:\n{text}\nUser:{state['message']}"
    res = llm.invoke(prompt)
    return {"response": res.content}


def order_node(state):
    orders = state.get("orders", [])
    res = llm.invoke(f"Orders: {orders}")
    return {"response": res.content}


graph = StateGraph(dict)

graph.add_node("router", router)
graph.add_node("chat_node", chat_node)
graph.add_node("product_node", product_node)
graph.add_node("order_node", order_node)

graph.set_entry_point("router")

graph.add_conditional_edges(
    "router",
    router,
    {
        "chat_node": "chat_node",
        "product_node": "product_node",
        "order_node": "order_node"
    }
)

graph.add_edge("chat_node", END)
graph.add_edge("product_node", END)
graph.add_edge("order_node", END)

agent = graph.compile()

def run_agent(message, products, orders):
    return agent.invoke({
        "message": message,
        "products": products,
        "orders": orders
    })

# =====================================================
# HOME
# =====================================================
@app.route('/')
def home():
    products = list(mongo.db.products.find())
    return render_template('dashboard.html', products=products)

# =====================================================
# REGISTER (FIXED SAFETY)
# =====================================================
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':

        if mongo.db.users.find_one({'username': request.form['username']}):
            return "User Exists"

        hashed = bcrypt.hashpw(
            request.form['password'].encode('utf-8'),
            bcrypt.gensalt()
        )

        mongo.db.users.insert_one({
            "username": request.form['username'],
            "password": hashed,
            "role": "user"
        })

        return redirect('/login')

    return render_template('register.html')

# =====================================================
# LOGIN (🔥 FIXED BCRYPT ERROR HERE)
# =====================================================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':

        user = mongo.db.users.find_one({'username': request.form['username']})

        if user:

            stored_password = user['password']

            # 🔥 FIX: convert string → bytes if needed
            if isinstance(stored_password, str):
                stored_password = stored_password.encode('utf-8')

            if bcrypt.checkpw(
                request.form['password'].encode('utf-8'),
                stored_password
            ):
                session['user_id'] = str(user['_id'])
                session['username'] = user['username']
                return redirect('/')

        return "Invalid login"

    return render_template('login.html')

# =====================================================
# ADMIN
# =====================================================
@app.route('/admin')
def admin():

    products = list(mongo.db.products.find())
    orders = list(mongo.db.orders.find())

    return render_template(
        "admin.html",
        products=products,
        total_products=len(products),
        total_orders=len(orders)
    )

# =====================================================
# CART
# =====================================================
@app.route('/add_to_cart/<id>')
def add_to_cart(id):

    if 'user_id' not in session:
        return redirect('/login')

    mongo.db.cart.insert_one({
        'user_id': session['user_id'],
        'product_id': str(id),
        'added_at': datetime.now()
    })

    return redirect('/cart')

@app.route('/cart')
def cart():

    if 'user_id' not in session:
        return redirect('/login')

    items = []

    cart_items = mongo.db.cart.find({'user_id': session['user_id']})

    for item in cart_items:

        product_id = item.get('product_id')
        if not product_id:
            continue

        product = mongo.db.products.find_one({
            '_id': ObjectId(product_id)
        })

        if product:
            items.append(product)

    return render_template('cart.html', items=items)

# =====================================================
# ORDERS
# =====================================================
@app.route('/orders')
def orders():

    user_orders = list(mongo.db.orders.find({'user_id': session.get('user_id')}))
    return render_template("orders.html", orders=user_orders)

# =====================================================
# AI CHAT
# =====================================================
@app.route('/ai-chat', methods=['POST'])
def ai_chat():

    data = request.json
    question = data.get("message")

    products = list(mongo.db.products.find())
    orders = list(mongo.db.orders.find({'user_id': session.get('user_id')}))

    result = run_agent(question, products, orders)

    return jsonify({"reply": result["response"]})

# =====================================================
# RUN
# =====================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)