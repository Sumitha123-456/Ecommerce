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
# AI SETUP
# ========================
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

llm = ChatGroq(
    model_name="llama-3.3-70b-versatile",
    groq_api_key=GROQ_API_KEY
)

# ========================
# APP SETUP
# ========================
app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = os.getenv("SECRET_KEY", "secret")

UPLOAD_FOLDER = "static/uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

mongo = PyMongo(app)

# =====================================================
# LANGGRAPH STATE
# =====================================================
from typing import TypedDict

class GraphState(TypedDict):
    message: str
    products: list
    orders: list
    response: str

# =====================================================
# LANGGRAPH NODES
# =====================================================

def router(state: GraphState):
    msg = state["message"].lower()

    if "price" in msg or "buy" in msg or "product" in msg:
        return "product_node"
    elif "order" in msg or "cart" in msg:
        return "order_node"
    else:
        return "chat_node"


def chat_node(state: GraphState):
    print("🟢 CHAT NODE TRIGGERED")
    res = llm.invoke(state["message"])
    return {"response": res.content}


def product_node(state: GraphState):
    print("🟡 PRODUCT NODE TRIGGERED")

    text = ""
    for p in state["products"]:
        text += f"{p['name']} - ₹{p['price']} - {p['description']}\n"

    prompt = f"""
    Ecommerce assistant:

    Products:
    {text}

    Question:
    {state['message']}
    """

    res = llm.invoke(prompt)
    return {"response": res.content}


def order_node(state: GraphState):
    print("🔵 ORDER NODE TRIGGERED")

    res = llm.invoke(f"Orders: {state['orders']}")
    return {"response": res.content}

# =====================================================
# LANGGRAPH BUILD
# =====================================================
graph = StateGraph(GraphState)

graph.add_node("chat_node", chat_node)
graph.add_node("product_node", product_node)
graph.add_node("order_node", order_node)

graph.set_entry_point("chat_node")

graph.add_conditional_edges(
    "chat_node",
    router,
    {
        "chat_node": END,
        "product_node": "product_node",
        "order_node": "order_node"
    }
)

graph.add_edge("product_node", END)
graph.add_edge("order_node", END)

agent = graph.compile()

def run_agent(message, products, orders):
    return agent.invoke({
        "message": message,
        "products": products,
        "orders": orders,
        "response": ""
    })

# =====================================================
# HOME
# =====================================================
@app.route('/')
def home():
    products = list(mongo.db.products.find())
    return render_template('dashboard.html', products=products)

# =====================================================
# REGISTER
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
# LOGIN
# =====================================================
@app.route('/login', methods=['GET', 'POST'])
def login():

    if request.method == 'POST':

        user = mongo.db.users.find_one({'username': request.form['username']})

        if user:
            stored = user['password']
            if isinstance(stored, str):
                stored = stored.encode('utf-8')

            if bcrypt.checkpw(
                request.form['password'].encode('utf-8'),
                stored
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
# ADD PRODUCT
# =====================================================
@app.route('/add_product', methods=['GET', 'POST'])
def add_product():

    if request.method == 'POST':

        file = request.files['image']
        filename = file.filename
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

        mongo.db.products.insert_one({
            "name": request.form['name'],
            "price": request.form['price'],
            "description": request.form['description'],
            "image": filename
        })

        return redirect('/admin')

    return render_template('add_product.html')

# =====================================================
# EDIT PRODUCT
# =====================================================
@app.route('/edit_product/<id>', methods=['GET', 'POST'])
def edit_product(id):

    product = mongo.db.products.find_one({'_id': ObjectId(id)})

    if request.method == 'POST':

        mongo.db.products.update_one(
            {'_id': ObjectId(id)},
            {"$set": {
                "name": request.form['name'],
                "price": request.form['price'],
                "description": request.form['description']
            }}
        )

        return redirect('/admin')

    return render_template('edit_product.html', product=product)

# =====================================================
# DELETE PRODUCT
# =====================================================
@app.route('/delete_product/<id>')
def delete_product(id):

    try:
        mongo.db.products.delete_one({'_id': ObjectId(id)})
    except:
        pass

    return redirect('/admin')

# =====================================================
# CART
# =====================================================
@app.route('/add_to_cart/<id>')
def add_to_cart(id):

    if 'user_id' not in session:
        return redirect('/login')

    mongo.db.cart.insert_one({
        "user_id": session['user_id'],
        "product_id": str(id),
        "added_at": datetime.now()
    })

    return redirect('/')

@app.route('/cart')
def cart():

    if 'user_id' not in session:
        return redirect('/login')

    items = []

    for item in mongo.db.cart.find({'user_id': session['user_id']}):

        pid = item.get('product_id')
        if not pid:
            continue

        product = mongo.db.products.find_one({'_id': ObjectId(pid)})
        if product:
            items.append(product)

    return render_template('cart.html', items=items)

# =====================================================
# PLACE ORDER
# =====================================================
@app.route('/place_order')
def place_order():

    if 'user_id' not in session:
        return redirect('/login')

    cart_items = list(mongo.db.cart.find({'user_id': session['user_id']}))

    for item in cart_items:
        product = mongo.db.products.find_one({'_id': ObjectId(item['product_id'])})

        if product:
            mongo.db.orders.insert_one({
                "user_id": session['user_id'],
                "product_name": product['name'],
                "price": product['price'],
                "status": "Placed",
                "created_at": datetime.now()
            })

    mongo.db.cart.delete_many({'user_id': session['user_id']})

    return redirect('/order_success')

# =====================================================
# ORDER SUCCESS PAGE
# =====================================================
@app.route('/order_success')
def order_success():
    return render_template('order_success.html')

# =====================================================
# ORDERS
# =====================================================
@app.route('/orders')
def orders():

    if 'user_id' not in session:
        return redirect('/login')

    user_orders = list(mongo.db.orders.find({'user_id': session['user_id']}))
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
# LANGGRAPH VIEWER
# =====================================================
@app.route("/graph")
def view_graph():
    return graph.get_graph().draw_mermaid()

@app.route("/graph.png")
def graph_png():
    return graph.get_graph().draw_mermaid_png()
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

# =====================================================
# RUN
# =====================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)