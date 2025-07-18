"""
Django DRF Extensions - Enhanced operations for Django REST Framework

Provides mixins for ViewSets to handle efficient async and synchronous operations
using Celery workers with Redis for progress tracking.
"""

__version__ = "0.2.0"
__author__ = "Konrad Beck"
__email__ = "konrad.beck@merchantcapital.co.za"

# Make common imports available at package level
from .mixins import (
    AsyncCreateMixin,
    AsyncDeleteMixin,
    AsyncGetMixin,
    AsyncOperationsMixin,
    AsyncReplaceMixin,
    AsyncUpdateMixin,
    SyncUpsertMixin,
)
from .views import OperationStatusView

__all__ = [
    "AsyncCreateMixin",
    "AsyncDeleteMixin", 
    "AsyncGetMixin",
    "AsyncOperationsMixin",
    "AsyncReplaceMixin",
    "AsyncUpdateMixin",
    "SyncUpsertMixin",
    "OperationStatusView",
]