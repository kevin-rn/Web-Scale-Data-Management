import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.engine import Connection
from sqlalchemy_cockroachdb import run_transaction
from sqlalchemy.orm.exc import NoResultFound, MultipleResultsFound
from werkzeug.exceptions import HTTPException
import uuid
import json
import requests
from flask import Flask, jsonify


# NOTE: make sure to run this app.py from this folder, so python app.py so that models are also read correctly from root
sys.path.append("../")
from orm_models.models import Order, Cart

stock_url = os.environ['STOCK_URL']
payment_url = os.environ['PAYMENT_URL']
datebase_url = os.environ['DATABASE_URL']

app = Flask("order-service")

try:
    engine = create_engine(datebase_url, connect_args={'connect_timeout': 5})
except Exception as e:
    print("Failed to connect to database.")
    print(f"{e}")


transaction_counter = 0

# Generates new transaction id.
def get_new_transaction_id():
    global transaction_counter
    transaction_counter += 1
    return transaction_counter

# Catch all unhandled exceptions
@app.errorhandler(Exception)
def handle_exception(e):
    # pass through HTTP errors
    if isinstance(e, HTTPException):
        return jsonify(error=str(e)), 400
    
    # now you're handling non-HTTP exceptions only
    return jsonify(error=str(e)), 400




@app.post('/create/<user_id>')
def create_order(user_id):
    order_uuid = uuid.uuid4()
    new_user_order = Order(order_id=order_uuid, user_id=user_id)
    run_transaction(sessionmaker(bind=engine), lambda s: s.add(new_user_order))
    return jsonify(order_id=order_uuid)

def remove_order_helper(session, order_id):
    session.query(Order).filter(Order.order_id == order_id).delete()

@app.delete('/remove/<order_id>')
def remove_order(order_id):
    try:
        run_transaction(
            sessionmaker(bind=engine),
            lambda s: remove_order_helper(s, order_id)
        )
        return '', 200
    except Exception:
        return "Something went wrong", 400


def add_item_order_helper(session, order_id, item_id):
    new_item_order = Cart(item_id=item_id, order_id=order_id)
    session.add(new_item_order)

@app.post('/addItem/<order_id>/<item_id>')
def add_item(order_id, item_id):
    try:
        run_transaction(
            sessionmaker(bind=engine),
            lambda s: add_item_order_helper(s, order_id, item_id)
        )
        return '',200
    except NoResultFound:
        return "No user_order was found", 400
    except MultipleResultsFound:
        return "Multiple user_orders were found while one is expected", 400

def remove_order_item_helper(session, order_id, item_id):
    session.query(Cart).filter(Cart.order_id == order_id, Cart.item_id == item_id).delete()

@app.delete('/removeItem/<order_id>/<item_id>')
def remove_item(order_id, item_id):
    try:
        run_transaction(
            sessionmaker(bind=engine),
            lambda s: remove_order_item_helper(s, order_id, item_id)
        )
        return '', 200
    except Exception:
        return "Something went wrong!", 400

def find_order_items_helper(session, order_id):
    order_items = session.query(Cart).filter(Cart.order_id == order_id).all()
    return order_items


@app.get('/find/<order_id>')
def find_order(order_id):
    try:
        ret_user_order: Order = run_transaction(
            sessionmaker(bind=engine, expire_on_commit=False),
            lambda s: s.query(Order).filter(Order.order_id == order_id).one()
        )
        ret_order_items: list[Cart] = run_transaction(
            sessionmaker(bind=engine, expire_on_commit=False),
            lambda s: find_order_items_helper(s, order_id)
        )

        if ret_user_order and ret_order_items:
            resp_pay_status = requests.post(f"{payment_url}/status/{ret_user_order.user_id}/{order_id}")
            if resp_pay_status.status_code >= 400:
                return resp_pay_status.text, 400
            status = resp_pay_status.json()['paid']
            items = []
            total_cost = 0.0
            for order_item in ret_order_items:
                resp_stock_price = requests.get(f"{stock_url}/find/{order_item.item_id}")
                if resp_stock_price.status_code >= 400:
                    return resp_stock_price.text, 400
                stock_price = resp_stock_price.json()['price']
                total_cost += float(stock_price)
                items.append(order_item.item_id)
            return jsonify(
                order_id=order_id,
                paid=status, 
                items=items, 
                user_id=ret_user_order.user_id, 
                total_cost=total_cost
            ), 200
        else:
            return 'Something went wrong!', 400
    except NoResultFound:
        return "No user_order was found", 400
    except MultipleResultsFound:
        return "Multiple user_orders were found while one is expected", 400



# @app.post('/checkout/<order_id>')
# def checkout(order_id):
#     try:
#         ret_order = json.loads(find_order(order_id)[0].get_data(as_text=True))
#         status_before = ret_order['paid']
#         resp_pay = requests.post(f"{payment_url}/pay/{ret_order['user_id']}/{ret_order['order_id']}/{ret_order['total_cost']}")
#         if resp_pay.status_code >= 400:
#             return resp_pay.text, 400
#         if not status_before:
#             for item_id in ret_order['items']:
#                 resp_stock = requests.post(f"{stock_url}/subtract/{item_id}/1")
#                 if resp_stock.status_code >= 400:
#                     return resp_stock.text, 400

#         return 'success', 200
#     except Exception as e:
#         return str(e), 400


@app.post('/checkout/<order_id>')
def checkout(order_id):
    print("Checkout started")
    try:
        payment_transaction_id = get_new_transaction_id()

        ret_order = json.loads(find_order(order_id)[0].get_data(as_text=True))
        status_before = ret_order['paid']

        stock_transaction_id = get_new_transaction_id()

        if status_before:
            # Order is already payed.
            return 'transaction already checked out', 400
        else:
            pay_status = requests.post(f"{payment_url}/prepare_pay/{payment_transaction_id}/{ret_order['user_id']}/{ret_order['order_id']}/{ret_order['total_cost']}")
            
            if pay_status.status_code >= 400:
                return pay_status.text, 400      

            stock_subtract_status_list = []
            for idx, item_id in enumerate(ret_order['items']):
                stock_subtract_status_list.append(requests.post(f"{stock_url}/prepare_subtract/{stock_transaction_id}/{item_id}/1"))
                if stock_subtract_status_list[idx].status_code >= 400:
                    return stock_subtract_status_list[idx].text, 400

            all_stock_requests = all([x.status_code == 200 for x in stock_subtract_status_list])
            
            # Check if both services are ready to commit.
            if pay_status and all_stock_requests:
                requests.post(f"{payment_url}/endTransaction/{payment_transaction_id}/commit")
                requests.post(f"{stock_url}/endTransaction/{stock_transaction_id}/commit")
            elif not pay_status:
                # Payment went wrong.
                requests.post(f"{payment_url}/endTransaction/{payment_transaction_id}/rollback")
            else:
                # Reducing the stock went wrong.
                requests.post(f"{stock_url}/endTransaction/{stock_transaction_id}/rollback")
        print("Checkout ended")    
        return 'success', 200
    except Exception as e:
        # add rollback 
        return f'failure {str(e)}', 400


@app.post('/endTransaction/<transaction_id>/<status>')
def endTransaction(transaction_id, status):

    try:
        if status == 'commit':
            transactions[transaction_id].commit()
        elif status == 'rollback':
            transactions[transaction_id].rollback()
        else :
            return 'Unknown status: ' + status, 400
        transactions[transaction_id].close()
        return 'Success', 200

    except Exception:
        return 'failure', 400
