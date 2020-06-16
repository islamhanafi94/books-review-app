import os
import requests
import json
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, session, render_template, request, flash, redirect, url_for, jsonify
from flask_session import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from flask_bootstrap import Bootstrap
from dotenv import load_dotenv

load_dotenv(verbose=True)

app = Flask(__name__)
bootstrap = Bootstrap(app)
# Check for environment variable
if not os.getenv("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL is not set")

# Configure session to use filesystem
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Set up database
engine = create_engine(os.getenv("DATABASE_URL"))
db = scoped_session(sessionmaker(bind=engine))


@app.route("/")
def index():
    if session.get('user-id'):
        return render_template("home.html")
    return redirect(url_for('login'))


@app.route("/login", methods=['POST', 'GET'])
def login():
    if request.method == 'GET':
        if not session.get('user-id'):
            return render_template("login.html")
        return redirect(url_for('index'))

    username = request.form['username']
    password = request.form['password']

    user = db.execute("SELECT * FROM users where username=:username",
                      {"username": username}).fetchone()

    if user and check_password_hash(user.password, password):
        session['user-id'] = user.id
        print(type(session), session)
        flash("You've successfully logged in!")
        return redirect(url_for('index'))

    return "No"


@app.route("/register", methods=["POST", "GET"])
def register():
    if request.method == 'GET':
        if not session.get('user-id'):
            return render_template("register.html")
        return redirect(url_for('index'))

    # validate input and check if username is not already taken

    username = request.form['username']
    password = request.form['password']
    repeted_password = request.form['checkPassword']

    username_errors = validate_username(username)
    password_errors = validatePassword(password, repeted_password)
    errors = {"username": username_errors,
              "password": password_errors}
    if username_errors or password_errors:
        return render_template("register.html", errors=errors)

    hashed_password = generate_password_hash(password)
    db.execute("INSERT INTO users (username,password) VALUES (:username,:password)",
               {"username": username, "password": hashed_password})
    db.commit()
    return redirect(url_for("login"))


@app.route("/logout", methods=["GET", "DELETE"])
def logout():
    session.pop('user-id', None)
    return redirect(url_for('index'))


@app.route("/search")
def search():
    if not session.get('user-id'):
        return redirect(url_for('login'))

    search_result = []
    search_word = '%'+request.args.get('search_value', '')+'%'
    search_result = db.execute(
        "SELECT * FROM books WHERE isbn LIKE :search_word OR title LIKE :search_word OR author LIKE :search_word", {"search_word": search_word}).fetchall()
    print(type(search_result), search_result)
    return render_template('search-result.html', books_list=search_result)


@app.route("/books/<isbn>")
def book_page(isbn):
    if not session.get('user-id'):
        return redirect(url_for('login'))

    res = requests.get("https://www.goodreads.com/book/review_counts.json",
                       params={"key": os.getenv('GOODREADS_API_KEY'), "isbns": isbn})
    book_data = db.execute(
        "SELECT * FROM books WHERE isbn=:isbn", {"isbn": isbn}).fetchone()

    book = {"title": book_data[1],
            "author": book_data[2],
            "year": book_data[3],
            "isbn": isbn,
            "ratings_count": res.json()['books'][0]['work_ratings_count'] or None,
            "average_rating": res.json()['books'][0]['average_rating'] or None
            }
    # reviews = db.execute(
    #     "SELECT * FROM users_reviews WHERE book_id=:book_id", {"book_id": isbn}).fetchall()

    reviews = db.execute("select user_id , book_id , review, rating,username from users_reviews , users WHERE book_id=:book_id  AND user_id=users.id",
                         {"book_id": isbn}).fetchall()
    print(reviews)
    return render_template('book.html', book=book, reviews=reviews)


@app.route("/review", methods=["POST"])
def add_review():
    if not session.get('user-id'):
        return redirect(url_for('login'))

    user_id = session.get("user-id")
    book_id = request.form["book_id"]
    review = request.form["review"]
    rating = request.form["rating"]
    print(request.form)

    if db.execute("SELECT * FROM users_reviews WHERE user_id=:user_id AND book_id=:book_id",
                  {"user_id": user_id, "book_id": book_id}).fetchall():
        flash("you have already reviewed this book")
        print("you have already reviewed this book")
        return redirect(url_for("book_page", isbn=book_id))

    db.execute(
        "INSERT INTO users_reviews (user_id,book_id,review,rating) VALUES (:user_id,:book_id,:review,:rating)", {
            "user_id": user_id, "book_id": book_id, "review": review, "rating": rating})
    db.commit()

    return redirect(url_for("book_page", isbn=book_id))


@app.route('/api/<isbn>')
def get_book(isbn):
    book_data = db.execute(
        "SELECT * FROM books WHERE isbn=:isbn", {"isbn": isbn}).fetchone()
    if not book_data:
        return "Page not found", 404
    res = requests.get("https://www.goodreads.com/book/review_counts.json",
                       params={"key": os.getenv('GOODREADS_API_KEY'), "isbns": isbn})

    book = {"title": book_data[1],
            "author": book_data[2],
            "year": book_data[3],
            "isbn": isbn,
            "ratings_count": res.json()['books'][0]['work_ratings_count'] or None,
            "average_rating": res.json()['books'][0]['average_rating'] or None
            }
    return jsonify(book), 201


def validatePassword(password, repetedPassword):
    errors = []
    if not password or not repetedPassword:
        errors.append("please enter password")
    if password != repetedPassword:
        errors.append("password doesn't match")

    return errors


def validate_username(username):
    errors = []
    # username is not empty string
    if not username:
        errors.append("please enter a valid username")
    # max length of usernmae is 30 chars
    if len(username) > 30:
        errors.append("username should no exceed 30 charachters")
    # if in db
    if db.execute("SELECT * FROM users where username=:username", {"username": username}).fetchall():
        errors.append("user already exists!")
    return errors
