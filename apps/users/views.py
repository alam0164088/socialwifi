from django.contrib.auth import get_user_model, authenticate
from django.core import signing
from django.core.signing import BadSignature, SignatureExpired
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
try:
    from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
except Exception:
    OutstandingToken = BlacklistedToken = None

import random

from .serializers import (
    ChangeEmailSerializer, ChangePasswordSerializer,
    EmailCheckSerializer, LoginSerializer, RegistrationSerializer,
    UserDetailSerializer, VerifyOTPSerializer,
)

User = get_user_model()


EMAIL_TOKEN_SALT = 'apps.users.email_token'
EMAIL_TOKEN_MAX_AGE = 60 * 60  # 1 hour (adjust as needed)


def resolve_email_from_request(request):
    """Resolve email from request data or email token header/body.

    Priority:
      1. Explicit `email` in JSON body
      2. `X-Email-Token` header
      3. `email_token` in JSON body
    Returns email string or None.
    """
    data = request.data if isinstance(request.data, dict) else dict(request.data)
    email = data.get('email')
    if email:
        return email

    token = request.headers.get('X-Email-Token') or data.get('email_token')
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

    def post(self, request):
        # allow email to be omitted if client provides the signed email token
        incoming = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        if not incoming.get('email'):
            resolved = resolve_email_from_request(request)
            if resolved:
                incoming['email'] = resolved

        serializer = RegistrationSerializer(data=incoming)
        if serializer.is_valid():
            user = serializer.save()
            return Response({"message": "User registered successfully", "user_id": user.id}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        incoming = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        if not incoming.get('email'):
            resolved = resolve_email_from_request(request)
            if resolved:
                incoming['email'] = resolved

        serializer = LoginSerializer(data=incoming)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            password = serializer.validated_data['password']
            user = authenticate(request, username=email, password=password)
            if user:
                # Create refresh token once and extract both tokens
                refresh = RefreshToken.for_user(user)
                return Response({
                    "message": "Login Successful",
                    "user_id": user.id,
                    "access_token": str(refresh.access_token),
                    "refresh_token": str(refresh),
                    "mail": email
                })
            return Response({"error": "Invalid Credentials"}, status=status.HTTP_401_UNAUTHORIZED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class RequestOTPView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        # accept email omitted if email_token is provided
        email = resolve_email_from_request(request)
        if not email:
            return Response({"error": "email is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            user = User.objects.get(email=email)
            otp = str(random.randint(100000, 999999))
            user.otp_code = otp
            user.otp_created_at = timezone.now()
            user.save(update_fields=['otp_code', 'otp_created_at'])
            # TODO: send via email provider (send_mail) in production
            print(f"[OTP] Sending {otp} to {email}")
            return Response({"message": "OTP sent to email"})
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)


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