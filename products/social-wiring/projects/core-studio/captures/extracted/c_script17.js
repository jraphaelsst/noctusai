
        $('form#customers-workspace-create').submit(function(e) {
            "use strict";

            e.preventDefault();

            const getPath = () => location.pathname.startsWith('/dashboard/admin/team') ?
                "/dashboard/admin/team" :
                "/dashboard/admin/customers";

            const baseUrl = window.location.origin;


            $('#create_workspace').prop('disabled', true);
            $('#create_workspace').text('Aguarde criando...');

            var formData = new FormData(this);

            $.ajax({
                type: "post",
                url: baseUrl + getPath() + "/workspace/create",
                data: formData,
                contentType: false,
                processData: false,
                success: function(data) {
                    toastr[data.type](data.message);

                    if (data.refresh) {
                        setTimeout(function() {
                            window.location.reload();
                        }, 1000);
                    }
                },
                error: function(data) {
                    // Trata apenas erros não relacionados ao CSRF
                    if (data.status !== 419 && (!data.responseJSON || !data.responseJSON.message
                            .toLowerCase().includes('csrf'))) {
                        if (data.responseJSON && (data.responseJSON.error || data.responseJSON
                                .errors)) {
                            if (data.responseJSON.errors) {
                                var errors = data.responseJSON.errors;
                                $.each(errors, function(index, value) {
                                    toastr.error(value);
                                });
                            } else {
                                toastr.error(data.responseJSON.message);
                            }
                        } else {
                            toastr.error('Ocorreu um erro ao atualizar o cliente.');
                        }
                    }

                    $('#create_workspace').prop('disabled', false);
                    $('#create_workspace').html(
                        '<svg  xmlns="http://www.w3.org/2000/svg"  width="24"  height="24"  viewBox="0 0 24 24"  fill="none"  stroke="currentColor"  stroke-width="2"  stroke-linecap="round"  stroke-linejoin="round"  class="icon icon-tabler icons-tabler-outline icon-tabler-plus"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M12 5l0 14" /><path d="M5 12l14 0" /></svg>Criar'
                    );
                }
            });
            return false;
        })
    