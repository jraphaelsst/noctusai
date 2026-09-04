from django.core.management.base import BaseCommand
from permuta.models import Match


class Command(BaseCommand):
    help = 'List all unilateral (non-bilateral) matches in the system'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--delete',
            action='store_true',
            help='Delete unilateral matches (USE WITH CAUTION)',
        )
        parser.add_argument(
            '--mark',
            action='store_true',
            help='Mark unilateral matches with observation',
        )
    
    def handle(self, *args, **options):
        unilateral_matches = Match.objects.filter(is_bilateral=False).select_related(
            'imovel', 'permuta_imovel', 'permuta_automovel', 'imovel_match'
        )
        
        count = unilateral_matches.count()
        
        self.stdout.write(f"\n{'='*60}")
        self.stdout.write(f"Found {count} UNILATERAL matches (without reverse interest)")
        self.stdout.write(f"{'='*60}\n")
        
        if count == 0:
            self.stdout.write(self.style.SUCCESS("All matches are bilateral!"))
            return
        
        for match in unilateral_matches[:50]:
            if match.permuta_imovel:
                match_target = f"PermutaImovel {match.permuta_imovel.codigo}"
            elif match.permuta_automovel:
                match_target = f"PermutaAutomovel {match.permuta_automovel.codigo}"
            elif match.imovel_match:
                match_target = f"Imovel {match.imovel_match.ref}"
            else:
                match_target = "Unknown"
            
            imovel_ref = match.imovel.ref if match.imovel else "N/A"
            self.stdout.write(
                f"  - {match.codigo}: {imovel_ref} -> {match_target} "
                f"[{match.etapa_do_funil}]"
            )
        
        if count > 50:
            self.stdout.write(f"\n  ... and {count - 50} more")
        
        if options['mark']:
            self.stdout.write("\nMarking matches with observation...")
            updated = unilateral_matches.update(
                observacoes='[UNILATERAL] Match criado antes do sistema bilateral'
            )
            self.stdout.write(self.style.SUCCESS(f"Marked {updated} matches"))
        
        if options['delete']:
            confirm = input(f"\nAre you sure you want to DELETE {count} matches? (yes/no): ")
            if confirm.lower() == 'yes':
                deleted, _ = unilateral_matches.delete()
                self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} matches"))
            else:
                self.stdout.write("Deletion cancelled")
