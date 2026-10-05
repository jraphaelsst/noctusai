
    $.ajaxSetup({
        headers: {
            'X-CSRF-TOKEN': $('meta[name="csrf-token"]').attr('content')
        }
    });

    // Interceptador global para erros de CSRF
    $(document).ajaxError(function(event, jqXHR, settings, thrownError) {
        if (jqXHR.status === 419 || // Laravel CSRF token expirado
            (jqXHR.responseJSON && 
            jqXHR.responseJSON.message && 
            jqXHR.responseJSON.message.toLowerCase().includes('csrf'))) {
            
            toastr.error('Sua sessão expirou. A página será recarregada.');
            
            // Recarrega a página após 2 segundos
            setTimeout(function() {
                window.location.reload();
            }, 2000);
        }
    });

    // Adiciona interceptador para renovar token CSRF periodicamente
    setInterval(function() {
        $.get('/csrf-token', function(data) {
            $('meta[name="csrf-token"]').attr('content', data.token);
        });
    }, 30 * 60 * 1000); // Renova a cada 30 minutos
