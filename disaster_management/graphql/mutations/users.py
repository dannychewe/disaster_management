import graphene
from graphql import GraphQLError
import graphql_jwt
from graphql_jwt.decorators import login_required
from django.contrib.auth import authenticate
from disaster_management.apps.core.utils import log_activity
from disaster_management.apps.users.models import PasswordResetOTP, User
from disaster_management.graphql.types.users import UserType
from django.utils import timezone

from disaster_management.utils.notifications import send_otp_email

class CreateUser(graphene.Mutation):
    user = graphene.Field(UserType)
    success = graphene.Boolean()
    message = graphene.String()

    class Arguments:
        email = graphene.String(required=True)
        password = graphene.String(required=True)
        first_name = graphene.String(required=True)
        last_name = graphene.String(required=True)
        phone_number = graphene.String(required=True)

    def mutate(self, info, email, password, first_name, last_name, phone_number):
        if User.objects.filter(email=email).exists():
            raise GraphQLError("Email already registered.")

        # role defaults to CITIZEN via model default
        user = User.objects.create_user(
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            phone_number=phone_number,
        )

        return CreateUser(user=user, success=True, message="User created successfully.")


class AssignRole(graphene.Mutation):
    success = graphene.Boolean()
    message = graphene.String()

    class Arguments:
        user_id = graphene.ID(required=True)
        role_name = graphene.String(required=True)  # "Admin" | "Responder" | "Citizen"

    @login_required
    def mutate(self, info, user_id, role_name):
        actor = info.context.user
        if not actor.is_authenticated:
            raise GraphQLError("Authentication required.")

        # Only Admins can assign roles
        if actor.role != User.RoleChoices.ADMIN:
            raise GraphQLError("Only admins can assign roles.")

        # Normalize and validate role
        normalized = role_name.capitalize()
        valid = [c.value for c in User.RoleChoices]
        if normalized not in valid:
            raise GraphQLError(f"Invalid role. Must be one of: {', '.join(valid)}")

        try:
            target_user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            raise GraphQLError("User not found.")

        target_user.role = normalized
        target_user.save()

        # Log activity
        log_activity(
            user=actor,
            action="update",
            model_name="User",
            object_id=str(target_user.id),
            description=f"Assigned role '{normalized}' to {target_user.email}",
        )

        return AssignRole(success=True, message=f"Role '{normalized}' assigned to {target_user.email}")


class ResignRole(graphene.Mutation):
    success = graphene.Boolean()
    message = graphene.String()

    @login_required
    def mutate(self, info):
        user = info.context.user
        if not user.is_authenticated:
            raise GraphQLError("Authentication required.")

        previous = user.role
        user.role = User.RoleChoices.CITIZEN
        user.save()

        log_activity(
            user=user,
            action="update",
            model_name="User",
            object_id=str(user.id),
            description=f"Resigned from role '{previous}' → 'Citizen'",
        )

        return ResignRole(success=True, message="You are now a 'Citizen'.")
    
class CustomLogin(graphene.Mutation):
    """Custom JWT login with activity logging and optional redirect hint"""

    class Arguments:
        email = graphene.String(required=True)
        password = graphene.String(required=True)

    token = graphene.String()
    user = graphene.Field(UserType)
    success = graphene.Boolean()
    message = graphene.String()
    redirect_path = graphene.String()

    @classmethod
    def mutate(cls, root, info, email, password):
        # 1️⃣ Authenticate user
        user = authenticate(email=email, password=password)
        if user is None:
            raise GraphQLError("Invalid email or password.")

        if not user.is_active:
            raise GraphQLError("Your account is inactive. Contact admin.")

        # 2️⃣ Update last_login
        user.last_login = timezone.now()
        user.save(update_fields=["last_login"])

        # 3️⃣ Generate JWT token
        token = graphql_jwt.shortcuts.get_token(user)

        # 4️⃣ Optional: redirect path hint (for frontend convenience)
        role_redirects = {
            User.RoleChoices.ADMIN: "/",
            User.RoleChoices.RESPONDER: "/",
            User.RoleChoices.CITIZEN: "/",
        }
        redirect_path = role_redirects.get(user.role, "/")

        # 5️⃣ Log login activity
        log_activity(
            user=user,
            action="login",
            model_name="User",
            object_id=str(user.id),
            description=f"{user.email} logged in and obtained JWT token.",
        )

        # 6️⃣ Return response
        return CustomLogin(
            token=token,
            user=user,
            success=True,
            message="Login successful.",
            redirect_path=redirect_path,
        )
        
        
class RegisterCitizen(graphene.Mutation):
    """Public registration for citizens."""

    class Arguments:
        email = graphene.String(required=True)
        password = graphene.String(required=True)
        first_name = graphene.String(required=True)
        last_name = graphene.String(required=True)
        phone_number = graphene.String(required=True)

    user = graphene.Field(UserType)
    success = graphene.Boolean()
    message = graphene.String()

    @classmethod
    def mutate(cls, root, info, email, password, first_name, last_name, phone_number):
        # Check if email already exists
        if User.objects.filter(email=email).exists():
            raise GraphQLError("Email already registered.")

        if User.objects.filter(phone_number=phone_number).exists():
            raise GraphQLError("Phone number already registered.")

        user = User.objects.create_user(
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            phone_number=phone_number,
            role=User.RoleChoices.CITIZEN,  # ensure role
        )

        log_activity(
            user=user,
            action="create",
            model_name="User",
            object_id=str(user.id),
            description="Registered as Citizen via public form.",
        )

        return RegisterCitizen(user=user, success=True, message="Citizen registered successfully.")


# ============================================================
# OTP-BASED PASSWORD FLOWS
# ============================================================

class RequestPasswordResetOTP(graphene.Mutation):
    """Step 1: Request an OTP for password reset."""
    success = graphene.Boolean()
    message = graphene.String()

    class Arguments:
        email = graphene.String(required=True)

    def mutate(self, info, email):
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise GraphQLError("No account found with this email.")

        otp_entry = PasswordResetOTP.create_for_user(user)

        # ✅ Send OTP via email
        send_otp_email(
            subject="[Disaster Management] Password Reset OTP",
            message=f"Hi {user.first_name},\n\nYour password reset OTP is: {otp_entry.code}\n\nIt expires in 10 minutes.\n\nIf you did not request this, please ignore.",
            from_email="dannychewe7@gmail.com",
            recipient_list=[user.email],
            fail_silently=False,
        )

        return RequestPasswordResetOTP(success=True, message="OTP sent to your registered email.")


class VerifyPasswordResetOTP(graphene.Mutation):
    """Step 2: Verify OTP (without resetting password yet)."""
    success = graphene.Boolean()
    message = graphene.String()

    class Arguments:
        email = graphene.String(required=True)
        otp_code = graphene.String(required=True)

    def mutate(self, info, email, otp_code):
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise GraphQLError("Invalid email address.")

        try:
            otp = PasswordResetOTP.objects.filter(user=user, code=otp_code).latest("created_at")
        except PasswordResetOTP.DoesNotExist:
            raise GraphQLError("Invalid OTP code.")

        if not otp.is_valid():
            raise GraphQLError("OTP is expired or already used.")

        return VerifyPasswordResetOTP(success=True, message="OTP verified successfully.")


class ResetPasswordWithOTP(graphene.Mutation):
    """Step 3: Set new password after verifying OTP."""
    success = graphene.Boolean()
    message = graphene.String()

    class Arguments:
        email = graphene.String(required=True)
        otp_code = graphene.String(required=True)
        new_password = graphene.String(required=True)

    def mutate(self, info, email, otp_code, new_password):
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise GraphQLError("User not found.")

        try:
            otp = PasswordResetOTP.objects.filter(user=user, code=otp_code).latest("created_at")
        except PasswordResetOTP.DoesNotExist:
            raise GraphQLError("Invalid OTP code.")

        if not otp.is_valid():
            raise GraphQLError("OTP expired or already used.")

        user.set_password(new_password)
        user.save()

        otp.mark_used()

        send_otp_email(
            subject="[Disaster Management] Password Changed Successfully",
            message=f"Hi {user.first_name},\n\nYour password has been updated successfully.\n\nIf you did not perform this change, please contact support immediately.",
            from_email="dannychewe7@gmail.com",
            recipient_list=[user.email],
            fail_silently=True,
        )

        return ResetPasswordWithOTP(success=True, message="Password reset successful.")


class UpdatePassword(graphene.Mutation):
    """Authenticated password change"""
    success = graphene.Boolean()
    message = graphene.String()

    class Arguments:
        old_password = graphene.String(required=True)
        new_password = graphene.String(required=True)

    @login_required
    def mutate(self, info, old_password, new_password):
        user = info.context.user

        if not user.check_password(old_password):
            raise GraphQLError("Old password is incorrect.")

        user.set_password(new_password)
        user.save()

        return UpdatePassword(success=True, message="Password updated successfully.")

class UserMutation(graphene.ObjectType):
    create_user = CreateUser.Field()
    assign_role = AssignRole.Field()
    resign_role = ResignRole.Field()
    register_citizen = RegisterCitizen.Field()
    token_auth = graphql_jwt.ObtainJSONWebToken.Field()
    verify_token = graphql_jwt.Verify.Field()
    refresh_token = graphql_jwt.Refresh.Field()
    # Custom login
    custom_login = CustomLogin.Field()
    
    # ✅ Password management (OTP based)
    request_password_reset_otp = RequestPasswordResetOTP.Field()
    verify_password_reset_otp = VerifyPasswordResetOTP.Field()
    reset_password_with_otp = ResetPasswordWithOTP.Field()
    update_password = UpdatePassword.Field()
