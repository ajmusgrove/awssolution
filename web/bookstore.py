""" main code file for the Doubleplusgood Bookstore """

import boto3
from botocore.config import Config
import botocore.exceptions
from flask import Flask, jsonify, request
import stripe
import config  # from terraform, local config takes precedence


STRIPE_PUBLIC_KEY = "stripe_public_key"

HTML_SUBSTITUTE = "{{TABLE}}"
clientconfig = Config(region_name=config.AWS_REGION)
STATIC_FOLDER = 'static'
FRONTDOOR = 'index.html'


def get_ssm_param(param):
    """ retrieves a parameter from the SSM Parameter Store """
    response = ssm_client.get_parameters(Names=[param])
    if len(response['Parameters']) != 1:
        raise KeyError(f"Cannot get SSM Parameter {param}")

    return response['Parameters'][0]['Value']


def read_file(filename):
    """ returns the full contents of a file """
    with open(filename, 'r', encoding='utf-8') as file:
        data = file.read()
        file.close()
        return data


def prepare_html(html, sub_value):
    """ handles substitutions in HTLL. Terribly written, need to change """
    sub_value = sub_value.replace("&", "&amp;")
    return html.replace(HTML_SUBSTITUTE, sub_value)


def generate_table():
    """ Generates the HTML table that is the product
        list for the front page """
    records = ddb_client.scan(
        TableName=config.BOOKS_TABLE,
        Select='ALL_ATTRIBUTES'
    )

    ret = ""

    for i in records['Items']:
        price = int(i['price']['N'])
        price_display = f"{price // 100}.{price % 100}"
        row = f"""
      <tr>
        <td>{i['title']['S']}</td>
        <td>{i['author']['S']}</td>
        <td>{price_display}</td>
        <td>
            <a href="checkout.html?isbn={i['ISBN13']['S']}">Buy</a>
        </td>
      </tr>
    """
        ret += row

    return ret


def send_to_fulfillment(session):
    """ Once the payment is complete, we send off to fulfillment. This will
        move to the backend probably because it is too difficult to secure here
        """
    isbn = session.metadata.isbn
    customer_email = session.customer_details.email
    print(f"Need to fulfill {isbn} for {customer_email}")


# need to define before the routes. a little out of place here but no choice
app = Flask(__name__, static_url_path='', static_folder=f'{STATIC_FOLDER}')


@app.route('/', methods=['GET'])
@app.route('/index.html', methods=['GET'])
def front_door():
    """ returns the front page book list """
    return prepare_html(
        read_file(f"{STATIC_FOLDER}/{FRONTDOOR}"), generate_table())


@app.route('/create-checkout-session', methods=['POST'])
def create_checkout_session():
    """ starting point for the hook into Stripe for the checkout """
    try:
        isbn = request.form.get('isbn')
        print(isbn)
        book = ddb_client.query(
          TableName=config.BOOKS_TABLE,
          KeyConditionExpression="ISBN13 = :isbn",
          ExpressionAttributeValues={
            ':isbn': {'S': isbn}
          }
        )
        print('count is ' + str(book['Count']))
        if book['Count'] != 1:
            print(f"Could not find ISBN {isbn}")
            # TO-DO syslog

        item = book['Items'][0]

        print(request.host_url)

        session = stripe.checkout.Session.create(
            metadata={
              "isbn": isbn,
              "fulfilled": False
            },
            ui_mode='embedded',
            line_items=[
                {
                    'price_data':
                    {
                        'product_data': {
                            'name': item['title']['S']
                         },
                        'unit_amount': item['price']['N'],
                        'currency': 'usd',
                        'tax_behavior': 'inclusive'
                    },
                    'quantity': 1,
                },
            ],
            mode='payment',
            return_url=request.host_url
            + 'return.html?session_id={CHECKOUT_SESSION_ID}',
        )
    except stripe.error.StripeError as ex:
        print(ex)
        return str(ex)
    except botocore.exceptions.BotoCoreError as ex:
        print(ex)
        return str(ex)
    except boto3.exceptions.Boto3Error as ex:
        print(ex)
        return str(ex)

    return jsonify(clientSecret=session.client_secret)


@app.route('/session-status', methods=['GET'])
def session_status():
    """ retries session status for display on the thank you page """
    session = stripe.checkout.Session.retrieve(request.args.get('session_id'))

    send_to_fulfillment(session)

    return jsonify(status=session.status,
                   customer_email=session.customer_details.email)


ssm_client = boto3.client("ssm", config=clientconfig)
ddb_client = boto3.client("dynamodb", config=clientconfig)

stripe.api_key = get_ssm_param(STRIPE_PUBLIC_KEY)

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=config.INTERNAL_PORT)
