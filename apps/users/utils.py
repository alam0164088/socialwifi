from django.core.mail import EmailMessage
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import User  # Adjust the import based on your project structure
import random

def send_otp_email(otp, recipient_email):
    email = EmailMessage(
        subject="Your OTP Code for HelpMeSpeak",
        body=f"""
        <html>
            <body>
                <p>Hello,</p>
                <p>Your OTP code is: <strong>{otp}</strong></p>
                <p>Please use this code to verify your account. If you did not request this, please ignore this email.</p>
                <br>
                <p>Thank you,<br>HelpMeSpeak Team</p>
            </body>
        </html>
        """,
        from_email="no-reply@helpmespeak.app",
        to=[recipient_email],
    )
    email.content_subtype = "html"  # Set the email content type to HTML
    email.send()

class RequestOTPView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        # Resolve email from request
        email = resolve_email_from_request(request)
        if not email:
            return Response({"error": "email is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            user = User.objects.get(email=email)
            otp = str(random.randint(100000, 999999))
            user.otp_code = otp
            user.otp_created_at = timezone.now()
            user.save(update_fields=['otp_code', 'otp_created_at'])

            # Send OTP via email
            subject = "Your OTP Code"
            message = f"""
            Hello,

            Your OTP code is: {otp}

            Please use this code to verify your account. If you did not request this, please ignore this email.

            Thank you,
            HelpMeSpeak Team
            """
            recipient_list = [email]
            try:
                send_mail(
                    subject,
                    message,
                    'no-reply@helpmespeak.app',  # Use the same email as EMAIL_HOST_USER
                    recipient_list,
                    fail_silently=False,
                )
                print(f"[OTP] Sending {otp} to {email}")
                return Response({"message": "OTP sent to email"})
            except Exception as e:
                print(f"❌ Failed to send email: {e}")
                return Response({"error": "Failed to send OTP email"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)