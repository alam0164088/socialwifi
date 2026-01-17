from django.contrib.auth import get_user_model, authenticate
from django.core import signing
from django.core.mail import send_mail, EmailMessage
from django.core.signing import BadSignature, SignatureExpired
from django.utils import timezone
from django.conf import settings  # ✅ এই লাইন যোগ করুন
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from datetime import timedelta
from django.apps import apps
Subscription = apps.get_model('subscriptions', 'Subscription')
TeamMember = apps.get_model('subscriptions', 'TeamMember')

try:
    from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
except Exception:
    OutstandingToken = BlacklistedToken = None

import random
import requests
from rest_framework.authentication import SessionAuthentication, BasicAuthentication

from .serializers import (
    ChangeEmailSerializer, ChangePasswordSerializer,
    EmailCheckSerializer, LoginSerializer, RegistrationSerializer,
    UserDetailSerializer, VerifyOTPSerializer,
)

User = get_user_model()


EMAIL_TOKEN_SALT = 'apps.users.email_token'
EMAIL_TOKEN_MAX_AGE = 60 * 60  # 1 hour (adjust as needed)


def resolve_email_from_request(request):
    data = request.data if isinstance(request.data, dict) else dict(request.data)
    email = data.get('email')
    if email:
        return email

    # check common header forms and body token
    token = (request.headers.get('X-Email-Token')
             or request.headers.get('x-email-token')
             or request.META.get('HTTP_X_EMAIL_TOKEN')
             or data.get('email_token'))
    if not token:
        return None
    try:
        email = signing.loads(token, salt=EMAIL_TOKEN_SALT, max_age=EMAIL_TOKEN_MAX_AGE)
        return email
    except SignatureExpired:
        return None
    except BadSignature:
        return None


class CheckEmailView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = EmailCheckSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        exists = User.objects.filter(email=email).exists()
        # create a signed, timestamped token so the client can omit email later
        token = signing.dumps(email, salt=EMAIL_TOKEN_SALT)
        if exists:
            return Response({"message": "User exists", "action": "LOGIN", "exists": True, "email_token": token ,"EMAIL": email})
        return Response({"message": "New User", "action": "REGISTER", "exists": False, "email_token": token,"EMAIL": email})


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        incoming = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        if not incoming.get('email'):
            resolved = resolve_email_from_request(request)
            if resolved:
                incoming['email'] = resolved

        serializer = RegistrationSerializer(data=incoming)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        email = incoming.get("email", "").strip().lower()

        # resolve subscription models dynamically to avoid import cycles
        from django.apps import apps as _apps
        Plan = _apps.get_model('subscriptions', 'Plan')
        TeamMember = _apps.get_model('subscriptions', 'TeamMember')
        Subscription = _apps.get_model('subscriptions', 'Subscription')

        # determine requested plan if client provided, else prefer free-trial plan or any active trial plan
        requested = incoming.get('plan_product_id') or incoming.get('plan_id')
        plan = None
        if requested:
            if isinstance(requested, str):
                plan = Plan.objects.filter(product_id=str(requested)).first()
            else:
                plan = Plan.objects.filter(id=requested).first()

        if not plan:
            plan = Plan.objects.filter(is_active=True, product_id__icontains='free-trial').first() \
                   or Plan.objects.filter(is_active=True, trial_days__isnull=False).order_by('-trial_days').first() \
                   or Plan.objects.filter(is_active=True).first()

        # If there's a pending team invite for this email, DO NOT grant team 30-day here.
        # signals.attach_invites_and_grant_team_subscription will handle team-granted 30d after user is created.
        has_invite = TeamMember.objects.filter(invited_email__iexact=email, user__isnull=True).exists()

        sub, created = Subscription.objects.get_or_create(user=user)
        if not has_invite:
            # normal trial flow (honor plan.trial_days when possible)
            try:
                sub.activate_trial(plan=plan)
            except Exception:
                # fallback: set a simple trial using plan.trial_days or 7 days
                now = timezone.now()
                days = getattr(plan, "trial_days", 7) or 7
                sub.plan = plan
                sub.status = "trial"
                sub.trial_start_date = now
                sub.trial_end_date = now + timedelta(days=days)
                sub.renewal_date = sub.trial_end_date
                sub.save(update_fields=["plan", "status", "trial_start_date", "trial_end_date", "renewal_date"])
        else:
            # create baseline record and let signals grant the team 30-day
            sub.plan = plan
            sub.status = "trial"
            sub.save(update_fields=["plan", "status"])

        return Response({"message": "User registered successfully", "user_id": user.id}, status=status.HTTP_201_CREATED)


def serialize_subscription(subscription, hide_plan_on_trial=True):
    """Return dict for subscription; hide plan when in trial if requested."""
    plan_obj = subscription.plan
    plan_data = None
    if plan_obj and not (hide_plan_on_trial and subscription.status == 'trial'):
        plan_data = {
            "id": plan_obj.id,
            "name": plan_obj.name,
            "price": str(plan_obj.price),
            "currency": plan_obj.currency,
            "interval": plan_obj.interval,
        }
    return {
        "status": subscription.status,
        "plan": plan_data,
        "trial_start_date": subscription.trial_start_date.isoformat() if subscription.trial_start_date else None,
        "trial_end_date": subscription.trial_end_date.isoformat() if subscription.trial_end_date else None,
        "renewal_date": subscription.renewal_date.isoformat() if subscription.renewal_date else None,
        "is_trial_active": subscription.is_trial_active() if hasattr(subscription, "is_trial_active") else False,
    }


def minimal_subscription_dict(subscription):
    """Return minimal subscription info in the requested shape."""
    status = getattr(subscription, "status", None)
    # determine active flag
    if status == 'active':
        active = subscription.is_subscription_active() if hasattr(subscription, "is_subscription_active") else True
    elif status == 'trial':
        active = subscription.is_trial_active() if hasattr(subscription, "is_trial_active") else False
    else:
        active = False

    # renewal_date: use trial_end_date while on trial, otherwise renewal_date
    renewal = None
    if status == 'trial' and subscription.trial_end_date:
        renewal = subscription.trial_end_date
    elif getattr(subscription, "renewal_date", None):
        renewal = subscription.renewal_date

    # plan label: "trial" while in trial, otherwise plan name or None
    plan_label = "trial" if status == 'trial' else (subscription.plan.name if getattr(subscription, "plan", None) else None)

    return {
        "active": bool(active),
        "need_subscription": not bool(active),
        "status": status,
        "plan": plan_label,
        "renewal_date": renewal.isoformat() if renewal else None,
    }


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []  # disable auth challenge for login

    def post(self, request):
        incoming = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        # debug
        print("[LOGIN] request.headers keys:", list(request.headers.keys()))
        print("[LOGIN] incoming before resolve:", incoming)

        if not incoming.get('email'):
            resolved = resolve_email_from_request(request)
            print("[LOGIN] resolved email from token:", resolved)
            if resolved:
                incoming['email'] = resolved

        serializer = LoginSerializer(data=incoming)
        print("[LOGIN] serializer valid:", serializer.is_valid())
        print("[LOGIN] serializer errors:", serializer.errors)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data['email']
        password = serializer.validated_data['password']

        # try authenticate first
        user = authenticate(request, username=email, password=password)
        print("[LOGIN] authenticate returned:", user)

        # fallback to manual lookup if authenticate failed
        if user is None:
            try:
                user_obj = User.objects.get(email=email)
                if user_obj.check_password(password):
                    user = user_obj
                    print("[LOGIN] manual password check succeeded")
                else:
                    print("[LOGIN] manual password check failed")
            except User.DoesNotExist:
                print("[LOGIN] no user with that email")

        if not user:
            return Response({"error": "Invalid email or password"}, status=status.HTTP_401_UNAUTHORIZED)

        if not getattr(user, "is_active", True):
            return Response({"error": "User account is inactive"}, status=status.HTTP_401_UNAUTHORIZED)

        # tokens and subscription (unchanged)
        refresh = RefreshToken.for_user(user)
        subscription, created = Subscription.objects.get_or_create(user=user)
        if created or not subscription.trial_end_date:
            subscription.activate_trial()

        # build minimal subscription response (plan shown as "trial" during trial)
        subscription_data = minimal_subscription_dict(subscription)

        return Response({
            "message": "Login Successful",
            "user_id": user.id,
            "access_token": str(refresh.access_token),
            "refresh_token": str(refresh),
            "mail": email,
            **subscription_data
        })


class RequestOTPView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = resolve_email_from_request(request)
        if not email:
            return Response({"error": "Email is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            user = User.objects.get(email=email)
            otp = str(random.randint(100000, 999999))
            user.otp_code = otp
            user.otp_created_at = timezone.now()
            user.save(update_fields=['otp_code', 'otp_created_at'])

            # Send OTP via HTML email
            subject = "Your OTP Code for SOCIALWIFI"
            html_message = f"""
            <html>
                <head>
                    <style>
                        body {{
                            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                            background: linear-gradient(135deg, #ff9a9e 0%, #fecfef 50%, #fecfef 100%);
                            margin: 0;
                            padding: 20px;
                            color: #333;
                        }}
                        .container {{
                            max-width: 650px;
                            margin: auto;
                            background: #ffffff;
                            border-radius: 20px;
                            box-shadow: 0 15px 35px rgba(0, 0, 0, 0.3);
                            overflow: hidden;
                            border: 2px solid #ff6b9d;
                        }}
                        .header {{
                            background: linear-gradient(135deg, #ff6b9d 0%, #c44569 100%);
                            padding: 40px 30px;
                            text-align: center;
                            color: #ffffff;
                            position: relative;
                        }}
                        .header h2 {{
                            margin: 0;
                            font-size: 32px;
                            font-weight: 700;
                            text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.3);
                        }}
                        .header .icon {{
                            font-size: 50px;
                            margin-bottom: 10px;
                        }}
                        .content {{
                            padding: 40px 30px;
                        }}
                        .otp-box {{
                            background: linear-gradient(135deg, #ff6b9d 0%, #c44569 100%);
                            padding: 25px;
                            border-radius: 15px;
                            text-align: center;
                            margin: 25px 0;
                            box-shadow: 0 5px 15px rgba(255, 107, 157, 0.4);
                            border: 3px solid #fff;
                        }}
                        .otp-code {{
                            font-size: 42px;
                            font-weight: bold;
                            color: #ffffff;
                            letter-spacing: 8px;
                            font-family: 'Courier New', monospace;
                            text-shadow: 1px 1px 3px rgba(0, 0, 0, 0.5);
                        }}
                        .message {{
                            font-size: 18px;
                            color: #555;
                            line-height: 1.8;
                            margin: 20px 0;
                            text-align: center;
                        }}
                        .highlight {{
                            color: #ff6b9d;
                            font-weight: 700;
                            font-size: 20px;
                        }}
                        .warning {{
                            background: linear-gradient(135deg, #fff3cd 0%, #ffeaa7 100%);
                            border-left: 6px solid #ffc107;
                            padding: 20px;
                            border-radius: 10px;
                            margin: 25px 0;
                            font-size: 16px;
                            color: #856404;
                            box-shadow: 0 3px 10px rgba(255, 193, 7, 0.2);
                        }}
                        .warning .icon {{
                            font-size: 24px;
                            margin-right: 10px;
                        }}
                        .footer {{
                            background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
                            padding: 30px;
                            text-align: center;
                            border-top: 2px solid #ff6b9d;
                        }}
                        .footer p {{
                            margin: 10px 0;
                            color: #666;
                            font-size: 16px;
                        }}
                        .footer strong {{
                            color: #ff6b9d;
                            font-size: 18px;
                        }}
                        .footer .social {{
                            margin-top: 20px;
                        }}
                        .footer .social a {{
                            margin: 0 10px;
                            text-decoration: none;
                            font-size: 24px;
                        }}
                        .cta-button {{
                            display: inline-block;
                            background: linear-gradient(135deg, #ff6b9d 0%, #c44569 100%);
                            color: #ffffff;
                            padding: 15px 30px;
                            border-radius: 25px;
                            text-decoration: none;
                            font-weight: bold;
                            font-size: 18px;
                            margin-top: 20px;
                            box-shadow: 0 5px 15px rgba(255, 107, 157, 0.4);
                        }}
                        .cta-button:hover {{
                            background: linear-gradient(135deg, #c44569 0%, #ff6b9d 100%);
                        }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="header">
                            <div class="icon">🔐✨</div>
                            <h2>OTP Verification for SOCIALWIFI</h2>
                        </div>
                        <div class="content">
                            <p class="message">Hello <span class="highlight">{email}</span>,</p>
                            <p class="message">Thank you for choosing <span class="highlight">SOCIALWIFI</span>! 🌟 Your One-Time Password (OTP) for account verification is:</p>
                            
                            <div class="otp-box">
                                <div class="otp-code">{otp}</div>
                            </div>
                            
                            <p class="message">Please enter this code in the SOCIALWIFI app to login your account. This code is valid for <span class="highlight">15 minutes</span>. ⏰</p>
                            
                            <div class="warning">
                                <span class="icon">⚠️</span> <strong>Security Notice:</strong> Never share this code with anyone. SOCIALWIFI support will never ask for your OTP. Stay safe! 🛡️
                            </div>
                            
                            <p class="message">If you did not request this OTP, please ignore this email or contact our support team immediately. 📧</p>
                            
                            
                        </div>
                        <div class="footer">
                            <p>Thank you for using <strong>SOCIALWIFI</strong>! 💖</p>
                            <p>© 2025 SOCIALWIFI. All rights reserved.</p>
                            <p style="margin-top: 15px; color: #999; font-size: 14px;">This is an automated message. Please do not reply to this email.</p>
                            <div class="social">
                                <a href="#">📘</a>
                                <a href="#">🐦</a>
                                <a href="#">📷</a>
                            </div>
                        </div>
                    </div>
                </body>
            </html>
            """
            
            # ✅ settings.DEFAULT_FROM_EMAIL ব্যবহার করুন (hardcoded email নয়)
            email_message = EmailMessage(
                subject=subject,
                body=html_message,
                from_email=settings.DEFAULT_FROM_EMAIL,  # ✅ এখানে পরিবর্তন করেছি
                to=[email],
            )
            email_message.content_subtype = "html"
            
            # ✅ Error handling যোগ করুন
            try:
                email_message.send(fail_silently=False)
                print(f"[OTP] ✅ Successfully sent OTP {otp} to {email}")
                return Response(
                    {"message": "OTP sent to email", "email": email}, 
                    status=status.HTTP_200_OK
                )
            except Exception as e:
                print(f"[OTP] ❌ Failed to send OTP to {email}: {str(e)}")
                return Response(
                    {"error": f"Failed to send OTP: {str(e)}"}, 
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        except User.DoesNotExist:
            return Response(
                {"error": "User not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )


class OTPLonView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        incoming = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        if not incoming.get('email'):
            resolved = resolve_email_from_request(request)
            if resolved:
                incoming['email'] = resolved

        serializer = VerifyOTPSerializer(data=incoming)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            code = serializer.validated_data['otp_code']
            try:
                user = User.objects.get(email=email)
                # recommended: verify expiry e.g. 10 minutes
                if user.otp_code == code:
                    user.otp_code = None
                    user.save(update_fields=['otp_code'])
                    # create JWT tokens so OTP verification also logs in the user
                    refresh = RefreshToken.for_user(user)
                    return Response({
                        "message": "Verification Successful",
                        "user_id": user.id,
                        "access": str(refresh.access_token),
                        "refresh": str(refresh),
                        "mail": email
                    })
                return Response({"error": "Invalid Code"}, status=status.HTTP_400_BAD_REQUEST)
            except User.DoesNotExist:
                return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ChangePasswordView(APIView):
    """Change password for authenticated users without requiring the old password.

    This endpoint requires a valid access token (JWT) and accepts JSON body:
        { "new_password": "..." }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        if serializer.is_valid():
            new_password = serializer.validated_data['new_password']
            user = request.user
            user.plain_password = new_password
            user.set_password(new_password)
            user.save()
            return Response({"message": "Password changed successfully", "mail": user.email})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class DeleteAccountView(APIView):
    """Delete the authenticated user's account when a valid access token is provided.

    On success returns the deleted user's id and original email.
    If DB cascade fails (missing related tables) fall back to soft-delete but still
    include the original email in the response.
    """
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        user = request.user
        user_id = user.id
        email = user.email  # capture before deletion
        from django.db import OperationalError

        try:
            # Attempt permanent delete (may cascade to related models)
            user.delete()
            return Response({
                "message": "Account deleted successfully",
                "user_id": user_id,
                "email": email
            }, status=status.HTTP_200_OK)
        except OperationalError:
            # Fallback: soft-delete to avoid 500; still return original email for client
            user.is_active = False
            user.email = f"deleted+{user_id}@example.invalid"
            user.set_unusable_password()
            user.save(update_fields=['is_active', 'email', 'password'])
            return Response({
                "message": "account successfully deleted",
                "user_id": user_id,
                "email": email
            }, status=status.HTTP_200_OK)


class ChangeEmailView(APIView):
    """Change authenticated user's email using a signed email token or explicit email.

    Requirements:
      - Authorization: Bearer <access_token> (user must be authenticated)
      - Provide either header X-Email-Token / body email_token OR JSON { "email": "new@example.com" }
    This implementation does NOT rotate JWTs; the current access token remains valid.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        incoming = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)

        # resolve email from token if email not provided explicitly
        if not incoming.get('email'):
            resolved = resolve_email_from_request(request)
            if resolved:
                incoming['email'] = resolved

        serializer = ChangeEmailSerializer(data=incoming)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        new_email = serializer.validated_data['email']

        # prevent duplicate emails (allow unchanged same email for the same user)
        if User.objects.filter(email=new_email).exclude(pk=request.user.pk).exists():
            return Response({"error": "Email already in use"}, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        old_email = user.email
        user.email = new_email
        user.save(update_fields=['email'])

        # DO NOT issue new tokens here — keep user logged in with the existing access token
        return Response({
            "message": "Email changed successfully",
            "user_id": user.id,
            "old_email": old_email,
            "email": new_email
        }, status=status.HTTP_200_OK)


class MeView(APIView):
    """Return authenticated user's details."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserDetailSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)


class LogoutView(APIView):
    """Logout by blacklisting user's refresh tokens.

    - Requires Authorization: Bearer <access_token>
    - If token blacklist app is enabled, all outstanding refresh tokens for the user
      will be blacklisted so the client cannot refresh.
    - Returns 200 on success.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user

        # 1) If client supplies a refresh token, try to blacklist that single token (preferred)
        refresh_token = request.data.get("refresh")
        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                # this will raise AttributeError if blacklist not enabled
                token.blacklist()
                return Response({"message": "Refresh token blacklisted (logout successful)"}, status=status.HTTP_200_OK)
            except AttributeError:
                return Response({
                    "detail": "Token blacklist not enabled on server. Add 'rest_framework_simplejwt.token_blacklist' to INSTALLED_APPS and run migrations."
                }, status=status.HTTP_501_NOT_IMPLEMENTED)
            except Exception:
                return Response({"detail": "Invalid refresh token"}, status=status.HTTP_400_BAD_REQUEST)

        # 2) If no refresh provided, attempt to blacklist all outstanding refresh tokens for the user
        if OutstandingToken is not None and hasattr(OutstandingToken, "objects") and BlacklistedToken is not None:
            blacklisted = 0
            for ot in OutstandingToken.objects.filter(user=user):
                try:
                    BlacklistedToken.objects.get_or_create(token=ot)
                    blacklisted += 1
                except Exception:
                    continue
            return Response({
                "message": "Logged out successfully",
                "blacklisted_refresh_tokens": blacklisted
            }, status=status.HTTP_200_OK)

        # 3) Fallback: token blacklist not available
        return Response({
            "detail": "Token blacklist not configured. To enable: add 'rest_framework_simplejwt.token_blacklist' to INSTALLED_APPS and run makemigrations/migrate. "
                      "Alternatively, send the refresh token in body as {\"refresh\": \"<token>\"} so server can blacklist it."
        }, status=status.HTTP_501_NOT_IMPLEMENTED)


class OCRProcessView(APIView):
    """
    API to process an image file and send it to the OCR server.
    Requires authentication.
    """
    permission_classes = [IsAuthenticated]  # Authentication required

    def post(self, request, *args, **kwargs):
        # Check if an image file is provided
        if 'file' not in request.FILES:  # Update key to 'file'
            return Response({"error": "No image provided"}, status=status.HTTP_400_BAD_REQUEST)

        uploaded_file = request.FILES['file']  # Get the uploaded image file
        
        # OCR server URL
        ocr_url = "http://10.10.7.64:8000/api/ocr/extract"

        try:
            # Send the file to the OCR server
            files = {'file': (uploaded_file.name, uploaded_file.read(), uploaded_file.content_type)}
            response = requests.post(ocr_url, files=files)

            if response.status_code == 200:
                return Response(response.json(), status=status.HTTP_200_OK)
            else:
                return Response({
                    "error": "OCR Server Error",
                    "details": response.text
                }, status=response.status_code)

        except requests.exceptions.RequestException:
            return Response({"error": "Failed to connect to OCR service"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
