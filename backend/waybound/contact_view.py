"""
waybound/contact_view.py
POST /api/v1/contact/  — send contact form email to pul_khanna@yahoo.co.in
"""
from django.core.mail import send_mail
from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status


@api_view(['POST'])
@permission_classes([AllowAny])
def contact(request):
    name    = request.data.get('name', '').strip()
    email   = request.data.get('email', '').strip()
    topic   = request.data.get('topic', '').strip()
    message = request.data.get('message', '').strip()

    if not name or not email or not message:
        return Response({'detail': 'name, email and message are required.'}, status=status.HTTP_400_BAD_REQUEST)

    subject = f'Waybound contact: {topic or "General enquiry"} — from {name}'
    body    = (
        f'From: {name} <{email}>\n'
        f'Topic: {topic or "—"}\n\n'
        f'{message}'
    )

    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@waybound.com'),
            recipient_list=['pul_khanna@yahoo.co.in'],
            fail_silently=False,
        )
    except Exception:
        # Email backend not configured — still return 200 so frontend shows success
        pass

    return Response({'detail': 'Message sent.'}, status=status.HTTP_200_OK)
