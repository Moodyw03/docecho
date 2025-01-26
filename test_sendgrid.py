from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
import os
from dotenv import load_dotenv

def test_sendgrid():
    try:
        # Load environment variables
        load_dotenv()
        
        # Get configuration
        sender_email = os.getenv('MAIL_DEFAULT_SENDER')
        sendgrid_api_key = os.getenv('SENDGRID_API_KEY')
        
        print(f"Sender email: {sender_email}")
        print(f"SendGrid API key present: {bool(sendgrid_api_key)}")
        
        if not sender_email:
            print("Error: MAIL_DEFAULT_SENDER not configured")
            return
            
        if not sendgrid_api_key:
            print("Error: SENDGRID_API_KEY not configured")
            return
            
        # Create message
        message = Mail(
            from_email=sender_email,
            to_emails=sender_email,
            subject='SendGrid Test Script',
            html_content='<strong>This is a test from the standalone script</strong>'
        )
        
        print("Message created successfully")
        
        # Initialize client
        print("Initializing SendGrid client...")
        sg = SendGridAPIClient(sendgrid_api_key)
        
        # Send email
        print("Sending email...")
        response = sg.send(message)
        
        print(f"Response status code: {response.status_code}")
        print(f"Response headers: {dict(response.headers)}")
        print(f"Response body: {response.body.decode() if response.body else None}")
        
    except Exception as e:
        print(f"Error: {str(e)}")
        if hasattr(e, 'body'):
            print(f"SendGrid error details: {e.body}")

if __name__ == '__main__':
    test_sendgrid() 