from rest_framework.throttling import ScopedRateThrottle


class SearchRateThrottle(ScopedRateThrottle):
    """
    Custom throttle for search/autocomplete endpoints.
    Uses the 'search' rate defined in settings.DEFAULT_THROTTLE_RATES
    """
    scope = 'search'
