from flask import Flask, render_template, request, redirect, session
from flask_pymongo import PyMongo
from bson.objectid import ObjectId
import bcrypt
import os
from werkzeug.utils import secure_filename
from config import Config

app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = "secret"

UPLOAD_FOLDER = "static/uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

print("MONGO_URI =", app.config.get("MONGO_URI"))

mongo = PyMongo(app)
# -----------------------------
# HOME
# -----------------------------@app.route('/')
@app.route('/')
def home():
    return "Hello Railway"
# REGISTER
# -----------------------------
@app.route('/register', methods=['GET', 'POST'])
def register():

    if request.method == 'POST':

        username = request.form['username']
        password = request.form['password']

        existing = mongo.db.users.find_one(
            {'username': username}
        )

        if existing:
            return "User Already Exists"

        hashed = bcrypt.hashpw(
            password.encode('utf-8'),
            bcrypt.gensalt()
        ).decode('utf-8')

        mongo.db.users.insert_one({
            'username': username,
            'password': hashed,
            'role': 'admin'   # change to 'user' if needed
        })

        return redirect('/login')

    return render_template('register.html')

# -----------------------------
# LOGIN
# -----------------------------
@app.route('/login', methods=['GET', 'POST'])
def login():

    if request.method == 'POST':

        username = request.form['username']
        password = request.form['password']

        user = mongo.db.users.find_one(
            {'username': username}
        )

        if user:

            stored_password = user['password']

            if isinstance(stored_password, str):
                stored_password = stored_password.encode('utf-8')

            if bcrypt.checkpw(
                password.encode('utf-8'),
                stored_password
            ):

                session['user_id'] = str(user['_id'])
                session['username'] = user['username']
                session['role'] = user.get('role', 'user')

                return redirect('/')

        return "Invalid Login"

    return render_template('login.html')

# -----------------------------
# LOGOUT
# -----------------------------
@app.route('/logout')
def logout():

    session.clear()
    return redirect('/')

# -----------------------------
# ADMIN DASHBOARD
# -----------------------------
@app.route('/admin')
def admin():

    products = list(mongo.db.products.find())

    total_products = mongo.db.products.count_documents({})
    total_users = mongo.db.users.count_documents({})
    total_orders = mongo.db.orders.count_documents({})

    return render_template(
        'admin.html',
        products=products,
        total_products=total_products,
        total_users=total_users,
        total_orders=total_orders
    )

# -----------------------------
# ADD PRODUCT
# -----------------------------
@app.route('/add_product', methods=['GET', 'POST'])
def add_product():

    if request.method == 'POST':

        filename = ""

        if 'image' in request.files:
            file = request.files['image']

            if file.filename != "":
                filename = secure_filename(file.filename)

                file.save(
                    os.path.join(
                        app.config['UPLOAD_FOLDER'],
                        filename
                    )
                )

        mongo.db.products.insert_one({

            'name': request.form['name'],
            'price': request.form['price'],
            'description': request.form['description'],
            'image': filename

        })

        return redirect('/admin')

    return render_template('add_product.html')

# -----------------------------
# EDIT PRODUCT
# -----------------------------
@app.route('/edit_product/<id>', methods=['GET', 'POST'])
def edit_product(id):

    product = mongo.db.products.find_one(
        {'_id': ObjectId(id)}
    )

    if request.method == 'POST':

        mongo.db.products.update_one(
            {'_id': ObjectId(id)},
            {
                '$set': {
                    'name': request.form['name'],
                    'price': request.form['price'],
                    'description': request.form['description']
                }
            }
        )

        return redirect('/admin')

    return render_template(
        'edit_product.html',
        product=product
    )

# -----------------------------
# DELETE PRODUCT
# -----------------------------
@app.route('/delete_product/<id>')
def delete_product(id):

    mongo.db.products.delete_one(
        {'_id': ObjectId(id)}
    )

    return redirect('/admin')

# -----------------------------
# ADD TO CART
# -----------------------------
@app.route('/add_to_cart/<id>')
def add_to_cart(id):

    if 'user_id' not in session:
        return redirect('/login')

    mongo.db.cart.insert_one({
        'user_id': session['user_id'],
        'product_id': id
    })

    return redirect('/')

# -----------------------------
# CART
# -----------------------------
@app.route('/cart')
def cart():

    if 'user_id' not in session:
        return redirect('/login')

    items = []

    cart_items = mongo.db.cart.find({
        'user_id': session['user_id']
    })

    for item in cart_items:

        product = mongo.db.products.find_one({
            '_id': ObjectId(item['product_id'])
        })

        if product:
            items.append(product)

    return render_template(
        'cart.html',
        items=items
    )

# -----------------------------
# REMOVE CART ITEM
# -----------------------------
@app.route('/remove_cart/<id>')
def remove_cart(id):

    if 'user_id' not in session:
        return redirect('/login')

    mongo.db.cart.delete_one({
        'user_id': session['user_id'],
        'product_id': str(id)
    })

    return redirect('/cart')

# -----------------------------
# PLACE ORDER
# -----------------------------
@app.route('/place_order')
def place_order():

    if 'user_id' not in session:
        return redirect('/login')

    cart_items = mongo.db.cart.find({
        'user_id': session['user_id']
    })

    for item in cart_items:

        mongo.db.orders.insert_one({

            'user_id': session['user_id'],
            'user': session['username'],
            'product_id': item['product_id']

        })

    mongo.db.cart.delete_many({
        'user_id': session['user_id']
    })

    return redirect('/orders')

# -----------------------------
# ORDERS
# -----------------------------
@app.route('/orders')
def orders():

    if 'user_id' not in session:
        return redirect('/login')

    user_orders = list(
        mongo.db.orders.find({
            'user_id': session['user_id']
        })
    )

    return render_template(
        'orders.html',
        orders=user_orders
    )

# -----------------------------
# RUN APP
# -----------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)