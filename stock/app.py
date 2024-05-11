import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy_cockroachdb import run_transaction
from sqlalchemy.orm.exc import NoResultFound, MultipleResultsFound
import uuid
from werkzeug.exceptions import HTTPException

from flask import Flask, jsonify

# NOTE: make sure to run this app.py from this folder, so python app.py so that models are also read correctly from root
sys.path.append("../")
from orm_models.models import Stock

datebase_url = os.environ['DATABASE_URL']

app = Flask("stock-service")

# DATABASE_URL= "cockroachdb://root@localhost:26257/defaultdb?sslmode=disable"

try:
    engine = create_engine(datebase_url, connect_args={'connect_timeout': 5})
except Exception as e:
    print("Failed to connect to database.")
    print(f"{e}")

# Catch all unhandled exceptions
@app.errorhandler(Exception)
def handle_exception(e):
    # pass through HTTP errors
    if isinstance(e, HTTPException):
        return jsonify(error=str(e)), 400
    
    # now you're handling non-HTTP exceptions only
    return jsonify(error=str(e)), 400

class NotEnoughStockException(Exception):
    """Exception class for handling insufficient stock of an item"""
    def __str__(self) -> str:
         return "Stock cannot be negative"




@app.post('/item/create/<price>')
def create_item(price: float):
    item_uuid = uuid.uuid4()
    new_item = Stock(item_id=item_uuid, price=float(price))
    run_transaction(sessionmaker(bind=engine), lambda s: s.add(new_item))
    return jsonify(item_id=item_uuid)

def find_item_helper(session, item_id):
    item = session.query(Stock).filter(Stock.item_id == item_id).one()
    return item


@app.get('/find/<item_id>')
def find_item(item_id: str):

    if not isItemResourceAvailable(item_id):
        return "Item is being used by another transaction", 400

    try:
        ret_item = run_transaction(
            sessionmaker(bind=engine, expire_on_commit=False),
            lambda s: find_item_helper(s, item_id)
        )
        return jsonify(
            stock=ret_item.stock,
            price=ret_item.price
        )
    except NoResultFound:
        return "No item was found", 400
    except MultipleResultsFound:
        return "Multiple items were found while one is expected", 400

def add_stock_helper(session, item_id, amount):
    item = session.query(Stock).filter(Stock.item_id == item_id).one()
    item.stock += amount

@app.post('/add/<item_id>/<int:amount>')
def add_stock(item_id: str, amount: int):

    if not isItemResourceAvailable(item_id):
        return "Item is being used by another transaction", 400

    try:
        run_transaction(
            sessionmaker(bind=engine),
            lambda s: add_stock_helper(s, item_id, amount)
        )
        return '', 200
    except NoResultFound:
        return "No item was found", 400
    except MultipleResultsFound:
        return "Multiple items were found while one is expected", 400

def remove_stock_helper(session, item_id, amount):
    item = session.query(Stock).filter(Stock.item_id == item_id).one()
    if item.stock >= amount:
        item.stock -= amount
    else:
        raise NotEnoughStockException()

@app.post('/subtract/<item_id>/<int:amount>')
def remove_stock(item_id: str, amount: int):
    print("Remove stock started")
    try:
        run_transaction(
            sessionmaker(bind=engine),
            lambda s: remove_stock_helper(s, item_id, amount)
        )
        print("Remove stock ended")
        return '', 200
    except NoResultFound:
        return "No item was found", 400
    except MultipleResultsFound:
        return "Multiple items were found while one is expected", 400
    except NotEnoughStockException as e:
        return str(e), 400

transactions = {}

@app.post('/prepare_subtract/<transaction_id>/<item_id>/<int:amount>')
def prepare_remove_stock(transaction_id, item_id: str, amount: int):
    try:
        session = None
        if transaction_id in transactions:
            session = transactions[transaction_id]["session"]
        else :
            session = sessionmaker(engine)()
            transactions[transaction_id] = {
                                            "session": session,
                                            "item_id": item_id
                                            }

        remove_stock_helper(session, item_id, amount)
        session.flush()

        return 'Ready', 200
    except NoResultFound:
        return "No item was found", 400
    except MultipleResultsFound:
        return "Multiple items were found while one is expected", 400
    except NotEnoughStockException as e:
        return str(e), 400

@app.post('/endTransaction/<transaction_id>/<status>')
def endTransaction(transaction_id, status):
    try:
        if status == 'commit':
            transactions[transaction_id]["session"].commit()
        elif status == 'rollback':
            transactions[transaction_id]["session"].rollback()
        else :
            return 'Unknown status: ' + status, 400
        transactions[transaction_id]["session"].close()
        del transactions[transaction_id]
        return 'Success', 200

    except Exception:
        return 'failure', 400

def isItemResourceAvailable(item_id):
    for key in transactions:
        if transactions[key]["item_id"] == item_id:
            return False
    return True