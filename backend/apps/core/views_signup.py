from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

# Import the new models we added earlier
from .models import (
    Organization, Branch, User,
    LegalDocument, OrganizationAgreement, AuditLog,
    OrganizationSettings,                                    # ← NEW
)


class SignupSerializer(serializers.Serializer):
    organization_name = serializers.CharField(max_length=200)
    organization_code = serializers.SlugField(max_length=50)
    full_name = serializers.CharField(max_length=200)
    email = serializers.EmailField()
    username = serializers.CharField(max_length=50)
    password = serializers.CharField(write_only=True, min_length=10)
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True)

    # --- NEW: Regulatory identifiers (required for verification) ---
    boz_license_number = serializers.CharField(
        max_length=30,
        required=True,
        error_messages={
            'required': 'Bank of Zambia licence number is required.',
            'blank': 'Bank of Zambia licence number is required.',
        },
    )
    pacra_number = serializers.CharField(
        max_length=30,
        required=True,
        error_messages={
            'required': 'PACRA registration number is required.',
            'blank': 'PACRA registration number is required.',
        },
    )
    tin = serializers.CharField(
        max_length=20, required=False, allow_blank=True,
        help_text='Zambia Revenue Authority Taxpayer Identification Number',
    )

    # --- Legal Agreement Fields ---
    agreed_to_terms = serializers.BooleanField(
        required=True,
        error_messages={'required': 'You must agree to the Terms and Conditions, DPA, and SLA to proceed.'}
    )
    signed_by_name = serializers.CharField(max_length=200, help_text="Full legal name of the signatory")
    signed_by_title = serializers.CharField(max_length=100, help_text="e.g., Managing Director, CEO")


@api_view(['POST'])
@permission_classes([AllowAny])
def signup(request):
    """
    Public self-service signup. Creates:
      - A tenant Organization (is_active=False, pending admin verification)
      - An HQ Branch under it
      - The first HQ_ADMIN user
      - An OrganizationSettings row holding the BoZ licence + PACRA numbers
      - Digital acceptance of all active Legal Documents (ECT Act compliant)

    The new Organization is created INACTIVE. A Nimbus platform admin must
    verify the BoZ licence number and activate the org before the tenant can
    access the platform (see OrganizationAdmin.verify_and_activate).
    """
    s = SignupSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    data = s.validated_data

    # 1. Basic Validation Checks
    if Organization.objects.filter(code=data['organization_code']).exists():
        return Response(
            {'error': 'This organization code is already taken.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if User.objects.filter(username=data['username']).exists():
        return Response(
            {'error': 'This username is already taken.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if User.objects.filter(email=data['email']).exists():
        return Response(
            {'error': 'This email is already registered.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    # Prevent duplicate licence submissions
    if OrganizationSettings.objects.filter(
        boz_license_number=data['boz_license_number']
    ).exists():
        return Response(
            {'error': 'An application with this Bank of Zambia licence number already exists.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        validate_password(data['password'])
    except ValidationError as e:
        return Response({'error': ' '.join(e.messages)}, status=status.HTTP_400_BAD_REQUEST)

    # 2. Atomic Transaction: Create everything or nothing
    with transaction.atomic():
        # Create Organization — INACTIVE until admin verifies BoZ licence
        org = Organization.objects.create(
            code=data['organization_code'],
            name=data['organization_name'],
            email=data['email'],
            phone=data.get('phone', ''),
            subscription_tier='TRIAL',
            is_active=False,                                       # ← CHANGED
        )

        # Create HQ Branch
        hq = Branch.objects.create(
            organization=org,
            code='HQ-001',
            name='Headquarters',
            is_hq=True,
        )

        # Create Admin User
        user = User.objects.create_user(
            username=data['username'],
            email=data['email'],
            password=data['password'],
            first_name=data['full_name'].split(' ')[0],
            last_name=' '.join(data['full_name'].split(' ')[1:]),
            organization=org,
            branch=hq,
            role='HQ_ADMIN',
            is_staff=False,
        )

        # --- NEW: Persist regulatory identifiers for admin verification ---
        OrganizationSettings.objects.create(
            organization=org,
            legal_name=data['organization_name'],
            trading_name=data['organization_name'],
            boz_license_number=data['boz_license_number'],
            pacra_number=data['pacra_number'],
            tin=data.get('tin', ''),
            phone=data.get('phone', ''),
            email=data['email'],
        )

        # 3. Record Digital Signatures for all Active Legal Documents
        active_docs = LegalDocument.objects.filter(is_active=True)
        signed_docs = []

        for doc in active_docs:
            OrganizationAgreement.objects.create(
                organization=org,
                document=doc,
                signed_by=user,
                signed_by_name=data['signed_by_name'],
                signed_by_title=data['signed_by_title'],
                signature_ip=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                signed_at=timezone.now(),
                status='SIGNED',
            )
            signed_docs.append(f"{doc.doc_type} v{doc.version}")

        # 4. Audit Log the Signup and Agreement Acceptance
        AuditLog.objects.create(
            organization=org,
            user=user,
            action='SIGNUP_AND_SIGN_AGREEMENT',
            entity_type='Organization',
            entity_id=org.id,
            new_values={
                'organization_code': org.code,
                'boz_license_number': data['boz_license_number'],
                'pacra_number': data['pacra_number'],
                'signed_documents': signed_docs,
                'signed_by_name': data['signed_by_name'],
                'signed_by_title': data['signed_by_title'],
                'activated': False,
            },
            ip_address=request.META.get('REMOTE_ADDR'),
        )

    # 5. Success Response
    return Response({
        'message': (
            'Account created. Your application is pending verification of your '
            'Bank of Zambia licence. You will be notified once activated.'
        ),
        'organization_code': org.code,
        'username': data['username'],
        'signed_documents': signed_docs,
        'status': 'PENDING_VERIFICATION',
    }, status=status.HTTP_201_CREATED)