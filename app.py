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
# GROQ AI SETUP
# ========================
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

llm = None
if GROQ_API_KEY:
    llm = ChatGroq(
        model_name="llama-3.3-70b-versatile",
        groq_api_key=GROQ_API_KEY
    )
    print("Groq AI enabled")
else:
    print("Groq API missing")

# ========================
# FLASK APP
# ========================
app = Flask(__name__)
app.config.from_object(Config)

app.secret_key = os.getenv("SECRET_KEY", "secret")

UPLOAD_FOLDER = "static/uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ========================
# MONGO INIT
# ========================
mongo = PyMongo(app)

# ==========================================================
# 🔥 LANGGRAPH SETUP (Ecommerce AI Brain)
# ==========================================================

def router(state):
    msg = state["message"].lower()

    if "price" in msg or "buy" in msg or "product" in msg:
        return "product_node"
    elif "order" in msg or "cart" in msg:
        return "order_node"
    else:
        return "chat_node"


def chat_node(state):
    response = llm.invoke(state["message"])
    return {"response": response.content}


def product_node(state):
    products = state["products"]

    text = ""
    for p in products:
        text += f"{p['name']} - ₹{p['price']} - {p['description']}\n"

    prompt = f"""
    You are an ecommerce assistant.

    Products:
    {text}

    User question:
    {state['message']}

    Recommend best products clearly.
    """

    response = llm.invoke(prompt)
    return {"response": response.content}


def order_node(state):
    orders = state.get("orders", [])

    prompt = f"""
    You are an order assistant.

    Orders:
    {orders}

    Explain order status clearly.
    """

    response = llm.invoke(prompt)
    return {"response": response.content}


# Build Graph
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

# ========================
# HOME
# ========================
@app.route('/')
def home():
    products = list(mongo.db.products.find())
    return render_template('dashboard.html', products=products)

# ========================
# ALL YOUR ROUTES (UNCHANGED)
# ========================
# (register, login, admin, cart, etc remain same)
# -------------------------------------------------

@app.route('/ai-chat', methods=['POST'])
def ai_chat():

    data = request.json
    question = data.get("message")

    products = list(mongo.db.products.find())
    orders = list(mongo.db.orders.find({'user_id': session.get('user_id')}))

    result = run_agent(question, products, orders)

    return jsonify({"reply": result["response"]})

# ========================
# RUN
# ========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)