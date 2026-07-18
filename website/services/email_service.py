import smtplib
from email.message import EmailMessage
import os
from dotenv import load_dotenv

load_dotenv()

SENDER_EMAIL = os.getenv("SENDER_EMAIL")
APP_PASSWORD = os.getenv("APP_PASSWORD")


def send_price_alert(receiver_email, product_name, current_price, target_price):

    message = EmailMessage()

    message["From"] = SENDER_EMAIL
    message["To"] = receiver_email
    message["Subject"] = "Price Drop Alert!"

    message.set_content(
        f"""
Great news!

Your tracked product has reached your target price.

Product: {product_name}

Current Price: ₹{current_price}

Your Target Price: ₹{target_price}

Happy Shopping!
"""
    )

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:

        smtp.login(
            SENDER_EMAIL,
            APP_PASSWORD
        )

        smtp.send_message(message)

