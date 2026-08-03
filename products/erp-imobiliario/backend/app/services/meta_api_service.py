"""
Meta API Service — Facebook/Instagram Lead Ads and Campaign sync.

Provides helpers for:
- Syncing leads from Facebook Lead Ads forms
- Syncing campaign metrics from Ads Manager
- Processing webhook events from Meta Lead Ads
"""
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MetaApiConfig:
    """Configuration for Meta Graph API."""

    def __init__(
        self,
        access_token: Optional[str] = None,
        page_id: Optional[str] = None,
        ad_account_id: Optional[str] = None,
        api_version: str = "v18.0",
    ):
        self.access_token = access_token
        self.page_id = page_id
        self.ad_account_id = ad_account_id
        self.api_version = api_version
        self.base_url = f"https://graph.facebook.com/{api_version}"

    @property
    def is_configured(self) -> bool:
        return bool(self.access_token)

    @property
    def headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}


async def sync_leads(config: MetaApiConfig, form_id: Optional[str] = None) -> List[Dict]:
    """
    Fetch leads from Facebook Lead Ads.

    Args:
        config: Meta API configuration
        form_id: Optional specific form ID to sync

    Returns:
        List of lead dicts with field_data
    """
    if not config.is_configured:
        logger.info("[Meta DRY-RUN] Would sync leads")
        return []

    try:
        import httpx

        url = f"{config.base_url}/{config.page_id}/leadgen_forms"
        if form_id:
            url = f"{config.base_url}/{form_id}/leads"

        params = {"access_token": config.access_token, "limit": 100}

        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=30.0)
            if response.status_code != 200:
                logger.error(f"Meta API error: {response.status_code} {response.text}")
                return []

            data = response.json()
            return data.get("data", [])

    except ImportError:
        logger.warning("httpx not installed. Cannot sync leads.")
        return []
    except Exception as e:
        logger.error(f"Meta leads sync error: {e}")
        return []


async def sync_campaigns(config: MetaApiConfig) -> List[Dict]:
    """
    Fetch campaign data from Facebook Ads Manager.

    Returns campaign-level metrics: spend, impressions, clicks, leads.
    """
    if not config.is_configured or not config.ad_account_id:
        logger.info("[Meta DRY-RUN] Would sync campaigns")
        return []

    try:
        import httpx

        url = f"{config.base_url}/act_{config.ad_account_id}/campaigns"
        params = {
            "access_token": config.access_token,
            "fields": "id,name,status,insights{spend,impressions,clicks,actions}",
            "limit": 50,
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=30.0)
            if response.status_code != 200:
                logger.error(f"Meta Campaigns API error: {response.status_code}")
                return []

            data = response.json()
            campaigns = []
            for camp in data.get("data", []):
                insights = camp.get("insights", {}).get("data", [{}])[0]
                actions = insights.get("actions", [])
                lead_count = 0
                for action in actions:
                    if action.get("action_type") == "lead":
                        lead_count = int(action.get("value", 0))

                spend = float(insights.get("spend", 0))
                campaigns.append({
                    "campaign_id": camp["id"],
                    "nome": camp.get("name"),
                    "status": camp.get("status"),
                    "spend": spend,
                    "impressions": int(insights.get("impressions", 0)),
                    "clicks": int(insights.get("clicks", 0)),
                    "leads": lead_count,
                    "cpl": round(spend / lead_count, 2) if lead_count > 0 else None,
                })

            return campaigns

    except ImportError:
        logger.warning("httpx not installed. Cannot sync campaigns.")
        return []
    except Exception as e:
        logger.error(f"Meta campaigns sync error: {e}")
        return []
