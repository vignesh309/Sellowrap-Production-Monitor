from fastapi import APIRouter, Query, File, Form, UploadFile, HTTPException
import smtplib
from email.message import EmailMessage
import os

router = APIRouter()

@router.post("/api/email_oee_report")
async def email_oee_report(
    file: UploadFile = File(...),
    recipient: str = Form("srinivignesh1999@gmail.com")
):
    """Receives generated Excel file from frontend and emails it."""
    
    sender_email = "Sellowrap.rpt@gmail.com"
    # It is highly recommended to pull this from your .env file
    sender_password = os.getenv("EMAIL_APP_PASSWORD") 

    if not sender_password:
        raise HTTPException(status_code=500, detail="Email App Password not configured in .env file.")

    try:
        # Read the incoming Excel file from memory
        file_content = await file.read()

        # Construct the email
        msg = EmailMessage()
        msg['Subject'] = f"Manufacturing Analytics: {file.filename}"
        msg['From'] = sender_email
        msg['To'] = recipient
        msg.set_content("Hello,\n\nPlease find the attached Machine OEE Breakdown Report generated from the Sellowrap Production Monitor.\n\nRegards,\nSellowrap System")

        # Attach the Excel file
        msg.add_attachment(
            file_content,
            maintype='application',
            subtype='vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            filename=file.filename
        )

        # Send the email via Gmail SMTP
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls() # Secure the connection
            server.login(sender_email, sender_password)
            server.send_message(msg)

        return {"message": "Email sent successfully!"}

    except Exception as e:
        print(f"Email Sending Error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to send email.")