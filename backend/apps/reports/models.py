from django.db import models
from apps.core.models import Organization, Branch


class DailyBranchStats(models.Model):
    id = models.BigAutoField(primary_key=True)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE,
        related_name='daily_stats', editable=False,
    )
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE)
    stat_date = models.DateField()
    disbursed_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    collections_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    new_clients = models.IntegerField(default=0)
    active_loans = models.IntegerField(default=0)
    overdue_loans = models.IntegerField(default=0)
    par_30 = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    class Meta:
        db_table = 'daily_branch_stats'
        unique_together = ['branch', 'stat_date']
        ordering = ['-stat_date']

    def save(self, *args, **kwargs):
        if self.branch_id and not self.organization_id:
            self.organization_id = self.branch.organization_id
        super().save(*args, **kwargs)