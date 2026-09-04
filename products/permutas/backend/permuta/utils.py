from django.db import transaction


def generate_sequential_code(prefix, model, field='codigo', width=4):
    with transaction.atomic():
        last_obj = model.objects.filter(
            **{f'{field}__startswith': prefix}
        ).order_by(f'-{field}').select_for_update().first()
        
        if last_obj:
            last_code = getattr(last_obj, field)
            last_number = int(last_code[len(prefix):])
            new_number = last_number + 1
        else:
            new_number = 0
        
        if new_number > 99999:
            raise ValueError(f'Maximum code limit reached for prefix {prefix}')
        
        new_code = f'{prefix}{str(new_number).zfill(width)}'
        return new_code
