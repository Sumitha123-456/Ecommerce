from flask import Flask, render_template, request, redirect, session, jsonify
from flask_pymongo import PyMongo
from bson.objectid import ObjectId
import bcrypt
import os
from werkzeug.utils import secure_filename
from config import Config
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from datetime import datetime

load_dotenv()

# ========================
# GROQ AI SETUP (FIXED)
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
# MONGO INIT (SAFE)
# ========================
try:
    mongo = PyMongo(app)
    print("MongoDB connected")
except Exception as e:
    print("MongoDB connection error:", e)
    mongo = None


# ========================
# HOME
# ========================
@app.route('/')
def home():
    products = list(mongo.db.products.find())
    return render_template('dashboard.html', products=products)


# ========================
# REGISTER
# ========================
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':

        username = request.form['username']
        password = request.form['password']

        existing = mongo.db.users.find_one({'username': username})

        if existing:
            return "User Already Exists"

        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

        mongo.db.users.insert_one({
            'username': username,
            'password': hashed,
            'role': 'admin'
        })

        return redirect('/login')

    return render_template('register.html')


# ========================
# LOGIN
# ========================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':

        user = mongo.db.users.find_one({'username': request.form['username']})

        if user and bcrypt.checkpw(
            request.form['password'].encode('utf-8'),
            user['password']
        ):
            session['user_id'] = str(user['_id'])
            session['username'] = user['username']
            session['role'] = user.get('role', 'user')

            return redirect('/')

        return "Invalid Login"

    return render_template('login.html')


# ========================
# LOGOUT
# ========================
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')


# ========================
# ADMIN (FIXED SECURITY)
# ========================
@app.route('/admin')
def admin():

    if 'user_id' not in session:
        return redirect('/login')

    products = list(mongo.db.products.find())

    total_products = mongo.db.products.count_documents({})
    total_users = mongo.db.users.count_documents({})
    total_orders = mongo.db.orders.count_documents({})

    orders = list(mongo.db.orders.find())

    from collections import Counter
    date_counts = Counter()

    for order in orders:
        if 'created_at' in order:
            date = order['created_at'].strftime("%d-%m")
            date_counts[date] += 1

    return render_template(
        'admin.html',
        products=products,
        total_products=total_products,
        total_users=total_users,
        total_orders=total_orders,
        labels=list(date_counts.keys()),
        values=list(date_counts.values())
    )


# ========================
# ADD PRODUCT
# ========================
@app.route('/add_product', methods=['GET', 'POST'])
def add_product():

    if request.method == 'POST':

        filename = ""

        file = request.files.get('image')
        if file and file.filename:
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

        mongo.db.products.insert_one({
            'name': request.form['name'],
            'price': request.form['price'],
            'description': request.form['description'],
            'image': filename
        })

        return redirect('/admin')

    return render_template('add_product.html')


# ========================
# EDIT PRODUCT
# ========================
@app.route('/edit_product/<id>', methods=['GET', 'POST'])
def edit_product(id):

    product = mongo.db.products.find_one({'_id': ObjectId(id)})

    if request.method == 'POST':
        mongo.db.products.update_one(
            {'_id': ObjectId(id)},
            {'$set': {
                'name': request.form['name'],
                'price': request.form['price'],
                'description': request.form['description']
            }}
        )
        return redirect('/admin')

    return render_template('edit_product.html', product=product)


# ========================
# DELETE PRODUCT
# ========================
@app.route('/delete_product/<id>')
def delete_product(id):
    mongo.db.products.delete_one({'_id': ObjectId(id)})
    return redirect('/admin')


# ========================
# ADD TO CART
# ========================
@app.route('/add_to_cart/<id>')
def add_to_cart(id):

    if 'user_id' not in session:
        return redirect('/login')

    mongo.db.cart.insert_one({
        'user_id': session['user_id'],
        'product_id': str(id)
    })

    return redirect('/')


# ========================
# CART
# ========================
@app.route('/cart')
def cart():

    if 'user_id' not in session:
        return redirect('/login')

    items = []

    for item in mongo.db.cart.find({'user_id': session['user_id']}):

        product = mongo.db.products.find_one({
            '_id': ObjectId(item['product_id'])
        })

        if product:
            items.append(product)

    return render_template('cart.html', items=items)


# ========================
# REMOVE CART
# ========================
@app.route('/remove_cart/<id>')
def remove_cart(id):

    if 'user_id' not in session:
        return redirect('/login')

    mongo.db.cart.delete_one({
        'user_id': session['user_id'],
        'product_id': str(id)
    })

    return redirect('/cart')


# ========================
# PLACE ORDER (FIXED BUG)
# ========================
@app.route('/place_order')
def place_order():

    if 'user_id' not in session:
        return redirect('/login')

    cart_items = list(mongo.db.cart.find({'user_id': session['user_id']}))

    for item in cart_items:

        product = mongo.db.products.find_one({
            '_id': ObjectId(item['product_id'])
        })

        if product:
            mongo.db.orders.insert_one({
                'user_id': session['user_id'],
                'user': session['username'],
                'product_id': item['product_id'],
                'product_name': product['name'],
                'price': product['price'],
                'image': product.get('image', ''),
                'status': 'Order Placed',
                'created_at': datetime.now()
            })

    mongo.db.cart.delete_many({'user_id': session['user_id']})

    return render_template('order_success.html')


# ========================
# ORDERS
# ========================
@app.route('/orders')
def orders():

    if 'user_id' not in session:
        return redirect('/login')

    user_orders = list(mongo.db.orders.find({'user_id': session['user_id']}))

    return render_template('orders.html', orders=user_orders)


# ========================
# AI CHAT (FIXED)
# ========================
@app.route('/ai-chat', methods=['POST'])
def ai_chat():

    question = request.json.get('message')

    products = list(mongo.db.products.find())

    watch_data = ""
    for p in products:
        watch_data += f"Name: {p.get('name','')}, Price: ₹{p.get('price','')}, Description: {p.get('description','')}\n"

    prompt = f"""
    You are an AI shopping assistant.

    Products:
    {watch_data}

    Question:
    {question}

    Only recommend from available products.
    """

    if not llm:
        return jsonify({"reply": "AI not configured"})

    response = llm.invoke(prompt)

    return jsonify({"reply": response.content})


# ========================
# RUN
# ========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)