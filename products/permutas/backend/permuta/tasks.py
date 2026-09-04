from celery import shared_task
from django.db import transaction
import logging

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name='permuta.sync_all_matches',
    max_retries=3,
    default_retry_delay=60
)
def sync_all_matches(self):
    """
    Asynchronously synchronize all BILATERAL matches.
    
    This task:
    1. Finds all interests (both forward and reverse)
    2. For each interest, finds compatible pairs where BOTH sides have interests
    3. Creates missing matches only when both sides are mutually compatible
    4. Returns count of matches created
    """
    from imovel.models import InteresseImovel, InteresseAutomovel
    from permuta.bilateral_matching import (
        create_bilateral_matches_for_interesse_imovel,
        create_bilateral_matches_for_interesse_automovel,
        create_bilateral_matches_for_interesse_permuta_imovel,
        create_bilateral_matches_for_interesse_permuta_automovel
    )
    from permuta.models import InteressePermutaImovel, InteressePermutaAutomovel
    from django.contrib.auth import get_user_model
    
    User = get_user_model()
    
    matches_created = 0
    
    try:
        system_user = User.objects.filter(is_superuser=True).first()
        if not system_user:
            system_user = User.objects.first()
        
        if not system_user:
            logger.error("No user found to attribute matches")
            return {'error': 'No user found', 'matches_created': 0}
        
        with transaction.atomic():
            for interesse in InteresseImovel.objects.select_related('imovel').all():
                try:
                    count = create_bilateral_matches_for_interesse_imovel(interesse, system_user)
                    matches_created += count
                except Exception as e:
                    logger.warning(f"Error processing InteresseImovel {interesse.id}: {e}")
            
            for interesse in InteresseAutomovel.objects.select_related('imovel').all():
                try:
                    count = create_bilateral_matches_for_interesse_automovel(interesse, system_user)
                    matches_created += count
                except Exception as e:
                    logger.warning(f"Error processing InteresseAutomovel {interesse.id}: {e}")
            
            for interesse in InteressePermutaImovel.objects.select_related('permuta_imovel').all():
                try:
                    count = create_bilateral_matches_for_interesse_permuta_imovel(interesse, system_user)
                    matches_created += count
                except Exception as e:
                    logger.warning(f"Error processing InteressePermutaImovel {interesse.id}: {e}")
            
            for interesse in InteressePermutaAutomovel.objects.select_related('permuta_automovel').all():
                try:
                    count = create_bilateral_matches_for_interesse_permuta_automovel(interesse, system_user)
                    matches_created += count
                except Exception as e:
                    logger.warning(f"Error processing InteressePermutaAutomovel {interesse.id}: {e}")
        
        logger.info(f"Bilateral match sync completed. Created {matches_created} matches.")
        return {'matches_created': matches_created}
        
    except Exception as exc:
        logger.error(f"Bilateral match sync failed: {exc}")
        raise self.retry(exc=exc)


@shared_task(
    name='permuta.sync_matches_for_interesse_imovel',
    max_retries=3
)
def sync_matches_for_interesse_imovel(interesse_id, user_id):
    """
    BILATERAL sync matches for a specific InteresseImovel.
    Called when an InteresseImovel is created or updated.
    """
    from imovel.models import InteresseImovel
    from permuta.bilateral_matching import create_bilateral_matches_for_interesse_imovel
    from django.contrib.auth import get_user_model
    
    User = get_user_model()
    
    try:
        interesse = InteresseImovel.objects.get(id=interesse_id)
        user = User.objects.get(id=user_id)
        
        count = create_bilateral_matches_for_interesse_imovel(interesse, user)
        
        logger.info(f"Created {count} bilateral matches for InteresseImovel {interesse_id}")
        return {'matches_created': count}
        
    except InteresseImovel.DoesNotExist:
        logger.error(f"InteresseImovel {interesse_id} not found")
        return {'error': 'Interest not found'}
    except Exception as e:
        logger.error(f"Error syncing bilateral matches for interesse {interesse_id}: {e}")
        raise


@shared_task(
    name='permuta.sync_matches_for_interesse_automovel',
    max_retries=3
)
def sync_matches_for_interesse_automovel(interesse_id, user_id):
    """
    BILATERAL sync matches for a specific InteresseAutomovel.
    Called when an InteresseAutomovel is created or updated.
    """
    from imovel.models import InteresseAutomovel
    from permuta.bilateral_matching import create_bilateral_matches_for_interesse_automovel
    from django.contrib.auth import get_user_model
    
    User = get_user_model()
    
    try:
        interesse = InteresseAutomovel.objects.get(id=interesse_id)
        user = User.objects.get(id=user_id)
        
        count = create_bilateral_matches_for_interesse_automovel(interesse, user)
        
        logger.info(f"Created {count} bilateral matches for InteresseAutomovel {interesse_id}")
        return {'matches_created': count}
        
    except InteresseAutomovel.DoesNotExist:
        logger.error(f"InteresseAutomovel {interesse_id} not found")
        return {'error': 'Interest not found'}
    except Exception as e:
        logger.error(f"Error syncing bilateral matches for interesse {interesse_id}: {e}")
        raise


@shared_task(
    name='permuta.sync_matches_for_interesse_permuta_imovel',
    max_retries=3
)
def sync_matches_for_interesse_permuta_imovel(interesse_id, user_id):
    """
    BILATERAL sync matches for a specific InteressePermutaImovel.
    Called when a reverse interest is added to a PermutaImovel.
    """
    from permuta.models import InteressePermutaImovel
    from permuta.bilateral_matching import create_bilateral_matches_for_interesse_permuta_imovel
    from django.contrib.auth import get_user_model
    
    User = get_user_model()
    
    try:
        interesse = InteressePermutaImovel.objects.get(id=interesse_id)
        user = User.objects.get(id=user_id)
        
        count = create_bilateral_matches_for_interesse_permuta_imovel(interesse, user)
        
        logger.info(f"Created {count} bilateral matches for InteressePermutaImovel {interesse_id}")
        return {'matches_created': count}
        
    except InteressePermutaImovel.DoesNotExist:
        logger.error(f"InteressePermutaImovel {interesse_id} not found")
        return {'error': 'Interest not found'}
    except Exception as e:
        logger.error(f"Error syncing bilateral matches for interesse permuta {interesse_id}: {e}")
        raise


@shared_task(
    name='permuta.sync_matches_for_interesse_permuta_automovel',
    max_retries=3
)
def sync_matches_for_interesse_permuta_automovel(interesse_id, user_id):
    """
    BILATERAL sync matches for a specific InteressePermutaAutomovel.
    Called when a reverse interest is added to a PermutaAutomovel.
    """
    from permuta.models import InteressePermutaAutomovel
    from permuta.bilateral_matching import create_bilateral_matches_for_interesse_permuta_automovel
    from django.contrib.auth import get_user_model
    
    User = get_user_model()
    
    try:
        interesse = InteressePermutaAutomovel.objects.get(id=interesse_id)
        user = User.objects.get(id=user_id)
        
        count = create_bilateral_matches_for_interesse_permuta_automovel(interesse, user)
        
        logger.info(f"Created {count} bilateral matches for InteressePermutaAutomovel {interesse_id}")
        return {'matches_created': count}
        
    except InteressePermutaAutomovel.DoesNotExist:
        logger.error(f"InteressePermutaAutomovel {interesse_id} not found")
        return {'error': 'Interest not found'}
    except Exception as e:
        logger.error(f"Error syncing bilateral matches for interesse permuta {interesse_id}: {e}")
        raise


@shared_task(
    name='permuta.sync_matches_for_imovel',
    max_retries=3
)
def sync_matches_for_imovel(imovel_id, user_id):
    """
    BILATERAL sync matches for a specific Imovel (create or update).
    Handles both forward interests and reverse imovel-to-imovel matching.
    """
    from imovel.models import Imovel
    from permuta.bilateral_matching import (
        create_bilateral_matches_for_imovel,
        create_bilateral_matches_for_interesse_imovel,
        create_bilateral_matches_for_interesse_automovel
    )
    from django.contrib.auth import get_user_model

    User = get_user_model()

    try:
        imovel = Imovel.objects.get(id=imovel_id)
        user = User.objects.get(id=user_id)

        count = create_bilateral_matches_for_imovel(imovel, user)

        logger.info(f"Created {count} bilateral matches for Imovel {imovel.ref}")
        return {'matches_created': count}

    except Imovel.DoesNotExist:
        logger.error(f"Imovel {imovel_id} not found")
        return {'error': 'Imovel not found'}
    except Exception as e:
        logger.error(f"Error syncing bilateral matches for imovel {imovel_id}: {e}")
        raise


@shared_task(
    name='permuta.sync_matches_for_imovel_update',
    max_retries=3
)
def sync_matches_for_imovel_update(imovel_id, user_id):
    """
    BILATERAL sync matches for a specific Imovel update.
    Re-runs matching for the imovel itself plus all its interests.
    """
    from imovel.models import Imovel, InteresseImovel, InteresseAutomovel
    from permuta.bilateral_matching import (
        create_bilateral_matches_for_imovel,
        create_bilateral_matches_for_interesse_imovel,
        create_bilateral_matches_for_interesse_automovel
    )
    from django.contrib.auth import get_user_model

    User = get_user_model()

    try:
        imovel = Imovel.objects.get(id=imovel_id)
        user = User.objects.get(id=user_id)

        count = create_bilateral_matches_for_imovel(imovel, user)

        for interesse in imovel.interesses_imoveis_rel.all():
            count += create_bilateral_matches_for_interesse_imovel(interesse, user)
        for interesse in imovel.interesses_automoveis_rel.all():
            count += create_bilateral_matches_for_interesse_automovel(interesse, user)

        logger.info(f"Created {count} bilateral matches for Imovel update {imovel.ref}")
        return {'matches_created': count}

    except Imovel.DoesNotExist:
        logger.error(f"Imovel {imovel_id} not found")
        return {'error': 'Imovel not found'}
    except Exception as e:
        logger.error(f"Error syncing bilateral matches for imovel update {imovel_id}: {e}")
        raise


@shared_task(
    name='permuta.sync_matches_for_permuta_imovel',
    max_retries=3
)
def sync_matches_for_permuta_imovel(permuta_id, user_id):
    """
    BILATERAL sync matches for a specific PermutaImovel (create).
    """
    from permuta.models import PermutaImovel
    from permuta.bilateral_matching import create_bilateral_matches_for_permuta_imovel
    from django.contrib.auth import get_user_model

    User = get_user_model()

    try:
        permuta = PermutaImovel.objects.get(id=permuta_id)
        user = User.objects.get(id=user_id)

        count = create_bilateral_matches_for_permuta_imovel(permuta, user)

        logger.info(f"Created {count} bilateral matches for PermutaImovel {permuta.codigo}")
        return {'matches_created': count}

    except PermutaImovel.DoesNotExist:
        logger.error(f"PermutaImovel {permuta_id} not found")
        return {'error': 'PermutaImovel not found'}
    except Exception as e:
        logger.error(f"Error syncing bilateral matches for permuta imovel {permuta_id}: {e}")
        raise
