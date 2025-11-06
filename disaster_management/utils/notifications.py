# core/utils/notifications.py
from django.conf import settings
from django.core.mail import send_mail
from django.contrib.auth import get_user_model
import logging
from disaster_management.apps.notifications.models import Notification, UserNotification
from disaster_management.apps.users.models import User
from django.core.mail import send_mail, EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)
def send_seasonal_alert_email(city, label, confidence):
    User = get_user_model()
    subject = f"[ALERT] Seasonal Outlook: {city} → {label.upper()}"
    message = f"""
Attention,

The seasonal outlook for {city} indicates a **{label.upper()}** rainfall season.
Confidence level: {confidence * 100:.1f}%

Please review the climate response plan.

- Disaster Management System
"""

    # Send to all admins
    recipients = list(User.objects.filter(is_staff=True).values_list('email', flat=True))
    if not recipients:
        return "[!] No admin users found to notify."

    send_mail(
        subject=subject,
        message=message,
        from_email="alerts@disaster-system.local",
        recipient_list=recipients,
        fail_silently=False
    )
    return f"[✓] Sent email to {len(recipients)} admins"


def send_alert(title, message, severity="critical"):
    # 1. Create Notification
    notification = Notification.objects.create(
        title=title,
        message=message,
        severity=severity,
        target_type='global'
    )

    # 2. Get all admin users (you can filter other roles if needed)
    admins = User.objects.filter(roles__name="Admin")

    for admin in admins:
        UserNotification.objects.create(user=admin, notification=notification)

        # 3. Send email
        if admin.email:
            send_mail(
                subject=f"[Alert] {title}",
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[admin.email],
                fail_silently=True
            )

    return f"Notification sent to {admins.count()} admins"


def notify_users(title, message, users, severity="info", html_template=None, context=None):
    """
    Creates an in-app notification AND sends email to target users.

    Args:
        title (str): Notification title
        message (str): Plain-text message
        users (QuerySet or list[User]): Target users
        severity (str): info | warning | critical
        html_template (str, optional): HTML template path for emails
        context (dict, optional): Context for rendering HTML email
    """
    if not users:
        logger.warning("[Notify] No users to notify.")
        return "No users specified."

    # 1️⃣ Create the Notification object
    notification = Notification.objects.create(
        title=title,
        message=message,
        severity=severity,
        target_type="user_list",
    )

    # 2️⃣ Create per-user notification + collect valid emails
    recipient_emails = []
    for user in users:
        UserNotification.objects.create(user=user, notification=notification)
        if user.email:
            recipient_emails.append(user.email)

    # 3️⃣ Send the email to valid recipients
    if recipient_emails:
        _send_email_notification(
            subject=f"[{severity.upper()}] {title}",
            message=message,
            recipient_list=recipient_emails,
            html_template=html_template,
            context=context or {"title": title, "message": message},
        )
        logger.info(f"[Notify] Sent email + in-app notification to {len(recipient_emails)} users.")
        return f"Sent to {len(recipient_emails)} users."
    else:
        logger.warning("[Notify] No email addresses found for recipients.")
        return "Notification created, but no emails sent."


# -------------------------------------------------------------------
# Internal helper for sending safe email with HTML fallback
# -------------------------------------------------------------------
def _send_email_notification(subject, message, recipient_list, html_template=None, context=None):
    """
    Handles the email sending safely with HTML + plaintext fallback.
    """
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@disaster-system.local")

    try:
        if html_template:
            html_content = render_to_string(html_template, context or {})
            text_content = strip_tags(html_content)
            email = EmailMultiAlternatives(subject, text_content, from_email, recipient_list)
            email.attach_alternative(html_content, "text/html")
            email.send(fail_silently=False)
        else:
            send_mail(
                subject=subject,
                message=message,
                from_email=from_email,
                recipient_list=recipient_list,
                fail_silently=False,
            )

    except Exception as e:
        logger.error(f"[Notify] Email sending failed: {e}")
        _fallback_log_email(subject, message, recipient_list)


def _fallback_log_email(subject, message, recipients):
    """
    Writes failed emails to file so they aren't lost.
    """
    file_path = getattr(settings, "EMAIL_FALLBACK_FILE", "/tmp/failed_emails.log")
    try:
        with open(file_path, "a") as f:
            f.write(f"\n--- FAILED EMAIL ---\n")
            f.write(f"To: {', '.join(recipients)}\n")
            f.write(f"Subject: {subject}\n")
            f.write(f"Message:\n{message}\n")
            f.write(f"{'-'*40}\n")
        logger.info(f"[Notify] Fallback log written to {file_path}")
    except Exception as e:
        logger.error(f"[Notify] Could not write fallback log: {e}")
        
        
        
def send_otp_email(user, otp_code, purpose="Password Reset"):
    """
    Sends an OTP email to a user.
    Purpose can be "Password Reset", "Account Verification", etc.
    """

    subject = f"[{settings.PROJECT_NAME if hasattr(settings, 'PROJECT_NAME') else 'Disaster Management'}] {purpose} OTP"

    message = f"""
Hello {user.first_name or 'User'},

Your OTP for {purpose.lower()} is: {otp_code}

🔐 This code is valid for 10 minutes.

If you did not request this, please ignore this message.

Best regards,
Disaster Management System
"""

    try:
        send_mail(
            subject=subject,
            message=message.strip(),
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@disaster-system.local"),
            recipient_list=[user.email],
            fail_silently=False,
        )
        logger.info(f"✅ OTP email sent to {user.email} for {purpose}")
        return True

    except Exception as e:
        logger.error(f"❌ Failed to send OTP email to {user.email}: {e}")
        return False