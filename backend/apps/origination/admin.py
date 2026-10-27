from django.contrib import admin
from .models import (
    WorkflowTemplate, WorkflowStage,
    LoanApplication, ApplicationDocument, ApplicationTransition, ApplicationReview,
    Task, TaskComment, Guarantor,
)


class WorkflowStageInline(admin.TabularInline):
    model = WorkflowStage
    extra = 0
    fields = ['order', 'name', 'role_required', 'sla_hours', 'can_reject', 'is_final']
    ordering = ['order']


@admin.register(WorkflowTemplate)
class WorkflowTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'organization', 'loan_product', 'is_default', 'is_active']
    list_filter = ['organization', 'is_active', 'is_default']
    search_fields = ['name']
    autocomplete_fields = ['organization', 'loan_product']
    inlines = [WorkflowStageInline]


@admin.register(WorkflowStage)
class WorkflowStageAdmin(admin.ModelAdmin):
    list_display = ['template', 'order', 'name', 'role_required', 'is_final']
    list_filter = ['role_required', 'is_final']
    search_fields = ['name', 'template__name']      
    autocomplete_fields = ['template']


class ApplicationDocumentInline(admin.TabularInline):
    model = ApplicationDocument
    extra = 0
    readonly_fields = ['uploaded_at']


class ApplicationTransitionInline(admin.TabularInline):
    model = ApplicationTransition
    extra = 0
    can_delete = False
    readonly_fields = ['from_stage', 'to_stage', 'action', 'user', 'comments', 'created_at']
    
    def has_add_permission(self, request, obj=None): 
        return False


class ApplicationReviewInline(admin.TabularInline):
    model = ApplicationReview
    extra = 0
    readonly_fields = ['created_at']


# --- NEW: Guarantor Inline ---
class GuarantorInline(admin.TabularInline):
    model = Guarantor
    extra = 2        # Show 2 empty slots by default
    max_num = 2      # Enforce a maximum of 2 guarantors
    fields = ['full_name', 'phone_number', 'nrc', 'relationship']
    can_delete = True


@admin.register(LoanApplication)
class LoanApplicationAdmin(admin.ModelAdmin):
    list_display = ['application_number', 'client', 'requested_amount',
                    'status', 'current_stage', 'credit_score_grade', 'submitted_at']
    list_filter = ['status', 'credit_score_grade', 'organization', 'branch']
    search_fields = ['application_number', 'client__first_name', 'client__last_name']
    autocomplete_fields = ['organization', 'branch', 'client', 'loan_product',
                           'loan_officer', 'workflow_template', 'current_stage',
                           'submitted_by', 'decided_by', 'loan', 'created_by']
    readonly_fields = ['id', 'application_number', 'created_at', 'updated_at']
    
    # --- Added GuarantorInline here ---
    inlines = [
        GuarantorInline, 
        ApplicationDocumentInline, 
        ApplicationTransitionInline, 
        ApplicationReviewInline
    ]


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ['title', 'assigned_to', 'priority', 'status', 'due_date', 'created_at']
    list_filter = ['status', 'priority', 'related_type', 'organization']
    search_fields = ['title', 'description']
    autocomplete_fields = ['organization', 'branch', 'assigned_to', 'created_by']
    list_editable = ['status', 'priority']
    list_display_links = ['title']


@admin.register(TaskComment)
class TaskCommentAdmin(admin.ModelAdmin):
    list_display = ['task', 'user', 'created_at']
    autocomplete_fields = ['task', 'user']