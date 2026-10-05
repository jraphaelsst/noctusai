
        document.addEventListener('DOMContentLoaded', function() {
            var modalEl = document.getElementById('modal-first-access-tutorial');
            if (!modalEl) return;

            // O backdrop do Bootstrap é anexado ao body, fora do modal — a classe no body
            // limita o escurecimento/blur a este modal e preserva os demais da plataforma.
            modalEl.addEventListener('show.bs.modal', function() {
                document.body.classList.add('first-access-modal-open');
            });
            modalEl.addEventListener('hidden.bs.modal', function() {
                document.body.classList.remove('first-access-modal-open');
            });

            
            function markFirstAccessSeen() {
                var token = document.querySelector('meta[name="csrf-token"]');
                if (!token) return;
                fetch('https://corestudio.ai/dashboard/user/first-access-seen', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRF-TOKEN': token.getAttribute('content'), 'Accept': 'application/json' },
                    body: '{}'
                }).catch(function() {});
            }

            document.getElementById('btn-first-access-trainings').addEventListener('click', markFirstAccessSeen, { once: true });
            document.getElementById('btn-first-access-skip').addEventListener('click', markFirstAccessSeen, { once: true });
        });
    