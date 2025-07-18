"""
Django DRF Extensions - Enhanced operations for Django REST Framework

Provides a unified mixin that enhances standard ViewSet endpoints with intelligent 
sync/async routing and adds /bulk/ endpoints for background processing.
"""

__version__ = "0.1.0"
__author__ = "Konrad Beck"
__email__ = "konrad.beck@merchantcapital.co.za"

# Make common imports available at package level
from .mixins import OperationsMixin
from .views import OperationStatusView

__all__ = [
    "OperationsMixin",
    "OperationStatusView",
]